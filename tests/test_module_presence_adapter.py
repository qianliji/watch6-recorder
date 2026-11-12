from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_settings import prepare_python_dependencies

prepare_python_dependencies()
from lupa.lua54 import LuaRuntime


class ModulePresenceAdapterTests(unittest.TestCase):
    def test_real_lua_owners_use_native_registry_and_retry_unknown(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        factories = [
            lua.execute((ROOT / 'src' / name).read_text(encoding='utf-8'))
            for name in ('phone-link.lua', 'archive.lua', 'source.lua', 'json.lua')
        ]
        flow = lua.execute((ROOT / 'tests/module_presence_flow.lua').read_text(encoding='utf-8'))
        result = flow(*factories)
        self.assertTrue(result['passed'])
        self.assertGreaterEqual(result['assertions'], 120)
        self.assertEqual(result['device_calls'], 0)
        self.assertEqual(result['microphone_calls'], 0)
        print(f"Native registry Lua adapter assertions: {result['assertions']}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
