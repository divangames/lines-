"""Owner-confirmed first payments and public offer terms."""

import secrets
import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import store
from .accounts import CredentialFields


PLANS = {"Личный": (199, 100), "Комфорт": (349, 300), "Семья": (549, 600)}


class JoinRequest(CredentialFields):
    account_username: str = Field(min_length=3, max_length=64)
    account_password: str = Field(min_length=12, max_length=256, repr=False)
    plan: Literal["Личный", "Комфорт", "Семья"]


class Terms(BaseModel):
    device_price: int = Field(default=49, ge=0, le=100000)
    traffic_price: int = Field(default=99, ge=0, le=100000)
    quarter_discount: int | None = Field(default=None, ge=1, le=100)
    year_discount: int | None = Field(default=None, ge=1, le=100)
    reward_days: int = Field(default=7, ge=1, le=365)
    router_help: str = Field(default="Разовая помощь", min_length=1, max_length=80)


def initialize(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS partners (
            client_id TEXT PRIMARY KEY REFERENCES clients(id),
            code TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS referrals (
            friend TEXT PRIMARY KEY REFERENCES clients(id),
            partner TEXT NOT NULL REFERENCES clients(id),
            days INTEGER NOT NULL,
            paid_at INTEGER,
            CHECK(friend <> partner)
        );
        CREATE INDEX IF NOT EXISTS referrals_partner ON referrals(partner);
        CREATE TABLE IF NOT EXISTS partner_requests (
            id TEXT PRIMARY KEY, partner TEXT NOT NULL REFERENCES clients(id),
            username TEXT NOT NULL, password_hash TEXT NOT NULL, plan TEXT NOT NULL,
            created_at INTEGER NOT NULL, days INTEGER NOT NULL,
            friend TEXT UNIQUE REFERENCES clients(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS partner_request_username
            ON partner_requests(username) WHERE friend IS NULL;
        INSERT INTO partners SELECT id, lower(hex(randomblob(8))) FROM clients
            WHERE id NOT IN (SELECT client_id FROM partners);
        CREATE TRIGGER IF NOT EXISTS new_partner AFTER INSERT ON clients BEGIN
            INSERT INTO partners VALUES (NEW.id, lower(hex(randomblob(8))));
        END;
    """)


def terms(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='offer_terms'").fetchone()
    return Terms.model_validate_json(row[0]) if row else Terms()


def invite(conn, friend, code):
    row = conn.execute("SELECT p.client_id FROM partners p JOIN clients c ON c.id=p.client_id WHERE p.code=? AND c.deleted=0", (code.lower().strip(),)).fetchone()
    if not row or row[0] == friend:
        raise HTTPException(422, "Проверьте код пригласившего пользователя")
    conn.execute("INSERT INTO referrals(friend,partner,days) VALUES (?,?,?)", (friend, row[0], terms(conn).reward_days))


def submit(code, body):
    with store.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        partner = conn.execute("SELECT p.client_id FROM partners p JOIN clients c ON c.id=p.client_id WHERE p.code=? AND c.deleted=0",(code,)).fetchone()
        if not partner:
            raise HTTPException(404, "Приглашение недействительно")
        conn.execute("DELETE FROM partner_requests WHERE friend IS NULL AND created_at<?",(store.now()-30*86400,))
        if conn.execute("SELECT 1 FROM clients WHERE account_username=?", (body.account_username,)).fetchone():
            raise HTTPException(409, "Логин уже занят")
        existing = conn.execute("SELECT * FROM partner_requests WHERE username=? AND friend IS NULL",(body.account_username,)).fetchone()
        if existing:
            if existing["partner"] == partner[0] and existing["plan"] == body.plan and store.password_matches(body.account_password, existing["password_hash"]):
                return
            raise HTTPException(409, "Логин уже занят")
        conn.execute("INSERT INTO partner_requests(id,partner,username,password_hash,plan,created_at,days) VALUES(?,?,?,?,?,?,?)",
                     (secrets.token_hex(12),partner[0],body.account_username,store.password_hash(body.account_password),body.plan,store.now(),terms(conn).reward_days))


def pending(conn):
    return [dict(row) for row in conn.execute("""SELECT r.id,r.username,r.plan,c.name AS partner_name
        FROM partner_requests r JOIN clients c ON r.partner=c.id WHERE r.friend IS NULL
        AND c.deleted=0 AND r.created_at>=? ORDER BY r.created_at""",(store.now()-30*86400,))]


def activate(request_id):
    with store.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM partner_requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Заявка не найдена")
        if row["friend"]:
            return
        if row["created_at"] < store.now()-30*86400:
            raise HTTPException(410, "Срок заявки истёк")
        if conn.execute("SELECT 1 FROM clients WHERE account_username=?", (row["username"],)).fetchone():
            raise HTTPException(409, "Этот логин уже используется")
        if conn.execute("SELECT COUNT(*) FROM clients WHERE deleted=0").fetchone()[0]>=500:
            raise HTTPException(409, "Достигнут лимит доступов")
        friend = secrets.token_hex(8)
        now = store.now()
        conn.execute("""INSERT INTO clients(id,name,token,tunnel_key,uuid,email,quota_bytes,expires_at,
            created_at,account_username,account_password_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (friend,row["username"],secrets.token_urlsafe(32),secrets.token_urlsafe(32),str(uuid.uuid4()),friend+"@linea",
             PLANS[row["plan"]][1]*1024**3,now+30*86400,now,row["username"],row["password_hash"]))
        conn.execute("INSERT INTO referrals(friend,partner,days) VALUES(?,?,?)",(friend,row["partner"],row["days"]))
        credit(conn,friend)
        conn.execute("UPDATE partner_requests SET friend=?,password_hash='' WHERE id=?",(friend,request_id))
        store.event("created",friend,"Первая оплата · "+row["plan"],connection=conn)


def summary(client_id):
    with store.db() as conn:
        row = conn.execute("""SELECT p.code, COUNT(r.friend) + (SELECT COUNT(*) FROM partner_requests q
            WHERE q.partner=p.client_id AND q.friend IS NULL AND q.created_at>=?) AS invited, COUNT(r.paid_at) AS paid,
            COALESCE(SUM(CASE WHEN r.paid_at IS NOT NULL THEN r.days ELSE 0 END),0) AS days
            FROM partners p LEFT JOIN referrals r ON r.partner=p.client_id WHERE p.client_id=? GROUP BY p.client_id""", (store.now()-30*86400,client_id)).fetchone()
        return dict(row) if row else None


def referral(client_id):
    with store.db() as conn:
        row = conn.execute("""SELECT c.name AS partner_name,r.days,r.paid_at FROM referrals r
            JOIN clients c ON c.id=r.partner WHERE r.friend=?""", (client_id,)).fetchone()
        return dict(row) if row else None


def confirm_payment(friend):
    with store.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        credit(conn,friend)


def credit(conn,friend):
    row = conn.execute("""SELECT r.* FROM referrals r JOIN clients c ON c.id=r.friend
        WHERE r.friend=? AND c.deleted=0""",(friend,)).fetchone()
    if not row:
        raise HTTPException(404, "Приглашение не найдено")
    if row["paid_at"] is not None:
        return
    now = store.now()
    updated = conn.execute("""UPDATE clients SET expires_at=CASE WHEN expires_at IS NULL THEN NULL
        ELSE MAX(expires_at,?)+? END WHERE id=? AND deleted=0""",(now,row["days"]*86400,row["partner"]))
    if not updated.rowcount:
        raise HTTPException(409, "Доступ пригласившего пользователя архивирован")
    conn.execute("UPDATE referrals SET paid_at=? WHERE friend=?", (now,friend))
    store.event("referral_reward",row["partner"],f"+{row['days']} дн. за первую оплату",connection=conn)
