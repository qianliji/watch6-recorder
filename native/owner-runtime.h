#ifndef VS_CONTINUOUS_OWNER_RUNTIME_H
#define VS_CONTINUOUS_OWNER_RUNTIME_H
#include "spool.h"
/* Fixed internal platform operations, never supplied through files or Lua.
 * The worker must be independently spawned and its module pinned through PID
 * exit. destroy_view only detaches presentation; it is not a capture Stop. */
struct vs_owner_runtime {
 void *cookie;
 uint32_t (*now)(void *);
 int (*stop_requested)(void *,const char nonce[17]); /* 0 or positive VS_REASON_* */
 int (*consume_durable_receipts)(void *,struct vs_owner *);
 int (*publish)(void *,const struct vs_owner *);
 void (*wait)(void *,uint32_t milliseconds);
 int (*max_duration_reached)(void *,uint32_t started,uint32_t now);
 int (*publish_stream)(void *,const struct vs_owner *); /* optional append-only prefix, never durable reclaim */
};
int vs_owner_run(struct vs_owner *,const struct vs_ops *,const struct vs_owner_runtime *,const char *,uint32_t rate,uint32_t slots);
#endif
