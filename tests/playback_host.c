/* Actual player/archive C compiled for ARM; synthetic RAM files and media RPC.
 * No operating-system or firmware instruction is executed by this harness. */
#define W6R_PLAYER_HOST 1
#include <stdarg.h>
#include "../native/player.c"
#define FILES 20
#define FILE_BYTES 140000
struct mem_file {char name[128];uint8_t bytes[FILE_BYTES];uint32_t size,used;};
struct descriptor {uint32_t file,pos,used;};
static struct mem_file files[FILES];static struct descriptor fds[16];
uint32_t host_cases,host_assertions,host_failures,host_line;
uint32_t host_permission_mode,host_permission_result;
static uint32_t clock_ms,short_reads,short_writes,fail_sync,fail_close,play_case,opens,starts,pauses,stops,closes;
static uint32_t enforce_cache_permissions,cache_mode;
static event_fn callback;static void *event_cookie;static uint32_t media_position;
#define CHECK(v) do{host_assertions++;if(!(v)){host_failures++;host_line=__LINE__;}}while(0)
static int same(const char *a,const char *b){return length(a)==length(b)&&equal(a,b,length(a));}
static int find_file(const char *name){uint32_t i;for(i=0;i<FILES;i++)if(files[i].used&&same(name,files[i].name))return (int)i;return -1;}
static int add_file(const char *name,const uint8_t *data,uint32_t size){uint32_t i;int existing=find_file(name);if(existing>=0)i=(uint32_t)existing;else for(i=0;i<FILES&&files[i].used;i++);if(i==FILES||size>FILE_BYTES)return -1;files[i].used=1;copy(files[i].name,name,length(name)+1);if(size&&data)copy(files[i].bytes,data,size);files[i].size=size;return (int)i;}
static int32_t m_open(const char *name,int32_t flags,...){int i=find_file(name);uint32_t d;if(flags==0x40e){va_list ap;va_start(ap,flags);cache_mode=va_arg(ap,unsigned int);va_end(ap);if(i>=0)return -17;i=add_file(name,0,0);}else if(enforce_cache_permissions&&same(name,ctx.cache_path)&&!(cache_mode&0400u))return -13;if(i<0)return -2;for(d=0;d<16&&fds[d].used;d++);if(d==16)return -24;fds[d].used=1;fds[d].file=(uint32_t)i;fds[d].pos=0;return (int32_t)d+3;}
static int32_t m_read(int32_t fd,void *out,uint32_t n){struct descriptor *d;struct mem_file *f;uint32_t got;if(fd<3||fd>=19)return -9;d=fds+fd-3;if(!d->used)return -9;f=files+d->file;got=f->size-d->pos;if(got>n)got=n;if(short_reads&&got>short_reads)got=short_reads;copy(out,f->bytes+d->pos,got);d->pos+=got;return (int32_t)got;}
static int32_t m_write(int32_t fd,const void *in,uint32_t n){struct descriptor *d;struct mem_file *f;if(fd<3||fd>=19)return -9;d=fds+fd-3;if(!d->used)return -9;f=files+d->file;if(short_writes&&n>short_writes)n=short_writes;if(d->pos+n>FILE_BYTES)return -28;copy(f->bytes+d->pos,in,n);d->pos+=n;if(d->pos>f->size)f->size=d->pos;return (int32_t)n;}
static int32_t m_close(int32_t fd){if(fd<3||fd>=19||!fds[fd-3].used)return -9;if(fail_close){fail_close--;return -5;}fds[fd-3].used=0;return 0;}
static int32_t m_sync(int32_t fd){(void)fd;return fail_sync?-5:0;}
static int32_t m_unlink(const char *name){int i=find_file(name);if(i<0)return -2;files[i].used=0;return 0;}
static uint64_t m_clock(void){return (uint64_t)clock_ms*10;}
static void control_frame(const char *kind,uint32_t seq){uint8_t raw[512];uint32_t i;for(i=0;i<512;i++)raw[i]=' ';copy(raw,"W6P1REQ\n",8);copy(raw+8,ctx.operation,16);copy(raw+24,ctx.record,16);hex8((char *)raw+40,seq);copy(raw+48,kind,8);copy(raw+88,ctx.cache,16);hex8((char *)raw+104,ctx.expected_crc);copy(raw+464,raw+40,8);hex8((char *)raw+472,crc(raw,472));copy(raw+480,ctx.operation,16);copy(raw+496,"W6P1END\n",8);add_file(BASE "w6r-player-control.txt",raw,512);}
static int32_t m_sleep(uint32_t us){clock_ms+=us/1000;if(play_case==1&&ctx.phase==P_PAUSED)control_frame("RESUME  ",4);return 0;}
static int32_t m_pid(void){return 42;}
static void *m_lookup(int32_t pid){(void)pid;return 0;}
static void *m_player_open(const char *stream){CHECK(same(stream,"Music"));opens++;return (void *)0x1234;}
static int32_t m_player_close(void *h,int32_t pending){CHECK(h==(void *)0x1234&&pending==0);closes++;return play_case==4?-5:0;}
static int32_t m_set_event(void *h,void *cookie,event_fn fn){CHECK(h==(void *)0x1234);event_cookie=cookie;callback=fn;return 0;}
static int32_t m_prepare(void *h,const char *name,const char *options){CHECK(h==(void *)0x1234&&same(name,ctx.cache_path)&&options==0);if(play_case!=3)callback(event_cookie,1,0,0);return 0;}
static int32_t m_start(void *h){CHECK(h==(void *)0x1234);starts++;callback(event_cookie,2,0,0);return 0;}
static int32_t m_pause(void *h){CHECK(h==(void *)0x1234);pauses++;callback(event_cookie,3,0,0);return 0;}
static int32_t m_stop(void *h){CHECK(h==(void *)0x1234);stops++;callback(event_cookie,4,0,0);return 0;}
static int32_t m_position(void *h,uint32_t *out){CHECK(h==(void *)0x1234);media_position+=250;*out=media_position;if(play_case==1&&media_position==250)control_frame("PAUSE   ",3);else if(play_case==2&&media_position>=250)control_frame("STOP    ",3);if(media_position>=1000)callback(event_cookie,6,0,0);return 0;}
uintptr_t w6r_player_host_call(uint32_t address){
 switch(address){
 case 0x0c8bef01u:return (uintptr_t)m_open;case 0x0c8beaf1u:return (uintptr_t)m_read;
 case 0x0c8be041u:return (uintptr_t)m_write;case 0x0c8bdba9u:return (uintptr_t)m_close;
 case 0x1c159e89u:return (uintptr_t)m_sync;case 0x0c8befd1u:return (uintptr_t)m_unlink;
 case 0x0c4c1e45u:return (uintptr_t)m_clock;case 0x0c4c8b39u:return (uintptr_t)m_sleep;
 case 0x0c4c96adu:return (uintptr_t)m_pid;case 0x0c4c5c45u:return (uintptr_t)m_lookup;
 case 0x1c039bbdu:return (uintptr_t)m_player_open;case 0x1c039c1du:return (uintptr_t)m_player_close;
 case 0x1c039c79u:return (uintptr_t)m_set_event;case 0x1c039cc5u:return (uintptr_t)m_prepare;
 case 0x1c039f51u:return (uintptr_t)m_start;case 0x1c039fc1u:return (uintptr_t)m_pause;
 case 0x1c039f79u:return (uintptr_t)m_stop;case 0x1c03a07du:return (uintptr_t)m_position;
 default:CHECK(0);return 0;}
}
static void metadata_fixture(uint8_t *raw,const char *kind){uint32_t i;for(i=0;i<512;i++)raw[i]=' ';copy(raw,"VSMC1\n",6);copy(raw+6,kind,8);copy(raw+14,ctx.record,16);raw[30]='\n';copy(raw+480,ctx.record,16);copy(raw+496,"\nend=VSMC1\n",11);}
static void checksum_fixture(uint8_t *raw){hex8((char *)raw+472,crc(raw,472));}
static void fixture(uint32_t total){char name[128];uint32_t offset=0,seq=1,i;uint8_t raw[512];
 zero(files,sizeof(files));zero(fds,sizeof(fds));zero(&ctx,sizeof(ctx));clock_ms=short_reads=short_writes=fail_sync=fail_close=play_case=opens=starts=pauses=stops=closes=media_position=0;callback=0;event_cookie=0;
 enforce_cache_permissions=cache_mode=0;
 copy(ctx.operation,"fedcba9876543210",17);copy(ctx.record,"1234567890abcdef",17);copy(ctx.cache,ctx.operation,17);path(ctx.cache_path,"w6r-play-",ctx.cache,UINT32_MAX,".wav");
 metadata_fixture(raw,"SESSION ");hex8((char *)raw+32,8000);checksum_fixture(raw);path(name,"vs-mc-",ctx.record,0,".session");add_file(name,raw,512);
 metadata_fixture(raw,"CLOSED  ");hex8((char *)raw+32,0);hex8((char *)raw+40,total);hex8((char *)raw+48,1);hex8((char *)raw+56,8000);checksum_fixture(raw);path(name,"vs-mc-",ctx.record,0,".end");add_file(name,raw,512);
 while(offset<total){uint32_t size=total-offset;if(size>65536)size=65536;path(name,"vs-mc-",ctx.record,seq,".pcm");i=(uint32_t)add_file(name,0,size);for(uint32_t j=0;j<size;j++)files[i].bytes[j]=(uint8_t)((offset+j)*31+3);
  metadata_fixture(raw,"SEALED  ");hex8((char *)raw+32,seq);hex8((char *)raw+40,0);hex8((char *)raw+48,offset);hex8((char *)raw+56,size);hex8((char *)raw+64,crc(files[i].bytes,size));hex8((char *)raw+72,8000);checksum_fixture(raw);path(name,"vs-mc-",ctx.record,seq,".meta");add_file(name,raw,512);offset+=size;seq++;
 }
 {static const uint8_t blocks[]="Size Blocks Used Free Mounted on\n4096 10000 100 9900 /data\n";add_file("/proc/fs/blocks",blocks,sizeof(blocks)-1);}
 add_file(BASE "w6r-player-status.txt",0,1536);control_frame("GO      ",2);ctx.control_sequence=2;
}
static int named(uint32_t seq,const char *suffix){char name[128];path(name,"vs-mc-",ctx.record,seq,suffix);return find_file(name);}
int run_suite(void){int f,r;uint32_t checksum;
 fixture(16000);enforce_cache_permissions=1;r=build_archive();host_permission_result=(uint32_t)r;host_permission_mode=cache_mode;CHECK(r==0);CHECK(cache_mode==0600u);CHECK(find_file(BASE "vs-mc-1234567890abcdef-00000001.pcm")>=0);host_cases++;
 fixture(66336);CHECK(build_archive()==0);f=find_file(ctx.cache_path);CHECK(f>=0&&files[f].size==66380);CHECK(equal(files[f].bytes,"RIFF",4)&&equal(files[f].bytes+36,"data",4));CHECK(ctx.prepared==66336&&ctx.pcm_crc==crc(files[f].bytes+44,66336));CHECK(source_unchanged()==0);host_cases++;
 fixture(16000);files[named(1,".pcm")].bytes[123]^=1;CHECK(build_archive()!=0&&find_file(ctx.cache_path)<0);CHECK(find_file(BASE "vs-mc-1234567890abcdef-00000001.pcm")>=0);host_cases++;
 fixture(16000);files[named(1,".pcm")].size++;CHECK(build_archive()!=0&&find_file(ctx.cache_path)<0);host_cases++;
 fixture(16000);f=named(0,".end");copy(files[f].bytes+6,"PARTIAL ",8);checksum_fixture(files[f].bytes);CHECK(build_archive()!=0&&find_file(ctx.cache_path)<0);host_cases++;
 fixture(66336);files[named(2,".meta")].used=0;CHECK(build_archive()!=0);host_cases++;
 fixture(16000);f=named(1,".meta");hex8((char *)files[f].bytes+48,2);checksum_fixture(files[f].bytes);CHECK(build_archive()!=0);host_cases++;
 fixture(16000);f=named(1,".meta");files[f].bytes[100]^=1;CHECK(build_archive()!=0);host_cases++;
 fixture(16000);short_reads=7;short_writes=73;CHECK(build_archive()==0);CHECK(cache_crc(ctx.pcm_crc)==0);host_cases++;
 fixture(16000);fail_sync=1;CHECK(build_archive()!=0&&find_file(ctx.cache_path)<0);host_cases++;
 fixture(16000);add_file(ctx.cache_path,(const uint8_t *)"old",3);CHECK(build_archive()!=0);f=find_file(ctx.cache_path);CHECK(f>=0&&files[f].size==3&&equal(files[f].bytes,"old",3));host_cases++;
 fixture(16000);control_frame("STOP    ",3);CHECK(build_archive()!=0&&find_file(ctx.cache_path)<0);host_cases++;
 fixture(16000);{static const uint8_t low[]="4096 100 99 1 /data\n";add_file("/proc/fs/blocks",low,sizeof(low)-1);}CHECK(build_archive()!=0&&find_file(ctx.cache_path)<0);host_cases++;
 fixture(16000);CHECK(build_archive()==0);checksum=ctx.pcm_crc;f=find_file(ctx.cache_path);files[f].bytes[44]^=1;CHECK(cache_crc(checksum)!=0);host_cases++;
 fixture(16000);CHECK(build_archive()==0);ctx.expected_crc=ctx.pcm_crc;copy(ctx.expected_hash,ctx.archive_hash,17);play_case=1;CHECK(play()==0);CHECK(starts==2&&pauses==1&&opens==1&&media_position>=1000);CHECK(media_close()==0&&closes==1&&ctx.handle==0);host_cases++;
 fixture(16000);CHECK(build_archive()==0);ctx.expected_crc=ctx.pcm_crc;copy(ctx.expected_hash,ctx.archive_hash,17);play_case=2;CHECK(play()==1&&stops==1);CHECK(media_close()==0&&ctx.handle==0);host_cases++;
 fixture(16000);CHECK(build_archive()==0);ctx.expected_crc=ctx.pcm_crc;copy(ctx.expected_hash,ctx.archive_hash,17);play_case=3;r=play();CHECK(r==-110&&clock_ms>=12000&&starts==0);CHECK(media_close()==0);host_cases++;
 fixture(16000);CHECK(build_archive()==0);ctx.expected_crc=ctx.pcm_crc;copy(ctx.expected_hash,ctx.archive_hash,17);play_case=4;CHECK(play()==0);CHECK(media_close()<0&&ctx.handle!=0);ctx.done=1;CHECK(unload(0)==-16);host_cases++;
 fixture(16000);fail_close=1;CHECK(build_archive()!=0&&ctx.io_uncertain==1);ctx.done=1;CHECK(unload(0)==-16);host_cases++;
 fixture(16000);f=named(0,".end");hex8((char *)files[f].bytes+56,30000);checksum_fixture(files[f].bytes);CHECK(worker(0,0)==0&&ctx.done&&ctx.phase==P_ERROR&&ctx.total==0&&ctx.rate==0);CHECK(unload(0)==0);host_cases++;
 fixture(16000);CHECK(worker(0,0)==0&&ctx.done&&ctx.phase==P_READY&&opens==0);CHECK(unload(0)==0);host_cases++;
 fixture(16000);files[find_file(BASE "w6r-player-control.txt")].used=0;CHECK(worker(0,0)<0&&ctx.done&&ctx.error==-125&&clock_ms>=8000);CHECK(opens==0&&find_file(ctx.cache_path)<0);host_cases++;
 return (int)host_failures;
}
