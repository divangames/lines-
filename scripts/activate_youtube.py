"""Apply the tested YouTube egress with backups and rollback; keep Xray counters alive."""
import json,os,shutil,sqlite3,subprocess,tarfile,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path

STAGE=Path('/root/VPN/youtube')
STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
BACKUP=Path('/root/VPN/backups')/('before-youtube-'+STAMP)
BACKUP.mkdir(mode=0o700)
os.umask(0o077)
FILES=[Path('/opt/linea/server/engine.py'),Path('/etc/linea/config.json'),Path('/root/VPN/Caddyfile'),
       Path('/var/lib/linea/xray.json')]
originals={str(path):path.read_bytes() for path in FILES}
for path in FILES:shutil.copy2(path,BACKUP/path.name)
with sqlite3.connect('/var/lib/linea/portal.db') as source,sqlite3.connect(BACKUP/'portal.db') as dest:
    source.backup(dest)
    assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def run(arguments,env=None):
    result=subprocess.run(arguments,capture_output=True,text=True,timeout=35,env=env)
    if result.returncode:
        (STAGE/'activation-error.log').write_text(result.stdout+result.stderr)
        raise RuntimeError('Command failed; private diagnostics saved: '+arguments[0])
    return result

def api(action,fragment):
    path=STAGE/('api-'+action+'.json');path.write_text(json.dumps(fragment));path.chmod(0o600)
    return run(['/opt/linea/bin/xray','api',action,'--server=127.0.0.1:10085','-timeout=20',str(path)],
               env={**os.environ,'XRAY_LOCATION_ASSET':'/var/lib/linea-filter'})

def health():
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088/healthz',timeout=2) as response:
                if json.load(response).get('ok'):return
        except Exception:time.sleep(.5)
    raise RuntimeError('Portal health check failed')

candidate=json.loads((STAGE/'xray.next.json').read_text())
caddy=originals['/root/VPN/Caddyfile'].decode()
line='upstream socks5://127.0.0.1:1089'
assert caddy.count('forward_proxy {')==1
if line not in caddy:caddy=caddy.replace('forward_proxy {','forward_proxy {\n            '+line,1)
(STAGE/'Caddyfile.next').write_text(caddy)
run(['/root/VPN/bin/caddy','validate','--config',str(STAGE/'Caddyfile.next'),'--adapter','caddyfile'])
assert json.loads((STAGE/'stage-report.json').read_text())['passed']
outbound=next(o for o in candidate['outbounds'] if o.get('tag')=='youtube-vpn')
inbound=next(i for i in candidate['inbounds'] if i.get('tag')=='naive-egress')
previous=json.loads(originals['/var/lib/linea/xray.json'])
added_outbound=False;added_inbound=False;changed_routing=False;changed_files=False;caddy_changed=False
youtube_path=Path('/etc/linea/youtube-upstream.json')
dropin=Path('/etc/systemd/system/naiveproxy.service.d/youtube.conf')
previous_private=youtube_path.read_bytes() if youtube_path.exists() else None
previous_dropin=dropin.read_bytes() if dropin.exists() else None
before_pid=subprocess.check_output(['systemctl','show','--value','-p','MainPID','linea-xray'],text=True).strip()
try:
    api('ado',{'outbounds':[outbound]});added_outbound=True
    api('adi',{'inbounds':[inbound]});added_inbound=True
    api('adrules',{'routing':candidate['routing']});changed_routing=True
    shutil.copyfile(STAGE/'private.json',youtube_path)
    shutil.chown(youtube_path,user='root',group='linea');youtube_path.chmod(0o640)
    config=json.loads(originals['/etc/linea/config.json'])
    config['youtube_upstream']=str(youtube_path)
    Path('/etc/linea/config.json').write_text(json.dumps(config,indent=2)+'\n')
    shutil.chown('/etc/linea/config.json',user='root',group='linea');Path('/etc/linea/config.json').chmod(0o640)
    shutil.copyfile(STAGE/'engine.py','/opt/linea/server/engine.py');Path('/opt/linea/server/engine.py').chmod(0o644)
    changed_files=True
    dropin.write_text('[Unit]\nWants=linea-xray.service\nAfter=linea-xray.service\n');dropin.chmod(0o644)
    run(['systemctl','daemon-reload'])
    run(['systemctl','restart','linea-portal']);health()
    Path('/root/VPN/Caddyfile').write_text(caddy);caddy_changed=True
    run(['systemctl','kill','-s','SIGUSR1','naiveproxy'])
    time.sleep(1)
    run(['systemctl','is-active','linea-xray','linea-portal','naiveproxy','linea-filter'])
    after_pid=subprocess.check_output(['systemctl','show','--value','-p','MainPID','linea-xray'],text=True).strip()
    assert before_pid==after_pid,'Xray process unexpectedly restarted'
    (STAGE/'activation-report.json').write_text(json.dumps({'applied':True,'backup':str(BACKUP),'xray_pid_preserved':True,
        'private_upstream':str(youtube_path),'naive_router':'127.0.0.1:1089'},indent=2)+'\n')
    print('Applied server-only YouTube egress to VLESS and NaiveProxy; Xray counters retained')
    print('Backup:',BACKUP)
except Exception:
    if changed_routing:
        try:api('adrules',{'routing':previous['routing']})
        except Exception:pass
    for path in FILES:
        if path.name!='xray.json':path.write_bytes(originals[str(path)])
    Path('/opt/linea/server/engine.py').chmod(0o644)
    shutil.chown('/etc/linea/config.json',user='root',group='linea');Path('/etc/linea/config.json').chmod(0o640)
    if previous_private is None:youtube_path.unlink(missing_ok=True)
    else:youtube_path.write_bytes(previous_private)
    if previous_dropin is None:dropin.unlink(missing_ok=True)
    else:dropin.write_bytes(previous_dropin)
    subprocess.run(['systemctl','daemon-reload'],capture_output=True)
    if changed_files:subprocess.run(['systemctl','restart','linea-portal'],capture_output=True)
    if caddy_changed:subprocess.run(['systemctl','kill','-s','SIGUSR1','naiveproxy'],capture_output=True)
    if added_inbound:subprocess.run(['/opt/linea/bin/xray','api','rmi','--server=127.0.0.1:10085','naive-egress'],capture_output=True)
    if added_outbound:subprocess.run(['/opt/linea/bin/xray','api','rmo','--server=127.0.0.1:10085','youtube-vpn'],capture_output=True)
    print('Activation failed; previous routing restored. Private diagnostics:',STAGE/'activation-error.log')
    raise
