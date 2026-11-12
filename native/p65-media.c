/* P65 3.100.043 fixed Capture/RPMSG adapter, STATIC CANDIDATE ONLY.
 * Function call sites and constants are listed in profile.json. This is not
 * enabled by the package: commercial control-call bounds and
 * physical STOPPED+EOF/tail acceptance still gate capability. */
#include "p65-media.h"
#include "spool.h"
#define CALL(T,A) ((T)(uintptr_t)(A))
typedef void *(*open_capture_fn)(const char *);
typedef int32_t (*capture_fn)(void *);
typedef void (*event_fn)(void *,int32_t,int32_t,const char *);
typedef int32_t (*listen_events_fn)(void *,void *,event_fn);
typedef int32_t (*rpc_fn)(void *,const char *,const char *,const char *,uint32_t,char *,uint32_t);
typedef int32_t (*socket_fn)(int32_t,int32_t,int32_t);
typedef int32_t (*bind_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*listen_fn)(int32_t,int32_t);
typedef int32_t (*accept_fn)(int32_t,void *,void *,int32_t);
typedef int32_t (*recv_fn)(int32_t,void *,uint32_t,int32_t);
typedef int32_t (*close_fn)(int32_t);
typedef int32_t *(*errno_fn)(void);
/* Exact P65 socket/accept4 bit tests and RPMSG recvmsg match pinned NuttX.
 * EAGAIN never closes this adapter's independently owned data socket. */
