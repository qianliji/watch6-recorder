package com.watch6.recorder;
import java.io.*;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** NDJSON transport boundary for cross-language host tests; no Android SDK stub. */
public final class ProtocolHarness {
    public static void main(String[] args) throws Exception {
        ArchiveStore store=new ArchiveStore(new File(args[0]),directory->{if(!directory.isDirectory())throw new IOException("missing");});
        BufferedReader input=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));String line;
        while((line=input.readLine())!=null){
            JSONObject request=null;
            try{request=Protocol.decode(line.getBytes(StandardCharsets.UTF_8));System.out.println(Protocol.handle(store,request,"12345678-1234-4234-8234-123456789abc"));}
            catch(Exception error){JSONObject reply=request==null?new JSONObject().put("ok",false).put("phase","error"):Protocol.reply(request,"12345678-1234-4234-8234-123456789abc").put("ok",false).put("phase","error").put("complete",false).put("next",0).put("durable",0);System.out.println(reply);}
        }
    }
}
