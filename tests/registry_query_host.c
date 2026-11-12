/* Production one-shot helper, with only firmware call boundaries injected. */
#define W6RQ_HOST 1
#include "../native/registry-query.c"
volatile uint32_t host_cases,host_assertions,host_failures;
static uint8_t input[129],output[256];static struct module_record records[8];
static uint32_t guard_good,owner_pid,lock_depth,record_count,iterator_mode,iterator_calls,
 opens,reads,writes,closes,read_pos,input_size,output_size,write_max,write_fail_at,read_fail,close_fail_at;
static void check(int value){host_assertions++;if(!value)host_failures++;}
static int guard(uint32_t a,uint32_t n,uint32_t h){(void)a;(void)n;(void)h;return (int)guard_good;}
static int32_t pid(void){return 321;}
uint32_t w6rq_host_word(uint32_t address){if(address==0x3c3b9390u)return owner_pid;if(address==0x3c3b9394u)return lock_depth;host_failures++;return 0;}
static int32_t open_file(const char *path,int32_t mode,...){opens++;if(mode==1){check(same(path,W6RQ_REQUEST_PATH,sizeof(W6RQ_REQUEST_PATH)));read_pos=0;return 1;}check(mode==2&&same(path,W6RQ_STATUS_PATH,sizeof(W6RQ_STATUS_PATH)));return 2;}
static int32_t read_file(int32_t fd,void *p,uint32_t n){reads++;check(fd==1);if(read_fail)return -1;if(n>input_size-read_pos)n=input_size-read_pos;copy(p,input+read_pos,n);read_pos+=n;return (int32_t)n;}
static int32_t write_file(int32_t fd,const void *p,uint32_t n){writes++;check(fd==2);if(write_fail_at&&writes>=write_fail_at)return 0;if(n>write_max)n=write_max;if(n>sizeof(output)-output_size){host_failures++;return -1;}copy(output+output_size,p,n);output_size+=n;return (int32_t)n;}
static int32_t close_file(int32_t fd){closes++;check(fd==1||fd==2);return close_fail_at==closes?-1:0;}
static int32_t foreach(int32_t (*callback)(const struct module_record *,void *),void *c){iterator_calls++;
 if(iterator_mode==1)return callback((const struct module_record *)(uintptr_t)4,c);
 if(iterator_mode==2){for(uint32_t i=0;i<1000;i++){int32_t r=callback(&records[0],c);if(r)return r;}host_failures++;return 0;}
 for(uint32_t i=0;i<record_count;i++){int32_t r=callback(&records[i],c);if(r)return r;}
 if(iterator_mode==3)return 1;if(iterator_mode==4)owner_pid=0;return 0;}
uintptr_t w6rq_host_call(uint32_t a){switch(a){case 0xfffffff0u:return (uintptr_t)guard;case 0x0c4c96adu:return (uintptr_t)pid;case 0x0c4fa055u:return (uintptr_t)foreach;case 0x0c8bef01u:return (uintptr_t)open_file;case 0x0c8beaf1u:return (uintptr_t)read_file;case 0x0c8be041u:return (uintptr_t)write_file;case 0x0c8bdba9u:return (uintptr_t)close_file;default:host_failures++;return 0;}}
static void set_name(uint32_t index,const char *name){uint32_t i=0;while(name[i]&&i<95){records[index].name[i]=name[i];i++;}records[index].name[i]=0;}
static void request(void){for(uint32_t i=0;i<64;i++)input[i]=' ';copy(input,"W6RQ1\n",6);copy(input+6,"0011223344556677",16);input[22]=input[31]=input[40]='\n';copy(input+23,"00000001",8);hex(input+32,8,crc(input,32));copy(input+56,"W6RQEND\n",8);copy(input+64,input,64);}
static void reset(void){host_cases++;for(uint32_t i=0;i<sizeof(input);i++)input[i]=0;for(uint32_t i=0;i<sizeof(output);i++)output[i]=0;for(uint32_t i=0;i<sizeof(records);i++)((uint8_t *)records)[i]=0;
 guard_good=1;owner_pid=321;lock_depth=1;record_count=iterator_mode=iterator_calls=opens=reads=writes=closes=read_pos=output_size=write_fail_at=read_fail=close_fail_at=0;input_size=128;write_max=256;request();}
