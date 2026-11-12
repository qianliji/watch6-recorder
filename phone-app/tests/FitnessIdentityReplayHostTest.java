package com.watch6.recorder;

import android.content.Context;
import android.os.Looper;
import com.xiaomi.xms.wearable.Task;
import com.xiaomi.xms.wearable.Wearable;
import com.xiaomi.xms.wearable.message.MessageApi;
import com.xiaomi.xms.wearable.node.Node;
import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Runs the real PhoneLink, lease, protocol and archive against SDK boundary
 * doubles from run_fitness_host.py. It does not execute firmware or verify a
 * signature. The listener-to-protocol dispatch below is a harness, rather than
 * the Android ReceiverService/disk worker/wake-lock implementation.
 */
public final class FitnessIdentityReplayHostTest {
    private static final String WATCH="watch-a";
    private static final String STORAGE="12345678-1234-4234-8234-123456789abc";
    private static int assertions;
    private static void check(boolean value,String reason){assertions++;if(!value)throw new AssertionError(reason);}
    private static void drain(){Looper.drain();}
    private static <T>T last(List<T> values){check(!values.isEmpty(),"expected SDK boundary call");return values.get(values.size()-1);}

    private static final class Environment implements PhoneLink.Listener {
        final Context context=new Context();
        final ArchiveStore store;
        final PhoneLink link;
        boolean ready;
        int deliveries,protocolCalls;
        Environment(File directory)throws Exception {
            store=new ArchiveStore(directory,d->{if(!d.isDirectory())throw new IOException("missing synthetic directory");});
            link=new PhoneLink(context,this);
        }
        public void state(String text,boolean value){ready=value;}
        public void message(byte[] bytes,long lease){
            deliveries++;
            check(link.accepts(lease),"actual PhoneLink must publish an active lease");
            JSONObject request=null;
            try {
                request=Protocol.decode(bytes);protocolCalls++;
                link.send(Protocol.handle(store,request,STORAGE).toString(),lease);
            } catch(Exception rejected) {
                if(request==null)throw new AssertionError("fixture did not reach the real protocol",rejected);
                try {
                    link.send(Protocol.reply(request,STORAGE).put("ok",false).put("phase","error")
                        .put("next",0).put("durable",0).put("complete",false).toString(),lease);
                } catch(Exception error){throw new AssertionError(error);}
            }
        }
        void discover(){link.connect(false);drain();last(Wearable.nodes.queries).success(Arrays.asList(new Node(WATCH)));drain();}
        void permission(boolean value){last(Wearable.auth.checks).success(value);drain();}
        void installed(boolean value){last(Wearable.nodes.installs).success(value);drain();}
        void added(){last(Wearable.messages.adds).task.success(null);drain();check(ready,"SDK accepted the listener");}
        void establish(){discover();permission(true);installed(true);added();}
        JSONObject diagnostic()throws Exception{return new JSONObject(link.diagnostics());}
        void assertPhase(String value,int code)throws Exception {
            JSONObject d=diagnostic();check(value.equals(d.getString("phase")),"expected phase "+value+", got "+d);
            check(d.getInt("last_error_code")==code,"expected error "+code);
            check(!ready&&!d.getBoolean("application_ready"),"blocked boundary cannot be ready");
            check(deliveries==0&&protocolCalls==0&&Wearable.messages.sends.isEmpty(),"blocked boundary must not process or ACK audio");
            check(store.list().isEmpty(),"blocked boundary must not persist any recording");
        }
        void close(){link.close();drain();for(MessageApi.Remove r:Wearable.messages.removes)r.task.success(null);drain();}
    }

    private static JSONObject report(String scenario,Environment e)throws Exception {
        return new JSONObject().put("scenario",scenario).put("assertions",assertions)
            .put("diagnostics",e.diagnostic()).put("deliveries",e.deliveries).put("protocol_calls",e.protocolCalls)
            .put("sdk_install_checks",Wearable.nodes.installs.size()).put("sdk_listener_adds",Wearable.messages.adds.size())
            .put("sdk_sends",Wearable.messages.sends.size()).put("scope","SDK boundary replay; not firmware identity validation");
    }

