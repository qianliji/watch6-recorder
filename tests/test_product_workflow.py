"""One continuous production-code workflow, with explicit synthetic hardware.

Starts with an empty watch archive. Deterministic PCM enters ONLY through the
Capture/RPMSG recv boundary, then unchanged ARM p65-media/owner/spool/fs/status
create the session, PCM, sealed metadata and CLOSED ledger consumed by actual
bundled Lua main/app/UI. Actual ARM player builds/revalidates its WAV, and the
actual ARM sender exchanges bytes/ACKs with JVM Protocol/ArchiveStore. Nothing
seeds a saved catalog, ready status, sealed source or prepared WAV.

Simulated: firmware guard success, OS/filesystem/task/clock APIs, microphone
PCM/notifications, speaker RPC/position/completion, MiFitness delivery/SDK
completion and directory fsync. The phone harness explicitly injects READY and
phone=1 in host_reset and uses host_online after a lost ACK; its real firmware
initializer/UV worker loop do not run. host_finalize simulates UV-loop/worker
exit before exercising Lua's receipt annotation. Java FileDescriptor.sync is real. No physical
microphone, speaker, radio, installation, RPK identity or latency is verified.
"""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_main_integration as main
import test_phone_transport as transport
from build_settings import arm_tools,program
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_R1

BASE=b'/data/watch6recorder/'
PHONE_EXTRA=r'''
void host_bind_nonce(const char *n){copy(ctx.nonce,n,16);ctx.nonce[16]=0;
 struct w6e_io io;w6e_fs_init(&export_fs,ctx.nonce);w6e_fs_ops(&export_fs,&io);io.send=export_send;
 w6e_init(&exporter,&io,ctx.nonce,321);w6e_transport(&exporter,1,1,0);}
void host_finalize(void){ctx.done=ctx.loop_closed=1;ctx.phase="closed";w6e_worker_closed(&exporter);(void)snapshot();}
'''

