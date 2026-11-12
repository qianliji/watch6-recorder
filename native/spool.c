#include "spool.h"
#define NONE UINT32_MAX
static void zero(void *dst,uint32_t bytes){uint8_t *p=dst;while(bytes--)*p++=0;}
static int same_nonce(const char *a,const char *b){uint32_t n;for(n=0;n<17;n++)if(a[n]!=b[n])return 0;return 1;}
static int nonce_valid(const char *s){uint32_t n;for(n=0;n<16;n++)if(!((s[n]>='0'&&s[n]<='9')||(s[n]>='a'&&s[n]<='f')))return 0;return s[16]==0;}
static uint32_t crc_bytes(uint32_t crc,const uint8_t *p,uint32_t n){uint32_t k;while(n--){crc^=*p++;for(k=0;k<8;k++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return crc;}
static void failure(struct vs_owner *o,uint32_t error){o->error=error;o->interrupted=1;}
static uint32_t elapsed(uint32_t now,uint32_t then){return now-then;}
static int seal(struct vs_owner *o){
 struct vs_extent *e;if(!o->have_active)return 0;e=&o->extents[o->active];
 if(e->bytes==0){
  /* seal owns the open extent handle even for an immediate zero-PCM stop.
   * Its empty case closes/removes only this newly-created empty shell and
   * must not publish a durable audio extent. Never drop ownership on error. */
  e->crc=0;
  if(o->ops.seal(o->ops.cookie,e)!=0){failure(o,12);return -1;}
  zero(e,(uint32_t)sizeof(*e));o->count--;o->have_active=0;o->active=NONE;return 0;
 }
 e->crc^=0xffffffffu;
 if(o->ops.seal(o->ops.cookie,e)!=0){e->crc^=0xffffffffu;failure(o,12);return -1;}
 e->state=VS_SEALED;o->durable=e->offset+e->bytes;o->have_active=0;o->active=NONE;return 0;
}
static int open_extent(struct vs_owner *o){
 uint32_t slot;struct vs_extent *e;
 if(o->count>=o->slots){failure(o,13);return -1;}
 slot=(o->head+o->count)%o->slots;e=&o->extents[slot];
 if(e->state!=VS_FREE){failure(o,14);return -1;}
 if(o->ops.open_extent(o->ops.cookie,o->next_seq,o->produced)!=0){failure(o,15);return -1;}
 e->offset=o->produced;e->seq=o->next_seq++;e->bytes=0;e->crc=0xffffffffu;e->state=VS_WRITING;
 o->active=slot;o->have_active=1;o->count++;return 0;
}
int vs_owner_init(struct vs_owner *o,const struct vs_ops *ops,const char *nonce,uint32_t rate,uint32_t normal_slots,uint32_t now){
 uint32_t i;zero(o,(uint32_t)sizeof(*o));o->active=NONE;
 if(!ops||ops->capabilities!=VS_CAP_ALL||!nonce||!nonce_valid(nonce)||(rate!=8000&&rate!=16000)||normal_slots<2||normal_slots>VS_MAX_EXTENTS){o->phase=VS_FAILED;o->error=1;return -1;}
 if(!ops->prepare||!ops->ready||!ops->start||!ops->read_pcm||!ops->stop_remote||!ops->stopped||!ops->close||!ops->check_space||!ops->open_extent||!ops->append||!ops->seal||!ops->reclaim||!ops->close_meeting){o->phase=VS_FAILED;o->error=2;return -1;}
 o->ops=*ops;for(i=0;i<17;i++)o->nonce[i]=nonce[i];o->rate=rate;o->normal_limit=normal_slots;o->slots=normal_slots+VS_TAIL_EXTENTS;o->next_seq=1;o->prepared_at=now;o->last_now=now;
 if(ops->check_space(ops->cookie,VS_EXTENT_BYTES,VS_TAIL_EXTENTS*VS_EXTENT_BYTES)!=1){o->phase=VS_FAILED;o->error=3;return -1;}
 /* prepare may partially acquire resources even on an error. Keep ownership. */
 o->media_opened=1;o->phase=VS_PREPARING;
 if(ops->prepare(ops->cookie,o->nonce)!=0){failure(o,4);o->phase=VS_STOPPING;o->reason=VS_REASON_CAPTURE;o->stop_at=now;return -1;}
 return 0;
}
static int request_stop(struct vs_owner *o,uint32_t reason,uint32_t now){
 if(o->phase==VS_CLOSED||o->phase==VS_FAILED||o->phase==VS_RETAINED)return 0;
 if(o->phase==VS_STOPPING||o->phase==VS_DRAINING)return 0;
 o->reason=reason;o->stop_at=now;o->phase=VS_STOPPING;return 0;
}
int vs_owner_stop(struct vs_owner *o,uint32_t reason,uint32_t now){return request_stop(o,reason,now);}
int vs_owner_pause(struct vs_owner *o,const struct vs_pause_ops *ops,uint32_t now){
 if(o->phase==VS_PAUSING||o->phase==VS_PAUSED)return 0;
 if(o->phase!=VS_RECORDING||!ops||!ops->pause||!ops->paused||!ops->resume||!ops->resumed||!ops->sync)return -1;
 o->pause_ops=*ops;o->pause_at=now;
 if(ops->pause(o->ops.cookie)!=0){failure(o,31);request_stop(o,VS_REASON_CAPTURE,now);return -1;}
 o->phase=VS_PAUSING;return 0;
}
int vs_owner_resume(struct vs_owner *o,uint32_t now){
 if(o->phase==VS_RESUMING||o->phase==VS_RECORDING)return 0;
 if(o->phase!=VS_PAUSED||!o->pause_ops.resume)return -1;
 o->pause_at=now;
 if(o->pause_ops.resume(o->ops.cookie)!=0){failure(o,32);request_stop(o,VS_REASON_CAPTURE,now);return -1;}
 o->phase=VS_RESUMING;return 0;
}
int vs_owner_ack(struct vs_owner *o,const char nonce[17],uint32_t seq,uint64_t end,uint32_t crc,const char *receipt){
 struct vs_extent *e;
 if(!nonce||!same_nonce(o->nonce,nonce)||!receipt||!receipt[0]||!o->count)return -1;
 e=&o->extents[o->head];
 /* Strict contiguous durability: an out-of-order/old/wrong-hash receipt can
  * never erase an active range, another session, or a later source extent. */
 if(e->state!=VS_SEALED||e->seq!=seq||e->offset!=o->phone_durable||e->offset+e->bytes!=end||e->crc!=crc)return -1;
 if(o->ops.reclaim(o->ops.cookie,e,receipt)!=0)return -1;
 o->phone_durable=end;zero(e,(uint32_t)sizeof(*e));o->head=(o->head+1)%o->slots;o->count--;return 0;
}
int vs_owner_step(struct vs_owner *o,uint32_t now){
 int ret,drained=0;uint32_t turn;
 if(o->phase==VS_CLOSED||o->phase==VS_FAILED||o->phase==VS_RETAINED)return 0;
 o->last_now=now;
 if(o->phase==VS_PREPARING){
  ret=o->ops.ready(o->ops.cookie);
  if(ret<0||elapsed(now,o->prepared_at)>8000u){failure(o,5);request_stop(o,VS_REASON_TIMEOUT,now);}
  else if(ret==1){
   if(open_extent(o)!=0){request_stop(o,VS_REASON_STORAGE,now);}
   else {o->start_calls++;ret=o->ops.start(o->ops.cookie);if(ret!=0){failure(o,6);request_stop(o,VS_REASON_CAPTURE,now);}else o->phase=VS_RECORDING;}
  }
 }
 if(o->phase==VS_STOPPING){
  if(o->start_calls){o->stop_calls++;ret=o->ops.stop_remote(o->ops.cookie);if(ret!=0)failure(o,7);}
  else {o->eof=1;o->stop_seen=1;}
  o->phase=VS_DRAINING;
 }
 if(o->phase==VS_RESUMING){
  ret=o->pause_ops.resumed(o->ops.cookie);
  if(ret<0||elapsed(now,o->pause_at)>8000u){failure(o,33);request_stop(o,VS_REASON_TIMEOUT,now);return -1;}
  if(ret==1)o->phase=VS_RECORDING;
 }
 if(o->phase==VS_PAUSED)return 0;
 if(o->phase!=VS_RECORDING&&o->phase!=VS_DRAINING&&o->phase!=VS_PAUSING&&o->phase!=VS_RESUMING)return 0;
 /* Bound one scheduler turn, not total capture: the owner schedules the next
  * turn promptly while readable. BLE/cloud are never on this data path. */
 for(turn=0;turn<8&&!o->eof;turn++){
  uint32_t room=VS_EXTENT_BYTES,amount;
  if(o->have_active)room-=o->extents[o->active].bytes;
  if(!room){if(seal(o)!=0){if(o->phase!=VS_DRAINING)request_stop(o,VS_REASON_STORAGE,now);else o->phase=VS_RETAINED;return -1;}room=VS_EXTENT_BYTES;}
  if(o->phase!=VS_DRAINING&&!o->have_active&&o->count>=o->normal_limit){request_stop(o,VS_REASON_BUDGET,now);return 1;}
  if(!o->have_active&&open_extent(o)!=0){o->phase=VS_RETAINED;return -1;}
  amount=room<VS_READ_BYTES?room:VS_READ_BYTES;
  if(o->ops.check_space(o->ops.cookie,amount,o->phase!=VS_DRAINING?VS_TAIL_EXTENTS*VS_EXTENT_BYTES:0)!=1){
   if(o->phase!=VS_DRAINING){request_stop(o,VS_REASON_SPACE,now);return 1;}
   failure(o,8);o->phase=VS_RETAINED;return -1;
  }
  ret=o->ops.read_pcm(o->ops.cookie,o->pcm,amount);
  if(ret==VS_RX_AGAIN){drained=1;break;}
  if(ret==VS_RX_EOF){o->eof=1;if(o->phase!=VS_DRAINING){failure(o,9);request_stop(o,VS_REASON_CAPTURE,now);return 1;}break;}
  if(ret<=0||(uint32_t)ret>amount||(ret&1)){failure(o,10);if(o->phase!=VS_DRAINING)request_stop(o,VS_REASON_CAPTURE,now);else o->phase=VS_RETAINED;return -1;}
  if(o->ops.append(o->ops.cookie,o->pcm,(uint32_t)ret)!=0){failure(o,11);if(o->phase!=VS_DRAINING)request_stop(o,VS_REASON_STORAGE,now);else o->phase=VS_RETAINED;return -1;}
  o->extents[o->active].crc=crc_bytes(o->extents[o->active].crc,o->pcm,(uint32_t)ret);o->extents[o->active].bytes+=(uint32_t)ret;o->produced+=(uint32_t)ret;
 }
 if(o->phase==VS_PAUSING){
  ret=o->pause_ops.paused(o->ops.cookie);
  if(ret<0||elapsed(now,o->pause_at)>8000u){failure(o,34);request_stop(o,VS_REASON_TIMEOUT,now);return -1;}
  if(ret==1&&drained){
   /* Keep the active extent and absolute offsets. A pause never creates a
    * short middle extent, restarts Capture, or inserts synthetic silence. */
   if(o->pause_ops.sync(o->ops.cookie)!=0){failure(o,35);request_stop(o,VS_REASON_STORAGE,now);return -1;}
   o->phase=VS_PAUSED;
  }
 }
 if(o->phase==VS_DRAINING){
  ret=o->ops.stopped(o->ops.cookie);if(ret<0)failure(o,16);if(ret==1)o->stop_seen=1;
  if(o->eof&&o->stop_seen){
   if(seal(o)!=0){o->phase=VS_RETAINED;return -1;}
   if(now<o->close_next)return 0;
   o->close_attempts++;ret=o->ops.close(o->ops.cookie);
   if(ret!=0){o->close_next=now+1000u;if(o->close_attempts>=3)o->phase=VS_RETAINED;return -1;}
   o->media_opened=0;
   /* seal/sync/readback can take time while notifications are still live.
    * close has now joined that thread: recheck its final error/STOPPED state
    * before promoting tail or whole-meeting completeness. */
   if(o->start_calls&&o->ops.stopped(o->ops.cookie)!=1)failure(o,19);
   o->complete=o->produced>0&&!o->interrupted&&o->reason==VS_REASON_USER;
   if(o->ops.close_meeting(o->ops.cookie,o->produced,(int)o->complete,(int)o->reason)!=0){failure(o,17);o->phase=VS_RETAINED;return -1;}
   o->phase=VS_CLOSED;return 0;
  }
  /* Timeout reports an unknown terminal state; it never frees a live handle
   * or promotes received data to a complete recording. The module stays. */
  if(elapsed(now,o->stop_at)>15000u){failure(o,18);o->phase=VS_RETAINED;return -1;}
 }
 return 0;
}
uint32_t vs_owner_unloadable(const struct vs_owner *o){return !o->media_opened&&(o->phase==VS_CLOSED||o->phase==VS_FAILED);}
