"""Live profile lifecycle through SSH and a separate local SOCKS client. Secrets stay in private files."""
import base64
import json
import subprocess
import sys
import time
import socket
import struct
from pathlib import Path
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT/'.venv/Lib/site-packages'))
from websockets.sync.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed
sys.path.insert(0,str(ROOT.parent/'tools'))
from vps_ssh import connect

credentials=json.loads((ROOT.parent/'info/LINEA-admin.json').read_text())
remote=r'''
import json,sys,httpx
data=json.load(sys.stdin)
with httpx.Client(base_url='http://127.0.0.1:8088',headers={'Origin':'https://linesonline.pro'}) as c:
    r=c.post('/api/auth/login',json=data['credentials']);r.raise_for_status()
    c.headers['X-CSRF-Token']=r.json()['csrf']
    c.headers['Cookie']='__Host-linea='+r.cookies.get('__Host-linea')
    if data['method']=='GET': r=c.get(data['path'])
    else: r=c.request(data['method'],data['path'],json=data.get('body'))
    print(json.dumps({'status':r.status_code,'data':r.json()}))
'''
ssh=connect(18,'192.168.100.76')
def api(method,path,body=None):
    payload={'credentials':{k:credentials[k] for k in ('username','password')},'method':method,'path':path,'body':body}
    # A separate input descriptor carries JSON; the command contains no secrets.
    code='import json,sys; data=json.loads(sys.stdin.readline()); exec('+repr(remote.replace('data=json.load(sys.stdin)','data=data'))+')'
    import shlex
    stdin,stdout,stderr=ssh.exec_command('/opt/linea/venv/bin/python -c '+shlex.quote(code))
    stdin.write(json.dumps(payload)+'\n');stdin.flush();stdin.channel.shutdown_write()
    result=json.loads(stdout.read().decode())
    if result['status']>=400: raise RuntimeError('Admin operation failed: '+str(result['status']))
    return result['data']

core=ROOT.parent/'VPN/windows-client/sing-box-1.14.4-windows-amd64/sing-box.exe'
profile=None
process=None
report={}
try:
    owner=next((row for row in api('GET','/api/admin/clients') if row['name']=='Мой доступ'),None)
    if not owner:owner=api('POST','/api/admin/clients',{'name':'Мой доступ','note':'Основной доступ владельца','quota_gb':0,'enabled':True})
    (ROOT.parent/'info/LINEA-my-access.json').write_text(json.dumps(owner,ensure_ascii=False,indent=2),encoding='utf-8')
    profile=api('POST','/api/admin/clients',{'name':'Проверка соединения','note':'Автоматический тест; будет архивирован','quota_gb':1,'enabled':True})
    uri=urlparse(profile['uri']);query=parse_qs(uri.query)
    config={'log':{'level':'error'},'inbounds':[{'type':'socks','listen':'127.0.0.1','listen_port':20993}],
      'outbounds':[{'type':'vless','tag':'vpn','server':uri.hostname,'server_port':443,'uuid':uri.username,
       'bind_interface':'Ethernet','tls':{'enabled':True,'server_name':uri.hostname,'utls':{'enabled':True,'fingerprint':'chrome'}},
       'transport':{'type':'ws','path':query['path'][0],'headers':{'Host':uri.hostname}}}]}
    config_path=ROOT/'private/live-client.json';config_path.write_text(json.dumps(config),encoding='utf-8')
    log=open(ROOT/'private/live-client.log','w')
    process=subprocess.Popen([str(core),'run','-c',str(config_path)],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(2)
    def curl(url,timeout=20):
        return subprocess.run(['curl.exe','--silent','--show-error','--fail','--max-time',str(timeout),'--socks5-hostname','127.0.0.1:20993',url],capture_output=True,timeout=timeout+5)
    result=curl('https://api.ipify.org')
    if result.returncode or result.stdout.strip()!=b'217.60.19.243':raise RuntimeError('VLESS external IP check failed')
    report['vless_public_ip']='217.60.19.243'
    result=curl('https://speed.cloudflare.com/__down?bytes=1048576')
    if result.returncode or len(result.stdout)<1048576:raise RuntimeError('Traffic transfer failed')
    for _ in range(4):
        time.sleep(3)
        row=next(r for r in api('GET','/api/admin/clients') if r['id']==profile['id'])
        if row['used_bytes']>=1048576:break
    if row['used_bytes']<1048576:raise RuntimeError('Real usage was not recorded')
    report['accounted_bytes']=row['used_bytes']
    # Open a genuine VLESS stream to a public HTTP site, then revoke it while open.
    raw=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    raw.setsockopt(socket.IPPROTO_IP,31,struct.pack('!I',18))
    raw.bind(('192.168.100.76',0));raw.settimeout(15);raw.connect((uri.hostname,443))
    import uuid
    address=b'example.com'
    header=b'\0'+uuid.UUID(uri.username).bytes+b'\0\x01'+(80).to_bytes(2,'big')+b'\x02'+bytes([len(address)])+address
    with ws_connect('wss://'+uri.hostname+query['path'][0],sock=raw,proxy=None,max_size=1048576,open_timeout=15) as stream:
        stream.send(header+b'GET / HTTP/1.1\r\nHost: example.com\r\nConnection: keep-alive\r\n\r\n')
        first=stream.recv(timeout=15)
        if not isinstance(first,bytes) or len(first)<3:raise RuntimeError('VLESS stream did not open')
        active=next(r for r in api('GET','/api/admin/clients') if r['id']==profile['id'])
        if not active['online']:raise RuntimeError('Open stream was not reported online')
        report['online_presence_verified']=True
        api('PUT','/api/admin/clients/'+profile['id'],{'name':profile['name'],'quota_gb':1,'enabled':False})
        try:
            for _ in range(20):stream.recv(timeout=10)
            raise RuntimeError('Open stream remained alive after revocation')
        except ConnectionClosed:
            report['open_stream_revoked']=True
    result=curl('https://api.ipify.org',8)
    if result.returncode==0:raise RuntimeError('Disabled profile still works')
    report['disabled_profile_denied']=True
    api('PUT','/api/admin/clients/'+profile['id'],{'name':profile['name'],'quota_gb':1,'enabled':True})
    result=curl('https://api.ipify.org')
    if result.returncode:raise RuntimeError('Re-enabled profile failed')
    report['reenabled_profile_works']=True
    api('PUT','/api/admin/clients/'+profile['id'],{'name':profile['name'],'quota_gb':0.000000001,'enabled':True})
    for _ in range(5):
        time.sleep(2)
        row=next(r for r in api('GET','/api/admin/clients') if r['id']==profile['id'])
        if row['status']=='limited':break
    if row['status']!='limited' or curl('https://api.ipify.org',8).returncode==0:raise RuntimeError('Quota did not block profile')
    report['quota_enforced']=True
    api('PUT','/api/admin/clients/'+profile['id'],{'name':profile['name'],'quota_gb':1,'enabled':True})
    rotated=api('POST','/api/admin/clients/'+profile['id']+'/rotate')
    if rotated['uri']==profile['uri']:raise RuntimeError('Credentials did not rotate')
    result=curl('https://api.ipify.org',8)
    if result.returncode==0:raise RuntimeError('Revoked credentials still work')
    report['old_credentials_denied']=True
    report['passed']=True
    (ROOT/'private/live-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    if process:process.terminate();process.wait(timeout=10)
    if profile:api('DELETE','/api/admin/clients/'+profile['id'])
    ssh.close()
