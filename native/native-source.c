/* Exact-P65 continuous candidate. Explicit START + GO are required.
 * Capability enablement permits the reviewed owned-worker path; physical
 * verification remains false and is never inferred from build/host results. */
#include <stdint.h>
#include <stddef.h>
#include "spool.h"
#include "p65-owner.h"
#include "status.h"
struct vs_guard { uint32_t address,count,fnv; };
#include "profile.h"
static int guard(void){uint32_t j;for(j=0;j<sizeof(source_guards)/sizeof(source_guards[0]);j++){
 uint32_t n,hash=2166136261u;const volatile uint8_t *p=(const volatile uint8_t *)(uintptr_t)source_guards[j].address;
 for(n=0;n<source_guards[j].count;n++)hash=(hash^p[n])*16777619u;if(hash!=source_guards[j].fnv)return 0;
 }return 1;}
static int report(void){
 static const char json[]="{\"v\":1,\"continuous\":false,\"verified\":false,\"phase\":\"blocked\",\"capability_mask\":63,\"required_mask\":127,\"code\":\"native_continuous_acceptance_required\",\"missing\":[\"commercial_buffer_prepare_accept_order\",\"commercial_flush_stop_tail_acceptance\",\"device_filesystem_latency_and_durability_acceptance\"]}\n";
 return vs_write_source_status("0000000000000000",1,json,sizeof(json)-1);
}
__attribute__((used,noinline,section(".text.watch6_entry")))
int32_t watch6_continuous_source_initialize(struct unload_pair *pair){
 if(!pair)return -1;pair->callback=0;pair->context=0;
 if(!guard())return -2;
 /* Deliberate fail-closed contract: the current artifact can report missing
  * capabilities but cannot accidentally start the unaccepted BUFFER path. */
 if(VS_STATIC_CAPABILITIES!=VS_CAP_ALL||!VS_CONTINUOUS_CANDIDATE_ENABLED)return report();
 return vs_p65_owner_initialize(pair);
}
