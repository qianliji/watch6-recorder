#ifndef VS_P65_CONTINUOUS_FS_H
#define VS_P65_CONTINUOUS_FS_H
#include "spool.h"
#define VS_RECORD_BYTES 512u
struct vs_p65_fs {
 char nonce[17],storage_id[37],epoch[37];
 uint32_t rate,receipt_sequence,ledger_generation,active_seq,active_bytes;
 uint64_t active_offset,sealed_offset,phone_durable,last_receipt_frontier,available;
 int32_t fd;
 uint32_t uncertain,space_known,allocation_bytes;
 char path[160],other[160];uint8_t record[VS_RECORD_BYTES],verify[VS_RECORD_BYTES];
};
/* Pure bounded parser, separately exercised by host fixtures. */
int vs_parse_data_blocks(const char *text,uint32_t bytes,uint64_t *available,uint32_t *blocksize);
int vs_p65_fs_init(struct vs_p65_fs *,const char nonce[17],uint32_t rate);
int vs_p65_fs_space(struct vs_p65_fs *,uint32_t bytes,uint32_t reserve);
int vs_p65_fs_open(struct vs_p65_fs *,uint32_t seq,uint64_t offset);
int vs_p65_fs_append(struct vs_p65_fs *,const uint8_t *,uint32_t);
int vs_p65_fs_pause_sync(struct vs_p65_fs *);
int vs_p65_fs_seal(struct vs_p65_fs *,const struct vs_extent *);
/* bind is called only by the independent owner after validating a matching
 * current phone SYNC/meeting receipt; it persists storage identity. */
int vs_p65_fs_bind_phone(struct vs_p65_fs *,const char storage_id[37],const char epoch[37]);
int vs_p65_fs_reclaim(struct vs_p65_fs *,const struct vs_extent *,const char receipt[VS_RECORD_BYTES]);
int vs_p65_fs_finish(struct vs_p65_fs *,uint64_t bytes,int complete,int reason);
#endif
