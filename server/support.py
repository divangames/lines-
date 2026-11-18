"""Постоянная история переписки, отложенные уведомления и доставка Telegram."""
import asyncio
import hashlib
import json
import logging
import re
import secrets
import time
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

from . import store

MAX_FILE = 8 * 1024**2
LOG = logging.getLogger("linea.support")


def initialize(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS support_messages(
      id INTEGER PRIMARY KEY, thread TEXT NOT NULL, role TEXT NOT NULL, body TEXT NOT NULL,
      filename TEXT NOT NULL DEFAULT '', file BLOB, stamp INTEGER NOT NULL, dedup TEXT UNIQUE);
    CREATE INDEX IF NOT EXISTS support_history ON support_messages(thread,id);
    CREATE TABLE IF NOT EXISTS support_queue(
      id INTEGER PRIMARY KEY, message INTEGER NOT NULL REFERENCES support_messages(id),
      recipient TEXT NOT NULL, due INTEGER NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
      state TEXT NOT NULL DEFAULT 'pending', lease INTEGER NOT NULL DEFAULT 0,
      expiry INTEGER, UNIQUE(message,recipient));
    CREATE INDEX IF NOT EXISTS support_due ON support_queue(state,due);
    CREATE TABLE IF NOT EXISTS publication_format(message INTEGER PRIMARY KEY REFERENCES support_messages(id),options TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS news_campaigns(key TEXT PRIMARY KEY, photo BLOB, recipients INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS news_photos(message INTEGER PRIMARY KEY REFERENCES support_messages(id), campaign TEXT NOT NULL REFERENCES news_campaigns(key));
    CREATE TABLE IF NOT EXISTS support_peers(thread TEXT PRIMARY KEY,name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS support_options(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS support_uploads(
      key TEXT PRIMARY KEY,thread TEXT NOT NULL,role TEXT NOT NULL,expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS support_parts(
      upload TEXT REFERENCES support_uploads(key) ON DELETE CASCADE,part INTEGER,bytes BLOB NOT NULL,
      PRIMARY KEY(upload,part));
    """)
    conn.execute("INSERT OR IGNORE INTO support_options VALUES ('started',?)", (str(store.now()),))


def option(conn, key):
    row = conn.execute("SELECT value FROM support_options WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def put_option(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO support_options VALUES (?,?)", (key, str(value)))


def client_thread(conn, client):
    link = conn.execute('SELECT chat FROM tg_trials WHERE client=?', (client,)).fetchone()
    return 't-'+str(link[0]) if link else 'c-'+client


def thread_name(conn, thread):
    if thread.startswith('t-'):
        row = conn.execute('SELECT c.name FROM clients c JOIN tg_trials t ON c.id=t.client WHERE t.chat=?', (thread[2:],)).fetchone()
        if row: return row[0]
        peer=conn.execute('SELECT name FROM support_peers WHERE thread=?',(thread,)).fetchone()
        return peer[0] if peer else 'Telegram · '+thread[2:]
    row = conn.execute('SELECT name FROM clients WHERE id=?', (thread[2:],)).fetchone()
    return row[0] if row else 'Клиент'


def save(conn, thread, role, body, key, filename='', data=None, stamp=None, expiry=None):
    now = store.now() if stamp is None else stamp
    cur = conn.execute("""INSERT INTO support_messages(thread,role,body,filename,file,stamp,dedup)
        VALUES (?,?,?,?,?,?,?) ON CONFLICT(dedup) DO NOTHING""", (thread,role,body,filename,data,now,key))
    if not cur.rowcount:
        return
    recipient = 'admin' if role=='client' else 'group' if thread.startswith('g-') else 'client' if thread.startswith('t-') else None
    if recipient:
        conn.execute('INSERT INTO support_queue(message,recipient,due,expiry) VALUES (?,?,?,?)',
                     (cur.lastrowid,recipient,now,expiry))
    return cur.lastrowid


def date_label(stamp):
    return datetime.fromtimestamp(stamp,ZoneInfo('Asia/Krasnoyarsk')).strftime('%d.%m.%Y в %H:%M (Красноярск)')


def renewal(conn, client, before, after):
    if before and (not after or after>before):
        text = 'Доступ продлён до '+date_label(after)+'.' if after else 'Ваш доступ теперь без ограничения срока.'
        save(conn,client_thread(conn,client),'service',text,'renew:'+client+':'+str(before)+':'+str(after))


def payment(conn, client, reference):
    key='payment:'+client+':'+hashlib.sha256(reference.encode()).hexdigest()
    save(conn,client_thread(conn,client),'service','Оплата подтверждена. Номер операции: '+reference,key)


def clean_filename(name):
    return re.sub(r'[\x00-\x1f\x7f/\\]', '_', name or 'Вложение')[:180]


def bot_request(method, payload, file=None):
    url = 'https://api.telegram.org/bot'+store.CONFIG['telegram_token']+'/'+method
    if file is None:
        res=httpx.post(url,json=payload,timeout=15)
    else:
        import json
        form={k: json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v).lower() if isinstance(v,bool) else str(v) for k,v in payload.items()}
        res=httpx.post(url,data=form,files={('photo' if method=='sendPhoto' else 'document'):file},timeout=45)
    return res


def incoming(message, handoff=False):
    from .telegram import bot_call
    chat=message['chat']['id']
    text=message.get('text') or message.get('caption','')
    file=None
    kind=''
    for key in ('document','photo','video','audio','voice','animation','video_note','sticker'):
        if message.get(key):
            kind=key
            file=message[key][-1] if key=='photo' else message[key]
            break
    if not text and not file:
        bot_call('sendMessage',chat_id=chat,text='Пришлите текст, фотографию или файл до 8 МБ.')
        return
    thread='t-'+str(chat)
    dedup=f"tg:{chat}:{message['message_id']}"
    with store.db() as conn:
        if conn.execute('SELECT 1 FROM support_messages WHERE dedup=?',(dedup,)).fetchone(): return
        count=conn.execute("SELECT count(*) FROM support_messages WHERE thread=? AND role='client' AND stamp>?",(thread,store.now()-3600)).fetchone()[0]
    if count>=90:
        bot_call('sendMessage',chat_id=chat,text='Достигнут часовой лимит сообщений. Попробуйте позже.')
        return
    name=''
    data=None
    if file:
        if file.get('file_size',0)>MAX_FILE:
            bot_call('sendMessage',chat_id=chat,text='Файл больше 8 МБ. Уменьшите его и отправьте снова.')
            return
        info=bot_call('getFile',file_id=file['file_id'])
        remote=info['file_path']
        if info.get('file_size',0)>MAX_FILE:
            bot_call('sendMessage',chat_id=chat,text='Принимаем файлы до 8 МБ.')
            return
        url='https://api.telegram.org/file/bot'+store.CONFIG['telegram_token']+'/'+quote(remote,safe='/')
        try:
            with httpx.stream('GET',url,timeout=30) as res:
                res.raise_for_status()
                blob=bytearray()
                for chunk in res.iter_bytes():
                    if len(blob)+len(chunk)>MAX_FILE: raise ValueError
                    blob.extend(chunk)
                data=bytes(blob)
        except (ValueError,httpx.HTTPError):
            raise HTTPException(503,'Не удалось получить файл из Telegram') from None
        name=clean_filename(file.get('file_name') or kind+'-'+remote.rsplit('/',1)[-1])
    with store.db() as conn:
        sender=message.get('from',{})
        label=' '.join(filter(None,(sender.get('first_name'),sender.get('last_name')))).strip()[:100]
        if label: conn.execute('INSERT OR REPLACE INTO support_peers VALUES (?,?)',(thread,label))
        identifier = save(conn,thread,'client',text,dedup,name,data)
        if handoff and identifier:
            from . import bot_help
            bot_help.handoff(conn,chat,dedup)


def bind_admin(chat, token):
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        valid=option(conn,'binding') or ''
        if secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(),valid) and int(option(conn,'binding_expiry') or 0)>store.now():
            put_option(conn,'admin_chat',chat)
            put_option(conn,'binding','')
            return 'Уведомления поддержки подключены к этому чату.'
    return 'Ссылка истекла. Получите новую в админке.'


def collect_expiry(conn):
    now=store.now()
    start=int(option(conn,'started'))
    rows=conn.execute("""SELECT c.id,c.expires_at,t.chat FROM clients c JOIN tg_trials t ON c.id=t.client
        WHERE c.enabled AND NOT c.deleted AND c.expires_at BETWEEN ? AND ?""",(start,now+86400))
    for row in rows:
        end=row['expires_at']
        kind='ended' if end<=now else 'near'
        body='Срок тарифа закончился '+date_label(end) if kind=='ended' else 'Срок тарифа заканчивается '+date_label(end)
        save(conn,'t-'+str(row['chat']),'service',body+'.','expiry:'+kind+':'+row['id']+':'+str(end),expiry=end)


def formatted_post(source):
    """Позиции выделений в Bot API измеряются единицами UTF-16."""
    result=[]
    entities=[]
    offset=0
    pos=0
    for match in re.finditer(r'(\*\*|__)([\s\S]+?)\1',source):
        plain=source[pos:match.start()]
        styled=match[2]
        offset+=len(plain.encode('utf-16-le'))//2
        length=len(styled.encode('utf-16-le'))//2
        entities.append({'type':'bold' if match[1]=='**' else 'italic','offset':offset,'length':length})
        result.extend([plain,styled])
        offset+=length
        pos=match.end()
    result.append(source[pos:])
    return ''.join(result),entities


def deliver_one():
    now=store.now()
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute("""SELECT q.id AS job,q.recipient,q.tries,q.expiry,m.* FROM support_queue q
          JOIN support_messages m ON m.id=q.message WHERE q.state='pending' AND q.due<=? AND q.lease<=?
          AND (q.recipient!='admin' OR EXISTS(SELECT 1 FROM support_options WHERE key='admin_chat'))
          ORDER BY q.due,q.id LIMIT 1""",(now,now)).fetchone()
        if not row: return False
        thread=row['thread']
        owner=row['recipient']=='admin'
        chat=option(conn,'admin_chat') if owner else thread[2:]
        photo=conn.execute('SELECT c.photo FROM news_photos p JOIN news_campaigns c ON c.key=p.campaign WHERE p.message=?',(row['id'],)).fetchone() if row['filename'] and row['role']=='service' else None
        fmt=conn.execute('SELECT options FROM publication_format WHERE message=?',(row['id'],)).fetchone() if row['role']=='service' else None
        label=thread_name(conn,thread)
        if row['expiry']:
            current=conn.execute('SELECT c.expires_at,c.enabled,c.deleted FROM clients c JOIN tg_trials t ON t.client=c.id WHERE t.chat=?',(chat,)).fetchone()
            if not current or current[0]!=row['expiry'] or not current[1] or current[2] or (row['dedup'].startswith('expiry:near:') and current[0]<=now):
                conn.execute("UPDATE support_queue SET state='skipped' WHERE id=?",(row['job'],))
                return True
        conn.execute('UPDATE support_queue SET lease=? WHERE id=?',(now+120,row['job']))
    title=('От '+label+'\n' if owner else 'Техподдержка Линии\n' if row['role']=='admin' else '')
    body=title+row['body']
    payload={'chat_id':chat}
    if owner:
        payload['reply_markup']={'inline_keyboard':[[{'text':'Открыть диалог','url':store.BASE_URL+'/admin?chat='+quote(thread)}]]}
    elif row['recipient']!='group':
        payload['reply_markup']={'inline_keyboard':[[{'text':'Кабинет','web_app':{'url':store.BASE_URL+'/account/mini'}},
            {'text':'Техподдержка','url':'https://t.me/'+store.CONFIG['telegram_username']+'?start=support'}]]}
    if row['role']=='bot':
        with store.db() as conn:
            markup=conn.execute('SELECT keyboard FROM telegram_help_replies WHERE message=?',(row['id'],)).fetchone()
        if markup: payload['reply_markup']=json.loads(markup[0])
    limit=1024 if row['file'] is not None else 4096
    if owner and len(body)>limit:
        payload['reply_markup']['inline_keyboard'][0][0]['text']='Открыть диалог · '+label[:40]
        body=row['body']
    if not owner and len(body)>limit:
        body=row['body']
    if fmt:
        payload.update(json.loads(fmt[0]))
    elif row['recipient']=='group':
        body,entities=formatted_post(body)
        if entities: payload['caption_entities' if photo else 'entities']=entities
    state='pending'
    delay=min(3600,10*2**min(row['tries'],8))
    try:
        if photo:
            mime='image/png' if photo[0].startswith(b'\x89PNG') else 'image/jpeg'
            res=bot_request('sendPhoto',{**payload,'caption':body},(row['filename'],photo[0],mime))
        elif row['file'] is not None:
            res=bot_request('sendDocument',{**payload,'caption':body[:1024]},(row['filename'],row['file'],'application/octet-stream'))
        else:
            res=bot_request('sendMessage',{**payload,'text':body[:4096]})
        if res.is_success: state='sent'
        elif res.status_code==429: delay=max(1,int(res.json().get('parameters',{}).get('retry_after',60)))
        elif res.status_code in (400,403): state='failed'
    except (ValueError,httpx.HTTPError):
        pass
    with store.db() as conn:
        conn.execute('UPDATE support_queue SET state=?,tries=tries+1,due=?,lease=0 WHERE id=?',
                     (state,store.now()+delay,row['job']))
    return True


async def worker():
    maintenance=0
    while True:
        try:
            if time.monotonic()>=maintenance:
                def maintain():
                    with store.db() as conn:
                        collect_expiry(conn)
                        conn.execute('DELETE FROM support_uploads WHERE expires<=?',(store.now(),))
                await asyncio.to_thread(maintain)
                maintenance=time.monotonic()+60
            active=await asyncio.to_thread(deliver_one) if store.CONFIG.get('telegram_token') else False
        except Exception:
            LOG.warning('Support delivery will retry')
            active=False
        await asyncio.sleep(0.15 if active else 3)
