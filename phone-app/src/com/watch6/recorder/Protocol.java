package com.watch6.recorder;

import java.nio.charset.*;
import java.nio.ByteBuffer;
import java.util.Base64;
import org.json.JSONObject;
import org.json.JSONTokener;

/** w6r1 only. The SDK listener passes a bounded frame to one disk worker. */
final class Protocol {
    static final String NAME="w6r1";
    static JSONObject decode(byte[] bytes) throws Exception {
        if(bytes==null||bytes.length<2||bytes.length>4096)throw new IllegalArgumentException("消息大小无效");
        String text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        boolean quoted=false,escape=false;int depth=0;
        for(int n=0;n<text.length();n++){
            char c=text.charAt(n);if(quoted){if(escape)escape=false;else if(c=='\\')escape=true;else if(c=='"')quoted=false;continue;}
            if(c=='"')quoted=true;else if(c=='{'||c=='['){if(++depth>8)throw new IllegalArgumentException("消息层级无效");}else if(c=='}'||c==']'){if(--depth<0)throw new IllegalArgumentException("消息格式无效");}
        }
        if(quoted||depth!=0)throw new IllegalArgumentException("消息格式无效");
        JSONTokener tokener=new JSONTokener(text);Object decoded=tokener.nextValue();
        if(!(decoded instanceof JSONObject)||tokener.nextClean()!=0)throw new IllegalArgumentException("消息格式无效");
        JSONObject message=(JSONObject)decoded;
        if(number(message,"v",1)!=1||!NAME.equals(message.optString("protocol")))throw new IllegalArgumentException("不是独立录音协议");
        String id=message.optString("id");if(!(message.opt("id") instanceof String)||!id.matches("[A-Za-z0-9._-]{1,80}"))throw new IllegalArgumentException("请求标识无效");
        return message;
    }
    static long number(JSONObject message,String key,long maximum) throws Exception {
        Object raw=message.opt(key);if(!(raw instanceof Number))throw new IllegalArgumentException("数值格式无效");
        double d=((Number)raw).doubleValue();long n=((Number)raw).longValue();if(!Double.isFinite(d)||d!=n||n<0||n>maximum)throw new IllegalArgumentException("数值范围无效");return n;
    }
    static JSONObject reply(JSONObject request,String storage) throws Exception {
        return new JSONObject().put("v",1).put("protocol",NAME).put("type","recorder_ack").put("request_id",request.optString("id")).put("recording_id",request.optString("recording_id")).put("storage_id",storage);
    }
    static JSONObject handle(ArchiveStore store,JSONObject request,String storage) throws Exception {
        JSONObject response=reply(request,storage);String action=request.optString("action"),id=request.optString("recording_id");ArchiveStore.Progress p;
        if("recorder_hello".equals(action))return response.put("ok",true).put("phase","ready").put("next",0).put("durable",0).put("complete",false).put("max_chunk_bytes",ArchiveStore.CHUNK_BYTES);
        if(!ArchiveStore.validId(id))throw new IllegalArgumentException("录音标识无效");
        switch(action){
            case "recorder_offer":
                if(!Boolean.TRUE.equals(request.opt("complete")))throw new IllegalArgumentException("请先结束并封存这条录音");
                p=store.offer(id,(int)number(request,"sample_rate",16000),number(request,"total_bytes",ArchiveStore.MAX_BYTES),request.optString("archive_hash"),request.optString("pcm_crc32"));break;
            case "recorder_chunk":
                String text=request.optString("data");if(text.isEmpty()||text.length()>2732)throw new IllegalArgumentException("音频包过长");
                byte[] data;try{data=Base64.getDecoder().decode(text);}catch(IllegalArgumentException error){throw new IllegalArgumentException("音频编码无效");}
                if(!Base64.getEncoder().encodeToString(data).equals(text))throw new IllegalArgumentException("音频编码不规范");
                p=store.chunk(id,number(request,"offset",ArchiveStore.MAX_BYTES),data,request.optString("crc32"));break;
            case "recorder_finish":p=store.finish(id,number(request,"total_bytes",ArchiveStore.MAX_BYTES),request.optString("archive_hash"),request.optString("pcm_crc32"));break;
            case "recorder_status":p=store.status(id);break;
            default:throw new IllegalArgumentException("不支持的录音操作");
        }
        return response.put("ok",true).put("phase",p.complete?"saved":"receiving").put("next",p.next).put("durable",p.next).put("complete",p.complete).put("sample_rate",p.rate).put("total_bytes",p.total).put("sha256",p.sha256);
    }
}
