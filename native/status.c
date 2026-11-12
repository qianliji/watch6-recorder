#include "status.h"
#ifndef VS_DATA_ROOT
#define VS_DATA_ROOT "/data/watch6recorder/"
#endif
typedef int32_t (*open_fn)(const char *,int32_t,...);
typedef int32_t (*write_fn)(int32_t,const void *,uint32_t);
typedef int32_t (*close_fn)(int32_t);
static void hex(char *p,uint32_t value){uint32_t n=8;while(n){uint32_t d=value&15;p[--n]=(char)(d<10?'0'+d:'a'+d-10);value>>=4;}}
static uint32_t crc(const char *p,uint32_t n){uint32_t c=0xffffffffu,k;while(n--){c^=(uint8_t)*p++;for(k=0;k<8;k++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return c^0xffffffffu;}
static void copy(char *a,const char *b,uint32_t n){while(n--)*a++=*b++;}
int vs_write_source_status(const char nonce[17],uint32_t sequence,const char *json,uint32_t bytes){
 char frame[1536];uint32_t n=0,tries=0;int32_t fd;int ret=0;if(!sequence||!bytes||bytes>1408)return -1;
 for(n=0;n<sizeof(frame);n++)frame[n]=' ';
 copy(frame,"VSMST1\n",7);copy(frame+7,nonce,16);frame[23]='\n';copy(frame+24,"seq=",4);hex(frame+28,sequence);frame[36]='\n';copy(frame+37,"len=",4);hex(frame+41,bytes);frame[49]='\n';copy(frame+50,"crc=",4);hex(frame+54,crc(json,bytes));frame[62]='\n';
 copy(frame+64,json,bytes);copy(frame+1472,frame,64);
 fd=((open_fn)(uintptr_t)0x0c8bef01u)(VS_DATA_ROOT "vs-meeting-source-status.txt",2);if(fd<0)return -1;n=0;
 while(n<sizeof(frame)&&tries++<32){int32_t got=((write_fn)(uintptr_t)0x0c8be041u)(fd,frame+n,sizeof(frame)-n);if(got<=0||(uint32_t)got>sizeof(frame)-n){ret=-1;break;}n+=(uint32_t)got;}
 if(((close_fn)(uintptr_t)0x0c8bdba9u)(fd)!=0)ret=-1;return ret||n!=sizeof(frame)?-1:0;
}
