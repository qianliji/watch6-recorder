"""Actual Cortex-M3 archive/player C with RAM-only filesystem/media boundary."""
from pathlib import Path
import json,struct,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import arm_tools,configuration,prepare_python_dependencies,program
prepare_python_dependencies()
if configuration().get('test_dependencies'):sys.path.insert(0,str(configuration()['test_dependencies']))
class PlaybackNative(unittest.TestCase):
 def test_arm_archive_and_player(self):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
  from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
  tools=arm_tools()
  with tempfile.TemporaryDirectory(prefix='w6r-playback-test-')as directory:
   out=Path(directory);ld=out/'test.ld';ld.write_text('ENTRY(run_suite)\nSECTIONS { . = 0x10000; .text : { *(.text*) *(.rodata*) } . = ALIGN(8); .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }}')
   flags=['-mcpu=cortex-m3','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(ROOT/'native')]
   obj=out/'test.o';r=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(ROOT/'tests/playback_host.c'),'-o',str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace');self.assertEqual(r.returncode,0,r.stderr)
   elf=out/'test.elf';r=subprocess.run([str(program(tools,'arm-none-eabi-ld')),'--gc-sections','-T',str(ld),'-o',str(elf),str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace');self.assertEqual(r.returncode,0,r.stderr)
   raw=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',raw);sections=[struct.unpack_from('<10I',raw,h[6]+i*h[11])for i in range(h[12])];symbols={}
   for section in sections:
    if section[1]==2:
     names_sec=sections[section[6]];names=raw[names_sec[4]:names_sec[4]+names_sec[5]]
     for p in range(section[4],section[4]+section[5],16):
      at,value,size,_,_,idx=struct.unpack_from('<IIIBBH',raw,p)
      if at:symbols[names[at:names.index(0,at)].decode()]=(value,size,idx)
   u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.mem_map(0x10000,0x1000000);u.mem_map(0x2000000,0x10000)
   for section in sections:
    if section[2]&2 and section[5] and section[1]!=8:u.mem_write(section[3],raw[section[4]:section[4]+section[5]])
   u.reg_write(UC_ARM_REG_SP,0x200fff8);u.reg_write(UC_ARM_REG_LR,0x2000001)
   u.emu_start(symbols['run_suite'][0]|1,0x2000000,timeout=50000000,count=400000000)
   self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x2000000,'bounded C suite did not finish')
   result={k:struct.unpack('<I',u.mem_read(symbols['host_'+k][0],4))[0]for k in ['cases','assertions','failures','line','permission_mode','permission_result']}
   if result['permission_result']>=0x80000000:result['permission_result']-=0x100000000
   self.assertEqual(result['cases'],22,result);self.assertEqual(result['failures'],0,result)
   (ROOT/'build').mkdir(exist_ok=True);(ROOT/'build/playback-native-test-report.json').write_text(json.dumps(dict(result,passed=True,device_calls=0,firmware_execution=False,physical_verified=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
