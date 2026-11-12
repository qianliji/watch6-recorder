/* Real p65-fs.c with synthetic C I/O implementations, no firmware address call. */
#include "p65-fs.h"
#include <stdarg.h>
extern uint32_t host_cases,host_assertions,host_failures;
#define CHECK(x) do{host_assertions++;if(!(x))host_failures++;}while(0)
struct file {char name[160];uint8_t bytes[65536];uint32_t size,present;};
struct descriptor {uint32_t opened,file,offset;};
static struct file files[12];static struct descriptor fds[16];static struct vs_p65_fs fs;
static uint32_t syncs,unlinks,fail_sync,fail_write,corrupt_read;static int32_t error;
static const char nonce[]="0123456789abcdef",storage[]="12345678-1234-1234-1234-123456789abc",epoch[]="abcdefab-1234-1234-1234-123456789abc";
static void zero(void *p,uint32_t n){uint8_t *b=p;while(n--)*b++=0;}
static int same(const char *a,const char *b){while(*a&&*b){if(*a++!=*b++)return 0;}return *a==*b;}
static void copy(void *a,const void *b,uint32_t n){uint8_t *x=a;const uint8_t *y=b;while(n--)*x++=*y++;}
static void text(char *a,const char *b){while((*a++=*b++));}
static uint32_t length(const char *s){uint32_t n=0;while(s[n])n++;return n;}
static void hex(char *p,uint64_t v,uint32_t n){while(n){uint32_t d=(uint32_t)v&15; p[--n]=(char)(d<10?'0'+d:'a'+d-10);v>>=4;}}
static uint32_t crc(const uint8_t *p,uint32_t n){uint32_t c=0xffffffffu,k;while(n--){c^=*p++;for(k=0;k<8;k++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return c^0xffffffffu;}
static int32_t op(const char *name,int32_t flags,...){uint32_t i,j,empty=12;for(i=0;i<12;i++){if(files[i].present&&same(files[i].name,name))break;if(!files[i].present&&empty==12)empty=i;}if(i<12&&(flags&8)){error=17;return -1;}if(i==12){if(!(flags&4)||empty==12){error=2;return -1;}i=empty;zero(&files[i],sizeof(files[i]));files[i].present=1;text(files[i].name,name);}for(j=0;j<16;j++)if(!fds[j].opened){fds[j].opened=1;fds[j].file=i;fds[j].offset=0;return (int32_t)j;}error=24;return -1;}
static int32_t rd(int32_t fd,void *out,uint32_t count){struct descriptor *d;struct file *f;if(fd<0||fd>=16||!fds[fd].opened)return -1;d=&fds[fd];f=&files[d->file];if(count>f->size-d->offset)count=f->size-d->offset;copy(out,f->bytes+d->offset,count);if(corrupt_read&&count&&f->size>512)((uint8_t*)out)[0]^=1;d->offset+=count;return (int32_t)count;}
static int32_t wr(int32_t fd,const void *in,uint32_t n){struct descriptor *d;struct file *f;if(fail_write||fd<0||fd>=16||!fds[fd].opened)return -1;d=&fds[fd];f=&files[d->file];if(n>sizeof(f->bytes)-d->offset)return -1;copy(f->bytes+d->offset,in,n);d->offset+=n;if(d->offset>f->size)f->size=d->offset;return (int32_t)n;}
static int32_t cl(int32_t fd){if(fd<0||fd>=16||!fds[fd].opened)return -1;fds[fd].opened=0;return 0;}
static int32_t sy(int32_t fd){if(fd<0||fd>=16||!fds[fd].opened)return -1;syncs++;return fail_sync?-1:0;}
static int32_t un(const char *name){uint32_t i;for(i=0;i<12;i++)if(files[i].present&&same(files[i].name,name)){files[i].present=0;unlinks++;return 0;}error=2;return -1;}
static int32_t *er(void){return &error;}
uintptr_t vs_host_io(uint32_t address){switch(address){case 0x0c8bef01:return (uintptr_t)op;case 0x0c8beaf1:return (uintptr_t)rd;case 0x0c8be041:return (uintptr_t)wr;case 0x0c8bdba9:return (uintptr_t)cl;case 0x1c159e89:return (uintptr_t)sy;case 0x0c8befd1:return (uintptr_t)un;case 0x0c4f793d:return (uintptr_t)er;default:host_failures++;return 0;}}
static void reset(void){static const char blocks[]="  Block    Number\n  Size     Blocks       Used   Available Mounted on\n131072 1024 100 924 /data\n";zero(files,sizeof(files));zero(fds,sizeof(fds));syncs=unlinks=fail_sync=fail_write=corrupt_read=0;error=0;files[0].present=1;text(files[0].name,"/proc/fs/blocks");copy(files[0].bytes,blocks,sizeof(blocks)-1);files[0].size=sizeof(blocks)-1;CHECK(vs_p65_fs_init(&fs,nonce,8000)==0);}
static uint32_t handles(void){uint32_t i,n=0;for(i=0;i<16;i++)n+=fds[i].opened;return n;}
static void extent(struct vs_extent *e,uint32_t seq,uint64_t offset){static uint8_t pcm[1024];uint32_t i;for(i=0;i<sizeof(pcm);i++)pcm[i]=(uint8_t)i;zero(e,sizeof(*e));e->seq=seq;e->offset=offset;e->bytes=sizeof(pcm);e->crc=crc(pcm,sizeof(pcm));e->state=VS_SEALED;CHECK(vs_p65_fs_open(&fs,seq,offset)==0);CHECK(vs_p65_fs_append(&fs,pcm,sizeof(pcm))==0);}
static void receipt(char *out,const struct vs_extent *e,uint32_t sequence,uint64_t frontier){uint32_t i;for(i=0;i<512;i++)out[i]=' ';copy(out,"VSMR1\n",6);copy(out+6,nonce,16);out[22]='\n';copy(out+24,storage,36);copy(out+60,epoch,36);hex(out+96,sequence,8);hex(out+104,frontier,16);hex(out+120,e->seq,8);hex(out+128,e->crc,8);copy(out+480,nonce,16);copy(out+496,"\nend=VSMR1\n",11);hex(out+464,sequence,8);hex(out+472,crc((const uint8_t *)out,472),8);}
static void test_parse(void){uint64_t free;uint32_t size;const char *good="512 100 10 90 /data\n";CHECK(vs_parse_data_blocks(good,length(good),&free,&size)==0&&free==86*512&&size==512);good="512 100 10 90 /data\n512 100 10 90 /data\n";CHECK(vs_parse_data_blocks(good,length(good),&free,&size)<0);good="512 100 1 90 /data\n";CHECK(vs_parse_data_blocks(good,length(good),&free,&size)<0);good="512 100 10 90 /data";CHECK(vs_parse_data_blocks(good,length(good),&free,&size)<0);host_cases++;}
static void test_empty(void){struct vs_extent e;reset();zero(&e,sizeof(e));e.seq=1;CHECK(vs_p65_fs_open(&fs,1,0)==0);CHECK(vs_p65_fs_seal(&fs,&e)==0);CHECK(!handles()&&unlinks==1&&fs.active_seq==0);host_cases++;}
static void test_seal(void){struct vs_extent e;reset();extent(&e,1,0);CHECK(vs_p65_fs_seal(&fs,&e)==0);CHECK(syncs==3&&!handles()&&fs.sealed_offset==1024);host_cases++;}
static void test_forged(void){struct vs_extent e;char proof[512];reset();extent(&e,1,0);CHECK(vs_p65_fs_seal(&fs,&e)==0);CHECK(vs_p65_fs_bind_phone(&fs,storage,epoch)==0);receipt(proof,&e,1,1024);proof[24]='9';CHECK(vs_p65_fs_reclaim(&fs,&e,proof)<0&&unlinks==0);proof[24]=storage[0];proof[60]='9';CHECK(vs_p65_fs_reclaim(&fs,&e,proof)<0&&unlinks==0);receipt(proof,&e,1,2048);CHECK(vs_p65_fs_reclaim(&fs,&e,proof)<0&&unlinks==0);host_cases++;}
static void test_cumulative(void){struct vs_extent a,b;char proof[512];reset();extent(&a,1,0);CHECK(vs_p65_fs_seal(&fs,&a)==0);extent(&b,2,1024);CHECK(vs_p65_fs_seal(&fs,&b)==0);CHECK(vs_p65_fs_bind_phone(&fs,storage,epoch)==0);receipt(proof,&a,7,2048);CHECK(vs_p65_fs_reclaim(&fs,&a,proof)==0);receipt(proof,&b,7,2048);CHECK(vs_p65_fs_reclaim(&fs,&b,proof)==0);CHECK(fs.phone_durable==2048&&unlinks>=4&&!handles());host_cases++;}
static void test_sync_failure(void){struct vs_extent e;char proof[512];reset();extent(&e,1,0);CHECK(vs_p65_fs_seal(&fs,&e)==0);CHECK(vs_p65_fs_bind_phone(&fs,storage,epoch)==0);receipt(proof,&e,1,1024);fail_sync=1;CHECK(vs_p65_fs_reclaim(&fs,&e,proof)<0&&unlinks==0&&fs.phone_durable==0&&fs.uncertain);CHECK(!handles());host_cases++;}
static void test_corruption(void){struct vs_extent e;reset();extent(&e,1,0);corrupt_read=1;CHECK(vs_p65_fs_seal(&fs,&e)<0&&fs.sealed_offset==0&&fs.uncertain&&!handles());host_cases++;}
/* Real capture/FS composition: phone reclaims the first sealed file while
 * capture has already opened the next one. Separate spool-only and FS-only
 * closed-file tests cannot exercise this production call ordering. */
static struct vs_owner active_owner;
static uint32_t source_read,source_total,source_stopped,source_closed;
uint32_t host_active_reclaim_phase,host_active_reclaim_error;
static int capture_prepare(void *p,const char *id){(void)p;(void)id;return 0;}
static int capture_ready(void *p){(void)p;return 1;}
static int capture_start(void *p){(void)p;return 0;}
static int capture_read(void *p,uint8_t *out,uint32_t amount){uint32_t i;(void)p;if(source_read>=source_total)return source_stopped?VS_RX_EOF:VS_RX_AGAIN;if(amount>source_total-source_read)amount=source_total-source_read;for(i=0;i<amount;i++)out[i]=(uint8_t)(source_read+i);source_read+=amount;return (int)amount;}
static int capture_stop(void *p){(void)p;source_stopped=1;return 0;}
static int capture_stopped(void *p){(void)p;return source_stopped;}
static int capture_close(void *p){(void)p;source_closed++;return 0;}
static int actual_space(void *p,uint32_t n,uint32_t reserve){return vs_p65_fs_space(p,n,reserve);}
static int actual_open(void *p,uint32_t seq,uint64_t offset){return vs_p65_fs_open(p,seq,offset);}
static int actual_append(void *p,const uint8_t *bytes,uint32_t n){return vs_p65_fs_append(p,bytes,n);}
static int actual_seal(void *p,const struct vs_extent *e){return vs_p65_fs_seal(p,e);}
static int actual_reclaim(void *p,const struct vs_extent *e,const char *proof){return vs_p65_fs_reclaim(p,e,proof);}
static int actual_finish(void *p,uint64_t n,int complete,int reason){return vs_p65_fs_finish(p,n,complete,reason);}
static void test_active_reclaim(void){
 uint32_t now=0,sequence=0;char proof[512],active_path[160];
 struct vs_ops ops={VS_CAP_ALL,&fs,capture_prepare,capture_ready,capture_start,capture_read,capture_stop,capture_stopped,capture_close,actual_space,actual_open,actual_append,actual_seal,actual_reclaim,actual_finish};
 reset();source_read=source_stopped=source_closed=0;source_total=3*65536+1234;
 CHECK(vs_p65_fs_bind_phone(&fs,storage,epoch)==0);
 CHECK(vs_owner_init(&active_owner,&ops,nonce,8000,4,0)==0);
 for(now=25;now<1000&&active_owner.produced<source_total;now+=25){
  (void)vs_owner_step(&active_owner,now);
  while(active_owner.count&&active_owner.extents[active_owner.head].state==VS_SEALED){
   struct vs_extent *e=&active_owner.extents[active_owner.head];int had_active=fs.fd>=0;text(active_path,fs.path);
   receipt(proof,e,++sequence,e->offset+e->bytes);
   CHECK(vs_owner_ack(&active_owner,nonce,e->seq,e->offset+e->bytes,e->crc,proof)==0);
   CHECK(!had_active||same(active_path,fs.path));
  }
  if(active_owner.phase==VS_RETAINED)break;
 }
 host_active_reclaim_phase=active_owner.phase;host_active_reclaim_error=active_owner.error;
 CHECK(active_owner.produced==source_total&&active_owner.error==0&&active_owner.phase==VS_RECORDING);
 vs_owner_stop(&active_owner,VS_REASON_USER,now);(void)vs_owner_step(&active_owner,now+25);
 CHECK(active_owner.phase==VS_CLOSED&&active_owner.complete&&source_closed==1&&active_owner.durable==source_total&&!fs.uncertain);
 CHECK(!handles());host_cases++;
}
void host_fs_all(void){test_parse();test_empty();test_seal();test_forged();test_cumulative();test_sync_failure();test_corruption();test_active_reclaim();}
