#ifndef VS_P65_CONTINUOUS_MEDIA_H
#define VS_P65_CONTINUOUS_MEDIA_H
#include <stdint.h>
/* Own listener/data FD, raw nonblocking socket calls; no opaque field writes. */
struct vs_p65_media {
 void *handle;int32_t listener,data;
 volatile uint32_t events;volatile int32_t event_error;
 uint32_t rate,start_calls,header_bytes,header_done,pcm_at,pcm_end,close_uncertain;
 uint8_t header[4096];
 char socket_name[16];
};
int vs_p65_media_prepare(struct vs_p65_media *,const char nonce[17],uint32_t rate);
int vs_p65_media_ready(struct vs_p65_media *);
int vs_p65_media_start(struct vs_p65_media *);
int vs_p65_media_pause(struct vs_p65_media *);
int vs_p65_media_paused(struct vs_p65_media *);
int vs_p65_media_resume(struct vs_p65_media *);
int vs_p65_media_resumed(struct vs_p65_media *);
int vs_p65_media_read(struct vs_p65_media *,uint8_t *,uint32_t);
int vs_p65_media_stop(struct vs_p65_media *);
int vs_p65_media_stopped(struct vs_p65_media *);
int vs_p65_media_close(struct vs_p65_media *);
#endif
