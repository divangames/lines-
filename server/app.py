import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect as ws_connect

from . import engine, store, routing, accounts, partners, telegram, support

LOG = logging.getLogger("linea")
CONNECTIONS = defaultdict(set)
PENDING = defaultdict(set)
LOGIN_FAILURES = defaultdict(deque)
FAILURE_LOCK = threading.Lock()
CSRF_SECRET = store.CONFIG["secret"].encode()
# Browsers and desktop clients can keep many HTTP/2, media and DNS tunnels open.
MAX_CLIENT_CONNECTIONS = 256
MAX_TOTAL_CONNECTIONS = 512


async def disconnect(client_id):
    sockets = list(CONNECTIONS.get(client_id, set()) | PENDING.get(client_id, set()))
    await asyncio.gather(*(socket.close(code=1008, reason="Доступ изменён") for socket in sockets), return_exceptions=True)


async def statistics_loop():
    while True:
        await asyncio.sleep(5)
        try:
            blocked = await asyncio.to_thread(engine.collect)
            for client_id in blocked:
                await disconnect(client_id)
            for client_id in set(CONNECTIONS) | set(PENDING):
                row = await asyncio.to_thread(store.get_client, client_id)
                if not row or store.status(row) != "active":
                    await disconnect(client_id)
        except Exception:
            LOG.warning("Background reconciliation will retry")


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    try:
        with engine.LOCK:
            engine.sync(force=True)
    except Exception:
        LOG.warning("VPN engine is not ready; background reconciliation will retry")
    worker = asyncio.create_task(statistics_loop())
    messenger = asyncio.create_task(support.worker())
    yield
    messenger.cancel()
    with suppress(asyncio.CancelledError):
        await messenger
    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker
    for client_id in list(CONNECTIONS):
        await disconnect(client_id)
    # A service update must save the last bytes before Xray is restarted.
    await asyncio.to_thread(engine.collect)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def account_validation_error(request: Request, error: RequestValidationError):
    if request.url.path.startswith('/api/account/'):
        # Password inputs and validation context must not be reflected in 422s.
        details = [{key: item[key] for key in ('type', 'loc', 'msg') if key in item} for item in error.errors()]
        return JSONResponse(status_code=422, content={'detail': details})
    return await request_validation_exception_handler(request, error)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf(token):
    return hmac.new(CSRF_SECRET, token.encode(), hashlib.sha256).hexdigest()


def check_origin(request):
    origin = request.headers.get("origin", "")
    allowed = {store.BASE_URL}
    if store.DEVELOPMENT:
        allowed.update({"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8088"})
    if origin not in allowed:
        raise HTTPException(403, "Источник запроса не разрешён")


def admin(request: Request):
    token = request.cookies.get(store.COOKIE, "")
    if not token or len(token) > 200:
        raise HTTPException(401, "Войдите в панель управления")
    with store.db() as conn:
        session = conn.execute("SELECT expires_at FROM sessions WHERE hash=?", (digest(token),)).fetchone()
    if not session or session["expires_at"] <= store.now():
        raise HTTPException(401, "Сессия завершена. Войдите ещё раз")
    if request.method not in ("GET", "HEAD"):
        check_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf(token)):
            raise HTTPException(403, "Обновите страницу и повторите действие")
    return token


