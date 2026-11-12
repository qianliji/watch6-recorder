"""Privacy contract tests use synthetic temporary projects, never actual secrets."""
from pathlib import Path
import importlib.util,json,struct,tempfile,unittest,zipfile,zlib
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('recorder_package_source',ROOT/'tools/package_source.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def icon_png():
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+chunk(b'IEND',b'')

class PrivacyTest(unittest.TestCase):
 def setUp(self):
  self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)/'project';self.root.mkdir()
  for name in ['LICENSE','README.md','NOTICE.md','build.py','src/recorder.lua','native/p65-media.c','tests/run_all.py']:
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic source\n',encoding='utf-8')
  self.put('build.py',"VERSION='"+module.DEFAULT_VERSION+"'\nsettings=dict(transport='mifitness')\n")
 def put(self,name,data='synthetic private material'):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8');return p
 def test_private_build_config_is_not_read(self):
  private=self.put('.local-build.json');original=Path.read_bytes
  def read(p):
   self.assertNotEqual(p,private,'Private build configuration was read');return original(p)
  with patch.object(Path,'read_bytes',read):files=module.collect(self.root)
  self.assertNotIn('.local-build.json',files)
 def test_external_packer_and_binary_files_are_not_read(self):
  excluded=[self.put('tools/Mi8WfBinTool.java'),self.put('native/firmware.bin'),self.put('artifacts/module.elf'),self.put('tests/private/cloud.key'),self.put('adapters/settings.json'),self.put('assets/recording.wav')];original=Path.read_bytes
  def read(p):self.assertNotIn(p,excluded);return original(p)
  with patch.object(Path,'read_bytes',read):module.collect(self.root)
 def test_keys_rejected_without_echoing_values(self):
  self.put('src/example.lua','local key="'+'sk-'+'a'*28+'"')
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertNotIn('a'*28,str(error.exception));self.assertEqual(error.exception.findings[0]['category'],'provider_key')
 def test_non_prefixed_assigned_credentials_rejected(self):
  self.put('src/example.lua','api_'+'key="'+'x'*28+'"')
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertEqual(error.exception.findings[0]['category'],'assigned_secret')
 def test_personal_path_rejected(self):
  self.put('docs/note.md','D'+':'+chr(92)+'personal'+chr(92)+'project')
  with self.assertRaises(module.Rejected):module.collect(self.root)
 def test_symlink_namespace_rejected(self):
  outside=Path(self.temporary.name)/'outside';outside.mkdir();(outside/'secret.py').write_text('synthetic',encoding='utf-8')
  try:(self.root/'tools').symlink_to(outside,target_is_directory=True)
  except OSError:self.skipTest('Symlinks unavailable for current Windows user')
  with self.assertRaises(module.Rejected):module.collect(self.root)
 def test_archive_hashes_and_private_exclusion(self):
  self.put('.local-build.json');archive=Path(self.temporary.name)/'source.zip';result=module.package(self.root,archive)
  self.assertTrue(result['passed'])
  with zipfile.ZipFile(archive) as z:
   prefix='Watch6-Recorder-'+module.DEFAULT_VERSION+'/'
   self.assertFalse(any('.local-build' in n for n in z.namelist()));manifest=json.loads(z.read(prefix+'SOURCE_MANIFEST.json'))
   for item in manifest['files']:self.assertEqual(module.digest(z.read(prefix+item['path'])),item['sha256'])
 def test_archive_never_overwrites_existing(self):
  archive=Path(self.temporary.name)/'source.zip';archive.write_bytes(b'synthetic existing')
  with self.assertRaises(FileExistsError):module.package(self.root,archive)
  self.assertEqual(archive.read_bytes(),b'synthetic existing')

 def test_phone_public_sources_are_explicitly_included(self):
  included=['phone-app/AndroidManifest.xml','phone-app/build.py','phone-app/README.md','phone-app/WIRE.md','phone-app/SOURCE_PROVENANCE.json','phone-app/build-config.example.json','phone-app/.gitignore','phone-app/src/com/example/Main.java','phone-app/assets/index.html','phone-app/assets/style.css','phone-app/assets/app.js','phone-app/res/values/strings.xml','phone-app/tests/StoreTest.java','phone-app/tests/run_storage.py','phone-app/watch-identity/package.json','phone-app/watch-identity/build.cjs','phone-app/watch-identity/src/app.ux','phone-app/watch-identity/src/manifest.json',module.PHONE_IDENTITY_ICON]
  for name in included:self.put(name,'{}' if name.endswith('.json') else 'synthetic source')
  (self.root/module.PHONE_IDENTITY_ICON).write_bytes(icon_png())
  files=module.collect(self.root)
  for name in included:self.assertIn(name,files)
 def test_phone_private_and_unreviewed_sources_are_never_read(self):
  names=['phone-app/.local-build.json','phone-app/.local-build.private.json','phone-app/.test-deps/json.jar','phone-app/libs/sdk.jar','phone-app/libs/secret.java','phone-app/signing/development.jks','phone-app/signing/secret.json','phone-app/build/generated.java','phone-app/artifacts/report.json','phone-app/phone-build.log','phone-app/unreviewed.java','phone-app/assets/test.wav','phone-app/assets/secret.json','phone-app/src/native.c','phone-app/tests/recording.json','phone-app/res/drawable/secret.java','phone-app/watch-identity/sign/release/private.pem','phone-app/watch-identity/node_modules/copy.js','phone-app/watch-identity/build/app.js','phone-app/watch-identity/dist/manifest.json','phone-app/watch-identity/.build-history/manifest.json','phone-app/watch-identity/src/private/config.json','phone-app/watch-identity/src/common/unreviewed.png','phone-app/watch-identity/unreviewed.json']
  excluded=[self.put(name) for name in names];original=Path.read_bytes
  def read(p):self.assertNotIn(p,excluded,'Private or unreviewed phone source was read');return original(p)
  with patch.object(Path,'read_bytes',read):files=module.collect(self.root)
  for name in names:self.assertNotIn(name,files)
 def test_phone_credentials_block_export_with_metadata_only(self):
  for name in ['phone-app/assets/app.js','phone-app/watch-identity/src/app.ux','phone-app/src/com/example/Main.java']:
   self.put(name,'const token="'+'sk-'+'z'*28+'"')
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  findings=error.exception.findings
  self.assertEqual(len(findings),3)
  self.assertTrue(all(set(f)=={'path','line','category'} for f in findings))
  self.assertNotIn('z'*28,str(error.exception))
  self.assertNotIn('z'*28,json.dumps(findings))
 def test_phone_signing_password_and_private_identity_rejected(self):
  self.put('phone-app/src/Main.java','password="'+'credential-'+'x'*12+'"')
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertEqual(error.exception.findings[0]['category'],'assigned_secret')
 def test_phone_root_symlink_rejected(self):
  outside=Path(self.temporary.name)/'outside';outside.mkdir();(outside/'README.md').write_text('synthetic',encoding='utf-8')
  try:(self.root/'phone-app').symlink_to(outside,target_is_directory=True)
  except OSError:self.skipTest('Symlinks unavailable for current Windows user')
  with self.assertRaises(module.Rejected):module.collect(self.root)
 def test_phone_identity_symlink_rejected(self):
  outside=Path(self.temporary.name)/'outside';outside.mkdir();(self.root/'phone-app').mkdir()
  try:(self.root/'phone-app/watch-identity').symlink_to(outside,target_is_directory=True)
  except OSError:self.skipTest('Symlinks unavailable for current Windows user')
  with self.assertRaises(module.Rejected):module.collect(self.root)
 def test_source_version_is_explicit_and_cannot_escape_zip_prefix(self):
  self.put('build.py',"VERSION='0.2.0-wire.1'\nsettings=dict(transport='mifitness')\n")
  archive=Path(self.temporary.name)/'source.zip';module.package(self.root,archive,'0.2.0-wire.1')
  with zipfile.ZipFile(archive) as z:self.assertIn('Watch6-Recorder-0.2.0-wire.1/SOURCE_MANIFEST.json',z.namelist())
  for invalid in ['../escape','0.2.0/../../escape','',None,'0.2.0\\escape']:
   with self.assertRaises(ValueError):module.package(self.root,Path(self.temporary.name)/'unused.zip',invalid)
 def test_phone_files_participate_in_manifest_hashes(self):
  self.put('phone-app/src/Main.java','synthetic source');archive=Path(self.temporary.name)/'phone.zip';module.package(self.root,archive)
  with zipfile.ZipFile(archive) as z:
   prefix='Watch6-Recorder-'+module.DEFAULT_VERSION+'/';manifest=json.loads(z.read(prefix+'SOURCE_MANIFEST.json'));entry=next(f for f in manifest['files'] if f['path']=='phone-app/src/Main.java');self.assertEqual(entry['sha256'],module.digest(z.read(prefix+entry['path'])))

 def test_phone_binary_disguised_as_source_rejected_with_metadata(self):
  p=self.put('phone-app/src/Binary.java');p.write_bytes(bytes([255,254,0,1]))
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertEqual(error.exception.findings,[{'path':'phone-app/src/Binary.java','category':'non_utf8_source'}])
 def test_phone_example_credentials_never_allowed(self):
  self.put('phone-app/build-config.example.json',json.dumps({'api_'+'key':'synthetic-placeholder'}))
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertEqual(error.exception.findings[0]['category'],'credential_in_build_example')
 def test_phone_oversize_source_is_not_read(self):
  p=self.put('phone-app/src/Oversize.java','a'*(2*1024*1024+1));original=Path.read_bytes
  def read(path):self.assertNotEqual(path,p);return original(path)
  with patch.object(Path,'read_bytes',read),self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertEqual(error.exception.findings[0]['category'],'unexpected_source_size')

 def test_retired_transports_and_capture_probe_are_never_read(self):
  names=['watch-app-probe/package.json','watch-app-probe/src/app.ux',
   'src/direct-link.lua','src/link-migration.lua','native/reverse-ble-owner.c',
   'native/reverse-wire.h','native/reverse-export-fs.c','adapters/reverse-ble-guards.json',
   'tools/reverse_ble_profile.py','tools/inspect_rpk_bootstrap.py',
   'tests/test_reverse_ble_owner.py','tests/test_reverse_export_fs.py',
   'tests/reverse_owner_host.c','tests/ReverseEndToEndHarness.java',
   'tests/test_legacy_migration_regression.py','tests/reproduce_legacy_release.py',
   'tests/reproduce_legacy_release.lua','tests/direct_link_flow.lua','tests/link_migration_flow.lua',
   'docs/DIRECT_LINK_API.md','docs/RELEASE_0.3.1.md','docs/RELEASE_0.3.2.md',
   'docs/SINGLE_INSTALL_RPK_RESEARCH_20261107.md','docs/RPK_NATIVE_TOOLCHAIN_20261107.md',
   'phone-app/src/com/watch6/recorder/DirectHandshake.java',
   'phone-app/src/com/watch6/recorder/BlePeripheral.java',
   'phone-app/src/com/watch6/recorder/blewire/WireSession.java']
  excluded=[self.put(name) for name in names];original=Path.read_bytes
  def read(path):self.assertNotIn(path,excluded,'Retired source was read');return original(path)
  with patch.object(Path,'read_bytes',read):files=module.collect(self.root)
  self.assertTrue(set(names).isdisjoint(files))
 def test_active_transport_and_registry_sources_remain_included(self):
  names=['src/phone-link.lua','src/registry.lua','native/phone-link.c',
   'native/export-relay.c','native/export-relay-fs.c','native/export-relay-json.c',
   'native/registry-query.c','native/registry-profile.h','tools/registry_profile.py',
   'tools/phone_link_profile.py','tests/test_phone_transport.py','tests/test_registry_lua_native.py']
  for name in names:self.put(name)
  self.assertTrue(set(names)<=module.collect(self.root).keys())
 def test_archive_version_must_match_watch_build_version(self):
  archive=Path(self.temporary.name)/'source.zip'
  with self.assertRaises(module.Rejected) as error:module.package(self.root,archive,'0.3.2-preview')
  self.assertEqual(error.exception.findings,[dict(path='build.py',category='source_archive_version_mismatch')]);self.assertFalse(archive.exists())
 def test_direct_transport_cannot_be_labeled_as_active_release(self):
  self.put('build.py',"VERSION='"+module.DEFAULT_VERSION+"'\nsettings=dict(transport='direct-ble')\n")
  archive=Path(self.temporary.name)/'source.zip'
  with self.assertRaises(module.Rejected) as error:module.package(self.root,archive)
  self.assertEqual(error.exception.findings,[dict(path='build.py',category='inactive_release_transport')]);self.assertFalse(archive.exists())
 def test_manifest_states_active_route_and_physical_acceptance_boundary(self):
  archive=Path(self.temporary.name)/'source.zip';module.package(self.root,archive)
  with zipfile.ZipFile(archive) as zipped:manifest=json.loads(zipped.read('Watch6-Recorder-'+module.DEFAULT_VERSION+'/SOURCE_MANIFEST.json'))
  self.assertEqual(manifest['transport'],'mifitness');self.assertTrue(manifest['fitness_required']);self.assertTrue(manifest['identity_rpk_required'])
  self.assertFalse(manifest['physical_verified']);self.assertFalse(manifest['standalone_capture_probe_included']);self.assertFalse(manifest['independent_ble_sources_included'])
 def test_identity_png_bytes_are_preserved_and_metadata_is_rejected(self):
  path=self.put(module.PHONE_IDENTITY_ICON);original=icon_png();path.write_bytes(original)
  self.assertEqual(module.collect(self.root)[module.PHONE_IDENTITY_ICON],original)
  payload=b'synthetic\x00metadata';kind=b'tEXt';chunk=struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
  path.write_bytes(original[:-12]+chunk+original[-12:])
  with self.assertRaises(module.Rejected) as error:module.collect(self.root)
  self.assertEqual(error.exception.findings,[dict(path=module.PHONE_IDENTITY_ICON,category='unexpected_identity_png_metadata')])

if __name__=='__main__':unittest.main()
