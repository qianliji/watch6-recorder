-- Two-generation local metadata journal. Audio extents never enter this file.
local function create(a)
 local records,generation={},0
 local function crc(s)local c=0xffffffff;for i=1,#s do c=c~s:byte(i);for _=1,8 do c=(c>>1)~((c&1)==1 and 0xedb88320 or 0) end end;return c~0xffffffff end
 local function parse(raw)
  if type(raw)~='string' or #raw>65580 then return nil end
  local seq,hash,body=raw:match('^W6RC1 ([0-9a-f]+) ([0-9a-f]+)\n(.*)$')
  if not seq or #seq~=8 or #hash~=8 or crc(body)~=tonumber(hash,16) then return nil end
  local ok,data=pcall(a.decode,body)
  if not ok or type(data)~='table' or type(data.records)~='table' or #data.records>256 then return nil end
  local seen={}
  for _,r in ipairs(data.records) do
   if type(r)~='table' or type(r.id)~='string' or #r.id~=16 or not r.id:match('^[0-9a-f]+$') or seen[r.id]
    or (r.rate~=8000 and r.rate~=16000) or type(r.bytes)~='number' or r.bytes<0 or r.bytes%2~=0 or r.bytes>134348800
    or (r.status~='pending' and r.status~='saved' and r.status~='partial' and r.status~='failed') then return nil end
   seen[r.id]=true
  end
  return tonumber(seq,16),data.records
 end
 local any=false
 for slot=0,1 do
  local raw,err=a.read(a.base..'catalog-'..slot..'.txt',65580)
  if raw~=nil or err~=2 then any=true end
  local seq,rows=parse(raw)
  if seq and seq>generation then generation,records=seq,rows end
 end
 local healthy=not any or generation>0
 local out={}
 local function copy(rows)local data={};for i,r in ipairs(rows)do data[i]={};for k,v in pairs(r)do data[i][k]=v end end;return data end
 function out.list()return copy(records) end
 function out.healthy()return healthy end
 function out.revision()return generation end
 function out.put(record)
  if not healthy or generation>=0xffffffff then return false end
  local rows=copy(records);local found=false
  for i,r in ipairs(rows)do if r.id==record.id then rows[i]=record;found=true;break end end
  if not found then if #rows>=256 then return false end;rows[#rows+1]=record end
  local body=a.encode({v=1,records=rows});if not body then return false end
  local seq=generation+1;local raw=string.format('W6RC1 %08x %08x\n',seq,crc(body))..body
  local target=a.base..'catalog-'..(seq%2)..'.txt'
  if not a.write(target,raw) or a.read(target,#raw)~=raw then return false end
  local verified,verified_rows=parse(raw);if verified~=seq then return false end
  generation,records=seq,verified_rows;return true
 end
 return out
end
return create