@app.middleware("http")
async def headers_and_limits(request, call_next):
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"detail": "Некорректный запрос"}, status_code=400)
    if content_length > 65536:
        return JSONResponse({"detail": "Запрос слишком большой"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not store.DEVELOPMENT:
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self' https://speed.cloudflare.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path.rstrip("/") == "/account/mini":
        del response.headers["X-Frame-Options"]
        if not store.DEVELOPMENT:
            response.headers["Content-Security-Policy"] = response.headers["Content-Security-Policy"].replace("frame-ancestors 'none'", "frame-ancestors https://web.telegram.org https://*.web.telegram.org").replace("script-src 'self'", "script-src 'self' https://telegram.org")
    if request.url.path.startswith(("/api", "/sub", "/connect", "/admin", "/account")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class ClientInput(accounts.CredentialFields):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=1000)
    quota_gb: float = Field(default=0, ge=0, le=1_000_000, allow_inf_nan=False)
    expires_at: int | None = Field(default=None, ge=0, le=4_102_444_800)
    enabled: bool = True

    @field_validator("name", "note")
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Недопустимые символы")
        return value


class NewClientInput(ClientInput):
    referral_code: str | None = Field(default=None, min_length=16, max_length=16, pattern=r"^[a-fA-F0-9]{16}$")


class SettingsInput(BaseModel):
    name: str = Field(min_length=1, max_length=25)
    tagline: str = Field(min_length=1, max_length=70)
    support_url: str = Field(default="", max_length=300)

    @field_validator("support_url")
    @classmethod
    def support_link(cls, value):
        if value and (urlparse(value).scheme != "https" or not urlparse(value).netloc):
            raise ValueError("Укажите HTTPS-ссылку")
        return value


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=16, max_length=256)


def row_or_404(client_id=None, token=None, tunnel_key=None):
    row = store.get_client(client_id, token, tunnel_key)
    if not row:
        raise HTTPException(404, "Ссылка не найдена или уже отозвана")
    return row


def client_view(row, private=False):
    result = {key: row[key] for key in ("id", "name", "quota_bytes", "expires_at", "uploaded", "downloaded", "created_at", "last_seen_at")}
    result.update(status=store.status(row), used_bytes=row["uploaded"] + row["downloaded"],
                  online=len(CONNECTIONS.get(row["id"], set())) > 0,
                  connections=len(CONNECTIONS.get(row["id"], set())))
    if private:
        result.update(note=row["note"], enabled=bool(row["enabled"]), token=row["token"], account_username=row["account_username"],
                      page_views=row["page_views"], subscription_fetches=row["subscription_fetches"],
                      last_page_at=row["last_page_at"], last_sync_at=row["last_sync_at"],
                      page_url=store.BASE_URL + "/connect/" + row["token"],
                      subscription_url=store.BASE_URL + "/sub/" + row["token"], uri=engine.uri(row))
    return result


@app.get("/api/public")
def public_settings():
    values = store.settings()
    return {**values, "server_online": not bool(engine.LAST_ERROR), "base_url": store.BASE_URL}


@app.get("/healthz")
def health():
    return {"ok": True}


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    check_origin(request)
    ip = request.headers.get("x-real-ip", "local") if request.client and request.client.host in ("127.0.0.1", "::1") else (request.client.host if request.client else "unknown")
    current = time.monotonic()
    with FAILURE_LOCK:
        failures = LOGIN_FAILURES[ip]
        while failures and failures[0] < current - 900:
            failures.popleft()
        if len(failures) >= 8:
            raise HTTPException(429, "Слишком много попыток. Повторите через 15 минут")
    config = store.settings(private=True)
    valid_password = store.password_matches(body.password, config["admin_password_hash"])
    if not hmac.compare_digest(body.username, config["admin_username"]) or not valid_password:
        with FAILURE_LOCK:
            failures.append(current)
        raise HTTPException(401, "Неверный логин или пароль")
    with FAILURE_LOCK:
        LOGIN_FAILURES.pop(ip, None)
    token = secrets.token_urlsafe(32)
    with store.db() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (store.now(),))
        conn.execute("INSERT INTO sessions VALUES (?,?)", (digest(token), store.now() + 43200))
    response.set_cookie(store.COOKIE, token, max_age=43200, httponly=True, secure=not store.DEVELOPMENT, samesite="strict", path="/")
    return {"csrf": csrf(token), "username": config["admin_username"]}


@app.get("/api/auth/me")
def me(token=Depends(admin)):
    return {"username": store.settings(private=True)["admin_username"], "csrf": csrf(token)}


