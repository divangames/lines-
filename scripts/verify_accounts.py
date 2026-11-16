"""Exercise recipient authentication on an isolated legacy database, never production."""
import hashlib
import json
import os
import secrets
import sys
import sqlite3
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
temporary=tempfile.TemporaryDirectory(prefix='linea-account-check-')
directory=Path(temporary.name)
password=secrets.token_urlsafe(24)
salt=secrets.token_hex(16)
config=directory/'config.json'
config.write_text(json.dumps({'base_url':'http://127.0.0.1:8088','server_host':'217.60.19.243','secret':secrets.token_urlsafe(48),'development':True,'state':str(directory/'state'),'admin_password_hash':salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=67108864).hex()}))
os.environ['LINEA_CONFIG']=str(config)
os.environ['LINEA_DIST']=str(ROOT/'dist')
# Seed the old schema and real-shaped access data before the additive migration.
state=directory/'state'
state.mkdir()
legacy_token=secrets.token_urlsafe(32)
with sqlite3.connect(state/'portal.db') as connection:
    connection.row_factory=sqlite3.Row
    connection.execute("CREATE TABLE clients (id TEXT PRIMARY KEY,name TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',token TEXT UNIQUE NOT NULL,tunnel_key TEXT UNIQUE NOT NULL,uuid TEXT UNIQUE NOT NULL,email TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,quota_bytes INTEGER NOT NULL DEFAULT 0,expires_at INTEGER,uploaded INTEGER NOT NULL DEFAULT 0,downloaded INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,last_seen_at INTEGER,last_page_at INTEGER,last_sync_at INTEGER,page_views INTEGER NOT NULL DEFAULT 0,subscription_fetches INTEGER NOT NULL DEFAULT 0,deleted INTEGER NOT NULL DEFAULT 0)")
    connection.execute('INSERT INTO clients(id,name,note,token,tunnel_key,uuid,email,quota_bytes,uploaded,downloaded,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',('legacy','Existing access','private note',legacy_token,secrets.token_urlsafe(32),'11111111-2222-4333-8444-555555555555','legacy@linea',1073741824,123,456,int(time.time())))
    legacy_row=dict(connection.execute("SELECT * FROM clients WHERE id='legacy'").fetchone())
connection.close()
from fastapi.testclient import TestClient
from server import store,engine,accounts
from server.app import app
engine.sync=lambda *args,**kwargs:None
engine.collect=lambda:[]
checks=[]
def check(condition,name):
    if not condition:raise AssertionError(name)
    checks.append(name)

