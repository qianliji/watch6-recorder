return function(make_link,make_archive,make_source,json)
 local count=0
 local function check(value,message)count=count+1;assert(value,message)end
 local ROOT='/data/watch6recorder/'
 local ID='1234567890abcdef'
 local function fixture(module,value,provided)
  local f={memory={},clock=0,queries=0,proc_reads=0,proc_opens=0,writes=0,removes=0,commands=0,value=value}
  local a={enabled=true,asset='vs-continuous-source-abcdefabcdef.elf',decode=json.decode,encode=json.encode,
   now_ms=function()return f.clock end,
   read=function(path)
    if path=='/proc/modules'then f.proc_reads=f.proc_reads+1 end
    if f.read_error and path==ROOT..'w6r-link-status.txt'then return nil,f.read_error end
    local raw=f.memory[path];if raw~=nil then return raw end;return nil,2
   end,
   write=function(path,raw)f.writes=f.writes+1;f.memory[path]=raw;return true end,
   remove=function(path)f.removes=f.removes+1;f.memory[path]=nil;return true end,
   execute=function()f.commands=f.commands+1;return true end,
   nonce=function()return 'abcdef1234567890'end,
   open=function(path)
    if path=='/proc/modules'then f.proc_opens=f.proc_opens+1 end
    local raw=f.memory[path];if raw==nil then return nil,'missing',2 end
    local pos=1
    return {read=function(_,n)if pos>#raw then return nil end;local data=raw:sub(pos,pos+n-1);pos=pos+#data;return data end,close=function()return true end}
   end}
  if provided then
   a.module_present=function(name)
    check(name==module,'queries only the owned module '..module);f.queries=f.queries+1
    if f.value=='throw'then error('query unavailable')end
    return f.value
   end
  end
  f.adapter=a;return f
 end
 local function no_proc(f,label)
  check(f.proc_reads==0 and f.proc_opens==0,label..' must not fall back to formatter output')
 end
 local function no_mutations(f,label)
  check(f.writes==0 and f.removes==0 and f.commands==0,label..' is a passive observation')
 end
 local function link_frame(pid)
  local h=string.format('VSL1 %s %08x %04x\n',ID,1,0);h=h..string.rep(' ',64-#h)
  local body=string.format('phase=connected\npid=%08x\ntx_ack=00000000\nrx_seq=00000000\nerror=00000000\nphone=00000001\n',pid)
  return h..body..string.rep(' ',128-#body)..h
 end
 -- Native false is authoritative; nil, exceptions and nonboolean values are
 -- unknown even when the old formatter happens to print an empty registry.
 for _,case in ipairs({{name='unknown'}, {name='absent',value=false}, {name='present',value=true}, {name='exception',value='throw'}, {name='invalid',value='false'}})do
  local f=fixture('w6rxlink',case.value,true);f.memory['/proc/modules']=''
  local link=make_link(f.adapter);local accepted=link.restore()
  check(accepted==(case.value==false),'legacy restore '..case.name)
  check(link.exportStatus().safe_to_release==(case.value==false),'legacy release '..case.name)
  check(link.getStatus().phase==(case.value==false and 'idle' or 'retained'),'legacy phase '..case.name)
  no_proc(f,'legacy '..case.name);no_mutations(f,'legacy '..case.name)
 end
 for _,raw in ipairs({string.rep(' ',256),'stale malformed mailbox'})do
  local f=fixture('w6rxlink',false,true);f.memory[ROOT..'w6r-link-status.txt']=raw
  local link=make_link(f.adapter);check(link.restore(),'authoritative absence releases stale non-lease metadata')
  check(f.memory[ROOT..'w6r-link-status.txt']==raw,'legacy metadata stays untouched')
  no_proc(f,'stale lease');no_mutations(f,'stale lease')
 end
 for _,case in ipairs({{name='gone',absent=true},{name='live',live=true},{name='pid unknown'}})do
  local f=fixture('w6rxlink',false,true);f.memory[ROOT..'w6r-link-status.txt']=link_frame(123)
  if case.live then f.memory['/proc/123/cmdline']='live';f.memory['/proc/123/status']='live' end
  if not case.live and not case.absent then
   local prior=f.adapter.read;f.adapter.read=function(path,capacity)if path:match('^/proc/123/')then return nil,5 end;return prior(path,capacity)end
  end
  local link=make_link(f.adapter);check(link.restore()==(case.absent==true),'valid old worker remains protected unless both PID paths are ENOENT: '..case.name)
  check(link.exportStatus().safe_to_release==(case.absent==true),'valid lease release '..case.name)
  no_proc(f,'valid lease '..case.name);no_mutations(f,'valid lease '..case.name)
 end
 do
  local f=fixture('w6rxlink',false,true);f.read_error=5
  local link=make_link(f.adapter);check(not link.restore(),'generic nil read is not ENOENT');check(not link.exportStatus().safe_to_release,'read error retains scratch')
  no_mutations(f,'read error')
 end
 do
  local f=fixture('w6rxlink',nil,false);f.memory['/proc/modules']='';local link=make_link(f.adapter)
  check(link.restore(),'host without native callback retains proc fallback');check(f.proc_reads==1,'host fallback reads proc')
  f=fixture('w6rxlink',nil,false);f.memory['/proc/modules']='';f.memory[ROOT..'w6r-link-status.txt']=string.rep(' ',256)
  check(not make_link(f.adapter).restore(),'formatter-only absence does not relax legacy invalid lease checks')
 end
 -- Initial archive observation may happen before explicit hardware preflight.
 -- It remains protected but must be retryable as soon as a query is prepared.
 for _,case in ipairs({{name='unknown'}, {name='absent',value=false}, {name='present',value=true}, {name='exception',value='throw'}, {name='invalid',value=0}})do
  local f=fixture('w6rplay',case.value,true);f.memory['/proc/modules']=''
  local archive=make_archive(f.adapter);local state=archive.state()
  check(state.safe_to_record==(case.value==false),'archive safe state '..case.name)
  check(state.active~=(case.value==false),'archive active protection '..case.name)
  no_proc(f,'archive '..case.name);no_mutations(f,'archive '..case.name)
 end
 do
  local f=fixture('w6rplay',nil,true);local archive=make_archive(f.adapter)
  check(not archive.safe_to_record(),'unknown initial archive remains protected')
  f.value=false
  check(archive.reobserve(),'explicit preflight retries unknown immediately without advancing clock')
  check(archive.safe_to_record(),'fresh authoritative absence enables recording immediately')
  check(not archive.reobserve(),'stable idle observation is not reset repeatedly')
  no_proc(f,'archive explicit retry');no_mutations(f,'archive explicit retry')
 end
 do
  local f=fixture('w6rplay',nil,true);local archive=make_archive(f.adapter);archive.tick();f.value=false
  f.clock=249;check(not archive.safe_to_record(),'automatic unknown retry respects existing polling bound')
  f.clock=250;check(archive.safe_to_record(),'later tick retries unknown observation')
 end
 do
  local f=fixture('w6rplay',true,true);local archive=make_archive(f.adapter);archive.tick();f.value=false
  check(not archive.reobserve(),'known-present retained player cannot be reset by unknown-only reobserve')
  check(not archive.safe_to_record(),'known-present player protection stays in place')
 end
 do
  local f=fixture('w6rplay',false,true);f.adapter.asset='w6r-player-test.elf';local archive=make_archive(f.adapter)
  check(archive.prepare(ID),'real prepare creates owned player operation')
  local queries=f.queries;f.value=nil
  check(not archive.reobserve(),'reobserve does not interrupt a loaded operation')
  check(f.queries==queries,'reobserve does not requery or adopt over loaded operation')
  check(archive.busy(),'loaded player operation remains busy')
 end
 do
  local f=fixture('w6rplay',nil,false);f.memory['/proc/modules']='';check(make_archive(f.adapter).safe_to_record(),'archive host proc fallback remains supported')
  check(f.proc_reads==1,'archive host uses bounded read fallback')
 end
 -- Use real START/GO mailboxes and the real resetAfterRestart operation.
 -- Only explicit authoritative false permits recovery, with a second query
 -- before cleanup. No audio archive is removed by recovery.
 for _,case in ipairs({{name='unknown'}, {name='absent',value=false}, {name='present',value=true}, {name='exception',value='throw'}, {name='invalid',value='false'}})do
  local f=fixture('w6rc',case.value,true);f.memory['/proc/modules']=''
  local source=make_source(f.adapter);check(source.start({id=ID,rate=8000,archive_only=true}),'real source startup fixture '..case.name)
  local pcm=ROOT..'vs-mc-'..ID..'-00000001.pcm';f.memory[pcm]='preserved audio'
  local writes=f.writes;local accepted=source.resetAfterRestart()
  check(accepted==(case.value==false),'source recovery '..case.name)
  check(f.memory[pcm]=='preserved audio','source audio preserved '..case.name)
  check((f.removes>0)==(case.value==false),'only false authorizes obsolete IPC removal '..case.name)
  if case.value~=false then check(f.writes==writes,'unknown/present source does not begin backup mutation '..case.name)end
  no_proc(f,'source '..case.name)
 end
 do
  local f=fixture('w6rc',false,true);local source=make_source(f.adapter);check(source.start({id=ID,rate=8000,archive_only=true}),'source changed-query fixture')
  local callback=f.adapter.module_present
  f.adapter.module_present=function(name)local result=callback(name);if f.queries==1 then f.value=nil end;return result end
  check(not source.resetAfterRestart(),'source unknown second query blocks cleanup after backup')
  check(f.removes==0,'source query changed to unknown never removes original IPC')
  check(f.memory[ROOT..'vs-meeting-source-start.txt']~=nil,'original source start preserved after unknown recheck')
 end
 do
  local f=fixture('w6rc',nil,false);f.memory['/proc/modules']='';local source=make_source(f.adapter)
  check(source.start({id=ID,rate=8000,archive_only=true}),'source host fallback startup')
  check(source.resetAfterRestart(),'source host complete registry fallback remains supported')
  check(f.proc_opens==2,'source fallback opens registry for both checks')
 end
 return {passed=true,assertions=count,device_calls=0,microphone_calls=0}
end
