#!/usr/bin/env bash
set -euo pipefail
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf "/root/VPN/backups/before-routing-$stamp.tar.gz" -C /opt/linea server
cd /opt/linea
LINEA_CONFIG=/etc/linea/config.json /opt/linea/venv/bin/python - <<'PY'
from server import store
import sqlite3
from datetime import datetime, timezone
destination='/root/VPN/backups/linea-db-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite3'
with store.db() as source, sqlite3.connect(destination) as backup:
    source.backup(backup)
    assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
print('Database backup verified')
PY
install -m 644 /root/VPN/filter/app.py /opt/linea/server/app.py
install -m 644 /root/VPN/filter/engine.py /opt/linea/server/engine.py
install -m 644 /root/VPN/filter/routing.py /opt/linea/server/routing.py
install -d -m 755 /etc/systemd/system/naiveproxy.service.d /etc/systemd/system/linea-xray.service.d
for service in naiveproxy linea-xray; do
cat > "/etc/systemd/system/$service.service.d/filter.conf" <<'UNIT'
[Unit]
After=linea-filter.service
Wants=linea-filter.service
[Service]
Environment=GODEBUG=netdns=go
BindReadOnlyPaths=/etc/linea-filter/resolv.conf:/etc/resolv.conf
UNIT
done
cat >> /etc/systemd/system/linea-xray.service.d/filter.conf <<'UNIT'
Environment=XRAY_LOCATION_ASSET=/var/lib/linea-filter
UNIT
# Test the exact new generated configuration before changing active tunnels.
LINEA_CONFIG=/etc/linea/config.json /opt/linea/venv/bin/python - <<'PY'
import json
from server import store,engine
rows=[r for r in store.clients() if store.status(r)=='active']
open('/root/VPN/filter/xray.next.json','w').write(json.dumps(engine.xray_config(rows)))
PY
XRAY_LOCATION_ASSET=/var/lib/linea-filter /opt/linea/bin/xray run -test -config /root/VPN/filter/xray.next.json
/root/VPN/bin/caddy validate --config /root/VPN/Caddyfile --adapter caddyfile >/dev/null 2>&1
systemctl daemon-reload
# First load the shutdown hook with the old Xray still running, retaining counters.
systemctl restart linea-portal
sleep 6
systemctl stop linea-portal
systemctl restart linea-xray
systemctl start linea-portal
systemctl restart naiveproxy
systemctl is-active linea-filter linea-xray linea-portal naiveproxy
echo 'Filtering and client routing activated; existing access keys preserved'
