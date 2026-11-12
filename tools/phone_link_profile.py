"""Generate the exact P65 phone-link guard profile; host-side, no device calls."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_settings import firmware_path

AP_SHA256 = 'a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858'
SPECS = [
    ('open_veneer', 0x0c8bef00, 8), ('read_veneer', 0x0c8beaf0, 8),
    ('write_veneer', 0x0c8be040, 8), ('close_veneer', 0x0c8bdba8, 8),
    ('module_locked_initializer', 0x0c4c49ac, 0x138),
    ('task_spawn', 0x0c4c96f4, 0xd8),
    ('task_spawn_initialize', 0x0c4c8cac, 0xd0),
    ('task_spawn_entry_arguments', 0x0c4c8fe8, 0x138),
    ('task_getpid', 0x0c4c96ac, 0x24),
    ('task_pid_lookup_critical', 0x0c4c5c44, 0x4c),
    ('task_attributes_init', 0x0c4fdcc8, 0x40),
    ('task_attributes_stack', 0x0c4fdd68, 0x24),
    ('uv_loop_init', 0x0c626360, 0x1a8),
    ('uv_loop_close', 0x0c62b528, 0x68),
    ('uv_loop_cleanup', 0x0c626508, 0xa4),
    ('uv_global_tls', 0x0c626620, 0xb0),
    ('uv_global_tls_destructor', 0x0c6265ac, 0x18),
    ('uv_run', 0x0c6220c8, 0x34c),
    ('uv_close', 0x0c621f98, 0xcc),
    ('uv_timer_init', 0x0c629dd0, 0x44),
    ('uv_timer_stop', 0x0c629e14, 0x1a0),
    ('uv_timer_start', 0x0c629fb4, 0x1a0),
    ('uv_timer_close', 0x0c62a2a0, 0xc),
    ('uv_timer_existing_caller', 0x0c9e3c66, 0xc0),
    ('miwear_connect', 0x0c62dd9c, 0xc8),
    ('miwear_send_dispatch', 0x0c62de64, 0xec),
    ('miwear_client_send', 0x0c62d610, 0xf8),
    ('miwear_write_done', 0x0c62d920, 0x88),
    ('miwear_stream_receive', 0x0c62d470, 0x1a0),
    ('miwear_reader', 0x0c62d708, 0x174),
    ('miwear_pipe_connected', 0x0c62d87c, 0xa4),
    ('miwear_reader_start', 0x0c62da9c, 0x94),
    ('miwear_close', 0x0c62df50, 0x28),
    ('miwear_close_callback', 0x0c62d37c, 0x1c),
    ('miwear_close_cancel_and_free', 0x0c62d2b4, 0xb4),
    ('miwear_reader_disconnect', 0x0c62d368, 0x14),
    ('miwear_existing_callback', 0x0c9d0b10, 0x130),
    ('miwear_stock_message', 0x0c82e1ec, 0x54),
    ('malloc', 0x0c50b2a0, 0x80), ('free', 0x0c50b25c, 0x48),
]


def generate(ap_path=None):
    root = Path(__file__).resolve().parents[1]/"adapters"
    ap_path = ap_path or firmware_path('ap')
    ap = Path(ap_path).read_bytes()
    assert hashlib.sha256(ap).hexdigest() == AP_SHA256
    rows = []
    for name, address, count in SPECS:
        offset = address - 0x0c0c0000
        raw = ap[offset:offset+count]
        assert len(raw) == count
        fnv = 2166136261
        for byte in raw:
            fnv = ((fnv ^ byte) * 16777619) & 0xffffffff
        rows.append(dict(id=name, address=address, offset=offset, count=count,
                         fnv=fnv, sha256=hashlib.sha256(raw).hexdigest()))
    report = dict(reference_ap_sha256=AP_SHA256, firmware='P65 3.100.043',
                  status='static candidate; not device validated',
                  device_execution=False, tests_run=False,
                  loop_bytes=0x280, timer_storage_bytes=0xa0,
                  connection_bytes=20, message_bytes=20,
                  worker_stack_bytes=8192, module_name='w6rxlink', windows=rows)
    (root/'phone-link-guards.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    lines = ['/* Generated only from the pinned P65 AP. */',
             'static const struct firmware_guard phone_guards[] = {']
    lines += ['{UINT32_C(0x%08x),%du,UINT32_C(0x%08x)},' % (r['address'],r['count'],r['fnv']) for r in rows]
    lines += ['};', '']
    (root/'phone-link-guards.h').write_text('\n'.join(lines), encoding='ascii')
    return report


if __name__ == '__main__':
    r=generate()
    print(json.dumps(dict(windows=len(r['windows']),device_execution=False)))
