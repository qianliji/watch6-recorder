"""Run production Protocol + ArchiveStore with real JSON-java on the JVM.

--fixture is NDJSON. --store is an explicit output directory for integration
fixtures, never a real phone directory. Replies are saved with --output.
"""
from pathlib import Path
import argparse,json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def configuration():
    p=ROOT/'.local-build.json';return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path);p.add_argument('--store',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();c=configuration()
    java=Path(os.environ.get('JAVA_HOME',c.get('java_home','')));suffix='.exe' if os.name=='nt' else '';jar=Path(os.environ.get('W6R_JSON_TEST_JAR',c.get('json_test_jar','')))
    if not jar.is_file():raise SystemExit('Provide W6R_JSON_TEST_JAR with an authorized JSON-java test dependency; it is not included in source')
    with tempfile.TemporaryDirectory(prefix='watch6-recorder-phone-wire-') as td:
        out=Path(td);files=[ROOT/'src/com/watch6/recorder/ArchiveStore.java',ROOT/'src/com/watch6/recorder/Protocol.java',ROOT/'tests/ProtocolHarness.java',ROOT/'tests/ProtocolHostTest.java']
        result=subprocess.run([str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-classpath',str(jar),'-d',str(out),*map(str,files)],capture_output=True,text=True,encoding='utf-8',errors='replace');assert result.returncode==0,result.stderr
        cp=os.pathsep.join([str(out),str(jar)])
        if a.fixture:
            if not a.store:p.error('--fixture requires an explicit --store output directory')
            result=subprocess.run([str(java/('bin/java'+suffix)),'-cp',cp,'com.watch6.recorder.ProtocolHarness',str(a.store)],input=a.fixture.read_text(encoding='utf-8'),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120);assert result.returncode==0,result.stderr
            replies=[json.loads(line) for line in result.stdout.splitlines() if line.strip()];report=dict(passed=bool(replies) and all(r.get('ok') for r in replies),replies=replies,real_device_access=False,directory_sync='injected JVM edge, Android fsync not exercised')
        else:
            result=subprocess.run([str(java/('bin/java'+suffix)),'-cp',cp,'com.watch6.recorder.ProtocolHostTest',str(out/'synthetic')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120);assert result.returncode==0,result.stderr;report=json.loads(result.stdout)
        if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
