"""Actual bundled Lua main/app/UI with a controlled LVGL/files/native boundary.

No firmware, microphone or device call executes. Guards use synthetic bytes;
mailboxes are the real production serializers and parsers, not stubbed owners.
"""
from pathlib import Path
import ast,importlib.util,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import prepare_python_dependencies
prepare_python_dependencies()
from lupa.lua54 import LuaRuntime

BASE='/data/watch6recorder/'
RECORD='1234567890abcdef'
BOOTSTRAP=r"""
host={files={},events={},nodes={},timers={},clock=0,native_modules={}}
local H=host
function H.event(kind,path,value)H.events[#H.events+1]={kind=kind,path=path,value=value}end
local Node={};Node.__index=Node
function Node:set(props)for k,v in pairs(props)do self.props[k]=v end end
function Node:add_flag(flag)self.flags[flag]=true end
function Node:clear_flag(flag)self.flags[flag]=nil end
function Node:onClicked(cb)self.click=cb end
function Node:onevent(event,cb)self.events[event]=cb end
function Node:delete()if self.events.DELETE then self.events.DELETE()end end
local function node(parent,props)local n=setmetatable({parent=parent,props=props or {},flags={},events={}},Node);H.nodes[#H.nodes+1]=n;return n end
package.preload.lvgl=function()return {
 Object=node,Label=node,Font=function(name,size)return {name=name,size=size}end,
 FLAG={HIDDEN='HIDDEN',CLICKABLE='CLICKABLE',SCROLLABLE='SCROLLABLE',EVENT_BUBBLE='EVENT_BUBBLE'},
 ALIGN={CENTER='center'},EVENT={PRESSED='PRESSED',RELEASED='RELEASED',PRESS_LOST='PRESS_LOST',DELETE='DELETE'},
 Timer=function(o)o.delete=function(t)t.deleted=true end;H.timers[#H.timers+1]=o;return o end}end
function H.hidden(n)while n do if n.flags.HIDDEN then return true end;n=n.parent end;return false end
function H.click(text)
 for _,n in ipairs(H.nodes)do if n.click and n.flags.CLICKABLE and not H.hidden(n)then
  for _,label in ipairs(H.nodes)do if label.parent==n and label.props.text==text then n.click();return true end end
 end end
 return false
end
function H.click_row(index)for _,n in ipairs(H.nodes)do if n.click and n.flags.CLICKABLE and not H.hidden(n) and n.props.w==376 and n.props.h==76 and n.props.y==151+((index or 1)-1)*87 then n.click();return true end end;return false end
function H.advance(ms)H.clock=H.clock+ms;for _,timer in ipairs(H.timers)do if not timer.deleted then timer.cb()end end end
function H.clear()H.events={}end
function H.set(name,value)H.files[name]=value end
function H.get(name)return H.files[name]end
function H.open(name,mode)
 H.event('open',name,mode)
 if mode=='rb' then
  if H.files[name]==nil then return nil,'synthetic missing',2 end
  local raw,pos=H.files[name],0
  return {read=function(_,n)if pos>=#raw then return nil end;local s=raw:sub(pos+1,pos+n);pos=pos+#s;return s end,
   seek=function(_,origin,offset)if origin=='set'then pos=offset elseif origin=='end'then pos=#raw+offset else pos=pos+offset end;return pos end,
   setvbuf=function()return true end,close=function()H.event('close',name);return true end}
 elseif mode=='wb' then
  H.event('write-open',name);local buffer=''
  return {write=function(self,data)buffer=buffer..data;H.files[name]=buffer;H.event('write',name,data);return self end,close=function()H.event('close',name);return true end}
 end
 error('unexpected file mode')
end
io.open=H.open
os.clock=function()return H.clock/1000 end
os.time=function()return 1700000000 end
os.remove=function(name)H.event('remove',name);if H.files[name]==nil then return nil,'synthetic missing',2 end;H.files[name]=nil;return true end
os.execute=function(command)
 H.event('execute',command)
 local module=command:match('^insmod .+ ([%w_]+)$')
 if module=='w6rqry'then
  if H.registry_failure then return nil,'exit',1 end
  local q=H.files['/data/watch6recorder/w6r-registry-request.txt'];local b=string.rep(' ',128)
  b=H.put(b,0,'W6RS1\n');b=H.put(b,6,q:sub(7,22));b=H.put(b,22,'\n');b=H.put(b,23,q:sub(24,31));b=H.put(b,31,'\n');b=H.put(b,32,'00000000\n')
  local visited=0;for _,v in pairs(H.native_modules)do if v then visited=visited+1 end end
  for i,n in ipairs({'w6rc','w6rplay','w6rplayer','w6rxlink','w6rdirect'})do b=H.put(b,41+(i-1)*9,H.native_modules[n]and '00000001\n'or '00000000\n')end
  b=H.put(b,86,string.format('%08x\n',visited));b=H.put(b,95,string.format('%08x\n',H.crc(b:sub(1,95))));b=H.put(b,120,'W6RSEND\n');H.files['/data/watch6recorder/w6r-registry-status.txt']=b..b
 end
 if module then H.native_modules[module]=true;H.files['/proc/modules']=(H.files['/proc/modules'] or '')..module..',0,0,0,0,0,0,0\n' end
 local unload=command:match('^rmmod ([%w_]+)$')
 if unload then H.native_modules[unload]=nil;H.files['/proc/modules']=(H.files['/proc/modules'] or ''):gsub(unload..',[^\n]*\n','')end
 return true,'exit',0
end
math.randomseed(1234)
function H.put(s,p,v)return s:sub(1,p)..v..s:sub(p+#v+1)end
function H.crc(raw)local c=0xffffffff;for i=1,#raw do c=c~raw:byte(i);for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0)end end;return c~0xffffffff end
function H.source_status(json,phase,seq)
 local start=H.files['/data/watch6recorder/vs-meeting-source-start.txt'];local id=start:sub(7,22)
 local raw=string.rep(' ',512);raw=H.put(raw,0,'VSMC1\n');raw=H.put(raw,6,'SESSION ');raw=H.put(raw,14,id);raw=H.put(raw,30,'\n');raw=H.put(raw,32,'00001f40');raw=H.put(raw,480,id);raw=H.put(raw,496,'\nend=VSMC1\n');raw=H.put(raw,472,string.format('%08x',H.crc(raw:sub(1,472))));H.files['/data/watch6recorder/vs-mc-'..id..'-00000000.session']=raw
 local s={v=1,continuous=true,id=id,user_started=true,identity_persisted=true,phase=phase,rate=8000,sample_rate=8000,pid=123,
  produced_offset=16000,readable_offset=16000,reclaimed_offset=0,phone_durable_offset=0,cache_used=16000,cache_limit=134348800,reserve_bytes=131072,
  extent_count=1,extent_first_seq=1,tail_complete=phase=='closed',whole_meeting_complete=phase=='closed',archive_only=true,storage_id='',error_code=0,
  status_sequence=seq,sequence_end=seq,stop_reason='user'}
 local text=json.encode(s);local h=string.rep(' ',64);h=H.put(h,0,'VSMST1\n');h=H.put(h,7,id);h=H.put(h,23,'\n');h=H.put(h,24,'seq=');h=H.put(h,28,string.format('%08x',seq));h=H.put(h,37,'len=');h=H.put(h,41,string.format('%08x',#text));h=H.put(h,50,'crc=');h=H.put(h,54,string.format('%08x',H.crc(text)))
 H.files['/data/watch6recorder/vs-meeting-source-status.txt']=h..text..string.rep(' ',1408-#text)..h
 return id
end
function H.player_status(json,phase,seq,done)
 local request=H.files['/data/watch6recorder/w6r-player-request.txt'];local op=request:sub(9,24);local id=request:sub(25,40);local cache=request:sub(89,104)
 local s={v=1,kind='player',operation_id=op,record_id=id,cache_id=cache,phase=phase,sequence=seq,pid=42,error=0,prepared_bytes=16000,total_bytes=16000,rate=8000,position_ms=phase=='done' and 1000 or 250,duration_ms=1000,archive_hash='deadbeeffeedbabe',pcm_crc32='1234abcd',done=done or false,handle_closed=done or false}
 local text=json.encode(s);local h=string.rep(' ',64);h=H.put(h,0,'W6PST1\n');h=H.put(h,7,op);h=H.put(h,24,'seq=');h=H.put(h,28,string.format('%08x',seq));h=H.put(h,37,'len=');h=H.put(h,41,string.format('%08x',#text));h=H.put(h,50,'crc=');h=H.put(h,54,string.format('%08x',H.crc(text)))
 H.files['/data/watch6recorder/w6r-player-status.txt']=h..text..string.rep(' ',1408-#text)..h
end
"""

