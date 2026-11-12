-- Exact native census of owned modules. Never infer absence from proc text.
local function create(a)
 local BASE='/data/watch6recorder/';local sequence=0;local enabled=false;local cached;local fault
 local names={'w6rc','w6rplay','w6rplayer','w6rxlink','w6rdirect'}
 local function hex(s,n)return type(s)=='string'and #s==n and s:match('^[0-9a-f]+$')~=nil end
 local function crc(s)local c=0xffffffff;for i=1,#s do c=c~s:byte(i);for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0)end end;return c~0xffffffff end
 local function write(name,b)return a.write(BASE..name,b)==true and a.read(BASE..name,#b)==b end
 local function put(b,p,v)return b:sub(1,p)..v..b:sub(p+#v+1)end
 local function parse(b,id,seq)
  if type(b)~='string'or #b~=256 or b:sub(1,128)~=b:sub(129)or b:sub(1,6)~='W6RS1\n'or b:sub(7,22)~=id or b:sub(23,23)~='\n'or b:sub(24,31)~=string.format('%08x',seq)or b:sub(32,32)~='\n'or b:sub(121,128)~='W6RSEND\n'or b:sub(105,120)~=string.rep(' ',16)then return end
  for _,p in ipairs({32,41,50,59,68,77,86,95})do if not hex(b:sub(p+1,p+8),8)or b:sub(p+9,p+9)~='\n'then return end end
  if tonumber(b:sub(33,40),16)~=0 or tonumber(b:sub(96,103),16)~=crc(b:sub(1,95))then return end
  local visited=tonumber(b:sub(87,94),16);if visited>128 then return end
  local out={};for i,name in ipairs(names)do local p=41+(i-1)*9;local n=tonumber(b:sub(p+1,p+8),16);if n>1 or n>visited then return end;out[name]=n==1 end
  return out
 end
 local out={}
 function out.refresh()
  enabled=true;cached=nil;fault=nil
  if type(a.asset)~='string'or not a.asset:match('^[%w_.-]+$')or sequence>=0xfffffffe then fault='组件查询不可用';return false,fault end
  local id=a.nonce();if not hex(id,16)or id=='0000000000000000'then fault='组件查询标识未生成';return false,fault end
  sequence=sequence+1;local b=string.rep(' ',64);b=put(b,0,'W6RQ1\n');b=put(b,6,id);b=put(b,22,'\n');b=put(b,23,string.format('%08x',sequence));b=put(b,31,'\n');b=put(b,32,string.format('%08x',crc(b:sub(1,32))));b=put(b,40,'\n');b=put(b,56,'W6RQEND\n')
  if not write('w6r-registry-request.txt',b..b)or not write('w6r-registry-status.txt',string.rep(' ',256))then fault='组件查询写入失败，原音保留';return false,fault end
  -- The shim has no retained callback, task or audio handle. Only it is removed.
  if a.execute('insmod '..BASE..a.asset..' w6rqry')~=true then fault='组件查询未完成，请重试';return false,fault end
  local status=a.read(BASE..'w6r-registry-status.txt',256)
  if a.execute('rmmod w6rqry')~=true then fault='组件查询退出未确认，请完整重启手表';return false,fault end
  cached=parse(status,id,sequence)
  if not cached then fault='组件查询结果未确认，原音保留';return false,fault end
  return true
 end
 function out.present(name)
  local known=false;for _,n in ipairs(names)do if name==n then known=true;break end end
  if not known or not enabled then return nil end
  if not cached and not fault then out.refresh()end
  if cached then return cached[name]end
  return nil
 end
 function out.invalidate()cached=nil;fault=nil end
 function out.activated()return enabled end
 function out.error()return fault end
 return out
end
return create
