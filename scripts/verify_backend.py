"""Exercise access control and lifecycle against an isolated temporary database."""
import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temporary = tempfile.TemporaryDirectory(prefix='linea-check-')
directory = Path(temporary.name)
password = secrets.token_urlsafe(24)
salt = secrets.token_hex(16)
config = directory/'config.json'
config.write_text(json.dumps({'base_url':'http://127.0.0.1:8088','server_host':'217.60.19.243',
 'secret':secrets.token_urlsafe(48),'development':True,'state':str(directory/'state'),
 'admin_password_hash':salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=67108864).hex()}))
os.environ['LINEA_CONFIG']=str(config)
frontend=directory/'frontend'
frontend.mkdir()
(frontend/'index.html').write_text('<!doctype html><html lang="ru"><body>Connection guide</body></html>',encoding='utf-8')
os.environ['LINEA_DIST']=str(frontend)
from fastapi.testclient import TestClient
from server.app import app
from server import store,engine

checks=[]
def check(condition,name):
    if not condition: raise AssertionError(name)
    checks.append(name)

with TestClient(app,base_url='http://127.0.0.1:8088') as c:
    check(c.get('/api/admin/clients').status_code==401,'Unauthenticated admin denied')
    check(c.post('/api/auth/login',json={'username':'admin','password':password}).status_code==403,'Login origin required')
    c.headers['Origin']='http://127.0.0.1:8088'
    check(c.post('/api/auth/login',json={'username':'admin','password':'wrong'}).status_code==401,'Wrong password denied')
    login=c.post('/api/auth/login',json={'username':'admin','password':password})
    check(login.status_code==200,'Admin login succeeds')
    body={'name':'Проверка <script>','note':'Личная заметка','quota_gb':1,'expires_at':int(time.time()+3600),'enabled':True}
    check(c.post('/api/admin/clients',json=body).status_code==403,'Mutation CSRF required')
    c.headers['X-CSRF-Token']=login.json()['csrf']
    created=c.post('/api/admin/clients',json=body)
    check(created.status_code==200,'Create personal access')
    row=created.json();identifier=row['id'];token=row['token']
    public=c.get('/api/access/'+token).json()
    check('note' not in public and 'token' not in public,'Public data excludes private note')
    sub=c.get('/sub/'+token)
    check(sub.status_code==200 and base64.b64decode(sub.text).decode().startswith('vless://'),'Standard VLESS subscription')
    check('total=1073741824' in sub.headers['subscription-userinfo'],'Subscription quota headers')
    happ=c.get('/sub/'+token,headers={'User-Agent':'Happ/4.7.2'})
    check(happ.headers['exclude-routes']=='217.60.19.243/32','Happ sends the VPN endpoint outside its TUN adapter')
    happ_rules=json.loads(base64.b64decode(happ.headers['routing'].removeprefix('happ://routing/onadd/')))
    check(happ_rules['DirectSites']==['domain:ru','domain:xn--p1ai','full:linesonline.pro','full:www.linesonline.pro'] and '217.60.19.243/32' in happ_rules['DirectIp'] and happ_rules['GlobalProxy']=='true','Happ imports Russian suffix bypass while other traffic stays proxied')
    v2=c.get('/sub/'+token,headers={'User-Agent':'v2RayTun/2.0'})
    v2_rules=json.loads(base64.b64decode(v2.headers['routing']))
    check(v2_rules['rules'][0]['outboundTag']=='direct' and v2_rules['rules'][0]['domain']==happ_rules['DirectSites'] and v2_rules['rules'][1]['ip']==['217.60.19.243/32'] and v2_rules['rules'][1]['outboundTag']=='direct','v2RayTun receives its native routing format')
    check('routing' not in sub.headers,'Unrelated clients do not receive an incompatible routing payload')
    upstream=directory/'upstream.json'
    upstream.write_text(json.dumps({'outbound':{'protocol':'vless','tag':'youtube-vpn','settings':{
        'vnext':[{'address':'192.0.2.123','port':443,'users':[{'id':'11111111-2222-4333-8444-555555555555','encryption':'none'}]}]}}}))
    store.CONFIG['youtube_upstream']=str(upstream)
    server_config=engine.xray_config(store.clients())
    check(server_config['outbounds'][0]['tag']=='direct' and server_config['routing']['rules'][-1]['outboundTag']=='youtube-vpn','YouTube upstream preserves the original default egress')
    private_subscription=base64.b64decode(c.get('/sub/'+token).text).decode()
    check('11111111-2222-4333-8444-555555555555' not in private_subscription and '192.0.2.123' not in private_subscription and private_subscription==base64.b64decode(sub.text).decode(),'Third-party VPN credentials stay off client subscriptions')
    upstream.write_text(json.dumps({'egress':'vps-ipv4'}))
    direct_config=engine.xray_config(store.clients())
    direct_video=next(o for o in direct_config['outbounds'] if o['tag']=='youtube-direct')
    check(direct_video['protocol']=='freedom' and direct_video['settings']['targetStrategy']=='ForceIPv4' and direct_config['routing']['rules'][-1]['outboundTag']==direct_video['tag'],'YouTube direct mode uses VPS IPv4 for video domains')
    store.CONFIG.pop('youtube_upstream')
    shared='/connect/'+token
    for agent in ('Happ/4.0','v2raytun/2.0','v2rayNG/1.10','v2rayN/7.0','Dart/3.8 (dart:io)'):
        imported=c.get(shared,headers={'User-Agent':agent,'Accept':'*/*'})
        check(imported.status_code==200 and imported.content==sub.content,'Shared invitation imports in '+agent.split('/')[0])
    check(c.get(shared,headers={'User-Agent':'Happ/4.0','Accept':'text/html'}).content==sub.content,'VPN client HTML Accept still imports')
    page=c.get(shared,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html','Sec-Fetch-Dest':'document'})
    check(page.status_code==200 and page.headers['content-type'].startswith('text/html'),'Browser invitation remains a setup page')
    check('User-Agent' in page.headers['vary'] and page.headers['cache-control']=='no-store','Negotiated invitation is never cached across clients')
    browser_headers={'User-Agent':'Mozilla/5.0','Accept':'text/html','Sec-Fetch-Dest':'document'}
    check(c.get('/sub/'+token,headers=browser_headers,follow_redirects=False).headers['location']==shared,'Subscription opens its guide in browsers')
    check(c.get('/sub/'+token,headers=browser_headers,follow_redirects=True).headers['content-type'].startswith('text/html'),'Browser subscription has no redirect loop')
    check(c.get('/api/access/'+token+'/qr.svg').headers['content-type'].startswith('image/svg+xml'),'Local SVG QR')
    c.put('/api/admin/clients/'+identifier,json={**body,'enabled':False})
    check(c.get('/sub/'+token).status_code==403,'Paused subscription denied')
    check(c.get(shared,headers={'User-Agent':'Happ/4.0','Accept':'*/*'}).status_code==403,'Shared invitation respects disabled access')
    c.put('/api/admin/clients/'+identifier,json={**body,'expires_at':int(time.time()-1)})
    check(c.get('/api/access/'+token).json()['status']=='expired','Expiry enforced')
    c.put('/api/admin/clients/'+identifier,json=body)
    with store.db() as conn:
        conn.execute('UPDATE clients SET downloaded=1073741824 WHERE id=?',(identifier,))
        conn.execute('INSERT INTO daily VALUES (?,?,?,?)',('2026-11-16',identifier,0,1073741824))
    check(c.get('/api/access/'+token).json()['status']=='limited' and c.get('/sub/'+token).status_code==403,'Quota enforced')
    c.post('/api/admin/clients/'+identifier+'/reset-traffic')
    check(c.get('/api/admin/overview').json()['used_bytes']==1073741824,'Reset preserves historical total')
    rotated=c.post('/api/admin/clients/'+identifier+'/rotate').json()
    check(rotated['token']!=token and rotated['uri']!=row['uri'] and c.get('/api/access/'+token).status_code==404,'Rotation revokes old credentials')
    check(c.post('/api/admin/clients',json={**body,'name':'   '}).status_code==422,'Whitespace names denied')
    check(c.put('/api/admin/settings',json={'name':'Линия','tagline':'VPN','support_url':'javascript:alert(1)'}).status_code==422,'Unsafe support URL denied')
    c.headers['Origin']='https://untrusted.example'
    check(c.delete('/api/admin/clients/'+identifier).status_code==403,'Foreign origin denied')
    c.headers['Origin']='http://127.0.0.1:8088'
    c.delete('/api/admin/clients/'+identifier)
    check(c.get('/api/access/'+rotated['token']).status_code==404 and c.get('/api/admin/clients').json()==[],'Archive revokes and removes access')
    changed=c.post('/api/admin/password',json={'current_password':password,'new_password':secrets.token_urlsafe(24)})
    check(changed.status_code==200 and c.get('/api/auth/me').status_code==401,'Password change invalidates sessions')
print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=True,indent=2))
temporary.cleanup()
