-- Owned MiFitness phone transport. Files are bounded IPC, never Lua FFI.
-- Explicit exports survive face recreation / sleep in the native worker.
local function create(a)
 local root,module='/data/watch6recorder/','w6rxlink'
 local nonce,phase='', 'idle'
 local started,requested,closing,detached=false,false,false,false
 local tx,rx,hb,serial=0,0,0,0
 local current,export,last_export=nil,nil,nil
 local export_owned,safe,observed=false,false,false
 local last_hb,next_attempt,release_at,last_status=0,0,0,''
 local receiver=a.on_message
 local api={}
 local function retired_owner()
  if a.retired_module_present==nil then return false end
  if type(a.retired_module_present)~='function'then return nil end
  local ok,present=pcall(a.retired_module_present)
  if not ok or type(present)~='boolean'then return nil end
  return present
 end
 local function migration_message(present)
  return present==true and '旧版直连组件仍驻留，请完整重启手表；原录音保留'
   or '旧版连接状态未确认，请点击连接重试；原录音保留'
 end
 local function now()return a.now_ms()end
 local function read(name,n)return a.read(root..name,n)end
 local function write(name,s)return a.write(root..name,s)==true end
 local function run(s)return a.execute(s)==true end
 local function hex(s,n)return type(s)=='string' and #s==n and s:match('^[0-9a-f]+$')~=nil end
 local function header(id,seq,len)local s=string.format('VSL1 %s %08x %04x\n',id,seq,len);return s..string.rep(' ',64-#s)end
 local function control(name,id,seq)local h=header(id,seq,0);return write(name,h..h)end
 local function frame(raw,size,id,body_capacity)
  if type(raw)~='string' or #raw~=size or raw:sub(1,64)~=raw:sub(-64) then return end
  local n,s,l=raw:sub(1,64):match('^VSL1 ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+)\n')
  if not hex(n,16) or not hex(s,8) or not hex(l,4) or (id and id~=n)then return end
  local seq,len=tonumber(s,16),tonumber(l,16)
  if raw:sub(1,64)~=header(n,seq,len) or len>(body_capacity or size-128)then return end
  return {nonce=n,sequence=seq,length=len,payload=raw:sub(65,64+len),raw=raw}
 end
 local function status(id)
  local f=frame(read('w6r-link-status.txt',256),256,id,128);if not f or f.length~=0 then return end
  local values={};for k,v in f.raw:sub(65,192):gmatch('([a-z_]+)=([^\n ]+)')do if values[k]then return end;values[k]=v end
  local function number(k)local v=values[k];if hex(v,8)then return tonumber(v,16)end end
  local p,pid,ack,count,err=values.phase,number('pid'),number('tx_ack'),number('rx_seq'),number('error')
  if not ({initializing=true,starting=true,connecting=true,reconnecting=true,connected=true,closing=true,closed=true,error=true,retained=true})[p] or not pid or not ack or not count or not err then return end
  f.phase,f.pid,f.tx_ack,f.rx_seq,f.error,f.phone=p,pid,ack,count,err>=0x80000000 and err-0x100000000 or err,number('phone')==1
  return f
 end
 local function export_status(id)
  local f=frame(read('w6r-export-status.txt',512),512,id,384);if not f or f.length<2 then return end
  local ok,s=pcall(a.decode,f.payload);if not ok or type(s)~='table'then return end
  local phases={idle=true,connecting=true,sending=true,confirming=true,saved=true,cancelled=true,error=true}
  if not phases[s.phase] or type(s.next)~='number' or type(s.total_bytes)~='number' or s.next<0 or s.next%2~=0 or s.next>s.total_bytes or s.total_bytes>134348800 or type(s.job_sequence)~='number' or type(s.pid)~='number' or type(s.source_closed)~='boolean' or type(s.worker_done)~='boolean' or type(s.code)~='number' then return end
  if s.phase~='idle' and not hex(s.recording_id,16)then return end
  s.nonce,s.sequence=f.nonce,f.sequence;return s
 end
 local function pid_absent(pid)
  if not pid or pid<1 then return false end
  local cmd,ce=a.read('/proc/'..tostring(pid)..'/cmdline',1024)
  local stat,se=a.read('/proc/'..tostring(pid)..'/status',2048)
  return cmd==nil and stat==nil and ce==2 and se==2
 end
 local function modules()
  if a.module_present~=nil then
   if type(a.module_present)~='function'then return nil,true end
   local ok,present=pcall(a.module_present,module)
   if not ok or type(present)~='boolean'then return nil,true end
   return present,true
  end
  local raw=a.read('/proc/modules',8193)
  if type(raw)~='string' or #raw>8192 or raw~='' and (raw:sub(-1)~='\n' or raw:find('\n\n',1,true))then return nil end
  local present=false
  for line in raw:gmatch('([^\n]+)\n')do
   local name=line:match('^([%w_.-]+),');if not name then return nil end
   if name==module then if present then return nil end;present=true end
  end
  return present
 end
 local function notify(s)if type(a.on_status)=='function'then a.on_status(s)end end
 local function terminal(s)return s and (s.phase=='saved' or s.phase=='cancelled' or s.phase=='error')end
 local function reap()
  -- UI/status files cannot authorize unloading; native uninit checks the actual
  -- worker PID and drained callbacks again under the firmware's PID lock.
  if not current or (current.phase~='closed' and current.phase~='error')then return false end
  if export_owned and (not export or not terminal(export) or not export.worker_done or not export.source_closed)then return false end
  if not pid_absent(current.pid) or not run('rmmod '..module) or modules()~=false then return false end
  safe=true;started=false;export_owned=false;last_export=export;return true
 end
 local function crc(s)local c=0xffffffff;for i=1,#s do c=c~s:byte(i);for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0)end end;return c~0xffffffff end
 local function job_status(id)
  local b=read('w6r-export-job.txt',512)
  if type(b)~='string' or #b~=512 or b:sub(1,6)~='W6RE1\n' or b:sub(7,22)~=id or b:sub(23,24)~='\n ' or b:sub(481,496)~=id or b:sub(497,507)~='\nend=W6RE1\n' or b:sub(508,512)~=string.rep(' ',5) or b:sub(113,464)~=string.rep(' ',352) or b:sub(105,112)~='00000001' then return end
  for _,f in ipairs({{25,40},{41,48},{49,56},{57,72},{73,80},{81,96},{97,104},{473,480}})do if not hex(b:sub(f[1],f[2]),f[2]-f[1]+1)then return end end
  if b:sub(465,472)~=b:sub(97,104) or tonumber(b:sub(473,480),16)~=crc(b:sub(1,472))then return end
  local rate,total,seq=tonumber(b:sub(41,48),16),tonumber(b:sub(49,56),16),tonumber(b:sub(97,104),16)
  if (rate~=8000 and rate~=16000) or total<2 or total%2~=0 or total>134348800 or seq<1 then return end
  return {phase='connecting',next=0,total_bytes=total,job_sequence=seq,recording_id=b:sub(25,40),code=0,source_closed=false,worker_done=false}
 end
 local function adopt(readonly)
  if modules()~=true then return false end
  local old=status();if not old then return false end
  local job=job_status(old.nonce);local ex=export_status(old.nonce)
  if not job then return false end
  -- GUI can disappear between writing a valid job and the first native tick.
  -- Adopt that authorized descriptor; never replace it with a fresh nonce.
  if not ex or ex.job_sequence==0 then ex=job end
  if ex.job_sequence~=job.job_sequence or ex.recording_id~=job.recording_id or ex.total_bytes~=job.total_bytes then return false end
  if old.phase=='closed' or old.phase=='error'then
   if not readonly and terminal(ex) and ex.worker_done and ex.source_closed and pid_absent(old.pid) and run('rmmod '..module)then
    nonce,current,export,last_export,safe=old.nonce,old,ex,ex,true;phase=old.phase;return false
   end
  end
  nonce,current,export=old.nonce,old,ex;tx,rx=old.tx_ack,old.rx_seq
  phase,started,export_owned,safe=old.phase,true,true,false
  return true
 end
 function api.restore()
  if detached then return false end
  observed=true
  if started then return true end
  local present,authoritative=modules()
  if present==nil then safe=false;phase='retained';return false end
  if present then
   if adopt(true)then return true end
   local old=status();local ex=old and export_status(old.nonce)
   local raw=read('w6r-export-job.txt',512)
   if old and ex and ex.phase=='idle' and ex.job_sequence==0 and type(raw)=='string' and raw==string.rep(' ',512)then
    -- Observe a foreground-only owner's natural shutdown without renewing an
    -- idle connection just because a face was recreated.
    nonce,current,phase=old.nonce,old,old.phase;tx,rx=old.tx_ack,old.rx_seq
    started,closing,export_owned,safe=true,true,false,false;return true
   end
   safe=false;phase='retained';return false
  end
  local old=status();local raw,err=read('w6r-link-status.txt',256)
  if old then
   if old.pid<1 or not pid_absent(old.pid)then safe=false;phase='retained';return false end
   local ex=export_status(old.nonce);if ex then export,last_export=ex,ex end
  elseif raw~=nil or err~=2 then
   -- A native registry query can prove no old module owns an invalid lease
   -- frame (including an old blank mailbox). Preserve that file as-is. A read
   -- failure is still unknown, and a valid worker identity above still needs
   -- two ENOENT PID observations before audio scratch can be released.
   if not authoritative or type(raw)~='string'then safe=false;phase='retained';return false end
  end
  -- Module absence and, for a valid old lease, two independent ENOENT PID
  -- reads prove no exporter still refers to scratch audio. No writes occur.
  safe=true;phase='idle';return true
 end
 api.observe_existing=api.restore
 local function prepare()
  serial=serial+1;local value=os.time()*1000+math.floor(now())%1000+serial
  local old=status();nonce=string.format('%016x',value)
  while old and old.nonce==nonce do value=value+1;nonce=string.format('%016x',value)end
  local raw,err=read('w6r-link-status.txt',256)
  if raw==nil and err==2 and not write('w6r-link-status.txt',string.rep(' ',256))then return false end
  if not control('w6r-link-start.txt',nonce,0)then return false end
  if not run('insmod '..root..a.asset..' '..module)then return false end
  started,requested,closing,safe,export_owned=true,false,false,false,false
  tx,rx,hb=0,0,1;current,export=nil,nil;phase='starting';last_hb=now()
  local h=header(nonce,0,0)
  local ok=write('w6r-link-stop.txt',string.rep(' ',128)) and control('w6r-link-consumed.txt',nonce,0)
   and write('w6r-link-tx.msg',h..string.rep(' ',4096)..h)
   and write('w6r-export-job.txt',string.rep(' ',512))
   and write('w6r-export-cancel.txt',string.rep(' ',128))
   and write('w6r-export-status.txt',string.rep(' ',512))
  for slot=0,3 do ok=write('w6r-link-rx-'..slot..'.msg',h..string.rep(' ',4096)..h) and ok end
  if not ok or not control('w6r-link-heartbeat.txt',nonce,hb)then closing=true;control('w6r-link-stop.txt',nonce,0);return false end
  return true
 end
 local function attempt()
  -- An active export may belong to a previous face instance. Adopt first;
  -- never stop it merely because its Lua page was recreated.
  if adopt()then requested=false;return true end
  if prepare()then return true end
  local old=status()
  if old and not pid_absent(old.pid)then
   control('w6r-link-stop.txt',old.nonce,0);return false
  end
  run('rmmod '..module);return false
 end
 function api.start()
  if detached then return false end
  local retired=retired_owner();if retired~=false then return false,migration_message(retired)end
  if started and not closing and phase~='closed' and phase~='error' and phase~='retained'then return true end
  requested=true;release_at=now();next_attempt=now()+250;phase='releasing';attempt();return true
 end
 function api.on_message(callback)receiver=callback end
 function api.send(packet)
  if retired_owner()~=false then return false end
  if detached or not started or closing or export_owned or not current or current.phase~='connected' or not current.phone or tx~=current.tx_ack or tx>=0xfffffffe then return false end
  local ok,p=pcall(a.encode,packet);if not ok or type(p)~='string' or #p<2 or #p>4096 then return false end
  local seq=tx+1;local h=header(nonce,seq,#p)
  if not write('w6r-link-tx.msg',h..p..string.rep(' ',4096-#p)..h)then return false end
  tx=seq;return true
 end
 function api.begin_export(info)
  local retired=retired_owner();if retired~=false then return false,migration_message(retired)end
  if detached or not started or closing or export_owned or nonce=='' or phase=='closed' or phase=='error' or phase=='retained'then return false,'连接尚未准备好' end
  if type(info)~='table'then return false,'录音信息无效'end
  local cache=type(info.path)=='string' and info.path:match('^/data/watch6recorder/w6r%-play%-([0-9a-f]+)%.wav$')
  local id=info.recording_id or info.id
  if not hex(cache,16) or not hex(id,16) or not hex(info.archive_hash,16) or not hex(info.pcm_crc32,8) or (info.rate~=8000 and info.rate~=16000) or type(info.total_bytes)~='number' or info.total_bytes<2 or info.total_bytes%2~=0 or info.total_bytes>134348800 or (info.data_offset~=nil and info.data_offset~=44)then return false,'录音尚未完整校验'end
  local seq=1;local b='W6RE1\n'..nonce..'\n '..id..string.format('%08x%08x',info.rate,info.total_bytes)..info.archive_hash..info.pcm_crc32..cache..string.format('%08x00000001',seq)
  b=b..string.rep(' ',464-#b)..string.format('%08x',seq)
  b=b..string.format('%08x',crc(b))..nonce..'\nend=W6RE1\n';b=b..string.rep(' ',512-#b)
  if #b~=512 or not write('w6r-export-job.txt',b) or read('w6r-export-job.txt',512)~=b then return false,'导出任务未能保存'end
  export={phase='connecting',next=0,total_bytes=info.total_bytes,recording_id=id,job_sequence=seq,code=0,source_closed=true,worker_done=false}
  export_owned,safe=true,false;return true
 end
 function api.cancel_export()
  if not export_owned or not export then return false end
  return control('w6r-export-cancel.txt',nonce,export.job_sequence)
 end
 function api.stop()
  if not started then requested=false;return true end
  if export_owned and not api.cancel_export()then return false end
  if not control('w6r-link-stop.txt',nonce,0)then return false end
  requested,closing=false,true;return true
 end
 function api.tick()
  if detached then return nil end
  if not observed then api.restore()end
  local stamp=now()
  if requested then
   if stamp-release_at>12000 then requested=false;phase='retained';notify({phase=phase,connected=false});return nil end
   if stamp>=next_attempt then next_attempt=stamp+250;attempt()end
   return 250
  end
  if not started then return nil end
  if not export_owned and not closing and stamp-last_hb>=1000 then hb=hb+1;last_hb=stamp;if hb>=0xfffffffe or not control('w6r-link-heartbeat.txt',nonce,hb)then api.stop()end end
  local incoming=status(nonce)
  if not incoming then return 250 end
  if current and incoming.sequence<current.sequence then return 250 end
  current,phase=incoming,incoming.phase
  if incoming.raw~=last_status then last_status=incoming.raw;notify(api.getStatus())end
  if export_owned then
   local ex=export_status(nonce)
   if ex and ex.job_sequence==export.job_sequence and ex.recording_id==export.recording_id and (not export.sequence or ex.sequence>=export.sequence)then export=ex;last_export=ex end
   reap();return 500
  end
  if incoming.tx_ack>tx or incoming.rx_seq<rx or incoming.rx_seq-rx>4 then api.stop();return 250 end
  while rx<incoming.rx_seq do
   local seq=rx+1;local f=frame(read('w6r-link-rx-'..((seq-1)%4)..'.msg',4224),4224,nonce,4096)
   if not f or f.sequence~=seq then return 100 end
   local ok,p=pcall(a.decode,f.payload);if not ok or type(p)~='table'then api.stop();return 250 end
   if not control('w6r-link-consumed.txt',nonce,seq)then api.stop();return 250 end
   rx=seq;if type(receiver)=='function'then receiver(p)end
  end
  if closing or phase=='closed' or phase=='error'then reap()end
  return started and (phase=='connected' and 100 or 500) or nil
 end
 function api.getStatus()
  local s={phase=phase,connected=not closing and current and current.phase=='connected' and current.phone or false,
   transportReady=not closing and current and current.phase=='connected' or false,nonce_ready=started and not closing,
   background_owned=export_owned,pid=current and current.pid or 0,error=current and current.error or 0,
   transport='mifitness',identity_required=true}
  local retired=retired_owner()
  if retired~=false then
   s.phase='retained';s.connected=false;s.transportReady=false;s.nonce_ready=false;s.message=migration_message(retired)
  elseif s.connected then s.message='手机录音接收通道已就绪'
  elseif s.transportReady then s.message='运动健康底层通道已连接，等待手机接收端'
  elseif phase=='retained'then s.message='连接组件退出未确认，请重试或完整重启手表；原音保留'
  elseif phase=='error'then s.message='连接未完成，请检查运动健康、身份组件和手机接收端'
  else s.message='手机打开「Watch6 录音」并连接；首次需安装同签名录音连接组件'end
  return s
 end
 api.status=api.getStatus
 function api.exportStatus()
  local result={};for k,v in pairs(export or last_export or {phase='idle',next=0,total_bytes=0})do result[k]=v end
  -- An old direct owner may still reference this directory's immutable WAV.
  -- Its absence must be established; this route never stops or unloads it.
  result.safe_to_release=safe and retired_owner()==false;return result
 end
 function api.detach()detached=true;receiver=nil;return true end
 return api
end
return create
