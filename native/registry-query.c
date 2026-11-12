/* A synchronous registry walk performed under insmod's existing recursive
 * loader lock. Only five exact names are counted. Addresses and audio are
 * never written, and no module entry, task or external callback is invoked. */
#include "registry-query.h"
#include <stddef.h>
#ifdef W6RQ_HOST
extern uintptr_t w6rq_host_call(uint32_t);
extern uint32_t w6rq_host_word(uint32_t);
#define CALL(T,A) ((T)w6rq_host_call((uint32_t)(A)))
#else
#define CALL(T,A) ((T)(uintptr_t)(A))
#endif
struct w6rq_guard {uint32_t address,count,fnv;};
#include "registry-profile.h"
struct module_record {struct module_record *next;char name[96];
 uint32_t entry,uninit,arg,exports,nexports,text,data,dynamic,text_size,data_size;};
_Static_assert(sizeof(void *)==4,"P65 pointer ABI");
_Static_assert(offsetof(struct module_record,name)==4,"P65 module name ABI");
_Static_assert(offsetof(struct module_record,entry)==0x64,"P65 module entry ABI");
_Static_assert(offsetof(struct module_record,data_size)==0x88,"P65 module size ABI");
typedef int32_t (*iterator_fn)(int32_t (*)(const struct module_record *,void *),void *);
typedef int32_t (*pid_fn)(void);
typedef int32_t (*open_fn)(const char *,int32_t,...);
typedef int32_t (*read_fn)(int32_t,void *,uint32_t);
typedef int32_t (*write_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*close_fn)(int32_t);
static const char *const names[]={"w6rc","w6rplay","w6rplayer","w6rxlink","w6rdirect"};
struct finding {uint32_t visited,counts[5];int32_t error;};
static void copy(void *to,const void *from,uint32_t n){uint8_t *d=to;const uint8_t *s=from;while(n--)*d++=*s++;}
static void clear(void *out,uint32_t n){volatile uint8_t *p=out;while(n--)*p++=0;}
static int same(const void *a,const void *b,uint32_t n){const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;}
static uint32_t word(uint32_t address){
#ifdef W6RQ_HOST
 return w6rq_host_word(address);
#else
 return *(volatile const uint32_t *)(uintptr_t)address;
#endif
}
static int firmware_matches(void){for(uint32_t k=0;k<sizeof(registry_guards)/sizeof(registry_guards[0]);k++){
 const struct w6rq_guard *g=&registry_guards[k];
#ifdef W6RQ_HOST
 typedef int (*guard_fn)(uint32_t,uint32_t,uint32_t);if(!CALL(guard_fn,0xfffffff0u)(g->address,g->count,g->fnv))return 0;
#else
 uint32_t h=2166136261u;const volatile uint8_t *p=(const volatile uint8_t *)(uintptr_t)g->address;
 for(uint32_t i=0;i<g->count;i++)h=(h^p[i])*16777619u;if(h!=g->fnv)return 0;
#endif
 }return 1;}
