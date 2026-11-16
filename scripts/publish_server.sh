set -euo pipefail
umask 077
python3 - <<'PY'
from pathlib import Path
from datetime import datetime,timezone
import subprocess
path=Path('/root/VPN/Caddyfile')
old=path.read_text()
if 'reverse_proxy 127.0.0.1:8088' in old:
    print('Public routing already configured')
else:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=Path('/root/VPN/backups/Caddyfile-'+stamp)
    backup.write_text(old)
    backup.chmod(0o600)
    normalized=old.expandtabs(4)
    anchor='    root * /root/VPN/www\n    file_server'
    if normalized.count(anchor)!=1 or normalized.count('    forward_proxy {')!=1:
        raise SystemExit('Unexpected Caddy structure; unchanged')
    new=normalized.replace('    forward_proxy {','    route {\n        forward_proxy {',1)
    new=new.replace(anchor,'''        request_body {
            max_size 64KB
        }
        reverse_proxy 127.0.0.1:8088 {
            header_up X-Real-IP {remote_host}
        }
    }''',1)
    candidate=path.with_name('Caddyfile.linea-next')
    candidate.write_text(new)
    candidate.chmod(0o600)
    result=subprocess.run(['/root/VPN/bin/caddy','validate','--adapter','caddyfile','--config',str(candidate)],capture_output=True)
    if result.returncode:
        candidate.unlink()
        raise SystemExit('Caddy validation failed; current file unchanged')
    candidate.replace(path)
    subprocess.run(['systemctl','kill','-s','SIGUSR1','naiveproxy'],check=True)
    print('Validated and gracefully reloaded HTTPS routing. Backup: '+str(backup))
PY
systemctl is-active naiveproxy linea-xray linea-portal
curl -fsS https://217.60.19.243/healthz
echo
