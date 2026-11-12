"""Render the actual Lua UI widget model for layout review, without a device.

These images approximate LVGL painting with Pillow. They are not watch captures,
audio tests, or proof of transport readiness. All scenario data is synthetic.
"""
from pathlib import Path
import argparse, hashlib, json, os, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_settings import prepare_python_dependencies

BOOTSTRAP=r'''
widgets={}
local function node(kind,parent,props)
 local o={kind=kind,parent=parent,props=props or {},flags={},events={}}
 widgets[#widgets+1]=o;o.index=#widgets
 function o:set(p)for k,v in pairs(p)do self.props[k]=v end end
 function o:add_flag(v)self.flags[v]=true end
 function o:clear_flag(v)self.flags[v]=nil end
 function o:onClicked(cb)self.click=cb end
 function o:onevent(e,cb)self.events[e]=cb end
 return o
end
package.loaded.lvgl={Object=function(p,v)return node('Object',p,v)end,
 Label=function(p,v)return node('Label',p,v)end,
 Font=function(n,s,w)return {name=n,size=s}end,ALIGN={CENTER='center'},
 FLAG={HIDDEN='hidden',CLICKABLE='clickable',SCROLLABLE='scrollable',EVENT_BUBBLE='bubble'},
 EVENT={PRESSED='pressed',RELEASED='released',PRESS_LOST='lost'}}
function visible(o)while o do if o.flags.hidden then return false end;o=o.parent end;return true end
function coordinate(o)
 local x,y=o.props.x or 0,o.props.y or 0
 if o.parent then local px,py=coordinate(o.parent);x=x+px;y=y+py end
 return x,y
end
'''

def table(lua,value):
    if isinstance(value,dict):return lua.table_from({k:table(lua,v)for k,v in value.items()})
    if isinstance(value,list):return lua.table_from([table(lua,v)for v in value])
    return value

