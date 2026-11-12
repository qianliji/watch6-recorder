-- Bounded data-only JSON. Dictated text is never evaluated as Lua code.
local NULL={}
local function decode(text,limit)
  if type(text)~='string' or #text>(limit or 4096) then return nil end
  local p,items=1,0
  local max_items=(limit or 4096)>4096 and 4096 or 256
  local function ws() while text:sub(p,p):match('[ \t\r\n]') do p=p+1 end end
  local function quoted()
    if text:sub(p,p)~='"' then error('string') end
    p=p+1;local out={}
    while p<=#text do
      local c=text:sub(p,p);p=p+1
      if c=='"' then return table.concat(out) end
      if c=='\\' then
        local e=text:sub(p,p);p=p+1
        local escapes={['"']='"',['\\']='\\',['/']='/',b='\b',f='\f',n='\n',r='\r',t='\t'}
        if escapes[e] then c=escapes[e]
        elseif e=='u' then
          local h=text:sub(p,p+3);if not h:match('^%x%x%x%x$') then error('unicode') end
          p=p+4;local n=tonumber(h,16)
          if n>=0xd800 and n<=0xdbff then
            if text:sub(p,p+1)~='\\u' then error('surrogate') end
            local low=text:sub(p+2,p+5);if not low:match('^%x%x%x%x$') then error('surrogate') end
            low=tonumber(low,16);if low<0xdc00 or low>0xdfff then error('surrogate') end
            p=p+6;n=0x10000+(n-0xd800)*1024+low-0xdc00
          elseif n>=0xdc00 and n<=0xdfff then error('surrogate') end
          c=utf8.char(n)
        else error('escape') end
      elseif c:byte()<32 then error('control') end
      out[#out+1]=c
    end
    error('unterminated')
  end
  local value
  value=function(depth)
    if depth>8 then error('depth') end
    items=items+1;if items>max_items then error('items') end
    ws();local c=text:sub(p,p)
    if c=='"' then return quoted() end
    if c=='{' or c=='[' then
      local object=c=='{';local finish=object and '}' or ']';p=p+1;ws()
      local out,seen={},{}
      if text:sub(p,p)==finish then p=p+1;return out end
      while true do
        ws();local key
        if object then
          key=quoted();if seen[key] then error('duplicate') end;seen[key]=true
          ws();if text:sub(p,p)~=':' then error('colon') end;p=p+1
        else key=#out+1 end
        out[key]=value(depth+1);ws();local nextchar=text:sub(p,p);p=p+1
        if nextchar==finish then return out end
        if nextchar~=',' then error('separator') end
      end
    end
    if text:sub(p,p+3)=='true' then p=p+4;return true end
    if text:sub(p,p+4)=='false' then p=p+5;return false end
    if text:sub(p,p+3)=='null' then p=p+4;return NULL end
    local start=p
    if c=='-' then p=p+1 end
    local digit=text:sub(p,p)
    if digit=='0' then p=p+1
    elseif digit:match('[1-9]') then repeat p=p+1 until not text:sub(p,p):match('%d')
    else error('number') end
    if text:sub(p,p)=='.' then
      p=p+1;if not text:sub(p,p):match('%d') then error('fraction') end
      repeat p=p+1 until not text:sub(p,p):match('%d')
    end
    if text:sub(p,p):match('[eE]') then
      p=p+1;if text:sub(p,p):match('[+-]') then p=p+1 end
      if not text:sub(p,p):match('%d') then error('exponent') end
      repeat p=p+1 until not text:sub(p,p):match('%d')
    end
    local number=tonumber(text:sub(start,p-1))
    if not number or number~=number or math.abs(number)==math.huge then error('finite') end
    return number
  end
  local ok,result=pcall(function()local out=value(0);ws();if p<=#text then error('trailing') end;return out end)
  return ok and result or nil
end
local function encode(data,limit)
  local items=0
  local max_items=(limit or 4096)>4096 and 4096 or 256
  local function quote(s)
    return '"'..s:gsub('[%z\1-\31\\"]',function(c)
      if c=='"' or c=='\\' then return '\\'..c end
      return string.format('\\u%04x',c:byte())
    end)..'"'
  end
  local value
  value=function(v,depth)
    items=items+1;if items>max_items or depth>8 then error('limit') end
    if v==NULL or v==nil then return 'null' end
    if type(v)=='boolean' then return v and 'true' or 'false' end
    if type(v)=='string' then return quote(v) end
    if type(v)=='number' then
      if v~=v or math.abs(v)==math.huge then error('finite') end
      return tostring(v)
    end
    if type(v)~='table' then error('type') end
    local count=#v
    if count>0 then
      for key in pairs(v) do if type(key)~='number' or key%1~=0 or key<1 or key>count then error('array key') end end
      local out={};for i=1,count do out[i]=value(v[i],depth+1) end
      return '['..table.concat(out,',')..']'
    end
    local keys={};for key in pairs(v) do if type(key)~='string' then error('key') end;keys[#keys+1]=key end
    table.sort(keys);local out={}
    for _,key in ipairs(keys) do out[#out+1]=quote(key)..':'..value(v[key],depth+1) end
    return '{'..table.concat(out,',')..'}'
  end
  local ok,result=pcall(value,data,0)
  return ok and #result<=(limit or 4096) and result or nil
end
-- Network callers retain the 4 KiB mailbox limit. Only the local result file
-- can contain both bounded text fields plus JSON escapes and metadata.
return {decode=function(text)return decode(text,4096)end,encode=function(data)return encode(data,4096)end,
 decode_local=function(text)return decode(text,65536)end,encode_local=function(data)return encode(data,65536)end,null=NULL}
