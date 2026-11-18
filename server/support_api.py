"""Маршруты чатов с раздельным доступом клиента и администратора."""
import base64
import hashlib
import json
from .post_format import parse
import secrets
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from . import store, support as s

PART=32768


class Message(BaseModel):
    key: str = Field(pattern=r'^[A-Za-z0-9-]{16,64}$')
    text: str = Field(default='',max_length=4000)
    filename: str = Field(default='',max_length=180)
    size: int = Field(default=0,ge=0,le=s.MAX_FILE)


class Chunk(BaseModel):
    data: str = Field(max_length=44000)


class News(Message):
    text: str = Field(default='',max_length=20000)
    rich: bool = False
    photo_spoiler: bool = False
    caption_above: bool = False
    hide_link_preview: bool = False
    link_size: Literal['auto','small','large']='auto'
    link_above: bool=False
    destination: Literal["clients","group"]="clients"
    at: int = Field(default=0,ge=0,le=4102444800)


class Receipt(BaseModel):
    reference: str = Field(min_length=1,max_length=100)


def upload_part(key,part,body,ctx):
    import re
    if not re.fullmatch(r'[A-Za-z0-9-]{16,64}',key) or not 0<=part<(s.MAX_FILE+PART-1)//PART:
        raise HTTPException(422,'Некорректная часть файла')
    try: data=base64.b64decode(body.data,validate=True)
    except ValueError: raise HTTPException(422,'Ошибка чтения файла') from None
    if not 0<len(data)<=PART: raise HTTPException(422,'Некорректный размер блока')
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT thread,role FROM support_uploads WHERE key=?',(key,)).fetchone()
        if row is None:
            if conn.execute('SELECT count(*) FROM support_uploads WHERE thread=? AND role=? AND expires>?',(*ctx,store.now())).fetchone()[0]>=4:
                raise HTTPException(429,'Завершите начатые загрузки или повторите через 15 минут')
            conn.execute('INSERT INTO support_uploads VALUES (?,?,?,?)',(key,*ctx,store.now()+900))
        elif tuple(row)!=ctx: raise HTTPException(404)
        conn.execute('UPDATE support_uploads SET expires=? WHERE key=?',(store.now()+900,key))
        conn.execute('INSERT OR REPLACE INTO support_parts VALUES (?,?,?)',(key,part,data))
    return {'ok':True}


def read_upload(conn,body,ctx):
    parts=conn.execute("""SELECT part,bytes FROM support_parts p JOIN support_uploads u ON u.key=p.upload
        WHERE u.key=? AND u.thread=? AND u.role=? AND u.expires>? ORDER BY part""",(body.key,*ctx,store.now())).fetchall()
    if any(r[0]!=i for i,r in enumerate(parts)): raise HTTPException(409,'Загрузите файл повторно')
    data=b''.join(r[1] for r in parts)
    if len(data)!=body.size: raise HTTPException(409,'Загрузка файла не завершена')
    conn.execute('DELETE FROM support_uploads WHERE key=? AND thread=? AND role=?',(body.key,*ctx))
    return data


