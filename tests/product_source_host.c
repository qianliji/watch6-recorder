/* Test-only exports around the unchanged production source owner. The Python
 * harness simulates OS, Capture/RPMSG and firmware notifications at fixed APIs. */
#include "../native/p65-owner.c"
uint32_t host_event_address(void){return (uint32_t)(uintptr_t)&ctx.media.events;}
uint32_t host_worker(void){return (uint32_t)(uintptr_t)worker;}
int32_t host_initialize(void){static struct unload_pair pair;return vs_p65_owner_initialize(&pair);}
int32_t host_unload(void){return unload(0);}
