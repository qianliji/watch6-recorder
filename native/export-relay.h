/* w6r1 bounded, receiver-durable export. No microphone or deletion API. */
#ifndef W6R_EXPORT_RELAY_H
#define W6R_EXPORT_RELAY_H
#include <stdint.h>
#define W6E_CHUNK 2048u
#define W6E_LIMIT 134348800u
enum {W6E_IDLE=0,W6E_OFFER,W6E_STREAM,W6E_FINISH,W6E_SAVED,W6E_CANCELLED,W6E_ERROR};
struct w6e_job {char nonce[17],recording_id[17],cache_id[17],archive_hash[17],pcm_crc32[9];uint32_t rate,total,sequence;};
struct w6e_status {uint32_t phase,next,total,sequence,pid,source_closed,worker_done;int32_t code;char recording_id[17];};
struct w6e_io {
 void *context;
 /* Return 1 valid new job, 0 absent/stale, -1 malformed. */
 int (*load)(void *,const char nonce[17],uint32_t after,struct w6e_job *);
 int (*cancel)(void *,const struct w6e_job *);
 /* Canonical WAV is opened only by this callback. 0 is bounded seek work;
  * >0 is exactly requested PCM, -1 is closed/error. */
 int (*read)(void *,const struct w6e_job *,uint32_t offset,uint8_t *,uint32_t);
 int (*send)(void *,const char *,uint32_t);
 int (*close)(void *);
 int (*publish)(void *,const struct w6e_status *);
};
struct w6e_relay {
 struct w6e_io io;struct w6e_job job;struct w6e_status status;
 char nonce[17],request[81],storage_id[37],wire[3584];uint8_t pcm[W6E_CHUNK];
 uint32_t phase,next,sequence,waiting,kind,sdk_pending,online,sent_at,serial,chunk_bytes;
 uint32_t worker_pid,dirty,last_publish;int32_t code;
};
uint32_t w6e_crc32(const void *,uint32_t);
int w6e_parse_job(const char *,uint32_t,const char nonce[17],struct w6e_job *);
void w6e_init(struct w6e_relay *,const struct w6e_io *,const char nonce[17],uint32_t pid);
void w6e_tick(struct w6e_relay *,uint32_t now);
void w6e_transport(struct w6e_relay *,int ready,int phone,uint32_t now);
int w6e_receive(struct w6e_relay *,const char *,uint32_t,uint32_t now);
void w6e_sent(struct w6e_relay *,int result,uint32_t now);
void w6e_cancel(struct w6e_relay *);
void w6e_worker_closed(struct w6e_relay *);
int w6e_holds_link(const struct w6e_relay *);
int w6e_terminal(const struct w6e_relay *);
const char *w6e_phase(uint32_t);
#endif
