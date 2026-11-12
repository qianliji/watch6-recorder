package com.watch6.recorder;

import android.content.Intent;
import android.os.Looper;
import com.xiaomi.xms.wearable.Wearable;
import com.xiaomi.xms.wearable.auth.Permission;
import com.xiaomi.xms.wearable.message.MessageApi;
import com.xiaomi.xms.wearable.message.OnMessageReceivedListener;
import com.xiaomi.xms.wearable.node.Node;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;

/** Production receive path, synthetic PCM, mocked Android/SDK boundaries only. */
public final class ReceiverServiceHostTest {
    private static int assertions,serial;
    private static final String ID="0123456789abcdef",HASH="fedcba9876543210";
    private static final byte[] PCM={1,2,3,4};
    private static void check(boolean b,String reason){assertions++;if(!b)throw new AssertionError(reason);}
    private static <T>T last(List<T> values){check(!values.isEmpty(),"expected SDK call");return values.get(values.size()-1);}
    private static JSONObject snapshot()throws Exception{return new JSONObject(ReceiverService.snapshot());}
    private static JSONObject diagnostic()throws Exception{return new JSONObject(ReceiverService.diagnostics());}
    private static void worker()throws Exception{
        for(int n=0;n<3;n++){CountDownLatch done=new CountDownLatch(1);ReceiverService.submit(done::countDown);check(done.await(3,TimeUnit.SECONDS),"disk worker must finish");Looper.drain();}
    }
    private static ReceiverService start(String action)throws Exception{ReceiverService s=new ReceiverService();s.onCreate();worker();s.onStartCommand(new Intent(s,ReceiverService.class).setAction(action),0,1);Looper.drain();return s;}
    private static void discover(boolean explicit)throws Exception{
        last(Wearable.nodes.queries).success(Arrays.asList(new Node("watch-a")));Looper.drain();
        last(Wearable.auth.checks).success(!explicit);Looper.drain();
        if(explicit){check(Wearable.auth.requests.size()==1,"only visible first connect opens authorization");last(Wearable.auth.requests).success(Arrays.asList(Permission.DEVICE_MANAGER));Looper.drain();}
        last(Wearable.nodes.installs).success(true);Looper.drain();last(Wearable.messages.adds).task.success(null);Looper.drain();
    }
    private static OnMessageReceivedListener receiver(){return last(Wearable.messages.adds).listener;}
    private static JSONObject request(String action)throws Exception{return new JSONObject().put("v",1).put("protocol","w6r1").put("id","host-"+(++serial)).put("action",action).put("recording_id",ID);}
    private static JSONObject offer()throws Exception{return request("recorder_offer").put("complete",true).put("sample_rate",16000).put("total_bytes",PCM.length).put("archive_hash",HASH).put("pcm_crc32",ArchiveStore.checksum(PCM));}
    private static JSONObject chunk()throws Exception{return request("recorder_chunk").put("offset",0).put("data",Base64.getEncoder().encodeToString(PCM)).put("crc32",ArchiveStore.checksum(PCM));}
    private static JSONObject finish()throws Exception{return request("recorder_finish").put("total_bytes",PCM.length).put("archive_hash",HASH).put("pcm_crc32",ArchiveStore.checksum(PCM));}
    private static JSONObject receive(JSONObject request)throws Exception{
        int before=Wearable.messages.sends.size();int syncs=AndroidDirectorySync.calls;
        receiver().onMessageReceived("watch-a",request.toString().getBytes(StandardCharsets.UTF_8));Looper.drain();worker();
        check(Wearable.messages.sends.size()==before+1,"one actual SDK ACK for handled request");MessageApi.Send sent=last(Wearable.messages.sends);JSONObject ack=new JSONObject(new String(sent.bytes,StandardCharsets.UTF_8));
        check(request.getString("id").equals(ack.getString("request_id")),"ACK correlates original watch request");
        if(!"recorder_hello".equals(request.optString("action"))&&ack.optBoolean("ok"))check(AndroidDirectorySync.calls>syncs,"successful storage ACK follows directory durability edge");
        sent.task.success(null);Looper.drain();return ack;
    }
    private static ArchiveStore store()throws Exception{return new ArchiveStore(new File(System.getProperty("test.files"),"recordings"),d->{});}
    private static void completeRoundTrip()throws Exception{
        JSONObject hello=receive(request("recorder_hello"));check(hello.getBoolean("ok")&&"ready".equals(hello.getString("phase")),"valid hello gets protocol ready ACK");
        check(snapshot().getBoolean("connected")&&diagnostic().getBoolean("application_ready"),"only validated protocol makes watch communication ready");
        JSONObject offered=receive(offer());check(offered.getLong("durable")==0&&!offered.getBoolean("complete"),"offer ACK is durable frontier zero");
        JSONObject packet=receive(chunk());check(packet.getLong("durable")==PCM.length&&!packet.getBoolean("complete"),"chunk ACK follows actual checkpoint");
        check(store().status(ID).next==PCM.length&&!store().status(ID).complete,"checkpoint agrees with wire ACK");
        JSONObject saved=receive(finish());check(saved.getBoolean("complete")&&"saved".equals(saved.getString("phase")),"only complete verified WAV gets saved ACK");
        byte[] wav=Files.readAllBytes(store().audio(ID).toPath());check(wav.length==44+PCM.length&&Arrays.equals(Arrays.copyOfRange(wav,44,wav.length),PCM),"stored WAV preserves every synthetic PCM byte");
    }
    private static CountDownLatch blockWorker()throws Exception{CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);ReceiverService.submit(()->{entered.countDown();try{if(!release.await(5,TimeUnit.SECONDS))throw new AssertionError("worker blocker timed out");}catch(InterruptedException e){throw new AssertionError(e);}});check(entered.await(3,TimeUnit.SECONDS),"controlled disk worker blocker entered");return release;}
    private static void firstAuthorizationRoundtrip()throws Exception{ReceiverService s=start("connect");discover(true);completeRoundTrip();s.onDestroy();Looper.drain();}
    private static void listenerAndInvalidFrames()throws Exception{
        ReceiverService s=start("connect");discover(false);check(diagnostic().getBoolean("listener_ready"),"listener may receive first protocol frame");check(!snapshot().getBoolean("connected")&&!diagnostic().getBoolean("application_ready"),"SDK registration alone cannot claim watch handshake");
        receiver().onMessageReceived("watch-a","{\"v\":1,\"protocol\":\"random\",\"id\":\"bad\"}".getBytes(StandardCharsets.UTF_8));Looper.drain();worker();check(Wearable.messages.sends.isEmpty()&&!snapshot().getBoolean("connected"),"unrelated JSON cannot cause ACK or verified connection");
        JSONObject invalid=receive(request("not_a_recorder_action"));check(!invalid.getBoolean("ok")&&!snapshot().getBoolean("connected"),"invalid recorder operation cannot verify connection");
        receive(request("recorder_hello"));check(snapshot().getBoolean("connected"),"first valid hello can pass listening gate and complete handshake");s.onDestroy();Looper.drain();
    }
    private static void restoreRoundtrip()throws Exception{
        ReceiverService old=start("connect");discover(true);receive(offer());receive(chunk());OnMessageReceivedListener stale=receiver();old.onDestroy();Looper.drain();last(Wearable.messages.removes).task.success(null);Looper.drain();
        java.lang.reflect.Field field=ReceiverService.class.getDeclaredField("store");field.setAccessible(true);field.set(null,null);
        ReceiverService restored=start("restore");discover(false);check(Wearable.auth.requests.size()==1,"enabled service restore never reopens authorization");
        int before=Wearable.messages.sends.size();stale.onMessageReceived("watch-a",finish().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();worker();check(Wearable.messages.sends.size()==before&&!store().status(ID).complete,"destroyed service callback cannot finish a new service session");
        JSONObject ack=receive(offer());check(ack.getLong("durable")==PCM.length,"restored actual store resumes from durable bytes");receive(finish());check(store().status(ID).complete,"restore completes existing recording without identity launch");restored.onDestroy();Looper.drain();
    }
    private static void disableQueuedFrame()throws Exception{
        ReceiverService s=start("connect");discover(false);receive(offer());int before=Wearable.messages.sends.size();CountDownLatch release=blockWorker();
        receiver().onMessageReceived("watch-a",chunk().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();s.onStartCommand(new Intent(s,ReceiverService.class).setAction("disable"),0,2);Looper.drain();release.countDown();worker();
        check(store().status(ID).next==0,"queued callback cannot write audio after user closes reception");check(Wearable.messages.sends.size()==before,"disabled reception cannot ACK queued old frame");check(!snapshot().getBoolean("enabled")&&!snapshot().getBoolean("connected"),"disable invalidates visible service state before delayed Android destruction");check(new File(System.getProperty("test.files"),"recordings/"+ID+"/state.properties").isFile(),"disable retains prior durable recording checkpoint");s.onDestroy();Looper.drain();
    }
    private static void staleSessionQueuedFrame()throws Exception{
        ReceiverService s=start("connect");discover(false);receive(offer());int before=Wearable.messages.sends.size();CountDownLatch release=blockWorker();OnMessageReceivedListener stale=receiver();
        stale.onMessageReceived("watch-a",chunk().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();last(Wearable.service.listeners).onServiceDisconnected();Looper.drain();last(Wearable.messages.removes).task.success(null);Looper.drain();last(Wearable.service.listeners).onServiceConnected();Looper.drain();discover(false);release.countDown();worker();
        check(store().status(ID).next==0,"queued frame from invalidated link cannot write in new link session");check(Wearable.messages.sends.size()==before,"old disk work cannot ACK under new SDK listener");
        stale.onMessageReceived("watch-a",chunk().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();worker();check(store().status(ID).next==0,"old SDK callback cannot reach new session");
        receive(chunk());receive(finish());check(store().status(ID).complete,"fresh SDK session may resume retained checkpoint");s.onDestroy();Looper.drain();
    }
    private static void disableAfterDurableWrite()throws Exception{
        ReceiverService s=start("connect");discover(false);receive(offer());int before=Wearable.messages.sends.size();
        CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);AndroidDirectorySync.release=release;AndroidDirectorySync.entered=entered;
        receiver().onMessageReceived("watch-a",chunk().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();check(entered.await(3,TimeUnit.SECONDS),"in-flight chunk reaches actual checkpoint durability boundary");
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("disable"),0,2);Looper.drain();release.countDown();worker();
        check(store().status(ID).next==PCM.length&&!store().status(ID).complete,"closing reception retains bytes already committed by an in-flight storage operation");
        check(Wearable.messages.sends.size()==before,"disabled in-flight completion cannot ACK into a retired session");check(!snapshot().getBoolean("connected")&&!snapshot().getBoolean("enabled"),"in-flight completion cannot revive disabled UI");s.onDestroy();Looper.drain();
    }
    private static void disableReconnectSameService()throws Exception{
        ReceiverService s=start("connect");discover(false);receive(offer());receive(chunk());OnMessageReceivedListener stale=receiver();int queries=Wearable.nodes.queries.size(),adds=Wearable.messages.adds.size();
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("disable"),0,2);
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("connect"),0,3);Looper.drain();
        check(Wearable.nodes.queries.size()==queries+1,"disable then connect on the same service must restart SDK discovery before Android onDestroy");
        last(Wearable.nodes.queries).success(Arrays.asList(new Node("watch-a")));Looper.drain();last(Wearable.auth.checks).success(true);Looper.drain();last(Wearable.nodes.installs).success(true);Looper.drain();
        check(Wearable.messages.adds.size()==adds,"new link waits for old SDK listener removal instead of racing its slot");last(Wearable.messages.removes).task.success(null);Looper.drain();
        check(Wearable.messages.adds.size()==adds+1,"successful owned removal admits the replacement listener");last(Wearable.messages.adds).task.success(null);Looper.drain();
        int before=Wearable.messages.sends.size();stale.onMessageReceived("watch-a",finish().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();worker();
        check(Wearable.messages.sends.size()==before&&!store().status(ID).complete,"old callback cannot ACK or finish after same-service reconnection");
        check(receive(offer()).getLong("durable")==PCM.length,"same-service re-enable preserves durable recording progress");receive(finish());check(store().status(ID).complete,"replacement link can finish the preserved recording");s.onDestroy();Looper.drain();
    }
    private static void disableAfterAckQueued()throws Exception{
        ReceiverService s=start("connect");discover(false);receive(offer());int before=Wearable.messages.sends.size();CountDownLatch release=blockWorker();
        receiver().onMessageReceived("watch-a",chunk().toString().getBytes(StandardCharsets.UTF_8));Looper.drain();release.countDown();
        CountDownLatch completed=new CountDownLatch(1);ReceiverService.submit(completed::countDown);check(completed.await(3,TimeUnit.SECONDS),"actual protocol storage completes before the main-thread result is dispatched");
        Looper.once();Looper.once();check(snapshot().getLong("durable")==PCM.length,"main result already committed and queued its confirmation and send");
        check(Wearable.messages.sends.size()==before,"SDK ACK is still queued behind the main result");
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("disable"),0,2);Looper.drain();worker();
        check(Wearable.messages.sends.size()==before,"disable must invalidate a posted ACK before SDK dispatch, even after main result passed its lease guard");
        check(!snapshot().getBoolean("enabled")&&!snapshot().getBoolean("connected"),"queued protocol confirmation cannot revive disabled reception");check(store().status(ID).next==PCM.length,"closing the ACK dispatch gap preserves the committed recording bytes");s.onDestroy();Looper.drain();
    }
    private static void durabilityFailure()throws Exception{
        ReceiverService s=start("connect");discover(false);AndroidDirectorySync.fail=true;JSONObject rejected=receive(offer());check(!rejected.getBoolean("ok")&&rejected.getLong("durable")==0&&!rejected.getBoolean("complete"),"failed directory durability may only return negative ACK");check(!snapshot().getBoolean("connected"),"failed handler does not claim verified watch communication");check("IOException".equals(diagnostic().optString("last_storage_error_kind")),"diagnostic preserves storage exception kind without paths or audio");check("receive".equals(diagnostic().optString("last_storage_action")),"diagnostic limits storage action to known enum");s.onDestroy();Looper.drain();
    }
    private static void finishFromPhone()throws Exception{
        ReceiverService s=start("connect");discover(false);receive(offer());
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("finish").putExtra("id",ID),0,2);worker();
        check(!store().status(ID).complete,"phone action must not finalize partial audio");
        receive(chunk());int sends=Wearable.messages.sends.size();
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("disable"),0,3);Looper.drain();
        s.onStartCommand(new Intent(s,ReceiverService.class).setAction("finish").putExtra("id",ID),0,4);worker();
        check(store().status(ID).complete,"received bytes can be finalized locally without reconnecting watch");
        check(store().audio(ID).length()==PCM.length+44,"local save produces verified full WAV");
        check(Wearable.messages.sends.size()==sends,"local save never sends SDK ACK without a watch request");s.onDestroy();Looper.drain();
    }
    public static void main(String[]args)throws Exception{
        switch(args[0]){case "finish_from_phone":finishFromPhone();break;case "first_authorization_roundtrip":firstAuthorizationRoundtrip();break;case "listener_and_invalid_frames":listenerAndInvalidFrames();break;case "restore_roundtrip":restoreRoundtrip();break;case "disable_queued_frame":disableQueuedFrame();break;case "disable_after_durable_write":disableAfterDurableWrite();break;case "disable_reconnect_same_service":disableReconnectSameService();break;case "disable_after_ack_queued":disableAfterAckQueued();break;case "stale_session_queued_frame":staleSessionQueuedFrame();break;case "durability_failure":durabilityFailure();break;default:throw new AssertionError("unknown scenario");}
        System.out.println(new JSONObject().put("scenario",args[0]).put("assertions",assertions).put("passed",true).put("physical_verified",false));
    }
}
