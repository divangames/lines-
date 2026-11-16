set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
umask 077
install -d -m 700 /root/VPN/portal /root/VPN/backups
if ! id linea >/dev/null 2>&1; then useradd --system --home-dir /var/lib/linea --shell /usr/sbin/nologin linea; fi
install -d -m 755 /opt/linea /opt/linea/bin
install -d -m 700 -o linea -g linea /var/lib/linea
install -d -m 750 -o root -g linea /etc/linea
if ! python3 -m venv /opt/linea/venv; then
  apt-get update -qq
  apt-get install -y -qq python3-venv
  python3 -m venv /opt/linea/venv
fi
python3 - <<'PY'
import hashlib,urllib.request,zipfile,io,pathlib
target=pathlib.Path('/opt/linea/bin/xray')
if not target.exists():
    url='https://github.com/XTLS/Xray-core/releases/download/v26.11.9/Xray-linux-64.zip'
    raw=urllib.request.urlopen(url,timeout=90).read()
    expected='b651f7e1d9966ee2c1b1ee1bf8b52c72771824d3065dce96bbc8bcc19ed95f82'
    if hashlib.sha256(raw).hexdigest()!=expected: raise SystemExit('Xray checksum mismatch')
    archive=zipfile.ZipFile(io.BytesIO(raw))
    target.write_bytes(archive.read('xray'))
    target.chmod(0o755)
    pathlib.Path('/root/VPN/portal/XRAY-SOURCE.txt').write_text(url+'\nsha256 '+expected+'\n')
print('Verified Xray binary ready')
PY
/opt/linea/bin/xray version | head -n 2
echo 'Server prerequisites ready'
