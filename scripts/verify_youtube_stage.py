"""Test the candidate server configuration in a separate core before deployment."""
import json,os,re,subprocess,tempfile,time
from pathlib import Path

base=Path('/root/VPN/youtube')
candidate=json.loads((base/'xray.next.json').read_text())
candidate['inbounds']=[{'tag':'stage','listen':'127.0.0.1','port':21099,'protocol':'socks','settings':{'auth':'noauth'}}]
candidate.pop('api',None)
candidate.pop('stats',None)
candidate.pop('policy',None)
candidate['routing']['rules']=[rule for rule in candidate['routing']['rules'] if rule.get('outboundTag')!='api']
path=base/'stage.json';path.write_text(json.dumps(candidate));path.chmod(0o600)
env={**os.environ,'XRAY_LOCATION_ASSET':'/var/lib/linea-filter'}
with (base/'stage.log').open('w') as log:
 process=subprocess.Popen(['/opt/linea/bin/xray','run','-config',str(path)],env=env,stdout=log,stderr=log)
 try:
  time.sleep(1)
  assert process.poll() is None,'Candidate failed to start'
  def get(url):
   return subprocess.run(['curl','-4','-fsS','--max-time','25','--socks5-hostname','127.0.0.1:21099',
      '-A','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',url],capture_output=True,timeout=30)
  result=get('https://api.ipify.org')
  assert result.returncode==0 and result.stdout.strip()==b'217.60.19.243','Non-YouTube traffic left the VPS'
  print('PASS: candidate retains VPS IP for ordinary traffic',flush=True)
  result=get('https://www.youtube.com/?hl=en')
  assert result.returncode==0,'YouTube connection through upstream failed'
  text=result.stdout.decode('utf-8','replace');client={}
  for match in re.finditer(r'ytcfg\.set\(',text):
   try:value,_=json.JSONDecoder().raw_decode(text[match.end():])
   except ValueError:continue
   current=value.get('INNERTUBE_CONTEXT',{}).get('client',{})
   if current.get('gl'):client=current;break
  print(json.dumps({'youtube_region':client.get('gl'),'youtube_ip':client.get('remoteHost')}),flush=True)
  assert client.get('gl')=='RU' and client.get('remoteHost') not in (None,'217.60.19.243','2a12:bec4:1485:525:0:0:0:2'),'Unexpected YouTube egress or region'
  print('PASS: YouTube uses external VPN IP with RU region',flush=True)
  result=get('https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg')
  assert result.returncode==0 and result.stdout.startswith(b'\xff\xd8'),'YouTube image endpoint failed'
  print('PASS: YouTube media resources load',flush=True)
  result=get('https://google-analytics.com/')
  assert result.returncode!=0,'Ad/tracker blocking stopped working'
  print('PASS: ad blocking retained',flush=True)
  (base/'stage-report.json').write_text(json.dumps({'passed':True,'youtube_region':client['gl'],'youtube_ip':client['remoteHost'],'normal_ip':'217.60.19.243'},indent=2))
 finally:
  process.terminate();process.wait(timeout=8)