def constants(registry=False):
 raw=b'AP!!';fnv=2166136261
 for b in raw:fnv=((fnv^b)*16777619)&0xffffffff
 names=['vs-continuous-source-abcdefabcdef.elf','w6r-player-abcdefabcdef.elf','w6r-phone-link-abcdefabcdef.elf']
 out=dict(transport='mifitness',version='0.4.0-preview',fitness_required=True,wireless_export_identity_required=True,wireless_export_rpk_required=True,identity=dict(package='com.watch6.recorder',same_package_and_signing_certificate_required=True),kernel='synthetic kernel',partitions='1:2',windows=[dict(offset=0,count=4,fnv=fnv)],source_asset=names[0],player_asset=names[1],phone_asset=names[2],assets=[dict(name=n,hex=b'synthetic ELF'.hex()) for n in names])
 if registry:
  out.update(registry_asset='registry-abcdefabcdef.elf');out['assets'].append(dict(name=out['registry_asset'],hex=b'synthetic registry ELF'.hex()))
 return out

def bundle_source(registry=False):
 # Read the actual build binding list so tests cannot silently use another set
 # of modules/order than the shipped face bundle. Build module import is inert.
 source=(ROOT/'build.py').read_text(encoding='utf-8');bindings=None
 for item in ast.walk(ast.parse(source)):
  if isinstance(item,ast.For) and isinstance(item.target,ast.Tuple) and [getattr(x,'id',None) for x in item.target.elts]==['name','binding']:
   bindings=ast.literal_eval(item.iter);break
 if bindings is None:raise AssertionError('Build no longer has an inspectable Lua bundle binding list')
 spec=importlib.util.spec_from_file_location('recorder_bundle_source_only',ROOT/'build.py');build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
 out='local C='+build.lua(constants(registry))+'\n'
 for name,binding in bindings:out+='local '+binding+'=(function()\n'+(ROOT/'src'/(name+'.lua')).read_text(encoding='utf-8')+'\nend)()\n'
 return out+(ROOT/'src/main.lua').read_text(encoding='utf-8')

