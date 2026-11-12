"""Product intent and export lifecycle regressions, using only synthetic owners."""
from pathlib import Path
import sys
import unittest
import test_main_integration as integration

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_settings import prepare_python_dependencies
prepare_python_dependencies()
from lupa.lua54 import LuaRuntime


APP = r"""
host={time=0,starts=0,stops=0,cancels=0,prepares=0,exports=0,plays=0,safe=false,
 record={phase='idle'},archive={phase='idle'},transfer_active=false}
local H=host
H.row={id='1111111111111111',status='saved',created=1}
H.app=make({now_ms=function()return H.time end,capture_allowed=function()return H.safe end,
 prepare_allowed=function()return true end,catalog={revision=function()return 0 end,list=function()return {H.row}end},
 recorder={state=function()return H.record end,start=function()H.starts=H.starts+1;H.record.phase='preparing';return true end,
 next=function()if H.record.phase~='saved'then return false end;H.record.phase='idle';return true end,
 stop=function()return false end,pause=function()return false end,resume=function()return false end,recover=function()return false end,tick=function()end,detach=function()end},
 archive={state=function()return H.archive end,info=function()return H.info end,
 prepare=function()H.prepares=H.prepares+1;H.archive.phase='preparing';return true end,
 cancel=function()H.cancels=H.cancels+1;return true end,tick=function()end,detach=function()end},
 player={state=function()return {phase='playing',active=not H.safe}end,stop=function()H.stops=H.stops+1;return true end,
 play=function()H.plays=H.plays+1;return true end,pause=function()return true end,resume=function()return true end,tick=function()end,detach=function()end},
 transfer={state=function()return {phase='idle',active=H.transfer_active}end,phone=function()return {}end,
 start=function()H.exports=H.exports1;return true end,connect=function()return true end,cancel=function()return true end,tick=function()end,detach=function()end}})
function H.act(...)local ok=H.app.act(...);return ok end
"""

TRANSFER = r"""
host={time=0,jobs=0,stops=0,cancels=0,saves=0,ready=false,background=false,
 status={phase='idle',safe_to_release=true,next=0,total_bytes=0}}
local H=host
H.info={id='1111111111111111',total_bytes=8000}
H.transfer=make({now_ms=function()return H.time end,prepare=function()return true end,
 on_saved=function()H.saves=H.saves+1 end,
 link={restore=function()return true end,start=function()return true end,tick=function()end,detach=function()end,
 getStatus=function()return {phase=H.link_phase or (H.ready and 'connected' or 'idle'),nonce_ready=H.ready,background_owned=H.background,connected=H.ready}end,
 exportStatus=function()return H.status end,begin_export=function(info)H.jobs=H.jobs+1;H.background=true;
 H.status={phase='connecting',safe_to_release=false,next=0,total_bytes=info.total_bytes,recording_id=info.id,code=0};return true end,
 cancel_export=function()H.cancels=H.cancels+1;return true end,
 stop=function()H.stops=H.stops+1;return true end}})
function H.start(...)local ok=H.transfer.start(...);return ok end
function H.cancel(...)local ok=H.transfer.cancel(...);return ok end
"""