#define CLOEXEC_NONBLOCK UINT32_C(0x80800)
#define DONTWAIT 0x40
static int pending(void){int32_t e=*CALL(errno_fn,UINT32_C(0x0c4f793d))();return e==11||e==4;}
static void clear(void *out,uint32_t bytes){uint8_t *p=out;while(bytes--)*p++=0;}
static uint32_t u16(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8;}
static uint32_t u32(const uint8_t *p){return u16(p)|u16(p+2)<<16;}
static int tag(const uint8_t *p,const char *s){return p[0]==(uint8_t)s[0]&&p[1]==(uint8_t)s[1]&&p[2]==(uint8_t)s[2]&&p[3]==(uint8_t)s[3];}
static void on_event(void *cookie,int32_t event,int32_t result,const char *extra){
 struct vs_p65_media *m=cookie;(void)extra;
 /* Firmware invokes this on its notification thread. No I/O, Lua, allocation,
  * teardown or OS call is permitted here; close joins this thread. */
 if(result<0)__atomic_store_n(&m->event_error,result,__ATOMIC_RELEASE);
 if(event>=1&&event<=6)__atomic_fetch_or(&m->events,1u<<(uint32_t)event,__ATOMIC_RELEASE);
}
int vs_p65_media_prepare(struct vs_p65_media *m,const char nonce[17],uint32_t rate){
 uint8_t address[128];uint32_t n;int32_t ret;const char *options;
 if(!m||!nonce||(rate!=8000&&rate!=16000))return -1;
 clear(m,(uint32_t)sizeof(*m));m->listener=m->data=-1;m->rate=rate;
 /* P65 rp_name[16] admits at most 15 bytes, including this fixed prefix.
  * Full session nonce remains the source/ledger identity; bind collision fails. */
 m->socket_name[0]='v';m->socket_name[1]='s';for(n=0;n<12;n++)m->socket_name[n+2]=nonce[n+4];
 clear(address,sizeof(address));address[0]=0x41; /* AF_RPMSG, exact AP prepare */
 address[2]='a';address[3]='u';address[4]='d';address[5]='i';address[6]='o';
 for(n=0;n<15;n++)address[18+n]=(uint8_t)m->socket_name[n];
 m->listener=CALL(socket_fn,UINT32_C(0x1c167c91))(0x41,(int32_t)(CLOEXEC_NONBLOCK|1u),0);
 if(m->listener<0)return -2;
 if(CALL(bind_fn,UINT32_C(0x1c1681e9))(m->listener,address,sizeof(address))<0||CALL(listen_fn,UINT32_C(0x1c165bf1))(m->listener,1)<0)return -3;
 m->handle=CALL(open_capture_fn,UINT32_C(0x1c03a189))("Capture");if(!m->handle)return -4;
 ret=CALL(listen_events_fn,UINT32_C(0x1c03a245))(m->handle,m,on_event);if(ret<0)return -5;
 options=rate==8000?"format=wav:flush_packets=1:sample_rate=8000:ch_layout=mono":"format=wav:flush_packets=1:sample_rate=16000:ch_layout=mono";
 ret=CALL(rpc_fn,UINT32_C(0x1c03b2e1))(m->handle,0,"set_options",options,0,0,0);if(ret<0)return -6;
 /* The stock BUFFER wrapper makes this exact RPC, then blocks in accept4.
  * We keep our listener outside the opaque handle and accept after readiness. */
 ret=CALL(rpc_fn,UINT32_C(0x1c03b2e1))(m->handle,"ap","prepare",m->socket_name,0,0,0);return ret<0?-7:0;
}
int vs_p65_media_ready(struct vs_p65_media *m){
 if(__atomic_load_n(&m->event_error,__ATOMIC_ACQUIRE)<0)return -1;
 /* PREPARED is emitted after the server's prepare path. Do not pop an early
  * RPMSG connection during its sync handshake: this firmware's accept has
  * an additional connection-sync wait despite listener NONBLOCK. Exact
  * commercial ordering remains a physical acceptance gate. */
 if(!(__atomic_load_n(&m->events,__ATOMIC_ACQUIRE)&(1u<<1)))return 0;
 if(m->data<0){
  m->data=CALL(accept_fn,UINT32_C(0x1c165b21))(m->listener,0,0,(int32_t)CLOEXEC_NONBLOCK);if(m->data<0)return pending()?0:-3;
 }
 return (__atomic_load_n(&m->events,__ATOMIC_ACQUIRE)&(1u<<1))?1:0;
}
int vs_p65_media_start(struct vs_p65_media *m){if(!m->handle||m->data<0||m->start_calls)return -1;m->start_calls++;return CALL(capture_fn,UINT32_C(0x1c03a50d))(m->handle);}
static int parse_header(struct vs_p65_media *m){
 uint32_t p=12;int format=0;
 if(m->header_bytes<12)return 0;if(!tag(m->header,"RIFF")||!tag(m->header+8,"WAVE"))return -1;
 while(p<sizeof(m->header)){
  uint32_t len;if(p+8>m->header_bytes)return 0;len=u32(m->header+p+4);
  if(tag(m->header+p,"data")){if(!format)return -1;m->header_done=1;m->pcm_at=p+8;m->pcm_end=m->header_bytes;return 1;}
  if(len>sizeof(m->header)-p-8)return -1;if(p+8+len>m->header_bytes)return 0;
  if(tag(m->header+p,"fmt ")){
   const uint8_t *v=m->header+p+8;
   if(format||len<16||u16(v)!=1||u16(v+2)!=1||u32(v+4)!=m->rate||u32(v+8)!=m->rate*2||u16(v+12)!=2||u16(v+14)!=16)return -1;format=1;
  }
  p+=8+len+(len&1u);
 }
 return -1;
}
int vs_p65_media_read(struct vs_p65_media *m,uint8_t *out,uint32_t cap){
 int ready,got;uint32_t n,count;
 if(!m->handle||m->data<0||cap<2||(cap&1))return -20;
 if(!m->header_done){
  got=CALL(recv_fn,UINT32_C(0x1c1687a9))(m->data,m->header+m->header_bytes,sizeof(m->header)-m->header_bytes,DONTWAIT);
  if(got<=0)return got==0?VS_RX_EOF:pending()?VS_RX_AGAIN:-22;m->header_bytes+=(uint32_t)got;
  ready=parse_header(m);if(ready<0)return -23;if(!ready)return VS_RX_AGAIN;
 }
 count=(m->pcm_end-m->pcm_at)&~1u;
 if(count){if(count>cap)count=cap;for(n=0;n<count;n++)out[n]=m->header[m->pcm_at+n];m->pcm_at+=count;return (int)count;}
 /* Preserve an odd TCP/RPMSG read boundary until the next complete PCM sample. */
 count=m->pcm_end-m->pcm_at;if(count)m->header[0]=m->header[m->pcm_at];m->pcm_at=0;m->pcm_end=count;
 got=CALL(recv_fn,UINT32_C(0x1c1687a9))(m->data,m->header+count,(uint32_t)sizeof(m->header)-count,DONTWAIT);
 if(got==0)return count?-25:VS_RX_EOF;if(got<0)return pending()?VS_RX_AGAIN:-26;m->pcm_end=count+(uint32_t)got;
 count=m->pcm_end&~1u;if(count>cap)count=cap;for(n=0;n<count;n++)out[n]=m->header[n];m->pcm_at=count;return count?(int)count:VS_RX_AGAIN;
}
int vs_p65_media_stop(struct vs_p65_media *m){if(!m->handle)return 0;return CALL(rpc_fn,UINT32_C(0x1c03b2e1))(m->handle,0,"stop",0,0,0,0);}
int vs_p65_media_pause(struct vs_p65_media *m){if(!m->handle||!m->start_calls)return -1;__atomic_fetch_and(&m->events,~(1u<<3),__ATOMIC_ACQ_REL);return CALL(capture_fn,UINT32_C(0x1c03a52d))(m->handle);}
int vs_p65_media_paused(struct vs_p65_media *m){if(__atomic_load_n(&m->event_error,__ATOMIC_ACQUIRE)<0)return -1;return (__atomic_load_n(&m->events,__ATOMIC_ACQUIRE)&(1u<<3))?1:0;}
int vs_p65_media_resume(struct vs_p65_media *m){if(!m->handle||!m->start_calls)return -1;__atomic_fetch_and(&m->events,~(1u<<2),__ATOMIC_ACQ_REL);return CALL(capture_fn,UINT32_C(0x1c03a50d))(m->handle);}
int vs_p65_media_resumed(struct vs_p65_media *m){if(__atomic_load_n(&m->event_error,__ATOMIC_ACQUIRE)<0)return -1;return (__atomic_load_n(&m->events,__ATOMIC_ACQUIRE)&(1u<<2))?1:0;}
int vs_p65_media_stopped(struct vs_p65_media *m){if(__atomic_load_n(&m->event_error,__ATOMIC_ACQUIRE)<0)return -1;return (__atomic_load_n(&m->events,__ATOMIC_ACQUIRE)&(1u<<4))?1:0;}
int vs_p65_media_close(struct vs_p65_media *m){
 int ret=0;int32_t fd;if(m->close_uncertain)return -27;
 if(m->handle){ret=CALL(capture_fn,UINT32_C(0x1c03a1e9))(m->handle);if(ret<0)return ret;m->handle=0;}
 if(m->data>=0){fd=m->data;m->data=-1;ret=CALL(close_fn,UINT32_C(0x1c154d9d))(fd);if(ret<0){m->close_uncertain=1;return ret;}}
 if(m->listener>=0){fd=m->listener;m->listener=-1;ret=CALL(close_fn,UINT32_C(0x1c154d9d))(fd);if(ret<0){m->close_uncertain=1;return ret;}}
 return 0;
}