EXTRA_BOOTSTRAP=r"""
function host.link_status(phase,phone,seq)
 local H=host;local nonce=H.files['/data/watch6recorder/w6r-link-start.txt']:sub(6,21)
 local function h(seq,n)local s=string.format('VSL1 %s %08x %04x\n',nonce,seq,n);return s..string.rep(' ',64-#s)end
 local body=string.format('phase=%s\npid=00000141\ntx_ack=00000000\nrx_seq=00000000\nerror=00000000\nphone=%08x\ntx_cap=00000003\n',phase,phone and 1 or 0)
 local head=h(seq or 2,0);H.files['/data/watch6recorder/w6r-link-status.txt']=head..body..string.rep(' ',128-#body)..head
end
function host.phone_status(json,phase,export_phase,done,closed)
 local H=host;H.link_status(phase,true,2);local nonce=H.files['/data/watch6recorder/w6r-link-start.txt']:sub(6,21)
 local function h(seq,n)local s=string.format('VSL1 %s %08x %04x\n',nonce,seq,n);return s..string.rep(' ',64-#s)end
 local descriptor=H.files['/data/watch6recorder/w6r-export-job.txt'];local id=descriptor:sub(25,40)
 local body=json.encode({phase=export_phase,next=export_phase=='saved' and 16000 or 4096,total_bytes=16000,job_sequence=1,recording_id=id,code=0,pid=321,source_closed=closed==true,worker_done=done==true})
 local head=h(4,#body);H.files['/data/watch6recorder/w6r-export-status.txt']=head..body..string.rep(' ',384-#body)..head
end
"""

