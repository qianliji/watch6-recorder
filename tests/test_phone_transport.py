"""Real ARM transport/export code with synthetic files and SDK callbacks.

No commercial firmware executes. No device, microphone or network calls occur.
"""
from pathlib import Path
import base64,binascii,json,struct,subprocess,sys,tempfile,unittest,zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_settings import arm_tools,configuration,prepare_python_dependencies,program
prepare_python_dependencies()
if configuration().get('test_dependencies'):sys.path.insert(0,str(configuration()['test_dependencies']))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3

BASE=b'/data/watch6recorder/'
NONCE='0011223344556677'
RECORD='0123456789abcdef'
CACHE='fedcba9876543210'
STORAGE='00112233-4455-4677-8899-aabbccddeeff'
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
WRAPPER=r'''
#include "phone-link.c"
static uint8_t host_node[0x100];
void host_reset(void){memory_zero(&ctx,sizeof(ctx));memory_zero(host_node,sizeof(host_node));
 copy(ctx.nonce,"0011223344556677",16);ctx.phase="connected";ctx.ready=ctx.phone=ctx.released=1;
 ctx.pid=321;ctx.spawn_attempted=1;ctx.conn.node=host_node;ctx.link_attempted=ctx.timer_initialized=1;ctx.tick_ms=25;
 struct w6e_io io;w6e_fs_init(&export_fs,ctx.nonce);w6e_fs_ops(&export_fs,&io);io.send=export_send;w6e_init(&exporter,&io,ctx.nonce,321);w6e_transport(&exporter,1,1,0);}
void host_tick(uint32_t stamp){*(uint32_t *)(void *)(ctx.loop.bytes+0x180)=stamp;tick(0);}
void host_receive(const char *s,uint32_t n){struct uv_message m;memory_zero(&m,sizeof(m));m.type=0x83;m.len=n;m.payload=(void *)s;received(&ctx.conn,0,&m,0);}
void host_event(uint32_t event){struct uv_message m;memory_zero(&m,sizeof(m));m.type=2;m.len=4;m.payload=&event;received(&ctx.conn,0,&m,0);}
void host_online(void){ctx.recovering=0;ctx.link_closed=0;ctx.conn.node=host_node;ctx.ready=ctx.phone=1;ctx.phase="connected";w6e_transport(&exporter,1,1,relay_now());}
uint32_t host_get(uint32_t k){switch(k){case 0:return ctx.tx_ack;case 1:return ctx.tx_pending;case 2:return ctx.closing;case 3:return (uint32_t)ctx.error;case 4:return exporter.phase;case 5:return exporter.next;case 6:return (uint32_t)exporter.code;case 7:return ctx.recovering;case 8:return exporter.status.worker_done;case 9:return exporter.status.source_closed;case 10:return export_fs.fd>=0;default:return 0;}}
void host_close(void){w6e_cancel(&exporter);begin_close(0);}
int32_t host_unload(void){ctx.done=ctx.loop_closed=1;return uninitialize(&ctx);}
void host_worker_closed(void){w6e_worker_closed(&exporter);}
void host_doubleclose(void){*(uint32_t *)(void *)(host_node+0x74)=1;begin_close(0);}
'''

def ipc(seq=0,payload=b''):
 h=f'VSL1 {NONCE} {seq:08x} {len(payload):04x}\n'.encode().ljust(64,b' ')
 return h+payload+h

def job(total,rate=8000,crc='12345678',sequence=1):
 b=(f'W6RE1\n{NONCE}\n {RECORD}{rate:08x}{total:08x}abcdef0123456789{crc}{CACHE}{sequence:08x}00000001').encode().ljust(464,b' ')+f'{sequence:08x}'.encode()
 b+=f'{zlib.crc32(b):08x}{NONCE}\nend=W6RE1\n'.encode()
 return b.ljust(512,b' ')

def wav(pcm,rate=8000):return struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',len(pcm)+36,b'WAVE',b'fmt ',16,1,1,rate,rate*2,2,16,b'data',len(pcm))+pcm

