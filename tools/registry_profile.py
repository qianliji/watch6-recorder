"""Pinned P65 one-shot module registry ABI. Emits hashes, never firmware bytes."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_settings import AP_SHA256,firmware_path,configuration,prepare_python_dependencies
AP_SHA=AP_SHA256

def offset(address):
 if not 0x0c0c0000<=address<0x0cc00000:raise ValueError('Address outside pinned P65 AP mapping')
 return address-0x0c0c0000

def fnv(data):
 value=2166136261
 for byte in data:value=((value^byte)*16777619)&0xffffffff
 return value
SPECS=[('module_insmod_locked_init',0x0c4c49ac,0x138),
 ('module_registry_lock_wrappers',0x0c4f9f70,0x20),('module_registry_foreach',0x0c4fa054,0x4c),
 ('recursive_mutex_lock',0x0c4f8b18,0x6c),('recursive_mutex_unlock',0x0c4f8b84,0x6c),
 ('module_current_pid',0x0c4c96ac,0x24),('module_record_formatter_layout',0x0c4c4c20,0x48),
 ('registry_open_veneer',0x0c8bef00,8),('registry_read_veneer',0x0c8beaf0,8),
 ('registry_write_veneer',0x0c8be040,8),('registry_close_veneer',0x0c8bdba8,8)]
def generate():
 ap=firmware_path('ap').read_bytes();assert hashlib.sha256(ap).hexdigest()==AP_SHA,'Unsupported AP'
 prepare_python_dependencies()
 if configuration().get('test_dependencies'):sys.path.insert(0,str(configuration()['test_dependencies']))
 from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_MCLASS
 cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS)
 def word(a):return struct.unpack_from('<I',ap,offset(a))[0]
 def op(a,name,args):return any(i.mnemonic==name and i.op_str==args for i in cs.disasm(ap[offset(a):offset(a)+4],a))
 checks=[]
 def check(name,value):assert value,name;checks.append(name)
 check('insmod_holds_outer_lock',op(0x0c4c49c4,'bl','#0xc4f9f70'))
 check('initializer_receives_unload_pair68',op(0x0c4c4aa6,'add.w','r0, r5, #0x68')and op(0x0c4c4aaa,'blx','r3'))
 check('registry_recursive_lock',op(0x0c4fa060,'bl','#0xc4f8b18')and word(0x0c4fa098)==0x3c3b9384)
 check('registry_list_head',word(0x0c4fa09c)==0x3c3d67c8)
 check('registry_callback_and_early_stop',op(0x0c4fa074,'blx','r8')and op(0x0c4fa07a,'beq','#0xc4fa06c'))
 check('registry_unlocks_after_callback',op(0x0c4fa07e,'bl','#0xc4f8b84')and op(0x0c4fa08c,'bl','#0xc4f8b84'))
 check('mutex_owner12',op(0x0c4f8b1c,'ldr','r4, [r0, #0xc]')and op(0x0c4f8b24,'cmp','r4, r0'))
 check('mutex_recursive_depth16',op(0x0c4f8b2a,'ldr','r3, [r5, #0x10]')and op(0x0c4f8b32,'str','r3, [r5, #0x10]'))
 check('mutex_unlock_decrements_depth',op(0x0c4f8b86,'ldr','r2, [r0, #0x10]')and op(0x0c4f8b90,'str','r4, [r0, #0x10]'))
 check('record_name4',op(0x0c4c4c48,'adds','r3, r0, #4'))
 check('record_entry64',op(0x0c4c4c3e,'ldr','r1, [r0, #0x64]'))
 windows=[]
 for name,address,count in SPECS:
  raw=ap[offset(address):offset(address)+count];assert len(raw)==count
  windows.append(dict(id=name,address=address,offset=offset(address),count=count,fnv=fnv(raw),sha256=hashlib.sha256(raw).hexdigest()))
 report=dict(reference_ap_sha256=AP_SHA,firmware='P65 3.100.043',windows=windows,static_assertions=checks,
  device_accessed=False,physical_verified=False,retained_callbacks=False,spawns_task=False,executes_module_entry=False,
  exact_names=['w6rc','w6rplay','w6rplayer','w6rxlink','w6rdirect'],max_modules=128,
  provenance='Same pinned loader/registry/recursive-lock ABI previously verified by VoiceSpace GUI attacher; only names are inspected')
 (ROOT/'adapters/registry-guards.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 (ROOT/'native/registry-profile.h').write_text('/* Generated exact P65 guards; no firmware instructions copied. */\nstatic const struct w6rq_guard registry_guards[] = {\n'+''.join('{0x%08xu,%uu,0x%08xu},\n'%(w['address'],w['count'],w['fnv'])for w in windows)+'};\n',encoding='utf-8')
 return report
if __name__=='__main__':
 r=generate();print(json.dumps(dict(guard_windows=len(r['windows']),static_assertions=len(r['static_assertions']),physical_verified=False)))
