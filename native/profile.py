"""Exact P65 reference bytes only. No device calls or firmware execution."""
from pathlib import Path
import hashlib,json,struct,zipfile,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from build_settings import firmware_path,firmware_audio_bytes
ROOT=Path(__file__).resolve().parent
AP_SHA='a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858'
AUDIO_SHA='e6013c449d6b0b2a762babb280c804356b34ba4ae681a84b4f1a4d9a61bae13c'
SPECS=[('rec_open',0x1c03a188,0x58),('rec_close_and_join',0x1c03a1e8,0x5c),
 ('rec_set_event',0x1c03a244,0x4c),('stock_prepare_buffer_oracle',0x1c03a290,0x160),
 ('rec_read_oracle',0x1c03a438,0x90),('rec_get_socket_oracle',0x1c03a4c8,0x20),
 ('rec_start',0x1c03a50c,0x20),('rec_pause',0x1c03a52c,0x20),('rec_pause_literal',0x1c2188c0,6),('stock_stop_closes_data_first',0x1c03a54c,0x44),
 ('fixed_rpc_once',0x1c03b2e0,0x1d0),('cpu_audio_literal_selection',0x1c03b4b0,0x164),
 ('proxy_disconnect_joins_thread',0x1c03b178,0x64),
 ('socket_veneer',0x1c167c90,8),('bind_veneer',0x1c1681e8,8),
 ('listen_veneer',0x1c165bf0,8),('accept4_veneer',0x1c165b20,8),
 ('recv_veneer',0x1c1687a8,8),('close_socket',0x1c154d9c,0x54),
 ('event_enum_stock_consumer',0x0c8ddd24,0xc4),
 ('status_open_veneer',0x0c8bef00,8),('status_read_veneer',0x0c8beaf0,8),('status_write_veneer',0x0c8be040,8),('status_close_veneer',0x0c8bdba8,8),
 ('unlink_veneer',0x0c8befd0,8),('unlink_impl',0x1c159914,0x118),
 ('file_fsync',0x1c159e48,0x40),('fsync_fd',0x1c159e88,0x6c),('file_get',0x1c154700,0x9c),('file_put',0x1c15479c,0x58),
 ('socket_type_nonblock',0x0c946674,0xa4),('psock_nonblock',0x0c932f70,0xa8),
 ('accept4_nonblock',0x0c9328b8,0xb0),('rpmsg_accept_handshake',0x0c93d3a8,0xe8),
 ('rpmsg_recv_nonblock',0x0c93d104,0x234),('rpmsg_interface_table',0x1c2b0000,0x48),
 ('errno_tls',0x0c4f793c,0x14),('blocks_procfs_format',0x1c15b994,0x90),
 ('nxsig_usleep',0x0c4c8b38,0x40),('nxsig_nanosleep',0x0c4c87bc,0x100),
 ('clock_elapsed',0x0c4c1e44,0x10),('clock_systime',0x0c4c21dc,0x24),('clock_hardware_ticks',0x0c4da534,0x90)]
def offset(address):
    if 0x1c000000<=address<0x1c3d2080:return 0x2fdc4+address-0x1c000000
    if 0x0c0c0000<=address<0x0cc00000:return address-0x0c0c0000
    raise ValueError(hex(address))
def fnv(data):
    n=2166136261
    for value in data:n=((n^value)*16777619)&0xffffffff
    return n
def generate():
    ap=firmware_path('ap').read_bytes();assert hashlib.sha256(ap).hexdigest()==AP_SHA
    audio=firmware_audio_bytes()
    assert hashlib.sha256(audio).hexdigest()==AUDIO_SHA
    windows=[]
    for name,address,count in SPECS:
        off=offset(address);raw=ap[off:off+count];assert len(raw)==count
        windows.append(dict(id=name,address=address,offset=off,count=count,fnv=fnv(raw),sha256=hashlib.sha256(raw).hexdigest()))
    audio_rows=[]
    # Header records body offset0x120 -> load address0x3db00000. Execution
    # alias is0x1db00000; no AP code may call these audio-CPU addresses.
    for name,off,count in [('image_header',0,0x120),('amoviesink_filter_descriptor',0x2a8124,0x50),
        ('amoviesink_process_command',0x136f1c,0x590),('wav_muxer_class',0x2b8680,0x50)]:
        raw=audio[off:off+count];audio_rows.append(dict(id=name,offset=off,count=count,sha256=hashlib.sha256(raw).hexdigest()))
    result=dict(reference_ap_sha256=AP_SHA,reference_audio_sha256=AUDIO_SHA,firmware='P65 3.100.043',
        status='enabled explicit-user-start candidate; not physically verified',device_execution=False,
        continuous_enabled=True,continuous_verified=False,capability_mask=127,required_capability_mask=127,
        missing=['commercial_buffer_prepare_accept_order_device_acceptance','commercial_flush_stop_tail_device_acceptance','device_filesystem_latency_and_durability_acceptance'],
        windows=windows,audio_evidence=audio_rows,
        callable=dict(open=0x1c03a189,set_event=0x1c03a245,start=0x1c03a50d,pause=0x1c03a52d,close=0x1c03a1e9,
          rpc_once=0x1c03b2e1,socket=0x1c167c91,bind=0x1c1681e9,listen=0x1c165bf1,
          accept4=0x1c165b21,recv=0x1c1687a9,close_socket=0x1c154d9d),
        cpu='audio',rpc_target='ap',rpmsg=dict(family=65,cpu_offset=2,name_offset=18,field_bytes=16,bind_bytes=128),
        events=dict(prepared=1,started=2,paused=3,stopped=4,seeked=5,completed=6),
        notes=['No event callback/firmware function was executed by this generator.',
          'STOPPED enum is proven in AP consumers; exact commercial tail delivery remains a physical acceptance gate.',
          'No set_next_output or commercial segment muxer support is asserted.'])
    shared=json.loads((ROOT.parent/'adapters/loader-guards.json').read_text())
    assert shared['reference_ap_sha256']==AP_SHA
    selected={'module_locked_initializer','task_spawn','task_spawn_initialize','task_spawn_entry_arguments','task_getpid','task_pid_lookup_critical','task_attributes_init','task_attributes_stack'}
    for row in shared['windows']:
        if row['id'] in selected:windows.append(row)
    (ROOT/'profile.json').write_text(json.dumps(result,indent=2)+'\n')
    rows=['/* Generated from exact P65 AP; do not hand-edit addresses. */','static const struct vs_guard source_guards[] = {']
    rows+=['{0x%08xu,%uu,0x%08xu},'%(r['address'],r['count'],r['fnv']) for r in windows]
    rows+=['};','#define VS_STATIC_CAPABILITIES 127u','#define VS_CONTINUOUS_CANDIDATE_ENABLED 1u','#define VS_CONTINUOUS_PHYSICALLY_VERIFIED 0u','']
    (ROOT/'profile.h').write_text('\n'.join(rows));return result
if __name__=='__main__':
    result=generate();print(json.dumps({'ap_windows':len(result['windows']),'capability_mask':result['capability_mask'],'continuous_verified':False}))