class Host:
 def __init__(self,raw,sections,syms):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);self.syms=syms
  for addr,size in [(0x10000,0x200000),(0x220000,0x10000),(0x300000,0x10000),(0x0c000000,0x1000000)]:self.u.mem_map(addr,size)
  for s in sections:
   if s[2]&2 and s[5] and s[1]!=8:self.u.mem_write(s[3],raw[s[4]:s[4]+s[5]])
  self.u.hook_add(UC_HOOK_CODE,self.hook,begin=0x0c000000,end=0x0cffffff)
  self.files={};self.fds={};self.nextfd=10;self.sent=[];self.closes=0;self.pid_present=False;self.fail_source_close=False
  self.call('host_reset')
 def cstring(self,address):
  b=bytearray()
  for i in range(256):
   c=bytes(self.u.mem_read(address+i,1))
   if c==b'\0':return bytes(b)
   b+=c
  raise AssertionError('unbounded path')
 def hook(self,u,address,size,data):
  r=[u.reg_read(x) for x in REGS];result=0
  if address==0x0c8bef00:
   path=self.cstring(r[0]);mode=r[1]
   if mode==1 and path not in self.files:result=-1
   else:fd=self.nextfd;self.nextfd+=1;self.fds[fd]=[path,0,mode];result=fd
  elif address==0x0c8beaf0:
   path,pos,_=self.fds[r[0]];value=self.files.get(path,b'')[pos:pos+r[2]]
   if value:u.mem_write(r[1],value)
   self.fds[r[0]][1]+=len(value);result=len(value)
  elif address==0x0c8be040:
   path,pos,_=self.fds[r[0]];value=bytes(u.mem_read(r[1],r[2]));old=self.files.get(path,b'')
   self.files[path]=old[:pos]+value+old[pos+len(value):];self.fds[r[0]][1]+=len(value);result=len(value)
  elif address==0x0c8bdba8:
   state=self.fds.pop(r[0],None)
   if self.fail_source_close and state and b'w6r-play-' in state[0]:result=-5
  elif address==0x0c62de64:
   msg=bytes(u.mem_read(r[2],20));length=struct.unpack_from('<I',msg,4)[0];payload=struct.unpack_from('<I',msg,16)[0]
   arg=struct.unpack('<I',u.mem_read(u.reg_read(UC_ARM_REG_SP),4))[0]
   copied=0x220000+len(self.sent)*32;u.mem_write(copied,msg)
   self.sent.append(dict(conn=r[0],msg=copied,callback=r[3],arg=arg,payload=payload,length=length,original=bytes(u.mem_read(payload,length)),done=False))
  elif address==0x0c62df50:self.closes+=1
  elif address==0x0c4c5c44:result=1 if self.pid_present else 0
  elif address in (0x0c621f98,0x0c629fb4):pass
  else:raise AssertionError('Unexpected fixed API '+hex(address))
  u.reg_write(UC_ARM_REG_R0,result&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def call_addr(self,address,*args):
  self.u.reg_write(UC_ARM_REG_SP,0x30fff8);self.u.reg_write(UC_ARM_REG_LR,0x300001)
  for reg,value in zip(REGS,args):self.u.reg_write(reg,value&0xffffffff)
  self.u.emu_start(address|1,0x300000,count=5000000)
  assert self.u.reg_read(UC_ARM_REG_PC)==0x300000,'ARM routine did not return'
  return self.u.reg_read(UC_ARM_REG_R0)
 def call(self,name,*args):return self.call_addr(self.syms[name][0],*args)
 def get(self,k):return self.call('host_get',k)
 def tick(self,stamp):self.call('host_tick',stamp)
 def setup(self,n=5000):
  self.pcm=bytes(i%251 for i in range(n));self.files[BASE+b'w6r-export-job.txt']=job(n,crc=f'{zlib.crc32(self.pcm):08x}')
  self.files[BASE+b'w6r-play-'+CACHE.encode()+b'.wav']=wav(self.pcm)
 def wire(self,index=-1):return json.loads(self.sent[index]['original'])
 def complete(self,index=-1,result=0):
  q=self.sent[index];self.call_addr(q['callback'],q['conn'],result,q['msg'],q['arg']);q['done']=True
 def receive(self,data):
  raw=json.dumps(data,separators=(',',':')).encode();self.u.mem_write(0x22e000,raw);self.call('host_receive',0x22e000,len(raw))
 def ack(self,offset,phase='receiving',complete=False,**kwargs):
  q=self.wire();d=dict(protocol='w6r1',type='recorder_ack',request_id=q['id'],recording_id=RECORD,ok=True,phase=phase,next=offset,durable=offset,complete=complete,storage_id=STORAGE);d.update(kwargs);self.receive(d)
 def unchanged(self):return all(q['done'] or bytes(self.u.mem_read(q['payload'],q['length']))==q['original'] for q in self.sent)

class TransportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='w6r-export-arm-');w=Path(cls.temp.name);tools=arm_tools();n=ROOT/'native'
  (w/'host.c').write_text(WRAPPER);(w/'host.ld').write_text('ENTRY(host_reset)\nSECTIONS {. = 0x10000; .text : { *(.text*) *(.rodata*) } . = ALIGN(8); .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }}')
  flags=['-mcpu=cortex-m3','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(n)]
  objects=[]
  for i,p in enumerate([w/'host.c',n/'export-relay.c',n/'export-relay-fs.c',n/'export-relay-json.c']):
   obj=w/f'{i}.o';r=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(p),'-o',str(obj)],capture_output=True,text=True,encoding="utf-8",errors="replace");assert r.returncode==0,r.stderr;objects.append(obj)
  elf=w/'host.elf';r=subprocess.run([str(program(tools,'arm-none-eabi-ld')),'-T',str(w/'host.ld'),'-o',str(elf),*map(str,objects)],capture_output=True,text=True,encoding="utf-8",errors="replace");assert r.returncode==0,r.stderr
  cls.raw=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',cls.raw);cls.sections=[struct.unpack_from('<10I',cls.raw,h[6]+i*h[11])for i in range(h[12])];cls.syms={}
  for s in cls.sections:
   if s[1]==2:
    st=cls.sections[s[6]];names=cls.raw[st[4]:st[4]+st[5]]
    for p in range(s[4],s[4]+s[5],16):
     at,v,size,_,_,idx=struct.unpack_from('<IIIBBH',cls.raw,p)
     if at:cls.syms[names[at:names.index(0,at)].decode()]=(v,size,idx)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def setUp(self):self.h=Host(self.raw,self.sections,self.syms)
 def offer(self,n=5000):
  h=self.h;h.setup(n);h.tick(25);self.assertEqual(h.wire()['action'],'recorder_offer');h.complete();h.ack(0,'ready');return h
 def test_complete_durable_export(self):
  h=self.offer();received=b'';stamp=50
  while len(received)<len(h.pcm):
   h.tick(stamp);q=h.wire();self.assertEqual(q['action'],'recorder_chunk');chunk=base64.b64decode(q['data'],validate=True);self.assertLessEqual(len(chunk),2048);self.assertEqual(q['crc32'],f'{zlib.crc32(chunk):08x}');self.assertEqual(q['offset'],len(received));self.assertEqual(h.get(5),len(received),'SDK acceptance is not a durable ACK')
   # Receipt may beat SDK completion; borrowed bytes remain immutable.
   received+=chunk;h.ack(len(received));h.tick(stamp+1);self.assertTrue(h.unchanged());h.complete();stamp+=25
  h.tick(stamp);self.assertEqual(h.wire()['action'],'recorder_finish');h.ack(len(received),'saved',True);self.assertEqual(h.get(4),4);self.assertEqual(h.get(9),1);h.tick(stamp+1);self.assertEqual(h.get(2),1);self.assertEqual(h.call('host_unload'),0xfffffff0,'Pending SDK callback forbids unloading');h.complete();h.call('host_worker_closed');self.assertEqual(h.call('host_unload'),0);self.assertEqual(received,h.pcm);self.assertIn(BASE+b'w6r-play-'+CACHE.encode()+b'.wav',h.files)
 def test_gui_sleep_does_not_expire_export(self):
  h=self.offer();h.tick(9000);self.assertEqual(h.get(2),0);self.assertEqual(h.get(4),2);self.assertEqual(h.get(5),0)
 def test_only_exact_durable_ack_advances(self):
  h=self.offer();h.tick(50);h.complete();h.ack(2048,request_id='wrong');self.assertEqual(h.get(5),0);self.assertEqual(h.get(4),2);h.ack(2048,durable=False);self.assertEqual(h.get(4),6);self.assertEqual(h.get(5),0)
 def test_gap_and_storage_change_fail_closed(self):
  h=self.offer();h.tick(50);h.complete();h.ack(4096);self.assertEqual(h.get(4),6);self.assertEqual(h.get(5),0)
  self.setUp();h=self.offer();h.tick(50);h.complete();h.ack(2048,storage_id='ffffffff-ffff-4fff-8fff-ffffffffffff');self.assertEqual(h.get(4),6)
 def test_disconnect_reoffers_phone_durable_frontier(self):
  h=self.offer(60000);h.tick(50);h.complete();h.call('host_event',3);self.assertEqual(h.get(7),1);self.assertEqual(h.get(2),0);h.call('host_online');h.tick(75);self.assertEqual(h.wire()['action'],'recorder_offer');h.complete();h.ack(40000,'receiving');self.assertEqual(h.get(5),40000)
  # No lseek guess: at most16KiB prefix work per tick, eventual exact chunk.
  sent=len(h.sent)
  for stamp in (100,125,150,175):h.tick(stamp)
  self.assertGreater(len(h.sent),sent);q=h.wire();self.assertEqual(q['offset'],40000);self.assertEqual(base64.b64decode(q['data']),h.pcm[40000:42048])
 def test_ack_timeout_reoffer_without_duplicate_advance(self):
  h=self.offer();h.tick(50);h.complete();h.tick(8051);self.assertEqual(h.wire()['action'],'recorder_offer');self.assertEqual(h.get(5),0);h.complete();h.ack(2048,'receiving');h.tick(8075);self.assertEqual(h.wire()['offset'],2048)
 def test_corrupt_wav_and_extra_tail_rejected(self):
  h=self.offer(100);path=BASE+b'w6r-play-'+CACHE.encode()+b'.wav';h.files[path]=b'BAD!'+h.files[path][4:];h.tick(50);self.assertEqual(h.get(4),6);self.assertEqual(len(h.sent),1)
  self.setUp();h=self.offer(100);h.files[path]+=b'x';h.tick(50);self.assertEqual(h.get(4),6)
 def test_explicit_cancel_closes_file_keeps_original(self):
  h=self.offer();h.tick(50);h.complete();self.assertEqual(h.get(10),1);h.files[BASE+b'w6r-export-cancel.txt']=ipc(1);h.tick(75);self.assertEqual(h.get(4),5);self.assertEqual(h.get(10),0);self.assertEqual(h.get(9),1);self.assertEqual(h.get(2),1);self.assertEqual(h.get(5),0)
 def test_invalid_job_crc_or_nonce_never_authorizes_background(self):
  h=self.h;h.setup();raw=h.files[BASE+b'w6r-export-job.txt'];h.files[BASE+b'w6r-export-job.txt']=raw[:72]+b'00000000'+raw[80:];h.tick(25);self.assertEqual(h.get(4),0);self.assertEqual(len(h.sent),0)
 def test_close_failure_never_proves_source_released(self):
  h=self.offer();h.tick(50);h.complete();h.fail_source_close=True;h.files[BASE+b'w6r-export-cancel.txt']=ipc(1);h.tick(75);self.assertEqual(h.get(9),0);self.assertEqual(h.get(4),6);h.call('host_worker_closed');self.assertEqual(h.get(9),0);self.assertEqual(h.call('host_unload'),0xfffffff0)
 def test_uv_double_close_and_pid_guard(self):
  h=self.h;h.call('host_doubleclose');self.assertEqual(h.closes,0,'Already closing SDK pipe must not be closed twice');h.pid_present=True;self.assertEqual(h.call('host_unload'),0xfffffff0);h.pid_present=False;self.assertEqual(h.call('host_unload'),0)

if __name__=='__main__':unittest.main(verbosity=2)
