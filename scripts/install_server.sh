set -euo pipefail
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
if [ -d /opt/linea/server ]; then
  tar -czf "/root/VPN/backups/linea-code-$stamp.tar.gz" -C /opt/linea server dist requirements.lock.txt
fi
tar -xzf /root/VPN/portal/release.tar.gz -C /opt/linea
chown -R root:root /opt/linea/server /opt/linea/dist
find /opt/linea/server /opt/linea/dist -type d -exec chmod 755 {} +
find /opt/linea/server /opt/linea/dist -type f -exec chmod 644 {} +
/opt/linea/venv/bin/pip install --disable-pip-version-check -q -r /opt/linea/requirements.lock.txt
chgrp -R linea /opt/linea/venv
chmod -R g+rX /opt/linea/venv
if [ ! -f /etc/linea/config.json ]; then
  install -m 640 -o root -g linea /root/VPN/portal/production-server.json /etc/linea/config.json
fi
cd /opt/linea
LINEA_CONFIG=/etc/linea/config.json runuser -u linea --preserve-environment -- /opt/linea/venv/bin/python - <<'PY'
from server import store,engine
store.initialize()
engine.persist_config([r for r in store.clients() if store.status(r)=='active'])
PY
cat > /opt/linea/bin/run-xray <<'SH'
#!/bin/sh
umask 077
echo $$ > /var/lib/linea/xray.pid
exec /opt/linea/bin/xray run -config /var/lib/linea/xray.json
SH
chmod 755 /opt/linea/bin/run-xray
cat > /etc/systemd/system/linea-xray.service <<'SERVICE'
[Unit]
Description=Linea VLESS engine
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=linea
Group=linea
ExecStart=/opt/linea/bin/run-xray
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/linea
RestrictSUIDSGID=true
LockPersonality=true
LimitNOFILE=16384
[Install]
WantedBy=multi-user.target
SERVICE
cat > /etc/systemd/system/linea-portal.service <<'SERVICE'
[Unit]
Description=Linea VPN portal
After=network-online.target linea-xray.service
Wants=network-online.target linea-xray.service
[Service]
Type=simple
User=linea
Group=linea
WorkingDirectory=/opt/linea
Environment=LINEA_CONFIG=/etc/linea/config.json
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/linea/venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8088 --workers 1 --no-access-log --no-proxy-headers --ws-max-size 1048576 --ws-max-queue 4
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/linea
RestrictSUIDSGID=true
LockPersonality=true
LimitNOFILE=16384
[Install]
WantedBy=multi-user.target
SERVICE
/opt/linea/bin/xray run -test -config /var/lib/linea/xray.json >/dev/null
systemctl daemon-reload
systemctl enable --now linea-xray linea-portal
systemctl restart linea-portal
echo 'Portal installed on loopback; public routing unchanged'
