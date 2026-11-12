from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import prepare_python_dependencies
prepare_python_dependencies()
from lupa.lua54 import LuaRuntime

class PhoneLinkLuaTests(unittest.TestCase):
 def test_background_lifecycle_and_read_only_restore(self):
  lua=LuaRuntime(unpack_returned_tuples=True)
  factory=lua.execute((ROOT/'src/phone-link.lua').read_text(encoding='utf-8'))
  codec=lua.execute((ROOT/'src/json.lua').read_text(encoding='utf-8'))
  result=lua.execute((ROOT/'tests/phone_link_flow.lua').read_text(encoding='utf-8'))(factory,codec)
  self.assertTrue(result['passed']);self.assertGreaterEqual(result['assertions'],20)

if __name__=='__main__':unittest.main(verbosity=2)
