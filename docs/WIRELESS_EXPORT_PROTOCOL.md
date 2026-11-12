# w6r1 wireless recording export

Version 1 transfers a complete, immutable recording. Current 0.4.0 uses the MiFitness application channel for `com.watch6.recorder`, with a matching signed identity RPK and explicit phone SDK authorization. It never starts recording, deletes source audio, invokes a cloud service, or injects desktop text. Firmware-specific native transport is a guarded adapter, not a promise that every firmware supports this ABI.

All packets are UTF-8 JSON objects. Requests contain `v:1`, `protocol:"w6r1"`, a unique `id` of at most 80 ASCII characters, an `action`, and `recording_id` consisting of 16 lowercase hexadecimal characters. A recording is mono PCM16LE at 8000 or 16000 Hz. `total_bytes` counts PCM only, excludes the 44-byte WAV header, is even, and is at most 134348800 bytes.

| Action | Additional fields |
| --- | --- |
| `recorder_offer` | `sample_rate`, `total_bytes`, `archive_hash` (16 lowercase hex), `pcm_crc32` (8 lowercase hex), `complete:true` |
| `recorder_chunk` | `offset` (PCM byte frontier), `data` (canonical base64, at most 2048 decoded bytes), `crc32` (8 lowercase hex, CRC32/ISO-HDLC of this decoded chunk) |
| `recorder_finish` | `total_bytes`, `archive_hash`, `pcm_crc32` |
| `recorder_status` | A read-only status query; the native sender currently resumes through a new offer instead. |

`archive_hash` is the verified session metadata CRC32 followed by the verified CLOSED metadata CRC32, both eight lowercase hexadecimal digits. `pcm_crc32` is CRC32/ISO-HDLC of the entire PCM stream, initial accumulator `ffffffff`, reflected polynomial `edb88320`, final XOR `ffffffff`. These checks detect corruption; they are not authentication or cryptographic signatures.

Phone replies:

```json
{
  "protocol":"w6r1", "type":"recorder_ack",
  "request_id":"exact request id", "recording_id":"0123456789abcdef",
  "ok":true, "phase":"receiving", "next":2048,
  "durable":2048, "complete":false,
  "storage_id":"00112233-4455-4677-8899-aabbccddeeff"
}
```

`storage_id` is the phone's persistent canonical lowercase UUID. It is pinned after the first valid ACK of this job; a change fails closed and requires a fresh user export. ACKs match both request and recording identity. An SDK send callback releases its borrowed buffer and **does not** advance the durable frontier.

After offer, `phase` is `ready` or `receiving`, `complete:false`, and `next` equals numeric `durable` and is an even durable offset within the declared total. A duplicate/recovered complete archive may reply `phase:"saved"`, `complete:true`, `next:total_bytes`. After each chunk, the ACK must be `receiving`, `complete:false`, and `next` must exactly equal `offset + decoded chunk length`. Only one application request and one immutable SDK buffer are inflight.

After finish, the phone validates the declared length, final CRC, canonical WAV header, and persistent archive. Only then does it reply `phase:"saved"`, `complete:true`, `next:total_bytes`, `durable:total_bytes`. It can also return the final `sha256`. A negative ACK is an export failure and does not authorize deleting source data.

On timeout or disconnect, the sender offers the same immutable archive again and resumes from the phone's durable frontier. Identical bytes below that frontier must be idempotent; inconsistent bytes, mismatching archive metadata, invalid base64, gaps, or a changed storage identity are rejected. Interrupted transfers keep the original watch PCM and metadata.

The watch exports an already CRC-checked prepared WAV from `/data/watch6recorder/w6r-play-<cache_id16hex>.wav`; arbitrary paths are not accepted. Preparing that WAV validates every sealed source extent, fsyncs, and reads it back. The sender validates the canonical WAV header, reads in bounded batches, checks EOF at the declared end, and includes per-chunk and whole-PCM checksums. Resuming uses bounded forward reads rather than an unverified seek ABI.

Export is owned by a native worker independently of the face view. Completion/cancel must match the exact job and prove its source descriptor closed; SDK/UV callbacks and task/PID shutdown must finish before guarded module unloading and `safe_to_release`. A radio failure never authorizes force-unloading callbacks. Cold startup may prove module absence read-only. This permits releasing the temporary prepared WAV; **it never permits deleting the original recording**. Actual sleep/radio behavior remains a device acceptance item. A pre-upgrade independent BLE callback owner is not reused as a MiFitness owner; if still present it requires a safe complete watch reboot.