class Flows(unittest.TestCase):
 def setup_flow(self, name, fixture):
  self.lua = LuaRuntime(unpack_returned_tuples=True)
  self.lua.globals().make = self.lua.execute((ROOT/'src'/f'{name}.lua').read_text(encoding='utf-8'))
  self.lua.execute(fixture)
  return self.lua.globals().host

 def test_pending_record_is_visible_cancelable_and_duplicate_does_not_renew(self):
  h=self.setup_flow('app',APP);a=h.app
  self.assertTrue(h.act('record'));deadline=a.pending()['deadline'];h.time=1000
  self.assertTrue(h.act('record'));self.assertEqual(a.pending()['deadline'],deadline);self.assertEqual(h.stops,1)
  extra=a.view()[2];self.assertTrue(extra['record_preparing']);self.assertEqual(extra['pending_action'],'record')
  self.assertTrue(h.act('cancel_pending'));h.safe=True;a.tick();self.assertEqual(h.starts,0);self.assertIsNone(a.pending())

 def test_rejected_or_duplicate_prepare_does_not_erase_existing_intent(self):
  h=self.setup_flow('app',APP);a=h.app;h.safe=True
  self.assertTrue(h.act('play',h.row.id));deadline=a.pending()['deadline'];h.time=1000
  self.assertTrue(h.act('play',h.row.id));self.assertEqual(h.prepares,1);self.assertEqual(a.pending()['deadline'],deadline)
  self.assertFalse(h.act('export',h.row.id));self.assertEqual(a.pending()['kind'],'play')
  self.assertFalse(h.act('record'));self.assertEqual(a.pending()['kind'],'play')
  h.info=self.lua.table_from({'id':h.row.id});h.archive.phase='ready';a.tick();self.assertEqual(h.plays,1)

 def test_timeout_back_and_detach_cannot_later_open_microphone(self):
  for exit_action in ['cancel_pending','next_record','detach','timeout']:
   with self.subTest(exit=exit_action):
    h=self.setup_flow('app',APP);a=h.app;self.assertTrue(h.act('record'))
    if exit_action=='detach': a.detach()
    elif exit_action=='timeout': h.time=12000
    else: h.act(exit_action)
    h.safe=True;a.tick();self.assertEqual(h.starts,0)
    if exit_action=='detach': self.assertFalse(h.act('record'));self.assertEqual(h.starts,0)

 def test_saved_can_return_idle_and_record_during_background_export(self):
  h=self.setup_flow('app',APP);a=h.app;h.safe=True;h.record.phase='saved';h.transfer_active=True
  self.assertTrue(h.act('next_record'));self.assertEqual(h.starts,0);self.assertEqual(h.record.phase,'idle')
  self.assertTrue(h.act('record'));self.assertEqual(h.starts,1)

 def test_cancel_before_native_job_keeps_selected_record_and_never_starts_later(self):
  h=self.setup_flow('transfer',TRANSFER);t=h.transfer
  self.assertTrue(h.start(h.info));self.assertTrue(h.cancel());h.ready=True;t.tick()
  self.assertEqual(h.jobs,0);self.assertEqual(t.state()['phase'],'cancelled');self.assertEqual(t.state()['id'],h.info.id)

 def test_cancel_active_is_visible_idempotent_and_keeps_cache_pinned(self):
  h=self.setup_flow('transfer',TRANSFER);t=h.transfer;h.ready=True;h.start(h.info);t.tick();h.status.phase='sending';h.status.next=4000
  self.assertTrue(h.cancel());self.assertTrue(h.cancel());self.assertEqual(h.cancels,1)
  self.assertEqual(t.state()['phase'],'cancelling');self.assertTrue(t.state()['active']);self.assertFalse(t.safe_to_release())
  h.status.phase='cancelled';t.tick();self.assertEqual(t.state()['phase'],'cancelled');self.assertFalse(t.safe_to_release())
  h.status.safe_to_release=True;h.background=False;t.tick();self.assertTrue(t.safe_to_release());self.assertTrue(h.start(h.info));t.tick();self.assertEqual(h.jobs,2)

 def test_waiting_retry_is_idempotent_and_timeout_preserves_target(self):
  h=self.setup_flow('transfer',TRANSFER);t=h.transfer;h.start(h.info);h.time=1000
  self.assertTrue(h.start(h.info));h.time=15000;t.tick();h.ready=True;t.tick()
  self.assertEqual(h.jobs,0);self.assertEqual(t.state()['phase'],'error');self.assertEqual(t.state()['id'],h.info.id)

 def test_only_full_saved_receipt_annotates_catalog_and_reconnect_does_not_restart(self):
  h=self.setup_flow('transfer',TRANSFER);t=h.transfer;h.ready=True;h.start(h.info);t.tick()
  h.status.phase='sending';h.status.next=8000;t.tick();self.assertEqual(h.saves,0)
  h.link_phase='reconnecting';h.ready=False;t.tick();self.assertEqual(h.jobs,1);self.assertTrue(t.state()['active']);self.assertFalse(t.safe_to_release());self.assertIn('恢复',t.state()['message'])
  h.status.phase='saved';h.status.next=4000;t.tick();self.assertEqual(h.saves,0);self.assertNotEqual(t.state()['phase'],'saved')
  h.status.next=8000;h.status.code=-1;t.tick();self.assertEqual(h.saves,0)
  h.status.code=0;t.tick();t.tick();self.assertEqual(h.saves,1);self.assertEqual(t.state()['phase'],'saved');self.assertFalse(t.safe_to_release())


class BundledIntentIntegration(unittest.TestCase):
 def setUp(self):
  self.flow=integration.MainIntegration();self.flow.setUp()

 def test_cancel_record_waiting_for_real_player_exit_never_writes_source_go(self):
  f=self.flow;f.begin_play();f.h.player_status(f.codec,'playing',1,False);f.h.advance(300)
  self.assertTrue(f.action('record'));self.assertTrue(f.result['app'].view()[2]['record_preparing'])
  self.assertTrue(f.action('cancel_pending'));f.h.clear();f.h.player_status(f.codec,'done',2,True);f.h.advance(300)
  self.assertEqual(f.result['core'].state()['phase'],'idle');self.assertIsNone(f.h.get(integration.BASE+'vs-meeting-source-go.txt'))
  self.assertFalse(any(e['path'].endswith(' w6rc') for e in f.events('execute')))

 def test_real_export_cancel_keeps_cache_until_closed_worker_and_unload(self):
  f=self.flow;f.begin_export();self.assertTrue(f.action('cancel_export'))
  self.assertEqual(f.result['app'].view()[2]['transfer']['phase'],'cancelling');self.assertIsNotNone(f.h.get(f.cache))
  f.h.phone_status(f.codec,'closing','cancelled',False,True);f.h.advance(300)
  self.assertFalse(f.action('play','fedcba9876543210'));self.assertIsNotNone(f.h.get(f.cache))
  f.h.phone_status(f.codec,'closed','cancelled',True,True);f.h.set('/proc/321/cmdline',None);f.h.set('/proc/321/status',None);f.h.advance(300)
  self.assertTrue(f.action('play','fedcba9876543210'));self.assertIsNone(f.h.get(f.cache))
  self.assertEqual(f.h.get(integration.BASE+'vs-mc-'+integration.RECORD+'-00000001.pcm'),'synthetic original')


if __name__=='__main__': unittest.main(verbosity=2)
