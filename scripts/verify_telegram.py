"""Проверка регистрации на временной БД с имитацией доставки Telegram."""
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlencode
from unittest.mock import patch

from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
with tempfile.TemporaryDirectory() as folder:
    config = Path(folder) / 'config.json'
    config.write_text(json.dumps(dict(development=True, base_url='http://testserver', server_host='vpn.test',
        admin_password_hash='unused', secret='test-only', state=folder, telegram_token='mock',
        telegram_webhook_secret='example', telegram_username='test_bot')))
    os.environ['LINEA_CONFIG'] = str(config)
    from server.app import app
    from server import telegram, store

    with TestClient(app) as client, patch.object(telegram, 'bot_call') as send:
        origin = {'Origin': 'http://testserver'}
        webhook = {'x-telegram-bot-api-secret-token': 'example'}
        def post(path, body):
            return client.post(path, json=body, headers=origin)
        def update(**message):
            payload = dict(chat={'id': 123, 'type':'private'}, **{'from':{'id':123}}, **message)
            return client.post('/api/telegram/update', json={'message':payload}, headers=webhook)

        assert client.post('/api/telegram/update', json={}).status_code == 403
        result = post('/api/account/register', {'name':'Тест', 'phone':'+1 (202) 555-0123'})
        token = result.json()['url'].split('=')[1]
        assert update(text='/start '+token).is_success
        assert update(contact={'user_id':456, 'phone_number':'12025550123'}).is_success
        assert update(contact={'user_id':123, 'phone_number':'12025550999'}).is_success
        assert not store.clients()
        contact = {'user_id':123, 'phone_number':'12025550123'}
        assert update(contact=contact).is_success
        password = send.call_args.kwargs['text'].split('Пароль: ')[1].splitlines()[0]
        assert update(contact=contact).is_success and 'Пароль:' not in send.call_args.kwargs['text']
        row, = store.clients()
        assert row['expires_at']-row['created_at']==48*3600 and row['quota_bytes']==5*1024**3
        assert post('/api/account/login', {'username':'+1 (202) 555-0123','password':password}).is_success
        for agent in ('Happ','v2rayTun'):
            sub = client.get('/sub/'+row['token'], headers={'user-agent':agent})
            assert '🇵🇱 Польша' in base64.b64decode(sub.headers['profile-title'][7:]).decode()
            assert '🇵🇱 Польша · Линия · Тест' in unquote(base64.b64decode(sub.content).decode())
        fields = {'auth_date':str(store.now()), 'user':'{"id":123}'}
        key=hmac.digest(b'WebAppData',b'mock','sha256')
        fields['hash']=hmac.digest(key,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),'sha256').hex()
        assert post('/api/account/telegram',{'data':urlencode(fields)}).is_success
        fields['user']='{"id":456}'
        assert post('/api/account/telegram',{'data':urlencode(fields)}).status_code==401
        for field, value in [('uploaded', row['quota_bytes']), ('expires_at', store.now()-1)]:
            with store.db() as conn:
                conn.execute(f'UPDATE clients SET uploaded=0,{field}=? WHERE id=?', (value, row['id']))
            assert client.get('/sub/'+row['token']).status_code==403
print('Registration, contact verification, trial uniqueness, password, mini login, both client profiles and both limits passed.')
