"""Регистрация клиентов и выдача пробного доступа через личный чат Telegram."""
import hashlib
import hmac
import json
import re
import secrets
import uuid
from urllib.parse import parse_qsl
from urllib.request import Request as HttpRequest, urlopen

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import accounts, engine, store, support, bot_help

WELCOME = ('Добро пожаловать в Линию! 🇵🇱 Попробуйте VPN в Польше бесплатно: '
           '48 часов и 5 ГБ. В кабинете доступны профили для sing-box, Happ и v2ray. '
           'Нажмите «Как подключиться», чтобы выбрать устройство. '
           'Укажите имя и подтвердите свой телефон — пароль придёт сюда.')
TRIAL_SECONDS = 48 * 3600
TRIAL_BYTES = 5 * 1024**3


class Registration(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=6, max_length=32)


class Launch(BaseModel):
    data: str = Field(max_length=8192, repr=False)


def initialize(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tg_requests (
            token TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
            expires INTEGER NOT NULL, peer TEXT NOT NULL, chat INTEGER UNIQUE
        );
        CREATE TABLE IF NOT EXISTS tg_trials (
            chat INTEGER PRIMARY KEY, phone TEXT NOT NULL UNIQUE,
            client TEXT NOT NULL UNIQUE REFERENCES clients(id), delivery_nonce TEXT
        );
    """)

    bot_help.initialize(conn)

def phone_number(value):
    value = re.sub(r'[ ()-]', '', value)
    if not re.fullmatch(r'\+?[1-9][0-9]{6,14}', value):
        raise ValueError('Введите номер с кодом страны')
    return '+' + value.lstrip('+')


def bot_call(method, **payload):
    token = store.CONFIG['telegram_token']
    req = HttpRequest(f'https://api.telegram.org/bot{token}/{method}',
                      data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=10) as res:
            result = json.load(res)
        if result.get('ok'):
            return result['result']
    except (OSError, ValueError):
        pass
    raise HTTPException(503, 'Telegram временно недоступен')


def menu():
    return {'inline_keyboard': [[{'text': 'Как подключиться', 'callback_data': 'help:devices'}], [{'text': 'Открыть кабинет', 'web_app': {'url': store.BASE_URL + '/account/mini'}}],
                                [{'text': 'Техподдержка', 'url': 'https://t.me/'+store.CONFIG.get('telegram_username','linesonline_bot')+'?start=support'}]]}


def register_contact(chat, contact):
    if contact.get('user_id') != chat:
        return 'Поделитесь своим номером кнопкой под сообщением.', None, None
    try:
        phone = phone_number(contact.get('phone_number', ''))
    except ValueError:
        return 'Проверьте номер в Telegram.', None, None
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        trial = conn.execute('SELECT * FROM tg_trials WHERE chat=?', (chat,)).fetchone()
        if not trial:
            pending = conn.execute('SELECT * FROM tg_requests WHERE chat=? AND expires>?', (chat, store.now())).fetchone()
            if not pending:
                return 'Начните регистрацию на сайте. Ссылка на подтверждение действует 15 минут.', menu(), None
            if pending['phone'] != phone:
                return 'Номер в заявке отличается от номера Telegram. Исправьте его на сайте.', menu(), None
            if conn.execute('SELECT 1 FROM tg_trials WHERE phone=? UNION SELECT 1 FROM clients WHERE account_username=?', (phone, phone)).fetchone():
                return 'Этот номер уже зарегистрирован. Войдите в кабинет или обратитесь в поддержку.', menu(), None
            if conn.execute('SELECT count(*) FROM clients WHERE deleted=0').fetchone()[0] >= 500:
                return 'Все пробные места заняты. Попробуйте позже.', None, None
            identifier = secrets.token_hex(8)
            nonce = secrets.token_hex(24)
            now = store.now()
            conn.execute("""INSERT INTO clients(id,name,token,tunnel_key,uuid,email,quota_bytes,expires_at,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?)""", (identifier, pending['name'], secrets.token_urlsafe(32),
                         secrets.token_urlsafe(32), str(uuid.uuid4()), identifier + '@linea', TRIAL_BYTES, now + TRIAL_SECONDS, now))
            conn.execute('INSERT INTO tg_trials VALUES (?,?,?,?)', (chat, phone, identifier, nonce))
            password = delivery_password(nonce)
            accounts.save_credentials(conn, identifier, phone, password)
            store.event('created', identifier, connection=conn)
            conn.execute('DELETE FROM tg_requests WHERE chat=?', (chat,))
        elif trial['delivery_nonce'] and trial['phone'] == phone:
            nonce = trial['delivery_nonce']
            password = delivery_password(nonce)
        else:
            return 'Вы уже зарегистрированы. Ваш доступ находится в кабинете.', menu(), None
    with engine.LOCK:
        try:
            engine.sync()
        except Exception:
            pass  # Фоновая сверка повторяет синхронизацию каждые пять секунд.
    return f'Ваш кабинет готов.\nЛогин: {phone}\nПароль: {password}\nПароль можно изменить в кабинете.', menu(), nonce


def delivery_password(nonce):
    return hmac.new(store.CONFIG['secret'].encode(), ('telegram-password:' + nonce).encode(), hashlib.sha256).hexdigest()[:28]


def telegram_identity(data):
    try:
        pairs = parse_qsl(data, strict_parsing=True, max_num_fields=32)
        fields = dict(pairs)
        signature = fields.pop('hash')
        if len(pairs) != len(fields) + 1 or not 0 <= store.now() - int(fields['auth_date']) <= 300:
            raise ValueError
        check = '\n'.join(f'{key}={fields[key]}' for key in sorted(fields))
        secret = hmac.digest(b'WebAppData', store.CONFIG['telegram_token'].encode(), 'sha256')
        if not hmac.compare_digest(hmac.digest(secret, check.encode(), 'sha256').hex(), signature):
            raise ValueError
        return int(json.loads(fields['user'])['id'])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(401, 'Откройте кабинет заново из меню бота') from None


def make_router(check_origin, csrf, access_view):
    router = APIRouter()

    @router.post('/api/account/register')
    def register(body: Registration, request: Request):
        check_origin(request)
        if not store.CONFIG.get('telegram_username'):
            raise HTTPException(503, 'Регистрация временно недоступна')
        name = body.name.strip()
        if not name or not name.isprintable():
            raise HTTPException(422, 'Укажите имя')
        try:
            phone = phone_number(body.phone)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        peer = request.client.host if request.client else ''
        if peer in ('127.0.0.1', '::1'):
            peer = request.headers.get('x-real-ip', peer)
        token = secrets.token_urlsafe(24)
        with store.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM tg_requests WHERE expires<=?', (store.now(),))
            if conn.execute('SELECT count(*) FROM tg_requests WHERE peer=?', (peer,)).fetchone()[0] >= 20:
                raise HTTPException(429, 'Повторите через 15 минут')
            conn.execute('INSERT INTO tg_requests(token,name,phone,expires,peer) VALUES (?,?,?,?,?)',
                         (token, name, phone, store.now()+900, peer))
        return {'url': f"https://t.me/{store.CONFIG['telegram_username']}?start={token}"}

    @router.post('/api/telegram/update')
    def update(body: dict, request: Request):
        secret = store.CONFIG.get('telegram_webhook_secret')
        if not secret or not hmac.compare_digest(request.headers.get('x-telegram-bot-api-secret-token', '').encode(), secret.encode()):
            raise HTTPException(403)
        callback = body.get('callback_query')
        if callback:
            message = callback.get('message', {})
            chat = message.get('chat', {}).get('id')
            sender = callback.get('from', {})
            if message.get('chat', {}).get('type') != 'private' or chat != sender.get('id'):
                return {'ok': True}
            topic = callback.get('data', '').removeprefix('help:')
            if callback.get('data', '').startswith('help:') and callback.get('id'):
                bot_help.respond(chat, topic, 'callback:'+callback['id'], sender)
                bot_call('answerCallbackQuery', callback_query_id=callback['id'])
            return {'ok': True}
        message = body.get('message', {})
        chat = message.get('chat', {}).get('id')
        if message.get('chat', {}).get('type') != 'private' or chat != message.get('from', {}).get('id'):
            return {'ok': True}
        text = message.get('text', '')
        nonce = None
        if bot_help.handle_text(message):
            return {'ok': True}
        if text.startswith('/start admin_'):
            reply, keyboard = support.bind_admin(chat,text[len('/start admin_'):]), menu()
        elif text in ('/support','/start support','Техподдержка'):
            reply, keyboard = 'Опишите проблему или отправьте файл до 8 МБ. Ответ администратора придёт сюда.', menu()
        elif text.startswith('/start '):
            with store.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                token = text.split(maxsplit=1)[-1]
                conn.execute('UPDATE tg_requests SET chat=NULL WHERE chat=? AND token<>?', (chat, token))
                bound = conn.execute('UPDATE tg_requests SET chat=? WHERE token=? AND expires>? AND (chat IS NULL OR chat=?)',
                                     (chat, token, store.now(), chat)).rowcount
            if bound:
                reply = 'Чтобы получить пароль, подтвердите номер телефона кнопкой ниже.'
                keyboard = {'keyboard': [[{'text': 'Подтвердить мой номер', 'request_contact': True}]], 'resize_keyboard': True, 'one_time_keyboard': True}
            else:
                reply, keyboard = 'Ссылка недействительна. Начните регистрацию ещё раз.', menu()
        elif 'successful_payment' in message:
            receipt=message['successful_payment'].get('telegram_payment_charge_id')
            if receipt:
                with store.db() as conn:
                    account=conn.execute('SELECT client FROM tg_trials WHERE chat=?',(chat,)).fetchone()
                    if account: support.payment(conn,account[0],receipt)
            return {'ok': True}
        elif 'contact' in message:
            reply, keyboard, nonce = register_contact(chat, message['contact'])
        elif text == '/start':
            reply, keyboard = WELCOME, menu()
        else:
            support.incoming(message, handoff=True)
            return {'ok': True}
        bot_call('sendMessage', chat_id=chat, text=reply, protect_content=True, **({'reply_markup': keyboard} if keyboard else {}))
        if nonce:
            with store.db() as conn:
                conn.execute('UPDATE tg_trials SET delivery_nonce=NULL WHERE chat=? AND delivery_nonce=?', (chat, nonce))
        return {'ok': True}

    @router.post('/api/account/telegram')
    def mini_login(body: Launch, request: Request, response: Response):
        check_origin(request)
        chat = telegram_identity(body.data)
        token = secrets.token_urlsafe(32)
        with store.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT clients.* FROM tg_trials JOIN clients ON clients.id=tg_trials.client WHERE chat=? AND deleted=0', (chat,)).fetchone()
            if not row:
                raise HTTPException(404, 'Зарегистрируйтесь для получения доступа')
            conn.execute('INSERT INTO client_sessions VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], store.now()+43200, 0))
        response.set_cookie(accounts.COOKIE, token, httponly=True, secure=not store.DEVELOPMENT, samesite='none' if not store.DEVELOPMENT else 'lax', path='/')
        return {**access_view(row), 'account_username': row['account_username'], 'csrf': csrf(token)}

    return router
