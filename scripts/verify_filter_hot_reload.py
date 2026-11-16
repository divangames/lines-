"""Exercise Xray filter replacement in an isolated core, with no production changes."""
import json,os,subprocess,tempfile,time,sys
from pathlib import Path
sys.path.insert(0,'/opt/linea-filter')
from update_filter import geosite

with tempfile.TemporaryDirectory(prefix='linea-filter-check-') as directory:
 root=Path(directory); asset=root/'test.dat'
 asset.write_bytes(geosite(['google-analytics.com']))
 config={'log':{'loglevel':'error','access':'none'},'api':{'tag':'api','services':['RoutingService']},
   'inbounds':[{'tag':'api','listen':'127.0.0.1','port':10086,'protocol':'dokodemo-door','settings':{'address':'127.0.0.1'}},
               {'tag':'check','listen':'127.0.0.1','port':21111,'protocol':'socks','settings':{'auth':'noauth'}}],
   'outbounds':[{'tag':'direct','protocol':'freedom'},{'tag':'blocked','protocol':'blackhole'}],
   'routing':{'rules':[{'type':'field','inboundTag':['api'],'outboundTag':'api'},
                       {'type':'field','domain':['ext:test.dat:ads'],'outboundTag':'blocked'}]}}
 path=root/'config.json';path.write_text(json.dumps(config))
 routing=root/'routing.json';routing.write_text(json.dumps({'routing':config['routing']}))
 env={**os.environ,'XRAY_LOCATION_ASSET':directory}
 with (root/'core.log').open('w') as log:
  process=subprocess.Popen(['/opt/linea/bin/xray','run','-config',str(path)],env=env,stdout=log,stderr=log)
  try:
   time.sleep(1)
   def request():
    return subprocess.run(['curl','--fail','--silent','--show-error','--max-time','10',
        '--socks5-hostname','127.0.0.1:21111','https://example.org'],capture_output=True)
   def reload():
    subprocess.run(['/opt/linea/bin/xray','api','adrules','--server=127.0.0.1:10086',str(routing)],env=env,check=True,capture_output=True)
   assert request().returncode==0,'Allowed baseline failed'
   (root/'test-v2.dat').write_bytes(geosite(['google-analytics.com','example.org']))
   config['routing']['rules'][1]['domain']=['ext:test-v2.dat:ads']
   routing.write_text(json.dumps({'routing':config['routing']}))
   reload()
   assert request().returncode!=0,'New block list did not take effect'
   config['routing']['rules'][1]['domain']=['ext:test.dat:ads']
   routing.write_text(json.dumps({'routing':config['routing']}))
   reload()
   assert request().returncode==0,'Previous filter not restored'
   assert process.poll() is None
   print('PASS: filter replacement and rollback apply without restarting Xray')
  finally:
   process.terminate();process.wait(timeout=5)
