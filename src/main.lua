-- Bundled by build.py. No microphone starts during initialization or reattach.
local BASE='/data/watch6recorder/'
local lvgl=require('lvgl');local alive=true;local timer,core,ui,app
local clock=0;local sequence=0;local prepared=false;local registry
local function now()
 local ok,value=pcall(os.clock)
 if ok and type(value)=='number' and value==value and value>=0 then clock=math.max(clock,math.floor(value*1000)) end
 return clock
end
local function read(name,limit)
 local ok,f,_,errno=pcall(io.open,name,'rb');if not ok or not f then return nil,errno end
 local good,raw,problem,read_errno=pcall(f.read,f,limit+1);local closed,result=pcall(f.close,f)
 if good and raw==nil and problem==nil and read_errno==nil then raw=''end -- normal empty-file EOF
 if not good or not closed or not result or type(raw)~='string' or #raw>limit then return nil end
 return raw
end
local function put(name,data)
 local ok,f=pcall(io.open,name,'wb');if not ok or not f then return false end
 local good,result=pcall(f.write,f,data);local closed,value=pcall(f.close,f)
 return good and result and closed and value and read(name,#data)==data or false
end
local function raw_execute(command)local ok,a,b,c=pcall(os.execute,command);return ok and a==true and b=='exit' and c==0 end
local function execute(command)
 if registry and (command:match('^insmod ')or command:match('^rmmod '))then registry.invalidate()end
 return raw_execute(command)
end
local function fnv(raw)local h=2166136261;for i=1,#raw do h=((h~raw:byte(i))*16777619)&0xffffffff end;return h end
local function prepare()
 if prepared then return true end
 local props=read('/etc/build.prop',8192)
 if not props or not ('\n'..props):match('\n%s*ro%.build%.version%s*=%s*3%.100%.043%s*\n') then return false,'此固件尚不支持，请勿强行加载' end
 local kernel=read('/proc/version',1024)
 if not kernel or kernel:gsub('%s+',' '):gsub(' $','')~=C.kernel then return false,'系统版本不匹配，未启动录音' end
 local parts=read('/proc/partitions',4096);local rows={}
 if parts then for a,b,c in parts:gmatch('(%d+)%s+(%d+)%s+([%w_]+)')do if c=='progmem' then rows[#rows+1]=a..':'..b end end end
 if table.concat(rows,',')~=C.partitions then return false,'分区不匹配，未启动录音' end
 local opened,f=pcall(io.open,'/dev/ap','rb');if not opened or not f then return false,'无法核对固件，未启动录音' end
 local good,matched=pcall(function()
  if not f:setvbuf('no') then return false end
  for _,w in ipairs(C.windows)do if f:seek('set',w.offset)~=w.offset then return false end;local raw=f:read(w.count);if type(raw)~='string' or #raw~=w.count or fnv(raw)~=w.fnv then return false end end
  return true
 end)
 local closed,result=pcall(f.close,f);if not good or not matched or not closed or not result then return false,'固件指纹不符，未启动录音' end
 -- Only the independent directory may be created, and only after all guards.
 execute('mkdir /data/watch6recorder')
 local marker,err=read(BASE..'recorder-marker.txt',64)
 if marker and marker~='watch6-recorder-v1\n' then return false,'录音目录标记异常，原文件保留' end
 if not marker and (err~=2 or not put(BASE..'recorder-marker.txt','watch6-recorder-v1\n')) then return false,'录音目录未就绪，未启动麦克风' end
 for _,asset in ipairs(C.assets)do
  local raw=(asset.hex:gsub('%x%x',function(v)return string.char(tonumber(v,16))end));local prior,problem=read(BASE..asset.name,#raw)
  if prior and prior~=raw then return false,'同名组件不同，原文件保留' end
  if not prior and (problem~=2 or not put(BASE..asset.name,raw)) then return false,'采音组件保存失败' end
 end
 prepared=true;return true
end
-- Metadata creation does not create a directory or acquire audio permissions.
local catalog=create_catalog({base=BASE,read=read,write=put,decode=voice_json.decode_local,encode=voice_json.encode_local})
local function nonce()
 sequence=sequence+1
 local ok,epoch=pcall(os.time);if not ok or type(epoch)~='number' or epoch<0 then epoch=0 end
 return string.format('%08x%08x',epoch&0xffffffff,(now()~math.random(1,0x7fffffff)~sequence)&0xffffffff)
end
if C.registry_asset then registry=create_registry({asset=C.registry_asset,read=read,write=put,execute=raw_execute,nonce=nonce})end
local module_present=registry and function(name)return registry.present(name)end or nil
local source=create_source({read=read,write=put,execute=execute,now_ms=now,decode=voice_json.decode,asset=C.source_asset,enabled=true,module_present=module_present})
-- First ever launch has no directory yet. Catalog is reopened after prepare.
local catalog_proxy={}
function catalog_proxy.healthy()return catalog.healthy() end
function catalog_proxy.list()return catalog.list() end
function catalog_proxy.put(row)return catalog.put(row) end
local archive,player,transfer
local function ready()
 if not archive.safe_to_record() then return false,'请先结束回听，麦克风尚未打开' end
 local ok,message=prepare();if not ok then return false,message end
 catalog=create_catalog({base=BASE,read=read,write=put,decode=voice_json.decode_local,encode=voice_json.encode_local})
 return catalog.healthy(),catalog.healthy() and nil or '录音目录需要恢复，原音保留'
end
function catalog_proxy.revision()return catalog.revision()end
local function retired_module_present()
 if module_present then return module_present('w6rdirect')end
 -- Compatibility for injected host adapters only. Production uses the exact
 -- registry helper, and never infers absence from damaged proc formatter text.
 local raw=read('/proc/modules',8193)
 if type(raw)~='string'or #raw>8192 or raw~=''and (raw:sub(-1)~='\n'or raw:find('\n\n',1,true))then return nil end
 local present=false
 for line in raw:gmatch('([^\n]+)\n')do
  local name=line:match('^([%w_.-]+),');if not name then return nil end
  if name=='w6rdirect'then if present then return nil end;present=true end
 end
 return present
end
local link=create_phone_link({asset=C.phone_asset,read=read,write=put,execute=execute,now_ms=now,decode=voice_json.decode,encode=voice_json.encode,
 module_present=module_present,retired_module_present=retired_module_present})
transfer=create_transfer({link=link,prepare=prepare,now_ms=now,on_saved=function(id)
 for _,r in ipairs(catalog.list())do if r.id==id and not r.phone_saved then r.phone_saved=true;catalog.put(r);break end end
end})
-- Read-only observation may resume showing a user-started background export.
-- Opening this view never starts a connection or an export by itself.
transfer.restore()
archive=create_archive({asset=C.player_asset,enabled=true,read=read,write=put,execute=execute,now_ms=now,
 decode=voice_json.decode,nonce=nonce,remove=os.remove,module_present=module_present,can_release=function()return transfer.safe_to_release()end})
local raw_player=create_playback(archive)
player={play=function(info)local ok,err=prepare();if not ok then return false,err end;return raw_player.play(info)end,
 stop=raw_player.stop,pause=raw_player.pause,resume=raw_player.resume,detach=raw_player.detach,tick=function()end,
 state=function()
  local s=raw_player.state()
  if s.phase=='done'then
   local complete=(s.duration_ms or 0)>0 and (s.position_ms or 0)>=s.duration_ms
   s.phase=complete and 'completed' or 'stopped';s.message=complete and '已完整播完' or '已停止回听'
  end
  return s
 end}
local guarded_archive={prepare=function(row)local ok,err=prepare();if not ok then return false,err end;return archive.prepare(row)end,
 tick=archive.tick,state=archive.state,info=archive.info,cancel=archive.cancel,detach=archive.detach}
core=create_recorder({source=source,catalog=catalog_proxy,prepare=ready,nonce=nonce,now_ms=now,created_at=function()
 local ok,value=pcall(os.time);return ok and type(value)=='number' and value>=0 and value or 0
end})
app=create_app({recorder=core,catalog=catalog_proxy,archive=guarded_archive,player=player,transfer=transfer,now_ms=now,
 capture_allowed=archive.safe_to_record,
 prepare_allowed=function()return archive.safe_to_record() and transfer.safe_to_release()end})
local actions={};local next_view_tick=0;local preflight_message
local function paint()
 if not alive or not ui then return false end
 local s,rows,extra=app.view()
 extra.phone.transport='mifitness';extra.phone.version=C.version;extra.phone.identity_required=true
 if registry and not registry.activated()then
  extra.phone.phase='idle';extra.phone.message='点击连接，自动检查手表状态'
  if not extra.transfer.id then extra.transfer.active=false end
 end
 if preflight_message then extra.phone.message=preflight_message;extra.message=preflight_message end
 ui.render(s,rows,extra)
 local capture=s.phase~='idle' and s.phase~='saved' and s.phase~='recovery'
 local phase=extra.phone.phase
 return capture or extra.record_preparing==true or extra.preparing_id~=nil or extra.playback.active==true or extra.transfer.active==true
  or phase=='scanning' or phase=='connecting' or phase=='discovering' or phase=='starting' or phase=='releasing'
end
function actions.render()next_view_tick=0;paint()end
function actions.act(action,id)
 if action=='show_transfer' or action=='show_playback'then if id then ui.showDetail(id)end
 else
  if registry and ({connect=true,record=true,recover_record=true,play=true,export=true})[action]then
   local ok,err=prepare()
   if ok then ok,err=registry.refresh()end
   if not ok then preflight_message=err or '组件状态未确认，原音保留';if action=='connect'then ui.showConnection()end;actions.render();return end
   preflight_message=nil;archive.reobserve();transfer.restore()
  end
  local ok=app.act(action,id)
  if action=='connect'then ui.showConnection()
  elseif ok and id and (action=='play' or action=='export')then ui.showDetail(id)end
 end
 actions.render()
end
ui=create_ui(actions);actions.render()
timer=lvgl.Timer({period=250,cb=function()
 if alive and now()>=next_view_tick then
  app.tick();local active=paint();next_view_tick=now()+(active and 250 or 1000)
 end
end})
if ui.root.onevent and lvgl.EVENT and lvgl.EVENT.DELETE then ui.root:onevent(lvgl.EVENT.DELETE,function()
 alive=false;if timer then pcall(function()timer:delete()end);timer=nil end;app.detach()
 -- Native workers continue only operations the user explicitly started.
end)end
return {core=core,ui=ui,app=app}
