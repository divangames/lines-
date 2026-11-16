"""Run on the Linea VPS: prepare HTTPS, then activate after DNS/TLS validation."""
import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

DOMAIN = "linesonline.pro"
IP = "217.60.19.243"
BASE = "https://" + DOMAIN
CADDY = Path("/root/VPN/Caddyfile")
CONFIG = Path("/etc/linea/config.json")
STATE = Path("/root/VPN/portal/domain-transition.json")
BEGIN = "# BEGIN LINEA CUSTOM DOMAIN"
END = "# END LINEA CUSTOM DOMAIN"
REDIRECT_MARKER = "        # Linea canonical website; legacy subscriptions and tunnels stay available."


def run(args, *, check=True, timeout=25):
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout)


def pids():
    result = {}
    for name in ("linea-portal", "linea-xray", "naiveproxy"):
        run(["systemctl", "is-active", "--quiet", name])
        result[name] = run(["systemctl", "show", "-p", "MainPID", "--value", name]).stdout.strip()
    return result


def atomic_write(path, content):
    metadata = path.stat()
    candidate = path.with_name(path.name + ".domain-next")
    candidate.write_text(content)
    os.chown(candidate, metadata.st_uid, metadata.st_gid)
    candidate.chmod(metadata.st_mode & 0o777)
    candidate.replace(path)


def backup():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = Path("/root/VPN/backups") / ("domain-" + stamp)
    directory.mkdir(mode=0o700, parents=True)
    for source in (CADDY, CONFIG):
        target = directory / source.name
        target.write_bytes(source.read_bytes())
        target.chmod(0o600)
    return str(directory)


def reload_caddy(content):
    candidate = CADDY.with_name("Caddyfile.domain-validate")
    candidate.write_text(content)
    candidate.chmod(0o600)
    result = run(["/root/VPN/bin/caddy", "validate", "--config", str(candidate), "--adapter", "caddyfile"], check=False)
    candidate.unlink()
    if result.returncode:
        raise RuntimeError("Candidate Caddy configuration failed validation; current configuration retained")
    atomic_write(CADDY, content)
    run(["systemctl", "kill", "-s", "SIGUSR1", "naiveproxy"])
    time.sleep(1)


def dns():
    result = {}
    for server in ("ns1.reg.ru", "ns2.reg.ru", "1.1.1.1", "8.8.8.8"):
        result[server] = {}
        for host in (DOMAIN, "www." + DOMAIN):
            response = run(["dig", "@" + server, host, "A", "+short", "+time=2", "+tries=1"], check=False, timeout=5)
            result[server][host] = response.stdout.strip().splitlines() if response.returncode == 0 else []
    return result


def request(host, path="/healthz", *, https=True):
    port = "443" if https else "80"
    response = run(["curl", "--noproxy", "*", "--silent", "--show-error", "--max-time", "8", "--resolve",
                    host + ":" + port + ":127.0.0.1", "-w", "\n%{http_code}",
                    ("https://" if https else "http://") + host + path], check=False, timeout=10)
    body, _, code = response.stdout.rpartition("\n")
    return {"ok": response.returncode == 0, "code": code, "body": body}


def tls_ready():
    apex = request(DOMAIN)
    www = request("www." + DOMAIN)
    return apex["ok"] and apex["code"] == "200" and json.loads(apex["body"]).get("ok") is True and www["ok"] and www["code"] == "301"


def save_state(value):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, indent=2) + "\n")
    STATE.chmod(0o600)


