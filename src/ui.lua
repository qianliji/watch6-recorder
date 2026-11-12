-- A fixed widget tree. Rendering only presents owner state; it never starts audio.
local function create(a)
 local lvgl=require('lvgl')
 local nodes,memo,flags,fonts={},{},{},{}
 local page,selected,index='home',nil,1
 local state,records,extra={phase='idle',bytes=0,rate=8000},{},{}
 local root=lvgl.Object(nil,{x=0,y=0,w=432,h=514,bg_color=0,pad_all=0,border_width=0})
 local function flag(o,n,v)
  if not lvgl.FLAG or not lvgl.FLAG[n] then return end
  local seen=flags[o] or {};if seen[n]==v then return end
  local f=v and o.add_flag or o.clear_flag
  if f then pcall(f,o,lvgl.FLAG[n])end;seen[n]=v;flags[o]=seen
 end
 local function set(o,p)
  local old=memo[o] or {};local delta,changed={},false
  for k,v in pairs(p)do if old[k]~=v then old[k]=v;delta[k]=v;changed=true end end
  if changed then o:set(delta)end;memo[o]=old
 end
 local function show(o,v)flag(o,'HIDDEN',not v)end
 local function font(n)
  if fonts[n]~=nil then return fonts[n]~=false and fonts[n] or nil end
  local ok,f=pcall(lvgl.Font,'MiSans-Medium',n,'normal');fonts[n]=ok and f or false;return ok and f or nil
 end
 local function object(parent,x,y,w,h,color,radius)
  local o=lvgl.Object(parent,{x=x,y=y,w=w,h=h,bg_color=color or 0,radius=radius or 0,pad_all=0,border_width=0})
  flag(o,'SCROLLABLE',false);flag(o,'CLICKABLE',false);return o
 end
 local function label(parent,text,x,y,w,h,size,color)
  local p={x=x,y=y,w=w,h=h,text=text,pad_all=0,text_color=color or 0xfafafa}
  local f=font(size);if f then p.text_font=f end
  if parent==root then p.text_align=(y==154 or y==242 or y==302)and 'center' or 'left' end
  local o=lvgl.Label(parent,p);flag(o,'CLICKABLE',false);flag(o,'SCROLLABLE',false);flag(o,'EVENT_BUBBLE',true);return o
 end
 local out={root=root}
 local function redraw()if a.render then a.render()else out.render(state,records,extra)end end
 local function leave_prepare()
  local record=page=='home' and (extra.record_preparing or extra.pending_action=='record')
  local detail=page=='detail' and extra.preparing_id and extra.preparing_id==selected
  if (record or detail)and a.act then a.act('cancel_pending',detail and selected or nil)end
 end
 local function dispatch(action,id)
  if action=='show_transfer' or action=='show_playback' then
   leave_prepare();if id then selected=id;page='detail'end
   if a.act then a.act(action,id)end;redraw();return
  end
  if action=='home' or action=='records' or action=='connection' or action=='help' or action=='back' or action=='select' then
   leave_prepare()
   if action=='home' then page='home'
   elseif action=='records' then page='list';index=1
   elseif action=='connection' then page='connection'
   elseif action=='help' then page='help'
   elseif action=='back' then page=page=='detail' and 'list' or page=='help' and 'connection' or 'home'
   else selected=id;page='detail';if a.act then a.act('select',id)end end
   redraw();return
  end
  if action=='previous' then index=math.max(1,index-1);redraw();return end
  if action=='next_page' then index=index+1;redraw();return end
  if a.act then a.act(action,id)end
 end
 local function button(text,x,y,w,h,strong,size)
  local b={base=strong and 0xfafafa or 0x171717,pressed=strong and 0xd2d2d2 or 0x343434,ink=strong and 0x171717 or 0xfafafa}
  b.box=object(root,x,y,w,h,b.base,20);b.box:set({border_width=1,border_color=strong and 0xffffff or 0x303033})
  local line=(size or 25)+10
  b.text=label(b.box,text,8,math.max(0,(h-line)//2),w-16,math.min(line,h),size or 25,b.ink)
  b.text:set({text_align='center'});if lvgl.ALIGN then b.text:set({align=lvgl.ALIGN.CENTER})end
  b.box:onClicked(function()if b.enabled and b.action then dispatch(b.action,b.id)end end)
  if lvgl.EVENT and b.box.onevent then
   for _,name in ipairs({'PRESSED','RELEASED','PRESS_LOST'})do local event=name
    if lvgl.EVENT[event] then b.box:onevent(lvgl.EVENT[event],function()
     set(b.box,{bg_color=b.enabled and event=='PRESSED' and b.pressed or b.enabled and b.base or 0x101010})
    end)end
   end
  end
  return b
 end
 local function configure(b,text,action,id,enabled)
  b.action,b.id,b.enabled=action,id,action~=nil and enabled~=false
  flag(b.box,'CLICKABLE',b.enabled)
  set(b.box,{bg_color=b.enabled and b.base or 0x101010,border_color=b.enabled and (b.base==0xfafafa and 0xffffff or 0x303033)or 0x2a2a2a})
  set(b.text,{text=text,text_color=b.enabled and b.ink or 0x858585});show(b.box,true)
 end
 flag(root,'SCROLLABLE',false)
 nodes.title=label(root,'录音机',28,24,248,48,32)
 nodes.top=button('录音列表',292,22,112,52,false,22)
 nodes.phone=button('连接手机 · 点击查看',28,86,376,52,false,20)
 nodes.surface=object(root,28,150,376,212,0x101012,28)
 nodes.surface:set({border_width=1,border_color=0x2a2a2e})
 nodes.meta=label(root,'',28,144,376,26,20,0xb5b5b5)
 nodes.time=label(root,'00:00',28,154,376,82,68)
 nodes.status=label(root,'准备就绪',28,242,376,40,28)
 nodes.track=object(root,28,266,376,5,0x292929,2)
 nodes.fill=object(nodes.track,0,0,1,5,0xe0e0e0,2)
 nodes.transfer=label(root,'尚未发送到手机',28,283,376,30,22,0xc5c5c5)
 nodes.transfertrack=object(root,28,318,376,4,0x292929,2)
 nodes.transferfill=object(nodes.transfertrack,0,0,1,4,0xe0e0e0,2)
 nodes.hint=label(root,'录音保存在手表',28,302,376,54,21,0xb5b5b5)
 nodes.primary=button('开始录音',28,374,376,64,true)
 nodes.left=button('录音列表',28,450,182,52,false,22)
 nodes.right=button('连接手机',222,450,182,52,false,22)
 nodes.rows={}
 for i=1,3 do
  local r={box=object(root,28,151+(i-1)*87,376,76,0x171717,20)}
  r.box:set({border_width=1,border_color=0x353535});flag(r.box,'CLICKABLE',true)
  r.title=label(r.box,'',16,8,344,32,25);r.subtitle=label(r.box,'',16,42,344,26,19,0xb5b5b5)
  r.box:onClicked(function()if r.id then dispatch('select',r.id)end end);nodes.rows[i]=r
 end
 nodes.previous=button('上一页',28,450,112,52,false,22)
 nodes.nextpage=button('下一页',292,450,112,52,false,22)
 nodes.fraction=label(root,'1 / 1',159,460,115,32,22,0xb5b5b5)
 local function duration(ms)
  local s=math.max(0,math.floor((tonumber(ms)or 0)/1000))
  if s>=3600 then return string.format('%d:%02d:%02d',s//3600,s//60%60,s%60)end
  return string.format('%02d:%02d',s//60,s%60)
 end
 local function length(r)
  if type(r.duration_ms)=='number' then return math.max(0,r.duration_ms)end
  local rate=tonumber(r.rate)or 0;return rate>0 and math.max(0,(tonumber(r.bytes)or 0)/(rate*2)*1000)or 0
 end
 local function ratio(v)return math.min(1,math.max(0,tonumber(v)or 0))end
 local function find(id)for _,r in ipairs(records)do if r.id==id then return r end end end
 local function title(r,n)
  if r and type(r.created)=='number' and r.created>0 then
   local ok,d=pcall(os.date,'%m-%d %H:%M',r.created);if ok and type(d)=='string' then return d end
  end
  return n and '录音 '..tostring(n)or '录音'
 end
 local capture_labels={preparing='正在准备收音',recording='正在录音',pausing='正在暂停录音',paused='录音已暂停',resuming='正在继续录音',saving='正在保存原音',recovery='录音需要恢复'}
 local transfer_busy={connecting=true,waiting=true,sending=true,confirming=true,cancelling=true,releasing=true}
 function out.render(s,rows,x)
  state,records,extra=s or state,rows or records,x or extra
  local p,t,phone=extra.playback or {},extra.transfer or {},extra.phone or {}
  local phase=state.phase or 'idle';local capture=phase~='idle' and phase~='saved'
  local pending_record=extra.record_preparing==true or extra.pending_action=='record'
  local sending=t.active==true or transfer_busy[t.phase]==true
  local listening=p.phase=='playing' or p.phase=='paused' or p.phase=='pausing' or p.phase=='resuming' or p.phase=='stopping'
  local note=extra.message or state.message or ''
  if page~='list' then for _,r in ipairs(nodes.rows)do show(r.box,false)end end
  show(nodes.previous.box,page=='list');show(nodes.nextpage.box,page=='list');show(nodes.fraction,page=='list')
  show(nodes.surface,page=='home');set(nodes.surface,{border_color=phase=='recording' and 0x4a4a50 or 0x2a2a2e})
  show(nodes.meta,page=='detail');show(nodes.track,page=='detail');show(nodes.transfer,page=='detail')
  if page~='detail' then show(nodes.transfertrack,false)end
  show(nodes.time,page~='list');show(nodes.status,true);show(nodes.hint,page~='list' or #records==0)
  local saved_home=page=='home' and phase=='saved' and find(state.id)
  configure(nodes.top,saved_home and '查看录音' or page=='home' and '设置' or '返回',saved_home and 'select' or page=='home' and 'connection' or 'back',saved_home and state.id or nil)
  local phone_text,phone_action,phone_id='连接手机 · 点击查看','connection',nil
  if capture and page~='home' then phone_text=(capture_labels[phase]or '录音处理中')..' · 返回控制';phone_action='home'
  elseif sending then phone_text=t.phase=='confirming' and '等待手机确认 · 点击查看' or (t.phase=='cancelling' or t.phase=='cancelled')and '正在暂停发送 · 点击查看' or t.phase=='saved' and '手机已保存 · 正在完成' or '正在发送手机 · 点击查看';phone_action='show_transfer';phone_id=t.id
  elseif listening then phone_text=p.phase=='paused' and '回听已暂停 · 点击查看' or '正在回听 · 点击查看';phone_action='show_playback';phone_id=p.id
  elseif phone.connected then phone_text='手机接收已就绪 · 点击查看'
  elseif phone.transportReady then phone_text='等待手机接收 App · 点击查看'end
  if page~='connection' and page~='help' then configure(nodes.phone,phone_text,phone_action,phone_id)end
  if page=='connection' then
   local connecting=({initializing=true,starting=true,connecting=true,reconnecting=true,releasing=true})[phone.phase]==true
   set(nodes.title,{text='手机连接'})
   set(nodes.time,{y=164,h=64,text=phone.connected and '接收已就绪' or phone.transportReady and '等待手机接收' or connecting and '正在连接手机' or '尚未连接',text_font=font(40)or false})
   set(nodes.status,{y=238,h=58,text=phone.connected and '可发送完整录音到手机' or phone.transportReady and '运动健康已连接\n请打开手机录音 App' or connecting and '请保持手机在手表附近' or '手机打开录音 App\n并保持运动健康连接',text_font=font(24)or false})
   local failed=phone.phase=='retained' or phone.phase=='error'
   set(nodes.hint,{y=302,h=54,text_font=font(21)or false,text=failed and phone.message or phone.connected and '手表原音会保留，发送成功以手机确认。' or '首次使用请先查看连接帮助。\n录音与回听可离线使用。'})
   configure(nodes.phone,'连接帮助 · 首次使用请查看','help')
   configure(nodes.primary,phone.connected and '连接正常' or connecting and '正在连接…' or '连接手机','connect',nil,not phone.connected and not connecting)
   configure(nodes.left,'返回录音','home')
   configure(nodes.right,'断开连接','disconnect',nil,phone.connected or phone.transportReady or connecting)
   return
  end
  if page=='help' then
   set(nodes.title,{text='连接帮助'})
   configure(nodes.phone,'返回手机连接','connection')
   set(nodes.time,{y=161,h=58,text='录音与导出',text_font=font(40)or false})
   set(nodes.status,{y=232,h=60,text='录音保存在手表\n可离线完整回听',text_font=font(25)or false})
   set(nodes.hint,{y=295,h=75,text='导出通过手机 App 和运动健康。\n首次安装配套录音连接组件，\n日常只需打开这个录音表盘。',text_font=font(20)or false})
   configure(nodes.primary,'查看连接状态','connection')
   configure(nodes.left,'返回录音','home');configure(nodes.right,'录音列表','records')
   return
  end
  if page=='list' then
   set(nodes.title,{text='全部录音'});show(nodes.time,false)
   set(nodes.status,{y=204,h=44,text_font=font(28)or false,text=#records==0 and '还没有录音' or ''})
   for _,b in ipairs({nodes.primary,nodes.left,nodes.right})do show(b.box,false)end
   local total=math.max(1,math.ceil(#records/3));index=math.max(1,math.min(index,total))
   for i,r in ipairs(nodes.rows)do
    local n=(index-1)*3+i;local item=records[n];r.id=item and item.id or nil;show(r.box,item~=nil)
    if item then set(r.title,{text=title(item,n)});set(r.subtitle,{text=duration(length(item))..' · '..(item.status=='saved' and '完整原音' or '原音待检查')})end
   end
   set(nodes.hint,{y=270,h=64,text_font=font(21)or false,text='返回录音页，点击开始录音。\n录音不需要连接手机。'})
   set(nodes.fraction,{text=index..' / '..total})
   configure(nodes.previous,'上一页','previous',nil,index>1);configure(nodes.nextpage,'下一页','next_page',nil,index<total)
   return
  end
  local item=page=='detail' and find(selected) or find(state.id)
  if page=='detail' and not item then page='list';out.render(state,records,extra);return end
  if page=='detail' then
   local id,total=item.id,length(item);local same=p.id==id;local same_transfer=t.id==id
   local preparing=extra.preparing_id==id
   local playing=same and (p.phase=='playing' or p.phase=='paused')
   local player_busy=same and (p.active==true or listening or p.phase=='preparing')
   local player_transition=same and (p.phase=='pausing' or p.phase=='resuming' or p.phase=='stopping' or p.phase=='retained' or p.phase=='preparing')
   local ready=item.status=='saved' and not capture and not pending_record
   local another_player=(p.active==true or listening)and not same
   local busy_transfer=sending or t.safe_to_release==false
   local may_start=ready and not extra.preparing_id and not another_player and not player_busy and not busy_transfer
   local position=same and math.max(0,tonumber(p.position_ms)or 0)or 0
   local playback_text='尚未播放'
   if preparing and extra.preparing_action~='export' then playback_text='正在准备完整回听'
   elseif same then playback_text=({playing='正在回听',paused='回听已暂停',pausing='正在暂停回听',resuming='正在继续回听',stopping='正在停止回听',preparing='正在打开完整原音',completed='已完整播完',ended='已完整播完',done='回听已结束',stopped='已停止回听',error='回听未完成',retained='回听状态需要恢复'})[p.phase]or playback_text end
   if item.status~='saved' then playback_text='原音待检查，暂不能回听'end
   set(nodes.title,{text='录音详情'});set(nodes.meta,{text=title(item)..' · '..(item.status=='saved' and '完整原音' or '原音待检查')})
   local has_playback=same and (listening or p.phase=='completed' or p.phase=='ended' or p.phase=='done' or p.phase=='stopped' or position>0)
   set(nodes.time,{y=173,h=48,text=has_playback and duration(position)..' / '..duration(total)or duration(total),text_font=font(34)or false})
   set(nodes.status,{y=229,h=32,text=playback_text,text_font=font(24)or false})
   local progress=total>0 and ratio(position/total)or 0
   show(nodes.fill,progress>0);set(nodes.fill,{w=math.max(1,math.floor(376*progress))})
   local transfer_text='尚未发送到手机';local transfer_progress=same_transfer and ratio(t.progress)or 0
   if same_transfer then
    if t.phase=='saved' then transfer_text='手机已完整保存'
    elseif t.phase=='cancelled' or t.phase=='paused' then transfer_text=t.active==true and '正在暂停发送…' or '发送已暂停 · '..math.floor(transfer_progress*100)..'%'
    elseif t.phase=='sending' then transfer_text='发送中 · '..math.floor(transfer_progress*100)..'%'
    else transfer_text=({connecting='正在连接手机发送',waiting='等待手机接收端',confirming='等待手机确认完整保存',cancelling='正在暂停发送…',releasing='正在确认发送状态',error='发送未完成 · 可重试',retained='发送状态需要恢复'})[t.phase]or transfer_text end
   end
   if preparing and extra.preparing_action=='export' then transfer_text='正在准备发送原音'end
   set(nodes.transfer,{text=transfer_text})
   show(nodes.transfertrack,same_transfer and t.phase~='idle');show(nodes.transferfill,transfer_progress>0)
   set(nodes.transferfill,{w=math.max(1,math.floor(376*transfer_progress))})
   local hint='手表原音保留，发送后以手机确认为准。'
   if preparing then hint='完整校验期间可随时取消，原音保留。'
   elseif capture then hint='请先结束并保存当前录音。'
   elseif another_player then hint='另一条正在回听，请先停止回听。'
   elseif same_transfer and (sending or t.phase=='error' or t.phase=='retained') then hint=t.message or hint
   elseif same and (p.phase=='error' or p.phase=='retained') then hint=p.message or hint
   elseif extra.message and extra.message~='' then hint=extra.message
   elseif playing then hint='停止回听后，可发送到手机。'end
   set(nodes.hint,{y=326,h=45,text=hint,text_font=font(18)or false})
   local play_action=playing and (p.phase=='paused' and 'resume_playback' or 'pause_playback')or 'play'
   local play_label=preparing and '正在准备…' or playing and (p.phase=='paused' and '继续播放' or '暂停播放')or player_transition and '正在处理回听…' or '播放完整录音'
   configure(nodes.primary,play_label,play_action,id,not preparing and ((playing and ready)or may_start)and not player_transition)
   configure(nodes.left,preparing and '取消准备' or player_busy and '停止回听' or '返回列表',preparing and 'cancel_pending' or player_busy and 'stop_playback' or 'records',id,not (same and p.phase=='stopping'))
   local can_pause=same_transfer and sending and t.phase~='cancelling' and t.phase~='releasing' and t.phase~='saved' and t.phase~='cancelled'
   local send_label=can_pause and '暂停发送' or same_transfer and (t.phase=='cancelling' or t.phase=='cancelled' and t.active==true)and '正在暂停…' or same_transfer and (t.phase=='cancelled' or t.phase=='paused')and '继续发送' or same_transfer and t.phase=='error' and '重试发送' or same_transfer and t.phase=='saved' and '再次发送' or '发送到手机'
   configure(nodes.right,send_label,can_pause and 'cancel_export' or 'export',id,can_pause or may_start)
   return
  end
  set(nodes.title,{text='录音机'});set(nodes.time,{y=164,h=82,text=duration(length(state)),text_font=font(68)or false})
  local status=phase=='idle' and '准备就绪' or phase=='saved' and (item and item.status~='saved' and '部分录音已保留' or '已保存在手表')or capture_labels[phase]or '正在检查状态'
  if pending_record then status='正在准备录音'end
  set(nodes.status,{y=242,h=40,text=status,text_font=font(28)or false})
  local home_hint=extra.message or (phase=='idle' and '点击开始才会开启麦克风。\n原音保存在手表，可离线回听。' or phase=='saved' and item and item.status=='saved' and '准备下一条后，再点击开始录音。\n这条录音会一直保留。' or note~='' and note or '原音保存在手表。')
  if pending_record then home_hint='正在结束回听，随后开始这次录音。\n现在取消不会开启麦克风。'end
  set(nodes.hint,{y=302,h=54,text=home_hint,text_font=font(21)or false})
  local map={idle={'开始录音','record'},preparing={'取消本次录音','stop_record'},recording={'结束并保存','stop_record'},pausing={'结束并保存','stop_record'},paused={'结束并保存','stop_record'},resuming={'结束并保存','stop_record'},saving={'正在保存…',nil},saved={'准备下一条','next_record'},recovery={'恢复录音状态','recover_record'}}
  local q=pending_record and {'取消准备','cancel_pending'}or map[phase]or {'正在检查…',nil}
  configure(nodes.primary,q[1],q[2])
  local latest;for _,r in ipairs(records)do if r.status=='saved' then latest=r;break end end
  if pending_record then configure(nodes.left,'录音列表','records');configure(nodes.right,'最近录音','select',latest and latest.id,latest~=nil)
  elseif phase=='recording' then configure(nodes.left,'暂停录音','pause_record');configure(nodes.right,'录音列表','records')
  elseif phase=='paused' then configure(nodes.left,'继续录音','resume_record');configure(nodes.right,'录音列表','records')
  elseif phase=='pausing' or phase=='resuming' then configure(nodes.left,phase=='pausing' and '正在暂停…' or '正在继续…',nil);configure(nodes.right,'录音列表','records')
  elseif phase=='saved' and item and item.status=='saved' then
   local may_start=not extra.preparing_id and not sending and t.safe_to_release~=false and p.active~=true and not listening
   configure(nodes.left,'完整回听','play',item.id,may_start);configure(nodes.right,'发送到手机','export',item.id,may_start)
  else configure(nodes.left,'录音列表','records');configure(nodes.right,'最近录音','select',latest and latest.id,latest~=nil)end
 end
 function out.showRecords()leave_prepare();page='list';index=1 end
 function out.showDetail(id)if page~='detail' or selected~=id then leave_prepare()end;selected=id;page='detail' end
 function out.showConnection()if page~='connection' then leave_prepare()end;page='connection' end
 function out.isList()return page=='list' end
 function out.page()return page end
 function out.selected()return selected end
 return out
end
return create
