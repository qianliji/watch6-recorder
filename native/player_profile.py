"""Read-only exact-image player ABI guard generator; no firmware bytes shipped."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_settings import firmware_path
from native.profile import AP_SHA,offset,fnv
SPECS=[('player_open',0x1c039bbc,0x60),('player_close_and_join',0x1c039c1c,0x5c),
 ('player_set_event',0x1c039c78,0x4c),('player_prepare_file',0x1c039cc4,0x160),
 ('player_start',0x1c039f50,0x28),('player_stop',0x1c039f78,0x48),
 ('player_pause',0x1c039fc0,0x20),('player_get_position',0x1c03a07c,0x40)]
def generate():
 ap=firmware_path('ap').read_bytes()
 assert hashlib.sha256(ap).hexdigest()==AP_SHA,'unsupported AP image'
 shared=json.loads((ROOT/'native/profile.json').read_text())
 assert shared['reference_ap_sha256']==AP_SHA
 wanted={'fixed_rpc_once','cpu_audio_literal_selection','proxy_disconnect_joins_thread',
  'status_open_veneer','status_read_veneer','status_write_veneer','status_close_veneer',
  'unlink_veneer','unlink_impl','file_fsync','fsync_fd','file_get','file_put','errno_tls',
  'blocks_procfs_format','nxsig_usleep','nxsig_nanosleep','clock_elapsed','clock_systime','clock_hardware_ticks',
  'module_locked_initializer','task_spawn','task_spawn_initialize','task_spawn_entry_arguments',
  'task_getpid','task_pid_lookup_critical','task_attributes_init','task_attributes_stack'}
 rows=[row for row in shared['windows'] if row['id'] in wanted]
 assert {row['id'] for row in rows}==wanted
 for name,address,count in SPECS:
  start=offset(address);data=ap[start:start+count];assert len(data)==count
  rows.append(dict(id=name,address=address,offset=start,count=count,fnv=fnv(data),sha256=hashlib.sha256(data).hexdigest()))
 for row in rows:
  data=ap[row['offset']:row['offset']+row['count']]
  assert hashlib.sha256(data).hexdigest()==row['sha256'] and fnv(data)==row['fnv']
 out=dict(reference_ap_sha256=AP_SHA,firmware='P65 3.100.043',device_execution=False,
  physical_verified=False,status='explicit-play candidate; exact pinned image only',windows=rows,
  callable=dict(open=0x1c039bbd,close=0x1c039c1d,set_event=0x1c039c79,prepare=0x1c039cc5,
   start=0x1c039f51,pause=0x1c039fc1,stop=0x1c039f79,get_position=0x1c03a07d),
  upstream='https://github.com/open-vela/frameworks_multimedia_media/blob/dev/include/media_player.h',
  limitations=['Speaker routing/focus and EOF audibility require physical acceptance.',
   'Unsealed or partial capture is never advertised as complete playback.'])
 (ROOT/'adapters/player-guards.json').write_text(json.dumps(out,indent=2)+'\n')
 (ROOT/'native/player-profile.h').write_text('/* Generated guards, not copied firmware code. */\nstatic const struct w6r_player_guard player_guards[] = {\n'+''.join('{0x%08xu,%uu,0x%08xu},\n'%(r['address'],r['count'],r['fnv'])for r in rows)+'};\n')
 return out
if __name__=='__main__':print(json.dumps({'guard_count':len(generate()['windows']),'physical_verified':False}))
