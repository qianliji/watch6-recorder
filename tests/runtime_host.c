/* Synthetic RAM-only test of the actual native local-archive owner loop. */
#include "host_adapter.c"
#include "owner-runtime.h"
static uint32_t runtime_clock,runtime_waits;
static uint32_t rt_now(void *p){(void)p;return runtime_clock;}
static int rt_stop(void*p,const char*n){(void)p;(void)n;return runtime_clock>=25?VS_REASON_USER:0;}
static int rt_receipts(void*p,struct vs_owner*o){(void)p;(void)o;return 0;}
static int rt_publish(void*p,const struct vs_owner*o){(void)p;(void)o;return 0;}
static void rt_wait(void*p,uint32_t n){(void)p;runtime_clock+=n;runtime_waits++;}
static int rt_max(void*p,uint32_t a,uint32_t b){(void)p;(void)a;(void)b;return 0;}
int run_suite(void){
 struct vs_ops o;struct vs_owner_runtime r={0,rt_now,rt_stop,rt_receipts,rt_publish,rt_wait,rt_max,0};
 (void)run_all();reset(1000);o=ops();runtime_clock=runtime_waits=0;
 CHECK(vs_owner_run(&f.owner,&o,&r,"fedcba9876543210",8000,2)==0);
 CHECK(f.owner.phase==VS_CLOSED&&f.owner.count==1&&f.owner.complete);
 CHECK(f.owner.produced==1000&&f.owner.durable==1000&&f.reclaims==0);
 CHECK(f.started==1&&f.stopped==1&&f.closed==1&&runtime_waits<10);
 CHECK(vs_owner_unloadable(&f.owner));host_cases++;return (int)host_failures;
}
