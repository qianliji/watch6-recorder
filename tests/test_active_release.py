"""The active release must not import retired experimental test dependencies."""
from pathlib import Path
import importlib.util,io,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('recorder_active_runner',ROOT/'tests/run_all.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
profile_spec=importlib.util.spec_from_file_location('recorder_registry_profile',ROOT/'tools/registry_profile.py');profile=importlib.util.module_from_spec(profile_spec);profile_spec.loader.exec_module(profile)

class ActiveReleaseTests(unittest.TestCase):
 def test_default_discovery_never_imports_experimental_test(self):
  with tempfile.TemporaryDirectory() as temporary:
   directory=Path(temporary)
   (directory/'test_release_synthetic_active.py').write_text('import unittest\nclass Active(unittest.TestCase):\n def test_pass(self):pass\n',encoding='utf-8')
   (directory/'test_reverse_release_synthetic.py').write_text("raise RuntimeError('retired dependency imported')\n",encoding='utf-8')
   suite=runner.discover_tests(directory);result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
   self.assertTrue(result.wasSuccessful());self.assertEqual(result.testsRun,1)
   self.assertNotIn('test_reverse_release_synthetic',sys.modules)
 def test_experimental_discovery_requires_explicit_opt_in(self):
  with tempfile.TemporaryDirectory() as temporary:
   directory=Path(temporary)
   (directory/'test_reverse_release_opt_in.py').write_text('import unittest\nclass Historical(unittest.TestCase):\n def test_pass(self):pass\n',encoding='utf-8')
   suite=runner.discover_tests(directory,include_experimental=True);result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
   self.assertTrue(result.wasSuccessful());self.assertEqual(result.testsRun,1)
 def test_registry_profile_maps_only_the_pinned_ap_region(self):
  self.assertEqual(profile.offset(0x0c0c0000),0);self.assertEqual(profile.offset(0x0cbfffff),0xb3ffff)
  for address in (0x0c0bffff,0x0cc00000,0x1c000000,0x3c000000):
   with self.subTest(address=address),self.assertRaises(ValueError):profile.offset(address)
  self.assertEqual(profile.fnv(b'hello'),0x4f9f2cab)

if __name__=='__main__':unittest.main()
