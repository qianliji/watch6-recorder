"""Actual ARM sender -> actual JVM Protocol/ArchiveStore -> actual ARM ACK.

Only the SDK/OS boundary and Android directory fsync are injected. This is not
a fake protocol parser, a real phone test, or a performance benchmark.
"""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_phone_transport as native

class CrossLayerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  native.TransportTests.setUpClass()
  cls.temp=tempfile.TemporaryDirectory(prefix='w6r-cross-wire-');cls.work=Path(cls.temp.name)
  phone=ROOT/'phone-app';config=json.loads((phone/'.local-build.json').read_text(encoding='utf-8-sig'))if(phone/'.local-build.json').is_file()else{}
  java=Path(os.environ.get('JAVA_HOME',config.get('java_home','')));jar=Path(os.environ.get('W6R_JSON_TEST_JAR',config.get('json_test_jar','')))
  if not jar.is_file():raise unittest.SkipTest('External authorized JSON-java test dependency is not configured')
  suffix='.exe'if os.name=='nt'else'';cls.java=java/('bin/java'+suffix)
  cls.cp=os.pathsep.join([str(cls.work),str(jar)])
  files=[phone/'src/com/watch6/recorder/ArchiveStore.java',phone/'src/com/watch6/recorder/Protocol.java',phone/'tests/ProtocolHarness.java']
  r=subprocess.run([str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-classpath',str(jar),'-d',str(cls.work),*map(str,files)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
  assert r.returncode==0,r.stderr
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup();native.TransportTests.tearDownClass()
 def setUp(self):self.h=native.Host(native.TransportTests.raw,native.TransportTests.sections,native.TransportTests.syms);self.store=self.work/self._testMethodName
 def phone(self,request):
  r=subprocess.run([str(self.java),'-cp',self.cp,'com.watch6.recorder.ProtocolHarness',str(self.store)],input=json.dumps(request,separators=(',',':'))+'\n',capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
  self.assertEqual(r.returncode,0,r.stderr);lines=[json.loads(s)for s in r.stdout.splitlines()if s.strip()];self.assertEqual(len(lines),1);return lines[0]
 def roundtrip(self):
  h=self.h;request=h.wire();reply=self.phone(request);self.assertTrue(reply['ok'],reply);self.assertEqual(reply['request_id'],request['id']);self.assertEqual(reply['durable'],reply['next']);h.complete();h.receive(reply);return reply
 def test_complete_wire_and_pcm_sha(self):
  h=self.h;h.setup(6000);h.tick(25);reply=self.roundtrip();self.assertEqual(reply['next'],0)
  for stamp in (50,75,100):h.tick(stamp);reply=self.roundtrip()
  self.assertEqual(reply['next'],6000);self.assertEqual(h.get(5),6000);h.tick(125);self.assertEqual(h.wire()['action'],'recorder_finish');reply=self.roundtrip();self.assertTrue(reply['complete']);self.assertEqual(h.get(4),4)
  files=list(self.store.rglob('*.wav'));self.assertEqual(len(files),1);data=files[0].read_bytes();self.assertEqual(data,native.wav(h.pcm));self.assertEqual(reply['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(h.get(9),1)
  h.tick(150);h.call('host_worker_closed');self.assertEqual(h.call('host_unload'),0)
 def test_lost_ack_real_checkpoint_reoffers_and_resumes(self):
  h=self.h;h.setup(6000);h.tick(25);self.roundtrip();h.tick(50);self.roundtrip();self.assertEqual(h.get(5),2048)
  h.tick(75);lost=self.phone(h.wire());self.assertEqual(lost['next'],4096);h.complete()
  # Phone committed a chunk but its ACK never reached the watch. This is a
  # fresh Java process/store load on every step, exercising durable checkpoint.
  h.call('host_event',3);h.call('host_online');h.tick(100);reply=self.roundtrip();self.assertEqual(reply['next'],4096);self.assertEqual(h.get(5),4096)
  h.tick(125);self.assertEqual(h.wire()['offset'],4096);self.roundtrip();h.tick(150);reply=self.roundtrip();self.assertTrue(reply['complete']);self.assertEqual(h.get(4),4);files=list(self.store.rglob('*.wav'));self.assertEqual(files[0].read_bytes(),native.wav(h.pcm))
 def test_phone_rejects_wrong_whole_crc_and_native_keeps_source(self):
  h=self.h;h.setup(100);h.files[native.BASE+b'w6r-export-job.txt']=native.job(100,crc='00000000');h.tick(25);self.roundtrip();h.tick(50);self.roundtrip();h.tick(75)
  reply=self.phone(h.wire());self.assertFalse(reply['ok']);h.complete();h.receive(reply);self.assertEqual(h.get(4),6);self.assertIn(native.BASE+b'w6r-play-'+native.CACHE.encode()+b'.wav',h.files);self.assertFalse(list(self.store.rglob('*.wav')))

if __name__=='__main__':unittest.main(verbosity=2)