    private static JSONObject scenario(String name,File directory)throws Exception {
        Environment e=new Environment(directory);
        switch(name) {
            case "permission_before_sdk":
                e.context.granted=false;e.link.connect(false);drain();e.assertPhase("permission_required",601);
                check(Wearable.getters==0,"OS denial must precede SDK initialization");break;
            case "authorization_before_identity":
                e.discover();e.permission(false);e.assertPhase("authorization_required",201);
                check(Wearable.nodes.installs.isEmpty()&&Wearable.messages.adds.isEmpty(),"authorization denial precedes identity/listener checks");
                check(Wearable.auth.requests.isEmpty(),"background replay cannot request authorization");break;
            case "identity_missing_after_authorization":
                e.discover();e.permission(true);e.installed(false);e.assertPhase("identity_required",301);
                check(Wearable.messages.adds.isEmpty(),"real PhoneLink must refuse listener registration without identity");
                check(Wearable.nodes.installTargets.equals(Arrays.asList(WATCH)),"identity query must target the selected watch");
                Looper.advance(59999);check(Wearable.nodes.queries.size()==1,"missing identity must use low-frequency retry");
                break;
            case "identity_lookup_failure":
                e.discover();e.permission(true);last(Wearable.nodes.installs).fail(new IOException("synthetic SDK identity lookup failure"));drain();
                e.assertPhase("retrying",302);check(Wearable.messages.adds.isEmpty(),"failed lookup is not installed=true");break;
            case "identity_true_listener_rejected":
                e.discover();e.permission(true);e.installed(true);
                last(Wearable.messages.adds).task.fail(new IOException("synthetic SDK listener rejection"));drain();e.assertPhase("retrying",401);break;
            case "ready_without_delivery_is_not_export":
                e.establish();check(e.deliveries==0&&e.protocolCalls==0&&e.store.list().isEmpty(),"SDK readiness alone cannot prove delivery or export");
                check(e.diagnostic().getLong("rx_packets")==0&&e.diagnostic().getLong("tx_packets")==0,"no message counters without traffic");break;
            case "wrong_peer_never_reaches_protocol":
                e.establish();last(Wearable.messages.adds).listener.onMessageReceived("watch-other",hello());drain();
                check(e.deliveries==0&&e.protocolCalls==0&&Wearable.messages.sends.isEmpty(),"wrong peer must be rejected by actual PhoneLink");
                check(e.store.list().isEmpty(),"wrong peer cannot write an archive");
                // The SDK-thread fast rejection increments the counter without
                // publishing diagnostics; the normal idempotent connect does.
                e.link.connect(false);drain();
                check(e.diagnostic().getLong("dropped_packets")==1,"wrong peer increments actual drop counter");break;
            default:throw new AssertionError("unknown scenario "+name);
        }
        JSONObject result=report(name,e);e.close();return result;
    }
    private static byte[] hello(){return "{\"v\":1,\"protocol\":\"w6r1\",\"id\":\"synthetic-hello\",\"action\":\"recorder_hello\"}".getBytes(StandardCharsets.UTF_8);}

    private static JSONObject frame(File directory,String line)throws Exception {
        Environment e=new Environment(directory);e.establish();
        JSONObject envelope=new JSONObject(line);byte[] bytes=envelope.getJSONObject("frame").toString().getBytes(StandardCharsets.UTF_8);
        last(Wearable.messages.adds).listener.onMessageReceived(envelope.optString("sender",WATCH),bytes);drain();
        JSONArray sends=new JSONArray();
        for(MessageApi.Send send:Wearable.messages.sends){
            check(WATCH.equals(send.node),"reply must target selected watch");
            sends.put(new JSONObject(new String(send.bytes,StandardCharsets.UTF_8)));
            send.task.success(null);drain();
        }
        JSONObject result=report("authorized_identity_frame",e).put("sends",sends);
        e.close();return result;
    }
    public static void main(String[] args)throws Exception {
        if(args.length!=2)throw new IllegalArgumentException("scenario synthetic-store-directory");
        JSONObject result;
        if("frame".equals(args[0])){
            String line=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8)).readLine();
            if(line==null)throw new IllegalArgumentException("missing synthetic frame");result=frame(new File(args[1]),line);
        } else result=scenario(args[0],new File(args[1]));
        System.out.println(result);
    }
}
