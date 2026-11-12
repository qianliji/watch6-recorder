"""Build an exact-firmware offline recorder preview. Never contacts a device."""
from pathlib import Path
import hashlib,importlib.util,json,struct,subprocess,sys,time
from build_settings import arm_tools,firmware_path,java_bin,lua_runtime,program,configuration

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'build';VERSION='0.5.3'
def run(args):
    r=subprocess.run([str(v) for v in args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if r.returncode:
        detail=r.stderr[-2500:]
        for value in configuration().values():
            if isinstance(value,Path):detail=detail.replace(str(value),'<private build input>')
        raise RuntimeError('Build step failed: '+Path(args[0]).name+'\n'+detail)
    return r.stdout
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lua(v):
    if v is None:return 'nil'
    if v is True:return 'true'
    if v is False:return 'false'
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,(int,float)):return str(v)
    if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
    return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'
def inspect(elf):
    raw=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',raw)
    assert h[0][:7]==b'\x7fELF\x01\x01\x01' and h[1:3]==(1,40) and h[4]==1
    sections=[struct.unpack_from('<10I',raw,h[6]+i*h[11]) for i in range(h[12])];relocations=set()
    for sec in sections:
        if sec[1]==2:
            st=sections[sec[6]];names=raw[st[4]:st[4]+st[5]]
            for p in range(sec[4],sec[4]+sec[5],16):
                n,_,_,_,_,idx=struct.unpack_from('<IIIBBH',raw,p)
                assert not n or idx,'Undefined native import: '+names[n:names.index(0,n)].decode()
        if sec[1]==9:
            for p in range(sec[4],sec[4]+sec[5],8):relocations.add(struct.unpack_from('<II',raw,p)[1]&255)
    assert relocations<={2},'Unsupported relocation'
    assert b'/data/quickapp/files/com.voicespace.mobile/' not in raw
    return dict(bytes=len(raw),sha256=sha(elf),loaded_bytes=sum(s[5] for s in sections if s[2]&2),entry=1,relocations=sorted(relocations),undefined_imports=[])

def generate_profile(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.generate()

def source_inputs():
    """Hash only public watch build/test sources, including nested generators."""
    from tools.package_source import excluded_release_source
    selected={}
    suffixes={'.c','.h','.lua','.py','.json','.ld','.java','.xml','.gradle','.md','.txt','.yml','.yaml'}
    excluded={'build','artifacts','__pycache__','private','firmware','sdk','dependencies','recordings','logs'}
    for base in ['src','native','adapters','tools','tests']:
        for p in sorted((ROOT/base).rglob('*')):
            relative=p.relative_to(ROOT)
            if p.is_file() and not p.is_symlink() and p.suffix in suffixes and not excluded_release_source(relative) and not any(part.startswith('.') or part.lower() in excluded for part in relative.parts) and p.name not in {'settings.json','Mi8WfBinTool.java'}:
                selected[relative.as_posix()]=sha(p)
    for name in ['build.py','build_settings.py','build-config.example.json']:
        selected[name]=sha(ROOT/name)
    return selected

def complete_parse(java,classes,output,package,assets,constants):
    """Use the complete external parser, then independently compare Lua/ELFs."""
    destination=OUT/('complete-parser-check-'+str(time.time_ns()))
    run([program(java,'java'),'-cp',classes,'Mi8WfBinTool','unpack',output,destination,'p65'])
    recovered=destination/'images/lua/main.lua';original=package/'images/lua/main.lua'
    assert recovered.read_bytes()==original.read_bytes(),'Complete parser changed embedded Lua'
    raw=recovered.read_text(encoding='utf-8');runtime=lua_runtime()()
    runtime.compile(raw,name='recovered-watch6-recorder.lua')
    constant_line=raw.splitlines()[1]
    assert constant_line.startswith('local C=')
    decoded=runtime.execute(constant_line+'\nreturn C')
    assert decoded['version']==VERSION and len(decoded['assets'])==len(assets)
    recovered_assets={item['name']:bytes.fromhex(item['hex']) for _,item in decoded['assets'].items()}
    for name,data in assets.items():assert recovered_assets.get(name)==data,'Embedded native ELF differs'
    for key in ['source_asset','player_asset','phone_asset','registry_asset']:assert decoded[key]==constants[key]
    assert decoded['transport']=='mifitness' and decoded['fitness_required'] is True
    assert decoded['wireless_export_identity_required'] is True and decoded['wireless_export_rpk_required'] is True
    assert decoded['identity']['package']=='com.watch6.recorder'
    assert decoded['identity']['same_package_and_signing_certificate_required'] is True
    assert decoded['phone_candidate_enabled'] is True and decoded['physical_verified'] is False
    assert decoded['direct_asset'] is None and decoded['direct_candidate_enabled'] is None
    assert not any(name.startswith('w6r-direct-') for name in recovered_assets)
    assert len(assets)==4 and len(recovered_assets)==4
    assert 'create_direct_link' not in raw and 'create_link_migration' not in raw
    assert b'com.watch6.recorder\x00' in assets[decoded['phone_asset']]
    assert len(decoded['windows'])==len(constants['windows'])
    wf=json.loads((destination/'wfDef.json').read_text(encoding='utf-8'))
    assert wf['id']=='491553031' and wf['elementsNormal'][0]['jsFileName']=='lua/main.lua'
    return dict(passed=True,output=destination.relative_to(ROOT).as_posix(),lua_bytes=original.stat().st_size,lua_sha256=sha(recovered),
                all_embedded_elfs_identical=True,embedded_elf_count=len(assets),lua_compiled=True,guard_windows=len(constants['windows']),
                transport='mifitness',identity_dependency_declared=True,direct_transport_bundled=False,device_accessed=False)
def main():
    OUT.mkdir(exist_ok=True);(ROOT/'artifacts').mkdir(exist_ok=True)
    tools=arm_tools();java=java_bin();c=configuration()
    packer=c.get('external_packer_source')
    if not packer or not packer.is_file():raise ValueError('Set W6R_PACKER_SOURCE to a legally obtained compatible Mi8WfBinTool.java; packer is not included')
    # Profile order is deliberate: player imports the generated shared source
    # guards. The phone transport reuses the MiFitness application-identity
    # route; registry inspection also protects retained experimental owners.
    evidence=generate_profile('recorder_p65_profile',ROOT/'native/profile.py')
    player_evidence=generate_profile('recorder_player_profile',ROOT/'native/player_profile.py')
    phone_evidence=generate_profile('recorder_phone_profile',ROOT/'tools/phone_link_profile.py')
    registry_evidence=generate_profile('recorder_registry_profile',ROOT/'tools/registry_profile.py')
    flags=['-mcpu=cortex-m33','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-fno-common','-fno-pic','-mlong-calls','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-DVS_DATA_ROOT="/data/watch6recorder/"']
    modules={
      'source':dict(entry='watch6_continuous_source_initialize',prefix='vs-continuous-source-',sources=['native-source','spool','p65-media','p65-fs','owner-runtime','p65-owner','status']),
      'player':dict(entry='watch6_player_initialize',prefix='w6r-player-',sources=['player']),
      'phone':dict(entry='watch6_recorder_phone_link_initialize',prefix='w6r-phone-link-',sources=['phone-link','export-relay','export-relay-fs','export-relay-json'],flags=['-ffunction-sections','-fdata-sections']),
      'registry':dict(entry='watch6_registry_query_initialize',prefix='w6r-registry-',sources=['registry-query'],flags=['-ffunction-sections','-fdata-sections'])}
    natives={};assets={};asset_names={}
    for kind,module in modules.items():
        objects=[]
        extra_flags=list(module.get('flags',[]))
        for n in module['sources']:
            # GCC may emit THM_CALL for same-section global helpers despite
            # -mlong-calls. Separate phone helper sections force absolute calls;
            # inspect() below remains the authoritative loader compatibility gate.
            obj=OUT/(n+'.o');run([program(tools,'arm-none-eabi-gcc'),*flags,*extra_flags,'-c',ROOT/'native'/(n+'.c'),'-o',obj]);objects.append(obj)
        elf=OUT/(kind+'.elf');run([program(tools,'arm-none-eabi-ld'),'-r','-e',module['entry'],'-T',ROOT/'native/entry.ld','-o',elf,*objects])
        native=inspect(elf);native['initializer']=module['entry'];natives[kind]=native
        name=module['prefix']+native['sha256'][:12]+'.elf';assets[name]=elf.read_bytes();asset_names[kind]=name
    platform=json.loads((ROOT/'adapters/platform-guards.json').read_text());ap=firmware_path('ap').read_bytes()
    assert hashlib.sha256(ap).hexdigest()==platform['reference_ap_sha256']
    windows=list(platform['windows']);seen={(w['offset'],w['count']) for w in windows}
    for profile in [evidence,player_evidence,phone_evidence,registry_evidence]:
        assert profile['reference_ap_sha256']==platform['reference_ap_sha256']
        for w in profile['windows']:
            identity=(w['offset'],w['count'])
            if identity not in seen:windows.append(w);seen.add(identity)
    for identifier,address,count in [('lua_clock',0x0c5cb8e8,64),('clock_elapsed',0x0c4c1e44,32),('clock_systime',0x0c4c21dc,96),('clock_hardware_ticks',0x0c4da534,96),('nsh_mkdir_command',0x0c284f60,16),('nsh_mkdir_handler',0x0c5b0448,244),('nsh_mkdir_veneer',0x0c8bd850,8),('nsh_absolute_fullpath',0x0c5aef5c,84)]:
        offset=address-0x0c0c0000;raw=ap[offset:offset+count];fnv=2166136261
        for b in raw:fnv=((fnv^b)*16777619)&0xffffffff
        if (offset,count) not in seen:windows.append(dict(id=identifier,offset=offset,count=count,fnv=fnv,sha256=hashlib.sha256(raw).hexdigest()));seen.add((offset,count))
    for w in windows:assert hashlib.sha256(ap[w['offset']:w['offset']+w['count']]).hexdigest()==w['sha256']
    constants=dict(version=VERSION,kernel=platform['kernel'],partitions=platform['partitions'],windows=windows,
      source_asset=asset_names['source'],player_asset=asset_names['player'],phone_asset=asset_names['phone'],registry_asset=asset_names['registry'],transport='mifitness',
      fitness_required=True,wireless_export_identity_required=True,wireless_export_rpk_required=True,
      identity=dict(package='com.watch6.recorder',same_package_and_signing_certificate_required=True,role='fitness-application-identity'),
      player_candidate_enabled=True,phone_candidate_enabled=True,physical_verified=False,
      assets=[dict(name=name,hex=data.hex()) for name,data in assets.items()])
    source='-- Watch6 Recorder '+VERSION+'; explicit capture only; physical acceptance pending.\nlocal C='+lua(constants)+'\n'
    for name,binding in [('json','voice_json'),('registry','create_registry'),('source','create_source'),('catalog','create_catalog'),('recorder','create_recorder'),('archive','create_archive'),('playback','create_playback'),('phone-link','create_phone_link'),('transfer','create_transfer'),('app','create_app'),('ui','create_ui')]:source+='local '+binding+'=(function()\n'+(ROOT/'src'/(name+'.lua')).read_text(encoding='utf-8')+'\nend)()\n'
    source+=(ROOT/'src/main.lua').read_text(encoding='utf-8');lua_runtime()().compile(source,name='watch6-recorder.lua')
    package=OUT/'package-input';(package/'images/lua').mkdir(parents=True,exist_ok=True)
    (package/'images/lua/main.lua').write_text(source,encoding='utf-8',newline='\n')
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(432,514),'black');draw=ImageDraw.Draw(image);draw.rounded_rectangle((28,36,404,478),radius=58,fill='#171717',outline='#777777',width=2);draw.rounded_rectangle((182,134,250,286),radius=34,fill='#fafafa');draw.arc((156,184,276,324),0,180,fill='#fafafa',width=8);draw.line((216,326,216,357),fill='#fafafa',width=8);draw.line((180,358,252,358),fill='#fafafa',width=8);image.save(package/'images/preview.png')
    (package/'wfDef.json').write_text(json.dumps(dict(name='录音机·运动健康',id='491553031',previewImg='preview',previewBgra32=True,elementsNormal=[dict(type='type_element_lua',jsFileName='lua/main.lua',x=0,y=0,w=432,h=514)],elementsAod=[]),ensure_ascii=False),encoding='utf-8')
    classes=OUT/'external-packer';classes.mkdir(exist_ok=True)
    run([program(java,'javac'),'-encoding','UTF-8','-d',classes,packer])
    output=ROOT/'artifacts'/('Watch6-Recorder-'+VERSION+'.bin')
    run([program(java,'java'),'-cp',classes,'Mi8WfBinTool','pack',package,output,'p65'])
    parsed=complete_parse(java,classes,output,package,assets,constants)
    (OUT/'complete-parser-report.json').write_text(json.dumps(parsed,indent=2)+'\n',encoding='utf-8')
    report=dict(version=VERSION,face=dict(path='artifacts/'+output.name,bytes=output.stat().st_size,sha256=sha(output)),native=natives['source'],natives=natives,source_inputs=source_inputs(),
      lua_sha256=sha(package/'images/lua/main.lua'),external_packer_sha256=sha(packer),external_packer_included=False,
      firmware='P65 3.100.043',data_root='/data/watch6recorder/',guard_windows=len(windows),source_and_audio_hashes_verified=True,
      standalone_capture_phone_required=False,wireless_export_phone_required=True,cloud_required=False,
      standalone_capture_rpk_required=False,wireless_export_rpk_required=True,wireless_export_identity_required=True,
      transport='mifitness',fitness_required=True,identity=constants['identity'],
      microphone_started=False,device_accessed=False,physical_verified=False,complete_parser=parsed)
    previous=OUT/'build-report.json'
    if previous.is_file():
        old=json.loads(previous.read_text(encoding='utf-8'));old_version=old.get('version')
        if isinstance(old_version,str) and old_version!=VERSION and all(ch.isalnum() or ch in '._-' for ch in old_version):
            preserved=OUT/('build-report-'+old_version+'.json')
            if not preserved.exists():preserved.write_bytes(previous.read_bytes())
    data=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    (OUT/('build-report-'+VERSION+'.json')).write_text(data,encoding='utf-8');previous.write_text(data,encoding='utf-8')
    print(json.dumps(dict(version=VERSION,face=report['face'],natives=natives,guard_windows=len(windows),complete_parse_passed=True,physical_verified=False),ensure_ascii=False))
if __name__=='__main__':main()
