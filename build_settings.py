"""External build inputs, kept separate from public watch source and runtime.

Paths come from environment or an ignored .local-build.json beside this file.
Importing this module does not inspect firmware, SDKs or private configuration.
"""
from pathlib import Path
import hashlib,json,os,sys,zipfile

ROOT=Path(__file__).resolve().parent
AP_SHA256='a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858'
AUDIO_SHA256='e6013c449d6b0b2a762babb280c804356b34ba4ae681a84b4f1a4d9a61bae13c'
TOOLCHAIN_ARCHIVE_SHA256='bae6a3d1667697ce750c3b13d6d26d80973ecedc2cc87bf04869e83447fd93ea'
P65_ARCHIVE='miwear.watch.p65_v3.100.043_full_662aa7db.bin'

def configuration(env=None,root=ROOT):
    env=dict(os.environ if env is None else env);root=Path(root).resolve()
    private=Path(env.get('VOICESPACE_WATCH_BUILD_CONFIG',str(root/'.local-build.json'))).expanduser()
    if not private.is_absolute():private=Path.cwd()/private
    try:settings=json.loads(private.read_text(encoding='utf-8-sig')) if private.is_file() else {}
    except (ValueError,OSError):raise ValueError('Invalid private watch build configuration') from None
    if not isinstance(settings,dict):raise ValueError('Watch build configuration must be an object')
    fields={
        'firmware_directory':('VOICESPACE_WATCH_FIRMWARE',),
        'firmware_ap':('VOICESPACE_WATCH_FIRMWARE_AP',),
        'firmware_audio':('VOICESPACE_WATCH_FIRMWARE_AUDIO',),
        'firmware_archive':('VOICESPACE_WATCH_FIRMWARE_ARCHIVE',),
        'firmware_resource':('VOICESPACE_WATCH_FIRMWARE_RESOURCE',),
        'arm_toolchain':('VOICESPACE_ARM_TOOLCHAIN',),
        'arm_toolchain_manifest':('VOICESPACE_ARM_TOOLCHAIN_MANIFEST',),
        'arm_toolchain_archive':('VOICESPACE_ARM_TOOLCHAIN_ARCHIVE',),
        'java_home':('VOICESPACE_WATCH_JAVA_HOME','JAVA_HOME'),
        'python_dependencies':('VOICESPACE_WATCH_PYTHON_DEPENDENCIES','VOICESPACE_LUA_DEPS'),
        'external_packer_source':('W6R_PACKER_SOURCE',),
        'test_dependencies':('W6R_TEST_DEPENDENCIES',),
    }
    out={}
    for key,names in fields.items():
        value=None;base=private.parent
        for name in names:
            if env.get(name):value=env[name];base=Path.cwd();break
        if value is None:value=settings.get(key)
        if value in (None,''):out[key]=None;continue
        if not isinstance(value,(str,os.PathLike)):raise ValueError('Watch build path must be text: '+key)
        path=Path(os.path.expandvars(os.fspath(value))).expanduser()
        out[key]=(path if path.is_absolute() else base/path).resolve()
    return out

def _required(path,name):
    if path is None:raise ValueError('Configure '+name+' in environment or .local-build.json')
    return path

def program(directory,name):
    """Find the named executable without leaking configured machine paths."""
    for suffix in (('.exe','') if os.name=='nt' else ('','.exe')):
        candidate=Path(directory)/(name+suffix)
        if candidate.is_file():return candidate
    raise FileNotFoundError('Missing build executable: '+name)

def arm_tools(env=None,root=ROOT):
    c=configuration(env,root);tools=c['arm_toolchain']
    if c['arm_toolchain_manifest']:
        try:meta=json.loads(c['arm_toolchain_manifest'].read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):raise ValueError('Invalid ARM toolchain provenance manifest') from None
        if meta.get('verified_zip_sha256')!=TOOLCHAIN_ARCHIVE_SHA256:raise ValueError('ARM toolchain archive checksum does not match the pinned build')
        if tools is None:
            raw=meta.get('toolchain_directory')
            if not isinstance(raw,str) or not raw:raise ValueError('ARM toolchain directory is not configured')
            tools=Path(raw).expanduser()
            if not tools.is_absolute():tools=c['arm_toolchain_manifest'].parent/tools
            tools=tools.resolve()
    if c['arm_toolchain_archive']:
        if hashlib.sha256(c['arm_toolchain_archive'].read_bytes()).hexdigest()!=TOOLCHAIN_ARCHIVE_SHA256:raise ValueError('ARM toolchain archive checksum does not match the pinned build')
    tools=_required(tools,'VOICESPACE_ARM_TOOLCHAIN')
    if (tools/'bin').is_dir():tools=tools/'bin'
    for name in ('arm-none-eabi-gcc','arm-none-eabi-ld','arm-none-eabi-objdump'):program(tools,name)
    return tools

def java_bin(env=None,root=ROOT):
    home=_required(configuration(env,root)['java_home'],'JAVA_HOME');directory=home/'bin'
    for name in ('java','javac'):program(directory,name)
    return directory

def firmware_path(kind='ap',env=None,root=ROOT):
    c=configuration(env,root)
    names={'ap':'vela_ap.bin','audio':'vela_audio.bin','archive':P65_ARCHIVE,'resource':'vela_resource.bin'}
    if kind not in names:raise ValueError('Unknown firmware input')
    path=c['firmware_'+kind]
    if path is None and c['firmware_directory'] is not None:path=c['firmware_directory']/names[kind]
    path=_required(path,'VOICESPACE_WATCH_FIRMWARE or VOICESPACE_WATCH_FIRMWARE_'+kind.upper())
    if not path.is_file():raise FileNotFoundError('Missing external P65 firmware input: '+kind)
    return path

def firmware_audio_bytes(env=None,root=ROOT):
    c=configuration(env,root);audio=c['firmware_audio']
    if audio is None and c['firmware_directory'] is not None:audio=c['firmware_directory']/'vela_audio.bin'
    if audio is not None and audio.is_file():raw=audio.read_bytes()
    else:
        with zipfile.ZipFile(firmware_path('archive',env,root)) as package:raw=package.read('vela_audio.bin')
    if hashlib.sha256(raw).hexdigest()!=AUDIO_SHA256:raise ValueError('Audio firmware differs from the pinned P65 build')
    return raw

def prepare_python_dependencies(env=None,root=ROOT):
    path=configuration(env,root)['python_dependencies']
    if path is not None and str(path) not in sys.path:sys.path.insert(0,str(path))

def lua_runtime():
    prepare_python_dependencies()
    try:from lupa.lua54 import LuaRuntime
    except ImportError:raise ImportError('Install lupa for the build Python, or configure VOICESPACE_WATCH_PYTHON_DEPENDENCIES') from None
    return LuaRuntime
