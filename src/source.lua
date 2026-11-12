-- Fixed P65 continuous-source file IPC. No native calls, dynamic paths, or mic on attach.
-- Pinned firmware/native capability guards remain authoritative; physical
-- verification is evidence, separate from candidate enable. A mailbox write is
-- not a reclaim: only the native status frontier confirms removal of audio.
local BASE='/data/watch6recorder/'
local MODULE='w6rc'
local function uint(n)return type(n)=='number' and n==n and n>=0 and n%1==0 and n<=0xffffffff end
local function even(n)return uint(n) and n%2==0 end
local function nonce(n)return type(n)=='string' and #n==16 and n:match('^[0-9a-f]+$')~=nil and n~='0000000000000000' end
local function uuid(n)return type(n)=='string' and #n==36 and n:match('^[0-9a-f]+%-[0-9a-f]+%-[0-9a-f]+%-[0-9a-f]+%-[0-9a-f]+$')~=nil and n:sub(9,9)=='-' and n:sub(14,14)=='-' and n:sub(19,19)=='-' and n:sub(24,24)=='-' end
local function hex(n,d)local out={};for i=d,1,-1 do out[i]=('0123456789abcdef'):sub(n%16+1,n%16+1);n=n//16 end;return table.concat(out) end
local crc_table={}
for i=0,255 do local c=i;for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0) end;crc_table[i]=c end
local function crc_update(c,s)for i=1,#s do c=(c>>8)~crc_table[(c~s:byte(i))&255] end;return c end
local function crc(s)return crc_update(0xffffffff,s)~0xffffffff end
local function field(s,p,n)return s:sub(p+1,p+n) end
local function putfield(s,p,v)return s:sub(1,p)..v..s:sub(p+#v+1) end
local function hexfield(s,p,n)local v=field(s,p,n);if #v~=n or not v:match('^[0-9a-f]+$') then return nil end;local value=tonumber(v,16);return value and value<=0xffffffff and value or nil end
local function copy(s)local out={};for k,v in pairs(s or {})do out[k]=v end;return out end
local function create(adapter)
 adapter=adapter or {}
 local config=type(C)=='table' and C or {}
 local asset=adapter.asset or config.meeting_source_asset
 local enabled=adapter.enabled==true or adapter.enabled==nil and config.meeting_candidate_enabled==true and config.meeting_native_source_available==true
 local read,write,execute=assert(adapter.read,'meeting read adapter'),assert(adapter.write,'meeting write adapter'),assert(adapter.execute,'meeting command adapter')
 local open=adapter.open or io.open
 local remove=adapter.remove or os.remove
 local decode=adapter.decode or (type(voice_json)=='table' and voice_json.decode)
 local now=assert(adapter.now_ms,'meeting clock adapter')
 local source={};local alive=true;local id,rate;local cached;local last_seq=0;local next_poll=0;local startup_deadline=0
 local known_loaded,unloaded=false,false
 local descriptors,order={},{}
 local pending_release=nil
 local phone_pair=nil
 local recovery={code=0}
 local function path(kind)return BASE..'vs-meeting-source-'..kind..'.txt' end
 local function extent_path(seq,suffix)return BASE..'vs-mc-'..id..'-'..hex(seq,8)..suffix end
 local function exact(name,size)local value,errno=read(name,size);if type(value)=='string' and #value==size then return value end;return nil,errno end
 local function write_exact(name,value)return write(name,value)==true and exact(name,#value)==value end
 local function missing(name)local value,err=read(name,1);return value==nil and err==2 end
 local function control(kind,seq,settings)
  local s=string.rep(' ',512);s=putfield(s,0,'VSMQ1\n');s=putfield(s,6,id);s=putfield(s,24,kind);s=putfield(s,32,hex(seq,8))
  if settings then
   if settings.rate then s=putfield(s,40,hex(settings.rate,8));s=putfield(s,48,hex(settings.slots,8));s=putfield(s,56,hex(settings.seconds,8)) end
   if settings.storage then s=putfield(s,64,settings.storage);s=putfield(s,100,settings.epoch) end
   if settings.reason then s=putfield(s,136,hex(settings.reason,8)) end
   if settings.archive_only~=nil then s=putfield(s,144,settings.archive_only and '00000001' or '00000000') end
  end
  s=putfield(s,464,hex(seq,8));s=putfield(s,472,hex(crc(s:sub(1,472)),8));s=putfield(s,480,id);return putfield(s,496,'\nend=VSMQ1\n')
 end
 local function parse_control(raw,kind,expected)
  if type(raw)~='string' or #raw~=512 or field(raw,0,6)~='VSMQ1\n' or field(raw,24,8)~=kind or field(raw,496,11)~='\nend=VSMQ1\n' then return nil end
  local n=field(raw,6,16);if not nonce(n) or expected and n~=expected or field(raw,480,16)~=n then return nil end
  local seq=hexfield(raw,32,8);if not seq or seq<1 or field(raw,32,8)~=field(raw,464,8) or hexfield(raw,472,8)~=crc(raw:sub(1,472)) then return nil end
  return {id=n,sequence=seq,rate=hexfield(raw,40,8),slots=hexfield(raw,48,8),seconds=hexfield(raw,56,8),storage=field(raw,64,36),epoch=field(raw,100,36),raw=raw}
 end
 local function immutable(raw,kind,seq)
  if not id or type(raw)~='string' or #raw~=512 or field(raw,0,6)~='VSMC1\n' or field(raw,6,8)~=kind or field(raw,14,16)~=id
   or field(raw,30,1)~='\n' or field(raw,480,16)~=id or field(raw,496,11)~='\nend=VSMC1\n' or hexfield(raw,472,8)~=crc(raw:sub(1,472)) then return nil end
  if kind=='SESSION ' then return hexfield(raw,32,8)==rate and true or nil end
  local number,start,bytes,checksum,sample=hexfield(raw,32,8),hexfield(raw,40,16),hexfield(raw,56,8),hexfield(raw,64,8),hexfield(raw,72,8)
  if number~=seq or not even(start) or not even(bytes) or bytes<2 or bytes>65536 or not checksum or sample~=rate then return nil end
  return {id=id,seq=seq,start=start,length=bytes,crc=checksum,sealed=true,raw=raw}
 end
 local function frame(raw)
  if type(raw)~='string' or #raw~=1536 or raw:sub(1,64)~=raw:sub(1473,1536) or field(raw,0,7)~='VSMST1\n'
   or field(raw,24,4)~='seq=' or field(raw,37,4)~='len=' or field(raw,50,4)~='crc=' then return nil end
  local n,seq,length,check=field(raw,7,16),hexfield(raw,28,8),hexfield(raw,41,8),hexfield(raw,54,8)
  if not seq or seq<1 or not length or length<1 or length>1408 or not check then return nil end
  local payload=field(raw,64,length);if crc(payload)~=check or type(decode)~='function' then return nil end
  local ok,s=pcall(decode,payload);if not ok or type(s)~='table' or s.v~=1 then return nil end
  if n=='0000000000000000' and s.continuous==false then return {phase='blocked',continuous=false,owner_present=true,safe_to_start=false,safe_to_destroy=false,error='原生连续采集能力尚未就绪'} end
  if not nonce(n) or id and id~=n or s.id~=n or s.continuous~=true or s.status_sequence~=seq or s.sequence_end~=seq or seq<last_seq then return nil end
  if not id then id=n end
  if s.rate~=8000 and s.rate~=16000 or s.sample_rate~=s.rate or rate and s.rate~=rate or not uint(s.pid) or s.pid<1
   or not even(s.produced_offset) or not even(s.readable_offset) or not even(s.reclaimed_offset) or not even(s.phone_durable_offset)
   or s.reclaimed_offset>s.readable_offset or s.readable_offset>s.produced_offset or s.phone_durable_offset<s.reclaimed_offset or s.phone_durable_offset>s.readable_offset
   or not uint(s.cache_used) or not uint(s.cache_limit) or s.cache_used>s.cache_limit or s.cache_limit<4*65536 or not uint(s.reserve_bytes) or s.reserve_bytes~=131072
   or not uint(s.extent_count) or s.extent_count>2050 or not uint(s.extent_first_seq) or s.extent_first_seq<1
   or type(s.tail_complete)~='boolean' or s.user_started~=true or s.identity_persisted~=true then return nil end
  rate=s.rate
  local intent=parse_control(exact(path('start'),512),'START   ',id)
  if not intent or intent.sequence~=1 or intent.rate~=rate or not immutable(exact(extent_path(0,'.session'),512),'SESSION ',0) then return nil end
  local phase=s.phase
  if phase=='draining' then s.native_phase=phase;s.phase='stopping' elseif phase=='retained' then s.native_phase=phase;s.phase='error' end
  if s.phase~='starting' and s.phase~='recording' and s.phase~='stopping' and s.phase~='closed' and s.phase~='error' and s.phase~='pausing' and s.phase~='paused' and s.phase~='resuming' then return nil end
  last_seq=seq;s.safe_to_start=false;s.owner_present=true;s.safe_to_destroy=false
  if s.phase=='closed' then
   local a,ae=read('/proc/'..s.pid..'/cmdline',1024);local b,be=read('/proc/'..s.pid..'/status',2048)
   if a==nil and b==nil and ae==2 and be==2 then s.owner_present=false;s.safe_to_destroy=true end
  end
  return s
 end
 local function observe(force)
  if not force and cached and now()<next_poll then return cached end
  next_poll=now()+250
  local raw,err=exact(path('status'),1536);local fresh=frame(raw)
  if fresh then
   if fresh.continuous==false then cached=fresh;return cached end
   if cached and cached.id==fresh.id then
    for _,key in ipairs({'produced_offset','readable_offset','reclaimed_offset','phone_durable_offset'})do
     if type(cached[key])=='number' and fresh[key]<cached[key] then fresh=nil;break end
    end
   end
   if fresh then cached=fresh
    if pending_release and fresh.reclaimed_offset>=pending_release.finish then pending_release=nil end
    for seq,value in pairs(descriptors)do if value.start+value.length<=fresh.reclaimed_offset then descriptors[seq]=nil end end
    return cached
   end
  end
  if not id then
   local intent=parse_control(exact(path('start'),512),'START   ')
   if intent then id=intent.id;rate=intent.rate end
  end
  if not id and raw==nil and err==2 and missing(path('start')) then
   cached={phase='idle',continuous=true,owner_present=false,safe_to_start=true,safe_to_destroy=false};return cached
  end
  -- A recreated view has no in-memory start deadline. Accept only the exact
  -- persisted user START + GO pair as a bounded pending identity; this is not
  -- SESSION/owner proof and never authorizes start, read, reclaim or destroy.
  if id and startup_deadline==0 and missing(extent_path(0,'.session')) then
   local intent=parse_control(exact(path('start'),512),'START   ',id)
   local go=parse_control(exact(path('go'),512),'GO      ',id)
   if intent and intent.sequence==1 and (intent.rate==8000 or intent.rate==16000) and go and go.sequence==2 then
    rate=intent.rate;startup_deadline=now()+10000
   end
  end
  if cached and cached.id and cached.phase~='closed' and now()<startup_deadline then return cached end
  cached={id=id,rate=rate,phase=now()<startup_deadline and 'starting' or 'error',continuous=true,user_started=id~=nil,identity_persisted=false,
   owner_present=true,safe_to_start=false,safe_to_destroy=false,tail_complete=false,error='连续采集状态或完整记录尚未确认'}
  return cached
 end
 local function verify_pcm(e)
  local ok,f=pcall(open,extent_path(e.seq,'.pcm'),'rb');if not ok or not f then return false end
  local valid=true;local good=pcall(function()
   if f:seek('end',0)~=e.length or f:seek('set',0)~=0 then valid=false;return end
   local left,c=e.length,0xffffffff
   while left>0 do local want=math.min(left,4096);local data=f:read(want);if type(data)~='string' or #data~=want then valid=false;return end;c=crc_update(c,data);left=left-want end
   valid=(c~0xffffffff)==e.crc
  end)
  local closed,result=pcall(f.close,f);return good and valid and closed and result and true or false
 end
 local function descriptor(seq,s)
  local prior=descriptors[seq];if prior then return prior end
  local e=immutable(exact(extent_path(seq,'.meta'),512),'SEALED  ',seq)
  if not e or e.start<s.reclaimed_offset or e.start+e.length>s.readable_offset or not verify_pcm(e) then return nil end
  if #order>=8 then descriptors[table.remove(order,1)]=nil end;order[#order+1]=seq;descriptors[seq]=e;return e
 end
 local function command_sequence(kind,name)
  local raw=exact(path(name),512);local previous=parse_control(raw,kind,id)
  if previous then return previous.sequence+1 end
  if raw==string.rep(' ',512) then return 1 end
  -- A torn/nonblank mailbox may once have carried a higher accepted number.
  -- Reverting to1 would silently strand control after a view recreation.
  return nil
 end
 function source.status()return copy(observe(false)) end
 local function module_snapshot()
  if adapter.module_present~=nil then
   if type(adapter.module_present)~='function'then return nil end
   local ok,present=pcall(adapter.module_present,MODULE)
   if not ok or type(present)~='boolean'then return nil end
   return {source=present}
  end
  -- The module registry is stronger than a persisted PID: task numbers may
  -- be reused after reboot. Require a complete bounded read, never a prefix.
  local opened,f=pcall(open,'/proc/modules','rb');if not opened or not f then return nil end
  local chunks,total={},0;local valid,ended=true,false
  for _=1,32 do
   local good,data,problem,errno=pcall(f.read,f,512)
   if not good or problem~=nil or errno~=nil then valid=false;break end
   if data==nil or data=='' then ended=true;break end
   if type(data)~='string' or total+#data>8192 then valid=false;break end
   total=total+#data;chunks[#chunks+1]=data
  end
  local closed,result=pcall(f.close,f);if not valid or not ended or not closed or not result then return nil end
  local raw=table.concat(chunks);if raw~='' and (raw:sub(-1)~='\n' or raw:sub(1,1)=='\n' or raw:find('\n\n',1,true)) then return nil end
  local out={source=false,peer=false};local names={}
  local function pointer(v)return v=='(nil)' or v=='0' or v:match('^0x[0-9a-fA-F]+$') and #v<=10 or v:match('^[0-9a-fA-F]+$') and #v<=8 end
  local function decimal(v)return v:match('^%d+$') and #v<=10 and tonumber(v)<=0xffffffff end
  for line in raw:gmatch('([^\n]+)\n')do
   local fields={};for value in (line..','):gmatch('(.-),')do fields[#fields+1]=value end
   local count=#fields;local name=fields[1]
   if (count~=8 and count~=9) or not name or #name>64 or not name:match('^[%w_.-]+$') or names[name] then return nil end
   names[name]=true;local shift=count==9 and 1 or 0
   if count==9 and not pointer(fields[2]) then return nil end
   if not pointer(fields[2+shift]) or not pointer(fields[3+shift]) or not decimal(fields[4+shift])
     or not pointer(fields[5+shift]) or not decimal(fields[6+shift]) or not pointer(fields[7+shift]) or not decimal(fields[8+shift]) then return nil end
   if name=='w6rc' then out.source=true end
  end
  return out
 end
 function source.resetAfterRestart()
  -- Preserve every PCM/session/extent ledger. Clear only obsolete IPC after
  -- a full module registry proves this standalone owner is absent.
  local s=observe(true);local modules=module_snapshot()
  if not s.id or not modules then return false,'无法确认采音组件退出，原音保留' end
  if modules.source then return false,'采音组件仍驻留，请完整重启手表后再恢复' end
  local names={'start','status','go','stop','phone','receipt','pause','prefix','ready'}
  for _,kind in ipairs(names)do
   local name=path(kind);local raw,err=read(name,4096)
   if raw then
    local backup=BASE..'w6r-recovery-'..s.id..'-'..kind..'.txt'
    local prior,problem=read(backup,4096)
    if prior then
     if prior~=raw then return false,'恢复备份已有不同内容，原音保留' end
    elseif problem~=2 or not write_exact(backup,raw) then return false,'恢复备份未完成，原音保留' end
   elseif err~=2 then return false,'原状态读取失败，原音保留' end
  end
  local latest=module_snapshot();if not latest or latest.source then return false,'采音组件状态变化，请重试' end
  for _,kind in ipairs(names)do local name=path(kind);if not missing(name) and (not remove(name) or not missing(name)) then return false,'恢复清理未完成，原音保留' end end
  id=nil;rate=nil;last_seq=0;cached=nil;startup_deadline=0;known_loaded=false;unloaded=false
  return true
 end
 function source.diagnostics()
  -- Pull-only fixed IPC metadata. No PCM reads, controls, native calls or IDs.
  local raw,errno=read(path('status'),1536)
  local d={status_bytes=type(raw)=='string' and #raw or 0,read_errno=errno or 0,frame_valid=false,recovery_code=recovery.code}
  for key,value in pairs(recovery)do if key~='code' then d['recovery_'..key]=value end end
  if type(raw)=='string' and #raw==1536 then
   d.header_equal=raw:sub(1,64)==raw:sub(1473,1536)
   local length=hexfield(raw,41,8);local check=hexfield(raw,54,8)
   d.checksum_valid=length~=nil and length>=1 and length<=1408 and check==crc(field(raw,64,length))
   if d.checksum_valid and type(decode)=='function' then
    local good,s=pcall(decode,field(raw,64,length))
    if good and type(s)=='table' then
     d.native_phase=type(s.phase)=='string' and s.phase:match('^[a-z_]+$') and s.phase or 'unknown'
     for _,key in ipairs({'error_code','produced_offset','readable_offset','reclaimed_offset','status_sequence'})do if uint(s[key]) then d[key]=s[key] end end
     local prior_id,prior_rate,prior_seq=id,rate,last_seq
     local accepted,parsed=pcall(frame,raw)
     id,rate,last_seq=prior_id,prior_rate,prior_seq
     d.frame_valid=accepted and parsed~=nil
    end
   end
  end
  return d
 end
 function source.tick()if alive then observe(false) end end
 function source.start(settings)
  if not alive or not enabled then return false,'连续采集候选功能尚未启用' end
  if type(asset)~='string' or not asset:match('^vs%-continuous%-source%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]%.elf$') then return false,'连续采集组件身份无效' end
  if type(settings)~='table' or not nonce(settings.id) or (settings.rate~=8000 and settings.rate~=16000) then return false,'会议身份无效' end
  local prior=observe(true);if prior.phase~='idle' or prior.owner_present~=false or prior.safe_to_start~=true then return false,'旧录音状态尚未安全关闭' end
  if not missing(BASE..'vs-mc-'..settings.id..'-00000000.session') then return false,'录音身份已经使用，原始文件保留' end
  id=settings.id;rate=settings.rate
  local slots=settings.slots or (settings.archive_only and 2048 or 128);local seconds=settings.max_seconds or 43200
  if not uint(slots) or slots<2 or slots>2048 or not uint(seconds) or seconds<1 or seconds>43200 then return false,'会议缓存或时限无效' end
  if not write_exact(path('start'),control('START   ',1,{rate=rate,slots=slots,seconds=seconds,archive_only=settings.archive_only})) then return false,'未能保存用户启动身份' end
  local old,err=read(path('status'),1536)
  if old==nil and err==2 and not write_exact(path('status'),string.rep(' ',1536)) then return false,'状态邮箱准备失败' end
  if not write_exact(path('go'),string.rep(' ',512)) then return false,'开始门控准备失败' end
  if execute('insmod '..BASE..asset..' '..MODULE)~=true then cached=nil;return false,'连续采集组件加载未确认，未发送GO' end
  known_loaded=true;unloaded=false;startup_deadline=now()+10000;next_poll=0;cached=nil
  for _,name in ipairs({'stop','phone','receipt','pause'})do if not write_exact(path(name),string.rep(' ',512)) then return false,'已加载组件，控制状态未确认；未开始收音' end end
  if not write_exact(path('go'),control('GO      ',2)) then return false,'开始请求未确认，组件仍需核对' end
  return true
 end
 function source.list(offset,limit)
  if not alive or not even(offset) or not uint(limit) or limit<1 or limit>8 then return nil end
  local s=observe(false);if not s.identity_persisted or not s.extent_count or offset<s.reclaimed_offset or offset>s.readable_offset then return nil end
  if offset~=s.reclaimed_offset then return nil end
  local out={};local expected=offset
  for seq=s.extent_first_seq,s.extent_first_seq+math.min(s.extent_count,limit)-1 do
   local e=descriptor(seq,s)
   if not e then break end
   if e.start~=expected then return nil end;out[#out+1]=copy(e);expected=e.start+e.length
  end
  return out
 end
 function source.read(offset,length)
  if not alive or not even(offset) or not even(length) or length<2 or length>2048 then return nil end
  local s=observe(false);if not s.identity_persisted or offset<s.reclaimed_offset or offset+length>s.readable_offset then return nil end
  local out={};local left=length
  -- spool.c seals every normal extent at65536; only its final EOF extent is
  -- shorter. Sequence1 starts at zero; immutable absolute offsets still verify
  -- the calculation. Do not CRC-scan unrelated queued extents per2KiB packet.
  local first=offset//65536+1
  if first<s.extent_first_seq or first>=s.extent_first_seq+s.extent_count then return nil end
  for seq=first,math.min(first+1,s.extent_first_seq+s.extent_count-1) do
   local e=descriptor(seq,s)
   if e and offset>=e.start and offset<e.start+e.length then
    local want=math.min(left,e.start+e.length-offset);local ok,f=pcall(open,extent_path(seq,'.pcm'),'rb');if not ok or not f then return nil end
    local good,data=pcall(function()if f:seek('set',offset-e.start)~=offset-e.start then return nil end;return f:read(want) end)
    local closed,result=pcall(f.close,f);if not good or not closed or not result or type(data)~='string' or #data~=want then return nil end
    out[#out+1]=data;offset=offset+want;left=left-want;if left==0 then return table.concat(out) end
   end
  end
  return nil
 end
 function source.stop(reason)
  if not alive then return false end
  local reasons={user=1,cache_low=2,cache_limit=2,low_space=3,protocol_error=4,capture_error=4,view_closed=4,retry_stop=4,storage_error=5,timeout=6}
  local value=reasons[reason];if not value then return false end
  local s=observe(false);if not id then return false end;if s.phase=='closed' then return true end
  local seq=command_sequence('STOP    ','stop');return seq~=nil and seq<=0xffffffff and write_exact(path('stop'),control('STOP    ',seq,{reason=value}))
 end
 function source.detach()alive=false;return true end
 function source.pause()
  if not alive then return false end
  local s=observe(true);if not s.archive_only or not s.identity_persisted or (s.phase~='recording' and s.phase~='pausing' and s.phase~='paused') then return false,'当前会议尚未进入可暂停状态' end
  if s.phase=='pausing' or s.phase=='paused' then return true end
  local old=exact(path('pause'),512);local prior=parse_control(old,'PAUSE   ',id) or parse_control(old,'RESUME  ',id)
  local seq=prior and prior.sequence+1 or old==string.rep(' ',512) and 1
  return seq and seq<=0xffffffff and write_exact(path('pause'),control('PAUSE   ',seq)) or false
 end
 function source.resume()
  if not alive then return false end
  local s=observe(true);if not s.archive_only or not s.identity_persisted or (s.phase~='paused' and s.phase~='resuming') then return false,'请先确认会议已暂停' end
  if s.phase=='resuming' then return true end
  local old=exact(path('pause'),512);local prior=parse_control(old,'PAUSE   ',id) or parse_control(old,'RESUME  ',id)
  return prior and prior.sequence<0xffffffff and write_exact(path('pause'),control('RESUME  ',prior.sequence+1)) or false
 end
 function source.destroy()
  if not alive then return false end
  local s=observe(true)
  if s.phase~='closed' or s.safe_to_destroy~=true or s.owner_present~=false then return false end
  if not unloaded then if execute('rmmod '..MODULE)~=true then return false end;unloaded=true;known_loaded=false end
  for _,name in ipairs({'go','stop','phone','receipt','pause','start','status'})do
   if not missing(path(name)) then local ok,result=pcall(remove,path(name));if not ok or not result or not missing(path(name)) then return false end end
  end
  id=nil;rate=nil;last_seq=0;startup_deadline=0;phone_pair=nil;pending_release=nil;cached={phase='idle',continuous=true,owner_present=false,safe_to_start=true,safe_to_destroy=false};descriptors={};order={};return true
 end
 return source
end
return create
