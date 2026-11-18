"""Чаты, файлы и уведомления на временной БД без внешних отправок."""
import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as temp:
    pw=secrets.token_urlsafe(20)
    salt=secrets.token_bytes(16)
    cfg=dict(base_url='http://testserver',server_host='vpn.test',development=True,
             admin_password_hash=salt.hex()+':'+hashlib.scrypt(pw.encode(),salt=salt,n=32768,r=8,p=1,maxmem=67108864).hex(),
             secret=secrets.token_hex(24),telegram_username='test_bot',telegram_webhook_secret='mock',state=temp)
    path=Path(temp)/'config.json'
    path.write_text(json.dumps(cfg))
    os.environ['LINEA_CONFIG']=str(path)
    from server import support as s,store,telegram
    from server.app import app
    with TestClient(app) as admin,TestClient(app) as user:
        admin.headers['Origin']=user.headers['Origin']=cfg['base_url']
        admin.headers['X-CSRF-Token']=admin.post('/api/auth/login',json=dict(username='admin',password=pw)).json()['csrf']
        member=admin.post('/api/admin/clients',json={'name':'Клиент','quota_gb':5,'expires_at':store.now()+80000}).json()
        with store.db() as conn:
            conn.execute('INSERT INTO tg_trials VALUES (?,?,?,NULL)',(123,'+12025550123',member['id']))
        user.headers['X-CSRF-Token']=user.post('/api/account/login',json=member['account_credentials']).json()['csrf']
        own='/api/account/support'
        managed='/api/admin/support/t-123'
        def send(client,route,body):
            r=client.post(route,json=body)
            assert r.is_success,(route,r.status_code,r.text)
            return r.json()
        bind=send(admin,'/api/admin/support/bind',{})['url'].split('admin_')[1]
        assert 'подключены' in s.bind_admin(456,bind) and 'истекла' in s.bind_admin(789,bind)
        for client,route,other,other_route in ((user,own,admin,managed),(admin,managed,user,own)):
            key=secrets.token_hex(16);data=os.urandom(41000)
            for part,chunk in enumerate((data[:32768],data[32768:])):
                assert client.put(f'{route}/upload/{key}/{part}',json={'data':base64.b64encode(chunk).decode()}).is_success
            body=dict(key=key,text='Текст и файл',filename='пример.bin',size=len(data))
            send(client,route,body);send(client,route,body)
            item=other.get(other_route).json()['messages'][-1]
            assert item['body']==body['text'] and other.get(other_route+'/file/'+str(item['id'])).content==data
        def incoming(message):
            return user.post('/api/telegram/update',headers={'X-Telegram-Bot-Api-Secret-Token':'mock'},
                json={'message':dict(chat={'id':123,'type':'private'},**{'from':{'id':123}},**message)})
        msg={'message_id':42,'text':'Сообщение из бота'}
        assert incoming(msg).is_success and incoming(msg).is_success
        from contextlib import contextmanager
        @contextmanager
        def blob(*args,**kwargs):
            yield httpx.Response(200,content=b'photo-bytes',request=httpx.Request('GET','https://example.org'))
        with patch.dict(store.CONFIG,telegram_token='test'),patch.object(telegram,'bot_call',return_value={'file_path':'photos/img.jpg'}),patch.object(httpx,'stream',blob):
            assert incoming({'message_id':43,'photo':[{'file_id':'abc'}],'caption':'Фото'}).is_success
        history=user.get(own).json()['messages']
        assert sum(m['role']!='bot' for m in history)==4 and admin.get(managed+'/file/'+str(history[-1]['id'])).content==b'photo-bytes'
        assert TestClient(app).get(own+'/file/'+str(history[-1]['id'])).status_code==401
        assert user.get(managed).status_code==401
        other=admin.post('/api/admin/clients',json={'name':'Другой'}).json()
        with TestClient(app) as stranger:
            stranger.headers['Origin']=cfg['base_url']
            assert stranger.post('/api/account/login',json=other['account_credentials']).is_success
            assert stranger.get(own+'/file/'+str(history[-1]['id'])).status_code==404
        for _ in range(2): send(admin,managed+'/payment',{'reference':'DEMO-1'})
        send(admin,'/api/admin/support/news',dict(key=secrets.token_hex(16),text='Будущая новость',at=store.now()+40000))
        assert all(m['body']!='Будущая новость' for m in user.get(own).json()['messages'])
        with store.db() as conn:
            s.collect_expiry(conn);s.collect_expiry(conn)
        assert admin.put('/api/admin/clients/'+member['id'],json={'name':'Клиент','enabled':True,'expires_at':store.now()+90000}).is_success
        with patch.object(s,'bot_request',return_value=httpx.Response(200,json={'ok':True})) as bot:
            while s.deliver_one(): pass
            calls=bot.call_args_list
            assert any(c.args[0]=='sendDocument' and c.args[1]['chat_id']=='123' for c in calls)
            assert any(c.args[0]=='sendDocument' and c.args[1]['chat_id']=='456' and '?chat=t-123' in str(c.args[1]['reply_markup']) for c in calls)
            assert any('От Клиент' in str(c) and 'Сообщение из бота' in str(c) for c in calls)
            assert sum('DEMO-1' in str(c) for c in calls)==1 and any('продлён' in str(c) for c in calls)
            assert not any('заканчивается' in str(c) for c in calls)
            with store.db() as conn:
                conn.execute('UPDATE clients SET expires_at=? WHERE id=?',(store.now(),member['id']))
                s.collect_expiry(conn);s.collect_expiry(conn)
            while s.deliver_one(): pass
            assert sum('закончился' in str(c) for c in bot.call_args_list)==1
        # Фото хранится один раз и отправляется в назначенную минуту.
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/hzEAAAAASUVORK5CYII=')
        campaign=secrets.token_hex(16)
        news_path='/api/admin/support/news'
        future=store.now()+7200
        assert admin.put(f'{news_path}/upload/{campaign}/0',json={'data':base64.b64encode(image).decode()}).is_success
        body=dict(key=campaign,text='Новость с фото',size=len(image),filename='фото.png',at=future)
        assert admin.post(news_path,json={**body,'at':store.now()-1}).status_code==422
        assert send(admin,news_path,body)==send(admin,news_path,body)=={'count':1}
        assert not any(m['body']==body['text'] for m in user.get(own).json()['messages'])
        with patch.object(store,'now',return_value=future),patch.object(s,'bot_request',return_value=httpx.Response(200)) as bot:
            while s.deliver_one(): pass
            photos=[c for c in bot.call_args_list if c.args[0]=='sendPhoto']
            assert len(photos)==1 and photos[0].args[2][1]==image and photos[0].args[1]['caption']==body['text']
            item=next(m for m in user.get(own).json()['messages'] if m['body']==body['text'])
            assert user.get(own+'/file/'+str(item['id'])).content==image
        with store.db() as conn:
            s.put_option(conn,'post_group','-123456')
        otherkey=secrets.token_hex(16)
        assert admin.put(f'{news_path}/upload/{otherkey}/0',json={'data':base64.b64encode(image).decode()}).is_success
        groupbody={**body,'destination':'group','key':otherkey,'text':'📌 **Новости** __сегодня__'}
        assert send(admin,news_path,groupbody)==send(admin,news_path,groupbody)=={'count':1}
        with patch.object(s,'bot_request',return_value=httpx.Response(200)) as bot:
            while s.deliver_one(): pass
            assert not bot.called
            with patch.object(store,'now',return_value=future):
                while s.deliver_one(): pass
            bot.assert_called_once()
            method,payload,file=bot.call_args.args
            assert method=='sendPhoto' and payload['chat_id']=='-123456' and file[1]==image
            assert payload['caption']=='📌 Новости сегодня' and payload['caption_entities']==[
                {'type':'bold','offset':3,'length':7},{'type':'italic','offset':11,'length':7}]
            assert 'reply_markup' not in payload
        source='📣 [b]Важное [u]сегодня[/u][/b] [spoiler]секрет[/spoiler] [link=https://example.org]сайт[/link]'
        preview=send(admin,news_path+'/preview',{'key':campaign,'text':source})
        assert preview['entities'][0]['offset']==3 and preview['entities'][-1]['url']=='https://example.org'
        assert admin.post(news_path+'/preview',json={'key':campaign,'text':'[code]x[/code][/b]'}).status_code==422
        for target in ('clients','group'):
            for with_photo in (True,False):
                key=secrets.token_hex(16)
                body=dict(key=key,text=source,destination=target,rich=True)
                if with_photo:
                    assert admin.put(f'{news_path}/upload/{key}/0',json={'data':base64.b64encode(image).decode()}).is_success
                    body.update(filename='x.png',size=len(image),caption_above=True,photo_spoiler=True)
                else:body.update(link_size='large',link_above=True)
                send(admin,news_path,body)
                with patch.object(s,'bot_request',return_value=httpx.Response(200)) as bot:
                    while s.deliver_one(): pass
                    bot.assert_called_once()
                    args=bot.call_args.args; payload=args[1]
                    assert payload['caption_entities' if with_photo else 'entities']==preview['entities']
                    assert payload['caption' if with_photo else 'text']==preview['text']
                    if with_photo: assert payload['has_spoiler'] and payload['show_caption_above_media']
                    else: assert payload['link_preview_options']=={'url':'https://example.org','show_above_text':True,'prefer_large_media':True}
        refresh='/api/admin/support/group/refresh'
        assert user.post(refresh).status_code==401
        with patch.object(telegram,'bot_call',return_value={'id':-123456,'title':'Новое название'}) as query:
            assert send(admin,refresh,{})=={'groupName':'Новое название'}
            query.assert_called_once_with('getChat',chat_id='-123456')
        with patch.object(telegram,'bot_call',return_value={'id':-456789,'title':'Другой чат'}):
            assert admin.post(refresh).status_code==502
        assert admin.get('/api/admin/support').json()['groupName']=='Новое название'
print('Passed: histories, isolation, files both directions, Telegram photo, duplicate webhook, admin alert with sender and link, payment, renewal, expiry, scheduled news.')
