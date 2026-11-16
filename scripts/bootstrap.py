"""Create private configuration. Never print credentials to the terminal."""
import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--production', action='store_true')
p.add_argument('--output', default='private/server.json')
p.add_argument('--credentials', default='private/admin-access.json')
a = p.parse_args()
target = Path(a.output)
if target.exists():
    raise SystemExit('Configuration already exists; left unchanged')
password = secrets.token_urlsafe(24)
salt = secrets.token_hex(16)
hashed = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=67108864).hex()
base = 'https://linesonline.pro' if a.production else 'http://127.0.0.1:5173'
config = {'secret':secrets.token_urlsafe(48),'admin_username':'admin','admin_password_hash':salt+':'+hashed,
          'base_url':base,'server_host':'linesonline.pro' if a.production else '217.60.19.243','development':not a.production}
if a.production:
    config.update(state='/var/lib/linea',xray='/opt/linea/bin/xray')
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
credentials=Path(a.credentials)
credentials.parent.mkdir(parents=True,exist_ok=True)
credentials.write_text(json.dumps({'url':base+'/admin','username':'admin','password':password},indent=2)+'\n',encoding='utf-8')
if os.name != 'nt':
    target.chmod(0o600)
    credentials.chmod(0o600)
print('Created configuration and private access file')
