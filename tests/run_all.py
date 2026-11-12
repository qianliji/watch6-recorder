"""Execute real Lua/Python and optional ARM native code with synthetic edges."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import arm_tools,configuration,prepare_python_dependencies,program
from tools.package_source import excluded_release_source

def discover_tests(directory,include_experimental=False):
 """Exclude retired transports before importing tests and their dependencies."""
 directory=Path(directory);suite=unittest.TestSuite();loader=unittest.TestLoader()
 for path in sorted(directory.glob('test_*.py')):
  if include_experimental or not excluded_release_source(Path('tests')/path.name):
   suite.addTests(loader.discover(str(directory),pattern=path.name))
 return suite
def native():
 from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
 from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
 tools=arm_tools();n=ROOT/'native'
 with tempfile.TemporaryDirectory(prefix='watch6-recorder-native-') as td:
  out=Path(td);(out/'host.ld').write_text('ENTRY(run_suite)\nSECTIONS { . = 0x10000; .text : { *(.text*) *(.rodata*) } . = ALIGN(8); .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }}')
  flags=['-mcpu=cortex-m3','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-DVS_HOST_IO=1','-I',str(n)]
  objects=[]
  for i,p in enumerate([ROOT/'tests/runtime_host.c',n/'spool.c',n/'p65-fs.c',n/'host_fs.c',n/'owner-runtime.c']):
   obj=out/f'{i}.o';r=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(p),'-o',str(obj)],capture_output=True,text=True);assert r.returncode==0,r.stderr;objects.append(obj)
  elf=out/'host.elf';subprocess.run([str(program(tools,'arm-none-eabi-ld')),'-T',str(out/'host.ld'),'-o',str(elf),*map(str,objects)],check=True,capture_output=True)
  raw=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',raw);ss=[struct.unpack_from('<10I',raw,h[6]+i*h[11]) for i in range(h[12])];syms={}
  for s in ss:
   if s[1]==2:
    st=ss[s[6]];names=raw[st[4]:st[4]+st[5]]
    for p in range(s[4],s[4]+s[5],16):
     at,v,size,_,_,idx=struct.unpack_from('<IIIBBH',raw,p)
     if at:syms[names[at:names.index(0,at)].decode()]=(v,size,idx)
  u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.mem_map(0x10000,0x200000);u.mem_map(0x300000,0x10000)
  for s in ss:
   if s[2]&2 and s[5] and s[1]!=8:u.mem_write(s[3],raw[s[4]:s[4]+s[5]])
  u.reg_write(UC_ARM_REG_SP,0x30fff8);u.reg_write(UC_ARM_REG_LR,0x300001);u.emu_start(syms['run_suite'][0]|1,0x300000,timeout=50000000,count=300000000)
  assert u.reg_read(UC_ARM_REG_PC)==0x300000,'Native owner did not exit within the bounded test budget'
  result={k:struct.unpack('<I',u.mem_read(syms['host_'+k][0],4))[0] for k in ['cases','assertions','failures']}
  assert result['cases']==23 and result['failures']==0,result
  return dict(passed=True,**result,scope='real spool, filesystem and local-archive owner runtime; synthetic ARM memory I/O')
def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--host-only',action='store_true');g.add_argument('--native',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--include-experimental',action='store_true',help='Also run historical direct-BLE tests; their historical phone sources/dependencies must be restored separately');args=p.parse_args()
 prepare_python_dependencies();c=configuration()
 if c.get('test_dependencies'):sys.path.insert(0,str(c['test_dependencies']))
 from lupa.lua54 import LuaRuntime
 lua=LuaRuntime(unpack_returned_tuples=True)
 factory=lambda n:lua.execute((ROOT/'src'/(n+'.lua')).read_text(encoding='utf-8'))
 for f in (ROOT/'src').glob('*.lua'):
  if args.include_experimental or not excluded_release_source(f.relative_to(ROOT)):lua.compile(f.read_text(encoding='utf-8'),name=f.name)
 data=lua.execute((ROOT/'tests/flow.lua').read_text(encoding='utf-8'))(factory('recorder'),factory('catalog'),factory('json'))
 flow={k:v for k,v in data.items()}
 ipc=lua.execute((ROOT/'tests/source_flow.lua').read_text(encoding='utf-8'))(factory('source'),factory('json'))
 ui=lua.execute((ROOT/'tests/ui_flow.lua').read_text(encoding='utf-8'))(factory('ui'))
 app=lua.execute((ROOT/'tests/app_flow.lua').read_text(encoding='utf-8'))(factory('app'))
 transfer=lua.execute((ROOT/'tests/transfer_flow.lua').read_text(encoding='utf-8'))(factory('transfer'))
 migration=lua.execute((ROOT/'tests/link_migration_flow.lua').read_text(encoding='utf-8'))(factory('link-migration')) if args.include_experimental else None
 suite=discover_tests(ROOT/'tests',args.include_experimental);result=unittest.TextTestRunner(verbosity=1).run(suite);assert result.wasSuccessful()
 report=dict(passed=True,transport='mifitness',experimental_tests_included=args.include_experimental,lua_flow=flow,lua_source_ipc={k:v for k,v in ipc.items()},lua_ui={k:v for k,v in ui.items()},lua_app_ordering={k:v for k,v in app.items()},lua_transfer={k:v for k,v in transfer.items()},lua_migration={k:v for k,v in migration.items()} if migration else dict(executed=False,reason='historical direct transport excluded'),python_cases=result.testsRun,python_skipped=len(result.skipped),native=native() if args.native else dict(executed=False,reason='--host-only requested'),
  microphone_calls=0,device_calls=0,network_calls=0,physical_verified=False)
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report))
if __name__=='__main__':main()