def router(admin,user):
    api=APIRouter()

    def own(auth=Depends(user)):
        with store.db() as conn:
            return s.client_thread(conn,auth[0]['id']), 'client'

    def managed(thread: str, _=Depends(admin)):
        with store.db() as conn:
            if thread.startswith('c-'):
                exists=conn.execute('SELECT id FROM clients WHERE id=?',(thread[2:],)).fetchone()
                if exists: return s.client_thread(conn,exists[0]), 'admin'
            if thread.startswith('t-') and thread[2:].isdigit():
                exists=conn.execute('SELECT 1 FROM support_messages WHERE thread=? UNION SELECT 1 FROM tg_trials WHERE chat=? LIMIT 1',(thread,thread[2:])).fetchone()
                if exists: return thread, 'admin'
        raise HTTPException(404,'Диалог не найден')

    @api.get('/api/admin/support')
    def inbox(_=Depends(admin)):
        with store.db() as conn:
            rows=conn.execute("""SELECT thread,MAX(id) AS last FROM support_messages WHERE thread NOT LIKE 'g-%' AND role!='bot' AND stamp<=?
                              GROUP BY thread ORDER BY last DESC""",(store.now(),)).fetchall()
            return {'linked':bool(s.option(conn,'admin_chat')), 'groupName':s.option(conn,'post_group_name'), 'threads':[
                {'id':r['thread'],'name':s.thread_name(conn,r['thread'])} for r in rows]}

    @api.post('/api/admin/support/group/refresh')
    def refresh_group(_=Depends(admin)):
        from .telegram import bot_call
        with store.db() as conn:
            target=s.option(conn,'post_group')
        if not target:
            raise HTTPException(409,'Группа Telegram не настроена')
        chat=bot_call('getChat',chat_id=target)
        title=chat.get('title')
        if str(chat.get('id'))!=target or not isinstance(title,str) or not title.strip():
            raise HTTPException(502,'Telegram не вернул название настроенной группы')
        with store.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if s.option(conn,'post_group')!=target:
                raise HTTPException(409,'Группа изменилась. Обновите название ещё раз')
            s.put_option(conn,'post_group_name',title)
        return {'groupName':title}

    @api.post('/api/admin/support/bind')
    def bind(_=Depends(admin)):
        token=secrets.token_urlsafe(24)
        with store.db() as conn:
            s.put_option(conn,'binding',hashlib.sha256(token.encode()).hexdigest())
            s.put_option(conn,'binding_expiry',store.now()+600)
        return {'url':'https://t.me/'+store.CONFIG['telegram_username']+'?start=admin_'+token}

    @api.put('/api/admin/support/news/upload/{key}/{part}')
    def upload_news(key:str,part:int,body:Chunk,_=Depends(admin)):
        return upload_part(key,part,body,('news','admin'))

    @api.post('/api/admin/support/news/preview')
    def preview(body:News,_=Depends(admin)):
        text,entities=parse(body.text.strip(),1024 if body.filename else 4096)
        return {'text':text,'entities':entities}

    @api.post('/api/admin/support/news')
    def news(body: News,_=Depends(admin)):
        text=body.text.strip()
        entities=[]
        if body.rich: text,entities=parse(text,1024 if body.filename else 4096)
        if not text.strip() and not body.filename: raise HTTPException(422,'Добавьте текст или фото')
        if body.filename and len(text)>1024: raise HTTPException(422,'Подпись к фото — до 1024 символов')
        with store.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            campaign=('group:'+body.key) if body.destination=='group' else body.key
            prior=conn.execute('SELECT recipients FROM news_campaigns WHERE key=?',(campaign,)).fetchone()
            if prior: return {'count':prior[0]}
            now=store.now()
            if body.at and body.at<=now: raise HTTPException(422,'Выберите будущее время отправки')
            data=read_upload(conn,body,('news','admin')) if body.filename else None
            if data is not None and not (data.startswith(bytes.fromhex('89504E470D0A1A0A')) or data.startswith(bytes.fromhex('FFD8FF'))):
                raise HTTPException(422,'Выберите изображение JPEG или PNG')
            if body.destination=='group':
                group=s.option(conn,'post_group')
                if not group or not group.startswith('-') or not group[1:].isdigit():
                    raise HTTPException(409,'Группа Telegram не настроена')
                threads=['g-'+group]
            else:
                threads=['t-'+str(r[0]) for r in conn.execute('SELECT chat FROM tg_trials t JOIN clients c ON t.client=c.id WHERE NOT c.deleted')]
            conn.execute('INSERT INTO news_campaigns(key,photo,recipients) VALUES (?,?,?)',(campaign,data,len(threads)))
            for thread in threads:
                message=s.save(conn,thread,'service',text,'news:'+campaign+':'+thread,
                               filename=s.clean_filename(body.filename) if data else '',stamp=body.at or now)
                if body.rich:
                    options={}
                    if entities: options['caption_entities' if data else 'entities']=entities
                    if data:
                        options.update(has_spoiler=body.photo_spoiler,show_caption_above_media=body.caption_above)
                    elif body.hide_link_preview: options['link_preview_options']={'is_disabled':True}
                    elif body.link_above or body.link_size!='auto':
                        card={'show_above_text':body.link_above}
                        if body.link_size!='auto':
                            import re
                            link=next((e['url'] for e in entities if e['type']=='text_link'),None)
                            found=re.search(r'https?://[^\s<>]+',text)
                            if link or found:
                                card['url']=link or found[0]
                                card['prefer_'+body.link_size+'_media']=True
                        options['link_preview_options']=card
                    conn.execute('INSERT INTO publication_format VALUES (?,?)',(message,json.dumps(options)))
                if data: conn.execute('INSERT INTO news_photos VALUES (?,?)',(message,campaign))
        return {'count':len(threads)}

    @api.post('/api/admin/support/{thread}/payment')
    def pay(body: Receipt,ctx=Depends(managed)):
        ref=body.reference.strip()
        if not ref: raise HTTPException(422,'Укажите номер операции')
        thread=ctx[0]
        with store.db() as conn:
            client=thread[2:]
            if thread.startswith('t-'):
                row=conn.execute('SELECT client FROM tg_trials WHERE chat=?',(client,)).fetchone()
                if not row: raise HTTPException(409,'Сначала зарегистрируйте кабинет')
                client=row[0]
            s.payment(conn,client,ref)
        return {'ok':True}

    def chat_routes(prefix, dependency):
        chat=APIRouter(prefix=prefix)

        @chat.get('')
        def history(before: int=0, ctx=Depends(dependency)):
            with store.db() as conn:
                rows=conn.execute("""SELECT m.id,m.role,m.body,m.filename,m.stamp,q.state AS delivery
                    FROM support_messages m LEFT JOIN support_queue q ON q.message=m.id
                    WHERE m.thread=? AND m.stamp<=? AND (?=0 OR m.id<?)
                    ORDER BY m.id DESC LIMIT 61""",(ctx[0],store.now(),before,before)).fetchall()
                return {'messages':[dict(r) for r in reversed(rows[:60])],'older':len(rows)>60}

        @chat.get('/file/{message}')
        def download(message:int,ctx=Depends(dependency)):
            with store.db() as conn:
                row=conn.execute('SELECT m.filename,COALESCE(m.file,c.photo) AS file FROM support_messages m LEFT JOIN news_photos p ON p.message=m.id LEFT JOIN news_campaigns c ON c.key=p.campaign WHERE m.id=? AND m.thread=? AND m.stamp<=? AND (m.file IS NOT NULL OR c.photo IS NOT NULL)',
                                 (message,ctx[0],store.now())).fetchone()
            if not row: raise HTTPException(404,'Файл не найден')
            return Response(row['file'],media_type='application/octet-stream',headers={
                'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['filename'],safe=''),
                'Content-Security-Policy':"default-src 'none'; sandbox"})

        @chat.put('/upload/{key}/{part}')
        def upload(key:str,part:int,body:Chunk,ctx=Depends(dependency)):
            return upload_part(key,part,body,ctx)

        @chat.post('')
        def post(body:Message,ctx=Depends(dependency)):
            thread,role=ctx
            dedup='web:'+thread+':'+role+':'+body.key
            text=body.text.strip()
            if not text and not body.filename: raise HTTPException(422,'Введите сообщение или выберите файл')
            if body.filename and len(text)>1024: raise HTTPException(422,'Подпись файла — до 1024 символов')
            with store.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute('SELECT 1 FROM support_messages WHERE dedup=?',(dedup,)).fetchone(): return {'ok':True}
                if role=='client' and conn.execute("SELECT count(*) FROM support_messages WHERE thread=? AND role='client' AND stamp>?",(thread,store.now()-3600)).fetchone()[0]>=90:
                    raise HTTPException(429,'Слишком много сообщений. Повторите позже')
                data=None
                if body.filename:
                    data=read_upload(conn,body,ctx)
                s.save(conn,thread,role,text,dedup,s.clean_filename(body.filename) if body.filename else '',data)
            return {'ok':True}
        api.include_router(chat)

    chat_routes('/api/account/support',own)
    chat_routes('/api/admin/support/{thread}',managed)
    return api
