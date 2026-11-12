/* Concrete independently spawned P65 meeting source candidate.
 * Candidate enablement is separate from physical acceptance; loading is never
 * a microphone Start without the explicit matching START + GO user intent.
 * After explicit START + GO, Capture start is called once, on THIS owner only. */
#include "p65-owner.h"
#include "p65-media.h"
#include "p65-fs.h"
#include "owner-runtime.h"
#include "status.h"
#ifndef VS_DATA_ROOT
#define VS_DATA_ROOT "/data/watch6recorder/"
#endif
#define BASE VS_DATA_ROOT
#define CALL(T,A) ((T)(uintptr_t)(A))
struct spawn_attr {uint8_t flags,priority,policy,padding;uint32_t mask[2],stacksize;void *stackaddr;};
typedef int32_t (*open_fn)(const char *,int32_t,...);
typedef int32_t (*read_fn)(int32_t,void *,uint32_t);
typedef int32_t (*write_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*close_fn)(int32_t);
typedef int32_t (*main_fn)(int32_t,char **);
typedef int32_t (*spawn_fn)(const char *,main_fn,const void *,const struct spawn_attr *,char *const *,char *const *);
typedef int32_t (*attr_fn)(struct spawn_attr *);
typedef int32_t (*stack_fn)(struct spawn_attr *,uint32_t);
typedef int32_t (*pid_fn)(void);
typedef void *(*lookup_fn)(int32_t);
typedef uint64_t (*clock_fn)(void);
typedef int32_t (*sleep_fn)(uint32_t);
_Static_assert(sizeof(struct spawn_attr)==20,"P65 spawn ABI");
struct owner_context {
 struct vs_owner owner;struct vs_p65_media media;struct vs_p65_fs fs;
 char nonce[17];uint32_t rate,slots,max_seconds,status_sequence,phone_sequence,archive_only;
 uint32_t next_control,next_stop,stop_sequence,spawned,done,wait_error,prefix_sequence,pause_sequence;int32_t pid;
 uint8_t control[512],receipt[512];char status[1536];
};
static struct owner_context ctx;
static void zero(void *p,uint32_t n){uint8_t *b=p;while(n--)*b++=0;}
static void copy(void *out,const void *in,uint32_t n){uint8_t *a=out;const uint8_t *b=in;while(n--)*a++=*b++;}
static int equal(const void *a,const void *b,uint32_t n){const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;}
static uint32_t crc(const uint8_t *p,uint32_t n){uint32_t c=0xffffffffu,k;while(n--){c^=*p++;for(k=0;k<8;k++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return c^0xffffffffu;}
static int parse(const char *s,uint32_t n,uint32_t *out){uint32_t v=0,i;for(i=0;i<n;i++){uint32_t c=(uint8_t)s[i],d;if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;else return 0;v=(v<<4)|d;}*out=v;return 1;}
static int read_fixed(const char *path,uint8_t *out){uint32_t n=0,tries=0;int ret=0;int32_t fd=CALL(open_fn,0x0c8bef01u)(path,0x401);if(fd<0)return -1;while(n<512&&tries++<32){int32_t got=CALL(read_fn,0x0c8beaf1u)(fd,out+n,512-n);if(got<=0||(uint32_t)got>512-n){ret=-1;break;}n+=(uint32_t)got;}if(!ret){uint8_t extra;if(CALL(read_fn,0x0c8beaf1u)(fd,&extra,1)!=0)ret=-1;}if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)ret=-1;return ret||n!=512?-1:0;}
static int valid_control(const char *path,const char kind[8],uint32_t *sequence){uint32_t check;if(read_fixed(path,ctx.control)!=0||!equal(ctx.control,"VSMQ1\n",6)||!equal(ctx.control+24,kind,8)||!equal(ctx.control+6,ctx.nonce,16)||!equal(ctx.control+480,ctx.nonce,16)||!equal(ctx.control+496,"\nend=VSMQ1\n",11)||!equal(ctx.control+32,ctx.control+464,8)||!parse((char *)ctx.control+32,8,sequence)||!*sequence||!parse((char *)ctx.control+472,8,&check)||crc(ctx.control,472)!=check)return 0;return 1;}
static uint32_t now(void *unused){uint64_t ticks=CALL(clock_fn,0x0c4c1e45u)(),remainder=0;uint32_t out=0,i;(void)unused;/* clock() is hardware elapsed ticks at10,000Hz, not process CPU usage. */for(i=0;i<64;i++){remainder=(remainder<<1)|(ticks>>63);ticks<<=1;out<<=1;if(remainder>=10){remainder-=10;out|=1;}}return out;}
static void wait_ms(void *unused,uint32_t ms){uint32_t start=now(0),elapsed;(void)unused;while((elapsed=now(0)-start)<ms){uint32_t left=ms-elapsed;int32_t ret;if(left>1000)left=1000;ret=CALL(sleep_fn,0x0c4c8b39u)(left*1000u);if(ret<0&&ret!=-4){ctx.wait_error=1;break;}}}
static int prepare(void *unused,const char nonce[17]){(void)unused;return vs_p65_media_prepare(&ctx.media,nonce,ctx.rate);}
static int ready(void *unused){
 uint32_t seq,rate;int media;(void)unused;
 media=vs_p65_media_ready(&ctx.media);if(media<=0)return media;
 /* Preparing SESSION/media never grants permission to start the microphone. */
 if(valid_control(BASE "vs-meeting-source-stop.txt","STOP    ",&seq)&&seq>ctx.stop_sequence)return 0;
 /* Explicit START+GO already authorizes this local-only meeting. Neither a
  * phone nor a cloud READY token is part of the recording data path. */
 if(ctx.archive_only)return 1;
 if(!ctx.fs.storage_id[0]||!ctx.fs.epoch[0]||!valid_control(BASE "vs-meeting-source-ready.txt","READY   ",&seq)
  ||!parse((char *)ctx.control+40,8,&rate)||rate!=ctx.rate
  ||!equal(ctx.control+64,ctx.fs.storage_id,36)||!equal(ctx.control+100,ctx.fs.epoch,36))return 0;
 return 1;
}
static int start(void *unused){(void)unused;return vs_p65_media_start(&ctx.media);}
static int read_pcm(void *unused,uint8_t *out,uint32_t bytes){(void)unused;return vs_p65_media_read(&ctx.media,out,bytes);}
static int stop(void *unused){(void)unused;return vs_p65_media_stop(&ctx.media);}
static int stopped(void *unused){(void)unused;return vs_p65_media_stopped(&ctx.media);}
static int close_media(void *unused){(void)unused;return vs_p65_media_close(&ctx.media);}
static int space(void *unused,uint32_t bytes,uint32_t reserve){(void)unused;return vs_p65_fs_space(&ctx.fs,bytes,reserve);}
static int open_extent(void *unused,uint32_t seq,uint64_t offset){(void)unused;return vs_p65_fs_open(&ctx.fs,seq,offset);}
static int append(void *unused,const uint8_t *bytes,uint32_t count){(void)unused;return vs_p65_fs_append(&ctx.fs,bytes,count);}
static int seal(void *unused,const struct vs_extent *e){(void)unused;return vs_p65_fs_seal(&ctx.fs,e);}
static int reclaim(void *unused,const struct vs_extent *e,const char *proof){(void)unused;return vs_p65_fs_reclaim(&ctx.fs,e,proof);}
static int finish(void *unused,uint64_t bytes,int complete,int reason){(void)unused;return vs_p65_fs_finish(&ctx.fs,bytes,complete,reason);}
static int pause_media(void *unused){(void)unused;return vs_p65_media_pause(&ctx.media);}
static int paused_media(void *unused){(void)unused;return vs_p65_media_paused(&ctx.media);}
static int resume_media(void *unused){(void)unused;return vs_p65_media_resume(&ctx.media);}
static int resumed_media(void *unused){(void)unused;return vs_p65_media_resumed(&ctx.media);}
static int pause_sync(void *unused){(void)unused;return vs_p65_fs_pause_sync(&ctx.fs);}
static const struct vs_pause_ops pause_ops={pause_media,paused_media,resume_media,resumed_media,pause_sync};
static int stop_requested(void *unused,const char nonce[17]){
 uint32_t seq,reason,current=now(0);(void)unused;(void)nonce;
 if(ctx.wait_error)return VS_REASON_CAPTURE;if((int32_t)(current-ctx.next_stop)<0)return 0;ctx.next_stop=current+250;
 if(valid_control(BASE "vs-meeting-source-stop.txt","STOP    ",&seq)&&seq>ctx.stop_sequence&&parse((char *)ctx.control+136,8,&reason)&&reason>=VS_REASON_USER&&reason<=VS_REASON_TIMEOUT){ctx.stop_sequence=seq;return (int)reason;}
 if(ctx.archive_only){
  if(valid_control(BASE "vs-meeting-source-pause.txt","PAUSE   ",&seq)&&seq>ctx.pause_sequence){ctx.pause_sequence=seq;(void)vs_owner_pause(&ctx.owner,&pause_ops,current);}
  else if(valid_control(BASE "vs-meeting-source-pause.txt","RESUME  ",&seq)&&seq>ctx.pause_sequence){ctx.pause_sequence=seq;(void)vs_owner_resume(&ctx.owner,current);}
 }
 return 0;
}
static int publish(void *,const struct vs_owner *);
/* Standalone recorder never accepts phone durability/reclaim messages. */
static int receipts(void *unused,struct vs_owner *owner){(void)unused;(void)owner;return ctx.wait_error?-1:0;}
static char *text(char *p,const char *s){while(*s)*p++=*s++;return p;}
static char *number(char *p,uint32_t v){char temp[10];uint32_t n=0;do{temp[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)*p++=temp[--n];return p;}
static int publish(void *unused,const struct vs_owner *o){
 static const char *const phases[]={"idle","starting","recording","stopping","draining","closed","retained","error","pausing","paused","resuming"};char *p=ctx.status;(void)unused;
 p=text(p,"{\"v\":1,\"continuous\":true,\"verified\":false,\"user_started\":true,\"identity_persisted\":true,\"id\":\"");p=text(p,ctx.nonce);p=text(p,"\",\"phase\":\"");p=text(p,phases[o->phase]);p=text(p,"\",\"rate\":");p=number(p,ctx.rate);p=text(p,",\"sample_rate\":");p=number(p,ctx.rate);p=text(p,",\"pid\":");p=number(p,(uint32_t)ctx.pid);
 p=text(p,",\"produced_offset\":");p=number(p,(uint32_t)o->produced);p=text(p,",\"readable_offset\":");p=number(p,(uint32_t)o->durable);p=text(p,",\"reclaimed_offset\":");p=number(p,(uint32_t)o->phone_durable);p=text(p,",\"phone_durable_offset\":");p=number(p,(uint32_t)ctx.fs.phone_durable);
 p=text(p,",\"archive_only\":");p=text(p,ctx.archive_only?"true":"false");
 p=text(p,",\"storage_id\":\"");p=text(p,ctx.fs.storage_id);p=text(p,"\",\"cache_used\":");p=number(p,(uint32_t)(o->produced-o->phone_durable));p=text(p,",\"cache_limit\":");p=number(p,(ctx.slots+VS_TAIL_EXTENTS)*VS_EXTENT_BYTES);p=text(p,",\"reserve_bytes\":131072,\"tail_complete\":");p=text(p,o->phase==VS_CLOSED&&o->eof&&o->stop_seen&&!o->interrupted&&!o->media_opened?"true":"false");p=text(p,",\"whole_meeting_complete\":");p=text(p,o->complete?"true":"false");p=text(p,",\"lost_samples\":");p=text(p,o->interrupted?"null":"0");p=text(p,",\"stop_reason\":\"");
 {static const char *const reasons[]={"","user","cache_limit","low_space","capture_error","storage_error","timeout"};p=text(p,o->reason<=VS_REASON_TIMEOUT?reasons[o->reason]:"unknown");}
 p=text(p,"\",\"error_code\":");p=number(p,o->error);p=text(p,",\"extent_first_seq\":");p=number(p,o->count?o->extents[o->head].seq:o->next_seq);p=text(p,",\"extent_count\":");p=number(p,o->count);p=text(p,",\"status_sequence\":");p=number(p,++ctx.status_sequence);p=text(p,",\"sequence_end\":");p=number(p,ctx.status_sequence);p=text(p,"}\n");
 return vs_write_source_status(ctx.nonce,ctx.status_sequence,ctx.status,(uint32_t)(p-ctx.status));
}
static void prefix_hex(char *p,uint64_t v,uint32_t digits){while(digits){uint32_t d=(uint32_t)v&15;p[--digits]=(char)(d<10?'0'+d:'a'+d-10);v>>=4;}}
static int publish_stream(void *unused,const struct vs_owner *o){char frame[128];uint32_t i,n=0;int32_t fd;int ret=0;(void)unused;if(ctx.fs.fd<0||!ctx.fs.active_seq||ctx.fs.active_bytes>65536||ctx.fs.active_offset+ctx.fs.active_bytes!=o->produced)return 0;
 for(i=0;i<128;i++)frame[i]=' ';copy(frame,"VSMP1\n",6);copy(frame+6,ctx.nonce,16);frame[22]='\n';prefix_hex(frame+24,++ctx.prefix_sequence,8);prefix_hex(frame+32,o->produced,16);prefix_hex(frame+48,ctx.fs.active_seq,8);prefix_hex(frame+56,ctx.fs.active_offset,16);prefix_hex(frame+72,ctx.fs.active_bytes,8);prefix_hex(frame+80,ctx.rate,8);prefix_hex(frame+96,ctx.prefix_sequence,8);prefix_hex(frame+104,crc((uint8_t *)frame,104),8);copy(frame+112,ctx.nonce,16);
 fd=CALL(open_fn,0x0c8bef01u)(BASE "vs-meeting-source-prefix.txt",0x406,0600);if(fd<0)return -1;while(n<128){int32_t got=CALL(write_fn,0x0c8be041u)(fd,frame+n,128-n);if(got<=0||(uint32_t)got>128-n){ret=-1;break;}n+=(uint32_t)got;}if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)ret=-1;return ret;
}
static int maximum(void *unused,uint32_t started,uint32_t current){(void)unused;return (uint32_t)(current-started)>=ctx.max_seconds*1000u;}
static int32_t worker(int32_t argc,char **argv){
 uint32_t since,seq;struct vs_ops ops={VS_CAP_ALL,0,prepare,ready,start,read_pcm,stop,stopped,close_media,space,open_extent,append,seal,reclaim,finish};struct vs_owner_runtime runtime={0,now,stop_requested,receipts,publish,wait_ms,maximum,publish_stream};(void)argc;(void)argv;
 ctx.pid=CALL(pid_fn,0x0c4c96adu)();since=now(0);
 /* init is under loader lock. This task waits for an explicit GO written only
  * after successful insmod, so it cannot open media in that initializer. */
 while(!valid_control(BASE "vs-meeting-source-go.txt","GO      ",&seq)||seq!=2){if((uint32_t)(now(0)-since)>=8000u||ctx.wait_error){__atomic_store_n(&ctx.done,1,__ATOMIC_RELEASE);return -1;}wait_ms(0,50);}
 if(vs_p65_fs_init(&ctx.fs,ctx.nonce,ctx.rate)!=0){__atomic_store_n(&ctx.done,1,__ATOMIC_RELEASE);return -1;}
 if(ctx.archive_only&&vs_p65_fs_space(&ctx.fs,VS_EXTENT_BYTES,VS_TAIL_EXTENTS*VS_EXTENT_BYTES)==1){
  /* Actual free flash determines the offline budget, never advertised RAM.
   * Account for a metadata allocation per extent and both tail extents. */
  uint32_t available=ctx.fs.available>0xffffffffu?0xffffffffu:(uint32_t)ctx.fs.available;
  uint32_t units=available/(VS_EXTENT_BYTES+ctx.fs.allocation_bytes);
  uint32_t slots=units>VS_TAIL_EXTENTS?((units-VS_TAIL_EXTENTS)>VS_MAX_EXTENTS?VS_MAX_EXTENTS:(uint32_t)(units-VS_TAIL_EXTENTS)):2u;
  if(slots<2)slots=2;if(slots<ctx.slots)ctx.slots=slots;
 }
 (void)vs_owner_run(&ctx.owner,&ops,&runtime,ctx.nonce,ctx.rate,ctx.slots);
 __atomic_store_n(&ctx.done,1,__ATOMIC_RELEASE);return 0;
}
static int32_t unload(void *unused){(void)unused;if(!ctx.spawned)return 0;if(!__atomic_load_n(&ctx.done,__ATOMIC_ACQUIRE)||ctx.pid<=0||CALL(lookup_fn,0x0c4c5c45u)(ctx.pid)!=0)return -16;return 0;}
int32_t vs_p65_owner_initialize(struct unload_pair *pair){
 struct spawn_attr attrs;char *argv[]={0};uint32_t seq;int32_t result;
 zero(&ctx,sizeof(ctx));ctx.media.listener=ctx.media.data=ctx.fs.fd=-1;
 /* Read nonce once before full verification; only strict lowercase16hex. */
 if(read_fixed(BASE "vs-meeting-source-start.txt",ctx.control)!=0)return -1;
 {uint32_t i;for(i=0;i<16;i++){char c=(char)ctx.control[6+i];if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return -2;ctx.nonce[i]=c;}}
 if(!valid_control(BASE "vs-meeting-source-start.txt","START   ",&seq)||seq!=1||!parse((char *)ctx.control+40,8,&ctx.rate)||!parse((char *)ctx.control+48,8,&ctx.slots)||!parse((char *)ctx.control+56,8,&ctx.max_seconds)||(ctx.rate!=8000&&ctx.rate!=16000)||ctx.slots<2||ctx.slots>VS_MAX_EXTENTS||!ctx.max_seconds||ctx.max_seconds>43200)return -3;
 /* Blank is the legacy cloud-gated intent. New intents must explicitly opt in. */
 if(!equal(ctx.control+144,"        ",8)&&(!parse((char *)ctx.control+144,8,&ctx.archive_only)||ctx.archive_only>1))return -3;
 if(valid_control(BASE "vs-meeting-source-go.txt","GO      ",&seq))return -7;
 result=CALL(attr_fn,0x0c4fdcc9u)(&attrs);if(result)return -4;result=CALL(stack_fn,0x0c4fdd69u)(&attrs,16384);if(result)return -5;
 pair->callback=unload;pair->context=&ctx;ctx.spawned=1;
 result=CALL(spawn_fn,0x0c4c96f5u)("w6rec_owner",worker,0,&attrs,argv,0);
 if(result<=0){ctx.spawned=0;pair->callback=0;pair->context=0;return -6;}
 /* Never return loader failure after a task may reference this module. */
 return 0;
}
