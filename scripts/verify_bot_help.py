"""Exercise device guides and the admin reply path without sending Telegram messages."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as folder:
    password = secrets.token_urlsafe(20)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=67108864).hex()
    config = dict(development=True, base_url='http://testserver', server_host='vpn.test',
                  state=folder, secret='test-only', telegram_username='test_bot',
                  telegram_webhook_secret='mock', admin_password_hash=salt.hex()+':'+digest)
    path = Path(folder)/'config.json'
    path.write_text(json.dumps(config))
    os.environ['LINEA_CONFIG'] = str(path)
    from server.app import app
    from server import store, telegram, support, bot_help

    with TestClient(app) as admin, patch.object(telegram, 'bot_call') as api:
        admin.headers['Origin'] = config['base_url']
        login = admin.post('/api/auth/login', json={'username':'admin', 'password':password})
        admin.headers['X-CSRF-Token'] = login.json()['csrf']
        headers = {'X-Telegram-Bot-Api-Secret-Token':'mock'}

        def message(identifier, text):
            response = admin.post('/api/telegram/update', headers=headers, json={'message':{
                'message_id':identifier, 'text':text, 'chat':{'id':123, 'type':'private'},
                'from':{'id':123, 'first_name':'Test'}}})
            assert response.is_success, response.text

        def callback(identifier, topic, sender=123):
            response = admin.post('/api/telegram/update', headers=headers, json={'callback_query':{
                'id':identifier, 'data':'help:'+topic, 'from':{'id':sender},
                'message':{'message_id':999, 'chat':{'id':123, 'type':'private'}}}})
            assert response.is_success, response.text

        message(1, '/support')
        message(1, '/support')
        for device in bot_help.DEVICES:
            callback(device, device)
            callback(device, device)
        with store.db() as conn:
            rows = conn.execute("SELECT * FROM support_messages WHERE role='bot'").fetchall()
            assert len(rows) == 7
            assert all(len(row['body']) < 4096 for row in rows)
            count = conn.execute('SELECT count(*) FROM telegram_help_events').fetchone()[0]
        callback('forged', 'admin', sender=456)
        with store.db() as conn:
            assert conn.execute('SELECT count(*) FROM telegram_help_events').fetchone()[0] == count
        assert admin.get('/api/admin/support').json()['threads'] == []

        message(20, 'Игра выдаёт ошибку 789, что делать?')
        message(20, 'Игра выдаёт ошибку 789, что делать?')
        message(21, 'Windows')  # Once handed off, the device name belongs to the admin conversation.
        inbox = admin.get('/api/admin/support').json()['threads']
        assert inbox == [{'id':'t-123', 'name':'Test'}]
        history = admin.get('/api/admin/support/t-123').json()['messages']
        assert [row['body'] for row in history if row['role']=='client'] == [
            'Игра выдаёт ошибку 789, что делать?', 'Windows']
        assert sum(row['body']==bot_help.ACKNOWLEDGEMENT for row in history) == 1

        body = {'key':secrets.token_hex(16), 'text':'Ответ администратора из админки'}
        for _ in range(2):
            response = admin.post('/api/admin/support/t-123', json=body)
            assert response.is_success, response.text
        with patch.object(support, 'bot_request', return_value=httpx.Response(200, json={'ok':True})) as delivery:
            while support.deliver_one():
                pass
            replies = [call.args[1] for call in delivery.call_args_list]
            assert sum(body['text'] in reply['text'] for reply in replies) == 1
            assert all(reply['chat_id']=='123' for reply in replies)
            choices = replies[0]['reply_markup']['inline_keyboard']
            assert sum(button.get('callback_data','') in {'help:'+key for key in bot_help.DEVICES}
                       for row in choices for button in row) == 6

        callback('back-to-guides', 'devices')
        message(22, 'как подключить vpn на android')
        callback('need-human', 'admin')
        callback('need-human', 'admin')
        history = admin.get('/api/admin/support/t-123').json()['messages']
        assert sum('Последняя инструкция: Android.' in row['body'] for row in history) == 1
        assert TestClient(app).get('/api/admin/support/t-123').status_code == 401

print('Passed: six guides, duplicate updates, callback isolation, unknown question handoff, '
      'ongoing admin conversation, admin API reply delivery, return to guides, and access control.')
