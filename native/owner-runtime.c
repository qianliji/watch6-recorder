#include "owner-runtime.h"
int vs_owner_run(struct vs_owner *owner,const struct vs_ops *ops,const struct vs_owner_runtime *runtime,const char *nonce,uint32_t rate,uint32_t slots){
 uint32_t started,now,prior_phase,prior_count,last_stream=0;uint64_t prior_durable,last_produced=0;int requested;
 if(!runtime||!runtime->now||!runtime->stop_requested||!runtime->consume_durable_receipts||!runtime->publish||!runtime->wait||!runtime->max_duration_reached)return -1;
 started=runtime->now(runtime->cookie);
 if(vs_owner_init(owner,ops,nonce,rate,slots,started)<0&&owner->phase==VS_FAILED){runtime->publish(runtime->cookie,owner);return -2;}
 runtime->publish(runtime->cookie,owner);
 /* Local archive owns durable sealed files; no phone receipt is required. */
 while(owner->phase!=VS_FAILED&&owner->phase!=VS_CLOSED){
  now=runtime->now(runtime->cookie);prior_phase=owner->phase;prior_count=owner->count;prior_durable=owner->durable;
  if(owner->phase==VS_RETAINED){
   /* Ambiguous close retains the SAME group, FDs, callback context and code.
    * No busy spin, forced unload, automatic new take, or fake completion. */
   runtime->publish(runtime->cookie,owner);runtime->wait(runtime->cookie,60000);continue;
  }
  if(runtime->consume_durable_receipts(runtime->cookie,owner)<0){owner->error=30;owner->interrupted=1;vs_owner_stop(owner,VS_REASON_STORAGE,now);}
  if(owner->phase==VS_CLOSED){
   if(owner->count!=prior_count)runtime->publish(runtime->cookie,owner);
   /* Capture/notify FDs are already closed; retain only this bounded spool
    * owner until the phone durably confirms all sealed source extents. */
   if(owner->count)runtime->wait(runtime->cookie,1000);continue;
  }
  requested=runtime->stop_requested(runtime->cookie,owner->nonce);
  if(requested>0)vs_owner_stop(owner,requested<=VS_REASON_TIMEOUT?(uint32_t)requested:VS_REASON_CAPTURE,now);
  if(runtime->max_duration_reached(runtime->cookie,started,now)>0)vs_owner_stop(owner,VS_REASON_TIMEOUT,now);
  vs_owner_step(owner,now);
  /* No PCM/status polling by the view is needed to keep capture alive. Idle
   * storage ledgers change only at seal/reclaim/phase boundaries. */
  if(owner->phase!=prior_phase||owner->count!=prior_count||owner->durable!=prior_durable)runtime->publish(runtime->cookie,owner);
  if(runtime->publish_stream&&owner->produced!=last_produced&&(uint32_t)(now-last_stream)>=100){runtime->publish_stream(runtime->cookie,owner);last_stream=now;last_produced=owner->produced;}
  if(owner->phase==VS_RECORDING||owner->phase==VS_DRAINING||owner->phase==VS_PAUSING||owner->phase==VS_RESUMING)runtime->wait(runtime->cookie,25);
  else if(owner->phase==VS_PREPARING)runtime->wait(runtime->cookie,25);
  else if(owner->phase==VS_PAUSED)runtime->wait(runtime->cookie,250);
 }
 runtime->publish(runtime->cookie,owner);return vs_owner_unloadable(owner)?0:-3;
}
