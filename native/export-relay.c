#include "export-relay.h"
#include "export-relay-json.h"
static void zero(void *p,uint32_t n){uint8_t *b=p;while(n--)*b++=0;}
static void copy(void *d,const void *s,uint32_t n){uint8_t *a=d;const uint8_t *b=s;while(n--)*a++=*b++;}
static int equal(const void *a,const void *b,uint32_t n){const uint8_t *x=a,*y=b;while(n--)if(*x++!=*y++)return 0;return 1;}
static int hex(const char *s,uint32_t n,uint32_t *value){uint32_t v=0,i;for(i=0;i<n;i++){uint32_t c=(uint8_t)s[i];if(c>='0'&&c<='9')c-='0';else if(c>='a'&&c<='f')c=c-'a'+10;else return 0;v=(v<<4)|c;}if(value)*value=v;return 1;}
static void hexout(char *s,uint32_t v,uint32_t n){while(n){uint32_t x=v&15u;s[--n]=(char)(x<10?'0'+x:'a'+x-10);v>>=4;}}
uint32_t w6e_crc32(const void *p,uint32_t n){const uint8_t *b=p;uint32_t c=0xffffffffu,k;while(n--){c^=*b++;for(k=0;k<8;k++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return c^0xffffffffu;}
/* Every variable field is authenticated by the record CRC and repeated nonce /
 * sequence. Reserved bytes must be spaces, so newer layouts fail closed. */
int w6e_parse_job(const char *b,uint32_t n,const char nonce[17],struct w6e_job *j){uint32_t seq,check,total,rate,i;
 if(n!=512||!equal(b,"W6RE1\n",6)||!equal(b+6,nonce,16)||b[22]!='\n'||b[23]!=' '||!equal(b+480,nonce,16)||!equal(b+496,"\nend=W6RE1\n",11))return 0;
 if(!hex(b+24,16,0)||!hex(b+40,8,&rate)||!hex(b+48,8,&total)||!hex(b+56,16,0)||!hex(b+72,8,0)||!hex(b+80,16,0)||!hex(b+96,8,&seq)||!seq||!equal(b+104,"00000001",8)||!equal(b+96,b+464,8)||!hex(b+472,8,&check)||w6e_crc32(b,472)!=check)return 0;
 for(i=112;i<464;i++)if(b[i]!=' ')return 0;for(i=507;i<512;i++)if(b[i]!=' ')return 0;
 if((rate!=8000&&rate!=16000)||!total||(total&1u)||total>W6E_LIMIT)return 0;
 zero(j,sizeof(*j));copy(j->nonce,nonce,16);copy(j->recording_id,b+24,16);copy(j->archive_hash,b+56,16);copy(j->pcm_crc32,b+72,8);copy(j->cache_id,b+80,16);j->rate=rate;j->total=total;j->sequence=seq;return 1;
}
const char *w6e_phase(uint32_t p){switch(p){case W6E_IDLE:return "idle";case W6E_OFFER:return "connecting";case W6E_STREAM:return "sending";case W6E_FINISH:return "confirming";case W6E_SAVED:return "saved";case W6E_CANCELLED:return "cancelled";default:return "error";}}
int w6e_holds_link(const struct w6e_relay *r){return r->phase>=W6E_OFFER&&r->phase<=W6E_FINISH;}
int w6e_terminal(const struct w6e_relay *r){return r->phase>=W6E_SAVED;}
static void publish(struct w6e_relay *r,uint32_t now){struct w6e_status *s=&r->status;s->phase=r->phase;s->next=r->next;s->total=r->job.total;s->sequence=r->job.sequence;s->pid=r->worker_pid;s->code=r->code;copy(s->recording_id,r->job.recording_id,17);if(r->io.publish)r->io.publish(r->io.context,s);r->dirty=0;r->last_publish=now;}
static void terminal(struct w6e_relay *r,uint32_t p,int32_t code){r->phase=p;r->code=code;r->waiting=0;r->dirty=1;if(!r->io.close||r->io.close(r->io.context)==0)r->status.source_closed=1;else {r->phase=W6E_ERROR;r->code=-416;}}
void w6e_init(struct w6e_relay *r,const struct w6e_io *io,const char nonce[17],uint32_t pid){zero(r,sizeof(*r));copy(&r->io,io,sizeof(*io));copy(r->nonce,nonce,17);r->worker_pid=pid;r->dirty=1;r->status.source_closed=1;}
void w6e_transport(struct w6e_relay *r,int ready,int phone,uint32_t now){uint32_t on=ready&&phone;(void)now;if(!on&&r->online&&w6e_holds_link(r)){r->waiting=0;r->phase=W6E_OFFER;r->dirty=1;}r->online=on;}
void w6e_sent(struct w6e_relay *r,int result,uint32_t now){(void)now;r->sdk_pending=0;if(result&&w6e_holds_link(r)){r->waiting=0;r->phase=W6E_OFFER;r->dirty=1;}}
void w6e_cancel(struct w6e_relay *r){if(w6e_holds_link(r))terminal(r,W6E_CANCELLED,0);}
void w6e_worker_closed(struct w6e_relay *r){if(w6e_holds_link(r))terminal(r,W6E_ERROR,-417);r->status.worker_done=1;publish(r,0);}
static int add(char *b,uint32_t *n,const char *s){while(*s){if(*n>=3583)return 0;b[(*n)++]=*s++;}return 1;}
static void dec(char *b,uint32_t *n,uint32_t v){char d[10];uint32_t k=0;do{d[k++]=(char)('0'+v%10);v/=10;}while(v);while(k)b[(*n)++]=d[--k];}
static uint32_t base64(char *o,const uint8_t *s,uint32_t n){static const char t[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";uint32_t p=0,i;for(i=0;i<n;i+=3){uint32_t a=s[i],b=i+1<n?s[i+1]:0,c=i+2<n?s[i+2]:0;o[p++]=t[a>>2];o[p++]=t[((a&3)<<4)|(b>>4)];o[p++]=i+1<n?t[((b&15)<<2)|(c>>6)]:'=';o[p++]=i+2<n?t[c&63]:'=';}return p;}
static uint32_t packet(struct w6e_relay *r,uint32_t kind,uint32_t bytes){char check[9];uint32_t n=0;hexout(check,w6e_crc32(r->pcm,bytes),8);check[8]=0;
 if(++r->serial==0)return 0;copy(r->request,"w6r-",4);copy(r->request+4,r->nonce,16);r->request[20]='-';hexout(r->request+21,r->job.sequence,8);r->request[29]='-';hexout(r->request+30,r->serial,8);r->request[38]=0;
 add(r->wire,&n,"{\"v\":1,\"protocol\":\"w6r1\",\"id\":\"");add(r->wire,&n,r->request);add(r->wire,&n,"\",\"action\":\"");add(r->wire,&n,kind==W6E_OFFER?"recorder_offer":kind==W6E_STREAM?"recorder_chunk":"recorder_finish");add(r->wire,&n,"\",\"recording_id\":\"");add(r->wire,&n,r->job.recording_id);add(r->wire,&n,"\"");
 if(kind==W6E_STREAM){add(r->wire,&n,",\"offset\":");dec(r->wire,&n,r->next);add(r->wire,&n,",\"data\":\"");n+=base64(r->wire+n,r->pcm,bytes);add(r->wire,&n,"\",\"crc32\":\"");add(r->wire,&n,check);add(r->wire,&n,"\"");}
 else {add(r->wire,&n,",\"total_bytes\":");dec(r->wire,&n,r->job.total);add(r->wire,&n,",\"archive_hash\":\"");add(r->wire,&n,r->job.archive_hash);add(r->wire,&n,"\",\"pcm_crc32\":\"");add(r->wire,&n,r->job.pcm_crc32);add(r->wire,&n,"\"");if(kind==W6E_OFFER){add(r->wire,&n,",\"sample_rate\":");dec(r->wire,&n,r->job.rate);add(r->wire,&n,",\"complete\":true");}}
 add(r->wire,&n,"}");return n;
}
void w6e_tick(struct w6e_relay *r,uint32_t now){
 if(r->phase==W6E_IDLE){struct w6e_job j;int result=r->io.load?r->io.load(r->io.context,r->nonce,r->sequence,&j):0;if(result<0){terminal(r,W6E_ERROR,-400);}else if(result>0){copy(&r->job,&j,sizeof(j));r->sequence=j.sequence;r->next=0;r->phase=W6E_OFFER;r->dirty=1;publish(r,now);}}
 if(w6e_holds_link(r)&&r->io.cancel&&r->io.cancel(r->io.context,&r->job))w6e_cancel(r);
 if(r->dirty&&(now-r->last_publish>=250u||w6e_terminal(r)))publish(r,now);
 if(!w6e_holds_link(r)||!r->online||r->sdk_pending)return;
 if(r->waiting){if(now-r->sent_at<8000u)return;r->waiting=0;r->phase=W6E_OFFER;r->dirty=1;}
 if(r->phase==W6E_STREAM&&r->next==r->job.total)r->phase=W6E_FINISH;
 uint32_t bytes=0,kind=r->phase;
 if(kind==W6E_STREAM){bytes=r->job.total-r->next;if(bytes>W6E_CHUNK)bytes=W6E_CHUNK;int result=r->io.read?r->io.read(r->io.context,&r->job,r->next,r->pcm,bytes):-1;if(result==0)return;if(result<0||(uint32_t)result!=bytes){terminal(r,W6E_ERROR,-401);publish(r,now);return;}r->status.source_closed=0;}
 uint32_t size=packet(r,kind,bytes);if(!size){terminal(r,W6E_ERROR,-402);publish(r,now);return;}
 /* Mark before SDK call: a synchronous ACK/completion is legal. */
 r->kind=kind;r->chunk_bytes=bytes;r->waiting=1;r->sdk_pending=1;r->sent_at=now;
 if(!r->io.send||!r->io.send(r->io.context,r->wire,size)){r->sdk_pending=0;r->waiting=0;r->phase=W6E_OFFER;r->dirty=1;}
}
static int uuid(const char *s){uint32_t i;if(!s||s[36])return 0;for(i=0;i<36;i++){if(i==8||i==13||i==18||i==23){if(s[i]!='-')return 0;}else if(!hex(s+i,1,0))return 0;}return 1;}
int w6e_receive(struct w6e_relay *r,const char *text,uint32_t bytes,uint32_t now){struct rj_doc d;char id[81],record[17],storage[37];uint32_t next,durable;int ok,complete,phase;
 if(rj_parse(&d,text,bytes)!=0||!rj_equal(&d,rj_field(&d,0,"protocol"),"w6r1")||!rj_equal(&d,rj_field(&d,0,"type"),"recorder_ack"))return 0;
 if(!w6e_holds_link(r)||!r->waiting)return 1;
 if(!rj_string(&d,rj_field(&d,0,"request_id"),id,sizeof(id))||!rj_string(&d,rj_field(&d,0,"recording_id"),record,sizeof(record))||!equal(id,r->request,39)||!equal(record,r->job.recording_id,17))return 1;
 if(!rj_bool(&d,rj_field(&d,0,"ok"),&ok)||!ok){terminal(r,W6E_ERROR,-403);publish(r,now);return 1;}
 if(!rj_uint(&d,rj_field(&d,0,"durable"),&durable)||!rj_bool(&d,rj_field(&d,0,"complete"),&complete)||!rj_uint(&d,rj_field(&d,0,"next"),&next)||next>r->job.total||durable!=next||(next&1u)||!rj_string(&d,rj_field(&d,0,"storage_id"),storage,sizeof(storage))||!uuid(storage)){terminal(r,W6E_ERROR,-404);publish(r,now);return 1;}
 if(r->storage_id[0]&&!equal(storage,r->storage_id,37)){terminal(r,W6E_ERROR,-405);publish(r,now);return 1;}copy(r->storage_id,storage,37);
 phase=rj_field(&d,0,"phase");
 if(complete){if(next!=r->job.total||!rj_equal(&d,phase,"saved")||(r->kind!=W6E_OFFER&&r->kind!=W6E_FINISH)){terminal(r,W6E_ERROR,-406);}else {r->next=next;terminal(r,W6E_SAVED,0);}}
 else if(r->kind==W6E_OFFER&&(rj_equal(&d,phase,"ready")||rj_equal(&d,phase,"receiving"))){r->next=next;r->phase=next==r->job.total?W6E_FINISH:W6E_STREAM;r->waiting=0;r->dirty=1;}
 else if(r->kind==W6E_STREAM&&rj_equal(&d,phase,"receiving")&&next==r->next+r->chunk_bytes){r->next=next;r->phase=next==r->job.total?W6E_FINISH:W6E_STREAM;r->waiting=0;r->dirty=1;}
 else terminal(r,W6E_ERROR,-407);
 if(r->dirty&&(w6e_terminal(r)||now-r->last_publish>=250u))publish(r,now);return 1;
}