def scenarios():
    first='1111111111111111'
    rows=[dict(id=first,rate=8000,bytes=960000,status='saved',created=1700000000),
          dict(id='2222222222222222',rate=8000,bytes=28800000,status='saved',created=1699999000),
          dict(id='3333333333333333',rate=8000,bytes=320000,status='partial',created=1699998000)]
    idle=dict(phase='idle',bytes=0,rate=8000,duration_ms=0)
    ready=dict(connected=True,phase='connected',transport='mifitness',identity_required=True)
    detail=lambda playback=None,transfer=None:dict(phone=ready,playback=playback or {},transfer=transfer or {})
    return rows,[
        ('home','待录音','home',idle,{}),
        ('preparing','准备中，可取消','home',idle,dict(pending_action='record',record_preparing=True,pending_kind='record',message='正在结束回听，请稍候')),
        ('capture-preparing','采音准备，可结束','home',dict(phase='preparing',bytes=0,rate=8000),{}),
        ('recording','正在录音','home',dict(phase='recording',bytes=1040000,rate=8000,duration_ms=65000),dict(phone=ready)),
        ('paused','暂停录音','home',dict(phase='paused',bytes=1040000,rate=8000,duration_ms=65000),dict(phone=ready)),
        ('saving','正在保存','home',dict(phase='saving',id=first,bytes=960000,rate=8000,duration_ms=60000),{}),
        ('saved','已保存在手表','home',dict(phase='saved',id=first,bytes=960000,rate=8000,duration_ms=60000),{}),
        ('library','录音列表','list',idle,{}),
        ('playback','完整回听','detail',idle,detail(dict(id=first,phase='playing',active=True,position_ms=12000,duration_ms=60000))),
        ('sending','发送到手机','detail',idle,detail(transfer=dict(id=first,phase='sending',active=True,progress=.42,bytes=403200,total_bytes=960000,message='正在发送，手表原音保留'))),
        ('confirming','等待手机确认','detail',idle,detail(transfer=dict(id=first,phase='confirming',active=True,progress=1,bytes=960000,total_bytes=960000,message='正在确认手机完整保存'))),
        ('send-error','发送中断，可重试','detail',idle,detail(transfer=dict(id=first,phase='error',active=False,progress=.42,bytes=403200,total_bytes=960000,message='发送未完成，手表原音保留'))),
        ('send-cancelled','已暂停，保留原音','detail',idle,detail(transfer=dict(id=first,phase='cancelled',active=False,progress=.42,bytes=403200,total_bytes=960000,message='发送已暂停，可继续发送'))),
        ('send-saved','手机已完整保存','detail',idle,detail(transfer=dict(id=first,phase='saved',active=False,progress=1,bytes=960000,total_bytes=960000,safe_to_release=True,message='手机已完整保存，手表原音保留'))),
        ('connection','等待手机接收','connection',idle,dict(phone=dict(phase='connecting',connected=False,transportReady=True,identity_required=True))),
        ('help','连接帮助与真实限制','help',idle,{}),
    ]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/ui-review-0.5.0/watch')
    parser.add_argument('--font',type=Path)
    args=parser.parse_args()
    prepare_python_dependencies()
    from lupa.lua54 import LuaRuntime
    from PIL import Image,ImageDraw,ImageFont
    candidates=[args.font]if args.font else[Path(os.environ.get('WINDIR',''))/'Fonts/msyh.ttc',Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    font_path=next((p for p in candidates if p and p.is_file()),None)
    if font_path is None:raise SystemExit('Provide --font with an authorized Chinese font for layout review')
    cache={}
    def font(size):
        if size not in cache:cache[size]=ImageFont.truetype(str(font_path),size)
        return cache[size]
    def color(value):
        return '#%06x'%(int(value)&0xffffff)
    lua=LuaRuntime(unpack_returned_tuples=True)
    lua.execute(BOOTSTRAP)
    ui=lua.execute((ROOT/'src/ui.lua').read_text(encoding='utf-8'))(lua.table_from({}))
    rows,cases=scenarios();args.output.mkdir(parents=True,exist_ok=True)
    images=[];report=[]
    for key,title,page,state,extra in cases:
        if page=='home':
            # Create a fresh actual UI, rather than inventing a home-only setter.
            lua=LuaRuntime(unpack_returned_tuples=True);lua.execute(BOOTSTRAP)
            ui=lua.execute((ROOT/'src/ui.lua').read_text(encoding='utf-8'))(lua.table_from({}))
        elif page=='list':ui.showRecords()
        elif page=='detail':ui.showDetail(rows[0]['id'])
        elif page=='connection':ui.showConnection()
        elif page=='help':
            ui.showConnection();ui.render(table(lua,state),table(lua,rows),table(lua,extra))
            for _,widget in lua.globals().widgets.items():
                if lua.globals().visible(widget) and widget.kind=='Label' and str(widget.props.text or '').startswith('连接帮助'):
                    widget.parent.click();break
            else:raise AssertionError('Actual connection help entry is missing')
        ui.render(table(lua,state),table(lua,rows),table(lua,extra))
        image=Image.new('RGB',(432,514),'black');draw=ImageDraw.Draw(image)
        widgets=lua.globals().widgets;visible=lua.globals().visible;coordinate=lua.globals().coordinate
        labels=[]
        for index in range(1,len(widgets)+1):
            widget=widgets[index]
            if not visible(widget):continue
            p=widget.props;x,y=coordinate(widget);x,y=int(x),int(y);w,h=int(p.w or 0),int(p.h or 0)
            if w<=0 or h<=0:continue
            if widget.kind=='Object':
                radius=int(p.radius or 0);width=int(p.border_width or 0)
                fill=color(p.bg_color or 0);outline=color(p.border_color or 0)if width else None
                draw.rounded_rectangle((x,y,x+w-1,y+h-1),radius=radius,fill=fill,outline=outline,width=max(1,width))
            elif widget.kind=='Label'and p.text:
                size=int(p.text_font.size)if p.text_font else 22
                chosen=font(size);lines=[]
                for paragraph in str(p.text).split('\n'):
                    line=''
                    for char in paragraph:
                        if line and draw.textlength(line+char,font=chosen)>w:
                            lines.append(line);line=char
                        else:line+=char
                    lines.append(line)
                line_height=size+5
                for number,line in enumerate(lines):
                    if (number+1)*line_height>h+4:break
                    left=x+(w-draw.textlength(line,font=chosen))/2 if p.text_align=='center' else x
                    draw.text((left,y+number*line_height),line,font=chosen,fill=color(p.text_color or 0xfafafa),anchor='lt')
                labels.append(dict(text=str(p.text),x=x,y=y,w=w,h=h,font_size=size))
        destination=args.output/(key+'.png');image.save(destination);images.append((title,image))
        report.append(dict(scenario=key,png=destination.name,labels=labels))
    gallery=Image.new('RGB',(432*4,554*((len(images)+3)//4)),'#202020');d=ImageDraw.Draw(gallery)
    for n,(title,image)in enumerate(images):
        x=(n%4)*432;y=(n//4)*554;d.text((x+20,y+9),title,font=font(19),fill='#fafafa');gallery.paste(image,(x,y+40))
    gallery.save(args.output/'gallery.png')
    manifest=dict(passed=True,ui_sha256=hashlib.sha256((ROOT/'src/ui.lua').read_bytes()).hexdigest(),scenarios=report,actual_ui_code_executed=True,synthetic_state=True,approximate_pillow_layout=True,physical_verified=False,device_accessed=False)
    (args.output/'layout-review.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,scenarios=len(report),actual_ui_code_executed=True,physical_verified=False)))

if __name__=='__main__':main()
