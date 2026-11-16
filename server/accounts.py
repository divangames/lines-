"""Recipient credentials and sessions, independent of owner authentication."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
import io

from . import store

COOKIE = 'linea_user_dev' if store.DEVELOPMENT else '__Host-linea_user'
SESSION_TTL = 30 * 86400
ATTEMPTS = defaultdict(deque)
ATTEMPTS_LOCK = threading.Lock()
PASSWORD_ATTEMPTS = defaultdict(deque)
DUMMY_HASH = store.password_hash(secrets.token_urlsafe(24))


class CredentialFields(BaseModel):
    account_username: str | None = Field(default=None, max_length=64)
    account_password: str | None = Field(default=None, min_length=12, max_length=256, repr=False)

    @field_validator('account_username', mode='before')
    @classmethod
    def username(cls, value):
        if value is None:
            return None
        value = str(value).strip().lower()
        if not value:
            return None
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,63}', value):
            raise ValueError('Логин: 3–64 латинские буквы, цифры, точка, дефис или подчёркивание')
        return value

    @field_validator('account_password', mode='before')
    @classmethod
    def optional_password(cls, value):
        return None if value == '' else value


class UserLogin(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256, repr=False)
    remember: bool = True


class UserPasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256, repr=False)
    new_password: str = Field(min_length=12, max_length=256, repr=False)
    confirm_password: str = Field(min_length=12, max_length=256, repr=False)


def save_credentials(connection, client_id, username=None, password=None, force=False):
    """Caller owns transaction. Cleartext is returned once and never persisted."""
    row = connection.execute('SELECT account_username,account_password_hash FROM clients WHERE id=? AND deleted=0', (client_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Доступ не найден')
    if not force and username is None and password is None:
        return None
    next_username = username or row['account_username'] or 'user_' + client_id
    issue_password = force or password is not None or not row['account_password_hash']
    if not issue_password and next_username == row['account_username']:
        return None
    if issue_password:
        password = password or secrets.token_urlsafe(18)
        password_hash = store.password_hash(password)
    else:
        password_hash = row['account_password_hash']
    try:
        connection.execute('UPDATE clients SET account_username=?,account_password_hash=? WHERE id=?', (next_username, password_hash, client_id))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Этот логин уже занят. Выберите другой') from None
    connection.execute('DELETE FROM client_sessions WHERE client_id=?', (client_id,))
    store.event('account_credentials_updated', client_id, connection=connection)
    return {'username': next_username, 'password': password, 'login_url': store.BASE_URL + '/account'} if issue_password else None


def make_router(admin_dependency, check_origin, csrf, access_view):
    router = APIRouter()

    def authenticated_user(request: Request):
        token = request.cookies.get(COOKIE, '')
        if not token or len(token) > 200:
            raise HTTPException(401, 'Войдите в личный кабинет')
        with store.db() as connection:
            session = connection.execute('SELECT client_id FROM client_sessions WHERE hash=? AND expires_at>?', (hashlib.sha256(token.encode()).hexdigest(), store.now())).fetchone()
        row = store.get_client(session['client_id']) if session else None
        if not row or not row['account_password_hash']:
            raise HTTPException(401, 'Сессия завершена. Войдите ещё раз')
        if request.method not in ('GET', 'HEAD'):
            check_origin(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf(token)):
                raise HTTPException(403, 'Обновите страницу и повторите действие')
        return row, token

    @router.post('/api/account/login')
    def login(body: UserLogin, request: Request, response: Response):
        check_origin(request)
        peer = request.client.host if request.client else 'unknown'
        ip = request.headers.get('x-real-ip', peer) if peer in ('127.0.0.1', '::1') else peer
        current = time.monotonic()
        with ATTEMPTS_LOCK:
            if len(ATTEMPTS) > 10000:
                for key in list(ATTEMPTS):
                    if not ATTEMPTS[key] or ATTEMPTS[key][-1][0] < current - 900:
                        ATTEMPTS.pop(key, None)
            attempts = ATTEMPTS[ip]
            while attempts and attempts[0][0] < current - 900:
                attempts.popleft()
            if len(attempts) >= 10:
                raise HTTPException(429, 'Слишком много попыток. Повторите через 15 минут')
            # Reserve before scrypt so concurrent attempts cannot bypass the limit.
            attempt = (current, secrets.token_hex(8))
            attempts.append(attempt)
        username = body.username.strip().lower()
        with store.db() as connection:
            row = connection.execute('SELECT id,account_password_hash FROM clients WHERE account_username=? AND deleted=0', (username,)).fetchone()
        expected = row['account_password_hash'] if row and row['account_password_hash'] else DUMMY_HASH
        valid = store.password_matches(body.password, expected)
        if not row or not valid:
            raise HTTPException(401, 'Неверный логин или пароль')
        token = secrets.token_urlsafe(32)
        ttl = SESSION_TTL if body.remember else 43200
        with store.db() as connection:
            # Serialize against password resets; an old password cannot create a new session after a reset.
            connection.execute('BEGIN IMMEDIATE')
            fresh = connection.execute('SELECT account_username,account_password_hash FROM clients WHERE id=? AND deleted=0', (row['id'],)).fetchone()
            if not fresh or fresh['account_username'] != username or not hmac.compare_digest(fresh['account_password_hash'] or '', expected):
                raise HTTPException(401, 'Неверный логин или пароль')
            connection.execute('DELETE FROM client_sessions WHERE expires_at<=?', (store.now(),))
            connection.execute('INSERT INTO client_sessions(hash,client_id,expires_at,remembered) VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], store.now() + ttl, int(body.remember)))
        with ATTEMPTS_LOCK:
            # A successful account may release only its own reservation, never
            # guesses against other accounts sharing the same IP.
            attempts = ATTEMPTS.get(ip)
            if attempts is not None:
                try:
                    attempts.remove(attempt)
                except ValueError:
                    pass
                if not attempts:
                    ATTEMPTS.pop(ip, None)
        response.set_cookie(COOKIE, token, max_age=ttl if body.remember else None, httponly=True, secure=not store.DEVELOPMENT, samesite='strict', path='/')
        result = access_view(store.get_client(row['id']))
        result.update(account_username=username, csrf=csrf(token))
        return result

    @router.get('/api/account/me')
    def me(auth=Depends(authenticated_user)):
        row, token = auth
        result = access_view(row)
        result.update(account_username=row['account_username'], csrf=csrf(token))
        return result

    @router.post('/api/account/logout')
    def logout(response: Response, auth=Depends(authenticated_user)):
        _, token = auth
        with store.db() as connection:
            connection.execute('DELETE FROM client_sessions WHERE hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie(COOKIE, path='/', secure=not store.DEVELOPMENT, httponly=True, samesite='strict')
        return {'ok': True}

    @router.post('/api/account/password')
    def change_password(body: UserPasswordChange, response: Response, auth=Depends(authenticated_user)):
        row, token = auth
        if body.new_password != body.confirm_password:
            raise HTTPException(422, 'Новые пароли не совпадают')
        if body.new_password == body.current_password:
            raise HTTPException(400, 'Новый пароль должен отличаться от текущего')
        current = time.monotonic()
        with ATTEMPTS_LOCK:
            if len(PASSWORD_ATTEMPTS) > 1000:
                for key in list(PASSWORD_ATTEMPTS):
                    if not PASSWORD_ATTEMPTS[key] or PASSWORD_ATTEMPTS[key][-1][0] < current - 900:
                        PASSWORD_ATTEMPTS.pop(key, None)
            attempts = PASSWORD_ATTEMPTS[row['id']]
            while attempts and attempts[0][0] < current - 900:
                attempts.popleft()
            if len(attempts) >= 5:
                raise HTTPException(429, 'Слишком много попыток. Повторите через 15 минут')
            attempt = (current, secrets.token_hex(8))
            attempts.append(attempt)
        if not store.password_matches(body.current_password, row['account_password_hash']):
            raise HTTPException(400, 'Текущий пароль неверен')
        next_hash = store.password_hash(body.new_password)
        next_token = secrets.token_urlsafe(32)
        old_digest = hashlib.sha256(token.encode()).hexdigest()
        with store.db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            fresh = connection.execute('SELECT account_username,account_password_hash FROM clients WHERE id=? AND deleted=0', (row['id'],)).fetchone()
            session = connection.execute('SELECT expires_at,remembered FROM client_sessions WHERE hash=? AND client_id=? AND expires_at>?', (old_digest, row['id'], store.now())).fetchone()
            if not fresh or not session or not hmac.compare_digest(fresh['account_password_hash'] or '', row['account_password_hash']):
                raise HTTPException(401, 'Сессия завершена. Войдите ещё раз')
            connection.execute('UPDATE clients SET account_password_hash=? WHERE id=?', (next_hash, row['id']))
            connection.execute('DELETE FROM client_sessions WHERE client_id=?', (row['id'],))
            connection.execute('INSERT INTO client_sessions(hash,client_id,expires_at,remembered) VALUES (?,?,?,?)', (hashlib.sha256(next_token.encode()).hexdigest(), row['id'], session['expires_at'], session['remembered']))
            store.event('account_password_changed', row['id'], connection=connection)
        with ATTEMPTS_LOCK:
            attempts = PASSWORD_ATTEMPTS.get(row['id'])
            if attempts is not None:
                try:
                    attempts.remove(attempt)
                except ValueError:
                    pass
                if not attempts:
                    PASSWORD_ATTEMPTS.pop(row['id'], None)
        # Rotate even the current session's token; preserve its original expiry
        # and remembered-login choice rather than extending its lifetime.
        ttl = max(1, session['expires_at'] - store.now())
        response.set_cookie(COOKIE, next_token, max_age=ttl if session['remembered'] else None, httponly=True, secure=not store.DEVELOPMENT, samesite='strict', path='/')
        result = access_view(store.get_client(row['id']))
        result.update(account_username=fresh['account_username'], csrf=csrf(next_token))
        return result

    @router.get('/api/account/qr.svg')
    def qr(auth=Depends(authenticated_user)):
        row, _ = auth
        code = qrcode.make(store.BASE_URL + '/sub/' + row['token'], image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
        output = io.BytesIO()
        code.save(output)
        return Response(output.getvalue(), media_type='image/svg+xml', headers={'Cache-Control': 'no-store'})

    @router.post('/api/admin/clients/{client_id}/account')
    def reset_credentials(client_id: str, body: CredentialFields, _=Depends(admin_dependency)):
        with store.db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            credentials = save_credentials(connection, client_id, body.account_username, body.account_password, force=True)
        return {'id': client_id, 'account_username': credentials['username'], 'account_credentials': credentials}

    return router
