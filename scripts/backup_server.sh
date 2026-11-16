set -euo pipefail
umask 077
python3 - <<'PY'
import sqlite3
from pathlib import Path
from datetime import datetime,timezone
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target=Path('/root/VPN/backups')/('linea-db-'+stamp+'.sqlite3')
with sqlite3.connect('/var/lib/linea/portal.db') as source, sqlite3.connect(target) as destination:
    source.backup(destination)
    if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise SystemExit('Backup integrity check failed')
target.chmod(0o600)
print('Verified database backup: '+str(target))
PY
