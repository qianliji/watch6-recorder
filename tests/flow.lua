return function(make_recorder,make_catalog,json)
 local assertions=0
 local function check(v,m)assertions=assertions+1;assert(v,m)end
 local memory={};local writes=0
 local a={base='owned/',read=function(n)return memory[n],memory[n] and nil or 2 end,
  write=function(n,s)writes=writes+1;memory[n]=s;return true end,encode=json.encode_local,decode=json.decode_local}
 local catalog=make_catalog(a);check(catalog.healthy(),'empty catalog healthy')
 check(catalog.put({id='1111111111111111',rate=8000,bytes=0,status='pending'}),'initial catalog write')
 check(catalog.put({id='1111111111111111',rate=8000,bytes=16000,status='saved'}),'second generation')
 local restored=make_catalog(a);check(restored.list()[1].bytes==16000,'restore newest catalog')
 memory['owned/catalog-0.txt']='torn'
 restored=make_catalog(a);check(restored.healthy() and restored.list()[1].bytes==0,'torn newest falls back to prior generation')
 memory['owned/catalog-1.txt']='torn';check(not make_catalog(a).healthy(),'both corrupt do not reset metadata')
 memory={};catalog=make_catalog(a);writes=0
 local native={phase='idle',safe_to_start=true};local now=0;local starts,stops,destroys,pauses,resumes=0,0,0,0,0;local recoverable=false
 local source={status=function()return native end,tick=function()end,start=function(s)starts=starts+1;native={phase='starting',id=s.id,rate=8000,identity_persisted=false};return true end,
 pause=function()pauses=pauses+1;return true end,resume=function()resumes=resumes+1;return true end,
 stop=function()stops=stops+1;return true end,destroy=function()destroys=destroys+1;native={phase='idle',safe_to_start=true};return true end,
 resetAfterRestart=function()if not recoverable then return false,'owner live' end;native={phase='idle',safe_to_start=true};return true end,detach=function()end}
 local ids=0;local function nonce()ids=ids+1;return string.format('%016x',ids)end
 local core=make_recorder({source=source,catalog=catalog,prepare=function()return true end,nonce=nonce,now_ms=function()return now end})
 check(starts==0,'attach never starts microphone')
 check(core.start() and starts==1 and core.state().phase=='preparing','explicit start only')
 check(not core.start() and starts==1,'double start rejected')
 core.tick();check(core.state().phase=='preparing','wait for microphone confirmation')
 native={phase='recording',id='0000000000000001',identity_persisted=true,rate=8000,produced_offset=16000,readable_offset=0}
 now=500;core.tick();check(core.state().phase=='recording','native recording acknowledgement')
 now=1000;core.tick();check(core.state().duration_ms==1500,'timer counts after native start')
 check(core.pause() and pauses==1,'explicit pause')
 core.tick();check(core.state().phase=='pausing','old recording snapshot does not cancel pause intent')
 now=1200;native.phase='paused';core.tick();local paused_ms=core.state().duration_ms
 now=5000;core.tick();check(core.state().duration_ms==paused_ms,'paused time excluded')
 check(core.resume() and resumes==1,'explicit resume')
 core.tick();check(core.state().phase=='resuming','old paused snapshot does not cancel resume intent')
 now=5100;native.phase='recording';core.tick();check(core.state().phase=='recording','resume acknowledged')
 check(core.stop() and stops==1,'explicit stop')
 core.tick();check(core.state().phase=='saving' and stops==1,'stop intent not overwritten or repeated')
 native={phase='closed',id='0000000000000001',identity_persisted=true,rate=8000,produced_offset=32000,readable_offset=32000,tail_complete=true,whole_meeting_complete=true,owner_present=true,safe_to_destroy=false}
 now=6000;core.tick();local saved_writes=writes;check(core.state().phase=='saving' and destroys==0,'wait for actual owner exit')
 now=6500;core.tick();check(writes==saved_writes,'closed-state polling does not repeatedly write catalog')
 native.owner_present=false;native.safe_to_destroy=true;core.tick()
 check(core.state().phase=='saved' and destroys==1,'sealed local recording releases without phone')
 check(core.records()[1].status=='saved' and core.records()[1].bytes==32000,'local record indexed')
 check(core.next() and core.state().phase=='idle' and starts==1,'next does not acquire microphone')
 check(core.start() and starts==2,'next explicit recording independent of cloud/phone')
 native={phase='error',native_phase='retained',id='0000000000000002',identity_persisted=true,rate=8000,produced_offset=1000,readable_offset=1000,error_code=12}
 core.tick();check(core.state().phase=='recovery' and destroys==1,'retained becomes bounded recovery UI; no forced unload')
 local protected_writes=writes;core.tick();core.tick();check(writes==protected_writes,'protected state does not repeatedly write catalog')
 check(not core.recover() and starts==2,'live owner cannot be reset')
 recoverable=true;check(core.recover() and core.state().phase=='idle' and starts==2,'explicit recovery preserves audio and does not start')
 check(core.records()[2].status=='partial','retained take stays partial')
 check(core.start() and starts==3,'start after recovery explicit')
 now=now+13000;core.tick();check(core.state().phase=='recovery','preparation timeout does not spin forever')
 check(stops==2,'preparation timeout requests one protective stop for the same take')
 core.detach();check(starts==3 and destroys==1,'detach does not reacquire or force free')
 local failed_catalog={healthy=function()return true end,list=function()return {}end,put=function()return false end}
 native={phase='idle',safe_to_start=true}
 local blocked=make_recorder({source=source,catalog=failed_catalog,prepare=function()return true end,nonce=nonce,now_ms=function()return now end})
 check(not blocked.start() and starts==3,'metadata failure stops before microphone')
 local unsupported=make_recorder({source=source,catalog=catalog,prepare=function()return false,'unsupported firmware' end,nonce=nonce,now_ms=function()return now end})
 check(not unsupported.start() and starts==3,'unsupported firmware never records')
 return {passed=true,assertions=assertions,microphone_calls=0,network_calls=0}
end
