# Transport extraction provenance

## Current 0.4.0 MiFitness transport

The current build embeds the guarded `phone-link.c` MiFitness owner and shared
archive relay described below. The watchface owns capture and complete local
playback. A matching signed application-identity RPK enables the SDK route;
the identity RPK does not call recording or load native code. The phone uses
an externally supplied vendor SDK and explicit authorization.

The 0.3.x independent BLE experiment is no longer embedded or included in the
active source release. If its old callback owner remains resident on a watch,
the new route must not force-unload it or discard a cache it could own. It
requires the user to end recording and perform a complete watch reboot.

The following source extraction record began with 0.2 and remains applicable
to the restored 0.4 route. It documents origin; it does not establish hardware
acceptance for a later build.

## MiFitness source extraction

The transport adapter was extracted on 2026-11-07 from the user's pre-existing VoiceSpace source tree, `phone-voice/watch-native`. The original project is not modified. These hashes identify the source that was reviewed; no private firmware, certificates, account identifiers, cloud key or SDK binary is copied into this independent recorder project.

| Source relative to the original watch-native directory | SHA-256 at extraction |
| --- | --- |
| `phone-link.c` | `21589d3e2baa36e1f1fd030a8354227108bacf39dc6e4dcabe79d7dee5ede36c` |
| `inline-link.lua` | `9154222c00b689a5af81f4ddac8a89fd1422e0c70e38a7d92041e818422ba4e0` |
| `phone-link-profile.py` | `b93c119a9f80a704af83de604e49a828c4a0ee2167bb6985a4dd8a27df6adf0c` |
| `continuous-native/relay-json.c` | `a5d8cfa2e9e72ecc4c8aa539af88aae8a194f8bf31d0193908e6c697384a92e3` |
| `continuous-native/relay-json.h` | `355e26e80b6f7168e491c9b42695a6db1e56bdf00a4248168705e9b8a39e14d5` |

`native/phone-link.c` retains the native worker/task ownership, exact-firmware guards, MiWear connection and UV close callback protection, mirrored fixed-file IPC, immutable per-request payload ownership, fresh nonce initialization gate and independent PID-checked unload. The original live-ASR and meeting relay compile branches were removed, not carried into the independent recorder.

`src/phone-link.lua` is a smaller factory based on the established fixed-file framing and lifecycle rules from `inline-link.lua`; it adds read-only adoption and explicit complete-archive export. It contains no cloud, transcription, meeting recording, desktop input, or microphone API. The source spool and native player are separate modules.

`native/export-relay.c` and `native/export-relay-fs.c` implement the new `w6r1` protocol, durable ACK frontier, a single immutable inflight payload, source close proof, a CRC-checked fixed job descriptor, bounded WAV reads, cancellation, reconnect/reoffer, and terminal worker status. Their JSON tokenizer comes from the listed `relay-json` source, with its bounded parser, duplicate-key checks and strict primitive helpers retained. See `WIRELESS_EXPORT_PROTOCOL.md` and `PHONE_LINK_API.md`.

The new isolation namespace is `/data/watch6recorder/`, module `w6rxlink`, task `w6rx_owner`, app identity `com.watch6.recorder`, and entry `watch6_recorder_phone_link_initialize`. Original VoiceSpace paths, module names and account identity are not used.

`tools/phone_link_profile.py` is adapted from the listed profile generator. It accepts only an externally provided pinned P65 3.100.043 AP image, SHA-256 `a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858`, and emits hashes and ABI metadata for 40 verified code windows. It does not embed the firmware instructions. All hard-coded function and private-structure uses in the adapter remain conditional on every runtime guard passing. Mismatched firmware fails closed.

The phone side uses the official MiFitness identity route and requires the appropriate user authorization. The native watch adapter is firmware-specific and is not represented as an officially supported third-party watchface API. Official communication documentation: https://iot.mi.com/vela/quickapp/zh/features/network/interconnect.html . The SDK and vendor component licensing remains separate from the project’s own source license; copying/adapting source does not establish ownership or grant vendor rights. See `NOTICE`, `docs/IP_REVIEW.md`, and `docs/LICENSE_OPTIONS_20261107.md` for the release review scope.

Host verification compiles the actual native sources for ARM and intercepts every fixed-address OS/SDK call in Unicorn. The tests exercise durable ACK rules, timeout/reoffer, bounded resume, corrupt WAV, explicit cancellation, GUI sleep, immutable pending buffers, close uncertainty, double-close protection, and PID unload guards. Lua tests exercise fresh installation, local-only cleanup safety, read-only export adoption, and the complete source release lifecycle. No host test executes a vendor firmware instruction or proves physical MiFitness delivery, speaker behavior or a legal authorization.
