/* Exact P65 3.100.043 player candidate. Own source WAV cache only; no firmware
 * writes, network, microphone operation, or deletion of original PCM/metadata.
 * Player ABI is corroborated by the local pinned image and upstream interface
 * definitions; real speaker/focus/tail behavior still requires device testing. */
#include "player.h"
#include <stddef.h>
#ifndef W6R_PLAYER_BASE
#define W6R_PLAYER_BASE "/data/watch6recorder/"
#endif
#define BASE W6R_PLAYER_BASE
#ifdef W6R_PLAYER_HOST
extern uintptr_t w6r_player_host_call(uint32_t);
#define CALL(T,A) ((T)w6r_player_host_call((uint32_t)(A)))
#else
#define CALL(T,A) ((T)(uintptr_t)(A))
#endif
struct w6r_player_guard {uint32_t address,count,fnv;};
#include "player-profile.h"
typedef int32_t (*open_fn)(const char *,int32_t,...);
typedef int32_t (*read_fn)(int32_t,void *,uint32_t);
typedef int32_t (*write_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*close_fn)(int32_t);
typedef int32_t (*sync_fn)(int32_t);
typedef int32_t (*unlink_fn)(const char *);
typedef int32_t *(*errno_fn)(void);
typedef uint64_t (*clock_fn)(void);
typedef int32_t (*sleep_fn)(uint32_t);
typedef void *(*player_open_fn)(const char *);
typedef int32_t (*player_close_fn)(void *,int32_t);
typedef int32_t (*player_prepare_fn)(void *,const char *,const char *);
typedef int32_t (*player_handle_fn)(void *);
typedef int32_t (*player_value_fn)(void *,uint32_t *);
typedef void (*event_fn)(void *,int32_t,int32_t,const char *);
typedef int32_t (*player_event_fn)(void *,void *,event_fn);
struct spawn_attr {uint8_t flags,priority,policy,padding;uint32_t mask[2],stacksize;void *stackaddr;};
typedef int32_t (*main_fn)(int32_t,char **);
typedef int32_t (*spawn_fn)(const char *,main_fn,const void *,const struct spawn_attr *,char *const *,char *const *);
typedef int32_t (*attr_fn)(struct spawn_attr *);
typedef int32_t (*stack_fn)(struct spawn_attr *,uint32_t);
typedef int32_t (*pid_fn)(void);
typedef void *(*lookup_fn)(int32_t);
enum {P_INIT=0,P_BUILD=1,P_READY=2,P_PREPARING=3,P_PLAYING=4,P_PAUSING=5,P_PAUSED=6,P_RESUMING=7,P_STOPPING=8,P_DONE=9,P_ERROR=10,P_RETAINED=11};
struct player_context {
 char operation[17],record[17],cache[17],cache_path[128],archive_hash[17],expected_hash[17];
 uint32_t mode,expected_crc,total,rate,pcm_crc,prepared,position,duration,phase,sequence,control_sequence,events,next_status,next_cancel;
 int32_t pid,error,event_error;void *handle;uint32_t done,spawned,cache_created,io_uncertain;
 uint8_t control[512],meta[512],session[512],end[512],buffer[2048],proc[4096];
};
static struct player_context ctx;
static void zero(void *out,uint32_t n){uint8_t *p=out;while(n--)*p++=0;}
static void copy(void *out,const void *in,uint32_t n){uint8_t *p=out;const uint8_t *q=in;while(n--)*p++=*q++;}
static int equal(const void *a,const void *b,uint32_t n){const uint8_t *p=a,*q=b;while(n--)if(*p++!=*q++)return 0;return 1;}
static uint32_t length(const char *s){uint32_t n=0;while(s[n])n++;return n;}
static uint32_t crc_table[256],crc_initialized;
static uint32_t crc_more(uint32_t c,const uint8_t *p,uint32_t n){uint32_t k;if(!crc_initialized){uint32_t i;for(i=0;i<256;i++){uint32_t v=i;for(k=0;k<8;k++)v=(v>>1)^(0xedb88320u&(0u-(v&1u)));crc_table[i]=v;}crc_initialized=1;}while(n--)c=(c>>8)^crc_table[(c^*p++)&255];return c;}
static uint32_t crc(const uint8_t *p,uint32_t n){return crc_more(0xffffffffu,p,n)^0xffffffffu;}
static int hex(const uint8_t *p,uint32_t n,uint32_t *out){uint32_t v=0,i;if(n>8)return 0;for(i=0;i<n;i++){uint32_t c=p[i],d;if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;else return 0;v=(v<<4)|d;}*out=v;return 1;}
static int id(const uint8_t *p){uint32_t i,nonzero=0;for(i=0;i<16;i++){uint32_t c=p[i];if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return 0;nonzero|=c!='0';}return nonzero!=0;}
static void hex8(char *out,uint32_t v){uint32_t i=8;while(i){uint32_t d=v&15u;out[--i]=(char)(d<10?'0'+d:'a'+d-10);v>>=4;}}
static uint32_t now(void){uint64_t ticks=CALL(clock_fn,0x0c4c1e45u)(),r=0;uint32_t out=0,i;for(i=0;i<64;i++){r=(r<<1)|(ticks>>63);ticks<<=1;out<<=1;if(r>=10){r-=10;out|=1;}}return out;}
static void sleep_ms(uint32_t ms){if(ms>1000)ms=1000;(void)CALL(sleep_fn,0x0c4c8b39u)(ms*1000u);}
static void path(char *out,const char *prefix,const char *identity,uint32_t seq,const char *suffix){uint32_t n=length(BASE),m;copy(out,BASE,n);m=length(prefix);copy(out+n,prefix,m);n+=m;copy(out+n,identity,16);n+=16;if(seq!=UINT32_MAX){out[n++]='-';hex8(out+n,seq);n+=8;}m=length(suffix);copy(out+n,suffix,m+1);}
static int close_owned(int32_t fd){if(CALL(close_fn,0x0c8bdba9u)(fd)!=0){ctx.io_uncertain=1;return -1;}return 0;}
static int read_fd(int32_t fd,uint8_t *out,uint32_t n){uint32_t got=0,tries=0;while(got<n&&tries++<4096){int32_t r=CALL(read_fn,0x0c8beaf1u)(fd,out+got,n-got);if(r<=0||(uint32_t)r>n-got)return -1;got+=(uint32_t)r;}return got==n?0:-1;}
static int read_exact(const char *name,uint8_t *out,uint32_t n){int error=0;int32_t fd=CALL(open_fn,0x0c8bef01u)(name,0x401);if(fd<0)return -1;if(read_fd(fd,out,n)!=0)error=1;if(!error){uint8_t extra;if(CALL(read_fn,0x0c8beaf1u)(fd,&extra,1)!=0)error=1;}if(close_owned(fd)!=0)error=1;return error?-1:0;}
static int write_all(int32_t fd,const uint8_t *p,uint32_t n){uint32_t tries=0;while(n&&tries++<64){int32_t r=CALL(write_fn,0x0c8be041u)(fd,p,n);if(r<=0||(uint32_t)r>n)return -1;p+=r;n-=(uint32_t)r;}return n?-1:0;}
static int metadata(const char *name,uint8_t *out,const char kind[8]){uint32_t value;if(read_exact(name,out,512)!=0||!equal(out,"VSMC1\n",6)||!equal(out+6,kind,8)||!equal(out+14,ctx.record,16)||out[30]!='\n'||!equal(out+480,ctx.record,16)||!equal(out+496,"\nend=VSMC1\n",11)||!hex(out+472,8,&value)||crc(out,472)!=value)return -1;return 0;}
static int source_identity(void){char name[128];uint32_t upper,rate,total,final_rate;path(name,"vs-mc-",ctx.record,0,".session");if(metadata(name,ctx.session,"SESSION ")!=0||!hex(ctx.session+32,8,&rate)||(rate!=8000&&rate!=16000))return -1;path(name,"vs-mc-",ctx.record,0,".end");if(metadata(name,ctx.end,"CLOSED  ")!=0||!hex(ctx.end+32,8,&upper)||upper||!hex(ctx.end+40,8,&total)||total<2||(total&1)||total>W6R_PLAYER_MAX_PCM||!hex(ctx.end+56,8,&final_rate)||final_rate!=rate)return -2;ctx.total=total;ctx.rate=rate;copy(ctx.archive_hash,ctx.session+472,8);copy(ctx.archive_hash+8,ctx.end+472,8);ctx.archive_hash[16]=0;ctx.duration=(ctx.total/(ctx.rate*2))*1000+((ctx.total%(ctx.rate*2))*1000)/(ctx.rate*2);return 0;}
static int source_unchanged(void){char name[128];path(name,"vs-mc-",ctx.record,0,".session");if(metadata(name,ctx.meta,"SESSION ")!=0||!equal(ctx.meta,ctx.session,512))return -1;path(name,"vs-mc-",ctx.record,0,".end");return metadata(name,ctx.meta,"CLOSED  ")||!equal(ctx.meta,ctx.end,512)?-1:0;}
static int control(const char kind[8],uint32_t *seq){uint32_t checksum;if(read_exact(BASE "w6r-player-control.txt",ctx.control,512)!=0||!equal(ctx.control,"W6P1REQ\n",8)||!equal(ctx.control+8,ctx.operation,16)||!equal(ctx.control+24,ctx.record,16)||!equal(ctx.control+48,kind,8)||!equal(ctx.control+40,ctx.control+464,8)||!equal(ctx.control+480,ctx.operation,16)||!equal(ctx.control+496,"W6P1END\n",8)||!hex(ctx.control+40,8,seq)||!*seq||!hex(ctx.control+472,8,&checksum)||crc(ctx.control,472)!=checksum)return 0;return 1;}
static int cancel_requested(void){uint32_t seq,current=now();if((int32_t)(current-ctx.next_cancel)<0)return 0;ctx.next_cancel=current+250;return control("STOP    ",&seq)&&seq>ctx.control_sequence?(ctx.control_sequence=seq,1):0;}
static char *text(char *p,const char *s){while(*s)*p++=*s++;return p;}
static char *number(char *p,uint32_t v){char s[10];uint32_t n=0;do{s[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)*p++=s[--n];return p;}
static char *signed_number(char *p,int32_t v){if(v<0){*p++='-';return number(p,0u-(uint32_t)v);}return number(p,(uint32_t)v);}
static int publish(void){static const char *const phases[]={"initializing","building","ready","preparing","playing","pausing","paused","resuming","stopping","done","error","retained"};uint8_t frame[1536];char json[1100],check[9],*p=json;uint32_t n,k,sequence=++ctx.sequence;int32_t fd;for(k=0;k<sizeof(frame);k++)frame[k]=' ';
 p=text(p,"{\"v\":1,\"kind\":\"player\",\"operation_id\":\"");p=text(p,ctx.operation);p=text(p,"\",\"record_id\":\"");p=text(p,ctx.record);p=text(p,"\",\"cache_id\":\"");p=text(p,ctx.cache);p=text(p,"\",\"phase\":\"");p=text(p,phases[ctx.phase]);p=text(p,"\",\"sequence\":");p=number(p,sequence);p=text(p,",\"pid\":");p=signed_number(p,ctx.pid);p=text(p,",\"error\":");p=signed_number(p,ctx.error);p=text(p,",\"prepared_bytes\":");p=number(p,ctx.prepared);p=text(p,",\"total_bytes\":");p=number(p,ctx.total);p=text(p,",\"rate\":");p=number(p,ctx.rate);p=text(p,",\"position_ms\":");p=number(p,ctx.position);p=text(p,",\"duration_ms\":");p=number(p,ctx.duration);p=text(p,",\"archive_hash\":\"");p=text(p,ctx.archive_hash);p=text(p,"\",\"pcm_crc32\":\"");hex8(check,ctx.pcm_crc);check[8]=0;p=text(p,check);p=text(p,"\",\"done\":");p=text(p,ctx.done?"true":"false");p=text(p,",\"handle_closed\":");p=text(p,ctx.handle?"false":"true");p=text(p,"}");n=(uint32_t)(p-json);if(n>1408)return -1;
 copy(frame,"W6PST1\n",7);copy(frame+7,ctx.operation,16);copy(frame+24,"seq=",4);hex8((char *)frame+28,sequence);copy(frame+37,"len=",4);hex8((char *)frame+41,n);copy(frame+50,"crc=",4);hex8((char *)frame+54,crc((uint8_t *)json,n));copy(frame+64,json,n);copy(frame+1472,frame,64);
 fd=CALL(open_fn,0x0c8bef01u)(BASE "w6r-player-status.txt",2);if(fd<0)return -1;k=write_all(fd,frame,1536)==0;if(close_owned(fd)!=0)k=0;ctx.next_status=now()+250;return k?0:-1;}
static void progress(void){if((int32_t)(now()-ctx.next_status)>=0)(void)publish();}
static int decimal(const char **p,const char *end,uint32_t *out){uint32_t v=0,count=0;while(*p<end&&(**p==' '||**p=='\t'))(*p)++;while(*p<end&&**p>='0'&&**p<='9'){uint32_t d=(uint32_t)(*(*p)++-'0');if(v>429496729u||(v==429496729u&&d>5))return 0;v=v*10+d;count++;}if(!count||*p==end||(**p!=' '&&**p!='\t'))return 0;*out=v;return 1;}
static int space(uint32_t bytes){int32_t fd=CALL(open_fn,0x0c8bef01u)("/proc/fs/blocks",0x401),n;const char *p,*end;uint32_t found=0;if(fd<0)return -1;n=0;while((uint32_t)n<sizeof(ctx.proc)){int32_t got=CALL(read_fn,0x0c8beaf1u)(fd,ctx.proc+n,sizeof(ctx.proc)-(uint32_t)n);if(got<0||(uint32_t)got>sizeof(ctx.proc)-(uint32_t)n){n=-1;break;}if(!got)break;n+=got;}if(close_owned(fd)!=0||n<1||(uint32_t)n==sizeof(ctx.proc))return -1;p=(char *)ctx.proc;end=p+n;while(p<end){const char *line=p,*last;uint32_t size,total,used,free;while(p<end&&*p!='\n')p++;if(p==end)return -1;last=p++;if(!decimal(&line,last,&size)||!decimal(&line,last,&total)||!decimal(&line,last,&used)||!decimal(&line,last,&free))continue;while(line<last&&(*line==' '||*line=='\t'))line++;if(last-line!=5||!equal(line,"/data",5))continue;if(found++||size<512||size>1048576||(size&(size-1))||free>total||used!=total-free)return -1;if((uint64_t)(free>4?free-4:0)*size<(uint64_t)bytes+262144u)return -1;}return found==1?0:-1;}
static void little16(uint8_t *p,uint32_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void little32(uint8_t *p,uint32_t v){little16(p,v);little16(p+2,v>>16);}
static void wav_header(uint8_t *h){zero(h,44);copy(h,"RIFF",4);little32(h+4,ctx.total+36);copy(h+8,"WAVEfmt ",8);little32(h+16,16);little16(h+20,1);little16(h+22,1);little32(h+24,ctx.rate);little32(h+28,ctx.rate*2);little16(h+32,2);little16(h+34,16);copy(h+36,"data",4);little32(h+40,ctx.total);}
static int cache_crc(uint32_t expected){int32_t fd;uint8_t header[44];uint32_t left=ctx.total,check=0xffffffffu;int result=0;wav_header(header);fd=CALL(open_fn,0x0c8bef01u)(ctx.cache_path,0x401);if(fd<0)return -1;if(read_fd(fd,ctx.buffer,44)!=0||!equal(ctx.buffer,header,44))result=-2;while(!result&&left){uint32_t want=left>sizeof(ctx.buffer)?sizeof(ctx.buffer):left;int32_t n=CALL(read_fn,0x0c8beaf1u)(fd,ctx.buffer,want);if(n<=0||(uint32_t)n>want){result=-3;break;}check=crc_more(check,ctx.buffer,(uint32_t)n);left-=(uint32_t)n;if(cancel_requested()){result=-4;break;}progress();}if(!result){uint8_t extra;if(CALL(read_fn,0x0c8beaf1u)(fd,&extra,1)!=0||(check^0xffffffffu)!=expected)result=-5;}if(close_owned(fd)!=0)result=-6;return result;}
static int build_archive(void){char name[128];uint8_t header[44];uint32_t seq=1,offset=0,whole=0xffffffffu;int32_t output=-1,input=-1;int result=-10;if(source_identity()!=0)return -11;if(space(ctx.total+44)!=0)return -12;output=CALL(open_fn,0x0c8bef01u)(ctx.cache_path,0x40e,0600);if(output<0)return -13;ctx.cache_created=1;wav_header(header);if(write_all(output,header,44)!=0)goto end;
 while(offset<ctx.total){uint32_t number_,high,start,size,checksum,rate,count=0,check=0xffffffffu;path(name,"vs-mc-",ctx.record,seq,".meta");if(metadata(name,ctx.meta,"SEALED  ")!=0||!hex(ctx.meta+32,8,&number_)||number_!=seq||!hex(ctx.meta+40,8,&high)||high||!hex(ctx.meta+48,8,&start)||start!=offset||!hex(ctx.meta+56,8,&size)||size!=(ctx.total-offset>65536?65536:ctx.total-offset)||!hex(ctx.meta+64,8,&checksum)||!hex(ctx.meta+72,8,&rate)||rate!=ctx.rate)goto end;path(name,"vs-mc-",ctx.record,seq,".pcm");input=CALL(open_fn,0x0c8bef01u)(name,0x401);if(input<0)goto end;
  while(count<size){uint32_t want=size-count;if(want>sizeof(ctx.buffer))want=sizeof(ctx.buffer);int32_t got=CALL(read_fn,0x0c8beaf1u)(input,ctx.buffer,want);if(got<=0||(uint32_t)got>want||write_all(output,ctx.buffer,(uint32_t)got)!=0)goto end;check=crc_more(check,ctx.buffer,(uint32_t)got);whole=crc_more(whole,ctx.buffer,(uint32_t)got);count+=(uint32_t)got;ctx.prepared=offset+count;if(cancel_requested()){result=-14;goto end;}progress();}
  {uint8_t extra;if(CALL(read_fn,0x0c8beaf1u)(input,&extra,1)!=0||(check^0xffffffffu)!=checksum)goto end;}if(close_owned(input)!=0){input=-1;goto end;}input=-1;offset+=size;seq++;
 }
 if(source_unchanged()!=0||CALL(sync_fn,0x1c159e89u)(output)!=0)goto end;if(close_owned(output)!=0){output=-1;goto end;}output=-1;ctx.pcm_crc=whole^0xffffffffu;if(cache_crc(ctx.pcm_crc)!=0)goto end;return 0;
end:if(input>=0)(void)close_owned(input);if(output>=0)(void)close_owned(output);if(ctx.cache_created&&!ctx.io_uncertain){(void)CALL(unlink_fn,0x0c8befd1u)(ctx.cache_path);ctx.cache_created=0;}return result;}
static void on_event(void *cookie,int32_t event,int32_t result,const char *extra){struct player_context *c=cookie;(void)extra;if(result<0)__atomic_store_n(&c->event_error,result,__ATOMIC_RELEASE);if(event>=1&&event<=6)__atomic_fetch_or(&c->events,1u<<(uint32_t)event,__ATOMIC_RELEASE);}
static int event(uint32_t n){return (__atomic_load_n(&ctx.events,__ATOMIC_ACQUIRE)&(1u<<n))!=0;}
static int media_close(void){int32_t r;if(!ctx.handle)return 0;r=CALL(player_close_fn,0x1c039c1du)(ctx.handle,0);if(r<0)return r;ctx.handle=0;return 0;}
static int wait_event(uint32_t expected,uint32_t phase){uint32_t began=now();ctx.phase=phase;(void)publish();while(now()-began<12000){{int32_t e=__atomic_load_n(&ctx.event_error,__ATOMIC_ACQUIRE);if(e<0)return e;}if(event(expected))return 0;if(cancel_requested())return -125;sleep_ms(50);progress();}return -110;}
static int play(void){uint32_t position_at=0;int32_t r;if(source_identity()!=0||!equal(ctx.archive_hash,ctx.expected_hash,16)||cache_crc(ctx.expected_crc)!=0)return -20;ctx.pcm_crc=ctx.expected_crc;ctx.prepared=ctx.total;ctx.handle=CALL(player_open_fn,0x1c039bbdu)("Music");if(!ctx.handle)return -21;r=CALL(player_event_fn,0x1c039c79u)(ctx.handle,&ctx,on_event);if(r<0)return r;r=CALL(player_prepare_fn,0x1c039cc5u)(ctx.handle,ctx.cache_path,0);if(r<0)return r;if((r=wait_event(1,P_PREPARING))<0)return r;r=CALL(player_handle_fn,0x1c039f51u)(ctx.handle);if(r<0)return r;if((r=wait_event(2,P_PREPARING))<0)return r;ctx.phase=P_PLAYING;(void)publish();
 for(;;){uint32_t seq,current=now();{int32_t e=__atomic_load_n(&ctx.event_error,__ATOMIC_ACQUIRE);if(e<0)return e;}if(event(6)){ctx.position=ctx.duration;return 0;}if(cancel_requested()){ctx.phase=P_STOPPING;(void)publish();(void)CALL(player_handle_fn,0x1c039f79u)(ctx.handle);return 1;}
  if(control("PAUSE   ",&seq)&&seq>ctx.control_sequence&&ctx.phase==P_PLAYING){ctx.control_sequence=seq;__atomic_fetch_and(&ctx.events,~(1u<<3),__ATOMIC_ACQ_REL);r=CALL(player_handle_fn,0x1c039fc1u)(ctx.handle);if(r<0)return r;if((r=wait_event(3,P_PAUSING))<0)return r;ctx.phase=P_PAUSED;(void)publish();}
  else if(control("RESUME  ",&seq)&&seq>ctx.control_sequence&&ctx.phase==P_PAUSED){ctx.control_sequence=seq;__atomic_fetch_and(&ctx.events,~(1u<<2),__ATOMIC_ACQ_REL);r=CALL(player_handle_fn,0x1c039f51u)(ctx.handle);if(r<0)return r;if((r=wait_event(2,P_RESUMING))<0)return r;ctx.phase=P_PLAYING;(void)publish();}
  if((int32_t)(current-position_at)>=0){uint32_t position=0;r=CALL(player_value_fn,0x1c03a07du)(ctx.handle,&position);if(r<0)return r;ctx.position=position>ctx.duration?ctx.duration:position;position_at=current+500;}
  progress();sleep_ms(50);
 }
}
static int32_t worker(int32_t argc,char **argv){int r;uint32_t seq,began;(void)argc;(void)argv;ctx.pid=CALL(pid_fn,0x0c4c96adu)();began=now();ctx.phase=P_INIT;(void)publish();while(!control("GO      ",&seq)||seq!=2){if(cancel_requested()||now()-began>=8000u){ctx.error=-125;ctx.phase=P_ERROR;__atomic_store_n(&ctx.done,1,__ATOMIC_RELEASE);(void)publish();return -1;}sleep_ms(50);}ctx.control_sequence=2;ctx.phase=ctx.mode?P_PREPARING:P_BUILD;(void)publish();r=ctx.mode?play():build_archive();ctx.error=r<0?r:0;if(media_close()<0||ctx.io_uncertain){ctx.error=-30;ctx.phase=P_RETAINED;(void)publish();for(;;)sleep_ms(1000);}ctx.phase=r<0?P_ERROR:ctx.mode?P_DONE:P_READY;__atomic_store_n(&ctx.done,1,__ATOMIC_RELEASE);(void)publish();return 0;}
static int32_t unload(void *unused){(void)unused;if(!__atomic_load_n(&ctx.done,__ATOMIC_ACQUIRE)||ctx.handle||ctx.io_uncertain)return -16;if(ctx.pid>0&&CALL(lookup_fn,0x0c4c5c45u)(ctx.pid))return -16;return 0;}
static int guards(void){uint32_t i;for(i=0;i<sizeof(player_guards)/sizeof(player_guards[0]);i++){uint32_t j,value=2166136261u;const volatile uint8_t *p=(const volatile uint8_t *)(uintptr_t)player_guards[i].address;for(j=0;j<player_guards[i].count;j++)value=(value^p[j])*16777619u;if(value!=player_guards[i].fnv)return 0;}return 1;}
__attribute__((used,noinline,section(".text.watch6_entry")))
int32_t watch6_player_initialize(struct w6r_player_unload *pair){struct spawn_attr attr;uint32_t seq,checksum;int32_t r;if(!pair)return -1;pair->callback=0;pair->context=0;if(!guards())return -2;zero(&ctx,sizeof(ctx));ctx.pid=-1;if(read_exact(BASE "w6r-player-request.txt",ctx.control,512)!=0||!equal(ctx.control,"W6P1REQ\n",8)||!id(ctx.control+8)||!id(ctx.control+24)||!id(ctx.control+88)||!hex(ctx.control+40,8,&seq)||seq!=1||!equal(ctx.control+40,ctx.control+464,8)||!equal(ctx.control+480,ctx.control+8,16)||!equal(ctx.control+496,"W6P1END\n",8)||!hex(ctx.control+472,8,&checksum)||crc(ctx.control,472)!=checksum)return -3;
 copy(ctx.operation,ctx.control+8,16);copy(ctx.record,ctx.control+24,16);copy(ctx.cache,ctx.control+88,16);ctx.mode=equal(ctx.control+48,"PLAY    ",8)?1:0;if(!ctx.mode&&!equal(ctx.control+48,"PREPARE ",8))return -4;if(ctx.mode&&(!hex(ctx.control+104,8,&ctx.expected_crc)||!hex(ctx.control+120,8,&checksum)||!hex(ctx.control+128,8,&checksum)))return -5;if(ctx.mode)copy(ctx.expected_hash,ctx.control+120,16);path(ctx.cache_path,"w6r-play-",ctx.cache,UINT32_MAX,".wav");
 r=CALL(attr_fn,0x0c4fdcc9u)(&attr);if(r!=0)return -6;r=CALL(stack_fn,0x0c4fdd69u)(&attr,12288);if(r!=0)return -7;pair->callback=unload;pair->context=&ctx;ctx.spawned=1;r=CALL(spawn_fn,0x0c4c96f5u)("w6r_player",worker,0,&attr,0,0);if(r<=0){ctx.spawned=0;pair->callback=0;pair->context=0;return -8;}return 0;}