def prepare():
    before = pids()
    previous = CADDY.read_text()
    if BEGIN in previous:
        assert previous.count(BEGIN) == previous.count(END) == 1
        print(json.dumps({"prepared": True, "already_present": True, "dns": dns(), "tls_ready": tls_ready()}))
        return
    assert DOMAIN not in previous, "Domain already appears outside this managed configuration"
    assert ":443, " + IP + " {" in previous, "Unexpected existing HTTPS configuration"
    issuer = "    tls {\n        issuer acme {\n            dir https://acme-v02.api.letsencrypt.org/directory\n        }\n    }\n"
    content = previous.rstrip() + "\n\n" + BEGIN + "\n" + DOMAIN + " {\n" + issuer + """    route {
        request_body {
            max_size 64KB
        }
        reverse_proxy 127.0.0.1:8088 {
            header_up X-Real-IP {remote_host}
        }
    }
}

""" + "www." + DOMAIN + " {\n" + issuer + "    redir " + BASE + "{uri} permanent\n}\n" + END + "\n"
    saved = backup()
    try:
        reload_caddy(content)
        assert pids() == before, "A service PID changed during graceful HTTPS reload"
        check = request(IP)
        assert check["ok"] and check["code"] == "200" and json.loads(check["body"])["ok"]
        assert request(DOMAIN, "/", https=False)["code"] == "308"
    except Exception:
        reload_caddy(previous)
        raise
    state = {"prepared": True, "activated": False, "domain": DOMAIN, "prepare_backup": saved,
             "vpn_services_unchanged": True, "dns": dns(), "tls_ready": tls_ready()}
    save_state(state)
    print(json.dumps(state))


def activate():
    state = json.loads(STATE.read_text())
    addresses = dns()
    assert all(addresses[server][host] == [IP] for server in ("ns1.reg.ru", "ns2.reg.ru") for host in (DOMAIN, "www." + DOMAIN)), "Authoritative DNS has not propagated yet"
    assert tls_ready(), "A trusted HTTPS certificate is not available yet; existing site retained"
    before = pids()
    previous_caddy = CADDY.read_text()
    previous_config = CONFIG.read_text()
    config = json.loads(previous_config)
    assert config["base_url"] in ("https://" + IP, BASE)
    assert config["server_host"] in (IP, DOMAIN)
    config.update(base_url=BASE, server_host=DOMAIN)
    prefix, separator, suffix = previous_caddy.partition(BEGIN)
    assert separator and END in suffix
    if REDIRECT_MARKER not in prefix:
        anchor = "        request_body {"
        assert prefix.count(anchor) == 1
        redirect = REDIRECT_MARKER + "\n" + """        @linea_website {
            host 217.60.19.243
            path / /admin /admin/* /account /account/*
        }
        redir @linea_website https://linesonline.pro{uri} permanent
        @linea_legacy_page {
            host 217.60.19.243
            path /connect/* /sub/*
            header Accept *text/html*
        }
        redir @linea_legacy_page https://linesonline.pro{uri} permanent
"""
        prefix = prefix.replace(anchor, redirect + anchor, 1)
    saved = backup()
    try:
        reload_caddy(prefix + separator + suffix)
        atomic_write(CONFIG, json.dumps(config, indent=2) + "\n")
        run(["systemctl", "restart", "linea-portal"])
        for _ in range(30):
            check = request(DOMAIN, "/api/public")
            if check["ok"] and check["code"] == "200" and json.loads(check["body"]).get("base_url") == BASE:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Portal did not become healthy after domain activation")
        after = pids()
        assert all(after[name] == before[name] for name in ("linea-xray", "naiveproxy")), "VPN service PID changed"
        assert tls_ready()
        assert request(IP, "/admin")["code"] == "301"
    except Exception:
        atomic_write(CONFIG, previous_config)
        reload_caddy(previous_caddy)
        run(["systemctl", "restart", "linea-portal"])
        raise
    state.update(activated=True, activate_backup=saved, dns=addresses, tls_ready=True, base_url=BASE, server_host=DOMAIN, vpn_services_unchanged=True)
    save_state(state)
    print(json.dumps(state))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "activate", "status"))
    phase = parser.parse_args().phase
    if phase == "prepare":
        prepare()
    elif phase == "activate":
        activate()
    else:
        print(json.dumps({"dns": dns(), "tls_ready": tls_ready(), "base_url": json.loads(CONFIG.read_text())["base_url"], "services": pids()}))
