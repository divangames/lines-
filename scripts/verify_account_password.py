"""Test self-service password changes using an isolated account database."""
import hashlib
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
temporary=tempfile.TemporaryDirectory(prefix='linea-password-check-')
directory=Path(temporary.name)
owner_password=secrets.token_urlsafe(24)
salt=secrets.token_hex(16)
config=directory/'config.json'
config.write_text(json.dumps({'base_url':'http://127.0.0.1:8088','server_host':'217.60.19.243','secret':secrets.token_urlsafe(48),'development':True,'state':str(directory/'state'),'admin_password_hash':salt+':'+hashlib.scrypt(owner_password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=67108864).hex()}))
os.environ['LINEA_CONFIG']=str(config)
os.environ['LINEA_DIST']=str(ROOT/'dist')
from fastapi.testclient import TestClient
from server import store,engine,accounts
from server.app import app
engine.sync=lambda *args,**kwargs:None
engine.collect=lambda:[]
checks=[]
def check(value,name):
    if not value:raise AssertionError(name)
    checks.append(name)
def signin(client,credentials,remember=True):
    response=client.post('/api/account/login',json={'username':credentials['username'],'password':credentials['password'],'remember':remember})
    check(response.status_code==200,'Password-test recipient login succeeds')
    client.headers['X-CSRF-Token']=response.json()['csrf']
    return response

