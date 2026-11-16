set -euo pipefail
umask 077
install -m 644 /root/VPN/youtube/youtube.py /opt/linea/server/youtube.py
cd /opt/linea
LINEA_CONFIG=/etc/linea/config.json /opt/linea/venv/bin/python - <<'PY'
import importlib.util,json
from pathlib import Path
from server import store
store.CONFIG['youtube_upstream']='/root/VPN/youtube/private.json'
spec=importlib.util.spec_from_file_location('server.engine_candidate','/root/VPN/youtube/engine.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
rows=[r for r in store.clients() if store.status(r)=='active']
candidate=module.xray_config(rows)
Path('/root/VPN/youtube/xray.next.json').write_text(json.dumps(candidate,indent=2))
print('Generated candidate with server-only YouTube credentials')
PY
XRAY_LOCATION_ASSET=/var/lib/linea-filter /opt/linea/bin/xray run -test -config /root/VPN/youtube/xray.next.json > /root/VPN/youtube/validation.log 2>&1
python3 /root/VPN/youtube/verify-stage.py
