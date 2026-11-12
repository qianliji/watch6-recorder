"""Validate MiFitness companion output without opening the SDK or a device."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();local=ROOT/'.local-build.json';cfg=json.loads(local.read_text(encoding='utf-8-sig'))if local.is_file()else{};r=json.loads((ROOT/'artifacts/build-report.json').read_text(encoding='utf-8'));checks=[]
 def check(label,value):
  checks.append({'check':label,'passed':bool(value)})
  assert value,label
 check('declared source inputs match current source',all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in r['source_inputs'].items()))
 apk=ROOT/r['apk']['path'];check('APK hash matches report',hashlib.sha256(apk.read_bytes()).hexdigest()==r['apk']['sha256'])
 check('APK signature verified',r['signature_verified'])
 historical_paths={'0.2.0-preview':ROOT/'artifacts/releases/0.2.0-preview/build-report.json','0.3.1-preview':ROOT/'artifacts/build-report-0.3.1-preview.json'}
 historical={version:json.loads(path.read_text(encoding='utf-8'))for version,path in historical_paths.items()if path.is_file()}
 if historical:check('same signer as available historical release reports',all(old['certificate_sha256']==r['certificate_sha256']for old in historical.values()))
 upgrade={'status':'verified_available_reports'if historical else'not_checked_no_historical_reports','versions_checked':list(historical),'versions_not_checked':[version for version in historical_paths if version not in historical],'device_upgrade_tested':False}
 check('MiFitness transport explicitly requires identity component',r['transport']=='mifitness_sdk' and r['identity_required']is True and r['vendor_sdk_included']is True)
 identity=r['compatible_identity'];check('current identity upgrades capture-check and matches APK signer',identity['new_identity_built']is True and identity['version_code']>=5 and identity['certificate_sha256']==r['certificate_sha256'] and hashlib.sha256((ROOT/identity['path']).read_bytes()).hexdigest()==identity['sha256'])
 identity_report=ROOT/('watch-identity/dist/build-report-'+identity['version']+'.json');check('identity build report is bound to APK release',hashlib.sha256(identity_report.read_bytes()).hexdigest()==identity['build_report_sha256'])
 ir=json.loads(identity_report.read_text(encoding='utf-8'));check('identity build inputs and public certificate match current release',ir['certificate_sha256']==r['certificate_sha256'] and all(hashlib.sha256((ROOT/'watch-identity'/name).read_bytes()).hexdigest()==digest for name,digest in ir['source_inputs'].items()) and hashlib.sha256((ROOT/'watch-identity/build.cjs').read_bytes()).hexdigest()==ir['build_script_sha256'])
 identity_bytes=(ROOT/identity['path']).read_bytes();embedded_certificate=False
 for offset in range(len(identity_bytes)-4):
  if identity_bytes[offset]!=0x30:continue
  length_byte=identity_bytes[offset+1];length_bytes=length_byte&0x7f if length_byte&0x80 else 0
  if length_bytes>3:continue
  header=2+length_bytes;size=int.from_bytes(identity_bytes[offset+2:offset+header],'big')if length_bytes else length_byte
  if size>0 and offset+header+size<=len(identity_bytes) and hashlib.sha256(identity_bytes[offset:offset+header+size]).hexdigest()==r['certificate_sha256']:embedded_certificate=True;break
 check('actual identity RPK embeds the matching public signing certificate',embedded_certificate)
 with zipfile.ZipFile(ROOT/identity['path'])as z:
  m=json.loads(z.read('manifest.json'));check('actual identity RPK is a pure communication component',m['package']==r['package'] and m['name']=='录音连接组件' and m['versionName']==identity['version'] and m['versionCode']>=5 and m['features']==[{'name':'system.interconnect'}])
  check('identity RPK has no native payload or recording implementation',all(not name.lower().endswith(('.so','.elf','.o','.a','.wav','.pcm'))for name in z.namelist()) and all(token not in z.read(name).decode('utf-8')for name in z.namelist()if name.endswith('.js')for token in ['@system.record','@system.audio','@system.file','@system.interconnect','device.start','globalThis.Module','dlopen']))
  page=z.read('pages/index/index.js').decode('utf-8');check('identity page sends users to the recording watchface',all(token in page for token in ['录音连接组件','录音表盘','不录音','无需打开']))
 tools=Path(os.environ.get('W6R_ANDROID_BUILD_TOOLS',cfg.get('build_tools','')));node=os.environ.get('W6R_NODE',cfg.get('node','node'));suffix='.exe'if os.name=='nt'else''
 java=Path(os.environ.get('JAVA_HOME',cfg.get('java_home','')))
 signature=subprocess.run([str(java/('bin/java'+suffix)),'-jar',str(tools/'lib/apksigner.jar'),'verify','--verbose','--print-certs',str(apk)],capture_output=True,text=True,encoding='utf-8',errors='replace');fingerprint=re.search(r'certificate SHA-256 digest:\s*([a-f0-9:]+)',signature.stdout,re.I)
 check('actual APK cryptographic signature and public certificate verified',signature.returncode==0 and fingerprint is not None and fingerprint.group(1).replace(':','').lower()==r['certificate_sha256'])
 proc=subprocess.run([str(tools/('aapt2'+suffix)),'dump','badging',str(apk)],capture_output=True,text=True,encoding='utf-8',errors='replace');check('actual APK manifest parses',proc.returncode==0)
 check('package remains com.watch6.recorder',"name='com.watch6.recorder'"in proc.stdout)
 check('APK version matches the declared candidate',("versionName='"+r['version']+"'")in proc.stdout)
 check('CONNECT permission present',"android.permission.BLUETOOTH_CONNECT"in proc.stdout)
 check('no microphone, internet, advertise, scan or broad storage permissions',all(n not in proc.stdout for n in ['android.permission.RECORD_AUDIO','android.permission.INTERNET','android.permission.BLUETOOTH_ADVERTISE','android.permission.BLUETOOTH_SCAN','android.permission.READ_EXTERNAL_STORAGE','android.permission.WRITE_EXTERNAL_STORAGE','android.permission.MANAGE_EXTERNAL_STORAGE']))
 with zipfile.ZipFile(apk)as z:
  dex=z.read('classes.dex');check('authorized MiFitness wearable SDK in actual DEX',b'com/xiaomi/xms/wearable'in dex)
  check('obsolete direct BLE code excluded from actual DEX',all(n not in dex for n in [b'DirectHandshake;',b'DirectDiagnostics;',b'DirectCallbackLease;',b'7f6b0001-3f15']))
  html=z.read('assets/index.html').decode();check('setup and diagnostics explain one-time component installation',all(n in html for n in ['id="setup"','id="diagnostics"','配套 RPK「录音连接组件」','日常无需打开']))
  check('recording library and connection settings shipped',all(n in html for n in ['id="libraryPanel"','id="settingsPanel"','id="libraryTab"','id="settingsTab"']))
  check('no direct pairing UI shipped',all(n not in html for n in ['id="pairing"','id="approve"','连接码','独立BLE']))
 proc=subprocess.run([node,'--check',str(ROOT/'assets/app.js')],capture_output=True,text=True,encoding='utf-8',errors='replace');check('production JS syntax valid',proc.returncode==0)
 ids=re.findall(r'\bid="([^"]+)"',(ROOT/'assets/index.html').read_text(encoding='utf-8'));check('no duplicate DOM ids',len(ids)==len(set(ids)))
 for source in (ROOT/'src').rglob('*.java'):check('no cloud URL/key in '+source.name,not re.search(r'(sk-[A-Za-z0-9]{15,}|https?://)',source.read_text(encoding='utf-8')))
 text=(ROOT/'src/com/watch6/recorder/PhoneLink.java').read_text(encoding='utf-8')
 check('no direct radio, global scan, automatic launch or adapter reset',all(n not in text for n in ['BluetoothGatt','startDiscovery(','getBluetoothLeScanner','BluetoothLeAdvertiser','adapter.enable(','adapter.disable(','launchWearApp']))
 check('owns and retires SDK listener lifecycle',all(n in text for n in ['LEASE.acquire','LEASE.release','unregisterServiceConnectionListener','accepts(lease)']))
 manifest=(ROOT/'AndroidManifest.xml').read_text(encoding='utf-8')
 check('boot/update restore and Fitness package visibility declared',all(n in manifest for n in ['android.intent.action.BOOT_COMPLETED','android.intent.action.MY_PACKAGE_REPLACED','com.mi.health','com.xiaomi.wearable']))
 report={'passed':True,'version':r['version'],'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'identity_sha256':hashlib.sha256(identity_bytes).hexdigest(),'build_report_sha256':hashlib.sha256((ROOT/'artifacts/build-report.json').read_bytes()).hexdigest(),'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':checks,'check_count':len(checks),'historical_upgrade':upgrade,'physical_verified':False,'scope':'actual APK signature, RPK public certificate, package contents and source validation; optional historical signer comparison does not test a device upgrade; not physical MiFitness authorization, Bluetooth transfer, background policy or speaker playback acceptance'}
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'passed':True,'check_count':len(checks),'apk_sha256':r['apk']['sha256'],'identity_required':True,'historical_upgrade':upgrade,'physical_verified':False}))
if __name__=='__main__':main()
