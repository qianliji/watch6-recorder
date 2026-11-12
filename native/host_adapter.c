/* Synthetic in-memory test adapter. Never linked into a device artifact. */
#include "spool.h"
struct memory_extent { uint8_t data[VS_EXTENT_BYTES];uint32_t seq,bytes,sealed,opened; };
struct fixture {
 struct memory_extent files[4];struct vs_owner owner;
 uint32_t total,received,prepared,started,stopped,closed,seals,reclaims,appends;
 uint32_t eof_enabled,event_enabled,close_error,seal_error,space_error,append_error,prepare_error,late_event_error;
 uint32_t published_complete,published_bytes,interrupted,active,storage_overwrite;
};
static struct fixture f;
uint32_t host_cases,host_assertions,host_failures;
#define CHECK(x) do { host_assertions++;if(!(x))host_failures++; } while(0)
static void reset(uint32_t total){uint32_t n;uint8_t *p=(uint8_t *)&f;for(n=0;n<sizeof(f);n++)p[n]=0;f.total=total;f.eof_enabled=f.event_enabled=1;}
static int prepare(void *p,const char *nonce){struct fixture *x=p;(void)nonce;x->prepared++;return x->prepare_error?-1:0;}
static int ready(void *p){(void)p;return 1;}
static int start(void *p){struct fixture *x=p;x->started++;return 0;}
static int receive(void *p,uint8_t *out,uint32_t cap){struct fixture *x=p;uint32_t n,count;if(x->received>=x->total)return x->stopped&&x->eof_enabled?VS_RX_EOF:VS_RX_AGAIN;count=x->total-x->received;if(count>cap)count=cap;for(n=0;n<count;n++)out[n]=(uint8_t)(x->received+n);x->received+=count;return (int)count;}
static int stop(void *p){struct fixture *x=p;x->stopped++;return 0;}
static int stopped(void *p){struct fixture *x=p;return x->stopped&&x->event_enabled?1:0;}
static int close_capture(void *p){struct fixture *x=p;x->closed++;if(x->late_event_error)x->event_enabled=0;return x->close_error?-1:0;}
static int space(void *p,uint32_t bytes,uint32_t reserve){struct fixture *x=p;(void)bytes;(void)reserve;return !x->space_error;}
static int open_extent(void *p,uint32_t seq,uint64_t offset){struct fixture *x=p;struct memory_extent *e=&x->files[(seq-1)%4];(void)offset;if(e->seq){x->storage_overwrite++;return -1;}e->seq=seq;e->opened=1;x->active=(seq-1)%4;return 0;}
static int append(void *p,const uint8_t *bytes,uint32_t count){struct fixture *x=p;struct memory_extent *e=&x->files[x->active];uint32_t n;x->appends++;if(x->append_error)return -1;if(count>VS_EXTENT_BYTES-e->bytes)return -1;for(n=0;n<count;n++)e->data[e->bytes+n]=bytes[n];e->bytes+=count;return 0;}
static int seal_extent(void *p,const struct vs_extent *extent){struct fixture *x=p;struct memory_extent *e=&x->files[x->active];if(x->seal_error||e->bytes!=extent->bytes)return -1;e->opened=0;if(!e->bytes){e->seq=0;return 0;}e->sealed=1;x->seals++;return 0;}
static int reclaim(void *p,const struct vs_extent *extent,const char *receipt){struct fixture *x=p;struct memory_extent *e=&x->files[(extent->seq-1)%4];(void)receipt;if(!e->sealed||e->seq!=extent->seq)return -1;e->seq=e->bytes=e->sealed=0;x->reclaims++;return 0;}
static int finish(void *p,uint64_t bytes,int complete,int reason){struct fixture *x=p;x->published_complete=(uint32_t)complete;x->published_bytes=(uint32_t)bytes;x->interrupted=reason!=VS_REASON_USER;return 0;}
static struct vs_ops ops(void){struct vs_ops o={VS_CAP_ALL,&f,prepare,ready,start,receive,stop,stopped,close_capture,space,open_extent,append,seal_extent,reclaim,finish};return o;}
static int begin(void){struct vs_ops p=ops();return vs_owner_init(&f.owner,&p,"0123456789abcdef",8000,2,0);}
static void acknowledge(void){while(f.owner.count){struct vs_extent *e=&f.owner.extents[f.owner.head];if(e->state!=VS_SEALED)return;CHECK(vs_owner_ack(&f.owner,f.owner.nonce,e->seq,e->offset+e->bytes,e->crc,"phone-durable-test-receipt")==0);}}
static void test_gate(void){struct vs_ops p;reset(4096);p=ops();p.capabilities&=~VS_CAP_DRAIN;CHECK(vs_owner_init(&f.owner,&p,"0123456789abcdef",8000,2,0)<0);CHECK(f.prepared==0&&f.started==0);host_cases++;}
static void test_short(void){reset(10000);CHECK(begin()==0);vs_owner_step(&f.owner,1);CHECK(f.owner.produced==10000&&f.started==1);vs_owner_stop(&f.owner,VS_REASON_USER,2);vs_owner_step(&f.owner,3);CHECK(f.owner.phase==VS_CLOSED&&f.published_complete==1&&f.published_bytes==10000);CHECK(f.started==1&&f.stopped==1&&f.closed==1&&vs_owner_unloadable(&f.owner));CHECK(f.seals==1);acknowledge();CHECK(f.owner.phone_durable==10000);host_cases++;}
static void test_continuous(void){uint32_t n;reset(10*VS_EXTENT_BYTES+1234);CHECK(begin()==0);for(n=1;n<300&&f.received<f.total;n++){vs_owner_step(&f.owner,n*25);acknowledge();}CHECK(f.received==f.total&&f.owner.produced==f.total&&f.started==1&&f.stopped==0);vs_owner_stop(&f.owner,VS_REASON_USER,8000);vs_owner_step(&f.owner,8025);acknowledge();CHECK(f.owner.phase==VS_CLOSED&&f.published_complete&&f.owner.phone_durable==f.total);CHECK(f.storage_overwrite==0&&f.reclaims==11);host_cases++;}
static void test_ack(void){struct vs_extent *e;reset(VS_EXTENT_BYTES+2);CHECK(begin()==0);vs_owner_step(&f.owner,1);vs_owner_step(&f.owner,26);vs_owner_step(&f.owner,51);e=&f.owner.extents[f.owner.head];CHECK(e->state==VS_SEALED);CHECK(vs_owner_ack(&f.owner,"1123456789abcdef",e->seq,e->offset+e->bytes,e->crc,"x")<0);CHECK(vs_owner_ack(&f.owner,f.owner.nonce,e->seq,e->offset+e->bytes,e->crc^1,"x")<0);CHECK(vs_owner_ack(&f.owner,f.owner.nonce,e->seq+1,e->offset+e->bytes,e->crc,"x")<0);CHECK(vs_owner_ack(&f.owner,f.owner.nonce,e->seq,e->offset+e->bytes,e->crc,"")<0);CHECK(f.reclaims==0);host_cases++;}
static void test_budget(void){uint32_t n;reset(2*VS_EXTENT_BYTES+4096);CHECK(begin()==0);for(n=1;n<20&&f.owner.phase!=VS_CLOSED;n++)vs_owner_step(&f.owner,n*25);CHECK(f.owner.phase==VS_CLOSED&&f.owner.reason==VS_REASON_BUDGET&&!f.published_complete);CHECK(f.started==1&&f.stopped==1&&f.owner.produced==f.total&&f.storage_overwrite==0);host_cases++;}
static void test_seal_failure(void){reset(VS_EXTENT_BYTES+2);CHECK(begin()==0);f.seal_error=1;vs_owner_step(&f.owner,1);vs_owner_step(&f.owner,26);vs_owner_step(&f.owner,51);CHECK(f.seals==0&&f.owner.durable==0&&!f.published_complete);CHECK(f.owner.error!=0&&f.owner.phone_durable==0);vs_owner_step(&f.owner,76);CHECK(f.owner.phase==VS_RETAINED&&f.stopped==1&&!vs_owner_unloadable(&f.owner));host_cases++;}
static void test_tail_event(void){reset(6000);CHECK(begin()==0);vs_owner_step(&f.owner,1);f.event_enabled=0;vs_owner_stop(&f.owner,VS_REASON_USER,2);vs_owner_step(&f.owner,3);CHECK(f.owner.phase==VS_DRAINING&&f.owner.eof&&f.closed==0);f.event_enabled=1;vs_owner_step(&f.owner,4);CHECK(f.owner.phase==VS_CLOSED&&f.published_complete);host_cases++;}
static void test_missing_eof(void){reset(100);CHECK(begin()==0);vs_owner_step(&f.owner,1);f.eof_enabled=0;vs_owner_stop(&f.owner,VS_REASON_USER,2);vs_owner_step(&f.owner,3);vs_owner_step(&f.owner,16003);CHECK(f.owner.phase==VS_RETAINED&&f.owner.media_opened&&!vs_owner_unloadable(&f.owner));CHECK(!f.published_complete&&f.closed==0);host_cases++;}
static void test_close_failure(void){reset(100);CHECK(begin()==0);vs_owner_step(&f.owner,1);f.close_error=1;vs_owner_stop(&f.owner,VS_REASON_USER,2);vs_owner_step(&f.owner,3);vs_owner_step(&f.owner,1004);vs_owner_step(&f.owner,2005);CHECK(f.owner.phase==VS_RETAINED&&f.closed==3&&!vs_owner_unloadable(&f.owner));CHECK(f.started==1&&f.stopped==1&&!f.published_complete);host_cases++;}
static void test_space(void){reset(100);f.space_error=1;CHECK(begin()<0);CHECK(f.prepared==0&&f.started==0);host_cases++;}
static void test_empty(void){uint32_t i;reset(0);CHECK(begin()==0);vs_owner_step(&f.owner,1);vs_owner_stop(&f.owner,VS_REASON_USER,2);vs_owner_step(&f.owner,3);CHECK(f.owner.phase==VS_CLOSED&&!f.published_complete&&f.published_bytes==0);CHECK(!f.owner.have_active&&!f.owner.count);for(i=0;i<4;i++)CHECK(!f.files[i].opened&&!f.files[i].seq);CHECK(vs_owner_unloadable(&f.owner));host_cases++;}
static void test_prepare_failure(void){reset(100);f.prepare_error=1;CHECK(begin()<0);vs_owner_step(&f.owner,1);CHECK(f.started==0&&f.stopped==0&&f.closed==1&&!f.published_complete);host_cases++;}
static void test_no_heartbeat_dependency(void){reset(500000);CHECK(begin()==0);vs_owner_step(&f.owner,1);acknowledge();vs_owner_step(&f.owner,600001);CHECK(f.started==1&&f.owner.phase==VS_RECORDING&&f.stopped==0);host_cases++;}
static void test_late_event(void){reset(1000);CHECK(begin()==0);vs_owner_step(&f.owner,1);f.late_event_error=1;vs_owner_stop(&f.owner,VS_REASON_USER,2);vs_owner_step(&f.owner,3);CHECK(f.owner.phase==VS_CLOSED&&f.closed==1&&!f.owner.media_opened);CHECK(f.owner.interrupted&&f.owner.error==19&&!f.published_complete);host_cases++;}
extern void host_fs_all(void);
int run_all(void){host_cases=host_assertions=host_failures=0;test_gate();test_short();test_continuous();test_ack();test_budget();test_seal_failure();test_tail_event();test_missing_eof();test_close_failure();test_space();test_empty();test_prepare_failure();test_no_heartbeat_dependency();test_late_event();host_fs_all();return (int)host_failures;}
