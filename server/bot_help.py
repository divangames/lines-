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
SING_BOX_CLIENTS = {
    'ios': ('sing-box MT', 'https://sing-box.sagernet.org/clients/apple/#download'),
    'android': ('sing-box для Android', 'https://sing-box.sagernet.org/clients/android/#download'),
    'windows': ('sing-box для Windows', 'https://sing-box.sagernet.org/clients/desktop/#download'),
    'macos': ('sing-box для macOS', 'https://sing-box.sagernet.org/clients/apple/#download-macos-standalone-version'),
    'linux': ('sing-box для Linux', 'https://sing-box.sagernet.org/clients/desktop/#download'),
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
                'Возможность установки sing-box и настройки маршрутов для всей сети зависит от модели и прошивки. '
                'Для подключения Линии роутер должен поддерживать VLESS с WebSocket и TLS.\n\n'
                '1. Найдите точную модель и версию прошивки в настройках роутера.\n'
                '2. Нажмите «Задать вопрос администратору» и укажите модель и прошивку. '
                'Администратор проверит совместимость и поможет с настройкой.\n\n'
                'До проверки можно подключить телефон или компьютер по отдельной инструкции.')
    client, download = SING_BOX_CLIENTS[device]
    tab = 'sing-box MT' if device == 'ios' else 'sing-box'
    alternatives = 'v2RAGE или INCY' if device == 'ios' else 'Happ или v2RayTun'
    windows_note = (' Для NaiveProxy на Windows установите 64-разрядную сборку.'
                    if device == 'windows' else '')
    return (f'Подключение · {label}\n\n'
            f'1. Установите {client}.\n{download}\n'
            f'2. Войдите в личный кабинет и в разделе «Устройства» выберите {tab}.\n'
            f'{store.BASE_URL}/account#devices\n'
            '3. Нажмите «Добавить VLESS». Если приложение не открылось, нажмите «Скопировать VLESS» '
            'и вставьте ссылку в новый удалённый профиль (Remote) в sing-box.\n'
            '4. Выберите профиль «Линия» и включите подключение. '
            'Подтвердите системный запрос на создание VPN, если он появится.\n\n'
            'Домены Госуслуг, Maxim и других сервисов из списка открываются напрямую. '
            'Для остального трафика используется VPS.\n\n'
            'Если в вашем кабинете есть «Добавить NaiveProxy», его можно импортировать отдельным профилем. '
            'Для ручного импорта нажмите «Скопировать NaiveProxy» и вставьте ссылку в удалённый профиль.'
            f'{windows_note}\n\n'
            f'Для {alternatives} выберите соответствующую вкладку в кабинете. '
            'Если подключение не работает, проверьте срок и остаток трафика в кабинете, '
            'обновите профиль и отключите другое VPN-приложение.')


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
