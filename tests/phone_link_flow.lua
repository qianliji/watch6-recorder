return function(factory,json)
 local base='/data/watch6recorder/';local memory={['/proc/modules']=''};local commands={};local clock=0;local deny_unload=false;local assertions=0
 local function check(v,m)assertions=assertions+1;assert(v,m)end
 local function h(id,seq,n)local s=string.format('VSL1 %s %08x %04x\n',id,seq,n);return s..string.rep(' ',64-#s)end
 local nonce
 local function native(phase,pid)
  local body=string.format('phase=%s\npid=%08x\ntx_ack=00000000\nrx_seq=00000000\nerror=00000000\nphone=00000001\ntx_cap=00000003\n',phase,pid or 321)
  local head=h(nonce,2,0);memory[base..'w6r-link-status.txt']=head..body..string.rep(' ',128-#body)..head
 end
 local function exported(phase,done,closed)
  local body=json.encode({phase=phase,next=phase=='saved' and 4000 or 0,total_bytes=4000,job_sequence=1,recording_id='0123456789abcdef',code=0,pid=321,source_closed=closed==true,worker_done=done==true})
  local head=h(nonce,4,#body);memory[base..'w6r-export-status.txt']=head..body..string.rep(' ',384-#body)..head
 end
 local adapter={asset='phone-link.elf',now_ms=function()return clock end,
  read=function(path,limit)local s=memory[path];if s==nil then return nil,2 end;return s:sub(1,limit)end,
  write=function(path,value)memory[path]=value;return true end,
  execute=function(cmd)
   commands[#commands+1]=cmd
   if cmd:match('^insmod ')then nonce=memory[base..'w6r-link-start.txt']:sub(6,21);memory['/proc/modules']='w6rxlink,0,0,0,0,0,0,0\n';native('starting');return true end
   if cmd=='rmmod w6rxlink'then if deny_unload then return false end;memory['/proc/modules']='';return true end
   return false
  end,encode=json.encode,decode=json.decode}
 local one=factory(adapter)
 check(one.restore(),'cold observer can confirm empty module registry')
 check(one.exportStatus().safe_to_release,'local playback cache can be released before any phone export')
 check(#commands==0,'cold restore must not load or connect anything')
 local two=factory(adapter);check(two.restore() and two.exportStatus().safe_to_release,'second local playback can clean cache without first phone connection')
 check(#commands==0,'second restore remains read only')
 check(one.start(),'phone owner may start only on explicit request')
 check(one.getStatus().nonce_ready,'initialization nonce permits export before phone connects')
 local info={id='0123456789abcdef',path=base..'w6r-play-fedcba9876543210.wav',rate=8000,total_bytes=4000,archive_hash='abcdef0123456789',pcm_crc32='87654321',data_offset=44}
 check(one.begin_export(info),'verified WAV can be queued during starting phase')
 local job=memory[base..'w6r-export-job.txt'];check(#job==512 and job:sub(1,6)=='W6RE1\n','fixed export descriptor')
 check(job:sub(25,40)==info.id and job:sub(73,80)==info.pcm_crc32 and job:sub(81,96)=='fedcba9876543210','descriptor identities match prepared WAV')
 check(not one.exportStatus().safe_to_release,'pending native job holds its cache')
 local early=factory(adapter);local early_commands=#commands
 check(early.restore() and early.getStatus().background_owned,'GUI recreation before first native status adopts the CRC-checked pending job')
 check(#commands==early_commands and memory[base..'w6r-export-job.txt']==job,'early adoption does not erase or restart pending export');early.detach()
 native('connected');exported('sending',false,false);memory['/proc/321/cmdline']='w6rx_owner';memory['/proc/321/status']='running'
 local heart=memory[base..'w6r-link-heartbeat.txt'];clock=10000;one.tick()
 check(memory[base..'w6r-link-heartbeat.txt']==heart,'background export does not require a GUI heartbeat')
 local before=#commands;one.detach();local restored=factory(adapter)
 check(restored.restore(),'face recreation adopts native export')
 check(restored.getStatus().background_owned and restored.exportStatus().phase=='sending','recreated GUI observes same active export')
 check(#commands==before,'restoration must not restart, unload, connect, or reset its job')
 check(memory[base..'w6r-export-job.txt']==job,'adoption preserves fixed job and durable frontier')
 exported('saved',false,true);native('closing');clock=10500;restored.tick();check(not restored.exportStatus().safe_to_release,'phone saved ACK alone is not native worker exit')
 exported('saved',true,true);native('closed');clock=11000;restored.tick();check(not restored.exportStatus().safe_to_release,'live PID blocks cache deletion')
 memory['/proc/321/cmdline']=nil;memory['/proc/321/status']=nil;deny_unload=true;clock=11500;restored.tick();check(not restored.exportStatus().safe_to_release,'failed native unload remains retained')
 deny_unload=false;clock=12000;restored.tick();check(restored.exportStatus().safe_to_release,'PID double ENOENT and successful native unload release scratch')
 check(restored.exportStatus().phase=='saved','saved result persists after worker exit')
 local foreground=factory(adapter);check(foreground.restore(),'nonexport observer starts safely')
 check(foreground.start(),'explicit foreground-only phone connection')
 check(foreground.stop(),'foreground-only connection may stop')
 native('closed');clock=12500;foreground.tick()
 check(foreground.exportStatus().safe_to_release,'stopped foreground-only owner releases scratch after guarded unload')
 check(memory['/proc/modules']=='','nonexport stop unloads its native module')
 local idle=factory(adapter);idle.restore();idle.start();native('connected')
 local body=json.encode({phase='idle',next=0,total_bytes=0,job_sequence=0,recording_id='',code=0,pid=321,source_closed=true,worker_done=false});local head=h(nonce,1,#body)
 memory[base..'w6r-export-status.txt']=head..body..string.rep(' ',384-#body)..head
 local idle_heart=memory[base..'w6r-link-heartbeat.txt'];local passive=factory(adapter)
 check(passive.restore(),'read-only recreation recognizes foreground-only owner')
 clock=13500;passive.tick();check(memory[base..'w6r-link-heartbeat.txt']==idle_heart,'recreated page must not keep an idle foreground connection alive')
 native('closed');clock=14000;passive.tick();check(passive.exportStatus().safe_to_release,'observed idle owner safely reaps after its natural lease expires')
 local unknown=factory({asset='phone-link.elf',now_ms=function()return clock end,read=function()return nil,5 end,write=adapter.write,execute=adapter.execute,encode=json.encode,decode=json.decode})
 check(not unknown.restore() and not unknown.exportStatus().safe_to_release,'unreadable registry never authorizes scratch cleanup')
 return {assertions=assertions,passed=true,device_calls=0}
end
