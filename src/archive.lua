-- Complete immutable archive preparation and speaker worker lifecycle.
-- Ready means canonical WAV validated, worker gone AND module unloaded.
local BASE='/data/watch6recorder/'
local MODULE='w6rplay'
local function valid_id(v)return type(v)=='string' and #v==16 and v:match('^[0-9a-f]+$') and v~='0000000000000000'end
local function hex_id(v)return type(v)=='string' and #v==16 and v:match('^[0-9a-f]+$')end
local function hex(v,n)local s={};for i=n,1,-1 do local d=v%16;s[i]=('0123456789abcdef'):sub(d+1,d+1);v=v//16 end;return table.concat(s)end
local table_crc={};for i=0,255 do local c=i;for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0)end;table_crc[i]=c end
local function crc(s)local c=0xffffffff;for i=1,#s do c=(c>>8)~table_crc[(c~s:byte(i))&255]end;return c~0xffffffff end
local function field(s,p,n)return s:sub(p+1,p+n)end
local function put(s,p,v)return s:sub(1,p)..v..s:sub(p+#v+1)end
local function uint(v)return type(v)=='number' and v>=0 and v<=0xffffffff and v%1==0 end
local function hexfield(s,p,n)local v=field(s,p,n);if #v~=n or not v:match('^[0-9a-f]+$')then return nil end;return tonumber(v,16)end
local function copy(t)local out={};for k,v in pairs(t or {})do out[k]=v end;return out end
local function create(a)
 a=a or {};local read,write,execute=assert(a.read),assert(a.write),assert(a.execute)
 local decode,now=assert(a.decode),assert(a.now_ms);local remove=a.remove or os.remove
 local config=type(C)=='table' and C or {};local asset=a.asset or config.player_asset
 local enabled=a.enabled==true or a.enabled==nil and config.player_candidate_enabled==true
 local current={phase='idle',active=false,safe_to_record=false};local operation,record,cache,mode,sequence,last_seq= nil,nil,nil,nil,0,0;local expected_crc='00000000';local expected_hash='0000000000000000'
 local saved;local polling=0;local deadline=0;local loaded=false;local attached=false;local detached=false;local unknown_initial=false
 local function failure_message(s)
  local stage=mode=='prepare' and '原音准备' or '回听'
  local detail=s.error~=0 and '错误 '..tostring(s.error) or '状态 '..tostring(s.native_phase or s.phase)
  return stage..'未完成（'..detail..'）\n原音保留'
 end
 local phases={initializing=true,building=true,ready=true,preparing=true,playing=true,pausing=true,paused=true,resuming=true,stopping=true,done=true,error=true,retained=true}
 local function p(name)return BASE..'w6r-player-'..name..'.txt'end
 local function exact(name,n)local raw,err=read(name,n);if type(raw)=='string' and #raw==n then return raw end;return nil,err end
 local function write_exact(name,data)return write(name,data)==true and exact(name,#data)==data end
 local function modules()
  if a.module_present~=nil then
   if type(a.module_present)~='function'then return nil end
   local ok,present=pcall(a.module_present,MODULE)
   if not ok or type(present)~='boolean'then return nil end
   return present
  end
  local raw=read('/proc/modules',8193)
  if type(raw)~='string' or #raw>8192 or raw~='' and (raw:sub(-1)~='\n' or raw:find('\n\n',1,true))then return nil end
  local seen=false
  for line in raw:gmatch('([^\n]+)\n')do local name=line:match('^([%w_.-]+),');if not name then return nil end;if name==MODULE then if seen then return nil end;seen=true end end
  return seen
 end
 local function request(kind,n)
  local s=string.rep(' ',512);s=put(s,0,'W6P1REQ\n');s=put(s,8,operation);s=put(s,24,record);s=put(s,40,hex(n,8));s=put(s,48,kind)
  s=put(s,88,cache);s=put(s,104,expected_crc);s=put(s,120,expected_hash);s=put(s,464,hex(n,8));s=put(s,472,hex(crc(s:sub(1,472)),8));s=put(s,480,operation);return put(s,496,'W6P1END\n')
 end
 local function parse_request(raw)
  if type(raw)~='string' or #raw~=512 or field(raw,0,8)~='W6P1REQ\n' or field(raw,496,8)~='W6P1END\n' or field(raw,480,16)~=field(raw,8,16)
   or field(raw,40,8)~=field(raw,464,8) or hexfield(raw,472,8)~=crc(raw:sub(1,472)) or not valid_id(field(raw,8,16)) or not valid_id(field(raw,24,16)) or not valid_id(field(raw,88,16))then return nil end
  return {operation=field(raw,8,16),record=field(raw,24,16),cache=field(raw,88,16),kind=field(raw,48,8),sequence=hexfield(raw,40,8),pcm_crc32=field(raw,104,8),archive_hash=field(raw,120,16)}
 end
 local function parse(raw)
  if type(raw)~='string' or #raw~=1536 or raw:sub(1,64)~=raw:sub(1473) or field(raw,0,7)~='W6PST1\n' or field(raw,7,16)~=operation
   or field(raw,24,4)~='seq=' or field(raw,37,4)~='len=' or field(raw,50,4)~='crc='then return nil end
  local seq,n,check=hexfield(raw,28,8),hexfield(raw,41,8),hexfield(raw,54,8)
  if not seq or seq<1 or seq<last_seq or not n or n<1 or n>1408 or crc(field(raw,64,n))~=check then return nil end
  local ok,s=pcall(decode,field(raw,64,n));if not ok or type(s)~='table' or s.v~=1 or s.kind~='player' or s.operation_id~=operation or s.record_id~=record or s.cache_id~=cache or s.sequence~=seq or not phases[s.phase]
   or not uint(s.pid) or s.pid<1 or not uint(s.prepared_bytes) or not uint(s.total_bytes) or s.total_bytes>134348800 or s.prepared_bytes>s.total_bytes
   or not uint(s.position_ms) or not uint(s.duration_ms) or s.position_ms>s.duration_ms or type(s.done)~='boolean' or type(s.handle_closed)~='boolean'
   or type(s.error)~='number' or s.error%1~=0 or s.error<(-2147483648) or s.error>2147483647 then return nil end
  if s.total_bytes>0 and (s.rate~=8000 and s.rate~=16000 or s.total_bytes%2~=0 or not hex_id(s.archive_hash))then return nil end
  if type(s.pcm_crc32)~='string' or #s.pcm_crc32~=8 or not s.pcm_crc32:match('^[0-9a-f]+$')then return nil end
  if s.done and (not s.handle_closed or s.phase~='ready' and s.phase~='done' and s.phase~='error')then return nil end
  if s.phase=='ready' or s.phase=='done' then if not s.done or not s.handle_closed or s.error~=0 or s.total_bytes<2 or s.prepared_bytes~=s.total_bytes then return nil end end
  if s.phase=='error' and (not s.done or s.error>=0)then return nil end
  if s.phase=='retained' and s.done then return nil end
  last_seq=seq;return s
 end
 local function command(kind)
  if not current.active or not operation or sequence>=0xfffffffe then return false,'回听任务未就绪'end
  sequence=sequence+1;if not write_exact(p('control'),request(kind,sequence))then return false,'控制未写入，请重试'end;return true
 end
 local function exited(pid)
  local x,xe=read('/proc/'..pid..'/cmdline',1024);local y,ye=read('/proc/'..pid..'/status',2048)
  return x==nil and y==nil and xe==2 and ye==2
 end
 local function info_from(s)return {id=record,cache_id=cache,path=BASE..'w6r-play-'..cache..'.wav',rate=s.rate,total_bytes=s.total_bytes,data_offset=44,archive_hash=s.archive_hash,pcm_crc32=s.pcm_crc32}end
 local out={}
 function out.tick()
  if detached or now()<polling then return end;polling=now()+250
  if not attached then
   attached=true;local present=modules()
   if present==nil then attached=false;unknown_initial=true;current={phase='retained',active=true,safe_to_record=false,message='无法确认回听组件状态，原音保留'};return end
   unknown_initial=false
   if not present then
    -- Recover the last successfully validated cache after a view recreation.
    -- Module absence is authoritative here: an active task could not have
    -- passed the native unload guard. Replaying still revalidates the WAV.
    local prior=parse_request(exact(p('request'),512))
    if prior and prior.sequence==1 and (prior.kind=='PREPARE ' or prior.kind=='PLAY    ')then
     operation,record,cache=prior.operation,prior.record,prior.cache;mode=prior.kind=='PLAY    ' and 'play' or 'prepare';expected_crc=prior.pcm_crc32;expected_hash=prior.archive_hash
     local prior_status=parse(exact(p('status'),1536))
     if prior_status and prior_status.done and prior_status.handle_closed and prior_status.error==0 and (prior_status.phase=='ready' or prior_status.phase=='done') and prior_status.prepared_bytes==prior_status.total_bytes and prior_status.total_bytes>0 then
      saved=info_from(prior_status);current={id=record,phase='ready',active=false,safe_to_record=true,message='完整原音已就绪'};return
     elseif prior_status and prior_status.done and prior_status.handle_closed and prior_status.phase=='error' then
      -- Module absence already proves ownership ended. Preserve the failure
      -- read-only so replacing the view cannot erase the diagnostic evidence.
      prior_status.id=record;prior_status.native_phase='error';prior_status.active=false;prior_status.safe_to_record=true
      prior_status.message=failure_message(prior_status);current=prior_status;return
     end
    end
    current={phase='idle',active=false,safe_to_record=true};return
   end
   local r=parse_request(exact(p('request'),512))
   if not r or r.sequence~=1 or r.kind~='PREPARE ' and r.kind~='PLAY    'then current={phase='retained',active=true,safe_to_record=false,message='回听组件状态需要恢复，原音保留'};return end
   operation,record,cache=r.operation,r.record,r.cache;mode=r.kind=='PLAY    ' and 'play' or 'prepare';expected_crc=r.pcm_crc32;expected_hash=r.archive_hash;loaded=true;sequence=2
   local c=parse_request(exact(p('control'),512));if c and c.operation==operation and c.sequence and c.sequence>sequence then sequence=c.sequence end
  end
  if not current.active and not loaded then return end
  local s=parse(exact(p('status'),1536))
  if not s then if deadline>0 and now()>deadline then current.phase='retained';current.message='回听状态尚未确认，原音保留'end;return end
  s.id=record;s.active=true;s.safe_to_record=false;s.native_phase=s.phase
  if s.phase=='initializing' or s.phase=='building' then s.phase='preparing';s.message='正在校验完整原音'
  elseif s.phase=='preparing' then s.message='正在打开扬声器'
  elseif s.phase=='playing' then s.message='正在回听'
  elseif s.phase=='paused' then s.message='回听已暂停'
  elseif s.phase=='retained' then s.message='回听组件退出未确认，原音保留'
  elseif s.phase=='error' then s.message=failure_message(s)end
  if s.done and s.handle_closed and s.native_phase~='retained' and exited(s.pid) then
   if execute('rmmod '..MODULE)==true and modules()==false then
    loaded=false;s.active=false;s.safe_to_record=true
    if mode=='prepare' and s.native_phase=='ready' and s.error==0 then saved=info_from(s);s.phase='ready';s.message='原音已完整校验'
    elseif s.native_phase=='done' then saved=info_from(s);s.phase='done';s.message='回听已结束'
    else s.phase='error';s.message=failure_message(s)end
   else s.phase='retained';s.message='回听组件退出未确认，原音保留'end
  end
  current=s
 end
 function out.reobserve()
  -- Initialization is passive. An explicit action may prepare the native
  -- registry query later; only retry an unknown first observation, never an
  -- already adopted or newly loaded player operation.
  if detached or not unknown_initial or operation or loaded then return false end
  attached=false;polling=0;out.tick();return true
 end
 function out.state()out.tick();return copy(current)end
 function out.info()return saved and copy(saved) or nil end
 function out.safe_to_record()out.tick();return current.safe_to_record==true and current.active==false end
 function out.busy()out.tick();return current.active==true end
 function out.release(info)
  if not info or not valid_id(info.cache_id) or info.path~=BASE..'w6r-play-'..info.cache_id..'.wav' or not out.safe_to_record() or type(a.can_release)~='function' or a.can_release(info)~=true then return false,'原音缓存仍在使用，暂不能释放'end
  local ok=remove(info.path);if ok~=true then local raw,errno=read(info.path,1);if raw~=nil or errno~=2 then return false,'原音缓存清理未确认'end end
  if saved and saved.cache_id==info.cache_id then saved=nil end;return true
 end
 local function begin(kind,item)
  if not enabled or type(asset)~='string' or not asset:match('^[%w_.-]+$')then return false,'此固件回听能力尚未启用'end
  if not out.safe_to_record() or modules()~=false then return false,'请先结束回听任务'end
  local target=type(item)=='table' and item.id or item
  if not valid_id(target)then return false,'录音标识不正确'end
  if kind=='play' then
   if type(item)~='table' or not valid_id(item.cache_id) or item.path~=BASE..'w6r-play-'..item.cache_id..'.wav' or item.data_offset~=44 or not uint(item.total_bytes) or item.total_bytes<2 or item.total_bytes>134348800 or item.total_bytes%2~=0 or item.rate~=8000 and item.rate~=16000 or not hex_id(item.archive_hash) or type(item.pcm_crc32)~='string' or #item.pcm_crc32~=8 or not item.pcm_crc32:match('^[0-9a-f]+$')then return false,'完整原音尚未准备好'end
   if saved and saved.cache_id~=item.cache_id then local ok,err=out.release(saved);if not ok then return false,err end end
   saved=copy(item)
  elseif saved then local ok,err=out.release(saved);if not ok then return false,err end end
  local next_id=type(a.nonce)=='function' and a.nonce() or nil;if not valid_id(next_id) or next_id==operation then return false,'无法生成独立回听任务'end
  operation,record,mode,sequence,last_seq=next_id,target,kind,2,0;cache=kind=='play' and item.cache_id or next_id;expected_crc=kind=='play' and item.pcm_crc32 or '00000000';expected_hash=kind=='play' and item.archive_hash or '0000000000000000'
  if not write_exact(p('status'),string.rep(' ',1536)) or not write_exact(p('control'),string.rep(' ',512)) or not write_exact(p('request'),request(kind=='play' and 'PLAY    ' or 'PREPARE ',1))then return false,'准备文件写入失败'end
  current={phase='preparing',active=true,safe_to_record=false,id=record,message='正在校验完整原音'};deadline=now()+12000;polling=0
  if execute('insmod '..BASE..asset..' '..MODULE)~=true then
   if modules()==false then current={phase='error',active=false,safe_to_record=true,message='回听组件加载失败，原音保留'}else current={phase='retained',active=true,safe_to_record=false,message='回听组件状态未确认，原音保留'}end
   return false,current.message
  end
  loaded=true
  if not write_exact(p('control'),request('GO      ',2))then current.message='回听启动未确认，正在等待安全退出';return false,current.message end
  return true
 end
 function out.prepare(item)return begin('prepare',item)end
 function out.play(info)return begin('play',info)end
 function out.pause()out.tick();if current.phase~='playing'then return false end;local ok,err=command('PAUSE   ');if ok then current.phase='pausing'end;return ok,err end
 function out.resume()out.tick();if current.phase~='paused'then return false end;local ok,err=command('RESUME  ');if ok then current.phase='resuming'end;return ok,err end
 function out.stop()out.tick();if not current.active then return current.safe_to_record==true end;local ok,err=command('STOP    ');if ok then current.phase='stopping'end;return ok,err end
 function out.cancel()return out.stop()end
 function out.detach()detached=true end
 return out
end
return create