static uint32_t crc(const uint8_t *b,uint32_t n){uint32_t c=~0u;while(n--){c^=*b++;for(uint32_t i=0;i<8;i++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;}
static int parse_hex(const uint8_t *s,uint32_t n,uint32_t *out){uint32_t v=0;while(n--){uint32_t d=*s++;if(d>='0'&&d<='9')d-='0';else if(d>='a'&&d<='f')d=d-'a'+10;else return 0;v=(v<<4)|d;}if(out)*out=v;return 1;}
static void hex(uint8_t *s,uint32_t n,uint32_t v){while(n){uint32_t d=v&15u;s[--n]=(uint8_t)(d<10?'0'+d:'a'+d-10);v>>=4;}}
static int read_request(uint8_t b[W6RQ_REQUEST_SIZE]){int32_t fd=CALL(open_fn,0x0c8bef01u)(W6RQ_REQUEST_PATH,1);if(fd<0)return W6RQ_IO;
 uint32_t at=0,tries=0;int result=0;uint8_t extra;
 while(at<W6RQ_REQUEST_SIZE&&tries++<32){int32_t n=CALL(read_fn,0x0c8beaf1u)(fd,b+at,W6RQ_REQUEST_SIZE-at);if(n<=0||(uint32_t)n>W6RQ_REQUEST_SIZE-at){result=W6RQ_SHORT;break;}at+=(uint32_t)n;}
 if(at!=W6RQ_REQUEST_SIZE||CALL(read_fn,0x0c8beaf1u)(fd,&extra,1)!=0)result=W6RQ_SHORT;
 if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)result=W6RQ_IO;return result;}
static int valid_request(const uint8_t b[W6RQ_REQUEST_SIZE]){uint32_t seq,check,nonzero=0;
 if(!same(b,b+64,64)||!same(b,"W6RQ1\n",6)||b[22]!='\n'||b[31]!='\n'||b[40]!='\n'||!same(b+56,"W6RQEND\n",8))return 0;
 for(uint32_t i=6;i<22;i++){if(!parse_hex(b+i,1,NULL))return 0;nonzero|=b[i]!='0';}
 if(!nonzero||!parse_hex(b+23,8,&seq)||!seq||!parse_hex(b+32,8,&check)||crc(b,32)!=check)return 0;
 for(uint32_t i=41;i<56;i++)if(b[i]!=' ')return 0;return 1;}
static int record_range(const struct module_record *m){uint32_t a=(uint32_t)(uintptr_t)m,n=(uint32_t)sizeof(*m);if(a&3u)return 0;
 return (a>=0x20000000u&&a<0x20200000u&&n<=0x20200000u-a)||(a>=0x3c000000u&&a<0x3e000000u&&n<=0x3e000000u-a);}
static int32_t inspect(const struct module_record *m,void *opaque){struct finding *f=opaque;
 if(++f->visited>W6RQ_MAX_MODULES||!record_range(m)){f->error=W6RQ_REGISTRY;return f->error;}
 uint32_t length=0;while(length<sizeof(m->name)&&m->name[length]){uint8_t c=(uint8_t)m->name[length];if(c<0x21||c>0x7e){f->error=W6RQ_REGISTRY;return f->error;}length++;}
 if(!length||length==sizeof(m->name)){f->error=W6RQ_REGISTRY;return f->error;}
 for(uint32_t k=0;k<5;k++){uint32_t j=0;while(j<length&&names[k][j]&&m->name[j]==names[k][j])j++;if(j==length&&names[k][j]==0){if(++f->counts[k]>1){f->error=W6RQ_DUPLICATE;return f->error;}break;}}
 return 0;}
static int write_status(const uint8_t request[W6RQ_REQUEST_SIZE],const struct finding *f,int32_t result){uint8_t b[W6RQ_STATUS_SIZE];
 for(uint32_t i=0;i<128;i++)b[i]=' ';copy(b,"W6RS1\n",6);copy(b+6,request+6,16);b[22]=b[31]=b[40]='\n';copy(b+23,request+23,8);hex(b+32,8,(uint32_t)result);
 for(uint32_t k=0;k<5;k++){uint32_t at=41+k*9;hex(b+at,8,f->counts[k]);b[at+8]='\n';}
 hex(b+86,8,f->visited);b[94]='\n';hex(b+95,8,crc(b,95));b[103]='\n';copy(b+120,"W6RSEND\n",8);copy(b+128,b,128);
 int32_t fd=CALL(open_fn,0x0c8bef01u)(W6RQ_STATUS_PATH,2);if(fd<0)return W6RQ_IO;uint32_t at=0,tries=0;int written=0;
 while(at<W6RQ_STATUS_SIZE&&tries++<32){int32_t n=CALL(write_fn,0x0c8be041u)(fd,b+at,W6RQ_STATUS_SIZE-at);if(n<=0||(uint32_t)n>W6RQ_STATUS_SIZE-at){written=W6RQ_SHORT;break;}at+=(uint32_t)n;}
 if(at!=W6RQ_STATUS_SIZE)written=W6RQ_SHORT;if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)written=W6RQ_IO;return written;}
__attribute__((used,noinline,section(".text.watch6_entry")))
int32_t watch6_registry_query_initialize(struct w6rq_unload_pair *pair){uint8_t request[W6RQ_REQUEST_SIZE];struct finding f;clear(&f,sizeof(f));
 if(!pair)return W6RQ_INVALID;pair->callback=NULL;pair->context=NULL;
 if(!firmware_matches())return W6RQ_FIRMWARE;
 int32_t pid=CALL(pid_fn,0x0c4c96adu)();uint32_t depth=word(0x3c3b9394u);
 if(pid<=0||(int32_t)word(0x3c3b9390u)!=pid||!depth||depth>65535u)return W6RQ_LOCK;
 if(read_request(request)!=0||!valid_request(request))return W6RQ_REQUEST;
 int32_t result=CALL(iterator_fn,0x0c4fa055u)(inspect,&f);
 if((int32_t)word(0x3c3b9390u)!=pid||word(0x3c3b9394u)!=depth)result=W6RQ_LOCK;
 else if(f.error)result=f.error;else if(result)result=W6RQ_REGISTRY;
 int logged=write_status(request,&f,result);return result?result:logged;
}