def compile_arm(work,name,files,wrapper=None):
 tools=arm_tools();out=work/name;out.mkdir()
 if wrapper is not None:
  source=out/'wrapper.c';source.write_text(wrapper,encoding='utf-8');files=[source,*files]
 script=out/'test.ld';script.write_text('ENTRY(host_initialize)\nSECTIONS {. = 0x10000; .text : { *(.text*) *(.rodata*) } . = ALIGN(8); .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }}')
 flags=['-mcpu=cortex-m3','-mthumb','-Os','-fno-inline','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(ROOT/'native')]
 objects=[]
 for i,source in enumerate(files):
  obj=out/f'{i}.o';r=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(source),'-o',str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace');assert r.returncode==0,r.stderr;objects.append(obj)
 elf=out/'test.elf';r=subprocess.run([str(program(tools,'arm-none-eabi-ld')),'-T',str(script),'-o',str(elf),*map(str,objects)],capture_output=True,text=True,encoding='utf-8',errors='replace');assert r.returncode==0,r.stderr
 raw=elf.read_bytes();header=struct.unpack_from('<16sHHIIIIIHHHHHH',raw);sections=[struct.unpack_from('<10I',raw,header[6]+i*header[11])for i in range(header[12])];symbols={}
 for section in sections:
  if section[1]==2:
   strings=sections[section[6]];names=raw[strings[4]:strings[4]+strings[5]]
   for p in range(section[4],section[4]+section[5],16):
    at,value,size,_,_,index=struct.unpack_from('<IIIBBH',raw,p)
    if at:symbols[names[at:names.index(0,at)].decode()]=(value,size,index)
 return raw,sections,symbols

class LuaFiles:
 """One shared binary-safe filesystem, also seen by unmodified Lua io.open."""
 def __init__(self,host):self.host=host
 def __contains__(self,path):return self.host.get(path)is not None
 def __getitem__(self,path):
  result=self.host.get(path)
  if result is None:raise KeyError(path)
  return result
 def __setitem__(self,path,value):self.host.set(path,value)
 def __delitem__(self,path):self.host.set(path,None)
 def get(self,path,default=None):
  value=self.host.get(path);return default if value is None else value
 def items(self):return self.host.files.items()

class NativeBoundary:
 """Real ARM instructions, hooks only at declared OS/media API addresses."""
 def __init__(self,artifact,flow,kind):
  raw,sections,self.syms=artifact;self.flow=flow;self.kind=kind;self.files=flow.files
  self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
  for address,size in [(0x10000,0x200000),(0x220000,0x10000),(0x300000,0x10000),(0x0c000000,0x1000000),(0x1c000000,0x1000000)]:self.u.mem_map(address,size)
  for section in sections:
   if section[2]&2 and section[5] and section[1]!=8:self.u.mem_write(section[3],raw[section[4]:section[4]+section[5]])
  for start,end in [(0x0c000000,0x0cffffff),(0x1c000000,0x1cffffff)]:self.u.hook_add(UC_HOOK_CODE,self.hook,begin=start,end=end)
  # Fingerprints cannot be inferred from host RAM. This is a declared guard
  # injection; the Lua main firmware checks still run against a synthetic image.
  if kind=='player':self.u.hook_add(UC_HOOK_CODE,self.guard,begin=self.syms['guards'][0]&~1,end=self.syms['guards'][0]&~1)
  self.fds={};self.nextfd=10;self.worker=None;self.alive=False;self.events=0
  self.pcm=flow.pcm;self.stream=transport.wav(self.pcm);self.stream_at=0
  self.starts=self.pauses=self.stops=self.closed=0;self.running=False;self.paused=False
  self.media_start=0;self.position=0;self.completed=False;self.played=b''
  self.missing_eof=False;self.expect_retained=False;self.halted_retained=False
 def guard(self,u,address,size,data):u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def call(self,name,*args):return self.call_addr(self.syms[name][0],*args)
 def call_addr(self,address,*args):
  self.u.reg_write(UC_ARM_REG_SP,0x30fff8);self.u.reg_write(UC_ARM_REG_LR,0x300001)
  for reg,value in zip(transport.REGS,args):self.u.reg_write(reg,value&0xffffffff)
  self.u.emu_start(address|1,0x300000,timeout=45000000,count=200000000)
  assert self.u.reg_read(UC_ARM_REG_PC)==0x300000 or self.halted_retained,f'{self.kind} did not return'
  return self.u.reg_read(UC_ARM_REG_R0)
 def cstring(self,address):
  if not address:return b''
  out=bytearray()
  for i in range(512):
   b=bytes(self.u.mem_read(address+i,1))
   if b==b'\0':return bytes(out)
   out+=b
  raise AssertionError('unbounded C string')
 def event(self,number):
  address=self.events;old=struct.unpack('<I',self.u.mem_read(address,4))[0];self.u.mem_write(address,struct.pack('<I',old|(1<<number)))
 def initialize(self):
  self.events=self.call('host_event_address');result=self.call('host_initialize');assert result==0,(self.kind,result)
 def run(self,retain=False):
  assert self.worker is not None
  self.expect_retained=retain
  self.alive=True;self.files[b'/proc/'+str(self.pid).encode()+b'/status']=b'synthetic live worker';self.files[b'/proc/'+str(self.pid).encode()+b'/cmdline']=b'synthetic live worker'
  try:result=self.call_addr(self.worker,0,0)
  finally:
   if not self.halted_retained:
    self.alive=False
    for suffix in [b'/status',b'/cmdline']:self.files.host.set(b'/proc/'+str(self.pid).encode()+suffix,None)
  if retain:
   assert self.halted_retained,'Expected the real owner to retain its live worker'
   return
  assert result==0,(self.kind,result)
 def hook(self,u,address,size,data):
  args=[u.reg_read(reg)for reg in transport.REGS];r=0
  if address==0x0c8bef00:
   path=self.cstring(args[0]);flags=args[1]
   if flags==0x40e and path in self.files:r=-17
   elif flags in (1,0x401,2) and path not in self.files:r=-2
   else:
    if flags==0x40e:self.files[path]=b''
    fd=self.nextfd;self.nextfd+=1;self.fds[fd]=[path,0,flags];r=fd
  elif address==0x0c8beaf0:
   path,pos,_=self.fds[args[0]];value=self.files.get(path,b'')[pos:pos+args[2]]
   if value:u.mem_write(args[1],value)
   self.fds[args[0]][1]+=len(value);r=len(value)
  elif address==0x0c8be040:
   path,pos,_=self.fds[args[0]];value=bytes(u.mem_read(args[1],args[2]));old=self.files.get(path,b'');self.files[path]=old[:pos]+value+old[pos+len(value):];self.fds[args[0]][1]+=len(value);r=len(value)
  elif address==0x0c8bdba8:self.fds.pop(args[0]);r=0
  elif address==0x0c8befd0:
   path=self.cstring(args[0]);r=0 if path in self.files else -2
   if r==0:del self.files[path]
  elif address==0x1c159e88:r=0 # Explicit RAM filesystem sync boundary.
  elif address==0x0c4f793c:u.mem_write(0x22ff00,struct.pack('<I',11));r=0x22ff00
  elif address==0x0c4c1e44:
   ticks=self.flow.clock*10;u.reg_write(UC_ARM_REG_R1,ticks>>32);r=ticks&0xffffffff
  elif address==0x0c4c8b38:
   retained_status=self.files.get(BASE+b'vs-meeting-source-status.txt',b'')
   if self.expect_retained and b'"phase":"retained"'in retained_status:
    # Suspend emulation at production's retained-owner wait. This is neither
    # worker completion nor unload proof; leave its PID and resources live.
    self.halted_retained=True;u.emu_stop();return
   delay=max(1,args[0]//1000)
   # A missing-EOF test advances its synthetic clock faster after STOP. The
   # real timeout/retention logic runs; no host wall-clock wait is necessary.
   self.flow.step(delay*(40 if self.missing_eof and self.stops else 1))
  elif address in (0x0c4fdcc8,0x0c4fdd68):r=0
  elif address==0x0c4c96f4:self.worker=args[1];self.pid=123 if self.kind=='source'else 42;r=self.pid
  elif address==0x0c4c96ac:r=self.pid
  elif address==0x0c4c5c44:r=1 if self.alive else 0
  elif self.kind=='source':
   if address==0x1c167c90:r=100
   elif address in (0x1c1681e8,0x1c165bf0,0x1c154d9c):r=0
   elif address==0x1c165b20:r=101
   elif address==0x1c03a188:assert self.cstring(args[0])==b'Capture';r=0x7777
   elif address==0x1c03a244:r=0
   elif address==0x1c03b2e0:
    action=self.cstring(args[2])
    if action==b'prepare':self.event(1)
    elif action==b'stop':self.stops+=1;self.running=False;self.paused=False;self.event(4)
    else:assert action==b'set_options',action
   elif address==0x1c03a50c:self.starts+=1;self.running=True;self.paused=False;self.event(2)
   elif address==0x1c03a52c:self.pauses+=1;self.paused=True;self.event(3)
   elif address==0x1c03a1e8:self.closed+=1
   elif address==0x1c1687a8:
    if self.stream_at>=len(self.stream):r=0 if self.stops and not self.missing_eof else -1
    elif self.paused or not self.running and not self.stops:r=-1
    else:
     # Deliberately odd packet boundaries exercise production carry handling.
     count=min(args[2],511,len(self.stream)-self.stream_at);u.mem_write(args[1],self.stream[self.stream_at:self.stream_at+count]);self.stream_at+=count;r=count
   else:raise AssertionError('Unexpected source API '+hex(address))
  else:
   if address==0x1c039bbc:assert self.cstring(args[0])==b'Music';r=0x8888
   elif address==0x1c039c78:r=0
   elif address==0x1c039cc4:
    path=self.cstring(args[1]);self.played=self.files[path][44:];assert self.played==self.pcm;self.event(1)
   elif address==0x1c039f50:self.starts+=1;self.media_start=self.flow.clock-self.position;self.running=True;self.paused=False;self.event(2)
   elif address==0x1c039fc0:self.pauses+=1;self.paused=True;self.event(3)
   elif address==0x1c039f78:self.stops+=1;self.running=False;self.event(4)
   elif address==0x1c039c1c:self.closed+=1;self.running=False
   elif address==0x1c03a07c:
    self.position=max(0,self.flow.clock-self.media_start);u.mem_write(args[1],struct.pack('<I',self.position))
    if self.position>=len(self.pcm)*1000//16000:self.completed=True;self.event(6)
   else:raise AssertionError('Unexpected player API '+hex(address))
  u.reg_write(UC_ARM_REG_R0,r&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))

class Flow:
 def __init__(self,test):
  self.test=test;self.clock=0;self.pcm=bytes((i*31+3)%256 for i in range(70000));self.lua=main.LuaRuntime(unpack_returned_tuples=True,encoding=None)
  self.lua.execute(main.BOOTSTRAP);self.h=self.lua.globals().host;self.files=LuaFiles(self.h);self.owners={};self.queue=[];self.schedule=None;self.phases=[]
  for name,value in {b'/etc/build.prop':b'ro.build.version=3.100.043\n',b'/proc/version':b'synthetic kernel\n',b'/proc/partitions':b'1 2 progmem\n',b'/dev/ap':b'AP!!',b'/proc/modules':b'system,0,0,0,0,0,0,0\n',b'/proc/fs/blocks':b'4096 10000 100 9900 /data\n'}.items():self.files[name]=value
  self.lua.globals().host_native_execute=self.execute
  self.lua.execute("local old=os.execute;os.execute=function(cmd)local result=host_native_execute(cmd);if result==false then return nil,'exit',1 end;return old(cmd)end")
  self.result=self.lua.execute(main.bundle_source(False))
 def core(self):return self.result[b'core'].state()
 def extra(self):return self.result[b'app'].view()[2]
 def act(self,name,id=None):
  result=self.result[b'app'].act(name.encode(),id);self.last_action=result;return result[0]if isinstance(result,tuple)else result
 def click(self,text):return self.h.click(text.encode())
 def execute(self,command):
  command=command.decode();module=command.rsplit(' ',1)[-1]
  if command.startswith('insmod ')and module in ('w6rc','w6rplay'):
   kind='source'if module=='w6rc'else'player';owner=NativeBoundary(self.test.artifacts[kind],self,kind)
   try:owner.initialize()
   except Exception as error:self.native_error=repr(error);raise
   self.owners[module]=owner;self.queue.append(owner)
  elif command.startswith('insmod ')and module=='w6rxlink':
   owner=transport.Host(*self.test.artifacts['phone']);owner.files=self.files;nonce=self.files[BASE+b'w6r-link-start.txt'][5:21];owner.u.mem_write(0x22e000,nonce+b'\0');owner.call('host_bind_nonce',0x22e000);self.owners[module]=owner
  elif command.startswith('rmmod ')and module in self.owners:
   owner=self.owners[module]
   if owner.call('host_unload')!=0:return False
  return True
 def step(self,ms=250):
  self.clock+=ms;self.h.advance(ms);phase=self.core()[b'phase'].decode()
  if not self.phases or self.phases[-1]!=phase:self.phases.append(phase)
  if self.schedule:self.schedule(self)
 def run_queued(self):
  while self.queue:
   owner=self.queue.pop(0);owner.run();self.step(1100)

class ProductWorkflow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  (ROOT/'build').mkdir(exist_ok=True)
  cls.temp=tempfile.TemporaryDirectory(prefix='w6r-product-flow-');cls.work=Path(cls.temp.name);n=ROOT/'native'
  cls.artifacts={
   'source':compile_arm(cls.work,'source',[ROOT/'tests/product_source_host.c',n/'spool.c',n/'p65-media.c',n/'p65-fs.c',n/'owner-runtime.c',n/'status.c']),
   'player':compile_arm(cls.work,'player',[ROOT/'tests/product_player_host.c']),
   'phone':compile_arm(cls.work,'phone',[n/'export-relay.c',n/'export-relay-fs.c',n/'export-relay-json.c'],transport.WRAPPER+PHONE_EXTRA)}
  phone=ROOT/'phone-app';config=json.loads((phone/'.local-build.json').read_text(encoding='utf-8-sig'))if(phone/'.local-build.json').is_file()else{}
  java=Path(os.environ.get('JAVA_HOME',config.get('java_home','')));jar=Path(os.environ.get('W6R_JSON_TEST_JAR',config.get('json_test_jar','')))
  if not jar.is_file():raise unittest.SkipTest('External authorized JSON-java test dependency is not configured')
  suffix='.exe'if os.name=='nt'else'';cls.java=java/('bin/java'+suffix);cls.cp=os.pathsep.join([str(cls.work),str(jar)])
  files=[phone/'src/com/watch6/recorder/ArchiveStore.java',phone/'src/com/watch6/recorder/Protocol.java',phone/'tests/ProtocolHarness.java']
  r=subprocess.run([str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-classpath',str(jar),'-d',str(cls.work),*map(str,files)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30);assert r.returncode==0,r.stderr
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def phone(self,request):
  r=subprocess.run([str(self.java),'-cp',self.cp,'com.watch6.recorder.ProtocolHarness',str(self.store)],input=json.dumps(request,separators=(',',':'))+'\n',capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30);self.assertEqual(r.returncode,0,r.stderr);return json.loads(r.stdout)
 def test_capture_pause_resume_save_full_play_stop_export_durable_restart(self):
  f=Flow(self);self.store=self.work/'phone-store';self.assertEqual(f.core()[b'phase'],b'idle');self.assertFalse(any(b'vs-mc-'in p or b'.wav'in p for p,_ in f.files.items()))
  self.assertTrue(f.click('开始录音'));record_id=f.core()[b'id'];capture=f.owners['w6rc'];stage=['recording'];pause_bytes=[]
  def recording(flow):
   phase=flow.core()[b'phase']
   if stage[0]=='recording'and phase==b'recording':self.assertTrue(flow.click('暂停录音'));stage[0]='pause'
   elif stage[0]=='pause'and phase==b'paused':pause_bytes.append(capture.stream_at);stage[0]='hold';self.pause_clock=flow.clock
   elif stage[0]=='hold'and flow.clock-self.pause_clock>=500:self.assertEqual(capture.stream_at,pause_bytes[0]);self.assertTrue(flow.click('继续录音'));stage[0]='resume'
   elif stage[0]=='resume'and phase==b'recording'and capture.stream_at==len(capture.stream):self.assertTrue(flow.click('结束并保存'));stage[0]='stopped'
  f.schedule=recording;f.run_queued();f.schedule=None;self.assertEqual(stage[0],'stopped');self.assertEqual(f.core()[b'phase'],b'saved');self.assertEqual(capture.starts,2);self.assertEqual(capture.pauses,1);self.assertEqual(capture.stops,1);self.assertEqual(capture.closed,1)
  rows=f.result[b'app'].view()[1];self.assertEqual(len(rows),1);self.assertEqual(rows[1][b'status'],b'saved');self.assertEqual(rows[1][b'bytes'],len(f.pcm));source={p:v for p,v in f.files.items()if b'vs-mc-'in p};self.assertEqual(b''.join(value for path,value in sorted(source.items())if path.endswith(b'.pcm')),f.pcm);self.assertEqual(len([p for p in source if p.endswith(b'.pcm')]),2)
  self.assertTrue(f.act('play',record_id),(f.last_action,getattr(f,'native_error',None)));f.run_queued();self.assertEqual(f.extra()[b'playback'][b'phase'],b'completed');full=f.owners['w6rplay'];self.assertTrue(full.completed);self.assertEqual(full.played,f.pcm);self.assertEqual(full.closed,1)
  # A second genuine playback is explicitly stopped; it must not be labelled
  # complete, and its native handle must close before an export can prepare.
  self.assertTrue(f.act('play',record_id));stopped=[False]
  def stop_play(flow):
   if not stopped[0]and flow.extra()[b'playback'][b'phase']==b'playing':self.assertTrue(flow.act('stop_playback'));stopped[0]=True
  f.schedule=stop_play;f.run_queued();f.schedule=None;self.assertTrue(stopped[0]);self.assertEqual(f.extra()[b'playback'][b'phase'],b'stopped');self.assertEqual(f.owners['w6rplay'].stops,1);self.assertEqual(f.owners['w6rplay'].closed,1)
  self.assertTrue(f.act('export',record_id));sender=f.owners['w6rxlink'];sender.tick(25);f.step(1100);self.assertIn(BASE+b'w6r-export-job.txt',f.files);job=f.files[BASE+b'w6r-export-job.txt'];self.assertEqual(job[24:40],record_id)
  actions=[];lost=False;stamp=50
  for _ in range(500):
   if sender.get(4)==4:break
   before=len(sender.sent);sender.tick(stamp);stamp+=25
   if len(sender.sent)==before:continue
   request=sender.wire();actions.append(request['action']);reply=self.phone(request);self.assertTrue(reply['ok'],reply);self.assertEqual(reply['durable'],reply['next']);frontier=sender.get(5);sender.complete()
   if request['action']=='recorder_chunk'and not lost:
    # Real ArchiveStore checkpoint committed, ACK dropped at the delivery edge.
    # Every next request starts a new JVM and reloads that same durable store.
    lost=True;self.assertEqual(sender.get(5),frontier);sender.call('host_event',3);sender.call('host_online');continue
   sender.receive(reply)
  self.assertEqual(sender.get(4),4,'Bounded end-to-end export did not finish');self.assertTrue(lost);self.assertEqual(sender.get(5),len(f.pcm));self.assertGreater(actions.count('recorder_offer'),1)
  files=list(self.store.rglob('*.wav'));self.assertEqual(len(files),1);exported=files[0].read_bytes();self.assertEqual(exported,transport.wav(f.pcm));self.assertEqual(reply['sha256'],hashlib.sha256(exported).hexdigest());self.assertEqual(sender.get(9),1)
  sender.tick(stamp);sender.call('host_finalize');f.step(300);self.assertEqual(f.extra()[b'transfer'][b'phase'],b'saved');self.assertTrue(f.extra()[b'transfer'][b'safe_to_release']);self.assertEqual({p:f.files[p]for p in source},source);self.assertTrue(f.result[b'app'].view()[1][1][b'phone_saved'])
  report=dict(passed=True,recording_bytes=len(f.pcm),extent_count=2,capture_phases=f.phases,capture_start_or_resume_calls=capture.starts,capture_pause_calls=capture.pauses,playback_complete=True,playback_explicit_stop=True,export_sha256=hashlib.sha256(exported).hexdigest(),lost_ack_resumed=True,jvm_store_reopened_per_packet=True,originals_unchanged=True,no_saved_catalog_or_source_or_wav_seed=True,
   native_phone_ready_injected=True,native_phone_ready_injection_functions=['test_phone_transport.WRAPPER.host_reset: ctx.ready=ctx.phone=1','test_phone_transport.WRAPPER.host_online: simulated SDK reconnect'],native_phone_setup_called=False,native_phone_initializer_or_uv_worker_executed=False,native_phone_exit_injected='host_finalize: ctx.done=ctx.loop_closed=1; w6e_worker_closed; snapshot',
   source_entry='production vs_p65_owner_initialize; outer native-source fingerprint guard excluded',player_entry='production watch6_player_initialize; guards() result injected',
   real_components=['bundled Lua main/app/UI/source/recorder/archive/playback/transfer/phone-link','ARM p65-owner worker/spool/p65-media/p65-fs/status','ARM player initializer/worker','ARM phone-link tick/callbacks/export-relay/fs/json','JVM Protocol/ArchiveStore'],synthetic_edges=['firmware fingerprint result','OS/task/clock/RAM filesystem and sync','Capture PCM/RPMSG/notifications','speaker RPC/position/complete notification (no decoder or speaker)','MiFitness link readiness/message delivery/SDK completion','Android directory fsync'],physical_verified=False,rpk_identity_verified=False,microphone_calls=0,speaker_calls=0,radio_calls=0)
  (ROOT/'build/product-workflow-test-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

 def test_missing_capture_eof_never_saves_plays_exports_or_unloads(self):
  f=Flow(self);self.assertTrue(f.click('开始录音'));record_id=f.core()[b'id'];capture=f.owners['w6rc'];capture.missing_eof=True;stopped=[False]
  def stop_after_pcm(flow):
   if not stopped[0]and flow.core()[b'phase']==b'recording'and capture.stream_at==len(capture.stream):self.assertTrue(flow.click('结束并保存'));stopped[0]=True
  f.schedule=stop_after_pcm;f.queue.clear();capture.run(retain=True);f.schedule=None;f.step(1100)
  self.assertTrue(stopped[0]);self.assertEqual(f.core()[b'phase'],b'recovery');self.assertTrue(capture.alive);self.assertEqual(capture.closed,0);self.assertEqual(capture.call('host_unload'),0xfffffff0)
  self.assertFalse(f.act('play',record_id));self.assertFalse(f.act('export',record_id));self.assertNotIn('w6rplay',f.owners);self.assertNotIn('w6rxlink',f.owners)
  rows=f.result[b'app'].view()[1];self.assertEqual(rows[1][b'status'],b'partial');self.assertFalse(rows[1][b'phone_saved']);self.assertFalse(any(path.endswith(b'.end')or path.endswith(b'.wav')for path,_ in f.files.items()));self.assertTrue(any(path.endswith(b'.pcm')for path,_ in f.files.items()))
  report=dict(passed=True,scope='actual source worker and bundled Lua reject a synthetic STOPPED-without-EOF capture boundary',native_worker_retained=True,pid_kept_live=True,media_closed=False,catalog_status='partial',play_rejected=True,export_rejected=True,unload_rejected=True,source_pcm_preserved=True,closed_ledger_created=False,synthetic_clock_accelerated_after_stop=True,physical_verified=False)
  (ROOT/'build/product-workflow-rejection-test-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
