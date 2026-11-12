/* Continuous capture owner core. No OS, Lua, microphone or network imports.
 * The platform adapter must be a fixed, firmware-guarded implementation.
 * All calls except on_event are made by ONE native owner task. */
#ifndef VS_CONTINUOUS_SPOOL_H
#define VS_CONTINUOUS_SPOOL_H
#include <stdint.h>
#include <stddef.h>
#define VS_EXTENT_BYTES 65536u
#define VS_MAX_EXTENTS 2048u
#define VS_TAIL_EXTENTS 2u
#define VS_READ_BYTES 4096u
#define VS_CAP_ALL 0x7fu
enum vs_capability { VS_CAP_CPU=1u,VS_CAP_RPC=2u,VS_CAP_SOCKET=4u,
 VS_CAP_EVENT_JOIN=8u,VS_CAP_STORAGE_SYNC=16u,VS_CAP_SPACE=32u,VS_CAP_DRAIN=64u };
enum vs_phase { VS_IDLE,VS_PREPARING,VS_RECORDING,VS_STOPPING,VS_DRAINING,
 VS_CLOSED,VS_RETAINED,VS_FAILED,VS_PAUSING,VS_PAUSED,VS_RESUMING };
enum vs_read_result { VS_RX_AGAIN=-2,VS_RX_EOF=-3 };
enum vs_extent_state { VS_FREE,VS_WRITING,VS_SEALED };
enum vs_reason { VS_REASON_USER=1,VS_REASON_BUDGET=2,VS_REASON_SPACE=3,
 VS_REASON_CAPTURE=4,VS_REASON_STORAGE=5,VS_REASON_TIMEOUT=6 };
struct vs_extent { uint64_t offset;uint32_t seq,bytes,crc,state; };
struct vs_ops {
 uint32_t capabilities;
 void *cookie;
 /* prepare creates an independently owned listener, queues fixed Capture
  * prepare and returns promptly. ready polls PREPARED + accepted data FD.
  * It must not use the firmware's blocking BUFFER prepare wrapper. */
 int (*prepare)(void *,const char nonce[17]);
 int (*ready)(void *); /* 0 pending, 1 prepared, <0 failure */
 int (*start)(void *); /* one call only, fixed Capture source */
 /* Read already validated PCM16 mono at the negotiated 8/16 kHz.
  * Adapter incrementally parses/retains the actual stream header. Never
  * pass WAV container bytes, EAGAIN, or a partial sample as PCM. */
 int (*read_pcm)(void *,uint8_t *,uint32_t);
 int (*stop_remote)(void *); /* must NOT close the data FD */
 int (*stopped)(void *); /* 1 only after matching successful STOPPED */
 int (*close)(void *); /* join callback thread before returning success */
 /* check_space accounts for all own extents + metadata + tail reserve;
  * no assumption about the watch's advertised storage capacity is valid. */
 int (*check_space)(void *,uint32_t bytes,uint32_t reserve_bytes);
 int (*open_extent)(void *,uint32_t seq,uint64_t offset);
 int (*append)(void *,const uint8_t *,uint32_t);
 /* seal must sync source bytes, close, publish the exact immutable ledger
  * and sync/read back the ledger before returning success. */
 int (*seal)(void *,const struct vs_extent *);
 /* reclaim may unlink ONLY the closed exact extent whose phone durability
  * receipt has been checked. Persist the receipt before removing bytes. */
 int (*reclaim)(void *,const struct vs_extent *,const char *receipt);
 /* close_meeting is durable metadata only: never reruns recognition/input. */
 int (*close_meeting)(void *,uint64_t bytes,int complete,int reason);
};
struct vs_pause_ops {
 int (*pause)(void *);int (*paused)(void *);
 int (*resume)(void *);int (*resumed)(void *);int (*sync)(void *);
};
struct vs_owner {
 struct vs_ops ops;
 struct vs_pause_ops pause_ops;
 struct vs_extent extents[VS_MAX_EXTENTS+VS_TAIL_EXTENTS];
 uint8_t pcm[VS_READ_BYTES];
 char nonce[17];
 uint64_t produced,durable,phone_durable;
 uint32_t normal_limit,slots,head,count,active,next_seq,rate;
 uint32_t phase,reason,error,start_calls,stop_calls,close_attempts;
 uint32_t prepared_at,stop_at,close_next,last_now;
 uint32_t eof,stop_seen,interrupted,have_active,media_opened,complete;
 uint32_t pause_at;
};
int vs_owner_init(struct vs_owner *,const struct vs_ops *,const char *,uint32_t rate,uint32_t normal_slots,uint32_t now);
int vs_owner_step(struct vs_owner *,uint32_t now);
int vs_owner_pause(struct vs_owner *,const struct vs_pause_ops *,uint32_t now);
int vs_owner_resume(struct vs_owner *,uint32_t now);
#if defined(__arm__)
__attribute__((long_call))
#endif
int vs_owner_stop(struct vs_owner *,uint32_t reason,uint32_t now);
int vs_owner_ack(struct vs_owner *,const char nonce[17],uint32_t seq,uint64_t end,uint32_t crc,const char *durable_receipt);
uint32_t vs_owner_unloadable(const struct vs_owner *);
#endif
