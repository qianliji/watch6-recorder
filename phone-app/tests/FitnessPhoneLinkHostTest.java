package com.watch6.recorder;

import android.content.Context;
import android.os.Looper;
import com.xiaomi.xms.wearable.Wearable;
import com.xiaomi.xms.wearable.Task;
import com.xiaomi.xms.wearable.auth.Permission;
import com.xiaomi.xms.wearable.message.MessageApi;
import com.xiaomi.xms.wearable.message.OnMessageReceivedListener;
import com.xiaomi.xms.wearable.node.Node;
import com.xiaomi.xms.wearable.service.OnServiceConnectionListener;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.json.JSONObject;

/** SDK boundary doubles drive actual PhoneLink and actual WatchListenerLease. */
public final class FitnessPhoneLinkHostTest {
    private static int assertions;
    private static void check(boolean value,String reason){assertions++;if(!value)throw new AssertionError(reason);}
    private static void drain(){Looper.drain();}
    private static <T> T last(List<T> values){check(!values.isEmpty(),"expected SDK call");return values.get(values.size()-1);}
    private static final class Environment implements PhoneLink.Listener {
        final Context context=new Context();final List<byte[]> received=new ArrayList<>();final List<Long> leases=new ArrayList<>();
        final PhoneLink link=new PhoneLink(context,this);boolean ready;String text;
        public void state(String message,boolean connected){text=message;ready=connected;}
        public void message(byte[] bytes,long lease){received.add(bytes);leases.add(lease);}
        void connect(boolean authorize){link.connect(authorize);drain();}
        OnServiceConnectionListener service(){return last(Wearable.service.listeners);}
        void nodes(){last(Wearable.nodes.queries).success(Arrays.asList(new Node("watch-a")));drain();}
        void permitted(){last(Wearable.auth.checks).success(Boolean.TRUE);drain();}
        void installed(){last(Wearable.nodes.installs).success(Boolean.TRUE);drain();}
        void added(){last(Wearable.messages.adds).task.success(null);drain();}
        void ready(){connect(false);nodes();permitted();installed();added();check(listening(),"listener should become ready");}
        OnMessageReceivedListener receiver(){return last(Wearable.messages.adds).listener;}
        long receive(){receiver().onMessageReceived("watch-a",new byte[]{1,2,3});drain();check(!leases.isEmpty(),"message should arrive");long lease=last(leases);check(link.accepts(lease),"published message lease should be active");return lease;}
        void disconnect(){service().onServiceDisconnected();drain();check(!ready&&!listening(),"disconnect must clear ready");}
        void remove(){last(Wearable.messages.removes).task.success(null);drain();}
        void reconnect(){service().onServiceConnected();drain();nodes();permitted();installed();added();check(listening(),"known receiver should reconnect");}
        JSONObject diagnostics()throws Exception{return new JSONObject(link.diagnostics());}
        boolean listening(){try{return diagnostics().getBoolean("listener_ready");}catch(Exception e){throw new AssertionError(e);}}
    }
    private static void restoreNoAuthorization()throws Exception {
        Environment e=new Environment();e.connect(false);e.nodes();last(Wearable.auth.checks).success(false);drain();
        check(Wearable.auth.requests.isEmpty(),"background restore must not open SDK authorization");check(!e.ready,"unapproved channel not ready");
        int queries=Wearable.nodes.queries.size();Looper.advance(59999);check(Wearable.nodes.queries.size()==queries,"missing authorization should use low-frequency retry");
        Looper.advance(1);e.nodes();last(Wearable.auth.checks).success(false);drain();check(Wearable.auth.requests.isEmpty(),"automatic retry must remain passive");
    }
    private static void explicitAuthorization(){
        Environment e=new Environment();e.connect(true);e.nodes();last(Wearable.auth.checks).success(false);drain();check(Wearable.auth.requests.size()==1,"visible connect may authorize once");
        last(Wearable.auth.requests).success(Arrays.asList(Permission.DEVICE_MANAGER));drain();e.installed();e.added();check(e.listening(),"authorized listener ready");
        e.connect(false);check(Wearable.auth.requests.size()==1&&Wearable.nodes.queries.size()==1,"ready restore is idempotent");
    }
    private static void nearbyPermission(){
        Environment e=new Environment();e.context.granted=false;e.connect(true);check(Wearable.getters==0,"without OS permission SDK must not initialize");Looper.advance(180000);check(Wearable.getters==0,"missing OS permission must not poll");e.link.close();e.link.close();drain();check(Wearable.service.unregistrations==0,"unregistered service must not be removed");
    }
    private static void identityMissing(){
        Environment e=new Environment();e.connect(false);e.nodes();e.permitted();last(Wearable.nodes.installs).success(false);drain();check(Wearable.messages.adds.isEmpty(),"missing identity cannot add listener");check(Wearable.auth.requests.isEmpty(),"missing identity must not authorize in background");int queries=Wearable.nodes.queries.size();Looper.advance(59999);check(Wearable.nodes.queries.size()==queries,"missing identity retry is low frequency");
    }
    private static void duplicateConnect(){
        Environment e=new Environment();for(int i=0;i<20;i++)e.link.connect(false);drain();check(Wearable.nodes.queries.size()==1,"parallel connect calls share one discovery");check(Wearable.service.registrations==1,"service listener installed once");e.service().onServiceConnected();drain();check(Wearable.nodes.queries.size()==1,"service signal does not duplicate active discovery");e.nodes();e.permitted();e.installed();e.added();for(int i=0;i<20;i++)e.link.connect(false);drain();check(Wearable.messages.adds.size()==1,"ready reconnect does not replace known listener");
    }
    private static void backoff(){
        Environment e=new Environment();e.connect(false);long[] delays={1000,3000,10000,30000,60000,60000};
        for(long delay:delays){Task<List<Node>> task=last(Wearable.nodes.queries);task.fail(new IllegalStateException("test unavailable"));drain();int before=Wearable.nodes.queries.size();Looper.advance(delay-1);check(Wearable.nodes.queries.size()==before,"retry must not run early");Looper.advance(1);check(Wearable.nodes.queries.size()==before+1,"retry must run at bounded backoff");}
        check(Wearable.auth.requests.isEmpty(),"failure retries never request authorization");
    }
    private static void staleDiscovery(){
        Environment e=new Environment();e.connect(false);Task<List<Node>> stale=last(Wearable.nodes.queries);e.disconnect();stale.success(Arrays.asList(new Node("watch-a")));drain();check(Wearable.auth.checks.isEmpty(),"disconnected discovery callback must be ignored");e.service().onServiceConnected();drain();e.nodes();e.permitted();e.installed();e.added();stale.success(Arrays.asList(new Node("wrong-watch")));drain();check(Wearable.auth.checks.size()==1&&e.listening(),"old discovery cannot replace current peer");
    }
    private static void receiveOwnership(){
        Environment e=new Environment();e.ready();OnMessageReceivedListener old=e.receiver();byte[] bytes={7,8,9};old.onMessageReceived("watch-a",bytes);bytes[0]=99;drain();check(e.received.size()==1&&e.received.get(0)[0]==7,"callback payload must be owned before posting");long lease=last(e.leases);e.disconnect();check(!e.link.accepts(lease),"disconnect immediately invalidates lease");old.onMessageReceived("watch-a",new byte[]{1,2});drain();check(e.received.size()==1,"old receiver cannot deliver after disconnect");e.remove();e.reconnect();long fresh=e.receive();check(fresh!=lease,"new session must have a new lease");old.onMessageReceived("watch-a",new byte[]{1,2});drain();check(e.received.size()==2,"old receiver cannot inject into new session");e.link.send("old",lease);drain();check(Wearable.messages.sends.isEmpty(),"old lease cannot send");e.link.send("new",fresh);drain();check(Wearable.messages.sends.size()==1,"current lease can send");
    }
    private static void closePendingListener(){
        Environment e=new Environment();e.connect(false);e.nodes();e.permitted();e.installed();MessageApi.Add old=last(Wearable.messages.adds);OnServiceConnectionListener staleService=e.service();e.link.close();drain();check(Wearable.service.unregistrations==1,"close unregisters only owned service listener");old.task.success(null);drain();check(!e.listening()&&Wearable.messages.removes.size()==1,"late successful add must be removed after close");old.listener.onMessageReceived("watch-a",new byte[]{1,2});staleService.onServiceConnected();drain();check(e.received.isEmpty()&&Wearable.nodes.queries.size()==1,"closed callbacks cannot reactivate instance");
        Environment next=new Environment();next.connect(false);next.nodes();next.permitted();next.installed();check(Wearable.messages.adds.size()==1,"new instance must wait for stale slot removal");e.remove();check(Wearable.messages.adds.size()==2,"known successful remove releases next listener");next.added();check(next.listening(),"new instance ready after serialized cleanup");
    }
    private static void listenerTimeoutLateSuccess(){
        Environment e=new Environment();e.connect(false);e.nodes();e.permitted();e.installed();MessageApi.Add old=last(Wearable.messages.adds);Looper.advance(12000);check(!e.listening(),"pending add timeout cannot report ready");Looper.advance(1000);e.nodes();e.permitted();e.installed();check(Wearable.messages.adds.size()==1,"pending add cannot be raced by another add");old.task.success(null);drain();check(Wearable.messages.removes.size()==1&&!e.listening(),"late timed-out add gets explicit cleanup");e.remove();check(Wearable.messages.adds.size()==2,"cleanup permits latest listener add");e.added();check(e.listening(),"latest listener connects after timeout recovery");old.listener.onMessageReceived("watch-a",new byte[]{1,2});drain();check(e.received.isEmpty(),"timed-out receiver cannot enter current session");
    }
    private static void replyQueueBound()throws Exception {
        Environment e=new Environment();e.ready();long lease=e.receive();for(int i=0;i<12;i++)e.link.send("reply-"+i,lease);drain();check(Wearable.messages.sends.size()==1,"only one send is in flight");check(e.diagnostics().getInt("reply_queue")==8,"reply queue bounded at eight");check(e.diagnostics().getLong("dropped_packets")>=3,"overflow is refused rather than evicting accepted replies");
        for(int i=0;i<9;i++){check(Wearable.messages.sends.size()==i+1,"one completion permits one next reply");MessageApi.Send send=Wearable.messages.sends.get(i);check(new String(send.bytes,StandardCharsets.UTF_8).equals("reply-"+i),"accepted reply order preserved");send.task.success(null);drain();}check(Wearable.messages.sends.size()==9,"refused replies are not later sent");
    }
    private static void staleSendToken(){
        Environment e=new Environment();e.ready();long lease=e.receive();e.link.send("first",lease);e.link.send("second",lease);drain();MessageApi.Send old=last(Wearable.messages.sends);Looper.advance(10000);check(Wearable.messages.sends.size()==2,"send timeout permits next bounded reply");e.link.send("third",lease);drain();old.task.success(null);drain();check(Wearable.messages.sends.size()==2,"old completion cannot release current frame");Wearable.messages.sends.get(1).task.success(null);drain();check(Wearable.messages.sends.size()==3,"current completion permits third reply");
    }
    private static void staleSendGeneration(){
        Environment e=new Environment();e.ready();long oldLease=e.receive();e.link.send("old",oldLease);drain();MessageApi.Send stale=last(Wearable.messages.sends);e.disconnect();e.remove();e.reconnect();long fresh=e.receive();e.link.send("new",fresh);e.link.send("tail",fresh);drain();check(Wearable.messages.sends.size()==2,"new generation has one in-flight reply");stale.task.success(null);drain();check(Wearable.messages.sends.size()==2&&!e.link.accepts(oldLease),"previous generation cannot drain new queue");Wearable.messages.sends.get(1).task.success(null);drain();check(Wearable.messages.sends.size()==3,"new generation completion drains its own queue");
    }
    private static void receiveQueueBound()throws Exception {
        Environment e=new Environment();e.ready();OnMessageReceivedListener receiver=e.receiver();for(int i=0;i<40;i++)receiver.onMessageReceived("watch-a",new byte[]{1,2});receiver.onMessageReceived("wrong-peer",new byte[]{1,2});receiver.onMessageReceived("watch-a",new byte[4097]);drain();check(e.received.size()==16,"inbound posted callbacks bounded at sixteen");check(e.diagnostics().getLong("dropped_packets")>=24,"inbound overflow is visible");
    }
    private static void healthFrequency(){
        Environment e=new Environment();e.ready();long lease=e.receive();int initial=Wearable.nodes.queries.size();Looper.advance(59999);check(Wearable.nodes.queries.size()==initial,"health does not poll while idle faster than 60s");Looper.advance(1);check(Wearable.nodes.queries.size()==initial+1,"quiet ready link has one health query");e.nodes();Looper.advance(59000);e.receive();Looper.advance(1000);check(Wearable.nodes.queries.size()==initial+1,"recent received traffic skips health IPC");Looper.advance(60000);check(Wearable.nodes.queries.size()==initial+2,"health resumes after traffic quiets");last(Wearable.nodes.queries).success(Collections.emptyList());drain();check(!e.link.accepts(lease),"health absence invalidates old lease");Looper.advance(1000);check(Wearable.nodes.queries.size()==initial+3,"health disconnect schedules recovery");
    }
    private static void healthTimeout(){
        Environment e=new Environment();e.ready();long lease=e.receive();Looper.advance(60000);int before=Wearable.nodes.queries.size();Looper.advance(10000);check(!e.link.accepts(lease),"lost health callback must invalidate stale channel");Looper.advance(1000);check(Wearable.nodes.queries.size()==before+1,"health deadline recovers without UI");
    }
    private static void serviceRegistrationRetry(){
        Environment e=new Environment();Wearable.service.failRegistrations=1;e.connect(false);check(Wearable.service.registrations==1,"initial service registration attempted");Looper.advance(1000);check(Wearable.service.registrations==2,"failed registration is retried");e.nodes();e.permitted();e.installed();e.added();check(e.listening(),"registration retry can complete normal flow");
    }
    private static void permissionRevoked(){
        Environment e=new Environment();e.ready();long lease=e.receive();e.context.granted=false;e.link.send("denied",lease);drain();check(Wearable.messages.sends.isEmpty(),"revoked nearby permission blocks send");check(!e.link.accepts(lease),"revocation invalidates current lease");int queries=Wearable.nodes.queries.size();Looper.advance(180000);check(Wearable.nodes.queries.size()==queries,"revocation does not keep polling SDK");
    }
    private static void authorizationThrow(){
        Environment e=new Environment();e.connect(true);e.nodes();Wearable.auth.throwRequests=1;last(Wearable.auth.checks).success(false);drain();check(!e.ready&&Wearable.auth.requests.isEmpty(),"synchronous authorization exception must be contained");int queries=Wearable.nodes.queries.size();Looper.advance(59999);check(Wearable.nodes.queries.size()==queries,"authorization failure must not hot loop");Looper.advance(1);e.nodes();last(Wearable.auth.checks).success(false);drain();check(Wearable.auth.requests.isEmpty(),"failed explicit authorization is not replayed in background");
    }
    private static void authorizationIntentConsumed(){
        Environment e=new Environment();e.connect(true);e.nodes();e.permitted();last(Wearable.nodes.installs).success(false);drain();Looper.advance(60000);e.nodes();last(Wearable.auth.checks).success(false);drain();check(Wearable.auth.requests.isEmpty(),"already granted authorization must consume old explicit intent before identity retry");
    }
    private static void listenerIsNotHandshake()throws Exception {
        Environment e=new Environment();e.connect(false);e.nodes();e.permitted();e.installed();e.added();
        check(e.diagnostics().getBoolean("listener_ready"),"installed listener may receive the first frame");
        check(!e.ready&&!e.diagnostics().getBoolean("application_ready"),"listener registration is not a verified watch protocol handshake");
    }
    private static void authorizationIntentNotReplayed(){
        Environment e=new Environment();e.connect(true);last(Wearable.nodes.queries).success(Collections.emptyList());drain();
        Looper.advance(1000);e.nodes();last(Wearable.auth.checks).success(false);drain();
        check(Wearable.auth.requests.isEmpty(),"discovery retry may not replay an old visible authorization intent in background");
    }
    private static void listenerExplicitRecheck(){
        Environment e=new Environment();e.ready();int before=Wearable.nodes.queries.size();e.connect(true);
        check(Wearable.nodes.queries.size()==before+1&&!e.listening(),"visible check connection refreshes SDK discovery instead of echoing a stale waiting status");
        e.nodes();e.permitted();e.installed();e.remove();e.added();check(e.listening()&&!e.ready,"explicit recheck restores passive listener without inventing protocol confirmation");
    }
    public static void main(String[] args)throws Exception {
        String scenario=args[0];switch(scenario){
            case "restore_no_authorization":restoreNoAuthorization();break;case "explicit_authorization":explicitAuthorization();break;case "nearby_permission":nearbyPermission();break;case "identity_missing":identityMissing();break;case "duplicate_connect":duplicateConnect();break;case "backoff":backoff();break;case "stale_discovery":staleDiscovery();break;case "receive_ownership":receiveOwnership();break;case "close_pending_listener":closePendingListener();break;case "listener_timeout_late_success":listenerTimeoutLateSuccess();break;case "reply_queue_bound":replyQueueBound();break;case "stale_send_token":staleSendToken();break;case "stale_send_generation":staleSendGeneration();break;case "receive_queue_bound":receiveQueueBound();break;case "health_frequency":healthFrequency();break;case "health_timeout":healthTimeout();break;case "service_registration_retry":serviceRegistrationRetry();break;case "permission_revoked":permissionRevoked();break;case "authorization_throw":authorizationThrow();break;case "authorization_intent_consumed":authorizationIntentConsumed();break;case "listener_is_not_handshake":listenerIsNotHandshake();break;case "authorization_intent_not_replayed":authorizationIntentNotReplayed();break;case "listener_explicit_recheck":listenerExplicitRecheck();break;default:throw new AssertionError("unknown scenario");
        }
        System.out.println(new JSONObject().put("scenario",scenario).put("assertions",assertions).put("passed",true).put("device_accessed",false).put("sdk_boundary_mocked",true));
    }
}
