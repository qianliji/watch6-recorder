/* P65 3.100.043 candidate: independent phone transport owner, no Lua calls.
 * No native microphone API is imported by this module. See phone-link-contract.json.
 * Every asynchronous object, callback and buffer remains allocated until the
 * independent task has drained close callbacks and its PID no longer exists. */
#include <stddef.h>
#include <stdint.h>

#define INL __attribute__((always_inline)) inline
#define CB __attribute__((used,noinline))
#define FN(type, address) ((type)(uintptr_t)UINT32_C(address))
#define BASE "/data/watch6recorder/"
#define MAX_PAYLOAD 4096u
#define HEADER_SIZE 64u
#define CONTROL_SIZE 128u
#define FRAME_SIZE 4224u
#define STATUS_SIZE 256u
#define FOREGROUND_TX_CAPACITY 3u

struct unload_pair { int32_t (*callback)(void *); void *context; };
struct spawn_attr { uint8_t flags,priority,policy,padding; uint32_t mask[2],stacksize; void *stackaddr; };
struct uv_message { uint8_t type,pad[3]; uint32_t len,seq,reserved; void *payload; };
struct uv_connection { void *node; void *callback; uint8_t mode,pad[3]; void *reader,*data; };
union uv_loop_storage { uint64_t align; uint8_t bytes[0x280]; };
union uv_timer_storage { uint64_t align; uint8_t bytes[0xa0]; };
struct firmware_guard { uint32_t address,count,fnv; };
#include "../adapters/phone-link-guards.h"
#include "export-relay-fs.h"

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
typedef int32_t (*loop_fn)(void *);
typedef int32_t (*run_fn)(void *,int32_t);
typedef void (*close_uv_fn)(void *,void (*)(void *));
typedef int32_t (*timer_init_fn)(void *,void *);
typedef int32_t (*timer_start_fn)(void *,void (*)(void *),uint64_t,uint64_t);
typedef void (*recv_cb)(struct uv_connection *,int32_t,struct uv_message *,const char *);
typedef void (*send_cb)(struct uv_connection *,int32_t,struct uv_message *,void *);
typedef int32_t (*connect_fn)(void *,struct uv_connection *,const char *,recv_cb);
typedef int32_t (*send_fn)(struct uv_connection *,const char *,struct uv_message *,send_cb,void *);
typedef int32_t (*link_close_fn)(struct uv_connection *);
typedef void (*free_fn)(void *);

_Static_assert(sizeof(void *)==4,"P65 pointer ABI");
_Static_assert(sizeof(struct uv_connection)==20,"P65 client connection plus application data");
_Static_assert(offsetof(struct uv_connection,reader)==12,"P65 internal reader offset");
_Static_assert(sizeof(struct uv_message)==20 && offsetof(struct uv_message,payload)==16,"P65 message ABI");
_Static_assert(sizeof(struct spawn_attr)==20,"P65 spawn ABI");
_Static_assert(sizeof(union uv_loop_storage)==0x280,"P65 loop memset size");

/* MiWear copies its message header but borrows payload until its own callback.
 * Every foreground request therefore owns a distinct slot, including its
 * callback context. The export relay retains its separate single request. */
struct foreground_tx {
    struct uv_message message;
    uint32_t sequence,submitted_ms,busy;
    char payload[MAX_PAYLOAD];
};

struct context {
    union uv_loop_storage loop;
    union uv_timer_storage timer;
    struct uv_connection conn;
    struct uv_message tx_message;
    struct foreground_tx foreground[FOREGROUND_TX_CAPACITY];
    volatile uint32_t spawn_attempted,done,loop_closed;
    volatile int32_t pid;
    char nonce[17];
    uint32_t generation,tx_ack,tx_pending,rx_seq,consumed,dropped;
    uint32_t timer_initialized,timer_closed,link_attempted,link_closed;
    uint32_t closing,ready,phone,released,elapsed_ms,heartbeat_ms,heartbeat_seq;
    uint32_t tx_age_ms,last_tx_ms,connect_ms,tick_ms,last_now;
    uint32_t export_pending,recovering,retry_at,retry_count;
    int32_t error;
    const char *phase;
    char tx_payload[MAX_PAYLOAD];
    char frame[FRAME_SIZE];
    char control[CONTROL_SIZE];
    char status[STATUS_SIZE];
};
static struct context ctx;
static struct w6e_relay exporter;
static struct w6e_fs export_fs;
static uint32_t relay_now(void){return *(const uint32_t *)(const void *)(ctx.loop.bytes+0x180);}
static const char *const rx_paths[4] = { BASE "w6r-link-rx-0.msg",BASE "w6r-link-rx-1.msg",BASE "w6r-link-rx-2.msg",BASE "w6r-link-rx-3.msg" };

