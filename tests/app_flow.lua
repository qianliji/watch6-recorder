return function(make)
 local n=0;local function check(v,m)n=n+1;assert(v,m)end
 local now=0;local starts,plays,exports,prepare,stops=0,0,0,0,0
 local record={phase='idle'};local safe=true;local can_prepare=true;local archive_state={phase='idle'};local info
 local row={id='1111111111111111',rate=8000,bytes=16000,status='saved',created=1};local active=false
 local a={now_ms=function()return now end,capture_allowed=function()return safe end,prepare_allowed=function()return can_prepare end,
 catalog={revision=function()return 1 end,list=function()return {row}end},
 recorder={state=function()return record end,start=function()starts=starts+1;record.phase='preparing';return true end,next=function()record.phase='idle';return true end,stop=function()record.phase='saving';return true end,pause=function()return true end,resume=function()return true end,recover=function()return true end,tick=function()end,detach=function()end},
 archive={state=function()return archive_state end,info=function()return info end,prepare=function()prepare=prepare+1;archive_state={phase='preparing'};return true end,cancel=function()return true end,tick=function()end,detach=function()end},
 player={state=function()return {phase='idle'}end,play=function(i)plays=plays+1;return true end,stop=function()stops=stops+1;return true end,pause=function()return true end,resume=function()return true end,tick=function()end,detach=function()end},
 transfer={state=function()return {phase='idle',active=active}end,phone=function()return {connected=false}end,start=function(i)exports=exports+1;active=true;return true end,connect=function()return true end,cancel=function()active=false;return true end,tick=function()end,detach=function()end}}
 local app=make(a);app.tick();check(starts==0 and plays==0 and exports==0,'reattach and tick never acquire audio or export')
 check(app.act('play',row.id) and prepare==1 and plays==0,'play waits for complete validation')
 app.tick();check(plays==0,'no early player launch')
 info={id=row.id};archive_state.phase='ready';app.tick();check(plays==1 and exports==0,'one explicit validated play')
 app.tick();check(plays==1,'poll does not replay audio')
 check(app.act('export',row.id) and exports==1,'validated export targets selected recording')
 check(app.act('cancel_export') and not active,'cancel leaves recording catalog intact')
 safe=false;check(app.act('record') and starts==0 and app.pending().kind=='record','record tap waits for safe playback shutdown')
 local deadline=app.pending().deadline;local _,_,extra=app.view()
 check(extra.record_preparing and extra.pending_action=='record','pending microphone intent is visible and cancellable')
 now=1000;check(app.act('record') and app.pending().deadline==deadline and stops==1,'duplicate record tap preserves original deadline')
 app.tick();check(starts==0,'unknown close cannot open microphone')
 safe=true;app.tick();check(starts==1 and not app.pending(),'one tap starts only after close proof')
 check(not app.act('play',row.id) and plays==1,'recording and playback cannot overlap')
 record.phase='saved';check(app.act('next_record') and starts==1,'next only returns to ready')
 safe=false;app.act('record');now=13000;safe=true;app.tick();check(starts==1,'expired tap cannot later start recording')
 info=nil;record.phase='idle';app.act('export',row.id);app.act('cancel_prepare');info={id=row.id};app.tick();check(exports==1,'cancelled preparation never later exports')
 safe=false;app.act('record');check(app.act('cancel_pending') and not app.pending(),'explicit cancellation consumes microphone intent');safe=true;app.tick();check(starts==1,'cancelled record cannot launch on later exit proof')
 can_prepare=false;check(not app.act('play',row.id) and plays==1,'pinned cache cannot be overwritten')
 app.detach();check(not app.act('record') and starts==1 and plays==1,'detach has no start side effects and rejects stale callbacks')
 return {passed=true,assertions=n,microphone_calls=0,device_calls=0}
end
