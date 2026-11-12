-- A prepared immutable WAV is pinned until the native exporter is proven gone.
local function create(a)
 local link=assert(a.link);local waiting;local detached=false;local completed={};local message;local local_result;local cancel_requested=false
 local function clock()return a.now_ms()end
 local function status()return link.exportStatus()end
 local function terminal(p)return p=='saved' or p=='cancelled' or p=='error' or p=='idle'end
 local function durable_saved(s)
  -- Native "saved" is published only after the receiver's durable, complete
  -- ACK. Keep its byte frontier and error code consistent before using it.
  return s.phase=='saved' and type(s.total_bytes)=='number' and s.total_bytes>0
   and s.total_bytes%2==0 and s.next==s.total_bytes and s.code==0
 end
 local function finish_waiting(phase)
  local_result={phase=phase,recording_id=waiting.info.id,total_bytes=waiting.info.total_bytes or 0,next=0}
  waiting=nil
 end
 local function no_job(live)
  return live.nonce_ready==true and live.background_owned==false and
   ({initializing=true,starting=true,connecting=true,reconnecting=true,connected=true})[live.phase]==true
 end
 local out={}
 function out.restore()return link.restore()end
 function out.connect()
  if detached then return false end
  local ok,err=a.prepare();if not ok then return false,err end
  return link.start()
 end
 function out.start(info)
  if detached then return false end
  if type(info)~='table' or not info.id then return false,'录音信息无效'end
  if waiting then if waiting.info.id==info.id then return true end;return false,'正在准备上一条发送'end
  local s=status()
  local live=link.getStatus()
  if s.safe_to_release~=true and not no_job(live) then return false,'上一条发送仍在退出，请稍候'end
  local ok,err=a.prepare();if not ok then return false,err end
  if not link.start()then return false,'连接组件未启动，手表原音保留'end
  waiting={info=info,deadline=clock()+15000};message=nil;local_result=nil;cancel_requested=false;return true
 end
 function out.cancel()
  if detached then return false end
  if waiting then finish_waiting('cancelled');local ok,err=link.stop();message=not ok and (err or '发送已撤销，连接退出尚未确认')or nil;return ok,err end
  if cancel_requested then return true end
  local s=status();if not terminal(s.phase)then
   local ok,err=link.cancel_export();if ok then cancel_requested=true end;return ok,err
  end
  return link.stop()
 end
 function out.disconnect()
  if detached then return false end
  if waiting then finish_waiting('cancelled')end
  local ok,err=link.stop();if ok and not terminal(status().phase)then cancel_requested=true end
  message=not ok and err or nil;return ok,err
 end
 function out.tick()
  if detached then return end
  link.tick()
  if waiting then
   if clock()>=waiting.deadline then finish_waiting('error');link.stop();message='手机连接未就绪，手表原音保留'
   elseif link.getStatus().nonce_ready then
    local job=waiting;waiting=nil;local ok,err=link.begin_export(job.info)
    if not ok then local_result={phase='error',recording_id=job.info.id,total_bytes=job.info.total_bytes or 0,next=0};link.stop();message=err or '发送未开始，手表原音保留'end
   end
  end
  local s=status()
  if terminal(s.phase)then cancel_requested=false end
  if durable_saved(s) and s.recording_id and not completed[s.recording_id] then
   -- This is only a UI/catalog annotation. It never authorizes source deletion.
   completed[s.recording_id]=true
   if a.on_saved then a.on_saved(s.recording_id,s)end
  end
 end
 function out.safe_to_release()
  local live=link.getStatus()
  -- A nonce-initialized foreground connection has no WAV job or open source.
  -- An unknown/releasing owner never gets this exception. Once a job exists,
  -- only the native exit proof can release its immutable WAV lease.
  return not waiting and (status().safe_to_release==true or no_job(live))==true
 end
 function out.phone()
  local s=link.getStatus()
  return {connected=s.connected,phase=s.phase,transport=s.transport,transportReady=s.transportReady,
   identity_required=s.identity_required,error=s.error,message=s.message}
 end
 function out.state()
  local native=status();local s=local_result or native;local phase=s.phase or 'idle';local id=s.recording_id
  local invalid_saved=phase=='saved' and not durable_saved(s)
  if invalid_saved then phase='error'end
  if cancel_requested and not terminal(phase)then phase='cancelling'end
  if waiting then phase='connecting';id=waiting.info.id end
  local texts={connecting='正在连接手机，原音已保存在手表',sending='正在无线发送，离开页面也会继续',confirming='正在确认手机完整保存',cancelling='正在暂停发送，等待安全退出',saved='手机已完整保存，手表原音保留',cancelled='发送已暂停，可重新发送继续',error='发送未完成，手表原音保留'}
  local total=waiting and waiting.info.total_bytes or s.total_bytes or 0;local n=waiting and 0 or s.next or 0
  local live=link.getStatus()
  local reconnecting=live.phase=='reconnecting' and not terminal(phase) and phase~='cancelling'
  return {id=id,phase=phase,active=waiting~=nil or not terminal(phase) or live.background_owned and native.safe_to_release~=true,
   progress=total>0 and math.min(1,n/total) or 0,bytes=n,total_bytes=total,
   safe_to_release=out.safe_to_release(),message=message or invalid_saved and '手机完整保存尚未确认，手表原音保留'
    or reconnecting and '手机连接已中断，正在恢复发送；原音保留' or texts[phase],code=s.code}
 end
 function out.detach()waiting=nil;detached=true;link.detach()end
 return out
end
return create