static INL void memory_zero(void *p,uint32_t count) { uint8_t *b=p; while(count--) *b++=0; }
static INL uint32_t equal(const void *a,const void *b,uint32_t n) { const uint8_t *x=a,*y=b; while(n--) if(*x++!=*y++) return 0; return 1; }
static INL void copy(void *a,const void *b,uint32_t n) { uint8_t *x=a; const uint8_t *y=b; while(n--) *x++=*y++; }
static INL uint32_t guarded(void) {
    uint32_t j;
    for(j=0;j<sizeof(phone_guards)/sizeof(phone_guards[0]);++j) {
        uint32_t h=UINT32_C(2166136261),i;
        const volatile uint8_t *p=(const volatile uint8_t *)(uintptr_t)phone_guards[j].address;
        for(i=0;i<phone_guards[j].count;++i) h=(h^p[i])*UINT32_C(16777619);
        if(h!=phone_guards[j].fnv) return 0;
    }
    return 1;
}
static INL int32_t read_fixed(const char *path,void *bytes,uint32_t count) {
    int32_t fd=FN(open_fn,0x0c8bef01)(path,1); uint32_t n=0,tries=0; int32_t result=0;
    if(fd<0) return -101;
    while(n<count && tries++<64) {
        int32_t got=FN(read_fn,0x0c8beaf1)(fd,(uint8_t *)bytes+n,count-n);
        if(got<=0 || (uint32_t)got>count-n) { result=-102; break; } n+=(uint32_t)got;
    }
    if(FN(close_fn,0x0c8bdba9)(fd)!=0) result=-103;
    return result ? result : n==count ? 0 : -104;
}
static INL int32_t write_fixed(const char *path,const void *bytes,uint32_t count) {
    int32_t fd=FN(open_fn,0x0c8bef01)(path,2); uint32_t n=0,tries=0; int32_t result=0;
    if(fd<0) return -105;
    while(n<count && tries++<64) {
        int32_t got=FN(write_fn,0x0c8be041)(fd,(const uint8_t *)bytes+n,count-n);
        if(got<=0 || (uint32_t)got>count-n) { result=-106; break; } n+=(uint32_t)got;
    }
    if(FN(close_fn,0x0c8bdba9)(fd)!=0) result=-107;
    return result ? result : n==count ? 0 : -108;
}
static INL void hex(char *out,uint32_t number,uint32_t digits) {
    while(digits) { uint32_t x=number&15u; out[--digits]=(char)(x<10?'0'+x:'a'+x-10); number>>=4; }
}
static INL uint32_t parse_hex(const char *in,uint32_t digits,uint32_t *out) {
    uint32_t i,n=0;
    for(i=0;i<digits;++i) { uint32_t c=(uint8_t)in[i],v;
        if(c>='0'&&c<='9') v=c-'0'; else if(c>='a'&&c<='f') v=c-'a'+10; else return 0;
        n=(n<<4)|v;
    } *out=n; return 1;
}
static INL void header(char *out,uint32_t seq,uint32_t len) {
    uint32_t i; for(i=0;i<64;++i) out[i]=' ';
    copy(out,"VSL1 ",5); copy(out+5,ctx.nonce,16); out[21]=' ';
    hex(out+22,seq,8); out[30]=' '; hex(out+31,len,4); out[35]='\n';
}
static INL uint32_t record(const char *bytes,uint32_t payload_size,uint32_t *seq,uint32_t *len,uint32_t start) {
    uint32_t i,high,low;
    if(!equal(bytes,"VSL1 ",5)||!equal(bytes,bytes+64+payload_size,64)) return 0;
    if(bytes[21]!=' '||bytes[30]!=' '||bytes[35]!='\n') return 0;
    for(i=36;i<64;++i) if(bytes[i]!=' ') return 0;
    if(!parse_hex(bytes+5,8,&high)||!parse_hex(bytes+13,8,&low)) return 0;
    if(!start && !equal(bytes+5,ctx.nonce,16)) return 0;
    if(!parse_hex(bytes+22,8,seq)||!parse_hex(bytes+31,4,len)) return 0;
    return *len<=payload_size;
}
static INL uint32_t control(const char *path,uint32_t *seq) {
    uint32_t len;
    return read_fixed(path,ctx.control,128)==0 && record(ctx.control,0,seq,&len,0) && len==0;
}
static INL uint32_t utf8_json(const char *s,uint32_t n) {
    uint32_t i=0;
    if(n<2||s[0]!='{'||s[n-1]!='}') return 0;
    while(i<n) { uint32_t c=(uint8_t)s[i++],need,min,v;
        if(c==0) return 0;
        if(c<128) continue;
        if(c>=0xc2&&c<=0xdf) { need=1; min=0x80; v=c&31; }
        else if(c>=0xe0&&c<=0xef) { need=2; min=0x800; v=c&15; }
        else if(c>=0xf0&&c<=0xf4) { need=3; min=0x10000; v=c&7; }
        else return 0;
        if(n-i<need) return 0;
        while(need--) { c=(uint8_t)s[i++]; if((c&0xc0)!=0x80) return 0; v=(v<<6)|(c&63); }
        if(v<min||v>0x10ffff||(v>=0xd800&&v<=0xdfff)) return 0;
    } return 1;
}
static INL void append(char *out,uint32_t *n,const char *text) { while(*text && *n<192) out[(*n)++]=*text++; }
static INL void number(char *out,uint32_t *n,const char *key,uint32_t val) {
    append(out,n,key); if(*n+9<=192) { hex(out+*n,val,8); *n+=8;out[(*n)++]='\n'; }
}
static INL int32_t snapshot(void) {
    uint32_t i,n=64;
    ++ctx.generation; if(!ctx.generation) ++ctx.generation;
    for(i=0;i<256;++i) ctx.status[i]=' ';
    header(ctx.status,ctx.generation,0); copy(ctx.status+192,ctx.status,64);
    append(ctx.status,&n,"phase="); append(ctx.status,&n,ctx.phase); append(ctx.status,&n,"\n");
    number(ctx.status,&n,"pid=",(uint32_t)ctx.pid);
    number(ctx.status,&n,"tx_ack=",ctx.tx_ack); number(ctx.status,&n,"rx_seq=",ctx.rx_seq);
    number(ctx.status,&n,"error=",(uint32_t)ctx.error); number(ctx.status,&n,"dropped=",ctx.dropped);
    number(ctx.status,&n,"phone=",ctx.phone);
    number(ctx.status,&n,"tx_cap=",FOREGROUND_TX_CAPACITY);
    return write_fixed(BASE "w6r-link-status.txt",ctx.status,256);
}
static INL void consumed_refresh(void) {
    uint32_t seq;
    if(control(BASE "w6r-link-consumed.txt",&seq) && seq>=ctx.consumed && seq<=ctx.rx_seq) ctx.consumed=seq;
}
static CB void timer_closed(void *handle) { (void)handle; ctx.timer_closed=1; }
static INL void begin_close(int32_t error) {
    if(ctx.closing) return;
    ctx.closing=1; if(error && !ctx.error) ctx.error=error;
    ctx.phase="closing"; (void)snapshot();
    if(ctx.timer_initialized && !ctx.timer_closed) FN(close_uv_fn,0x0c621f99)(&ctx.timer,timer_closed);
    if(ctx.link_attempted && !ctx.link_closed && ctx.conn.node) {
        /* The reader can already have queued its own EOF close. uv_close
         * asserts on a second close. Exact P65 uv_handle flags are +0x6c,
         * pipe is private-node+8, and bits0/1 denote closing/closed. Do not
         * replace its existing close callback/data in that case. */
        uint32_t flags=*(const uint32_t *)((const uint8_t *)ctx.conn.node+0x74);
        if(!(flags&3u)) (void)FN(link_close_fn,0x0c62df51)(&ctx.conn);
    } else ctx.link_closed=1;
}
static CB void sent(struct uv_connection *,int32_t,struct uv_message *,void *);
static CB void foreground_sent(struct uv_connection *,int32_t,struct uv_message *,void *);
static void recover_link(int32_t error){
 if(ctx.closing)return;if(!w6e_holds_link(&exporter)&&!ctx.released){begin_close(error);return;}if(ctx.recovering)return;
 ctx.recovering=1;ctx.ready=ctx.phone=0;ctx.phase="reconnecting";
 w6e_transport(&exporter,0,0,relay_now());
 uint32_t delay=ctx.retry_count==0?1000u:ctx.retry_count==1?2000u:ctx.retry_count==2?5000u:10000u;
 if(ctx.retry_count<3)ctx.retry_count++;ctx.retry_at=relay_now()+delay;
 if(ctx.conn.node&&!ctx.link_closed){uint32_t flags=*(const uint32_t *)((const uint8_t *)ctx.conn.node+0x74);if(!(flags&3u))(void)FN(link_close_fn,0x0c62df51)(&ctx.conn);}else ctx.link_closed=1;
 (void)snapshot();
}
static int export_send(void *unused,const char *json,uint32_t bytes){int32_t result;(void)unused;
 if(ctx.closing||ctx.recovering||!ctx.ready||!ctx.phone||!ctx.conn.node||ctx.tx_pending||!bytes||bytes>4096)return 0;
 copy(ctx.tx_payload,json,bytes);memory_zero(&ctx.tx_message,sizeof(ctx.tx_message));
 ctx.tx_message.type=0x83;ctx.tx_message.len=bytes;ctx.tx_message.payload=ctx.tx_payload;
 ctx.tx_pending=ctx.export_pending=1;ctx.tx_age_ms=ctx.last_tx_ms=0;
 result=FN(send_fn,0x0c62de65)(&ctx.conn,NULL,&ctx.tx_message,sent,&ctx);
 if(result){if(ctx.export_pending){ctx.export_pending=0;ctx.tx_pending=0;w6e_sent(&exporter,result,relay_now());}recover_link(result);return 0;}
 return 1;
}
static INL struct foreground_tx *foreground_free(void) {
    uint32_t i;
    for(i=0;i<FOREGROUND_TX_CAPACITY;++i) if(!ctx.foreground[i].busy) return &ctx.foreground[i];
    return NULL;
}
static INL uint32_t foreground_expired(uint32_t now) {
    uint32_t i;
    for(i=0;i<FOREGROUND_TX_CAPACITY;++i)
        if(ctx.foreground[i].busy && now-ctx.foreground[i].submitted_ms>=15000u) return 1;
    return 0;
}
static CB void foreground_sent(struct uv_connection *conn,int32_t result,struct uv_message *msg,void *arg) {
    uint32_t i;struct foreground_tx *slot=NULL;
    (void)conn;(void)msg;
    for(i=0;i<FOREGROUND_TX_CAPACITY;++i) if(arg==&ctx.foreground[i]) { slot=&ctx.foreground[i];break; }
    if(!slot || !slot->busy) return;
    slot->busy=0;if(ctx.tx_pending) --ctx.tx_pending;
    /* Completion only releases the borrowed buffer. tx_ack already admitted
     * this exact immutable request; only the phone's audio_ack confirms audio. */
    if(result!=0 && !ctx.closing) {
        begin_close(result);return;
    }
    (void)snapshot();
}
static CB void sent(struct uv_connection *conn,int32_t result,struct uv_message *msg,void *arg) {
 (void)conn;(void)msg;(void)arg;
 if(!ctx.export_pending)return;
 ctx.export_pending=0;ctx.tx_pending=0;ctx.tx_age_ms=0;
 w6e_sent(&exporter,result,relay_now());
 if(result&&!ctx.closing)recover_link(result);
}
static CB void received(struct uv_connection *conn,int32_t result,struct uv_message *msg,const char *client) {
    (void)conn; (void)client;
    if(msg && msg->type==2 && msg->len>=4 && msg->payload) {
        uint32_t event=*(const uint32_t *)msg->payload;
        if(event==3) { ctx.link_closed=1; ctx.conn.node=NULL; ctx.conn.reader=NULL;
            if(!ctx.closing) { recover_link(result ? result : -203); }
            return; }
        if(ctx.closing) return;
        if(result!=0 || event==2 || event==6 || event==7) {
            recover_link(result ? result : -204-(int32_t)event); return; }
        if(event==1) { ctx.ready=1; ctx.phase="connected"; (void)snapshot(); }
        if(event==5) { ctx.phone=1; (void)snapshot(); }
        w6e_transport(&exporter,ctx.ready,ctx.phone,relay_now());if(ctx.ready&&ctx.phone)ctx.retry_count=0;
        return;
    }
    if(ctx.closing) return;
    if(result!=0) {
        recover_link(result); return; }
    if(!msg || msg->type!=0x83) return;
    if(msg->len>MAX_PAYLOAD) { ++ctx.dropped; (void)snapshot(); return; }
    if(!msg->payload || !utf8_json(msg->payload,msg->len)) {
        begin_close(-221); return; }
    if(w6e_holds_link(&exporter)){(void)w6e_receive(&exporter,msg->payload,msg->len,relay_now());return;}
    consumed_refresh();
    if(ctx.rx_seq-ctx.consumed>=4) { begin_close(-222); return; }
    if(ctx.rx_seq==UINT32_MAX) { begin_close(-223); return; }
    uint32_t seq=ctx.rx_seq+1,i;
    header(ctx.frame,seq,msg->len); for(i=0;i<4096;++i) ctx.frame[64+i]=' ';
    copy(ctx.frame+64,msg->payload,msg->len); copy(ctx.frame+4160,ctx.frame,64);
    if(write_fixed(rx_paths[(seq-1)&3u],ctx.frame,4224)!=0) { begin_close(-224); return; }
    ctx.rx_seq=seq; (void)snapshot();
}
static CB void tick(void *handle) {
    (void)handle;
    uint32_t seq,len;
    if(ctx.closing) return;
    /* P65 timer_start reads loop+0x180 as the monotonic millisecond clock.
     * Count actual elapsed loop time, rather than assuming each tick ran on
     * schedule. OS/FS blocking itself cannot be given a hard wall-clock bound. */
    uint32_t now=*(const uint32_t *)(const void *)(ctx.loop.bytes+0x180);
    uint32_t elapsed=now-ctx.last_now;ctx.last_now=now;
    ctx.elapsed_ms+=elapsed; ctx.heartbeat_ms+=elapsed;
    ctx.connect_ms+=elapsed; ctx.last_tx_ms+=elapsed;
    if(ctx.tx_pending) ctx.tx_age_ms+=elapsed;
    if(foreground_expired(now)) {
        begin_close(-233);return;
    }
    if(!ctx.released) {
        /* New initialization may replace start.txt while an older same-name
         * module is still loaded: insmod then fails before reaching this code.
         * Only a successfully loaded new generation can run this worker. Lua
         * resets its bounded mailboxes AFTER successful insmod, and writes
         * this fresh-nonce heartbeat LAST. Before that gate, do not inspect
         * stop/TX/consumed or connect to the server: those belong to old IPC. */
        if(control(BASE "w6r-link-heartbeat.txt",&seq) && seq>=1) {
            ctx.released=1;ctx.heartbeat_seq=seq;
            ctx.elapsed_ms=0;ctx.heartbeat_ms=0;ctx.connect_ms=0;ctx.last_tx_ms=0;
            w6e_tick(&exporter,now);
            ctx.phase="connecting";ctx.link_attempted=1;
            int32_t result=FN(connect_fn,0x0c62dd9d)(&ctx.loop,&ctx.conn,"com.watch6.recorder",received);
            if(result!=0) {
                /* Both negative exits precede uv_pipe_init. On the second
                 * allocation failure only an unregistered node was allocated. */
                if(ctx.conn.node) FN(free_fn,0x0c50b25d)(ctx.conn.node);
                ctx.conn.node=NULL;ctx.link_closed=1;recover_link(result);
            } else (void)snapshot();
        } else if(ctx.elapsed_ms>=8000) begin_close(-235);
        return;
    }
    w6e_tick(&exporter,now);
    if(control(BASE "w6r-link-stop.txt",&seq) && seq==0){w6e_cancel(&exporter);begin_close(0);return;}
    if(w6e_terminal(&exporter)){begin_close(exporter.code);return;}
    if(w6e_holds_link(&exporter)){
        if(ctx.recovering&&ctx.link_closed&&!ctx.tx_pending&&(int32_t)(now-ctx.retry_at)>=0){
            memory_zero(&ctx.conn,sizeof(ctx.conn));ctx.link_closed=0;ctx.recovering=0;ctx.connect_ms=0;ctx.link_attempted=1;
            int32_t result=FN(connect_fn,0x0c62dd9d)(&ctx.loop,&ctx.conn,"com.watch6.recorder",received);
            if(result){if(ctx.conn.node)FN(free_fn,0x0c50b25d)(ctx.conn.node);ctx.conn.node=NULL;ctx.link_closed=1;recover_link(result);}
        }
        if(!ctx.recovering&&!ctx.ready&&ctx.connect_ms>=15000)recover_link(-232);
        if(ctx.tx_pending&&ctx.tx_age_ms>=15000)recover_link(-233);
        if(ctx.ready&&ctx.conn.node&&(*(const uint32_t *)((const uint8_t *)ctx.conn.node+0x74)&3u))recover_link(-203);
        uint32_t next=ctx.ready&&ctx.phone&&!ctx.recovering?25u:1000u;
        if(next!=ctx.tick_ms){ctx.tick_ms=next;int32_t result=FN(timer_start_fn,0x0c629fb5)(&ctx.timer,tick,next,next);if(result)begin_close(result);}
        return; /* Explicit export owns the lease. GUI sleep is not cancellation. */
    }
    if(ctx.recovering&&ctx.link_closed&&!ctx.tx_pending&&(int32_t)(now-ctx.retry_at)>=0){
        memory_zero(&ctx.conn,sizeof(ctx.conn));ctx.link_closed=0;ctx.recovering=0;ctx.connect_ms=0;
        int32_t result=FN(connect_fn,0x0c62dd9d)(&ctx.loop,&ctx.conn,"com.watch6.recorder",received);
        if(result){if(ctx.conn.node)FN(free_fn,0x0c50b25d)(ctx.conn.node);ctx.conn.node=NULL;ctx.link_closed=1;recover_link(result);}
    }
    if(control(BASE "w6r-link-stop.txt",&seq) && seq==0) { begin_close(0); return; }
    if(ctx.heartbeat_ms>=1000) {
        ctx.heartbeat_ms=0;
        if(control(BASE "w6r-link-heartbeat.txt",&seq) && seq>ctx.heartbeat_seq) { ctx.heartbeat_seq=seq; ctx.elapsed_ms=0; }
        if(ctx.elapsed_ms>=8000) { begin_close(-231); return; }
        consumed_refresh();
    }
    if(!ctx.ready && ctx.connect_ms>=15000) { begin_close(-232); return; }
    if(ctx.tx_pending && ctx.tx_age_ms>=15000) { begin_close(-233); return; }
    if(ctx.ready && ctx.conn.node &&
            (*(const uint32_t *)((const uint8_t *)ctx.conn.node+0x74)&3u)) {
        begin_close(-203);return;
    }
    struct foreground_tx *slot=foreground_free();
    if(ctx.ready && slot && read_fixed(BASE "w6r-link-tx.msg",ctx.frame,4224)==0 &&
            record(ctx.frame,4096,&seq,&len,0) && seq>ctx.tx_ack) {
        if(seq!=ctx.tx_ack+1 || !len || !utf8_json(ctx.frame+64,len)) { begin_close(-234); return; }
        copy(slot->payload,ctx.frame+64,len);memory_zero(&slot->message,sizeof(slot->message));
        slot->message.type=0x83;slot->message.len=len;slot->message.payload=slot->payload;
        slot->sequence=seq;slot->submitted_ms=now;slot->busy=1;
        ++ctx.tx_pending;ctx.tx_age_ms=0;ctx.last_tx_ms=0;
        int32_t result=FN(send_fn,0x0c62de65)(&ctx.conn,NULL,&slot->message,foreground_sent,slot);
        /* A defensive synchronous error callback may already own teardown. */
        if(ctx.closing) return;
        if(result!=0) {
            if(slot->busy) { slot->busy=0;if(ctx.tx_pending) --ctx.tx_pending; }
            begin_close(result);return;
        }
        /* This frees only the file mailbox, after bytes have an owned slot and
         * MiWear accepted the request. It is deliberately not a delivery ACK. */
        ctx.tx_ack=seq;(void)snapshot();
    }
    /* One 1536-byte PCM packet every 250ms is insufficient for 8kHz mono.
     * The 25ms activity lease supports bounded single-packet backpressure.
     * No timer callback spins; uv_run sleeps in the firmware poll backend. */
    uint32_t next=(ctx.tx_pending || ctx.last_tx_ms<1200) ? 25u : 1000u;
    if(next!=ctx.tick_ms) {
        ctx.tick_ms=next;
        int32_t result=FN(timer_start_fn,0x0c629fb5)(&ctx.timer,tick,(uint64_t)next,(uint64_t)next);
        if(result!=0) begin_close(result);
    }
}
static CB int32_t worker(int32_t argc,char **argv) {
    (void)argc;(void)argv;
    ctx.pid=FN(pid_fn,0x0c4c96ad)();
    {struct w6e_io io;w6e_fs_init(&export_fs,ctx.nonce);w6e_fs_ops(&export_fs,&io);io.send=export_send;w6e_init(&exporter,&io,ctx.nonce,(uint32_t)ctx.pid);}
    ctx.phase="starting"; (void)snapshot();
    int32_t result=FN(loop_fn,0x0c626361)(&ctx.loop);
    if(result!=0) { ctx.error=result;ctx.phase="error";(void)snapshot();ctx.done=1;return 0; }
    ctx.last_now=*(const uint32_t *)(const void *)(ctx.loop.bytes+0x180);
    result=FN(timer_init_fn,0x0c629dd1)(&ctx.loop,&ctx.timer);
    if(result==0) {
        ctx.timer_initialized=1;ctx.tick_ms=25;ctx.phase="starting";
        result=FN(timer_start_fn,0x0c629fb5)(&ctx.timer,tick,UINT64_C(25),UINT64_C(25));
    }
    if(result!=0) begin_close(result); else (void)snapshot();
    (void)FN(run_fn,0x0c6220c9)(&ctx.loop,0);
    /* UV_RUN_DEFAULT returns only after all active/closing handles and
     * pending requests have drained. A close callback is not unload proof. */
    result=FN(loop_fn,0x0c62b529)(&ctx.loop);
    if(result==0 && !ctx.tx_pending && (!ctx.link_attempted || ctx.link_closed) && (!ctx.timer_initialized || ctx.timer_closed)) {
        ctx.loop_closed=1;ctx.phase=ctx.error ? "error" : "closed";
    } else { ctx.error=result ? result : -241;ctx.phase="retained"; }
    (void)w6e_fs_close(&export_fs);if(ctx.loop_closed)w6e_worker_closed(&exporter);
    (void)snapshot();
    ctx.done=1; /* uninit also requires PID hash no longer containing worker */
    return 0;
}
static CB int32_t uninitialize(void *opaque) {
    if(opaque!=&ctx) return -16;
    if(!ctx.spawn_attempted) return 0;
    if(!ctx.done || !ctx.loop_closed || ctx.tx_pending || ctx.pid<=0 || export_fs.fd>=0 || export_fs.uncertain) return -16;
    /* This exact P65 lookup masks interrupts, checks hash collision/PID, then
     * restores BASEPRI. We never dereference its returned TCB pointer. A reused
     * PID conservatively retains code. No signal, kill, or force-unload occurs. */
    if(FN(lookup_fn,0x0c4c5c45)(ctx.pid)!=NULL) return -16;
    return 0;
}
__attribute__((used,noinline,section(".text.watch6_entry")))
int32_t watch6_recorder_phone_link_initialize(struct unload_pair *pair) {
    struct spawn_attr attrs __attribute__((aligned(8)));
    uint32_t seq,len;
    if(!pair) return -1;
    pair->callback=NULL;pair->context=NULL;
    if(!guarded()) return -2;
    if(read_fixed(BASE "w6r-link-start.txt",ctx.control,128)!=0 || !record(ctx.control,0,&seq,&len,1) || seq!=0 || len!=0) return -3;
    copy(ctx.nonce,ctx.control+5,16);ctx.nonce[16]=0;
    ctx.phase="initializing";ctx.pid=0;
    if(snapshot()!=0) return -4;
    int32_t result=FN(attr_fn,0x0c4fdcc9)(&attrs);
    if(result!=0) { ctx.error=result;ctx.phase="error";(void)snapshot();return 0; }
    result=FN(stack_fn,0x0c4fdd69)(&attrs,8192);
    if(result!=0) { ctx.error=result;ctx.phase="error";(void)snapshot();return 0; }
    pair->callback=uninitialize;pair->context=&ctx;
    ctx.spawn_attempted=1;
    char *argv[1]={NULL};
    result=FN(spawn_fn,0x0c4c96f5)("w6rx_owner",worker,NULL,&attrs,argv,NULL);
    if(result<=0) {
        ctx.spawn_attempted=0;ctx.error=result;ctx.phase="error";(void)snapshot();
    }
    /* A successful worker owns status writes and pid from this point. Never
     * report init failure after spawn: the loader must retain its code. */
    return 0;
}
