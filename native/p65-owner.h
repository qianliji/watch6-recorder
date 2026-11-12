#ifndef VS_CONTINUOUS_P65_OWNER_H
#define VS_CONTINUOUS_P65_OWNER_H
#include <stdint.h>
struct unload_pair { int32_t (*callback)(void *);void *context; };
/* Fixed request -> spawn an independent gated owner. No arbitrary entry,
 * pathname, command, package, source or peer can be selected by the request. */
int32_t vs_p65_owner_initialize(struct unload_pair *pair);
#endif
