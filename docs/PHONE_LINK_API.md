# Watch phone/export integration

This describes the active 0.4.0 MiFitness adapter. The watchface owns capture,
playback and complete-archive export. A matching application-identity RPK and
the phone SDK provide the MiFitness application route; the RPK never records.
The independent BLE experiment and standalone RPK capture probe are retired.

`src/phone-link.lua` returns a factory. Pass these plain functions (no implicit `self`):

```lua
local link = create({
  asset = 'phone-link.elf',
  now_ms = monotonic_ms,
  read = read_file,       -- (absolute_path, limit) -> text | nil, errno
  write = write_file,     -- (absolute_path, text) -> true on complete write
  execute = execute,     -- bounded insmod/rmmod; true only on success
  encode = json.encode,
  decode = json.decode,
  on_status = callback,  -- optional
  on_message = callback  -- optional; foreground packets only
})
```

The only commands are `insmod /data/watch6recorder/<asset> w6rxlink` and `rmmod w6rxlink`. `asset` is a trusted build configuration basename, never a user path.

| API | Behavior |
| --- | --- |
| `restore()` / `observe_existing()` | Read-only startup observation. Validates bounded `/proc/modules`, fixed IPC and PID records. Adopts existing background export without a new connection or job. Empty module registry plus absent/stopped owner proves scratch release safe. Unknown/error reads retain it. |
| `start()` | Explicitly loads/reuses the guarded owner. Call `tick()` until `getStatus().nonce_ready` before queuing an export. |
| `begin_export(info)` | Writes and reads back the exact fixed descriptor below. Allowed during `starting`/`connecting`; does not need the phone online. Returns `true` or `false,reason`. |
| `cancel_export()` | Explicit per-job cancel IPC. No original audio deletion. |
| `tick()` | Polls bounded IPC and safely reaps terminated native owner. Returns suggested delay in milliseconds or `nil` when no task is running. |
| `getStatus()` / `status()` | `{phase,connected,transportReady,nonce_ready,background_owned,pid,error}`. Connection phase is `idle/releasing/initializing/starting/connecting/reconnecting/connected/closing/closed/error/retained`. |
| `exportStatus()` | `{phase,next,total_bytes,recording_id,job_sequence,code,pid,source_closed,worker_done,safe_to_release}`. Export phase is `idle/connecting/sending/confirming/saved/cancelled/error`. `saved` requires phone durable completion; cache release still requires `safe_to_release`. |
| `send(packet)` / `on_message(callback)` | Bounded foreground channel. Not admitted while the native exporter owns it. SDK admission is not application delivery. |
| `stop()` | Explicit safe stop. Cancels a pending export before stopping the owner. |
| `detach()` | Ends GUI observation only. An authorized native export keeps running and can be adopted by the next GUI instance. |

`info` is the completed native archive preparation result:

```lua
{ id='0123456789abcdef', -- recording_id is an alias
  cache_id='fedcba9876543210',
  path='/data/watch6recorder/w6r-play-fedcba9876543210.wav',
  rate=8000, total_bytes=4000, data_offset=44,
  archive_hash='abcdef0123456789', pcm_crc32='87654321' }
```

Do not release this `info` while the exporter may reference it. Call archive release only after `exportStatus().safe_to_release` is true, and the independent playback worker is also proven absent. Cold startup `restore()` allows local-only playback cache cleanup even if wireless export has never been used. For malformed/unreadable `/proc` or lifecycle state, keep the cache and original audio.

## Native build

Run `python tools/phone_link_profile.py` using a private external firmware configuration. This requires the exact pinned AP SHA-256 and emits only guard hashes/ABI metadata in `adapters/phone-link-guards.json` and `.h`. No firmware code is distributed. Compile `native/phone-link.c`, `native/export-relay.c`, `native/export-relay-fs.c`, and `native/export-relay-json.c`, entry `watch6_recorder_phone_link_initialize`, module `w6rxlink`. Do not define the original VoiceSpace meeting/live relay macros.

## Fixed IPC

All files are below `/data/watch6recorder/`. Existing connection IPC uses mirrored 64-byte `VSL1` headers and a fresh 16-hex nonce, copied after successful module load; heartbeat is published last. Connection controls are `w6r-link-{start,stop,heartbeat,consumed}.txt` (128 bytes), `w6r-link-status.txt` (256), `w6r-link-tx.msg` and four `w6r-link-rx-N.msg` (4224).

`w6r-export-job.txt` is exactly 512 bytes, spaces except these zero-based fields:

| Offset | Bytes | Value |
| --- | --- | --- |
| 0 | 6 | `W6RE1\n` |
| 6 | 16 | connection nonce |
| 22 | 1 | newline |
| 24 | 16 | recording ID |
| 40 | 8 | sample rate, lowercase hex |
| 48 | 8 | PCM byte total, lowercase hex |
| 56 | 16 | archive hash |
| 72 | 8 | whole PCM CRC32 |
| 80 | 16 | cache ID; native constructs the fixed WAV path |
| 96 | 8 | job sequence (`00000001` for one owner) |
| 104 | 8 | complete flag `00000001` |
| 464 | 8 | repeated job sequence |
| 472 | 8 | CRC32 of bytes 0..471 |
| 480 | 16 | repeated connection nonce |
| 496 | 11 | `\nend=W6RE1\n` |

`w6r-export-cancel.txt` is 128 bytes, two identical VSL1 control headers with this nonce, job sequence, payload length 0. `w6r-export-status.txt` is 512 bytes: VSL1 header (64), JSON payload at offset64 with length from header (capacity384, remaining spaces), repeated header at448. SDK completion and `source_closed` alone are never unload proof. The Lua wrapper also requires terminal status, `worker_done`, double ENOENT PID observations and successful native-guarded unload.
