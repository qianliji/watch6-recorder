-- Cross-feature ordering. Hardware facts come from the injected owners.
local function create(a)
 local pending;local detached=false;local message='';local message_until=0;local cached_records={};local revision=-1;local selected
 local function note(text)message=text or '';message_until=a.now_ms()+7000 end
 local function rows()
  local next_revision=a.catalog.revision and a.catalog.revision() or 0
  if next_revision~=revision then
   cached_records=a.catalog.list();table.sort(cached_records,function(x,y)if (x.created or 0)==(y.created or 0)then return x.id>y.id end;return (x.created or 0)>(y.created or 0)end);revision=next_revision
  end
  return cached_records
 end
 local function find(id)for _,r in ipairs(rows())do if r.id==id then return r end end end
 local function capture_busy()local p=a.recorder.state().phase;return p~='idle' and p~='saved' end
 -- Rejecting another tap must not consume an already authorized intent.
 local function fail(text)note(text);return false,text end
 local function launch_record()
  if not a.capture_allowed() then return false end
  pending=nil
  if a.recorder.state().phase=='saved' then local ok,err=a.recorder.next();if not ok then return fail(err or '上一条录音尚未结束，请检查状态')end end
  local ok,err=a.recorder.start();if not ok then note(err or '录音未开始，请检查状态')end;return ok,err
 end
 local out={}
 function out.act(action,id)
  if detached then return false end
  if action=='select' then selected=id;return true end
  if action=='cancel_pending' or action=='cancel_prepare' then
   local intent=pending;pending=nil
   if intent and intent.kind=='record' then note('已取消这次录音准备，麦克风未打开');return true end
   if intent or action=='cancel_prepare' then
    local ok,err=a.archive.cancel();note(ok and '准备已取消，原音保留' or err or '准备取消尚未确认，原音保留');return ok,err
   end
   return true
  end
  if action=='record' then
   if pending then if pending.kind=='record' then return true end;return fail('正在准备上一项操作，可先点取消')end
   if capture_busy() then return fail('请先结束或恢复当前录音')end
   if a.capture_allowed()then return launch_record()end
   -- This intent exists only after this explicit tap, and expires with this view.
   local stopped=a.player.stop();local canceled=not stopped and a.archive.cancel()
   if not stopped and not canceled then return fail('回听组件退出未确认，原音保留；请完整重启手表后重试')end
   pending={kind='record',deadline=a.now_ms()+12000};note('正在结束回听，随后开始这次录音');return true
  end
  if action=='next_record' then pending=nil;return a.recorder.next()end
  if action=='stop_record' then pending=nil;return a.recorder.stop()end
  if action=='pause_record' then return a.recorder.pause()end
  if action=='resume_record' then return a.recorder.resume()end
  if action=='recover_record' then pending=nil;return a.recorder.recover()end
  if action=='connect' then local ok,err=a.transfer.connect();if not ok then note(err or '正在等待手机，请检查首次授权')end;return ok end
  if action=='disconnect' then local stop=a.transfer.disconnect or a.transfer.cancel;local ok,err=stop();note(ok and '正在断开连接，原音保留' or err);return ok end
  if action=='cancel_export' then local ok,err=a.transfer.cancel();note(ok and '已请求暂停发送，手表原音保留' or err);return ok end
  if action=='pause_playback' then return a.player.pause()end
  if action=='resume_playback' then return a.player.resume()end
  if action=='stop_playback' then pending=nil;return a.player.stop()end
  if action=='play' or action=='export' then
   if pending then if pending.kind==action and pending.id==id then return true end;return fail('正在准备上一项操作，可先点取消')end
   if capture_busy()then return fail('请先结束并保存当前录音')end
   local row=find(id);if not row or row.status~='saved' then return fail('这条录音还未完整封存，原音保留')end
   if not a.prepare_allowed()then return fail('请先结束当前回听或发送，再选择另一条')end
   selected=id
   local info=a.archive.info()
   if info and info.id==id then
    local ok,err;if action=='play' then ok,err=a.player.play(info)else ok,err=a.transfer.start(info)end
    if not ok then note(err or '操作未开始，原音保留')end;return ok,err
   end
   local ok,err=a.archive.prepare(row)
   if not ok then return fail(err or '无法准备完整录音，原音保留')end
   pending={kind=action,id=id,deadline=a.now_ms()+600000};note('正在完整校验原音，请稍候');return true
  end
  return false
 end
 function out.tick()
  if detached then return end
  a.recorder.tick();a.archive.tick();a.player.tick();a.transfer.tick()
  if pending then
   local intent=pending
   if a.now_ms()>=intent.deadline then
    pending=nil;if intent.kind~='record' then a.archive.cancel()end;note('准备超时，原音保留，请重试');return
   end
   if intent.kind=='record' then
    if a.capture_allowed() then launch_record()end
   else
    local s=a.archive.state();local info=a.archive.info()
    if s.phase=='error' or s.phase=='retained' then pending=nil;fail(s.message or '原音准备未完成，请检查状态')
    elseif info and info.id==intent.id then
     pending=nil;message='';message_until=0
     local ok,err;if intent.kind=='play' then ok,err=a.player.play(info)else ok,err=a.transfer.start(info)end
     if not ok then note(err or '操作未开始，原音保留')end
    end
   end
  end
 end
 function out.view()
  local t,p=a.transfer.state(),a.player.state();local ar=a.archive.state()
  local text=a.now_ms()<message_until and message or ''
  if text=='' then
   if pending and pending.kind=='record' then text='正在结束回听，随后开始这次录音'
   elseif pending then text=ar.message or '正在校验与准备完整原音'
   elseif t.active and t.message then text=t.message
   elseif p.message and p.phase~='idle' then text=p.message end
  end
  return a.recorder.state(),rows(),{playback=p,transfer=t,phone=a.transfer.phone(),message=text~='' and text or nil,
   pending_action=pending and pending.kind or nil,record_preparing=pending~=nil and pending.kind=='record',
   preparing_action=pending and pending.kind~='record' and pending.kind or nil,
   preparing_id=pending and pending.kind~='record' and pending.id or nil,selected_id=selected}
 end
 function out.pending()return pending and {kind=pending.kind,id=pending.id,deadline=pending.deadline}or nil end
 function out.detach()pending=nil;detached=true;a.archive.detach();a.player.detach();a.transfer.detach();a.recorder.detach()end
 return out
end
return create
