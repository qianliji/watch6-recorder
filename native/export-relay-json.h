#ifndef W6R_EXPORT_RELAY_JSON_H
#define W6R_EXPORT_RELAY_JSON_H
#include <stdint.h>
#define RJ_TOKENS 320
enum {RJ_OBJECT=1,RJ_ARRAY,RJ_STRING,RJ_NUMBER,RJ_TRUE,RJ_FALSE,RJ_NULL};
struct rj_token {uint16_t start,end,parent;uint8_t type,pad;};
struct rj_doc {const char *text;uint32_t bytes,count;struct rj_token tokens[RJ_TOKENS];};
int rj_parse(struct rj_doc *,const char *,uint32_t);
int rj_field(const struct rj_doc *,int object,const char *key);
int rj_uint(const struct rj_doc *,int token,uint32_t *);
int rj_bool(const struct rj_doc *,int token,int *);
int rj_string(const struct rj_doc *,int token,char *,uint32_t);
int rj_equal(const struct rj_doc *,int token,const char *);
int rj_raw_string(const struct rj_doc *,int token,char *,uint32_t);
#endif
