"""Execute actual registry-query C on ARM; no device or firmware code executes."""
from pathlib import Path
import json,struct,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import arm_tools,configuration,prepare_python_dependencies,program
prepare_python_dependencies()
if configuration().get('test_dependencies'):sys.path.insert(0,str(configuration()['test_dependencies']))
class RegistryQueryNative(unittest.TestCase):
 def test_actual_one_shot_helper(self):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
  from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
  tools=arm_tools()
  with tempfile.TemporaryDirectory(prefix='w6r-registry-test-')as directory:
   out=Path(directory);ld=out/'test.ld'
   ld.write_text('ENTRY(host_registry_suite)\nSECTIONS { . = 0x10000; .text : { *(.text*) *(.rodata*) } . = 0x3c100000; .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }}')
   flags=['-mcpu=cortex-m33','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(ROOT/'native')]
   obj=out/'test.o';result=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(ROOT/'tests/registry_query_host.c'),'-o',str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace');self.assertEqual(result.returncode,0,result.stderr)
   elf=out/'test.elf';result=subprocess.run([str(program(tools,'arm-none-eabi-ld')),'--gc-sections','-T',str(ld),'-o',str(elf),str(obj)],capture_output=True,text=True,encoding='utf-8',errors='replace');self.assertEqual(result.returncode,0,result.stderr)
   raw=elf.read_bytes();header=struct.unpack_from('<16sHHIIIIIHHHHHH',raw);sections=[struct.unpack_from('<10I',raw,header[6]+i*header[11])for i in range(header[12])];symbols={}
   for section in sections:
    if section[1]==2:
     names_section=sections[section[6]];names=raw[names_section[4]:names_section[4]+names_section[5]]
     for at in range(section[4],section[4]+section[5],16):
      name,value,size,_,_,index=struct.unpack_from('<IIIBBH',raw,at)
      if name:symbols[names[name:names.index(0,name)].decode()]=(value,size,index)
   cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);cpu.mem_map(0x10000,0x100000);cpu.mem_map(0x20000000,0x20000);cpu.mem_map(0x3c100000,0x100000)
   for section in sections:
    if section[2]&2 and section[5] and section[1]!=8:cpu.mem_write(section[3],raw[section[4]:section[4]+section[5]])
   cpu.reg_write(UC_ARM_REG_SP,0x2001fff8);cpu.reg_write(UC_ARM_REG_LR,0x100001)
   cpu.emu_start(symbols['host_registry_suite'][0]|1,0x100000,timeout=50000000,count=200000000)
   self.assertEqual(cpu.reg_read(UC_ARM_REG_PC),0x100000,'bounded registry suite did not finish')
   result={name:struct.unpack('<I',cpu.mem_read(symbols['host_'+name][0],4))[0]for name in ['cases','assertions','failures']}
   self.assertEqual(result['cases'],22,result);self.assertEqual(result['failures'],0,result)
   production=out/'production.o';compiled=subprocess.run([str(program(tools,'arm-none-eabi-gcc')),*flags,'-c',str(ROOT/'native/registry-query.c'),'-o',str(production)],capture_output=True,text=True,encoding='utf-8',errors='replace');self.assertEqual(compiled.returncode,0,compiled.stderr)
   undefined=subprocess.run([str(program(tools,'arm-none-eabi-nm')),'-u',str(production)],capture_output=True,text=True,encoding='utf-8');self.assertEqual(undefined.returncode,0,undefined.stderr);self.assertEqual(undefined.stdout.strip(),'')
   (ROOT/'build').mkdir(exist_ok=True);(ROOT/'build/registry-query-native-test-report.json').write_text(json.dumps(dict(result,passed=True,production_werror=True,undefined_imports=0,real_helper=True,device_calls=0,firmware_execution=False,physical_verified=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
