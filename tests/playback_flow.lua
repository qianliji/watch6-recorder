return function(make_archive,make_playback,json)
 local checks=0;local function check(v,m)checks=checks+1;assert(v,m)end
 local memory={['/proc/modules']=''};local commands={};local clock=0;local serial=0;local deny_unload=false;local can_release=false
 local BASE='/data/watch6recorder/';local row={id='1234567890abcdef',status='saved'}
 local function put(s,p,v)return s:sub(1,p)..v..s:sub(p+#v+1)end
 local function crc(raw)local c=0xffffffff;for i=1,#raw do c=c~raw:byte(i);for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0)end end;return c~0xffffffff end
 local function status(phase,seq,done)
  local request=memory[BASE..'w6r-player-request.txt'];local op=request:sub(9,24);local id=request:sub(25,40);local cache=request:sub(89,104)
  local s={v=1,kind='player',operation_id=op,record_id=id,cache_id=cache,phase=phase,sequence=seq,pid=42,error=phase=='error' and -10 or 0,prepared_bytes=16000,total_bytes=16000,rate=8000,position_ms=phase=='done' and 1000 or 250,duration_ms=1000,archive_hash='deadbeeffeedbabe',pcm_crc32='1234abcd',done=done or false,handle_closed=done or false}
  local payload=json.encode(s);local header=string.rep(' ',64);header=put(header,0,'W6PST1\n');header=put(header,7,op);header=put(header,24,'seq=');header=put(header,28,string.format('%08x',seq));header=put(header,37,'len=');header=put(header,41,string.format('%08x',#payload));header=put(header,50,'crc=');header=put(header,54,string.format('%08x',crc(payload)))
  memory[BASE..'w6r-player-status.txt']=header..payload..string.rep(' ',1408-#payload)..header
  clock=clock+300
 end
 local adapter={asset='w6r-player-abcdefabcdef.elf',enabled=true,decode=json.decode,now_ms=function()return clock end,
  read=function(p,n)local raw=memory[p];if raw==nil then return nil,2 end;if #raw>n then return nil end;return raw end,
  write=function(p,s)memory[p]=s;return true end,nonce=function()serial=serial+1;return string.format('00000000%08x',serial)end,
  execute=function(cmd)commands[#commands+1]=cmd;if cmd:match('^insmod ')then memory['/proc/modules']='w6rplay,0,0,0,0,0,0,0\n';return true end;if cmd=='rmmod w6rplay'then if deny_unload then return false end;memory['/proc/modules']='';return true end;return false end,
  remove=function(p)memory[p]=nil;return true end,can_release=function()return can_release end}
 local archive=make_archive(adapter);local player=make_playback(archive)
 check(archive.safe_to_record(),'initial proven module absence permits capture')
 check(not archive.prepare('../bad'),'reject dynamic paths')
 check(archive.prepare(row),'explicit prepare accepted')
 check(#commands==1 and commands[1]:match('^insmod /data/watch6recorder/w6r%-player%-'),'one independent native task')
 local control=memory[BASE..'w6r-player-control.txt'];check(control:sub(49,56)=='GO      ' and control:sub(41,48)=='00000002','GO only after successful insmod')
 check(archive.info()==nil and archive.busy(),'prepare never starts speaker or pretends ready')
 check(not archive.prepare(row),'second operation prohibited while task active')
 status('building',1,false);check(archive.state().phase=='preparing','native build presented as preparation')
 memory['/proc/42/cmdline']='w6r_player';memory['/proc/42/status']='Name: w6r_player\n';status('ready',2,true)
 check(archive.busy() and archive.info()==nil,'done frame while process exists cannot unlock microphone')
 memory['/proc/42/cmdline']=nil;memory['/proc/42/status']=nil;clock=clock+300;archive.tick()
 local info=archive.info();check(info and info.id==row.id and info.data_offset==44 and info.pcm_crc32=='1234abcd','ready info carries full CRC and canonical WAV offset')
 check(info.path==BASE..'w6r-play-'..info.cache_id..'.wav' and info.archive_hash=='deadbeeffeedbabe','fixed own-cache path and archive identity')
 check(archive.safe_to_record() and archive.state().phase=='ready','ready only after process exit and successful rmmod')
 memory[info.path]='cache';memory[BASE..'vs-mc-'..row.id..'-00000001.pcm']='original'
 check(not archive.release(info),'cache lease retained without exporter proof')
 check(player.play(info),'explicit play after prepare')
 status('playing',1,false);check(player.state().phase=='playing' and not player.safe_to_record(),'actual player state active')
 check(player.pause() and player.state().phase=='pausing','pause UI waits for actual PAUSED event')
 control=memory[BASE..'w6r-player-control.txt'];check(control:sub(49,56)=='PAUSE   ' and control:sub(41,48)=='00000003','pause monotonic control')
 status('paused',2,false);check(player.resume() and player.state().phase=='resuming','resume explicit')
 control=memory[BASE..'w6r-player-control.txt'];check(control:sub(49,56)=='RESUME  ' and control:sub(41,48)=='00000004','resume monotonic control')
 status('playing',3,false);check(player.state().phase=='playing','started event resumes UI')
 check(player.stop() and player.state().phase=='stopping','stop immediate pending state')
 status('done',4,true);deny_unload=true;check(not player.safe_to_record() and player.state().phase=='retained','unload failure prohibits new microphone')
 deny_unload=false;clock=clock+300;player.tick();check(player.safe_to_record() and player.state().phase=='done','retry only unlocks when rmmod confirmed')
 local recreated=make_archive(adapter);check(recreated.info()==nil,'reattach requires lifecycle observation');check(recreated.safe_to_record() and recreated.info().cache_id==info.cache_id,'completed cache recovered across view recreation without a second WAV');
 can_release=true;local bad={cache_id=info.cache_id,path=BASE..'../wrong.wav'};check(not archive.release(bad),'cleanup rejects path traversal')
 check(archive.release(info) and memory[info.path]==nil,'own cache cleanup after complete proof')
 check(memory[BASE..'vs-mc-'..row.id..'-00000001.pcm']=='original','cleanup never touches PCM archive')
 check(archive.prepare(row),'prepare next explicit operation')
 status('retained',1,false);check(not archive.safe_to_record() and archive.state().active,'retained callback context blocks recording')
 check(archive.cancel(),'cancel uses STOP but does not pretend exited')
 check(not archive.safe_to_record(),'STOP mailbox alone cannot release audio')
 -- Recreated view can safely stop a PLAY operation without in-memory saved info.
 local restored=make_archive(adapter);status('paused',2,false);check(restored.state().phase=='paused','view reattaches persisted identity')
 check(restored.stop(),'reattach stop does not require memory-only cache info')
 local isolated=make_archive({read=function()return nil end,write=function()return true end,execute=function()return true end,decode=json.decode,now_ms=function()return 0 end})
 check(not isolated.safe_to_record() and isolated.state().phase=='retained','unknown module registry fails closed')
 -- A real failed native status must survive unload and remain actionable on
 -- the home page; both playback and export share this archive owner.
 memory['/proc/modules']='';can_release=true
 local failed=make_archive(adapter);check(failed.safe_to_record(),'fresh archive observes worker absence')
 check(failed.prepare(row),'explicit prepare for native failure replay')
 status('error',1,true)
 local failure=failed.state()
 check(failure.phase=='error' and failure.error==-10 and not failure.active,'failed worker can retire safely without losing errno')
 check(failure.message:find('-10',1,true) and failure.message:find('原音准备',1,true),'preparation failure exposes exact native error and operation')
 check(failed.info()==nil,'failed preparation never offers a complete WAV to playback or export')
 check(memory[BASE..'vs-mc-'..row.id..'-00000001.pcm']=='original','diagnostic handling preserves source audio')
 local command_count=#commands
 local restored_failure=make_archive(adapter);local restored_status=restored_failure.state()
 check(restored_status.phase=='error' and restored_status.error==-10 and restored_status.message:find('-10',1,true),'view recreation preserves the last failed native diagnosis')
 check(#commands==command_count and restored_failure.info()==nil and restored_failure.safe_to_record(),'restoring failure is read-only and never offers a failed WAV')
 return {assertions=checks,device_calls=0,physical_verified=false}
end
