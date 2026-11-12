return function(make_source,json)
 local count=0;local function check(v,m)count=count+1;assert(v,m)end
 local memory,commands={},{};local clock=0;local root='/data/watch6recorder/';local nonce='1234567890abcdef'
 local function crc(raw)local c=0xffffffff;for i=1,#raw do c=c~raw:byte(i);for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0) end end;return c~0xffffffff end
 local function put(s,p,v)return s:sub(1,p)..v..s:sub(p+#v+1)end
 local function session()
  local raw=string.rep(' ',512);raw=put(raw,0,'VSMC1\n');raw=put(raw,6,'SESSION ');raw=put(raw,14,nonce);raw=put(raw,30,'\n');raw=put(raw,32,'00001f40');raw=put(raw,480,nonce);raw=put(raw,496,'\nend=VSMC1\n');return put(raw,472,string.format('%08x',crc(raw:sub(1,472))))
 end
 local function status(phase,seq)
  local s={v=1,continuous=true,id=nonce,user_started=true,identity_persisted=true,phase=phase,rate=8000,sample_rate=8000,pid=123,
   produced_offset=16000,readable_offset=16000,reclaimed_offset=0,phone_durable_offset=0,cache_used=16000,cache_limit=134348800,reserve_bytes=131072,
   extent_count=1,extent_first_seq=1,tail_complete=phase=='closed',whole_meeting_complete=phase=='closed',archive_only=true,storage_id='',error_code=phase=='retained' and 12 or 0,
   status_sequence=seq,sequence_end=seq,stop_reason='user'}
  local text=json.encode(s);check(text~=nil,'status fixture bounded')
  local header=string.rep(' ',64);header=put(header,0,'VSMST1\n');header=put(header,7,nonce);header=put(header,23,'\n');header=put(header,24,'seq=');header=put(header,28,string.format('%08x',seq));header=put(header,37,'len=');header=put(header,41,string.format('%08x',#text));header=put(header,50,'crc=');header=put(header,54,string.format('%08x',crc(text)))
  local raw=header..text..string.rep(' ',1408-#text)..header;check(#raw==1536,'framed status length');return raw
 end
 local function open(name)
  local raw=memory[name];if raw==nil then return nil,'missing',2 end
  local p=1;return {read=function(_,n)if p>#raw then return nil end;local s=raw:sub(p,p+n-1);p=p+#s;return s end,close=function()return true end}
 end
 local adapter={read=function(n)return memory[n],memory[n] and nil or 2 end,write=function(n,s)memory[n]=s;return true end,
  remove=function(n)memory[n]=nil;return true end,execute=function(s)commands[#commands+1]=s;return true end,now_ms=function()return clock end,
  open=open,decode=json.decode,asset='vs-continuous-source-abcdefabcdef.elf',enabled=true}
 local source=make_source(adapter)
 check(source.status().phase=='idle','no old state is idle')
 check(source.start({id=nonce,rate=8000,archive_only=true}),'start writes a matching explicit START and GO')
 check(commands[1]=='insmod '..root..'vs-continuous-source-abcdefabcdef.elf w6rc','independent native path and module')
 check(memory[root..'vs-meeting-source-go.txt']~=nil,'GO persists after successful insmod')
 check(source.release==nil,'standalone interface exposes no phone reclaim')
 memory[root..'vs-mc-'..nonce..'-00000000.session']=session()
 memory[root..'vs-meeting-source-status.txt']=status('recording',1);clock=300;source.tick()
 check(source.status().phase=='recording','actual status frame decoded')
 check(source.pause(),'pause mailbox accepted');check(memory[root..'vs-meeting-source-pause.txt']:sub(25,32)=='PAUSE   ','pause control identity')
 memory[root..'vs-meeting-source-status.txt']=status('paused',2);clock=600;source.tick();check(source.resume(),'resume mailbox accepted')
 check(memory[root..'vs-meeting-source-pause.txt']:sub(25,32)=='RESUME  ','resume distinct command')
 check(source.stop('user'),'explicit stop command')
 memory[root..'vs-meeting-source-status.txt']=status('closed',3);clock=900;source.tick()
 check(source.status().safe_to_destroy and not source.status().owner_present,'closed plus vanished owner permits unload')
 check(source.destroy(),'closed source retires without phone receipt')
 check(commands[#commands]=='rmmod w6rc','only own module unloaded')
 check(memory[root..'vs-mc-'..nonce..'-00000000.session']~=nil,'session archive is preserved')
 check(source.status().phase=='idle','next recording now idle')
 -- Retained close must not allow unload or cleanup while the module exists.
 source=make_source(adapter)
 local start=string.rep(' ',512)
 check(source.start({id=nonce,rate=8000,archive_only=true})==false,'used identity cannot overwrite a recording')
 -- Restore a previously persisted protected state exactly, as after view recreation.
 memory[root..'vs-meeting-source-start.txt']=nil
 local fresh='abcdef1234567890';nonce=fresh
 check(source.start({id=nonce,rate=8000,archive_only=true}),'fresh explicit identity')
 memory[root..'vs-mc-'..nonce..'-00000000.session']=session();memory[root..'vs-meeting-source-status.txt']=status('retained',4)
 memory['/proc/modules']='w6rc,0x100,0x200,12,0x0,0,0x0,0\n';clock=1200;source.tick()
 check(not source.destroy(),'retained owner cannot be force-unloaded')
 check(not source.resetAfterRestart(),'live module blocks explicit recovery')
 memory['/proc/modules']='';check(source.resetAfterRestart(),'complete empty module registry permits post-reboot recovery')
 check(memory[root..'vs-mc-'..nonce..'-00000000.session']~=nil,'post-reboot recovery preserves recording archive')
 check(memory[root..'w6r-recovery-'..nonce..'-status.txt']~=nil,'old IPC backed up before cleanup')
 check(source.status().phase=='idle','recovery leaves microphone idle')
 return {passed=true,assertions=count,device_calls=0,microphone_calls=0}
end
