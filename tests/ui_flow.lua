return function(make_ui)
 local checks=0;local function check(v,m)checks=checks+1;assert(v,m)end
 local all={};local writes,flag_writes,font_calls=0,0,0
 local lvgl={FLAG={HIDDEN=1,CLICKABLE=2,SCROLLABLE=3,EVENT_BUBBLE=4},EVENT={PRESSED=1,RELEASED=2,PRESS_LOST=3},ALIGN={CENTER=0}}
 local function object(parent,p)
  local o={parent=parent,p=p,events={},flags={}};all[#all+1]=o
  function o:set(values)writes=writes+1;for k,v in pairs(values)do self.p[k]=v end end
  function o:add_flag(f)flag_writes=flag_writes+1;self.flags[f]=true end
  function o:clear_flag(f)flag_writes=flag_writes+1;self.flags[f]=nil end
  function o:onClicked(fn)self.click=fn end;function o:onevent(e,fn)self.events[e]=fn end
  return o
 end
 lvgl.Object=object;lvgl.Label=object
 lvgl.Font=function(f,s,w)font_calls=font_calls+1;return {family=f,size=s,weight=w}end;package.loaded.lvgl=lvgl
 local actions={};local id='1111111111111111';local other='2222222222222222'
 local state={phase='idle',bytes=0,rate=8000,message='离线录音'}
 local rows={{id=id,rate=8000,bytes=160000,status='saved',created=0}}
 local extra={};local ui
 ui=make_ui({act=function(name,target)actions[#actions+1]={name,target}end,render=function()ui.render(state,rows,extra)end})
 local function visible(o)while o do if o.flags[lvgl.FLAG.HIDDEN] then return false end;o=o.parent end;return true end
 local function find(text)for _,o in ipairs(all)do if o.p.text==text and visible(o) then return o end end end
 local function tap(text)local o=find(text);check(o and o.parent.click,'visible button '..text);o.parent.click()end
 local function last(action,target)local v=actions[#actions];check(v and v[1]==action and (not target or v[2]==target),'action '..action)end
 local function disabled(text)
  local o=find(text);check(o and o.parent.click and not o.parent.flags[lvgl.FLAG.CLICKABLE],'disabled button '..text)
  check(o.p.text_color==0x858585,'disabled visual '..text);local n=#actions;o.parent.click();check(n==#actions,'disabled tap has no effect '..text)
 end
 local function render()ui.render(state,rows,extra)end
 local function home()
  extra={};state={phase='idle',bytes=0,rate=8000};ui.showRecords();render();tap('返回');check(ui.page()=='home','home navigation')
 end
 local function detail()ui.showDetail(id);render();check(ui.page()=='detail' and ui.selected()==id,'selected detail')end
 render();check(#actions==0,'initialization has no audio effect')
 check(find('00:00').p.text_font.size==68 and find('准备就绪').p.text_font.size==28,'clear home type hierarchy')
 tap('最近录音');check(ui.page()=='detail' and ui.selected()==id,'recent recording only opens detail');last('select',id)
 check(find('00:10')and find('尚未播放')and not find('00:00 / 00:10'),'unplayed recording shows total duration without implying autoplay')
 tap('返回');tap('返回');tap('开始录音');last('record')
 local b=find('开始录音').parent;b.events[lvgl.EVENT.PRESSED]();check(b.p.bg_color==0xd2d2d2,'press feedback')
 b.events[lvgl.EVENT.PRESS_LOST]();check(b.p.bg_color==0xfafafa,'lost press restores surface')
 b.events[lvgl.EVENT.PRESSED]();b.events[lvgl.EVENT.RELEASED]();check(b.p.bg_color==0xfafafa,'release feedback')
 extra={record_preparing=true,pending_action='record'};render();check(find('正在准备录音'),'waiting microphone intent is visible');tap('取消准备');last('cancel_pending')
 extra={};state.phase='preparing';render();tap('取消本次录音');last('stop_record')
 state={phase='recording',bytes=16000,rate=8000,duration_ms=60000};render()
 check(find('01:00')and find('正在录音'),'recording elapsed duration and state');tap('暂停录音');last('pause_record')
 state.phase='pausing';render();disabled('正在暂停…');tap('结束并保存');last('stop_record')
 state.phase='paused';render();tap('继续录音');last('resume_record');check(find('录音已暂停'),'paused recording is explicit')
 state.phase='resuming';render();disabled('正在继续…');tap('结束并保存');last('stop_record')
 state.phase='saving';render();disabled('正在保存…');check(find('正在保存原音'),'save pending is not success')
 state.phase='saved';state.id=id;render();check(find('已保存在手表'),'local saved scope is explicit')
 check(find('查看录音'),'saved recording has a visible detail entry without swiping')
 tap('查看录音');check(ui.page()=='detail','saved detail is one tap away');tap('返回');tap('返回');render()
 local before=#actions;tap('准备下一条');check(#actions==before+1,'next has one explicit action');last('next_record')
 check(actions[#actions][1]~='record','next does not open microphone')
 home();tap('录音列表');check(ui.isList(),'library navigation');tap('录音 1');last('select',id)
 tap('播放完整录音');last('play',id);tap('发送到手机');last('export',id)
 extra={playback={id=id,phase='playing',active=true,position_ms=5000}};render()
 check(find('00:05 / 00:10')and find('正在回听')and find('尚未发送到手机'),'playback and transfer are independent')
 tap('暂停播放');last('pause_playback');disabled('发送到手机')
 extra.playback.phase='paused';render();tap('继续播放');last('resume_playback')
 extra.playback.phase='pausing';render();disabled('正在处理回听…');tap('停止回听');last('stop_playback')
 extra.playback.phase='stopping';render();disabled('正在处理回听…');disabled('停止回听')
 extra.playback.phase='stopped';extra.playback.active=false;render()
 check(find('已停止回听')and not find('已完整播完'),'manual stop never claims complete playback')
 extra.playback.phase='completed';render();check(find('已完整播完'),'natural completion is explicit')
 extra.playback.phase='done';render();check(find('回听已结束')and not find('已完整播完'),'unspecified done does not claim full completion')
 extra={preparing_id=id,preparing_action='play',pending_action='play'};render()
 check(find('正在准备完整回听'),'play preparation shown');disabled('正在准备…');disabled('发送到手机');tap('取消准备');last('cancel_pending',id)
 extra={preparing_id=id,preparing_action='export',pending_action='export'};render()
 check(find('尚未播放')and find('正在准备发送原音'),'export preparation does not change playback state')
 before=#actions;tap('返回');check(ui.page()=='list','back leaves prepare');check(actions[before+1][1]=='cancel_pending','leaving preparation cancels intent')
 extra={};detail()
 extra={playback={id=id,phase='stopped',position_ms=5000},transfer={id=id,phase='sending',active=true,progress=.5}};render()
 check(find('发送中 · 50%')and find('已停止回听')and find('00:05 / 00:10'),'independent transfer and playback progress')
 disabled('播放完整录音');tap('暂停发送');last('cancel_export',id)
 extra.transfer.phase='cancelling';render();disabled('正在暂停…');check(find('正在暂停发送…')and not find('发送已暂停 · 50%'),'pause request waits for native acknowledgement')
 extra.transfer.phase='cancelled';render();disabled('正在暂停…');check(find('正在暂停发送…'),'terminal cancel with live owner still waits')
 extra.transfer.active=false;extra.transfer.safe_to_release=true;render();check(find('发送已暂停 · 50%'),'confirmed pause shown');tap('继续发送');last('export',id)
 extra.transfer.phase='error';extra.transfer.message='手机连接中断，手表原音保留';render()
 check(find('发送未完成 · 可重试')and find(extra.transfer.message),'failure remains visible after transfer stops');tap('重试发送');last('export',id)
 extra.transfer={id=id,phase='sending',active=true,progress=1};render();check(find('发送中 · 100%')and not find('手机已完整保存'),'100 percent is not receiver confirmation')
 extra.transfer.phase='confirming';render();check(find('等待手机确认完整保存')and not find('手机已完整保存'),'waiting acknowledgement is not success');tap('暂停发送');last('cancel_export',id)
 extra.transfer.phase='saved';extra.transfer.active=false;render();check(find('手机已完整保存'),'only confirmed saved state claims phone success');tap('再次发送');last('export',id)
 extra.transfer={id=id,phase='sending',active=true,progress=3,message='手机连接已中断，正在恢复发送；原音保留'};render()
 check(find('发送中 · 100%')and find(extra.transfer.message),'reconnect message persists without inventing a fresh task')
 for _,o in ipairs(all)do if o.parent and o.parent.p.h==4 and o.parent.parent==ui.root then check(o.p.w==376,'transfer progress clamps to track width')end end
 extra.transfer.progress=-1;render();check(find('发送中 · 0%'),'negative progress clamps to zero')
 state={phase='recording',bytes=16000,rate=8000,duration_ms=60000};extra={};render();disabled('播放完整录音');disabled('发送到手机')
 tap('正在录音 · 返回控制');check(ui.page()=='home'and find('暂停录音'),'active recording is reachable from other pages')
 state.phase='recovery';render();tap('恢复录音状态');last('recover_record');detail();disabled('播放完整录音');disabled('发送到手机')
 home();extra={record_preparing=true,pending_action='record',playback={id=id,phase='playing',active=true,position_ms=1000}};render()
 before=#actions;tap('正在回听 · 点击查看');check(ui.page()=='detail','status bar navigates to playback')
 check(actions[before+1][1]=='cancel_pending'and actions[before+2][1]=='show_playback','status navigation cancels pending microphone before leaving')
 home();extra={record_preparing=true,pending_action='record'};render();before=#actions;tap('设置')
 check(ui.page()=='connection'and actions[before+1][1]=='cancel_pending','settings navigation cancels pending microphone')
 extra={phone={transport='mifitness',identity_required=true,phase='idle',version='0.4.1-preview'}};render()
 check(find('尚未连接')and not find('0.4.1-preview'),'connection view presents user state without build number')
 before=#actions;tap('连接帮助 · 首次使用请查看');check(ui.page()=='help'and #actions==before,'help does not start transport')
 check(find('导出通过手机 App 和运动健康。\n首次安装配套录音连接组件，\n日常只需打开这个录音表盘。'),'help explains one-time identity installation and everyday watchface use')
 tap('查看连接状态');tap('连接手机');last('connect')
 extra.phone.phase='connecting';render();disabled('正在连接…');tap('断开连接');last('disconnect')
 extra.phone.transportReady=true;extra.phone.phase='connected';render()
 check(find('等待手机接收')and find('运动健康已连接\n请打开手机录音 App')and not find('接收已就绪'),'transport readiness does not imply receiver readiness')
 extra.transfer={id=id,phase='connecting',active=true,progress=0};render()
 check(find('等待手机接收')and not find('接收已就绪'),'pending export does not manufacture receiver readiness')
 extra.phone.connected=true;render();check(find('接收已就绪')and find('可发送完整录音到手机'),'real receiver readiness shown')
 disabled('连接正常');tap('断开连接');last('disconnect');tap('返回录音');check(ui.page()=='home','connection always has a return')
 home();rows={};render();disabled('最近录音');tap('录音列表');check(find('还没有录音'),'empty library has a useful state');disabled('上一页');disabled('下一页')
 rows={};for i=1,7 do rows[i]={id=tostring(i),rate=8000,bytes=i*16000,status=i==1 and 'partial'or 'saved'}end
 render();check(find('1 / 3')and find('00:01 · 原音待检查'),'paged library shows incomplete recordings truthfully')
 tap('下一页');check(find('2 / 3')and find('录音 4'),'next page');tap('下一页');check(find('3 / 3')and find('录音 7'),'last page');disabled('下一页')
 rows={rows[1]};render();check(find('1 / 1'),'library shrink clamps page');disabled('上一页')
 tap('录音 1');disabled('播放完整录音');disabled('发送到手机');check(find('原音待检查，暂不能回听'),'partial original is protected from full-play claim')
 rows={{id=id,rate=8000,bytes=160000,status='saved'},{id=other,rate=8000,bytes=320000,status='saved'}}
 extra={playback={id=other,phase='playing',active=true}};state={phase='idle',rate=8000,bytes=0};detail();disabled('播放完整录音');disabled('发送到手机')
 before=#actions;tap('正在回听 · 点击查看');check(ui.selected()==other,'status bar selects the actual playing recording');last('show_playback',other)
 extra={};detail();local widget_count=#all;local font_count=font_calls;local old_writes,old_flags=writes,flag_writes
 for _=1,1000 do render()end
 check(#all==widget_count and font_calls==font_count,'steady rendering allocates no widgets or fonts')
 check(writes==old_writes and flag_writes==old_flags,'unchanged detail frame performs no widget or flag writes')
 for _,o in ipairs(all)do
  if o.parent==ui.root then
   check(o.p.x>=0 and o.p.y>=0 and o.p.x+(o.p.w or 0)<=432 and o.p.y+(o.p.h or 0)<=514,'inside physical screen')
   if o.click then check(o.p.h>=52,'all touch targets at least 52 pixels high')end
  end
 end
 return {passed=true,assertions=checks,device_calls=0,widget_count=#all,steady_frames=1000,steady_widget_writes=writes-old_writes}
end
