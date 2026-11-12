return function(create)
 local assertions=0
 local function check(v)assert(v);assertions=assertions+1 end
 local time=0;local calls={start=0,job=0,stop=0,saved=0,restore=0};local ready=false;local background=false
 local s={phase='idle',safe_to_release=true,next=0,total_bytes=0};local job
 local link={restore=function()calls.restore=calls.restore+1;return true end,
  getStatus=function()return {phase=ready and 'connected' or 'idle',nonce_ready=ready,background_owned=background,connected=ready}end,
  exportStatus=function()return s end,start=function()calls.start=calls.start+1;return true end,
  begin_export=function(info)calls.job=calls.job+1;job=info;background=true;s={phase='connecting',safe_to_release=false,next=0,total_bytes=info.total_bytes,recording_id=info.id,code=0};return true end,
  stop=function()calls.stop=calls.stop+1;return true end,cancel_export=function()calls.stop=calls.stop+1;return true end,
  tick=function()end,detach=function()end}
 local a={link=link,now_ms=function()return time end,prepare=function()return true end,on_saved=function()calls.saved=calls.saved+1 end}
 local t=create(a);t.restore();check(calls.restore==1 and calls.start==0 and calls.job==0)
 local info={id='1111111111111111',total_bytes=8000}
 check(t.start(info));t.tick();check(calls.job==0 and t.state().active and not t.safe_to_release())
 ready=true;t.tick();t.tick();check(calls.job==1 and job==info)
 s.phase='sending';s.next=4000;check(t.state().progress==0.5)
 check(not t.start({id='2222222222222222'}));check(calls.job==1)
 s.phase='confirming';s.next=8000;t.tick();check(calls.saved==0 and t.state().phase=='confirming')
 s.phase='saved';t.tick();t.tick();check(calls.saved==1 and t.state().active and not t.safe_to_release())
 s.safe_to_release=true;check(t.safe_to_release() and not t.state().active)
 background=false;ready=false;check(t.start(info));check(t.cancel());ready=true;t.tick();check(calls.job==1 and t.state().id==info.id and t.state().phase=='cancelled')
 ready=false;s.safe_to_release=true;check(t.start(info));time=16000;t.tick();check(calls.job==1 and calls.stop==2 and not t.state().active and t.state().phase=='error')
 -- An explicit connect may be reused once initialized; it is not an export.
 ready=true;s.safe_to_release=false;check(t.safe_to_release() and not t.state().active)
 check(t.start(info));t.tick();check(calls.job==2 and not t.safe_to_release())
 t.detach();ready=true;t.tick();check(calls.job==2 and not t.start(info))
 return {passed=true,assertions=assertions}
end
