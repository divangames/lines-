import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get("LINEA_CONFIG", ROOT / "private/server.json"))
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
STATE = Path(os.environ.get("LINEA_STATE", CONFIG.get("state", ROOT / "private/state")))
DIST = Path(os.environ.get("LINEA_DIST", ROOT / "dist"))
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE / "portal.db"
BASE_URL = CONFIG["base_url"].rstrip("/")
DEVELOPMENT = CONFIG.get("development", False)
COOKIE = "linea_dev" if DEVELOPMENT else "__Host-linea"


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1, maxmem=67108864)
    return salt + ":" + result.hex()


def password_matches(password, expected):
    try:
        return hmac.compare_digest(password_hash(password, expected.split(":")[0]), expected)
    except (ValueError, TypeError):
        return False


@contextmanager
def db():
    connection = sqlite3.connect(DB, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    with db() as connection:
        connection.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            token TEXT UNIQUE NOT NULL, tunnel_key TEXT UNIQUE NOT NULL, uuid TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            quota_bytes INTEGER NOT NULL DEFAULT 0, expires_at INTEGER,
            uploaded INTEGER NOT NULL DEFAULT 0, downloaded INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL, last_seen_at INTEGER, last_page_at INTEGER,
            last_sync_at INTEGER, page_views INTEGER NOT NULL DEFAULT 0,
            subscription_fetches INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT, kind TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY, value INTEGER NOT NULL, marker TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily (
            day TEXT NOT NULL, client_id TEXT NOT NULL, uploaded INTEGER NOT NULL DEFAULT 0,
            downloaded INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, client_id)
        );
        CREATE INDEX IF NOT EXISTS events_date_idx ON events(created_at);
        """)
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(clients)')}
        if 'account_username' not in columns:
            connection.execute('ALTER TABLE clients ADD COLUMN account_username TEXT')
        if 'account_password_hash' not in columns:
            connection.execute('ALTER TABLE clients ADD COLUMN account_password_hash TEXT')
        connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS account_username_unique ON clients(account_username) WHERE account_username IS NOT NULL')
        connection.execute('''CREATE TABLE IF NOT EXISTS client_sessions (
            hash TEXT PRIMARY KEY, client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL, remembered INTEGER NOT NULL DEFAULT 0
        )''')
        session_columns = {row['name'] for row in connection.execute('PRAGMA table_info(client_sessions)')}
        if 'remembered' not in session_columns:
            connection.execute('ALTER TABLE client_sessions ADD COLUMN remembered INTEGER NOT NULL DEFAULT 0')
            # Old nonpersistent sessions never lasted longer than 12 hours.
            # Preserve remembered sessions where their remaining TTL proves it;
            # unknown short-lived legacy cookies keep the safer session default.
            connection.execute('UPDATE client_sessions SET remembered=1 WHERE expires_at>?', (now() + 43200,))
        connection.execute('CREATE INDEX IF NOT EXISTS client_session_expiry_idx ON client_sessions(expires_at)')
        connection.execute('DELETE FROM client_sessions WHERE expires_at<=?', (now(),))
        defaults = {"name": "Линия", "tagline": "VPN для своих", "support_url": "",
                    "admin_username": CONFIG.get("admin_username", "admin"),
                    "admin_password_hash": CONFIG["admin_password_hash"]}
        for key, value in defaults.items():
            connection.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, value))
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
    if os.name != "nt":
        os.chmod(DB, 0o600)


def now():
    return int(time.time())


def settings(private=False):
    with db() as connection:
        values = dict(connection.execute("SELECT key,value FROM settings").fetchall())
    if not private:
        values.pop("admin_password_hash", None)
        values.pop("admin_username", None)
    return values


def clients(include_deleted=False):
    with db() as connection:
        query = "SELECT * FROM clients" + ("" if include_deleted else " WHERE deleted=0") + " ORDER BY created_at DESC,id"
        return [dict(row) for row in connection.execute(query)]


def get_client(client_id=None, token=None, tunnel_key=None):
    key, value = ("id", client_id) if client_id else (("token", token) if token else ("tunnel_key", tunnel_key))
    with db() as connection:
        row = connection.execute(f"SELECT * FROM clients WHERE {key}=? AND deleted=0", (value,)).fetchone()
        return dict(row) if row else None


def status(row):
    if row["deleted"]:
        return "archived"
    if not row["enabled"]:
        return "disabled"
    if row["expires_at"] and row["expires_at"] <= now():
        return "expired"
    if row["quota_bytes"] and row["uploaded"] + row["downloaded"] >= row["quota_bytes"]:
        return "limited"
    return "active"


def event(kind, client_id=None, detail="", connection=None):
    values = (client_id, kind, detail[:240], now())
    if connection:
        connection.execute("INSERT INTO events(client_id,kind,detail,created_at) VALUES (?,?,?,?)", values)
    else:
        with db() as conn:
            conn.execute("INSERT INTO events(client_id,kind,detail,created_at) VALUES (?,?,?,?)", values)
