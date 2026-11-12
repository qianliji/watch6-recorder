-- Public recorder interface. Every capture start originates in start(), never attach/tick.
local function create(a)
 local source,catalog=a.source,a.catalog
 local state={phase='idle',bytes=0,rate=8000,message='离线录音 · 不需要手机或密钥'}
 local active,deadline,closed_at,pending,indexed=nil,0,nil,nil,nil
 local recorded_ms,recording_at=0,nil
 local stop_on_error_sent=false
 local function snapshot()local s={};for k,v in pairs(state)do s[k]=v end;return s end
 local function error(message)
  if active and state.id==active.id and not stop_on_error_sent then
   local current=source.status()
   if current.native_phase~='retained' and current.phase~='closed' and current.phase~='idle' then
    stop_on_error_sent=true;pcall(source.stop,'timeout')
   end
  end
  state.phase='recovery';state.message=message;return false,message
 end
 local out={}
 function out.state()return snapshot() end
 function out.records()return catalog.list() end
 function out.start()
  if state.phase~='idle' then return false,'请先结束或恢复上一条录音' end
  if not catalog.healthy() or #catalog.list()>=256 then return error('录音目录需要备份或恢复，未启动麦克风') end
  local current=source.status();if current.phase~='idle' or current.safe_to_start~=true then return error('旧采音状态未关闭，未启动麦克风') end
  local matched,message=a.prepare();if not matched then return error(message) end
  local id=a.nonce();if type(id)~='string' or #id~=16 or not id:match('^[0-9a-f]+$') or id=='0000000000000000' then return error('无法生成录音身份，未启动麦克风') end
  for _,r in ipairs(catalog.list())do if r.id==id then return error('录音身份重复，原音保留') end end
  active={id=id,rate=8000,bytes=0,status='pending',created=a.created_at and a.created_at() or 0}
  if not catalog.put(active) then active=nil;return error('录音目录写入失败，未启动麦克风') end
  local ok,problem=source.start({id=id,rate=8000,slots=2048,max_seconds=43200,archive_only=true})
  if not ok then active.status='failed';catalog.put(active);return error(problem or '采音组件未就绪，原音保留') end
  recorded_ms,recording_at,pending,indexed,stop_on_error_sent=0,nil,nil,nil,false
  deadline=a.now_ms()+12000;state={phase='preparing',id=id,bytes=0,rate=8000,message='正在开启麦克风，请稍候'};return true
 end
 function out.pause()
  if state.phase~='recording' then return false end
  local ok,message=source.pause();if not ok then return error(message or '暂停请求未确认，原音保留') end
  pending='pause';state.phase='pausing';deadline=a.now_ms()+10000;state.message='正在暂停';return true
 end
 function out.resume()
  if state.phase~='paused' then return false end
  local ok,message=source.resume();if not ok then return error(message or '继续请求未确认，原音保留') end
  pending='resume';state.phase='resuming';deadline=a.now_ms()+10000;state.message='正在继续';return true
 end
 function out.stop()
  if state.phase~='recording' and state.phase~='paused' and state.phase~='preparing' and state.phase~='pausing' and state.phase~='resuming' then return false end
  if not source.stop('user') then return error('结束请求未确认，原音保留') end
  pending='stop';state.phase='saving';state.message='正在保存录音，请稍候';deadline=a.now_ms()+25000;return true
 end
 function out.next()
  if state.phase~='saved' then return false end
  active=nil;closed_at=nil;pending=nil;indexed=nil;state={phase='idle',bytes=0,rate=8000,message='离线录音 · 不需要手机或密钥'};return true
 end
 function out.recover()
  if state.phase~='recovery' then return false end
  local existing=source.status()
  if existing.phase=='closed' and existing.safe_to_destroy and not existing.owner_present then
   state.phase='saving';closed_at=nil;deadline=a.now_ms()+10000;out.tick();return state.phase=='saved'
  end
  if existing.phase=='idle' and existing.safe_to_start then active=nil;deadline=0;state={phase='idle',bytes=0,rate=8000,message='未开始录音，可重新检查'};return true end
  local ok,message=source.resetAfterRestart()
  if not ok then return error(message or '请完整重启手表后恢复，原音保留') end
  active=nil;closed_at=nil;pending=nil;indexed=nil;state={phase='idle',bytes=0,rate=8000,message='已恢复。旧录音片段保留，可导出检查'};return true
 end
 function out.tick()
  source.tick();local s=source.status();local now=a.now_ms()
  if not s then return error('采音状态不可读，原音保留') end
  if state.phase=='recovery' then return true end -- no repeated writes/control while protected
  if s.phase=='idle' then return true end
  if not active and s.id and s.identity_persisted then
   for _,r in ipairs(catalog.list())do if r.id==s.id then active=r;break end end
   active=active or {id=s.id,rate=s.rate or 8000,bytes=s.produced_offset or 0,status='pending',created=0}
  end
  state.id=s.id;state.bytes=s.produced_offset or state.bytes;state.rate=s.rate or state.rate
  if s.phase=='recording' then
   if not recording_at then recording_at=now;if recorded_ms==0 then recorded_ms=math.floor(state.bytes/state.rate/2*1000) end end
   if pending~='stop' and pending~='pause' then pending=nil;state.phase='recording';state.message='正在录音 · 录音自动保存在手表';deadline=0 end
  elseif s.phase=='paused' then
   if recording_at then recorded_ms=recorded_ms+now-recording_at;recording_at=nil end
   if pending~='stop' and pending~='resume' then pending=nil;state.phase='paused';state.message='已暂停 · 点击继续录音';deadline=0 end
  elseif s.phase=='closed' and active then
   pending=nil;recording_at=nil;recorded_ms=math.floor(state.bytes/state.rate/2*1000)
   state.phase='saving';state.message='正在封存原音';closed_at=closed_at or now
   active.bytes=s.readable_offset or 0;active.rate=s.rate;active.status=s.tail_complete and s.whole_meeting_complete and 'saved' or 'partial'
   active.reason=s.stop_reason or '';active.error=s.error_code or 0
   if indexed~=active.id then
    if not catalog.put(active) then return error('原音已保留，但目录保存失败，请备份录音后恢复') end
    indexed=active.id
   end
   if s.safe_to_destroy and not s.owner_present then
    if source.destroy() then state.phase='saved';state.message=active.status=='saved' and '已保存在手表 · 原音不会自动删除' or '已保留部分录音 · 导出后检查';closed_at=nil
    elseif now-closed_at>=10000 then return error('原音已封存，组件退出未确认，请重启后恢复') end
   elseif now-closed_at>=10000 then return error('原音已封存，任务退出未确认，请重启后恢复') end
  elseif s.phase=='error' or s.native_phase=='retained' or s.phase=='blocked' then
   if active then active.bytes=s.readable_offset or active.bytes;active.status='partial';active.error=s.error_code or 0;catalog.put(active) end
   return error('录音已保护保留。请完整重启手表，再点恢复。')
  elseif s.phase=='starting' and deadline==0 then state.phase='preparing';deadline=now+12000;state.message='正在恢复采音状态'
  end
  state.duration_ms=recorded_ms+(recording_at and now-recording_at or 0)
  if deadline>0 and now>=deadline then return error('采音状态确认超时，原音保留，请重启后恢复') end
  return true
 end
 function out.detach()source.detach();return true end
 -- Reattach only observes the old owner. It never opens the microphone.
 out.tick();return out
end
return create
