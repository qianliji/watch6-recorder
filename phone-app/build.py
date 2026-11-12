"""Build the MiFitness Android receiver with an authorized wearable SDK.

Private paths/passwords stay in ignored local configuration and signing sidecar.
No device install, microphone, private VoiceSpace signer or service credentials.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,secrets,subprocess,time,zipfile
ROOT=Path(__file__).resolve().parent
VERSION='0.5.1'
IDENTITY_VERSION='0.5.0'
def config():
    path=Path(os.environ.get('W6R_PHONE_BUILD_CONFIG',str(ROOT/'.local-build.json')))
    if not path.is_absolute():path=ROOT/path
    c=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    def get(env,key,default=''):return os.environ.get(env,c.get(key,default))
    java=Path(get('JAVA_HOME','java_home'));sdk=get('ANDROID_HOME','android_home',os.environ.get('ANDROID_SDK_ROOT',''))
    tools=get('W6R_ANDROID_BUILD_TOOLS','build_tools')
    if not tools and sdk:
        choices=list((Path(sdk)/'build-tools').glob('*'));tools=str(max(choices,key=lambda p:p.name)) if choices else ''
    android=get('W6R_ANDROID_PLATFORM','android_jar',str(Path(sdk)/'platforms/android-35/android.jar') if sdk else '')
    jars=os.environ.get('W6R_WEARABLE_JARS');libs=[Path(v) for v in jars.split(os.pathsep)] if jars else [Path(v) for v in c.get('sdk_jars',[])]
    if not tools or not android or not libs or any(not p.is_file() for p in libs):raise ValueError('Provide Android build-tools/platform and an authorized Xiaomi wearable SDK JAR')
    return dict(java=java,tools=Path(tools),android=Path(android),libs=libs)

def run(args,cwd=None,env=None):
    r=subprocess.run([str(a) for a in args],cwd=cwd or ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:raise RuntimeError('Build step failed: '+Path(str(args[0])).name+'\n'+r.stderr[-2200:]+'\n'+r.stdout[-1200:])
    return r.stdout
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signer(c,env):
    key=Path(os.environ.get('W6R_ANDROID_KEYSTORE',str(ROOT/'signing/recorder-development.jks')))
    sidecar=key.with_name(key.name+'.private.json');existing=json.loads(sidecar.read_text()) if sidecar.is_file() else {}
    password=os.environ.get('W6R_ANDROID_STORE_PASSWORD',existing.get('password',''))
    alias=os.environ.get('W6R_ANDROID_KEY_ALIAS',existing.get('alias','watch6-recorder'))
    if key.exists() and not password:raise ValueError('Existing signer requires private signing configuration')
    password=password or secrets.token_urlsafe(32);process_env={**env,'W6R_SIGN_PASSWORD':password};key.parent.mkdir(parents=True,exist_ok=True)
    if not key.exists():
        run([c['java']/'bin/keytool.exe' if os.name=='nt' else c['java']/'bin/keytool','-genkeypair','-keystore',key,'-storepass:env','W6R_SIGN_PASSWORD','-keypass:env','W6R_SIGN_PASSWORD','-alias',alias,'-dname','CN=Watch6 Recorder Development','-keyalg','RSA','-keysize','2048','-validity','3650'],env=process_env)
        with sidecar.open('x',encoding='utf-8') as out:json.dump(dict(password=password,alias=alias),out);out.flush();os.fsync(out.fileno())
        if os.name!='nt':sidecar.chmod(0o600)
    return key,alias,process_env
def main():
    p=argparse.ArgumentParser(description=__doc__);args=p.parse_args();c=config();suffix='.exe' if os.name=='nt' else ''
    out=ROOT/'build';out.mkdir(exist_ok=True);artifacts=ROOT/'artifacts';artifacts.mkdir(exist_ok=True);classes=out/'classes'
    if classes.exists():classes.rename(out/('classes-history-'+str(time.time_ns())))
    classes.mkdir();generated=out/'generated';generated.mkdir(exist_ok=True)
    env={**os.environ,'JAVA_HOME':str(c['java'])};key,alias,env=signer(c,env)
    tools=c['tools'];java=c['java'];resource=out/'resources.zip';unsigned=out/'unsigned.apk'
    run([tools/('aapt2'+suffix),'compile','--dir','res','-o',resource],env=env)
    run([tools/('aapt2'+suffix),'link','-I',c['android'],'--manifest','AndroidManifest.xml','-A','assets','--java',generated,'-o',unsigned,resource],env=env)
    cp=os.pathsep.join(str(v) for v in [c['android'],*c['libs']])
    run([java/('bin/javac'+suffix),'-encoding','UTF-8','-source','8','-target','8','-classpath',cp,'-d',classes,*list((ROOT/'src').rglob('*.java')),*list(generated.rglob('*.java'))],env=env)
    jar=out/'classes.jar'
    with zipfile.ZipFile(jar,'w') as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
    run([java/('bin/java'+suffix),'-cp',tools/'lib/d8.jar','com.android.tools.r8.D8','--lib',c['android'],'--min-api','31','--output',out,jar,*c['libs']],env=env)
    with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as z:z.write(out/'classes.dex','classes.dex')
    aligned=out/'aligned.apk';run([tools/('zipalign'+suffix),'-f','4',unsigned,aligned],env=env)
    apk=artifacts/('Watch6-Recorder-Phone-'+VERSION+'.apk')
    if apk.exists():apk.rename(artifacts/(apk.name+'.history-'+str(time.time_ns())))
    run([java/('bin/java'+suffix),'-jar',tools/'lib/apksigner.jar','sign','--ks',key,'--ks-key-alias',alias,'--ks-pass','env:W6R_SIGN_PASSWORD','--key-pass','env:W6R_SIGN_PASSWORD','--out',apk,aligned],env=env)
    verify=run([java/('bin/java'+suffix),'-jar',tools/'lib/apksigner.jar','verify','--verbose','--print-certs',apk],env=env)
    match=re.search(r'certificate SHA-256 digest:\s*([a-f0-9:]+)',verify,re.I)
    if not match:raise ValueError('Unable to verify APK signer fingerprint')
    fingerprint=match.group(1).replace(':','').lower()
    report=dict(version=VERSION,transport='mifitness_sdk',identity_required=True,vendor_sdk_included=True,package='com.watch6.recorder',apk=dict(path=apk.relative_to(ROOT).as_posix(),bytes=apk.stat().st_size,sha256=sha(apk)),signature_verified=True,certificate_sha256=fingerprint,source_inputs={f.relative_to(ROOT).as_posix():sha(f) for tree in ['src','assets','res'] for f in (ROOT/tree).rglob('*') if f.is_file()},vendor_inputs=[dict(name=p.name,sha256=sha(p)) for p in c['libs']],device_accessed=False,microphone_started=False,physical_verified=False,old_voice_space_signer_used=False)
    identity_report=ROOT/('watch-identity/dist/build-report-'+IDENTITY_VERSION+'.json')
    identity=json.loads(identity_report.read_text(encoding='utf-8'))
    package=ROOT/('watch-identity/dist/com.watch6.recorder.release.'+IDENTITY_VERSION+'.rpk')
    if identity['package']!=report['package'] or identity['version_code']<5 or sha(package)!=identity['sha256'] or identity['certificate_sha256']!=fingerprint:raise ValueError('Build the matching current identity RPK before the APK')
    for name,digest in identity['source_inputs'].items():
        if sha(ROOT/'watch-identity'/name)!=digest:raise ValueError('Identity source changed since RPK build')
    with zipfile.ZipFile(package)as z:
        manifest=json.loads(z.read('manifest.json'))
        if manifest['package']!=report['package'] or manifest['versionCode']!=identity['version_code']:raise ValueError('Identity package manifest does not match build report')
    identity_copy=artifacts/('Watch6-Recorder-Identity-'+IDENTITY_VERSION+'.rpk');identity_copy.write_bytes(package.read_bytes())
    report['compatible_identity']=dict(path=identity_copy.relative_to(ROOT).as_posix(),bytes=package.stat().st_size,sha256=sha(package),certificate_sha256=fingerprint,signer_certificate_der_embedded=identity['signer_certificate_der_embedded'],version=identity['version'],version_code=identity['version_code'],new_identity_built=True,build_report_sha256=sha(identity_report))
    for n in ['build.py','AndroidManifest.xml']:report['source_inputs'][n]=sha(ROOT/n)
    text=json.dumps(report,indent=2)+'\n'
    (artifacts/('build-report-'+VERSION+'.json')).write_text(text,encoding='utf-8');(artifacts/'build-report.json').write_text(text,encoding='utf-8')
    print(json.dumps({'version':report['version'],'apk':report['apk'],'signature_verified':True,'certificate_sha256':fingerprint,'identity_required':True,'vendor_sdk_included':True,'source_inputs':len(report['source_inputs']),'physical_verified':False}))
if __name__=='__main__':main()
