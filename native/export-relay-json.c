/* Bounded strict JSON tokenizer. No allocation, recursion beyond16, or libc. */
#include "export-relay-json.h"
static int same(const char *a,const char *b,uint32_t n){
    while(n--)if(*a++!=*b++)return 0;
    return 1;
}
static uint32_t length(const char *s){
    uint32_t n=0;
    while(s[n])n++;
    return n;
}
static void space(const char *s,uint32_t n,uint32_t *p){
    while(*p<n&&(s[*p]==' '||s[*p]=='\n'||s[*p]=='\r'||s[*p]=='\t'))(*p)++;
}
static int token(struct rj_doc *d,uint32_t start,uint32_t end,uint32_t parent,uint32_t type){
    uint32_t t=d->count;
    if(t>=RJ_TOKENS)return -1;
    d->count++;
    d->tokens[t].start=(uint16_t)start;
    d->tokens[t].end=(uint16_t)end;
    d->tokens[t].parent=(uint16_t)parent;
    d->tokens[t].type=(uint8_t)type;
    d->tokens[t].pad=0;
    return (int)t;
}
static int string_end(const char *s,uint32_t n,uint32_t *p,int key){
    if(*p>=n||s[(*p)++]!='"')return 0;
    while(*p<n){
        uint32_t c=(uint8_t)s[(*p)++];
        if(c=='"')return 1;
        if(c<32)return 0;
        if(c=='\\'){
            uint32_t k;
            if(key||*p==n)return 0;
            c=(uint8_t)s[(*p)++];
            if(c=='u'){
                for(k=0;k<4;k++){
                    if(*p==n)return 0;
                    c=(uint8_t)s[(*p)++];
                    if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F')))return 0;
                }
            }
            else if(c!='"'&&c!='\\'&&c!='/'&&c!='b'&&c!='f'&&c!='n'&&c!='r'&&c!='t')return 0;
        }
    }
    return 0;
}
static int value(struct rj_doc *d,uint32_t *p,uint32_t parent,uint32_t depth){
    const char *s=d->text;
    uint32_t n=d->bytes,start=*p;
    int t;
    if(depth>16||*p>=n)return -1;
    if(s[*p]=='{'||s[*p]=='['){
        char close=s[*p]=='{'?'}':']';
        uint32_t kind=s[*p]=='{'?RJ_OBJECT:RJ_ARRAY;
        (*p)++;
        t=token(d,start,0,parent,kind);
        if(t<0)return -1;
        space(s,n,p);
        if(*p<n&&s[*p]==close){
            d->tokens[t].end=(uint16_t)++*p;
            return t;
        }
        while(*p<n){
            if(kind==RJ_OBJECT){
                uint32_t begin=*p,j;
                int key;
                if(!string_end(s,n,p,1))return -1;
                for(j=(uint32_t)t+1;j<d->count;j++)if(d->tokens[j].parent==(uint16_t)t&&d->tokens[j].pad&&(uint32_t)(d->tokens[j].end-d->tokens[j].start)==*p-begin&&same(s+d->tokens[j].start,s+begin,*p-begin))return -1;
                key=token(d,begin,*p,(uint32_t)t,RJ_STRING);
                if(key<0)return -1;
                d->tokens[key].pad=1;
                space(s,n,p);
                if(*p==n||s[(*p)++]!=':')return -1;
                space(s,n,p);
            }
            if(value(d,p,(uint32_t)t,depth+1)<0)return -1;
            space(s,n,p);
            if(*p==n)return -1;
            if(s[*p]==close){
                d->tokens[t].end=(uint16_t)++*p;
                return t;
            }
            if(s[(*p)++]!=',')return -1;
            space(s,n,p);
        }
        return -1;
    }
    if(s[*p]=='"'){
        if(!string_end(s,n,p,0))return -1;
        return token(d,start,*p,parent,RJ_STRING);
    }
    {
        const char *lit=0;
        uint32_t kind=0,k;
        if(s[*p]=='t'){
            lit="true";
            kind=RJ_TRUE;
        }
        else if(s[*p]=='f'){
            lit="false";
            kind=RJ_FALSE;
        }
        else if(s[*p]=='n'){
            lit="null";
            kind=RJ_NULL;
        }
        if(lit){
            k=length(lit);
            if(n-*p<k||!same(s+*p,lit,k))return -1;
            *p+=k;
            return token(d,start,*p,parent,kind);
        }
    }
    if(s[*p]=='-')(*p)++;
    if(*p==n||s[*p]<'0'||s[*p]>'9')return -1;
    if(s[*p]=='0')(*p)++;
    else while(*p<n&&s[*p]>='0'&&s[*p]<='9')(*p)++;
    if(*p<n&&s[*p]=='.'){
        (*p)++;
        if(*p==n||s[*p]<'0'||s[*p]>'9')return -1;
        while(*p<n&&s[*p]>='0'&&s[*p]<='9')(*p)++;
    }
    if(*p<n&&(s[*p]=='e'||s[*p]=='E')){
        (*p)++;
        if(*p<n&&(s[*p]=='+'||s[*p]=='-'))(*p)++;
        if(*p==n||s[*p]<'0'||s[*p]>'9')return -1;
        while(*p<n&&s[*p]>='0'&&s[*p]<='9')(*p)++;
    }
    return token(d,start,*p,parent,RJ_NUMBER);
}
int rj_parse(struct rj_doc *d,const char *s,uint32_t n){
    uint32_t p=0;
    if(!d||!s||n>4096)return -1;
    d->text=s;
    d->bytes=n;
    d->count=0;
    space(s,n,&p);
    if(value(d,&p,65535,0)!=0)return -1;
    space(s,n,&p);
    return p==n&&d->tokens[0].type==RJ_OBJECT?0:-1;
}
static int equal_token(const struct rj_doc *d,int t,const char *s){
    uint32_t n=length(s);
    if(t<0||(uint32_t)t>=d->count||d->tokens[t].type!=RJ_STRING||(uint32_t)(d->tokens[t].end-d->tokens[t].start)!=n+2)return 0;
    return same(d->text+d->tokens[t].start+1,s,n);
}
int rj_field(const struct rj_doc *d,int obj,const char *key){
    uint32_t i;
    if(obj<0||(uint32_t)obj>=d->count||d->tokens[obj].type!=RJ_OBJECT)return -1;
    for(i=(uint32_t)obj+1;i+1<d->count;i++)if(d->tokens[i].start<d->tokens[obj].end&&d->tokens[i].parent==(uint16_t)obj&&d->tokens[i].pad&&equal_token(d,(int)i,key))return (int)i+1;
    return -1;
}
int rj_uint(const struct rj_doc *d,int t,uint32_t *out){
    uint32_t p,v=0;
    if(t<0||(uint32_t)t>=d->count||d->tokens[t].type!=RJ_NUMBER)return 0;
    for(p=d->tokens[t].start;p<d->tokens[t].end;p++){
        uint32_t c=(uint8_t)d->text[p];
        if(c<'0'||c>'9'||v>429496729u||(v==429496729u&&c>'5'))return 0;
        v=v*10u+c-'0';
    }
    *out=v;
    return 1;
}
int rj_bool(const struct rj_doc *d,int t,int *out){
    if(t<0||(uint32_t)t>=d->count)return 0;
    if(d->tokens[t].type==RJ_TRUE){
        *out=1;
        return 1;
    }
    if(d->tokens[t].type==RJ_FALSE){
        *out=0;
        return 1;
    }
    return 0;
}
int rj_string(const struct rj_doc *d,int t,char *out,uint32_t cap){
    uint32_t p,n=0;
    if(t<0||(uint32_t)t>=d->count||d->tokens[t].type!=RJ_STRING)return 0;
    for(p=d->tokens[t].start+1;p+1<d->tokens[t].end;p++){
        uint32_t c=(uint8_t)d->text[p];
        if(c<32||c>126||c=='\\'||n+1>=cap)return 0;
        out[n++]=(char)c;
    }
    out[n]=0;
    return 1;
}
int rj_raw_string(const struct rj_doc *d,int t,char *out,uint32_t cap){
    uint32_t i,n;
    if(t<0||(uint32_t)t>=d->count||d->tokens[t].type!=RJ_STRING)return 0;
    n=d->tokens[t].end-d->tokens[t].start;
    if(n+1>cap)return 0;
    for(i=0;i<n;i++)out[i]=d->text[d->tokens[t].start+i];
    out[n]=0;
    return 1;
}
int rj_equal(const struct rj_doc *d,int t,const char *s){
    return equal_token(d,t,s);
}
