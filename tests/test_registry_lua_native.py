"""Real Lua request -> actual ARM helper -> real Lua parser, without device IO."""
from pathlib import Path
import json,struct,subprocess,sys,tempfile,unittest,zlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import arm_tools,configuration,prepare_python_dependencies,program,lua_runtime
prepare_python_dependencies()
if configuration().get('test_dependencies'):sys.path.insert(0,str(configuration()['test_dependencies']))
BASE='/data/watch6recorder/'
REQUEST=BASE+'w6r-registry-request.txt'
STATUS=BASE+'w6r-registry-status.txt'
OWNERS=['w6rc','w6rplay','w6rplayer','w6rxlink','w6rdirect']

class ArmHelper:
 def __init__(self,directory):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
  from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0
  self.sp,self.lr,self.pc,self.r0=UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0
  tools=arm_tools();out=Path(directory);ld=out/'test.ld'
  ld.write_text('ENTRY(host_exchange_run)\nSECTIONS { . = 0x10000; .text : { *(.text*) *(.rodata*) } . = 0x3c100000; .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }}')
  flags=['-mcpu=cortex-m33','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(ROOT/'native')]
  obj=out/'test.o';result=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(ROOT/'tests/registry_query_host.c'),'-o',str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace')
  if result.returncode:raise AssertionError(result.stderr)
  elf=out/'test.elf';result=subprocess.run([str(program(tools,'arm-none-eabi-ld')),'-T',str(ld),'-o',str(elf),str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace')
  if result.returncode:raise AssertionError(result.stderr)
  raw=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',raw);sections=[struct.unpack_from('<10I',raw,h[6]+i*h[11])for i in range(h[12])];self.symbols={}
  for section in sections:
   if section[1]==2:
    names_section=sections[section[6]];names=raw[names_section[4]:names_section[4]+names_section[5]]
    for at in range(section[4],section[4]+section[5],16):
     name,value,_,_,_,_=struct.unpack_from('<IIIBBH',raw,at)
     if name:self.symbols[names[name:names.index(0,name)].decode()]=value
  self.cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);self.cpu.mem_map(0x10000,0x100000);self.cpu.mem_map(0x20000000,0x20000);self.cpu.mem_map(0x3c100000,0x100000)
  for section in sections:
   if section[2]&2 and section[5] and section[1]!=8:self.cpu.mem_write(section[3],raw[section[4]:section[4]+section[5]])
 def call(self,name,argument=0):
  self.cpu.reg_write(self.sp,0x2001fff8);self.cpu.reg_write(self.lr,0x100001);self.cpu.reg_write(self.r0,argument)
  self.cpu.emu_start(self.symbols[name]|1,0x100000,timeout=10000000,count=20000000)
  if self.cpu.reg_read(self.pc)!=0x100000:raise AssertionError('ARM helper did not return')
  return self.cpu.reg_read(self.r0)&0xffffffff
 def failures(self):return struct.unpack('<I',self.cpu.mem_read(self.symbols['host_failures'],4))[0]
 def exchange(self,request,mask):
  self.call('host_exchange_setup',mask);at=self.call('host_exchange_input');self.cpu.mem_write(at,request)
  records_at=self.call('host_exchange_records');record_size=self.call('host_exchange_records_size');before=bytes(self.cpu.mem_read(records_at,record_size))
  result=self.call('host_exchange_run');size=self.call('host_exchange_output_size');output=bytes(self.cpu.mem_read(self.call('host_exchange_output'),size))
  if before!=bytes(self.cpu.mem_read(records_at,record_size)):raise AssertionError('query mutated owner records')
  if self.failures():raise AssertionError('unexpected OS boundary, module entry or retained callback')
  return result,output

class RegistryLuaNative(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temporary=tempfile.TemporaryDirectory(prefix='w6r-registry-lua-arm-');cls.machine=ArmHelper(cls.temporary.name)
 @classmethod
 def tearDownClass(cls):cls.temporary.cleanup()
 def setup_facade(self,mask=0,tamper=None):
  self.files={};self.events=[];self.native_calls=0;self.mask=mask;self.tamper=tamper;self.next_nonce=0
  def read(name,n):
   self.events.append(('read',name));data=self.files.get(name)
   return data[:n].decode('ascii')if data is not None else None
  def write(name,text):
   self.events.append(('write',name));self.assertIn(name,[REQUEST,STATUS]);self.files[name]=text.encode('ascii');return True
  def execute(command):
   self.events.append(('execute',command))
   if command=='rmmod w6rqry':return True
   self.assertEqual(command,'insmod '+BASE+'registry-query.elf w6rqry');request=self.files[REQUEST];self.assertEqual(len(request),128)
   if self.tamper=='request_crc':
    first=bytearray(request[:64]);first[32]=ord('0')if first[32]!=ord('0')else ord('1');request=bytes(first)*2
   result,response=self.machine.exchange(request,self.mask);self.native_calls+=1
   if response:
    if self.tamper in ['nonce','response_crc']:
     first=bytearray(response[:128])
     if self.tamper=='nonce':
      first[6]=ord('f')if first[6]!=ord('f')else ord('e');first[95:103]=f'{zlib.crc32(first[:95])&0xffffffff:08x}'.encode()
     else:first[84]=ord('0')if first[84]!=ord('0')else ord('1')
     response=bytes(first)*2
    self.files[STATUS]=response
   return result==0
  def nonce():self.next_nonce+=1;return f'{self.next_nonce:016x}'
  self.lua=lua_runtime()();create=self.lua.execute((ROOT/'src/registry.lua').read_text(encoding='utf-8'))
  self.facade=create(self.lua.table_from(dict(read=read,write=write,execute=execute,nonce=nonce,asset='registry-query.elf')))
 def assert_only_query_io(self):
  for kind,value in self.events:
   if kind in ['read','write']:self.assertIn(value,[REQUEST,STATUS])
   else:self.assertIn(value,['insmod '+BASE+'registry-query.elf w6rqry','rmmod w6rqry'])
 def test_empty_registry_is_false_and_cached(self):
  self.setup_facade();self.assertIsNone(self.facade.present('w6rdirect'));self.assertEqual(self.native_calls,0)
  self.assertTrue(self.facade.refresh())
  for owner in OWNERS:self.assertIs(self.facade.present(owner),False)
  self.assertIsNone(self.facade.present('unrecognized-owner'));self.assertEqual(self.native_calls,1);self.assert_only_query_io()
 def test_direct_present_with_real_helper(self):
  self.setup_facade(mask=1<<4);self.assertTrue(self.facade.refresh());self.assertIs(self.facade.present('w6rdirect'),True)
  for owner in OWNERS[:-1]:self.assertIs(self.facade.present(owner),False)
  self.assert_only_query_io()
 def test_each_exact_owner_and_invalidation(self):
  for index,owner in enumerate(OWNERS):
   with self.subTest(owner=owner):
    self.setup_facade(mask=1<<index);self.assertTrue(self.facade.refresh());self.assertIs(self.facade.present(owner),True)
    self.mask=0;self.facade.invalidate();self.assertIs(self.facade.present(owner),False);self.assertEqual(self.native_calls,2);self.assert_only_query_io()
 def test_nonce_rejected_even_with_valid_crc(self):
  self.setup_facade(mask=1<<4,tamper='nonce');self.assertIs(self.facade.refresh()[0],False);self.assertIsNone(self.facade.present('w6rdirect'));self.assertEqual(self.native_calls,1);self.assert_only_query_io()
 def test_response_crc_rejected(self):
  self.setup_facade(mask=1<<4,tamper='response_crc');self.assertIs(self.facade.refresh()[0],False);self.assertIsNone(self.facade.present('w6rdirect'));self.assertEqual(self.native_calls,1);self.assert_only_query_io()
 def test_request_crc_rejected_by_actual_arm_helper(self):
  self.setup_facade(tamper='request_crc');self.assertIs(self.facade.refresh()[0],False);self.assertIsNone(self.facade.present('w6rc'));self.assertEqual(self.machine.call('host_exchange_iterator_calls'),0);self.assert_only_query_io()
if __name__=='__main__':unittest.main()