@app.post("/api/auth/logout")
def logout(response: Response, token=Depends(admin)):
    with store.db() as conn:
        conn.execute("DELETE FROM sessions WHERE hash=?", (digest(token),))
    response.delete_cookie(store.COOKIE, path="/", secure=not store.DEVELOPMENT, httponly=True, samesite="strict")
    return {"ok": True}


@app.get("/api/admin/overview")
def overview(_=Depends(admin)):
    rows = store.clients()
    today = datetime.now(ZoneInfo("Asia/Krasnoyarsk")).date()
    with store.db() as conn:
        days = {row["day"]: dict(row) for row in conn.execute("SELECT day,SUM(uploaded) AS uploaded,SUM(downloaded) AS downloaded FROM daily GROUP BY day ORDER BY day DESC LIMIT 30")}
        invitations = partners.pending(conn)
        events = [dict(row) for row in conn.execute("SELECT events.*,clients.name AS client_name FROM events LEFT JOIN clients ON clients.id=events.client_id ORDER BY events.id DESC LIMIT 30")]
        all_time = conn.execute("SELECT COALESCE(SUM(uploaded+downloaded),0) FROM daily").fetchone()[0]
    history = []
    for index in range(13, -1, -1):
        date = (today - timedelta(days=index)).isoformat()
        history.append({"day": date, "uploaded": days.get(date, {}).get("uploaded", 0), "downloaded": days.get(date, {}).get("downloaded", 0)})
    return {"total": len(rows), "active": sum(store.status(row) == "active" for row in rows),
            "online": sum(bool(CONNECTIONS.get(row["id"])) for row in rows),
            "used_bytes": all_time,
            "today_bytes": sum(days.get(today.isoformat(), {}).get(field, 0) for field in ("uploaded", "downloaded")),
            "history": history, "events": events, "engine_error": engine.LAST_ERROR,
            "last_poll": engine.LAST_POLL, "settings": store.settings(), "partner_requests": invitations}


@app.get("/api/admin/clients")
def list_clients(_=Depends(admin)):
    return [client_view(row, True) for row in store.clients()]


