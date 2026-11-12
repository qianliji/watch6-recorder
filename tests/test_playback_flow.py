from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from build_settings import prepare_python_dependencies
prepare_python_dependencies()
from lupa.lua54 import LuaRuntime
class PlaybackFlow(unittest.TestCase):
 def test_lifecycle_and_cleanup(self):
  lua=LuaRuntime(unpack_returned_tuples=True)
  factory=lambda name:lua.execute((ROOT/'src'/(name+'.lua')).read_text(encoding='utf-8'))
  result=lua.execute((ROOT/'tests/playback_flow.lua').read_text(encoding='utf-8'))(factory('archive'),factory('playback'),factory('json'))
  report={k:v for k,v in result.items()};self.assertGreaterEqual(report['assertions'],30)
  (ROOT/'build').mkdir(exist_ok=True);(ROOT/'build/playback-flow-test-report.json').write_text(json.dumps(dict(report,passed=True),indent=2)+'\n')
if __name__=='__main__':unittest.main()