with TestClient(app,base_url='http://127.0.0.1:8088') as owner, TestClient(app,base_url='http://127.0.0.1:8088') as user:
    migrated=store.get_client('legacy')
    check(all(migrated[key]==value for key,value in legacy_row.items()),'Migration preserves every existing access field')
    check(migrated['account_username'] is None,'Legacy accounts are not silently assigned unknown passwords')
    store.initialize()
    check(store.get_client('legacy')['token']==legacy_token,'Migration is idempotent')
    check(user.get('/api/account/me').status_code==401,'Anonymous cabinet denied')
    check(user.get('/api/account/qr.svg').status_code==401,'Anonymous personal QR denied')
    check(user.post('/api/account/login',json={'username':'admin','password':password}).status_code==403,'User login requires trusted Origin')
    owner.headers['Origin']=user.headers['Origin']='http://127.0.0.1:8088'
    check(user.post('/api/account/login',json={'username':'admin','password':password}).status_code==401,'Owner password cannot authenticate recipient')
    login=owner.post('/api/auth/login',json={'username':'admin','password':password})
    owner.headers['X-CSRF-Token']=login.json()['csrf']
    body={'name':'Recipient','note':'owner-only note','quota_gb':1,'expires_at':int(time.time()+86400),'enabled':True}
    result=owner.post('/api/admin/clients',json=body)
    check(result.status_code==200,'Creating access automatically issues login credentials')
    access=result.json();credentials=access['account_credentials'];identifier=access['id'];token=access['token']
    row=store.get_client(identifier)
    check(len(credentials['password'])>=12 and credentials['username']==row['account_username'],'Generated credentials satisfy policy')
    check(row['account_password_hash']!=credentials['password'] and store.password_matches(credentials['password'],row['account_password_hash']),'Only salted scrypt password hash is stored')
    listed=owner.get('/api/admin/clients').json()
    check(all('account_credentials' not in item and 'account_password_hash' not in item for item in listed),'Regular admin responses never reveal hashes or passwords')
    public=user.get('/api/access/'+token).json()
    check(not any(key in public for key in ['account_username','account_password_hash','account_credentials','note']),'Bearer access excludes credential and owner-only fields')
    check(user.post('/api/admin/clients/'+identifier+'/account',json={}).status_code==401,'Recipient cannot issue credentials')
    owner_csrf=owner.headers.pop('X-CSRF-Token')
    check(owner.post('/api/admin/clients/'+identifier+'/account',json={}).status_code==403,'Credential reset requires owner CSRF')
    owner.headers['X-CSRF-Token']=owner_csrf
    before_count=len(store.clients())
    duplicate=owner.post('/api/admin/clients',json={**body,'account_username':credentials['username'].upper()})
    check(duplicate.status_code==409 and len(store.clients())==before_count,'Case-normalized duplicate login rolls back creation')
    check(owner.post('/api/admin/clients',json={**body,'account_username':'a<bad>','account_password':'strong-test-password'}).status_code==422,'Invalid username rejected')
    check(owner.post('/api/admin/clients',json={**body,'account_password':'short'}).status_code==422,'Weak short password rejected')
    custom_password=secrets.token_urlsafe(18)
    second=owner.post('/api/admin/clients',json={**body,'name':'Second recipient','account_username':'second.user','account_password':custom_password}).json()
    check(second['account_credentials']['password']==custom_password,'Owner can set custom login and password')
    duplicate_update=owner.put('/api/admin/clients/'+second['id'],json={**body,'name':'Should not persist','account_username':credentials['username']})
    check(duplicate_update.status_code==409 and store.get_client(second['id'])['name']=='Second recipient','Duplicate username rolls back all edited conditions')
    rejected=user.post('/api/account/login',json={'username':credentials['username'],'password':'incorrect'})
    unknown=user.post('/api/account/login',json={'username':'unknown.user','password':'incorrect'})
    check(rejected.status_code==unknown.status_code==401 and rejected.json()==unknown.json(),'Unknown users and wrong passwords have identical errors')
    logged=user.post('/api/account/login',json={'username':credentials['username'].upper(),'password':credentials['password'],'remember':True})
    check(logged.status_code==200,'Recipient logs in case-insensitively')
    cookie=logged.headers['set-cookie'].lower()
    check('httponly' in cookie and 'samesite=strict' in cookie and 'max-age=2592000' in cookie and 'path=/' in cookie,'Remembered cookie is HttpOnly, Strict and persistent for 30 days')
    with store.db() as connection:
        session=connection.execute('SELECT hash,client_id FROM client_sessions').fetchone()
    check(session['hash']!=user.cookies.get(accounts.COOKIE) and session['client_id']==identifier,'Session bearer is stored only as a hash')
    me=user.get('/api/account/me')
    check(me.status_code==200 and me.json()['id']==identifier and me.json()['subscription_url'].endswith(token),'Session exposes only its own current access')
    check('no-store' in me.headers['cache-control'] and 'account_password_hash' not in me.json(),'Session data is uncacheable and excludes password hash')
    check(user.get('/api/admin/clients').status_code==401,'Recipient session cannot act as owner')
    check(owner.get('/api/account/me').status_code==401,'Owner cookie is not a recipient cookie')
    check(user.get('/api/account/qr.svg').headers['content-type'].startswith('image/svg+xml'),'Authenticated QR endpoint works')
    check(user.get('/account').headers.get('cache-control')=='no-store','Account HTML cannot be cached')
    user_csrf=me.json()['csrf']
    check(user.post('/api/account/logout').status_code==403,'Logout requires recipient CSRF')
    user.headers['X-CSRF-Token']=user_csrf
    user.headers['Origin']='https://untrusted.example'
    check(user.post('/api/account/logout').status_code==403,'Logout rejects foreign Origin')
    user.headers['Origin']='http://127.0.0.1:8088'
    old_cookie=user.cookies.get(accounts.COOKIE)
    check(user.post('/api/account/logout').status_code==200 and user.get('/api/account/me').status_code==401,'Logout deletes the session')
    user.cookies.set(accounts.COOKIE,old_cookie)
    check(user.get('/api/account/me').status_code==401,'Logged-out cookie cannot be replayed')
    user.cookies.clear()
    nonpersistent=user.post('/api/account/login',json={'username':credentials['username'],'password':credentials['password'],'remember':False})
    check(nonpersistent.status_code==200 and 'max-age=' not in nonpersistent.headers['set-cookie'].lower(),'Unchecked remember uses a browser-session cookie')
    with store.db() as connection:
        expiry=connection.execute('SELECT expires_at FROM client_sessions WHERE hash=?',(hashlib.sha256(user.cookies.get(accounts.COOKIE).encode()).hexdigest(),)).fetchone()[0]
    check(43190<=expiry-store.now()<=43200,'Browser session has a 12-hour server limit')
    for condition,expected_status in [({'enabled':False},'disabled'),({'expires_at':int(time.time()-1)},'expired')]:
        owner.put('/api/admin/clients/'+identifier,json={**body,**condition})
        check(user.get('/api/account/me').status_code==200 and user.get('/api/account/me').json()['status']==expected_status,'Stopped tariff can still log in and inspect '+expected_status)
    owner.put('/api/admin/clients/'+identifier,json=body)
    with store.db() as connection:connection.execute('UPDATE clients SET uploaded=1073741824 WHERE id=?',(identifier,))
    check(user.get('/api/account/me').json()['status']=='limited','Exhausted account can still inspect renewal information')
    with store.db() as connection:connection.execute('UPDATE clients SET uploaded=0 WHERE id=?',(identifier,))
    rotated=owner.post('/api/admin/clients/'+identifier+'/rotate').json()
    check(user.get('/api/account/me').status_code==200 and user.get('/api/account/me').json()['subscription_url'].endswith(rotated['token']),'VPN link rotation preserves login and updates subscription')
    token=rotated['token']
    reset=owner.post('/api/admin/clients/'+identifier+'/account',json={}).json()['account_credentials']
    check(reset['password']!=credentials['password'] and reset['username']==credentials['username'],'Password reset keeps username and issues a fresh password')
    check(user.get('/api/account/me').status_code==401,'Password reset invalidates recipient sessions')
    check(store.get_client(identifier)['token']==token,'Password reset does not rotate the VPN subscription')
    check(user.post('/api/account/login',json={'username':credentials['username'],'password':credentials['password']}).status_code==401,'Old password is rejected')
    check(user.post('/api/account/login',json={'username':reset['username'],'password':reset['password']}).status_code==200,'New password logs in')
    before_hash=store.get_client(identifier)['account_password_hash']
    edited=owner.put('/api/admin/clients/'+identifier,json={**body,'account_username':reset['username'],'account_password':''}).json()
    check('account_credentials' not in edited and store.get_client(identifier)['account_password_hash']==before_hash and user.get('/api/account/me').status_code==200,'Editing tariff with empty password preserves credentials and sessions')
    owner.put('/api/admin/clients/'+identifier,json={**body,'account_username':'renamed.user'})
    check(user.get('/api/account/me').status_code==401,'Username change invalidates sessions')
    check(user.post('/api/account/login',json={'username':reset['username'],'password':reset['password']}).status_code==401,'Old username rejected after rename')
    check(user.post('/api/account/login',json={'username':'renamed.user','password':reset['password']}).status_code==200,'Renamed login retains existing password')
    with store.db() as connection:connection.execute('UPDATE client_sessions SET expires_at=? WHERE client_id=?',(store.now()-1,identifier))
    check(user.get('/api/account/me').status_code==401,'Expired session cannot read account')
    user.post('/api/account/login',json={'username':'renamed.user','password':reset['password']})
    owner.delete('/api/admin/clients/'+identifier)
    check(user.get('/api/account/me').status_code==401 and user.post('/api/account/login',json={'username':'renamed.user','password':reset['password']}).status_code==401,'Archiving revokes login and all sessions')
    legacy_creds=owner.post('/api/admin/clients/legacy/account',json={}).json()['account_credentials']
    after=store.get_client('legacy')
    check(all(after[key]==value for key,value in legacy_row.items()),'Enabling login on existing access preserves VPN credentials and accounting')
    check(user.post('/api/account/login',json={'username':legacy_creds['username'],'password':legacy_creds['password']}).status_code==200,'Existing recipient can use newly issued login')
    # A rename occurring during password hashing must not authorize the old username.
    original_matches=store.password_matches
    def concurrent_rename(value,expected):
        valid=original_matches(value,expected)
        with store.db() as connection:
            connection.execute("UPDATE clients SET account_username='legacy.renamed' WHERE id='legacy'")
            connection.execute("DELETE FROM client_sessions WHERE client_id='legacy'")
        return valid
    store.password_matches=concurrent_rename
    check(user.post('/api/account/login',json={'username':legacy_creds['username'],'password':legacy_creds['password']}).status_code==401,'Concurrent rename cannot authorize the old username')
    store.password_matches=original_matches
    accounts.ATTEMPTS.clear()
    statuses=[user.post('/api/account/login',json={'username':'unknown.user','password':'incorrect'}).status_code for _ in range(11)]
    check(statuses[:10]==[401]*10 and statuses[10]==429,'Concurrent-safe login attempt budget is enforced')
    accounts.ATTEMPTS.clear()
    guesses=[user.post('/api/account/login',json={'username':'second.user','password':'incorrect'}).status_code for _ in range(9)]
    own_login=user.post('/api/account/login',json={'username':'legacy.renamed','password':legacy_creds['password']})
    last_guess=user.post('/api/account/login',json={'username':'second.user','password':'incorrect'})
    blocked=user.post('/api/account/login',json={'username':'legacy.renamed','password':legacy_creds['password']})
    check(guesses==[401]*9 and own_login.status_code==200 and last_guess.status_code==401 and blocked.status_code==429,'Own successful login cannot reset failed guesses against another recipient')
    accounts.ATTEMPTS.clear()
    store.DEVELOPMENT=False
    secure=user.post('/api/account/login',json={'username':'legacy.renamed','password':legacy_creds['password']})
    check(secure.status_code==200 and '; secure' in secure.headers['set-cookie'].lower(),'Production cookies require HTTPS')
    store.DEVELOPMENT=True
    check(owner.get('/api/auth/me').status_code==200,'Recipient actions preserve owner authentication')

print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=True,indent=2))
temporary.cleanup()
