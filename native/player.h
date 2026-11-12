#ifndef WATCH6_RECORDER_PLAYER_H
#define WATCH6_RECORDER_PLAYER_H
#include <stdint.h>
/* Frame layout is shared by src/archive.lua. No arbitrary path/function pointer
 * is accepted: every source and cache filename is constructed from 16 hex IDs. */
#define W6R_PLAYER_FRAME_BYTES 512u
#define W6R_PLAYER_STATUS_BYTES 1536u
#define W6R_PLAYER_MAX_PCM 134348800u
struct w6r_player_unload { int32_t (*callback)(void *); void *context; };
int32_t watch6_player_initialize(struct w6r_player_unload *);
#endif
