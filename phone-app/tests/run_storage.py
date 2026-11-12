"""Compile and execute the production Java archive with synthetic audio only."""
from pathlib import Path
import argparse,importlib.util,json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
def configuration():
    p=ROOT/'.local-build.json';return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args();c=configuration()
    java=Path(os.environ.get('JAVA_HOME',c.get('java_home','')));suffix='.exe' if os.name=='nt' else ''
    with tempfile.TemporaryDirectory(prefix='watch6-recorder-phone-storage-') as td:
        out=Path(td);command=[str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-d',str(out),str(ROOT/'src/com/watch6/recorder/ArchiveStore.java'),str(ROOT/'tests/ArchiveStoreTest.java')]
        r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace');assert r.returncode==0,r.stderr
        r=subprocess.run([str(java/('bin/java'+suffix)),'-cp',str(out),'com.watch6.recorder.ArchiveStoreTest',str(out/'synthetic')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60);assert r.returncode==0,r.stderr
        report=json.loads(r.stdout);report['scope']='production ArchiveStore with JVM synthetic files and injected directory-sync edge; not Android filesystem or radio acceptance'
        if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report))
if __name__=='__main__':main()
