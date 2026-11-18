"""Prepared connection guides and explicit handoff to the support inbox."""
import json
import re

from . import store, support


DEVICES = {
    'ios': ('iPhone / iPad', ('ios', 'iphone', 'ipad', 'айфон', 'айпад')),
    'android': ('Android', ('android', 'андроид')),
    'windows': ('Windows', ('windows', 'виндовс', 'виндоус', 'пк')),
    'macos': ('macOS', ('macos', 'mac', 'мак', 'макбук')),
    'linux': ('Linux', ('linux', 'линукс')),
    'router': ('Роутер', ('роутер', 'маршрутизатор')),
}
ACKNOWLEDGEMENT = ('Ваш вопрос передан администратору. Ответ придёт в этот чат. '
                   'Можно дополнить сообщение или приложить скриншот без паролей и персональной ссылки.')


def initialize(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS telegram_help_events (key TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS telegram_help_state (
            chat INTEGER PRIMARY KEY, handoff INTEGER NOT NULL DEFAULT 0, topic TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS telegram_help_replies (
            message INTEGER PRIMARY KEY REFERENCES support_messages(id), keyboard TEXT NOT NULL
        );
    """)


def keyboard(devices=False):
    rows = []
    if devices:
        items = list(DEVICES.items())
        rows = [[{'text': label, 'callback_data': 'help:'+key} for key, (label, _) in items[i:i+2]]
                for i in range(0, len(items), 2)]
    else:
        rows.append([{'text': 'Инструкции по устройствам', 'callback_data': 'help:devices'}])
    rows.append([{'text': 'Задать вопрос администратору', 'callback_data': 'help:admin'}])
    rows.append([{'text': 'Открыть кабинет', 'web_app': {'url': store.BASE_URL+'/account/mini'}}])
    return {'inline_keyboard': rows}


def guide(device):
    label = DEVICES[device][0]
    if device == 'router':
        return ('Подключение на роутере\n\n'
                'Поддержка зависит от модели и прошивки: нужен клиент VLESS с WebSocket и TLS. '
                'Обычного раздела OpenVPN или WireGuard недостаточно.\n\n'
                '1. Найдите точную модель и версию прошивки в настройках роутера.\n'
                '2. Подготовьте ссылку подписки из личного кабинета, но не отправляйте её в общий чат.\n'
                '3. Нажмите «Задать вопрос администратору» и укажите модель и прошивку. '
                'Администратор проверит совместимость и поможет с настройкой.\n\n'
                'До проверки можно подключить телефон или компьютер по отдельной инструкции.')
    install = ('Установите v2RAGE из App Store: https://apps.apple.com/app/v2rage/id6761075402'
               if device == 'ios' else
               'Откройте https://happ.info/ и установите Happ для '+label+'.')
    importing = ('В v2RAGE откройте «Настройки» → «Импортировать подписку», вставьте ссылку и подтвердите.'
                 if device == 'ios' else
                 'В Happ добавьте подписку из буфера обмена и подтвердите импорт.')
    return (f'Подключение на {label}\n\n1. {install}\n'
            f'2. Войдите в кабинет: {store.BASE_URL}/account. '
            'Если доступа ещё нет, выберите регистрацию.\n'
            '3. Скопируйте ссылку подписки из кабинета.\n'
            f'4. {importing}\n'
            '5. Выберите сервер Линии и включите подключение. '
            'Подтвердите системный запрос на создание VPN-подключения, если он появится.\n'
            '6. Откройте сайт или приложение и проверьте соединение.\n\n'
            'Если подключение не работает, проверьте срок и остаток трафика в кабинете, '
            'обновите подписку и отключите другое VPN-приложение. '
            'Если это не помогло, нажмите кнопку обращения к администратору и опишите ошибку.')


def reply(conn, chat, text, key, markup=None):
    identifier = support.save(conn, 't-'+str(chat), 'bot', text, key)
    if identifier:
        conn.execute('INSERT INTO telegram_help_replies VALUES (?,?)',
                     (identifier, json.dumps(markup or keyboard(), ensure_ascii=False)))


def handoff(conn, chat, key):
    state = conn.execute('SELECT handoff FROM telegram_help_state WHERE chat=?', (chat,)).fetchone()
    conn.execute("INSERT INTO telegram_help_state(chat,handoff) VALUES (?,1) "
                 "ON CONFLICT(chat) DO UPDATE SET handoff=1", (chat,))
    if not state or not state[0]:
        reply(conn, chat, ACKNOWLEDGEMENT, 'help-ack:'+key)


def text_topic(text):
    text = re.sub(r'[?!.,:]+', '', text.lower()).strip()
    if text in ('/help', '/support', '/setup', '/start support', 'техподдержка',
                'инструкции', 'как подключиться', 'как подключить vpn'):
        return 'devices'
    if text in ('администратор', 'оператор', 'позвать администратора'):
        return 'admin'
    for key, (_, aliases) in DEVICES.items():
        for alias in aliases:
            if text in (alias, 'как подключить '+alias, 'как подключиться на '+alias,
                        'как подключить vpn на '+alias, 'подключение на '+alias):
                return key
    return None


def respond(chat, topic, event, sender=None):
    if topic not in (*DEVICES, 'devices', 'admin'):
        return False
    with store.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('INSERT OR IGNORE INTO telegram_help_events VALUES (?)', (event,)).rowcount:
            return True
        recent = conn.execute("SELECT count(*) FROM support_messages WHERE thread=? AND role='bot' AND stamp>?",
                              ('t-'+str(chat), store.now()-3600)).fetchone()[0]
        if recent >= 90:
            return True
        if sender:
            name = ' '.join(filter(None, (sender.get('first_name'), sender.get('last_name'))))[:100]
            if name:
                conn.execute('INSERT OR REPLACE INTO support_peers VALUES (?,?)', ('t-'+str(chat), name))
        if topic == 'admin':
            state = conn.execute('SELECT topic FROM telegram_help_state WHERE chat=?', (chat,)).fetchone()
            device = DEVICES.get(state[0]) if state else None
            text = 'Пользователь запросил помощь администратора.'
            if device:
                text += ' Последняя инструкция: '+device[0]+'.'
            support.save(conn, 't-'+str(chat), 'client', text, 'help-request:'+event)
            handoff(conn, chat, event)
        else:
            conn.execute('INSERT INTO telegram_help_state(chat,handoff,topic) VALUES (?,0,?) '
                         'ON CONFLICT(chat) DO UPDATE SET handoff=0,topic=excluded.topic', (chat, topic))
            text = ('Выберите устройство — пришлю инструкцию по подключению. '
                    'Если ответа не хватит, задайте вопрос: его получит администратор.'
                    if topic == 'devices' else guide(topic))
            reply(conn, chat, text, 'help-reply:'+event, keyboard(topic == 'devices'))
    return True


def handle_text(message):
    chat = message['chat']['id']
    text = message.get('text', '')
    topic = text_topic(text)
    if not topic or not message.get('message_id'):
        return False
    with store.db() as conn:
        state = conn.execute('SELECT handoff FROM telegram_help_state WHERE chat=?', (chat,)).fetchone()
    # Only an explicit menu command returns an ongoing admin conversation to the bot.
    if state and state[0] and topic not in ('devices', 'admin'):
        return False
    return respond(chat, topic, f"message:{chat}:{message['message_id']}", message.get('from'))