@app.post("/api/admin/clients")
def create_client(body: NewClientInput, _=Depends(admin)):
    if not body.name.strip():
        raise HTTPException(422, "Укажите имя")
    with engine.LOCK:
        if len(store.clients()) >= 500:
            raise HTTPException(409, "Достигнут лимит в 500 активных записей")
        identifier = secrets.token_hex(8)
        with store.db() as conn:
            conn.execute("""INSERT INTO clients(id,name,note,token,tunnel_key,uuid,email,enabled,quota_bytes,expires_at,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                         (identifier, body.name.strip(), body.note, secrets.token_urlsafe(32), secrets.token_urlsafe(32), str(uuid.uuid4()),
                          identifier + "@linea", int(body.enabled), round(body.quota_gb * 1024**3), body.expires_at or None, store.now()))
            if body.referral_code:
                partners.invite(conn, identifier, body.referral_code)
            credentials = accounts.save_credentials(conn, identifier, body.account_username, body.account_password, force=True)
            store.event("created", identifier, connection=conn)
        try:
            engine.sync()
        except Exception:
            LOG.warning("New access saved; engine reconciliation will retry")
    result = client_view(row_or_404(identifier), True)
    result['account_credentials'] = credentials
    return result


@app.put("/api/admin/clients/{client_id}")
async def update_client(client_id: str, body: ClientInput, _=Depends(admin)):
    if not body.name.strip():
        raise HTTPException(422, "Укажите имя")
    def update():
        with engine.LOCK:
            previous = row_or_404(client_id)
            with store.db() as conn:
                conn.execute("UPDATE clients SET name=?,note=?,quota_bytes=?,expires_at=?,enabled=? WHERE id=?",
                             (body.name.strip(), body.note, round(body.quota_gb * 1024**3), body.expires_at or None, int(body.enabled), client_id))
                support.renewal(conn, client_id, previous["expires_at"], body.expires_at or None)
                credentials = accounts.save_credentials(conn, client_id, body.account_username, body.account_password)
                store.event("enabled" if body.enabled and not previous["enabled"] else ("disabled" if not body.enabled and previous["enabled"] else "updated"), client_id, connection=conn)
            try:
                engine.sync()
            except Exception:
                LOG.warning("Access change saved; engine reconciliation will retry")
        return row_or_404(client_id), credentials
    row, credentials = await asyncio.to_thread(update)
    if store.status(row) != "active":
        await disconnect(client_id)
    result = client_view(row, True)
    if credentials:
        result['account_credentials'] = credentials
    return result


@app.post("/api/admin/clients/{client_id}/rotate")
async def rotate_client(client_id: str, _=Depends(admin)):
    def rotate():
        with engine.LOCK:
            row_or_404(client_id)
            with store.db() as conn:
                conn.execute("UPDATE clients SET token=?,tunnel_key=?,uuid=? WHERE id=?", (secrets.token_urlsafe(32), secrets.token_urlsafe(32), str(uuid.uuid4()), client_id))
                store.event("rotated", client_id, connection=conn)
            try:
                engine.sync()
            except Exception:
                LOG.warning("Link rotated; engine reconciliation will retry")
    await asyncio.to_thread(rotate)
    await disconnect(client_id)
    return client_view(row_or_404(client_id), True)


@app.post("/api/admin/clients/{client_id}/reset-traffic")
def reset_traffic(client_id: str, _=Depends(admin)):
    with engine.LOCK:
        row_or_404(client_id)
        engine.collect()
        with store.db() as conn:
            conn.execute("UPDATE clients SET uploaded=0,downloaded=0 WHERE id=?", (client_id,))
            store.event("traffic_reset", client_id, connection=conn)
        try:
            engine.sync()
        except Exception:
            LOG.warning("Traffic reset saved; engine reconciliation will retry")
    return client_view(row_or_404(client_id), True)


@app.delete("/api/admin/clients/{client_id}")
async def archive_client(client_id: str, _=Depends(admin)):
    def archive():
        with engine.LOCK:
            row_or_404(client_id)
            with store.db() as conn:
                conn.execute("UPDATE clients SET deleted=1,enabled=0 WHERE id=?", (client_id,))
                conn.execute('DELETE FROM client_sessions WHERE client_id=?', (client_id,))
                store.event("archived", client_id, connection=conn)
            try:
                engine.sync()
            except Exception:
                LOG.warning("Access archived; engine reconciliation will retry")
    await asyncio.to_thread(archive)
    await disconnect(client_id)
    return {"ok": True}


@app.put("/api/admin/settings")
def update_settings(body: SettingsInput, _=Depends(admin)):
    if not body.name.strip() or not body.tagline.strip():
        raise HTTPException(422, "Название и заголовок не могут быть пустыми")
    with store.db() as conn:
        for key, value in body.model_dump().items():
            conn.execute("UPDATE settings SET value=? WHERE key=?", (value.strip(), key))
        store.event("settings_updated", connection=conn)
    return store.settings()


@app.put("/api/admin/offers")
def update_offers(body: partners.Terms, _=Depends(admin)):
    if not body.router_help.strip():
        raise HTTPException(422, "Укажите условия помощи с роутером")
    with store.db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES ('offer_terms',?)", (body.model_dump_json(),))
    return store.settings()


INVITE_ATTEMPTS = deque(maxlen=200)


@app.post("/api/invitations/{code}/join", status_code=202)
def join_invitation(code: str, body: partners.JoinRequest, request: Request):
    check_origin(request)
    peer = request.client.host if request.client else "unknown"
    ip = request.headers.get("x-real-ip",peer) if peer in ("127.0.0.1","::1") else peer
    now = time.monotonic()
    with FAILURE_LOCK:
        while INVITE_ATTEMPTS and INVITE_ATTEMPTS[0][0] < now-600:
            INVITE_ATTEMPTS.popleft()
        if len(INVITE_ATTEMPTS)>=200 or sum(source==ip for _,source in INVITE_ATTEMPTS)>=10:
            raise HTTPException(429, "Повторите попытку через 10 минут")
        INVITE_ATTEMPTS.append((now,ip))
    partners.submit(code,body)
    return {"ok": True}


@app.post("/api/admin/invitations/{request_id}/payment")
def pay_invitation(request_id: str, _=Depends(admin)):
    with engine.LOCK:
        partners.activate(request_id)
        try:
            engine.sync()
        except Exception:
            LOG.warning("Invitation activated; engine reconciliation will retry")
    return {"ok": True}


@app.get("/api/admin/clients/{client_id}/referral")
def get_referral(client_id: str, _=Depends(admin)):
    row_or_404(client_id)
    return partners.referral(client_id)


@app.post("/api/admin/clients/{client_id}/referral/payment")
def referral_payment(client_id: str, _=Depends(admin)):
    with engine.LOCK:
        partners.confirm_payment(client_id)
        try:
            engine.sync()
        except Exception:
            LOG.warning("Referral saved; engine reconciliation will retry")
    return partners.referral(client_id)


@app.post("/api/admin/password")
def change_password(body: ChangePassword, response: Response, _=Depends(admin)):
    if not store.password_matches(body.current_password, store.settings(private=True)["admin_password_hash"]):
        raise HTTPException(400, "Текущий пароль неверен")
    with store.db() as conn:
        conn.execute("UPDATE settings SET value=? WHERE key='admin_password_hash'", (store.password_hash(body.new_password),))
        conn.execute("DELETE FROM sessions")
        store.event("password_updated", connection=conn)
    response.delete_cookie(store.COOKIE, path="/", secure=not store.DEVELOPMENT)
    return {"ok": True}


@app.get("/api/access/{token}")
def access(token: str):
    row = row_or_404(token=token)
    return access_view(row)


def access_view(row):
    result = client_view(row)
    result["partner"] = partners.summary(row["id"])
    result["settings"] = store.settings()
    result["subscription_url"] = store.BASE_URL + "/sub/" + row["token"]
    result["page_url"] = store.BASE_URL + "/connect/" + row["token"]
    if store.status(row) == "active":
        result["uri"] = engine.uri(row)
    return result


@app.post("/api/access/{token}/view")
def page_view(token: str):
    row = row_or_404(token=token)
    with store.db() as conn:
        conn.execute("UPDATE clients SET page_views=page_views+1,last_page_at=? WHERE id=?", (store.now(), row["id"]))
    return {"ok": True}


@app.get("/api/access/{token}/qr.svg")
def access_qr(token: str):
    row = row_or_404(token=token)
    code = qrcode.make(store.BASE_URL + "/sub/" + row["token"], image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
    output = io.BytesIO()
    code.save(output)
    return Response(output.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


def subscription_response(token: str, request: Request):
    row = row_or_404(token=token)
    if store.status(row) != "active":
        raise HTTPException(403, "Доступ приостановлен, закончился срок или трафик")
    with store.db() as conn:
        conn.execute("UPDATE clients SET subscription_fetches=subscription_fetches+1,last_sync_at=? WHERE id=?", (store.now(), row["id"]))
    title = "base64:" + base64.b64encode(engine.profile_name(row).encode()).decode()
    headers = {"profile-title": title, "profile-update-interval": "1",
               "subscription-userinfo": f"upload={row['uploaded']}; download={row['downloaded']}; total={row['quota_bytes']}; expire={row['expires_at'] or 0}",
               "profile-web-page-url": store.BASE_URL + "/connect/" + row["token"],
               "Content-Disposition": 'attachment; filename="linea-subscription.txt"'}
    support = store.settings()["support_url"]
    headers.update(routing.subscription_headers(request.headers.get("user-agent", "")))
    if support:
        headers["support-url"] = support
    return Response(base64.b64encode((engine.uri(row) + "\n").encode()).decode(), media_type="text/plain", headers=headers)


def browser_document(request: Request):
    agent = request.headers.get("user-agent", "")
    vpn_client = re.search(r"happ|v2ray|v2box|hiddify|shadowrocket|streisand|sing-box|clash|mihomo|nekobox", agent, re.I)
    return not vpn_client and (
        request.headers.get("sec-fetch-dest", "").lower() in ("document", "iframe")
        or "text/html" in request.headers.get("accept", "").lower()
    )


@app.api_route("/sub/{token}", methods=["GET", "HEAD"])
def subscription(token: str, request: Request):
    response = RedirectResponse("/connect/" + token, status_code=307) if browser_document(request) else subscription_response(token, request)
    response.headers["Vary"] = "Accept, User-Agent, Sec-Fetch-Dest"
    return response


@app.api_route("/connect/{token}", methods=["GET", "HEAD"])
def connection_link(token: str, request: Request):
    """A shared invitation opens the guide in browsers and imports in VPN clients."""
    response = frontend("index.html") if browser_document(request) else subscription_response(token, request)
    response.headers["Vary"] = "Accept, User-Agent, Sec-Fetch-Dest"
    return response


@app.websocket("/tunnel/{key}")
async def tunnel(websocket: WebSocket, key: str):
    row = await asyncio.to_thread(store.get_client, None, None, key)
    if not row or store.status(row) != "active":
        await websocket.close(code=1008)
        return
    identifier = row["id"]
    if len(CONNECTIONS.get(identifier, ())) + len(PENDING.get(identifier, ())) >= MAX_CLIENT_CONNECTIONS or sum(map(len, CONNECTIONS.values())) + sum(map(len, PENDING.values())) >= MAX_TOTAL_CONNECTIONS:
        await websocket.close(code=1008)
        return
    PENDING[identifier].add(websocket)
    try:
        await websocket.accept()
        initial = bytearray()
        async with asyncio.timeout(12):
            while len(initial) < 17:
                initial.extend(await websocket.receive_bytes())
                if len(initial) > 1048576:
                    raise ValueError("Handshake is too large")
        if initial[0] != 0 or not hmac.compare_digest(bytes(initial[1:17]), uuid.UUID(row["uuid"]).bytes):
            await websocket.close(code=1008)
            return
        async with ws_connect("ws://127.0.0.1:10000/internal-linea", proxy=None, compression=None,
                              max_size=1048576, max_queue=4, open_timeout=10, ping_interval=25) as upstream:
            fresh = await asyncio.to_thread(store.get_client, row["id"])
            if not fresh or fresh["uuid"] != row["uuid"] or store.status(fresh) != "active":
                await websocket.close(code=1008)
                return
            CONNECTIONS[row["id"]].add(websocket)
            PENDING[identifier].discard(websocket)
            await upstream.send(bytes(initial))

            async def to_engine():
                while True:
                    await upstream.send(await websocket.receive_bytes())

            async def from_engine():
                async for data in upstream:
                    if isinstance(data, bytes):
                        await websocket.send_bytes(data)

            tasks = [asyncio.create_task(to_engine()), asyncio.create_task(from_engine())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (WebSocketDisconnect, TimeoutError, ValueError, RuntimeError, OSError):
        pass
    except Exception:
        LOG.warning("VPN channel closed")
    finally:
        PENDING[identifier].discard(websocket)
        if not PENDING[identifier]:
            PENDING.pop(identifier, None)
        CONNECTIONS[row["id"]].discard(websocket)
        if not CONNECTIONS[row["id"]]:
            CONNECTIONS.pop(row["id"], None)
        with suppress(Exception):
            await websocket.close()


app.include_router(telegram.make_router(check_origin, csrf, access_view))
app.include_router(accounts.make_router(admin, check_origin, csrf, access_view))


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /admin\nDisallow: /account\nDisallow: /connect/\nDisallow: /sub/\nDisallow: /api/\n", media_type="text/plain")


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith(("api/", "sub/", "tunnel/", "private/")):
        raise HTTPException(404, "Страница не найдена")
    target = (store.DIST / path).resolve()
    if target.is_relative_to(store.DIST.resolve()) and target.is_file():
        return FileResponse(target)
    index = store.DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Интерфейс ещё собирается")
    return FileResponse(index)
