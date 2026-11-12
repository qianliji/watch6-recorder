/* P65 IO calls are permitted only after phone-link's complete firmware guard.
 * Reuses existing open/read/write/close guards; no new unverified ABI. Reads
 * forward in <=16 KiB bounded batches when resuming, instead of guessing seek. */
#include "export-relay-fs.h"
#include <stddef.h>
#define BASE "/data/watch6recorder/"
#ifdef W6R_EXPORT_FS_HOST
extern uintptr_t w6r_export_host_call(uint32_t);
#define CALL(T,A) ((T)w6r_export_host_call((uint32_t)(A)))
#else
#define CALL(T,A) ((T)(uintptr_t)(A))
#endif
typedef int32_t (*open_fn)(const char *,int32_t,...);
typedef int32_t (*read_fn)(int32_t,void *,uint32_t);
typedef int32_t (*write_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*close_fn)(int32_t);
static void copy(void *a,const void *b,uint32_t n){uint8_t *x=a;const uint8_t *y=b;while(n--)*x++=*y++;}
static int equal(const void *a,const void *b,uint32_t n){const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;}
static void zeros(void *a,uint32_t n){uint8_t *x=a;while(n--)*x++=0;}
static int read_exact(int32_t fd,void *out,uint32_t n){uint32_t count=0,tries=0;while(count<n&&tries++<64){int32_t k=CALL(read_fn,0x0c8beaf1u)(fd,(uint8_t *)out+count,n-count);if(k<=0||(uint32_t)k>n-count)return -1;count+=(uint32_t)k;}return count==n?0:-1;}
static int fixed(const char *path,void *out,uint32_t n){int r;int32_t fd=CALL(open_fn,0x0c8bef01u)(path,1);if(fd<0)return -1;r=read_exact(fd,out,n);if(CALL(close_fn,0x0c8bdba9u)(fd)!=0)r=-1;return r;}
static int put(const char *path,const void *out,uint32_t n){uint32_t pos=0,tries=0;int r=0;int32_t fd=CALL(open_fn,0x0c8bef01u)(path,2);if(fd<0)return -1;while(pos<n&&tries++<64){int32_t k=CALL(write_fn,0x0c8be041u)(fd,(const uint8_t *)out+pos,n-pos);if(k<=0||(uint32_t)k>n-pos){r=-1;break;}pos+=(uint32_t)k;}if(CALL(close_fn,0x0c8bdba9u)(fd)!=0||pos!=n)r=-1;return r;}
static void hex(char *s,uint32_t v,uint32_t n){while(n){uint32_t k=v&15u;s[--n]=(char)(k<10?'0'+k:'a'+k-10);v>>=4;}}
static void header(char *s,const char nonce[17],uint32_t seq,uint32_t len){uint32_t k;for(k=0;k<64;k++)s[k]=' ';copy(s,"VSL1 ",5);copy(s+5,nonce,16);s[21]=' ';hex(s+22,seq,8);s[30]=' ';hex(s+31,len,4);s[35]='\n';}
static int load(void *c,const char nonce[17],uint32_t after,struct w6e_job *j){struct w6e_fs *f=c;if(fixed(BASE "w6r-export-job.txt",f->frame,512)!=0)return 0;if(!w6e_parse_job(f->frame,512,nonce,j))return 0;return j->sequence>after?1:0;}
static int cancel(void *c,const struct w6e_job *j){struct w6e_fs *f=c;char h[64];header(h,j->nonce,j->sequence,0);return fixed(BASE "w6r-export-cancel.txt",f->control,128)==0&&equal(f->control,h,64)&&equal(f->control+64,h,64);}
int w6e_fs_close(void *c){struct w6e_fs *f=c;int32_t fd=f->fd;if(f->uncertain)return -1;f->fd=-1;f->position=0;f->cache[0]=0;if(fd>=0&&CALL(close_fn,0x0c8bdba9u)(fd)!=0){f->uncertain=1;return -1;}return 0;}
static void le32(uint8_t *b,uint32_t v){b[0]=(uint8_t)v;b[1]=(uint8_t)(v>>8);b[2]=(uint8_t)(v>>16);b[3]=(uint8_t)(v>>24);}
static int read_pcm(void *c,const struct w6e_job *j,uint32_t offset,uint8_t *out,uint32_t n){struct w6e_fs *f=c;uint32_t budget=16384u;
 if(f->uncertain||offset>j->total||n>W6E_CHUNK||n>j->total-offset)return -1;
 if(f->fd>=0&&(!equal(f->cache,j->cache_id,17)||offset<f->position))if(w6e_fs_close(f)!=0)return -1;
 if(f->fd<0){char name[64];uint8_t expected[44];copy(name,BASE "w6r-play-",sizeof(BASE "w6r-play-")-1);uint32_t at=sizeof(BASE "w6r-play-")-1;copy(name+at,j->cache_id,16);copy(name+at+16,".wav",5);
  zeros(expected,44);copy(expected,"RIFF",4);le32(expected+4,j->total+36);copy(expected+8,"WAVEfmt ",8);le32(expected+16,16);expected[20]=expected[22]=1;le32(expected+24,j->rate);le32(expected+28,j->rate*2);expected[32]=2;expected[34]=16;copy(expected+36,"data",4);le32(expected+40,j->total);
  f->fd=CALL(open_fn,0x0c8bef01u)(name,1);if(f->fd<0)return -1;copy(f->cache,j->cache_id,17);f->position=0;
  if(read_exact(f->fd,f->scratch,44)!=0||!equal(f->scratch,expected,44)){(void)w6e_fs_close(f);return -1;}}
 while(f->position<offset&&budget){uint32_t want=offset-f->position;if(want>sizeof(f->scratch))want=sizeof(f->scratch);if(want>budget)want=budget;if(read_exact(f->fd,f->scratch,want)!=0){(void)w6e_fs_close(f);return -1;}f->position+=want;budget-=want;}
 if(f->position<offset)return 0;
 if(read_exact(f->fd,out,n)!=0){(void)w6e_fs_close(f);return -1;}f->position+=n;
 if(f->position==j->total){uint8_t extra;int32_t r=CALL(read_fn,0x0c8beaf1u)(f->fd,&extra,1);if(r!=0){(void)w6e_fs_close(f);return -1;}}
 return (int)n;
}
static void add(char *s,uint32_t *n,const char *v){while(*v&&*n<384)s[(*n)++]=*v++;}
static void decimal(char *s,uint32_t *n,uint32_t v){char d[10];uint32_t k=0;do{d[k++]=(char)('0'+v%10);v/=10;}while(v);while(k&&*n<384)s[(*n)++]=d[--k];}
static int publish(void *c,const struct w6e_status *s){struct w6e_fs *f=c;uint32_t i,n=64;for(i=0;i<512;i++)f->frame[i]=' ';add(f->frame,&n,"{\"phase\":\"");add(f->frame,&n,w6e_phase(s->phase));add(f->frame,&n,"\",\"next\":");decimal(f->frame,&n,s->next);add(f->frame,&n,",\"total_bytes\":");decimal(f->frame,&n,s->total);add(f->frame,&n,",\"job_sequence\":");decimal(f->frame,&n,s->sequence);add(f->frame,&n,",\"recording_id\":\"");add(f->frame,&n,s->recording_id);add(f->frame,&n,"\",\"code\":");if(s->code<0){add(f->frame,&n,"-");decimal(f->frame,&n,0u-(uint32_t)s->code);}else decimal(f->frame,&n,(uint32_t)s->code);add(f->frame,&n,",\"pid\":");decimal(f->frame,&n,s->pid);add(f->frame,&n,",\"source_closed\":");add(f->frame,&n,s->source_closed?"true":"false");add(f->frame,&n,",\"worker_done\":");add(f->frame,&n,s->worker_done?"true":"false");add(f->frame,&n,"}");header(f->frame,f->nonce,++f->generation,n-64);copy(f->frame+448,f->frame,64);return put(BASE "w6r-export-status.txt",f->frame,512);}
void w6e_fs_init(struct w6e_fs *f,const char nonce[17]){zeros(f,sizeof(*f));f->fd=-1;copy(f->nonce,nonce,17);}
void w6e_fs_ops(struct w6e_fs *f,struct w6e_io *io){zeros(io,sizeof(*io));io->context=f;io->load=load;io->cancel=cancel;io->read=read_pcm;io->close=w6e_fs_close;io->publish=publish;}
