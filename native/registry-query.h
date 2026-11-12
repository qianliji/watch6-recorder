/* Read-only, one-shot P65 module-name snapshot. No task or retained callback. */
#ifndef W6R_REGISTRY_QUERY_H
#define W6R_REGISTRY_QUERY_H
#include <stdint.h>
#define W6RQ_REQUEST_SIZE 128u
#define W6RQ_STATUS_SIZE 256u
#define W6RQ_MAX_MODULES 128u
#define W6RQ_REQUEST_PATH "/data/watch6recorder/w6r-registry-request.txt"
#define W6RQ_STATUS_PATH "/data/watch6recorder/w6r-registry-status.txt"
enum {W6RQ_OK=0,W6RQ_INVALID=-1,W6RQ_FIRMWARE=-2,W6RQ_REQUEST=-3,
 W6RQ_LOCK=-4,W6RQ_REGISTRY=-5,W6RQ_DUPLICATE=-6,W6RQ_IO=-7,W6RQ_SHORT=-8};
struct w6rq_unload_pair {int32_t (*callback)(void *);void *context;};
int32_t watch6_registry_query_initialize(struct w6rq_unload_pair *pair);
#endif
