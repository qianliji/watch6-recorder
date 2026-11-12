#ifndef W6R_EXPORT_RELAY_FS_H
#define W6R_EXPORT_RELAY_FS_H
#include "export-relay.h"
struct w6e_fs {int32_t fd;uint32_t position,generation,uncertain;char cache[17],nonce[17];uint8_t scratch[2048];char frame[512],control[128];};
void w6e_fs_init(struct w6e_fs *,const char nonce[17]);
void w6e_fs_ops(struct w6e_fs *,struct w6e_io *);
int w6e_fs_close(void *);
#endif