class MainIntegration(unittest.TestCase):
 def setUp(self):
  self.lua=LuaRuntime(unpack_returned_tuples=True);self.lua.execute(BOOTSTRAP+EXTRA_BOOTSTRAP);self.h=self.lua.globals().host
  for name,data in {'/etc/build.prop':'ro.build.version=3.100.043\n','/proc/version':'synthetic kernel\n','/proc/partitions':'1 2 progmem\n','/dev/ap':'AP!!','/proc/modules':'system,0,0,0,0,0,0,0\n'}.items():self.h.set(name,data)
  self.codec=self.lua.execute((ROOT/'src/json.lua').read_text(encoding='utf-8'));self.result=None
 def start(self,registry=False):self.h.clear();self.result=self.lua.execute(bundle_source(registry));return self.result
 def connect_button(self):
  if self.result['ui'].page()!='connection' and not (self.h.click('设置') or self.h.click('连接手机 · 点击查看')):return False
  return self.h.click('连接手机')
 def events(self,kind=None):return [dict(e.items()) for _,e in self.h.events.items() if kind is None or e['kind']==kind]
 def mutations(self):return [e for e in self.events() if e['kind'] in {'write-open','write','execute','remove'}]
 def action(self,name,id=None):
  result=self.result['app'].act(name,id);return result[0] if isinstance(result,tuple) else result
 def seed_record(self,id=RECORD):
  maker=self.lua.execute((ROOT/'src/catalog.lua').read_text(encoding='utf-8'))
  adapter=self.lua.eval("function(json)return {base='/data/watch6recorder/',read=function(n)return host.files[n],host.files[n] and nil or 2 end,write=function(n,s)host.files[n]=s;return true end,encode=json.encode_local,decode=json.decode_local}end")(self.codec)
  catalog=maker(adapter);self.assertTrue(catalog.put(self.lua.table_from(dict(id=id,rate=8000,bytes=16000,status='saved',created=1))))
 def begin_play(self):
  self.seed_record();self.start();self.assertTrue(self.action('play',RECORD));self.h.player_status(self.codec,'ready',1,True);self.h.advance(300)
 def test_fresh_init_and_idle_ticks_have_no_io_mutation_or_start(self):
  self.start();self.assertEqual(self.mutations(),[]);self.assertEqual(self.result['core'].state()['phase'],'idle')
  for _ in range(8):self.h.advance(250)
  self.assertEqual(self.mutations(),[])
 def test_visible_library_and_back_buttons_are_passive(self):
  self.start();self.assertTrue(self.h.click('录音列表'));self.assertEqual(self.result['ui'].page(),'list');self.assertTrue(self.h.click('返回'));self.assertEqual(self.result['ui'].page(),'home');self.assertEqual(self.mutations(),[])
 def test_idle_observation_does_not_read_ipc_every_timer_callback(self):
  self.start();self.h.clear();self.h.advance(250);reads=len(self.events('open'));self.assertGreater(reads,0)
  for _ in range(3):self.h.advance(250)
  self.assertEqual(len(self.events('open')),reads)
  self.h.advance(250);self.assertGreater(len(self.events('open')),reads)
 def test_wrong_firmware_blocks_explicit_record_before_any_mutation(self):
  self.h.set('/etc/build.prop','ro.build.version=0.0.0\n');self.start();self.assertFalse(self.action('record'));self.assertEqual(self.mutations(),[])
 def test_wrong_fingerprint_blocks_connect_play_and_export_before_mutation(self):
  for action in ['connect','play','export']:
   with self.subTest(action=action):
    self.setUp();self.seed_record();self.h.set('/dev/ap','NO!!');self.start();self.assertFalse(self.action(action,RECORD));self.assertEqual(self.mutations(),[])
 def test_explicit_record_loads_only_after_guard_and_writes_go_after_insmod(self):
  self.start();self.assertTrue(self.h.click('开始录音'));events=self.events();first_mutation=next(i for i,e in enumerate(events) if e['kind'] in {'write-open','execute','remove'})
  self.assertTrue(any(e['kind']=='close' and e['path']=='/dev/ap' for e in events[:first_mutation]));commands=self.events('execute');self.assertEqual(sum(e['path'].startswith('insmod ') for e in commands),1)
  loaded=next(i for i,e in enumerate(events) if e['kind']=='execute' and e['path'].endswith(' w6rc'));go=next(i for i,e in enumerate(events) if e['kind']=='write' and e['path']==BASE+'vs-meeting-source-go.txt' and e['value'][24:32]=='GO      ');self.assertLess(loaded,go)
  self.assertEqual(self.result['core'].state()['phase'],'preparing')
 def test_record_pause_resume_stop_routes_actual_mailbox_actions(self):
  self.start();self.assertTrue(self.action('record'));self.h.source_status(self.codec,'recording',1);self.h.advance(300)
  self.assertTrue(self.h.click('暂停录音'));self.assertEqual(self.h.get(BASE+'vs-meeting-source-pause.txt')[24:32],'PAUSE   ')
  self.h.source_status(self.codec,'paused',2);self.h.advance(300);self.assertTrue(self.h.click('继续录音'));self.assertEqual(self.h.get(BASE+'vs-meeting-source-pause.txt')[24:32],'RESUME  ')
  self.h.source_status(self.codec,'recording',3);self.h.advance(300);self.assertTrue(self.h.click('结束并保存'));self.assertEqual(self.h.get(BASE+'vs-meeting-source-stop.txt')[24:32],'STOP    ')
 def test_next_after_saved_never_starts_another_capture(self):
  self.start();self.assertTrue(self.action('record'));self.h.source_status(self.codec,'recording',1);self.h.advance(300);self.assertTrue(self.action('stop_record'));self.h.source_status(self.codec,'closed',2);self.h.advance(300)
  self.assertEqual(self.result['core'].state()['phase'],'saved');self.h.clear();self.assertTrue(self.h.click('准备下一条'));self.assertEqual(self.result['core'].state()['phase'],'idle');self.assertEqual(self.mutations(),[])
 def test_playback_capture_mutex_and_pending_tap_canceled_on_detach(self):
  self.begin_play();self.h.player_status(self.codec,'playing',1,False);self.h.advance(300);self.h.clear();self.assertTrue(self.action('record'));self.assertEqual(self.result['app'].pending()['kind'],'record');self.assertFalse(any(e['kind']=='execute' and e['path'].endswith(' w6rc') for e in self.events()))
  self.result['ui'].root.delete(self.result['ui'].root);self.h.player_status(self.codec,'done',2,True);self.h.advance(300);self.assertIsNone(self.result['app'].pending());self.assertFalse(any(e['kind']=='execute' and e['path'].endswith(' w6rc') for e in self.events()))
 def test_record_during_play_waits_for_close_and_does_not_start_twice(self):
  self.begin_play();self.h.player_status(self.codec,'playing',1,False);self.h.advance(300);self.h.clear();self.assertTrue(self.action('record'));self.assertEqual(self.result['core'].state()['phase'],'idle');self.h.player_status(self.codec,'done',2,True);self.h.advance(300)
  self.assertEqual(self.result['core'].state()['phase'],'preparing');self.h.advance(300);self.assertEqual(sum(e['kind']=='execute' and e['path'].endswith(' w6rc') for e in self.events()),1)
 def test_library_detail_keeps_visible_return_control(self):
  self.seed_record();self.start();self.assertTrue(self.h.click('录音列表'));self.assertTrue(self.h.click_row(1));self.assertEqual(self.result['ui'].page(),'detail');self.assertTrue(self.h.click('返回'));self.assertEqual(self.result['ui'].page(),'list');self.assertEqual(self.mutations(),[])

 def begin_export(self):
  self.seed_record();self.seed_record('fedcba9876543210');self.start();self.assertTrue(self.action('export',RECORD));self.h.player_status(self.codec,'ready',1,True);self.h.advance(300);self.h.advance(300)
  request=self.h.get(BASE+'w6r-player-request.txt');cache=request[88:104];self.cache=BASE+'w6r-play-'+cache+'.wav';self.h.set(self.cache,'synthetic validated immutable WAV');self.h.set(BASE+'vs-mc-'+RECORD+'-00000001.pcm','synthetic original')
  self.assertIsNotNone(self.h.get(BASE+'w6r-export-job.txt'));self.h.phone_status(self.codec,'connected','sending',False,False);self.h.set('/proc/321/cmdline','synthetic export worker');self.h.set('/proc/321/status','synthetic alive');self.h.advance(300)
 def test_explicit_connect_cannot_automatically_open_microphone(self):
  self.start();self.assertTrue(self.action('connect'))
  for _ in range(4):self.h.advance(250)
  self.assertEqual(self.result['core'].state()['phase'],'idle');self.assertFalse(any(e['kind']=='execute' and e['path'].endswith(' w6rc') for e in self.events()));self.assertIsNone(self.h.get(BASE+'vs-meeting-source-go.txt'))
 def test_export_pins_cache_and_new_prepare_cannot_remove_it(self):
  self.begin_export();job=self.h.get(BASE+'w6r-export-job.txt');self.h.clear();self.assertFalse(self.action('play','fedcba9876543210'));self.assertFalse(self.action('export','fedcba9876543210'));self.assertEqual(self.h.get(self.cache),'synthetic validated immutable WAV');self.assertEqual(self.h.get(BASE+'w6r-export-job.txt'),job);self.assertEqual(self.events('remove'),[])
 def test_active_export_restores_read_only_across_face_recreation(self):
  self.begin_export();job=self.h.get(BASE+'w6r-export-job.txt');self.result['ui'].root.delete(self.result['ui'].root);self.start();self.assertEqual(self.mutations(),[])
  transfer=self.result['app'].view()[2]['transfer'];self.assertTrue(transfer['active']);self.assertEqual(transfer['phase'],'sending');self.h.advance(300);self.assertEqual(self.mutations(),[]);self.assertEqual(self.h.get(BASE+'w6r-export-job.txt'),job);self.assertEqual(self.h.get(self.cache),'synthetic validated immutable WAV')
 def test_saved_receipt_does_not_unpin_before_real_exit_and_unload(self):
  self.begin_export();self.h.phone_status(self.codec,'closing','saved',False,True);self.h.advance(300);self.h.clear();self.assertFalse(self.action('play','fedcba9876543210'));self.assertEqual(self.events('remove'),[])
  self.h.phone_status(self.codec,'closed','saved',True,True);self.h.set('/proc/321/cmdline',None);self.h.set('/proc/321/status',None);self.h.advance(300);self.assertTrue(self.action('play','fedcba9876543210'));self.assertIsNone(self.h.get(self.cache));self.assertEqual(self.h.get(BASE+'vs-mc-'+RECORD+'-00000001.pcm'),'synthetic original')
 def test_recording_may_use_mic_while_independent_export_keeps_cache_pinned(self):
  self.begin_export();job=self.h.get(BASE+'w6r-export-job.txt');self.assertTrue(self.action('record'));self.assertEqual(self.result['core'].state()['phase'],'preparing');self.assertEqual(self.h.get(self.cache),'synthetic validated immutable WAV');self.assertEqual(self.h.get(BASE+'w6r-export-job.txt'),job)
 def test_ui_cancel_prepare_prevents_later_automatic_export(self):
  self.seed_record();self.start();self.assertTrue(self.h.click('录音列表'));self.assertTrue(self.h.click_row(1));self.assertTrue(self.h.click('发送到手机'));self.assertEqual(self.result['app'].pending()['kind'],'export');self.assertTrue(self.h.click('取消准备'));self.assertIsNone(self.result['app'].pending());self.h.player_status(self.codec,'ready',1,True);self.h.advance(300);self.assertIsNone(self.h.get(BASE+'w6r-link-start.txt'));self.assertTrue(self.h.click('返回'))

 def test_fitness_launch_navigation_never_starts_transport_or_microphone(self):
  self.start(True);self.assertTrue(self.h.click('连接手机 · 点击查看'));self.assertEqual(self.result['ui'].page(),'connection')
  for _ in range(8):self.h.advance(250)
  self.assertEqual(self.mutations(),[]);self.assertEqual(self.result['core'].state()['phase'],'idle');self.assertTrue(self.h.click('返回录音'))
 def test_fitness_explicit_connect_loads_only_guarded_phone_and_registry(self):
  self.start(True);self.assertTrue(self.connect_button());commands=self.events('execute')
  self.assertEqual(sum(e['path'].endswith(' w6rxlink') and e['path'].startswith('insmod ') for e in commands),1)
  self.assertFalse(any(e['path'].startswith('insmod ') and not (e['path'].endswith(' w6rxlink')or e['path'].endswith(' w6rqry')) for e in commands));self.assertIsNone(self.h.get(BASE+'w6r-direct-start.txt'));self.assertIsNone(self.h.get(BASE+'vs-meeting-source-go.txt'))
  first=next(i for i,e in enumerate(self.events()) if e['kind'] in {'write-open','execute','remove'})
  self.assertTrue(any(e['path']=='/dev/ap' and e['kind']=='close' for e in self.events()[:first]))
 def test_fitness_underlying_connection_is_not_phone_audio_ready(self):
  self.start(True);self.assertTrue(self.h.click('连接手机 · 点击查看'));self.assertTrue(self.connect_button());self.h.link_status('connected',False,1);self.h.advance(300)
  phone=self.result['app'].view()[2]['phone'];self.assertTrue(phone['transportReady']);self.assertFalse(phone['connected']);self.assertTrue(phone['identity_required'])
  self.assertFalse(self.h.click('连接正常'));self.h.link_status('connected',True,2);self.h.advance(1100)
  self.assertTrue(self.result['app'].view()[2]['phone']['connected']);self.assertTrue(self.h.click('断开连接'));self.assertIsNotNone(self.h.get(BASE+'w6r-link-stop.txt'))
  self.assertFalse(any(e['path'] in {'rmmod w6rxlink','rmmod w6rdirect'} for e in self.events('execute')))
 def test_fitness_wrong_fingerprint_rejects_without_touching_old_ipc(self):
  self.h.set('/dev/ap','NO!!');self.start(True);self.assertTrue(self.connect_button());self.assertEqual(self.mutations(),[])
 def test_registry_route_damaged_proc_and_blank_legacy_start_phone_owner(self):
  self.h.set('/proc/modules','system,0x1234,callback\x00truncated');self.h.set(BASE+'w6r-link-status.txt',' '*256)
  self.start(True);self.assertEqual(self.mutations(),[])
  self.assertTrue(self.h.click('连接手机 · 点击查看'));self.assertTrue(self.connect_button())
  self.assertIsNotNone(self.h.get(BASE+'w6r-link-start.txt'))
  commands=self.events('execute');self.assertEqual(sum(e['path'].startswith('insmod ')and e['path'].endswith(' w6rxlink')for e in commands),1)
  self.assertGreaterEqual(sum(e['path'].endswith(' w6rqry')for e in commands),2)
  self.assertFalse(any(e['path'].endswith(' w6rdirect')for e in commands));self.assertEqual(self.h.get(BASE+'w6r-link-status.txt'),' '*256)
  self.h.link_status('connected',True,1);self.h.advance(300);self.assertTrue(self.result['app'].view()[2]['phone']['connected'])
 def test_retained_old_direct_owner_blocks_export_without_stopping_or_erasing_it(self):
  self.seed_record();self.h.native_modules['w6rdirect']=True;self.h.set(BASE+'w6r-direct-status.txt','synthetic old live status');self.h.set(BASE+'w6r-play-deadbeefdeadbeef.wav','synthetic pinned WAV')
  self.start(True);self.assertEqual(self.mutations(),[]);self.assertTrue(self.connect_button())
  phone=self.result['app'].view()[2]['phone'];self.assertEqual(phone['phase'],'retained');self.assertIn('完整重启',phone['message']);self.assertFalse(phone['connected'])
  self.assertIsNone(self.h.get(BASE+'w6r-link-start.txt'));self.assertFalse(self.action('export',RECORD));self.assertFalse(self.action('play',RECORD))
  self.assertEqual(self.h.get(BASE+'w6r-direct-status.txt'),'synthetic old live status');self.assertEqual(self.h.get(BASE+'w6r-play-deadbeefdeadbeef.wav'),'synthetic pinned WAV');self.assertEqual(self.events('remove'),[])
  self.assertFalse(any('w6rdirect'in e['path'] or e['path'].endswith(' w6rxlink')for e in self.events('execute')))
  self.assertTrue(self.h.click('返回录音'));self.assertTrue(self.h.click('开始录音'));self.assertEqual(self.result['core'].state()['phase'],'preparing')
 def test_stale_old_direct_files_stay_untouched_after_registry_proves_absence(self):
  self.h.set(BASE+'w6r-direct-status.txt','synthetic stale status');self.h.set(BASE+'w6r-direct-job.txt','synthetic old descriptor')
  self.start(True);self.assertTrue(self.connect_button());self.assertIsNotNone(self.h.get(BASE+'w6r-link-start.txt'))
  self.assertEqual(self.h.get(BASE+'w6r-direct-status.txt'),'synthetic stale status');self.assertEqual(self.h.get(BASE+'w6r-direct-job.txt'),'synthetic old descriptor');self.assertEqual(self.events('remove'),[])
 def test_registry_fresh_record_recovers_initial_unknown_player_immediately(self):
  self.h.set('/proc/modules','truncated\x00');self.start(True);self.assertEqual(self.mutations(),[])
  self.assertTrue(self.h.click('开始录音'));self.assertEqual(self.result['core'].state()['phase'],'preparing')
  self.assertTrue(any(e['path'].endswith(' w6rc')for e in self.events('execute')));self.assertIsNotNone(self.h.get(BASE+'vs-meeting-source-go.txt'))
 def test_registry_guard_failure_never_queries_or_opens_microphone(self):
  self.h.set('/dev/ap','BAD!');self.start(True);self.assertTrue(self.h.click('开始录音'));self.assertEqual(self.mutations(),[])
 def test_registry_helper_failure_retains_state_then_explicit_retry_connects(self):
  self.start(True);self.h.registry_failure=True;self.assertTrue(self.connect_button());self.assertIsNone(self.h.get(BASE+'w6r-link-start.txt'));self.assertIsNone(self.h.get(BASE+'vs-meeting-source-go.txt'))
  self.h.registry_failure=False;self.assertTrue(self.connect_button());self.assertIsNotNone(self.h.get(BASE+'w6r-link-start.txt'))

if __name__=='__main__':unittest.main(verbosity=2)
