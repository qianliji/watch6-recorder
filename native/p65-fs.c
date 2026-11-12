/* Fixed P65 filesystem binding, compiled candidate; never invoked by default.
 * Raw PCM extents and 512-byte immutable metadata use only this package prefix.
 * No path or function pointer is read from a request. */
#include "p65-fs.h"
#ifndef VS_DATA_ROOT
#define VS_DATA_ROOT "/data/watch6recorder/"
#endif
#define BASE VS_DATA_ROOT
#ifdef VS_HOST_IO
extern uintptr_t vs_host_io(uint32_t address);
#define CALL(T,A) ((T)vs_host_io(A))
#else
#define CALL(T,A) ((T)(uintptr_t)(A))
#endif
typedef int32_t (*open_fn)(const char *,int32_t,...);
typedef int32_t (*read_fn)(int32_t,void *,uint32_t);
typedef int32_t (*write_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*close_fn)(int32_t);
typedef int32_t (*sync_fn)(int32_t);
typedef int32_t (*unlink_fn)(const char *);
typedef int32_t *(*errno_fn)(void);
#define OPEN_READ 0x401
#define OPEN_NEW 0x40e
static void zero(void *out,uint32_t n){uint8_t *p=out;while(n--)*p++=0;}
static void copy(void *out,const void *in,uint32_t n){uint8_t *a=out;const uint8_t *b=in;while(n--)*a++=*b++;}
static int equal(const void *a,const void *b,uint32_t n){const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;}
static uint32_t len(const char *s){uint32_t n=0;while(s[n])n++;return n;}
static void hex(char *out,uint64_t number,uint32_t digits){while(digits){uint32_t n=(uint32_t)number&15u;out[--digits]=(char)(n<10?'0'+n:'a'+n-10);number>>=4;}}
static int uuid(const char *s){uint32_t n;for(n=0;n<36;n++){char c=s[n];if(n==8||n==13||n==18||n==23){if(c!='-')return 0;}else if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return 0;}return s[36]==0;}
static uint32_t crc_bytes(uint32_t crc,const uint8_t *p,uint32_t n){uint32_t k;while(n--){crc^=*p++;for(k=0;k<8;k++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return crc;}
static int num(const char **p,const char *end,uint32_t *out){uint32_t n=0,count=0;while(*p<end&&(**p==' '||**p=='\t'))(*p)++;while(*p<end&&**p>='0'&&**p<='9'){uint32_t digit=(uint32_t)(*(*p)++-'0');if(n>429496729u||(n==429496729u&&digit>5u))return 0;n=n*10u+digit;count++;}if(!count||*p==end||(**p!=' '&&**p!='\t'))return 0;*out=n;return 1;}
static int parse_data_blocks(const char *text,uint32_t bytes,uint64_t *available,uint32_t *blocksize){
 const char *p=text,*end=text+bytes;uint32_t found=0;
 if(!text||!available||!blocksize||bytes>4096)return -1;
 while(p<end){const char *line=p,*last;uint32_t size,total,used,free;
  while(p<end&&*p!='\n')p++;if(p==end)return -1;last=p++;
  if(!num(&line,last,&size)||!num(&line,last,&total)||!num(&line,last,&used)||!num(&line,last,&free))continue;
  while(line<last&&(*line==' '||*line=='\t'))line++;
  if(last-line!=5||!equal(line,"/data",5))continue;
  if(found||size<512||size>1048576||(size&(size-1))||free>total||used!=total-free)return -1;
  /* Leave four real filesystem allocation blocks for the system, metadata,
   * close ledger and tail. Advertised capacity never enters this arithmetic. */
  *available=(uint64_t)(free>4?free-4:0)*size;*blocksize=size;found=1;
 }
 return found?0:-1;
}
int vs_parse_data_blocks(const char *text,uint32_t bytes,uint64_t *available,uint32_t *blocksize){return parse_data_blocks(text,bytes,available,blocksize);}
static void path(struct vs_p65_fs *fs,const char *suffix,uint32_t seq,char *out){
 uint32_t n=len(BASE),m=len(suffix);copy(out,BASE,n);copy(out+n,"vs-mc-",6);n+=6;copy(out+n,fs->nonce,16);n+=16;out[n++]='-';hex(out+n,seq,8);n+=8;copy(out+n,suffix,m+1);
}
static int write_all(int32_t fd,const uint8_t *p,uint32_t n){uint32_t tries=0;while(n&&tries++<64){int32_t r=CALL(write_fn,0x0c8be041u)(fd,p,n);if(r<=0||(uint32_t)r>n)return -1;p+=r;n-=(uint32_t)r;}return n?-1:0;}
static int read_exact(const char *name,uint8_t *out,uint32_t n){
 int32_t fd=CALL(open_fn,0x0c8bef01u)(name,OPEN_READ);uint32_t got=0,tries=0;int ret=0;if(fd<0)return -1;
 while(got<n&&tries++<64){int32_t r=CALL(read_fn,0x0c8beaf1u)(fd,out+got,n-got);if(r<=0||(uint32_t)r>n-got){ret=-1;break;}got+=(uint32_t)r;}
 if(!ret){uint8_t extra;if(CALL(read_fn,0x0c8beaf1u)(fd,&extra,1)!=0)ret=-1;}
 if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)ret=-1;return ret||got!=n?-1:0;
}
static int close_active(struct vs_p65_fs *fs){int32_t fd=fs->fd;if(fd<0)return 0;fs->fd=-1;if(CALL(close_fn,0x0c8bdba9u)(fd)!=0){fs->uncertain=1;return -1;}return 0;}
static int verify_pcm(struct vs_p65_fs *fs,const struct vs_extent *e){
 uint32_t got=0,crc=0xffffffffu,tries=0;int ret=0;int32_t fd=CALL(open_fn,0x0c8bef01u)(fs->path,OPEN_READ);if(fd<0)return -1;
 while(got<e->bytes&&tries++<160){uint32_t want=e->bytes-got;int32_t n;if(want>VS_RECORD_BYTES)want=VS_RECORD_BYTES;n=CALL(read_fn,0x0c8beaf1u)(fd,fs->verify,want);if(n<=0||(uint32_t)n>want){ret=-1;break;}got+=(uint32_t)n;crc=crc_bytes(crc,fs->verify,(uint32_t)n);}
 if(!ret){uint8_t extra;if(CALL(read_fn,0x0c8beaf1u)(fd,&extra,1)!=0)ret=-1;}
 if(CALL(close_fn,0x0c8bdba9u)(fd)!=0){fs->uncertain=1;ret=-1;}return ret||got!=e->bytes||(crc^0xffffffffu)!=e->crc?-1:0;
}
static int record_new(struct vs_p65_fs *fs,const char *name){
 int32_t fd;int ret=0;hex((char *)fs->record+472,crc_bytes(0xffffffffu,fs->record,472)^0xffffffffu,8);
 fd=CALL(open_fn,0x0c8bef01u)(name,OPEN_NEW,0600);if(fd<0)return -1;
 if(write_all(fd,fs->record,VS_RECORD_BYTES)!=0||CALL(sync_fn,0x1c159e89u)(fd)!=0)ret=-1;
 if(CALL(close_fn,0x0c8bdba9u)(fd)!=0){fs->uncertain=1;ret=-1;}
 if(ret||read_exact(name,fs->verify,VS_RECORD_BYTES)!=0||!equal(fs->record,fs->verify,VS_RECORD_BYTES))return -1;return 0;
}
static void blank_record(struct vs_p65_fs *fs,const char *kind){uint32_t n;for(n=0;n<VS_RECORD_BYTES;n++)fs->record[n]=' ';copy(fs->record,"VSMC1\n",6);copy(fs->record+6,kind,8);copy(fs->record+14,fs->nonce,16);fs->record[30]='\n';copy(fs->record+480,fs->nonce,16);copy(fs->record+496,"\nend=VSMC1\n",11);}
int vs_p65_fs_init(struct vs_p65_fs *fs,const char nonce[17],uint32_t rate){
 uint32_t n;if(!fs||!nonce||(rate!=8000&&rate!=16000))return -1;zero(fs,sizeof(*fs));fs->fd=-1;fs->rate=rate;
 for(n=0;n<16;n++)if(!((nonce[n]>='0'&&nonce[n]<='9')||(nonce[n]>='a'&&nonce[n]<='f')))return -1;if(nonce[16])return -1;copy(fs->nonce,nonce,17);
 /* Persist the source identity BEFORE prepare/start can acquire the mic.
  * O_EXCL also refuses replay of a completed/partial old meeting nonce. */
 blank_record(fs,"SESSION ");hex((char *)fs->record+32,rate,8);path(fs,".session",0,fs->other);return record_new(fs,fs->other);
}
static int refresh_space(struct vs_p65_fs *fs){
 char text[4097];uint32_t n=0,tries=0,size;int32_t fd=CALL(open_fn,0x0c8bef01u)("/proc/fs/blocks",OPEN_READ);int ret=0;if(fd<0)return -1;
 while(n<sizeof(text)&&tries++<64){int32_t r=CALL(read_fn,0x0c8beaf1u)(fd,text+n,sizeof(text)-n);if(r<0||(uint32_t)r>sizeof(text)-n){ret=-1;break;}if(!r)break;n+=(uint32_t)r;}
 if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)ret=-1;if(ret||n==sizeof(text)||parse_data_blocks(text,n,&fs->available,&size)!=0)return -1;fs->space_known=1;fs->allocation_bytes=size;return 0;
}
int vs_p65_fs_space(struct vs_p65_fs *fs,uint32_t bytes,uint32_t reserve){if(fs->uncertain)return 0;if(!fs->space_known&&refresh_space(fs)!=0)return 0;return fs->available>=(uint64_t)bytes+reserve?1:0;}
int vs_p65_fs_open(struct vs_p65_fs *fs,uint32_t seq,uint64_t offset){
 if(fs->fd>=0||fs->uncertain||!seq||(offset&1)||refresh_space(fs)!=0)return -1;
 path(fs,".pcm",seq,fs->path);fs->fd=CALL(open_fn,0x0c8bef01u)(fs->path,OPEN_NEW,0600);if(fs->fd<0)return -1;
 fs->active_seq=seq;fs->active_offset=offset;fs->active_bytes=0;return 0;
}
int vs_p65_fs_append(struct vs_p65_fs *fs,const uint8_t *bytes,uint32_t count){
 if(fs->fd<0||fs->uncertain||!count||(count&1)||count>VS_EXTENT_BYTES-fs->active_bytes)return -1;
 if(write_all(fs->fd,bytes,count)!=0){fs->uncertain=1;(void)close_active(fs);return -1;}
 fs->active_bytes+=count;fs->available=fs->available>count?fs->available-count:0;return 0;
}
int vs_p65_fs_pause_sync(struct vs_p65_fs *fs){if(fs->uncertain)return -1;if(fs->fd<0)return 0;if(CALL(sync_fn,0x1c159e89u)(fs->fd)!=0){fs->uncertain=1;return -1;}return 0;}
int vs_p65_fs_seal(struct vs_p65_fs *fs,const struct vs_extent *e){
 if(fs->uncertain||e->seq!=fs->active_seq||e->offset!=fs->active_offset||e->bytes!=fs->active_bytes||fs->fd<0)return -1;
 if(!e->bytes){if(close_active(fs)!=0)return -1;if(CALL(unlink_fn,0x0c8befd1u)(fs->path)!=0){fs->uncertain=1;return -1;}fs->active_seq=0;return 0;}
 if(CALL(sync_fn,0x1c159e89u)(fs->fd)!=0){fs->uncertain=1;(void)close_active(fs);return -1;}
 if(close_active(fs)!=0)return -1;
 if(verify_pcm(fs,e)!=0){fs->uncertain=1;return -1;}
 blank_record(fs,"SEALED  ");hex((char *)fs->record+32,e->seq,8);hex((char *)fs->record+40,e->offset,16);hex((char *)fs->record+56,e->bytes,8);hex((char *)fs->record+64,e->crc,8);hex((char *)fs->record+72,fs->rate,8);
 path(fs,".meta",e->seq,fs->other);if(record_new(fs,fs->other)!=0){fs->uncertain=1;return -1;}fs->sealed_offset=e->offset+e->bytes;fs->active_seq=0;return 0;
}
static int ledger(struct vs_p65_fs *fs,uint64_t frontier,uint32_t sequence){
 /* A/B generation files are bounded; this generation is O_EXCL. Removing
  * an obsolete ledger is only allowed after the other complete record was
  * synced/read back. Both reference bytes already durable on the phone. */
 uint32_t target=(fs->ledger_generation+1)&1u;int32_t fd;
 path(fs,".ledger",target,fs->other);
 if(fs->ledger_generation>=2){fd=CALL(open_fn,0x0c8bef01u)(fs->other,OPEN_READ);if(fd>=0){if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)return -1;if(CALL(unlink_fn,0x0c8befd1u)(fs->other)!=0)return -1;}else if(*CALL(errno_fn,0x0c4f793du)()!=2)return -1;}
 blank_record(fs,"DURABLE ");copy(fs->record+32,fs->storage_id,36);copy(fs->record+68,fs->epoch,36);hex((char *)fs->record+104,sequence,8);hex((char *)fs->record+112,frontier,16);hex((char *)fs->record+128,fs->ledger_generation+1,8);hex((char *)fs->record+136,fs->last_receipt_frontier,16);
 if(record_new(fs,fs->other)!=0){fs->uncertain=1;return -1;}fs->ledger_generation++;return 0;
}
int vs_p65_fs_bind_phone(struct vs_p65_fs *fs,const char storage[37],const char epoch[37]){
 char prior[37];if(!uuid(storage)||!uuid(epoch)||fs->uncertain)return -1;
 if(fs->storage_id[0]&&!equal(fs->storage_id,storage,36))return -1;
 copy(prior,fs->epoch,37);copy(fs->storage_id,storage,37);copy(fs->epoch,epoch,37);
 if(ledger(fs,fs->phone_durable,0)!=0){copy(fs->epoch,prior,37);return -1;}fs->receipt_sequence=0;fs->last_receipt_frontier=fs->phone_durable;return 0;
}
static int parsehex(const char *p,uint32_t digits,uint64_t *out){uint64_t n=0;uint32_t i;for(i=0;i<digits;i++){uint32_t c=(uint8_t)p[i],v;if(c>='0'&&c<='9')v=c-'0';else if(c>='a'&&c<='f')v=c-'a'+10;else return 0;n=(n<<4)|v;}*out=n;return 1;}
int vs_p65_fs_reclaim(struct vs_p65_fs *fs,const struct vs_extent *e,const char receipt[VS_RECORD_BYTES]){
 uint64_t sequence,frontier,seq,crc,packet_crc;uint64_t end=e->offset+e->bytes;
 if(fs->uncertain||!fs->storage_id[0]||!fs->epoch[0]||!equal(receipt,"VSMR1\n",6)||!equal(receipt+6,fs->nonce,16)||receipt[22]!='\n'||!equal(receipt+24,fs->storage_id,36)||!equal(receipt+60,fs->epoch,36)||!equal(receipt+480,fs->nonce,16)||!equal(receipt+496,"\nend=VSMR1\n",11))return -1;
 if(!parsehex(receipt+96,8,&sequence)||!equal(receipt+96,receipt+464,8)||!parsehex(receipt+472,8,&packet_crc)||(crc_bytes(0xffffffffu,(const uint8_t *)receipt,472)^0xffffffffu)!=packet_crc||!parsehex(receipt+104,16,&frontier)||!parsehex(receipt+120,8,&seq)||!parsehex(receipt+128,8,&crc)||sequence<fs->receipt_sequence||(sequence==fs->receipt_sequence&&frontier!=fs->last_receipt_frontier)||frontier<end||frontier>fs->sealed_offset||(frontier&1)||seq!=e->seq||crc!=e->crc||e->state!=VS_SEALED||e->offset!=fs->phone_durable)return -1;
 /* Read back the immutable descriptor; no caller can authorize deleting a
  * writing range, unknown file, other session or changed extent CRC/size. */
 path(fs,".meta",e->seq,fs->other);if(read_exact(fs->other,fs->verify,VS_RECORD_BYTES)!=0)return -1;
 blank_record(fs,"SEALED  ");hex((char *)fs->record+32,e->seq,8);hex((char *)fs->record+40,e->offset,16);hex((char *)fs->record+56,e->bytes,8);hex((char *)fs->record+64,e->crc,8);hex((char *)fs->record+72,fs->rate,8);hex((char *)fs->record+472,crc_bytes(0xffffffffu,fs->record,472)^0xffffffffu,8);if(!equal(fs->record,fs->verify,VS_RECORD_BYTES))return -1;
 fs->last_receipt_frontier=frontier;if(ledger(fs,end,(uint32_t)sequence)!=0)return -1;
 /* fs->path belongs to the active writer, which may be the NEXT extent.
  * Reclaim is interleaved with capture; never redirect its later seal/readback
  * to the acknowledged old PCM file being removed here. */
 path(fs,".pcm",e->seq,fs->other);if(CALL(unlink_fn,0x0c8befd1u)(fs->other)!=0){fs->uncertain=1;return -1;}
 path(fs,".meta",e->seq,fs->other);if(CALL(unlink_fn,0x0c8befd1u)(fs->other)!=0){fs->uncertain=1;return -1;}
 fs->phone_durable=end;fs->receipt_sequence=(uint32_t)sequence;fs->space_known=0;return 0;
}
int vs_p65_fs_finish(struct vs_p65_fs *fs,uint64_t bytes,int complete,int reason){
 if(fs->uncertain||fs->fd>=0||fs->active_seq)return -1;blank_record(fs,complete?"CLOSED  ":"PARTIAL ");hex((char *)fs->record+32,bytes,16);hex((char *)fs->record+48,(uint32_t)reason,8);hex((char *)fs->record+56,fs->rate,8);path(fs,".end",0,fs->other);return record_new(fs,fs->other);
}
