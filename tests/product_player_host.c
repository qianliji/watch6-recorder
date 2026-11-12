/* Test-only exports; all request/archive/playback/status logic is production C.
 * The Python harness replaces the firmware fingerprint outcome explicitly. */
#include "../native/player.c"
uint32_t host_event_address(void){return (uint32_t)(uintptr_t)&ctx.events;}
uint32_t host_worker(void){return (uint32_t)(uintptr_t)worker;}
uint32_t host_duration(void){return ctx.duration;}
int32_t host_initialize(void){static struct w6r_player_unload pair;return watch6_player_initialize(&pair);}
int32_t host_unload(void){return unload(0);}
