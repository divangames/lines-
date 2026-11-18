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
from server import store,engine,routing

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
    sing_box_path='/sub/'+token+'/sing-box'
    naive_path=sing_box_path+'/naive'
    check(public['sing_box_url'].endswith(sing_box_path) and 'sing_box_naive_url' not in public,
          'Active access advertises the VLESS profile without a shared NaiveProxy password')
    sing_box=c.get(sing_box_path,headers={'Accept':'text/html'})
    profile=sing_box.json()
    vpn=profile['outbounds'][0]
    check(sing_box.status_code==200 and sing_box.headers['cache-control']=='no-store'
          and profile['route']['final']=='vpn' and vpn['uuid']==routing.xray_vless_outbound(row['uri'])['settings']['vnext'][0]['users'][0]['id']
          and profile['route']['rules'][3]['domain_suffix']==list(routing.SERVICE_DOMAINS)
          and profile['dns']['servers'][0]['detour']=='vpn',
          'Remote VLESS profile uses the personal key, direct service domains and tunneled default DNS')
    check(c.head(sing_box_path).status_code==200,'Remote profiles support HEAD preflight')
    naive_profile=routing.singbox_vless_profile(row['uri'])
    naive_profile['outbounds'][0]={'type':'naive','tag':'vpn','password':'fixture-password'}
    naive_file=store.STATE/'sing-box-naive.json'
    naive_file.write_text(json.dumps({'client_id':'different-client','profile':naive_profile}),encoding='utf-8')
    check(c.get(naive_path).status_code==404 and 'sing_box_naive_url' not in c.get('/api/access/'+token).json(),
          'Another subscription cannot retrieve an owner NaiveProxy profile')
    naive_file.write_text(json.dumps({'client_id':identifier,'profile':naive_profile}),encoding='utf-8')
    check(c.get(naive_path).json()==naive_profile and c.get('/api/access/'+token).json()['sing_box_naive_url'].endswith(naive_path),
          'Owner receives the separate private NaiveProxy profile')
    sub=c.get('/sub/'+token)
    check(sub.status_code==200 and base64.b64decode(sub.text).decode().startswith('vless://'),'Standard VLESS subscription')
    check('total=1073741824' in sub.headers['subscription-userinfo'],'Subscription quota headers')
    xray_path='/sub/'+token+'/happ-xray'
    check(c.get(xray_path).status_code==404,'Retired Xray pilot URL is unavailable')
    xray=c.get('/sub/'+token,headers={'User-Agent':'Happ/4.7.2 (iOS)'})
    check(xray.status_code==200 and xray.headers['content-type']=='application/json'
          and xray.headers['cache-control']=='no-store' and 'routing' not in xray.headers,
          'The existing Happ URL returns a full uncached JSON subscription')
    full_profile,=xray.json()
    check(full_profile['outbounds'][0]==routing.xray_vless_outbound(row['uri'])
          and full_profile['outbounds'][1]['tag']=='direct',
          'Full Xray uses each subscription credential and keeps the VPN as its first outbound')
    check(xray.headers['exclude-routes']==routing.VPN_ENDPOINT,'Happ sends the VPN endpoint outside its TUN adapter')
    check(c.head('/sub/'+token,headers={'User-Agent':'Happ/4.7.2'}).status_code==200,'Happ may preflight the subscription with HEAD')
    direct_sites=full_profile['dns']['servers'][0]['domains']
    check(direct_sites==routing.DIRECT_DOMAINS and 'domain:ozon.com' in direct_sites and 'domain:taximaxim.com' in direct_sites
          and not {'domain:ru','domain:xn--p1ai'} & set(direct_sites) and full_profile['dns']['servers'][0]['skipFallback'],
          'Happ keeps selected domains and separate DNS without a country-wide bypass')
    v2=c.get('/sub/'+token,headers={'User-Agent':'v2RayTun/2.0'})
    v2_rules=json.loads(base64.b64decode(v2.headers['routing']))
    check(v2_rules['rules'][0]['outboundTag']=='direct' and v2_rules['rules'][0]['domain']==direct_sites and v2_rules['rules'][1]['ip']==[routing.VPN_ENDPOINT,*routing.LOCAL_NETWORKS] and v2_rules['rules'][1]['outboundTag']=='direct','v2RayTun receives its native routing format')
    incy=c.get('/connect/'+token,headers={'User-Agent':'INCY/1.0/iOS','Accept':'text/html'})
    incy_rules=json.loads(base64.b64decode(incy.headers['routing'].removeprefix('incy://routing/onadd/')))
    check(incy.content==sub.content and incy_rules['DirectSites']==direct_sites and incy_rules['GlobalProxy']=='true','INCY receives the existing subscription and its own routing header')
    check(all(len(response.headers['routing'])<8192 for response in (v2,incy)), 'Routing payloads fit within an 8 KiB header field')
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
    for agent in ('v2raytun/2.0','v2rayNG/1.10','v2rayN/7.0','Dart/3.8 (dart:io)'):
        imported=c.get(shared,headers={'User-Agent':agent,'Accept':'*/*'})
        check(imported.status_code==200 and imported.content==sub.content,'Shared invitation imports in '+agent.split('/')[0])
    check(c.get(shared,headers={'User-Agent':'Happ/4.0','Accept':'text/html'}).content==xray.content,'Happ invitation still imports its full profile')
    page=c.get(shared,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html','Sec-Fetch-Dest':'document'})
    check(page.status_code==200 and page.headers['content-type'].startswith('text/html'),'Browser invitation remains a setup page')
    check('User-Agent' in page.headers['vary'] and page.headers['cache-control']=='no-store','Negotiated invitation is never cached across clients')
    browser_headers={'User-Agent':'Mozilla/5.0','Accept':'text/html','Sec-Fetch-Dest':'document'}
    check(c.get('/sub/'+token,headers=browser_headers,follow_redirects=False).headers['location']==shared,'Subscription opens its guide in browsers')
    check(c.get('/sub/'+token,headers=browser_headers,follow_redirects=True).headers['content-type'].startswith('text/html'),'Browser subscription has no redirect loop')
    check(c.get('/api/access/'+token+'/qr.svg').headers['content-type'].startswith('image/svg+xml'),'Local SVG QR')
    c.put('/api/admin/clients/'+identifier,json={**body,'enabled':False})
    check(c.get('/sub/'+token).status_code==403,'Paused subscription denied')
    check(c.get(sing_box_path).status_code==403 and c.get(naive_path).status_code==403,
          'Both remote profile downloads require active access')
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
