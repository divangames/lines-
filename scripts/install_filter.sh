#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/opt/linea-filter
state=/var/lib/linea-filter
install -d -m 700 /root/VPN/backups /root/VPN/filter
stamp=$(date -u +%Y%m%dT%H%M%SZ)
tar -czf "/root/VPN/backups/before-filter-$stamp.tar.gz" -C / opt/linea/server etc/systemd/system/naiveproxy.service var/lib/linea/xray.json root/VPN/Caddyfile
id linea-filter >/dev/null 2>&1 || useradd --system --home-dir "$state" --shell /usr/sbin/nologin linea-filter
install -d -m 755 "$base" "$state"
install -d -m 700 -o linea-filter -g linea-filter /etc/linea-filter "$state/work"
curl --fail --location --silent --show-error --retry 3 --max-time 180 \
  https://github.com/AdguardTeam/AdGuardHome/releases/download/v0.107.80/AdGuardHome_linux_amd64.tar.gz \
  -o /root/VPN/filter/AdGuardHome_linux_amd64.tar.gz
echo '28593bc761d71469abdbc6f39ca42cbed763ec92b63082c729177b037ed51d18  /root/VPN/filter/AdGuardHome_linux_amd64.tar.gz' | sha256sum --check --status
tar -xzf /root/VPN/filter/AdGuardHome_linux_amd64.tar.gz -C "$base" --strip-components=2 ./AdGuardHome/AdGuardHome
chmod 755 "$base/AdGuardHome"
install -m 600 -o linea-filter -g linea-filter /root/VPN/filter/AdGuardHome.yaml /etc/linea-filter/AdGuardHome.yaml
printf 'nameserver 127.0.0.1\noptions timeout:2 attempts:2\n' > /etc/linea-filter/resolv.conf
chmod 644 /etc/linea-filter/resolv.conf
# Services need to traverse the directory to bind/read the resolver file.
chmod 755 /etc/linea-filter
install -m 755 /root/VPN/filter/update_filter.py "$base/update_filter.py"
"$base/AdGuardHome" --check-config -c /etc/linea-filter/AdGuardHome.yaml -w "$state/work"
cat > /etc/systemd/system/linea-filter.service <<'UNIT'
[Unit]
Description=Linea private ad and tracker DNS filter
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=linea-filter
Group=linea-filter
ExecStart=/opt/linea-filter/AdGuardHome --no-check-update -c /etc/linea-filter/AdGuardHome.yaml -w /var/lib/linea-filter/work
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ReadWritePaths=/var/lib/linea-filter/work /etc/linea-filter
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
RestrictSUIDSGID=true
LockPersonality=true
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/linea-filter-update.service <<'UNIT'
[Unit]
Description=Update Linea ad and tracker domain rules
After=network-online.target linea-xray.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/linea-filter/update_filter.py
TimeoutStartSec=180
UMask=0022
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/linea-filter
UNIT
cat > /etc/systemd/system/linea-filter-update.timer <<'UNIT'
[Unit]
Description=Daily Linea domain filter update
[Timer]
OnCalendar=*-*-* 03:30:00 UTC
RandomizedDelaySec=30m
Persistent=true
[Install]
WantedBy=timers.target
UNIT
python3 /opt/linea-filter/update_filter.py
systemctl daemon-reload
systemctl enable --now linea-filter linea-filter-update.timer
for attempt in $(seq 1 30); do
  if dig @127.0.0.1 example.com +time=2 +tries=1 +short | grep -qE '[0-9]'; then break; fi
  sleep 1
done
dig @127.0.0.1 example.com +time=3 +tries=1 +short
dig @127.0.0.1 doubleclick.net +time=3 +tries=1 +noall +comments
echo 'Private filter installed. VPN services have not been restarted yet.'