static int32_t run(void){struct w6rq_unload_pair pair;pair.callback=(int32_t (*)(void *))(uintptr_t)123;pair.context=(void *)(uintptr_t)456;int32_t r=watch6_registry_query_initialize(&pair);check(!pair.callback&&!pair.context);return r;}
static uint32_t field(uint32_t at){uint32_t v=0;check(parse_hex(output+at,8,&v));return v;}
static void valid_status(int32_t result){check(output_size==256&&same(output,output+128,128));check(same(output,"W6RS1\n",6)&&same(output+6,input+6,16)&&same(output+23,input+23,8)&&same(output+120,"W6RSEND\n",8));check(field(32)==(uint32_t)result&&field(95)==crc(output,95));}
/* Cross-layer test entry points. Lua supplies the request bytes; the actual
 * production helper creates the response. No request/status encoder is faked. */
void host_exchange_setup(uint32_t mask){reset();for(uint32_t i=0;i<5;i++)if(mask&(1u<<i)){set_name(record_count,names[i]);records[record_count].entry=0x12345679u;records[record_count].uninit=0x87654321u;records[record_count].arg=0x40000000u;record_count++;}}
uint32_t host_exchange_input(void){return (uint32_t)(uintptr_t)input;}
uint32_t host_exchange_output(void){return (uint32_t)(uintptr_t)output;}
uint32_t host_exchange_output_size(void){return output_size;}
uint32_t host_exchange_records(void){return (uint32_t)(uintptr_t)records;}
uint32_t host_exchange_records_size(void){return sizeof(records);}
uint32_t host_exchange_iterator_calls(void){return iterator_calls;}
int32_t host_exchange_run(void){return run();}
void host_registry_suite(void){
 reset();check(run()==0&&iterator_calls==1);valid_status(0);for(uint32_t k=0;k<5;k++)check(field(41+k*9)==0);check(field(86)==0);
 reset();record_count=7;for(uint32_t k=0;k<5;k++)set_name(k,names[k]);set_name(5,"system-module");set_name(6,"w6rqry");check(run()==0);valid_status(0);for(uint32_t k=0;k<5;k++)check(field(41+k*9)==1);check(field(86)==7);
 reset();record_count=2;set_name(0,"w6rc-extra");set_name(1,"w6rxlin");check(run()==0);valid_status(0);check(field(41)==0&&field(68)==0);
 reset();record_count=2;set_name(0,"w6rdirect");set_name(1,"w6rdirect");check(run()==W6RQ_DUPLICATE);valid_status(W6RQ_DUPLICATE);check(field(77)==2);
 reset();record_count=1;for(uint32_t i=0;i<96;i++)records[0].name[i]='x';check(run()==W6RQ_REGISTRY);valid_status(W6RQ_REGISTRY);
 reset();iterator_mode=1;check(run()==W6RQ_REGISTRY);valid_status(W6RQ_REGISTRY);
 reset();iterator_mode=2;set_name(0,"foreign");check(run()==W6RQ_REGISTRY);valid_status(W6RQ_REGISTRY);check(field(86)==129);
 reset();owner_pid=999;check(run()==W6RQ_LOCK&&opens==0&&iterator_calls==0);
 reset();lock_depth=0;check(run()==W6RQ_LOCK&&opens==0&&iterator_calls==0);
 reset();guard_good=0;check(run()==W6RQ_FIRMWARE&&opens==0&&iterator_calls==0);
 reset();input[32]='f';input[96]='f';check(run()==W6RQ_REQUEST&&iterator_calls==0&&writes==0);
 reset();input_size=127;check(run()==W6RQ_REQUEST&&iterator_calls==0&&writes==0);
 reset();input_size=129;check(run()==W6RQ_REQUEST&&iterator_calls==0&&writes==0);
 reset();write_max=20;write_fail_at=2;check(run()==W6RQ_SHORT&&output_size==20&&writes==2&&closes==2);
 reset();write_max=20;check(run()==0&&writes==13);valid_status(0);
 reset();close_fail_at=1;check(run()==W6RQ_REQUEST&&iterator_calls==0&&writes==0);
 reset();iterator_mode=3;check(run()==W6RQ_REGISTRY);valid_status(W6RQ_REGISTRY);
 reset();iterator_mode=4;check(run()==W6RQ_LOCK);valid_status(W6RQ_LOCK);
 reset();for(uint32_t i=6;i<22;i++)input[i]='0';hex(input+32,8,crc(input,32));copy(input+64,input,64);check(run()==W6RQ_REQUEST&&iterator_calls==0);
 reset();check(watch6_registry_query_initialize(NULL)==W6RQ_INVALID&&opens==0);
 reset();read_fail=1;check(run()==W6RQ_REQUEST&&iterator_calls==0&&writes==0);
 reset();record_count=1;records[0].name[0]=1;check(run()==W6RQ_REGISTRY);valid_status(W6RQ_REGISTRY);
}
