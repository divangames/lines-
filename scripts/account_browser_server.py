"""Isolated real API for browser checks. Requires an explicit test-only directory."""
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
directory=Path(sys.argv[1]).resolve()
assert directory.is_relative_to((ROOT/'private').resolve()) and directory.name.startswith('auth-browser-')
directory.mkdir(parents=True,exist_ok=True)
config=directory/'config.json'
if not config.exists():
    salt=secrets.token_hex(16)
    config.write_text(json.dumps({'base_url':'http://127.0.0.1:5196','server_host':'217.60.19.243','secret':secrets.token_urlsafe(48),'development':True,'state':str(directory/'state'),'admin_password_hash':salt+':'+hashlib.scrypt(b'Local-Owner-Password-Only',salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=67108864).hex()}))
os.environ['LINEA_CONFIG']=str(config)
os.environ['LINEA_DIST']=str(ROOT/'dist')
from server import store,engine
engine.sync=lambda *args,**kwargs:None
engine.collect=lambda:[]
store.initialize()
with store.db() as connection:
    connection.execute('INSERT OR IGNORE INTO clients(id,name,note,token,tunnel_key,uuid,email,created_at) VALUES (?,?,?,?,?,?,?,?)',('legacy-browser','Существующий доступ','Только тестовые данные',secrets.token_urlsafe(32),secrets.token_urlsafe(32),str(uuid.uuid4()),'legacy-browser@linea',int(time.time())))
from server.app import app
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=5196,access_log=False,log_level='error')
