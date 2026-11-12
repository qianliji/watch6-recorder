#ifndef VS_CONTINUOUS_STATUS_H
#define VS_CONTINUOUS_STATUS_H
#include <stdint.h>
int vs_write_source_status(const char nonce[17],uint32_t sequence,const char *json,uint32_t bytes);
#endif
