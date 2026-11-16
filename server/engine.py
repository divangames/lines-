import json
import os
import re
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo

from . import store, youtube

TAG = "linea-vless"
API = "127.0.0.1:10085"
XRAY = Path(os.environ.get("LINEA_XRAY", store.CONFIG.get("xray", "/opt/linea/bin/xray")))
LOCK = threading.RLock()
APPLIED = {}
LAST_ERROR = ""
LAST_POLL = None


def ad_filter_asset():
    try:
        asset = json.loads(Path('/var/lib/linea-filter/filter-status.json').read_text())['asset']
        if re.fullmatch(r'linea-ads-[0-9a-f]{16}\.dat', asset):
            return asset
    except (OSError, ValueError, KeyError):
        pass
    return 'linea-ads.dat'


def uri(row):
    host = store.CONFIG["server_host"]
    query = urlencode({"encryption": "none", "security": "tls", "sni": host, "fp": "chrome",
                       "type": "ws", "host": host, "path": "/tunnel/" + row["tunnel_key"]})
    return f"vless://{row['uuid']}@{host}:443?{query}#{quote(store.settings()['name'] + ' · ' + row['name'])}"


def xray_config(rows):
    config = {
        "log": {"loglevel": "warning", "access": "none"},
        "api": {"tag": "api", "services": ["HandlerService", "StatsService", "RoutingService"]},
        "dns": {"servers": ["tcp+local://127.0.0.1"], "queryStrategy": "UseIP"},
        "stats": {},
        "policy": {"levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True,
                                              "handshake": 15, "connIdle": 300, "bufferSize": 64}}},
        "inbounds": [
            {"tag": "api", "listen": "127.0.0.1", "port": 10085, "protocol": "dokodemo-door",
             "settings": {"address": "127.0.0.1"}},
            {"tag": TAG, "listen": "127.0.0.1", "port": 10000, "protocol": "vless",
             "settings": {"clients": [{"id": r["uuid"], "email": r["email"], "level": 0} for r in rows], "decryption": "none"},
             "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True},
             "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/internal-linea"}}}
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct", "settings": {"targetStrategy": "ForceIP"}},
            {"protocol": "blackhole", "tag": "blocked"},
            {"protocol": "dns", "tag": "filtered-dns", "settings": {
                "rewriteAddress": "127.0.0.1", "rewritePort": 53,
                "rules": [{"action": "direct"}]}}
        ],
        "routing": {"domainStrategy": "IPIfNonMatch", "rules": [
            {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
            {"type": "field", "inboundTag": [TAG], "port": "53", "outboundTag": "filtered-dns"},
            {"type": "field", "domain": ["ext:" + ad_filter_asset() + ":ads"], "outboundTag": "blocked"},
            {"type": "field", "ip": ["0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4", "::/128", "::1/128", "fc00::/7", "fe80::/10"], "outboundTag": "blocked"}
        ]}
    }
    if upstream := store.CONFIG.get('youtube_upstream'):
        youtube.apply(config, json.loads(Path(upstream).read_text(encoding='utf-8')))
    return config


def command(action, *arguments):
    result = subprocess.run([str(XRAY), "api", action, "--server=" + API, "-timeout=4", *arguments],
                            capture_output=True, text=True, timeout=8,
                            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    if result.returncode:
        raise RuntimeError("Сервис подключения временно недоступен")
    return result.stdout


def json_command(action, *arguments):
    return json.loads(command(action, *arguments) or "{}")


def persist_config(rows):
    target = store.STATE / "xray.json"
    temporary = store.STATE / "xray.next.json"
    temporary.write_text(json.dumps(xray_config(rows), ensure_ascii=False, indent=2) + "\n")
    if os.name != "nt":
        os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def sync(force=False):
    global APPLIED, LAST_ERROR
    rows = [row for row in store.clients() if store.status(row) == "active"]
    desired = {row["email"]: row["uuid"] for row in rows}
    persist_config(rows)
    if store.DEVELOPMENT and not XRAY.is_file():
        APPLIED = desired
        LAST_ERROR = ""
        return
    try:
        if force:
            actual = json_command("inbounduser", "-tag=" + TAG)
            APPLIED = {item["email"]: "unknown" for item in actual.get("users", []) if item.get("email")}
        for email in list(APPLIED):
            if desired.get(email) != APPLIED[email]:
                command("rmu", "-tag=" + TAG, email)
                del APPLIED[email]
        additions = [row for row in rows if row["email"] not in APPLIED]
        if additions:
            fragment = {"inbounds": [xray_config(additions)["inbounds"][1]]}
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=store.STATE, delete=False) as output:
                json.dump(fragment, output)
                path = output.name
            try:
                response = command("adu", path)
                if f"Added {len(additions)} user(s)" not in response:
                    raise RuntimeError("Не удалось применить профили подключения")
            finally:
                Path(path).unlink(missing_ok=True)
            APPLIED.update({row["email"]: row["uuid"] for row in additions})
        LAST_ERROR = ""
    except Exception:
        LAST_ERROR = "Не удалось связаться с сервисом подключения"
        raise


def marker():
    try:
        pid = (store.STATE / "xray.pid").read_text().strip()
        if not pid.isdigit():
            return "unknown"
        return pid + ":" + Path(f"/proc/{pid}/stat").read_text().split()[21]
    except OSError:
        return "unknown"


def collect():
    global LAST_POLL, LAST_ERROR
    with LOCK:
        if store.DEVELOPMENT and not XRAY.is_file():
            LAST_POLL = store.now()
            return []
        try:
            response = json_command("statsquery", "-pattern=user>>>")
            current_marker = marker()
            rows = {row["email"]: row for row in store.clients(include_deleted=True)}
            today = datetime.now(ZoneInfo("Asia/Krasnoyarsk")).date().isoformat()
            with store.db() as conn:
                for counter in response.get("stat", []):
                    match = re.fullmatch(r"user>>>(.+)>>>traffic>>>(uplink|downlink)", counter.get("name", ""))
                    if not match or match[1] not in rows:
                        continue
                    row = rows[match[1]]
                    value = max(0, int(counter["value"]))
                    previous = conn.execute("SELECT value,marker FROM counters WHERE name=?", (counter["name"],)).fetchone()
                    delta = value if not previous or previous["marker"] != current_marker or value < previous["value"] else value - previous["value"]
                    conn.execute("INSERT INTO counters VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value,marker=excluded.marker", (counter["name"], value, current_marker))
                    if delta:
                        field = "uploaded" if match[2] == "uplink" else "downloaded"
                        conn.execute(f"UPDATE clients SET {field}={field}+?,last_seen_at=? WHERE id=?", (delta, store.now(), row["id"]))
                        conn.execute(f"INSERT INTO daily(day,client_id,{field}) VALUES (?,?,?) ON CONFLICT(day,client_id) DO UPDATE SET {field}={field}+excluded.{field}", (today, row["id"], delta))
            before = set(APPLIED)
            sync()
            blocked = [row["id"] for row in store.clients() if row["email"] in before and store.status(row) != "active"]
            LAST_POLL = store.now()
            LAST_ERROR = ""
            return blocked
        except Exception:
            LAST_ERROR = "Статистика временно недоступна"
            return []
