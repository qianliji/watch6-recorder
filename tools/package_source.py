"""Export only reviewed recorder source; never archive the working directory."""
from pathlib import Path, PurePosixPath
import argparse,ast,hashlib,json,os,re,struct,zipfile,zlib

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'README.md','LICENSE','NOTICE.md','CONTRIBUTING.md','SECURITY.md','.gitignore',
    'build.py','build_settings.py','build-config.example.json','BUILDING.md','requirements.txt','requirements-dev.txt','requirements-build.txt','SOURCE_PROVENANCE.json'}
TREES={'src','native','adapters','docs','tests','tools','.github','assets'}
SUFFIXES={'.py','.lua','.c','.h','.ld','.json','.md','.txt','.yml','.yaml'}
PRIVATE_PARTS={'build','artifacts','dist','runtime','logs','recordings','node_modules','dependencies','__pycache__','.git','private','backups','libs','sdk','sign','signing','.test-deps','.build-history'}
PRIVATE_NAMES={'settings.json','cloud_ssh.json','cloud.key','cloud_known_hosts','known_hosts','.local-build.json'}
PATTERNS={
 'provider_key':re.compile(r'\bsk-[A-Za-z0-9_-]{16,}'),
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'personal_home':re.compile(r'(?i)(?:/public/home/[a-z0-9_.-]+|/home/[a-z0-9_.-]+|[a-z]:[\\/]+Users[\\/]+[^\\/\s]+)'),
 'machine_path':re.compile(r'(?i)\b[a-z]:[\\/]+(?!path[\\/]+to[\\/])'),
 'bluetooth_address':re.compile(r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b'),
 'private_network':re.compile(r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b')}
ASSIGNED_SECRET=re.compile(r'''(?i)["']?(?:api_key|cloud_token|access_token|secret_key|password)["']?\s*[:=]\s*(["'])([^\r\n"']{8,})\1''')


# Phone code uses a separate narrow namespace; dependency and signer folders
# never become eligible merely because a new extension is needed by the app.
PHONE_ROOT_FILES={'README.md','WIRE.md','SOURCE_PROVENANCE.json','build.py',
    'build-config.example.json','AndroidManifest.xml','.gitignore'}
PHONE_TREES={'src':{'.java'},'assets':{'.html','.css','.js'},'res':{'.xml'},
    'tests':{'.py','.java','.cjs'},'docs':{'.md','.txt','.json'}}
PHONE_IDENTITY_FILES={'package.json','build.cjs'}
PHONE_IDENTITY_SUFFIXES={'.ux','.json'}
PHONE_IDENTITY_ICON='phone-app/watch-identity/src/common/icon.png'
DEFAULT_VERSION='0.5.3'
VERSION=re.compile(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?')

# Keep abandoned transports available for local historical work without making
# them part of the active MiFitness source release or its regression suite.
EXPERIMENTAL_FILES={'src/direct-link.lua','src/link-migration.lua',
 'tools/reverse_ble_profile.py','tools/inspect_rpk_bootstrap.py',
 'tests/test_legacy_migration_regression.py','tests/direct_link_flow.lua',
 'tests/link_migration_flow.lua','tests/ReverseEndToEndHarness.java',
 'phone-app/src/com/watch6/recorder/DirectHandshake.java',
 'phone-app/src/com/watch6/recorder/BlePeripheral.java',
 'docs/DIRECT_LINK_API.md','docs/RELEASE_0.3.1.md','docs/RELEASE_0.3.2.md'}

def excluded_release_source(relative):
 p=PurePosixPath(relative.as_posix() if isinstance(relative,Path) else str(relative).replace('\\','/'))
 name=p.as_posix()
 return (p.parts and p.parts[0]=='watch-app-probe') or name in EXPERIMENTAL_FILES or name.startswith((
  'native/reverse-','adapters/reverse-ble-','tests/reverse_',
  'tests/test_reverse_','tests/reproduce_legacy_release.',
  'phone-app/src/com/watch6/recorder/blewire/','docs/SINGLE_INSTALL_','docs/SINGLE_FACE_','docs/RPK_'))

class Rejected(ValueError):
 def __init__(self,findings):
  self.findings=findings
  super().__init__('Source export rejected; sensitive values were not printed')

def digest(data):return hashlib.sha256(data).hexdigest()
def private(p):
 return any(part.lower() in PRIVATE_PARTS for part in p.parts) or p.name.lower() in PRIVATE_NAMES or any(part.startswith('.') and part not in {'.github','.gitignore'} for part in p.parts) or p.name.lower().endswith(('.private.json','.local.json')) or p.name=='Mi8WfBinTool.java'

def source_tree(root,base,suffixes,exact=()):
 selected=[]
 if base.is_symlink():raise Rejected([dict(path=base.relative_to(root).as_posix(),category='linked_source_namespace')])
 if not base.is_dir():return selected
 for directory,dirs,files in os.walk(base,followlinks=False):
  for child in list(dirs):
   p=Path(directory)/child
   if p.is_symlink():raise Rejected([dict(path=p.relative_to(root).as_posix(),category='linked_source_namespace')])
  dirs[:]=sorted(d for d in dirs if not private((Path(directory)/d).relative_to(root)))
  for name in sorted(files):
   p=Path(directory)/name;relative=p.relative_to(root)
   if private(relative) or excluded_release_source(relative):continue
   if p.is_symlink():raise Rejected([dict(path=relative.as_posix(),category='linked_source')])
   if p.suffix in suffixes or relative.as_posix() in exact:selected.append(p)
 return selected

def exact_files(root,base,names):
 selected=[]
 if base.is_symlink():raise Rejected([dict(path=base.relative_to(root).as_posix(),category='linked_source_namespace')])
 for name in sorted(names):
  p=base/name
  if p.is_symlink():raise Rejected([dict(path=p.relative_to(root).as_posix(),category='linked_source')])
  if p.is_file():selected.append(p)
 return selected

def paths(root):
 root=Path(root).resolve();selected=exact_files(root,root,ROOT_FILES)
 for tree in sorted(TREES):selected.extend(source_tree(root,root/tree,SUFFIXES,{'assets/preview.png'}))
 phone=root/'phone-app'
 if phone.is_symlink():raise Rejected([dict(path='phone-app',category='linked_source_namespace')])
 if phone.is_dir():
  selected.extend(exact_files(root,phone,PHONE_ROOT_FILES))
  for tree,suffixes in sorted(PHONE_TREES.items()):selected.extend(source_tree(root,phone/tree,suffixes))
  identity=phone/'watch-identity'
  selected.extend(exact_files(root,identity,PHONE_IDENTITY_FILES))
  selected.extend(source_tree(root,identity/'src',PHONE_IDENTITY_SUFFIXES,{PHONE_IDENTITY_ICON}))
 return sorted(set(selected))

def png(data):
 if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Invalid preview PNG')
 out=bytearray(data[:8]);at=8;ended=False
 while at+12<=len(data):
  length=struct.unpack_from('>I',data,at)[0];end=at+12+length
  if end>len(data):raise ValueError('Truncated PNG')
  kind=data[at+4:at+8];payload=data[at+8:end-4]
  if zlib.crc32(kind+payload)&0xffffffff!=struct.unpack_from('>I',data,end-4)[0]:raise ValueError('PNG CRC mismatch')
  if kind in {b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS',b'gAMA',b'cHRM',b'sRGB'}:out.extend(data[at:end])
  at=end
  if kind==b'IEND':ended=True;break
 if not ended or at!=len(data):raise ValueError('PNG trailing data or missing end')
 return bytes(out)

def collect(root):
 root=Path(root).resolve();output={};findings=[]
 for p in paths(root):
  relative=p.relative_to(root).as_posix()
  if not p.resolve().is_relative_to(root):raise Rejected([dict(path=relative,category='source_outside_root')])
  if p.stat().st_size>2*1024*1024:raise Rejected([dict(path=relative,category='unexpected_source_size')])
  data=p.read_bytes()
  if relative=='assets/preview.png':data=png(data)
  elif relative==PHONE_IDENTITY_ICON:
   # Keep the reviewed identity input byte-for-byte reproducible. Metadata is
   # rejected rather than silently changing the hash expected by its builder.
   if png(data)!=data:raise Rejected([dict(path=relative,category='unexpected_identity_png_metadata')])
  else:
   try:text=data.decode('utf-8-sig')
   except UnicodeDecodeError:raise Rejected([dict(path=relative,category='non_utf8_source')]) from None
   for number,line in enumerate(text.splitlines(),1):
    for category,pattern in PATTERNS.items():
     if pattern.search(line):findings.append(dict(path=relative,line=number,category=category))
    for hit in ASSIGNED_SECRET.finditer(line):
     if not hit.group(2).lower().startswith(('synthetic-','example-','replace-','your-','${')):findings.append(dict(path=relative,line=number,category='assigned_secret'))
   if p.name=='build-config.example.json':
    cfg=json.loads(text)
    if any(k in cfg for k in ['password','api_key','token','cloud_token']):findings.append(dict(path=relative,category='credential_in_build_example'))
  output[relative]=data
 if findings:raise Rejected(findings)
 required={'LICENSE','README.md','NOTICE.md','build.py','src/recorder.lua','native/p65-media.c','tests/run_all.py'}
 if not required<=output.keys():raise Rejected([dict(path=n,category='missing_required_source') for n in sorted(required-output.keys())])
 return output

def release_metadata(files):
 """Read public build declarations; importing the builder would read no inputs,
 but parsing also makes this check independent of local build dependencies.
 """
 try:tree=ast.parse(files['build.py'].decode('utf-8-sig'))
 except (SyntaxError,UnicodeDecodeError):raise Rejected([dict(path='build.py',category='invalid_build_source')]) from None
 versions=[]
 for statement in tree.body:
  if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in statement.targets):
   versions.append(statement.value.value if isinstance(statement.value,ast.Constant) else None)
 if len(versions)!=1 or not isinstance(versions[0],str) or VERSION.fullmatch(versions[0]) is None:
  raise Rejected([dict(path='build.py',category='missing_literal_build_version')])
 transports=[item.value.value if isinstance(item.value,ast.Constant) else None for item in ast.walk(tree) if isinstance(item,ast.keyword) and item.arg=='transport']
 if not transports or any(t!='mifitness' for t in transports):
  raise Rejected([dict(path='build.py',category='inactive_release_transport')])
 return dict(version=versions[0],transport='mifitness',fitness_required=True,identity_rpk_required=True)

def package(root,target,version=DEFAULT_VERSION):
 if not isinstance(version,str) or len(version)>64 or VERSION.fullmatch(version) is None:raise ValueError('Invalid source archive version')
 files=collect(root);metadata=release_metadata(files);target=Path(target)
 if metadata['version']!=version:raise Rejected([dict(path='build.py',category='source_archive_version_mismatch')])
 if target.exists():raise FileExistsError('Refusing to overwrite an existing source archive')
 target.parent.mkdir(parents=True,exist_ok=True)
 manifest=dict(project='Watch6 Recorder',version=version,license='MIT',candidate_only=True,physical_verified=False,
   transport=metadata['transport'],fitness_required=True,identity_rpk_required=True,
   standalone_capture_probe_included=False,independent_ble_sources_included=False,
   external_firmware_or_packer_included=False,private_configuration_included=False,
   files=[dict(path=n,bytes=len(d),sha256=digest(d)) for n,d in files.items()])
 prefix='Watch6-Recorder-'+version+'/'
 with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
  for name,data in files.items():z.writestr(prefix+name,data)
  z.writestr(prefix+'SOURCE_MANIFEST.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
 with zipfile.ZipFile(target) as z:
  if z.testzip() is not None:raise ValueError('Source archive CRC failure')
  for item in manifest['files']:
   data=z.read(prefix+item['path'])
   if len(data)!=item['bytes'] or digest(data)!=item['sha256']:raise ValueError('Source archive mismatch')
 return dict(passed=True,path=str(target),bytes=target.stat().st_size,sha256=digest(target.read_bytes()),source_files=len(files),zip_entries=len(files)+1,physical_verified=False)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--check-only',action='store_true');parser.add_argument('--version',default=DEFAULT_VERSION,help='Source archive version, for example 0.2.0-preview');args=parser.parse_args()
 try:
  if args.check_only:
   files=collect(ROOT);metadata=release_metadata(files);print(json.dumps(dict(passed=True,source_files=len(files),source_version=metadata['version'],transport=metadata['transport'],private_values_output=False,physical_verified=False)));return
  if not args.output:parser.error('--output is required unless --check-only')
  print(json.dumps(package(ROOT,args.output,args.version),ensure_ascii=False))
 except Rejected as e:
  print(json.dumps(dict(passed=False,private_values_output=False,findings=e.findings),ensure_ascii=False));raise SystemExit(1)

if __name__=='__main__':main()