with TestClient(app,base_url='http://127.0.0.1:8088') as owner, TestClient(app,base_url='http://127.0.0.1:8088') as user, TestClient(app,base_url='http://127.0.0.1:8088') as other_device, TestClient(app,base_url='http://127.0.0.1:8088') as other_user:
    for client in [owner,user,other_device,other_user]:client.headers['Origin']='http://127.0.0.1:8088'
    logged=owner.post('/api/auth/login',json={'username':'admin','password':owner_password})
    owner.headers['X-CSRF-Token']=logged.json()['csrf']
    access=owner.post('/api/admin/clients',json={'name':'Password test','quota_gb':5,'expires_at':int(time.time()+86400)}).json()
    account=access['account_credentials'];identifier=access['id']
    unrelated=owner.post('/api/admin/clients',json={'name':'Other user'}).json()
    signin(user,account);signin(other_device,account);signin(other_user,unrelated['account_credentials'])
    original_row=store.get_client(identifier)
    current_cookie=user.cookies.get(accounts.COOKIE)
    original_csrf=user.headers['X-CSRF-Token']
    with store.db() as connection:
        original_session=dict(connection.execute('SELECT * FROM client_sessions WHERE hash=?',(hashlib.sha256(current_cookie.encode()).hexdigest(),)).fetchone())
    next_password=secrets.token_urlsafe(24)
    body={'current_password':account['password'],'new_password':next_password,'confirm_password':next_password}
    anonymous=TestClient(app,base_url='http://127.0.0.1:8088')
    check(anonymous.post('/api/account/password',json=body).status_code==401,'Anonymous and bearer-only requests cannot change a password')
    check(owner.post('/api/account/password',json=body).status_code==401,'Owner cookie cannot change a recipient password')
    csrf=user.headers.pop('X-CSRF-Token')
    check(user.post('/api/account/password',json=body).status_code==403,'Self-service mutation requires CSRF')
    user.headers['X-CSRF-Token']=csrf;user.headers['Origin']='https://untrusted.example'
    check(user.post('/api/account/password',json=body).status_code==403,'Self-service mutation rejects foreign Origin')
    user.headers['Origin']='http://127.0.0.1:8088'
    check(user.post('/api/account/password',json={**body,'confirm_password':secrets.token_urlsafe(24)}).status_code==422,'Confirmation mismatch rejected by server')
    check(user.post('/api/account/password',json={**body,'new_password':'short','confirm_password':'short'}).status_code==422,'Password policy enforced by server')
    for field,value in [('new_password','EchoNew123'),('confirm_password','EchoRep123'),('current_password','CurrentSecretEcho-'*20)]:
        invalid=user.post('/api/account/password',json={**body,field:value})
        details=invalid.json()['detail']
        check(invalid.status_code==422 and value not in invalid.text and isinstance(details,list) and all('input' not in item and 'ctx' not in item for item in details),'Invalid '+field+' is never reflected in validation responses')
    check(user.post('/api/account/password',json={**body,'new_password':account['password'],'confirm_password':account['password']}).status_code==400,'Identical current and new password rejected')
    wrong=user.post('/api/account/password',json={**body,'current_password':'wrong-current-password'})
    check(wrong.status_code==400 and wrong.json()['detail']=='Текущий пароль неверен','Incorrect current password rejected')
    check(store.get_client(identifier)['account_password_hash']==original_row['account_password_hash'] and other_device.get('/api/account/me').status_code==200,'Rejected changes preserve credentials and all sessions')
    changed=user.post('/api/account/password',json=body)
    check(changed.status_code==200,'Recipient changes own password')
    check(user.get('/api/account/me').status_code==200 and changed.json()['id']==identifier,'Current browser remains signed in')
    check(user.cookies.get(accounts.COOKIE)!=current_cookie and changed.json()['csrf']!=original_csrf,'Current cookie and CSRF rotate')
    cookie_header=changed.headers['set-cookie'].lower()
    check('httponly' in cookie_header and 'samesite=strict' in cookie_header and 'max-age=' in cookie_header,'Remembered cookie policy is preserved')
    with store.db() as connection:
        replacement=dict(connection.execute('SELECT * FROM client_sessions WHERE client_id=?',(identifier,)).fetchone())
        count=connection.execute('SELECT COUNT(*) FROM client_sessions WHERE client_id=?',(identifier,)).fetchone()[0]
    check(count==1 and replacement['expires_at']==original_session['expires_at'] and replacement['remembered']==1,'Exactly one new session remains with original expiry and preference')
    check(other_device.get('/api/account/me').status_code==401,'Other device session is revoked')
    check(other_user.get('/api/account/me').status_code==200 and owner.get('/api/auth/me').status_code==200,'Other recipients and owner sessions are unaffected')
    changed_row=store.get_client(identifier)
    check(all(changed_row[key]==value for key,value in original_row.items() if key!='account_password_hash'),'Password change preserves all VPN credentials, quota and accounting')
    check(store.password_matches(next_password,changed_row['account_password_hash']) and not store.password_matches(account['password'],changed_row['account_password_hash']),'New hash accepts only the new password')
    check(not any(key in changed.json() for key in ['password','new_password','current_password','account_password_hash','account_credentials']) and next_password not in changed.text,'Response never returns cleartext or password hash')
    with store.db() as connection:
        event=connection.execute("SELECT kind,detail FROM events WHERE client_id=? ORDER BY id DESC LIMIT 1",(identifier,)).fetchone()
    check(event['kind']=='account_password_changed' and event['detail']=='','Event records action without secret values')
    replay=TestClient(app,base_url='http://127.0.0.1:8088');replay.cookies.set(accounts.COOKIE,current_cookie)
    check(replay.get('/api/account/me').status_code==401,'Old current-session cookie cannot be replayed')
    check(user.post('/api/account/logout').status_code==403,'Old CSRF cannot mutate the rotated session')
    user.headers['X-CSRF-Token']=changed.json()['csrf']
    check(user.post('/api/account/logout').status_code==200,'New CSRF can log out after password change')
    check(user.post('/api/account/login',json={'username':account['username'],'password':account['password']}).status_code==401,'Old password no longer logs in')
    account={**account,'password':next_password};signin(user,account,remember=False)
    final_password=secrets.token_urlsafe(24)
    changed=user.post('/api/account/password',json={'current_password':next_password,'new_password':final_password,'confirm_password':final_password})
    check(changed.status_code==200 and 'max-age=' not in changed.headers['set-cookie'].lower(),'Nonremembered login remains a browser-session cookie')
    user.headers['X-CSRF-Token']=changed.json()['csrf']
    account={**account,'password':final_password}
    owner.put('/api/admin/clients/'+identifier,json={'name':'Password test','enabled':False})
    paused_password=secrets.token_urlsafe(24)
    changed=user.post('/api/account/password',json={'current_password':final_password,'new_password':paused_password,'confirm_password':paused_password})
    check(changed.status_code==200 and changed.json()['status']=='disabled','Paused tariff does not block account password management')
    user.headers['X-CSRF-Token']=changed.json()['csrf'];account={**account,'password':paused_password}
    accounts.PASSWORD_ATTEMPTS.clear()
    failures=[user.post('/api/account/password',json={'current_password':'wrong-current-password','new_password':next_password,'confirm_password':next_password}).status_code for _ in range(6)]
    check(failures[:5]==[400]*5 and failures[5]==429,'Current-password guessing is limited to five attempts per 15 minutes')
    check(user.get('/api/account/me').status_code==200,'Password-attempt limit does not end the valid session')
    accounts.PASSWORD_ATTEMPTS.clear()
    # A concurrent owner reset must win over a request checked against an old hash.
    original_matches=store.password_matches
    owner_reset_password=secrets.token_urlsafe(24)
    def concurrent_reset(value,expected):
        valid=original_matches(value,expected)
        with store.db() as connection:
            connection.execute('UPDATE clients SET account_password_hash=? WHERE id=?',(store.password_hash(owner_reset_password),identifier))
            connection.execute('DELETE FROM client_sessions WHERE client_id=?',(identifier,))
        return valid
    store.password_matches=concurrent_reset
    raced=user.post('/api/account/password',json={'current_password':paused_password,'new_password':next_password,'confirm_password':next_password})
    store.password_matches=original_matches
    check(raced.status_code==401 and original_matches(owner_reset_password,store.get_client(identifier)['account_password_hash']),'Concurrent reset cannot be overwritten by a stale password change')
    # Migrate the previous three-column session table without dropping live sessions.
    with store.db() as connection:
        connection.execute('DROP TABLE client_sessions')
        connection.execute('CREATE TABLE client_sessions(hash TEXT PRIMARY KEY,client_id TEXT NOT NULL,expires_at INTEGER NOT NULL)')
        legacy_expiry=store.now()+10*86400
        connection.execute('INSERT INTO client_sessions VALUES (?,?,?)',('legacy-remembered','legacy',legacy_expiry))
        connection.execute('INSERT INTO client_sessions VALUES (?,?,?)',('legacy-short','legacy',store.now()+3600))
    store.initialize();store.initialize()
    with store.db() as connection:
        legacy=dict(connection.execute("SELECT * FROM client_sessions WHERE hash='legacy-remembered'").fetchone())
        short=dict(connection.execute("SELECT * FROM client_sessions WHERE hash='legacy-short'").fetchone())
    check(legacy['expires_at']==legacy_expiry and legacy['remembered']==1 and short['remembered']==0,'Session metadata migration is additive, idempotent and conservative')

print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=True,indent=2))
temporary.cleanup()
