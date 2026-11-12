package com.watch6.recorder;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import org.json.JSONObject;
public final class ProtocolHostTest {
    static int cases,assertions;static String ID="0123456789abcdef",HASH="abcdef0123456789",STORAGE="12345678-1234-4234-8234-123456789abc";
    static void check(boolean value,String text){assertions++;if(!value)throw new AssertionError(text);}
    interface Job{void run() throws Exception;}
    static void reject(Job job,String text) throws Exception {boolean rejected=false;try{job.run();}catch(Exception e){rejected=true;}check(rejected,text);cases++;}
    static JSONObject request(String action) throws Exception{return new JSONObject().put("v",1).put("protocol","w6r1").put("id","synthetic-"+action).put("action",action).put("recording_id",ID);}
    static JSONObject wire(JSONObject request) throws Exception{return Protocol.decode(request.toString().getBytes(StandardCharsets.UTF_8));}
    public static void main(String[] args) throws Exception {
        ArchiveStore store=new ArchiveStore(new File(args[0]),d->{if(!d.isDirectory())throw new IOException();});byte[] raw=new byte[5000];for(int i=0;i<raw.length;i++)raw[i]=(byte)(i%251);String crc=ArchiveStore.checksum(raw);
        JSONObject hello=Protocol.handle(store,wire(request("recorder_hello")),STORAGE);check(hello.getBoolean("ok")&&hello.getString("phase").equals("ready")&&hello.getInt("max_chunk_bytes")==2048,"hello ready and wire capacity");cases++;
        reject(()->Protocol.decode(new byte[]{(byte)255}),"invalid UTF8 rejected");
        reject(()->wire(request("recorder_hello").put("v",1.1)),"noninteger protocol version rejected");
        reject(()->wire(request("recorder_hello").put("id",123)),"numeric request identity rejected");
        reject(()->wire(request("recorder_hello").put("protocol","other")),"other application protocol rejected");
        reject(()->Protocol.decode(new byte[4097]),"oversize UTF8 frame rejected");
        reject(()->Protocol.decode("{\"nested\":[[[[[[[[[0]]]]]]]]]}".getBytes(StandardCharsets.UTF_8)),"deep JSON rejected");
        reject(()->Protocol.decode((request("recorder_hello").toString()+" true").getBytes(StandardCharsets.UTF_8)),"trailing JSON rejected");
        JSONObject offer=request("recorder_offer").put("sample_rate",8000).put("total_bytes",raw.length).put("archive_hash",HASH).put("pcm_crc32",crc).put("complete",true);
        reject(()->Protocol.handle(store,wire(new JSONObject(offer.toString()).put("complete",false)),STORAGE),"unsealed source not accepted");
        JSONObject missingChecksum=new JSONObject(offer.toString());missingChecksum.remove("pcm_crc32");
        reject(()->Protocol.handle(store,wire(missingChecksum),STORAGE),"whole checksum required");
        reject(()->Protocol.handle(store,wire(new JSONObject(offer.toString()).put("total_bytes","5000")),STORAGE),"string numeric fields rejected");
        reject(()->Protocol.handle(store,wire(new JSONObject(offer.toString()).put("total_bytes",4999.5)),STORAGE),"fractional length rejected");
        JSONObject first=Protocol.handle(store,wire(offer),STORAGE);check(first.getLong("next")==0&&first.getLong("durable")==0&&!first.getBoolean("complete"),"offer ACK starts at durable zero");cases++;
        JSONObject premature=request("recorder_finish").put("total_bytes",raw.length).put("archive_hash",HASH).put("pcm_crc32",crc);reject(()->Protocol.handle(store,wire(premature),STORAGE),"finish cannot precede entire audio");
        reject(()->Protocol.handle(store,wire(request("recorder_chunk").put("offset",0).put("data","AAAA=").put("crc32","00000000")),STORAGE),"noncanonical base64 rejected");
        for(int offset=0;offset<raw.length;){int end=Math.min(raw.length,offset+2048);byte[] part=Arrays.copyOfRange(raw,offset,end);JSONObject chunk=request("recorder_chunk").put("offset",offset).put("data",Base64.getEncoder().encodeToString(part)).put("crc32",ArchiveStore.checksum(part));
            JSONObject ack=Protocol.handle(store,wire(chunk),STORAGE);check(ack.getBoolean("ok")&&ack.getLong("durable")==end&&ack.getLong("next")==end&&!ack.getBoolean("complete"),"chunk ACK follows durable storage");
            JSONObject duplicate=Protocol.handle(store,wire(chunk),STORAGE);check(duplicate.getLong("durable")==end,"duplicate ACK stable");offset=end;
        }cases++;
        JSONObject status=Protocol.handle(store,wire(request("recorder_status")),STORAGE);check(status.getLong("durable")==raw.length&&!status.getBoolean("complete"),"full bytes alone are not saved receipt");cases++;
        JSONObject done=Protocol.handle(store,wire(premature),STORAGE);check(done.getBoolean("complete")&&done.getString("phase").equals("saved")&&done.getString("sha256").length()==64,"global CRC and WAV seal required for saved");
        byte[] wav=Files.readAllBytes(store.audio(ID).toPath());check(Arrays.equals(Arrays.copyOfRange(wav,44,wav.length),raw),"wire decoder to full WAV bit identity");cases++;
        check(Protocol.handle(store,wire(offer),STORAGE).getBoolean("complete"),"resume offer returns saved receipt");cases++;
        reject(()->Protocol.handle(store,wire(request("recorder_finish").put("total_bytes",raw.length).put("archive_hash",HASH).put("pcm_crc32","00000000")),STORAGE),"finish checksum identity cannot change");
        reject(()->Protocol.handle(store,wire(request("unknown")),STORAGE),"unknown action rejected");
        System.out.println("{\"passed\":true,\"cases\":"+cases+",\"assertions\":"+assertions+",\"wire_json_parser\":\"JSON-java external JVM dependency; Android parser not executed\",\"real_device_access\":false}");
    }
}
