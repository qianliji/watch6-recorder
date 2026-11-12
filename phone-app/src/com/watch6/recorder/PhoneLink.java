package com.watch6.recorder;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import com.xiaomi.xms.wearable.Wearable;
import com.xiaomi.xms.wearable.auth.AuthApi;
import com.xiaomi.xms.wearable.auth.Permission;
import com.xiaomi.xms.wearable.message.MessageApi;
import com.xiaomi.xms.wearable.message.OnMessageReceivedListener;
import com.xiaomi.xms.wearable.node.Node;
import com.xiaomi.xms.wearable.node.NodeApi;
import com.xiaomi.xms.wearable.service.OnServiceConnectionListener;
import com.xiaomi.xms.wearable.service.ServiceApi;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.json.JSONObject;

/** Own MiFitness listener. SDK authorization can only follow a visible action. */
final class PhoneLink {
    interface Listener {void state(String text,boolean ready);void message(byte[] bytes,long lease);}
    private static final int MESSAGE_LIMIT=16,REPLY_LIMIT=8;
    private static final long[] RETRY={1000,3000,10000,30000,60000};
    private static final WatchListenerLease LEASE=new WatchListenerLease(SystemClock::elapsedRealtime);
    private final Context context;private final Listener listener;private final Handler main=new Handler(Looper.getMainLooper());
    private final AtomicInteger queued=new AtomicInteger();private final ArrayDeque<String> replies=new ArrayDeque<>();
    private final AtomicBoolean closing=new AtomicBoolean();
    private MessageApi messages;private NodeApi nodes;private AuthApi auth;private ServiceApi service;
    private String node,preferred;private boolean enabled,discovering,registered,subscribed,sending,allowAuth;
    private volatile boolean alive=true,ready;private boolean peerConfirmed;private volatile long publishedLease=1;private volatile String diagnosticJson="{}";
    private long generation=1,query,sendSerial,lastReceived,lastSent,rxPackets,txPackets,dropped;
    private int retry,lastError;private String phase="idle";
    private Runnable recovery,deadline,sendDeadline,health,healthDeadline;
    PhoneLink(Context c,Listener l){context=c.getApplicationContext();listener=l;preferred=context.getSharedPreferences("recorder",0).getString("fitness_node","");publish();}
    private boolean permission(){return context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED;}
    boolean accepts(long lease){return alive&&ready&&publishedLease==lease;}
    String diagnostics(){return diagnosticJson;}
    void connect(boolean authorize){main.post(()->{
        if(!alive)return;enabled=true;allowAuth|=authorize;
        if(!permission()){allowAuth=false;invalidate();cancelRecovery();status("permission_required","请允许附近设备权限，才能保持手表录音接收",false,601);return;}
        if(ready){if(authorize&&!peerConfirmed){invalidate();retry=0;cancelRecovery();initialize();return;}allowAuth=false;status(peerConfirmed?"ready":"listener_ready",peerConfirmed?"已确认手表录音通信":"接收已待命，请在手表导出录音",true,0);return;}
        if(discovering)return;
        if(authorize){retry=0;cancelRecovery();}
        initialize();
    });}
    private void status(String p,String text,boolean connected,int code){phase=p;ready=connected;if(code!=0)lastError=code;listener.state(text,connected&&peerConfirmed);publish();}
    private void publish(){try{
        diagnosticJson=new JSONObject().put("version","0.5.1").put("transport","mifitness_sdk").put("phase",phase).put("enabled",enabled).put("sdk_initialized",messages!=null).put("service_listener_registered",registered).put("listener_ready",subscribed).put("application_ready",ready&&peerConfirmed).put("checking",discovering).put("retry_stage",retry).put("callback_queue",queued.get()).put("reply_queue",replies.size()).put("rx_packets",rxPackets).put("tx_packets",txPackets).put("dropped_packets",dropped).put("last_receive_elapsed_ms",lastReceived).put("last_send_elapsed_ms",lastSent).put("last_error_code",lastError).put("identity_required",true).put("contains_device_identifier",false).put("contains_audio",false).toString();
    }catch(Exception ignored){}
    }
    private boolean current(long g,long q){return alive&&enabled&&g==generation&&q==query;}
    private long begin(long timeout,boolean installing){
        clear();long g=generation,q=query;
        deadline=()->{if(!current(g,q))return;deadline=null;
            if(installing){invalidate();status("listener_pending","正在等待运动健康确认连接，录音仍在手表上",false,402);schedule();return;}
            query++;discovering=false;status("retrying","连接检查较慢，正在后台重试",false,111);schedule();
        };main.postDelayed(deadline,timeout);return q;
    }
    private void clear(){if(deadline!=null)main.removeCallbacks(deadline);deadline=null;query++;}
    private void cancelRecovery(){if(recovery!=null)main.removeCallbacks(recovery);recovery=null;}
    private void schedule(){
        allowAuth=false;
        if(!alive||!enabled||ready||recovery!=null)return;
        long delay=RETRY[Math.min(retry++,RETRY.length-1)];
        recovery=()->{recovery=null;initialize();};main.postDelayed(recovery,delay);publish();
    }
    private void invalidate(){
        generation++;publishedLease=generation;ready=false;peerConfirmed=false;lastReceived=0;clear();LEASE.release(this);discovering=subscribed=sending=false;node=null;
        replies.clear();sendSerial++;if(sendDeadline!=null)main.removeCallbacks(sendDeadline);sendDeadline=null;
        if(health!=null)main.removeCallbacks(health);health=null;
        if(healthDeadline!=null)main.removeCallbacks(healthDeadline);healthDeadline=null;
    }
    private final OnServiceConnectionListener connection=new OnServiceConnectionListener(){
        public void onServiceConnected(){main.post(()->{if(!alive||!enabled||ready||discovering)return;cancelRecovery();initialize();});}
        public void onServiceDisconnected(){main.post(()->{if(!alive||!enabled)return;invalidate();status("service_disconnected","运动健康连接已断开，正在自动重连",false,112);schedule();});}
    };
    private void initialize(){
        if(!alive||!enabled||ready||discovering)return;
        if(!permission()){cancelRecovery();status("permission_required","附近设备权限已关闭，请在手机设置中允许",false,601);return;}
        try{
            if(messages==null){
                MessageApi m=Wearable.getMessageApi(context);NodeApi n=Wearable.getNodeApi(context);AuthApi a=Wearable.getAuthApi(context);ServiceApi s=Wearable.getServiceApi(context);
                messages=m;nodes=n;auth=a;service=s;
            }
            if(!registered){service.registerServiceConnectionListener(connection);registered=true;}
            discovering=true;long g=generation,q=begin(10000,false);status("connecting","正在连接运动健康",false,0);
            nodes.getConnectedNodes().addOnSuccessListener(list->main.post(()->{
                if(!current(g,q))return;clear();String candidate=choose(list);
                if(candidate==null){discovering=false;status("watch_unavailable",list==null||list.isEmpty()?"正在等待手表连接运动健康":"运动健康连接了多块手表，请仅保留目标手表",false,113);schedule();return;}
                permission(candidate,g);
            })).addOnFailureListener(error->main.post(()->{if(current(g,q)){clear();discovering=false;status("retrying","运动健康尚未准备好，正在自动重试",false,114);schedule();}}));
        }catch(Exception unavailable){clear();discovering=false;status("fitness_unavailable","请先安装小米运动健康并连接手表",false,101);schedule();}
    }
    private String choose(List<Node> list){
        if(list==null)return null;
        if(!preferred.isEmpty())for(Node n:list)if(n!=null&&preferred.equals(n.id))return n.id;
        return list.size()==1&&list.get(0)!=null&&list.get(0).id!=null&&!list.get(0).id.isEmpty()?list.get(0).id:null;
    }
    private void permission(String candidate,long g){
        long q=begin(10000,false);
        try{auth.checkPermission(candidate,Permission.DEVICE_MANAGER).addOnSuccessListener(granted->main.post(()->{
            if(!current(g,q))return;clear();
            if(Boolean.TRUE.equals(granted)){allowAuth=false;subscribe(candidate,g);return;}
            if(!allowAuth){discovering=false;retry=RETRY.length-1;status("authorization_required","首次请点“开启接收”完成运动健康授权",false,201);schedule();return;}
            allowAuth=false;long rq=begin(60000,false);status("authorizing","请在运动健康授权页面允许手表通信",false,0);
            try{auth.requestPermission(candidate,Permission.DEVICE_MANAGER).addOnSuccessListener(values->main.post(()->{
                if(!current(g,rq))return;clear();boolean grantedNow=false;if(values!=null)for(Permission p:values)if(p!=null&&Permission.DEVICE_MANAGER.getName().equals(p.getName()))grantedNow=true;
                if(grantedNow)subscribe(candidate,g);else{discovering=false;retry=RETRY.length-1;status("authorization_required","手表通信尚未获准，准备好后点“开启接收”重试",false,202);schedule();}
            })).addOnFailureListener(error->main.post(()->{if(current(g,rq)){clear();discovering=false;retry=RETRY.length-1;status("authorization_required","授权尚未完成，准备好后点“开启接收”重试",false,203);schedule();}}));}
            catch(Exception unavailable){if(current(g,rq)){clear();discovering=false;retry=RETRY.length-1;status("authorization_required","授权暂时无法打开，请在手机点“开启接收”重试",false,203);schedule();}}
        })).addOnFailureListener(error->main.post(()->{if(current(g,q)){clear();discovering=false;status("retrying","暂时无法核对手表授权，正在重试",false,204);schedule();}}));}
        catch(Exception unavailable){clear();discovering=false;status("retrying","手表通信暂不可用，正在自动重连",false,205);schedule();}
    }
    private void subscribe(String candidate,long g){
        long q=begin(10000,false);status("checking_identity","正在核对手表连接组件",false,0);
        try{nodes.isWearAppInstalled(candidate).addOnSuccessListener(installed->main.post(()->{
            if(!current(g,q))return;clear();
            if(!Boolean.TRUE.equals(installed)){discovering=false;retry=RETRY.length-1;status("identity_required","首次请在手表安装录音连接组件；日常无需打开",false,301);schedule();return;}
            long sq=begin(12000,true);status("subscribing","正在建立录音接收通道",false,0);
            OnMessageReceivedListener receiver=(sender,bytes)->{
                if(bytes==null||bytes.length<2||bytes.length>4096||!candidate.equals(sender)){dropped++;return;}
                if(queued.incrementAndGet()>MESSAGE_LIMIT){queued.decrementAndGet();dropped++;return;}
                byte[] owned=bytes.clone();
                main.post(()->{try{if(alive&&ready&&subscribed&&generation==g&&candidate.equals(node)){
                    if(!permission()){invalidate();status("permission_required","附近设备权限已关闭，请在手机设置中允许",false,601);return;}
                    rxPackets++;lastReceived=SystemClock.elapsedRealtime();listener.message(owned,g);publish();
                }}finally{queued.decrementAndGet();}});
            };
            LEASE.acquire(this,g,candidate,new WatchListenerLease.Port(){
                public void add(String target,WatchListenerLease.Result result){messages.addListener(target,receiver).addOnSuccessListener(v->result.complete(null)).addOnFailureListener(result::complete);}
                public void remove(String target,WatchListenerLease.Result result){messages.removeListener(target).addOnSuccessListener(v->result.complete(null)).addOnFailureListener(result::complete);}
            },(r,delay)->main.postDelayed(r,delay),new WatchListenerLease.Completion(){
                public void ready(){if(!current(g,sq))return;clear();node=candidate;preferred=candidate;context.getSharedPreferences("recorder",0).edit().putString("fitness_node",candidate).apply();subscribed=true;discovering=false;retry=0;allowAuth=false;peerConfirmed=false;publishedLease=g;cancelRecovery();status("listener_ready","接收已待命，请在手表导出录音",true,0);armHealth();pump();}
                public void failed(Exception error){if(current(g,sq)){clear();discovering=false;status("retrying","手表连接未完成，正在后台重试",false,401);schedule();}}
            });
        })).addOnFailureListener(error->main.post(()->{if(current(g,q)){clear();discovering=false;status("retrying","暂时无法核对连接组件，正在重试",false,302);schedule();}}));}
        catch(Exception unavailable){clear();discovering=false;status("retrying","手表连接暂不可用，正在自动重试",false,303);schedule();}
    }
    /** Called only after the receive worker has successfully handled w6r1. */
    void confirmed(long lease){main.post(()->{if(!accepts(lease))return;peerConfirmed=true;status("ready","已确认手表录音通信",true,0);});}
    private void armHealth(){
        if(health!=null)main.removeCallbacks(health);long g=generation;
        health=()->{health=null;if(!alive||!enabled||!ready||g!=generation)return;
            if(!permission()){invalidate();status("permission_required","附近设备权限已关闭，请在手机设置中允许",false,601);return;}
            if(lastReceived>0&&SystemClock.elapsedRealtime()-lastReceived<60000){armHealth();return;}
            healthDeadline=()->{healthDeadline=null;if(alive&&g==generation&&ready){invalidate();status("retrying","连接检查较慢，正在后台恢复",false,111);schedule();}};main.postDelayed(healthDeadline,10000);
            try{nodes.getConnectedNodes().addOnSuccessListener(list->main.post(()->{
                if(!alive||g!=generation||!ready)return;if(healthDeadline!=null)main.removeCallbacks(healthDeadline);healthDeadline=null;boolean present=false;if(list!=null)for(Node n:list)if(n!=null&&node.equals(n.id))present=true;
                if(present)armHealth();else{invalidate();status("watch_unavailable","手表暂时离线，正在等待自动连接",false,113);schedule();}
            })).addOnFailureListener(error->main.post(()->{if(alive&&g==generation&&ready){invalidate();status("retrying","运动健康连接暂不可用，正在自动重连",false,114);schedule();}}));}
            catch(Exception unavailable){invalidate();status("retrying","运动健康连接暂不可用，正在自动重连",false,114);schedule();}
        };main.postDelayed(health,60000);
    }
    void send(String payload,long lease){
        if(payload==null)return;
        main.post(()->{if(!alive||!accepts(lease)||node==null||payload.getBytes(StandardCharsets.UTF_8).length>4096)return;
            if(!permission()){invalidate();status("permission_required","附近设备权限已关闭，请在手机设置中允许",false,601);return;}
            if(replies.size()>=REPLY_LIMIT){dropped++;publish();return;}
            replies.addLast(payload);publish();pump();
        });
    }
    private void pump(){
        if(!alive||!ready||sending||node==null||replies.isEmpty())return;
        String payload=replies.removeFirst();sending=true;long token=++sendSerial,g=generation;
        sendDeadline=()->{if(!alive||g!=generation||token!=sendSerial)return;sending=false;sendDeadline=null;status(peerConfirmed?"ready":"listener_ready","确认回传较慢，请在手表重新导出以续传",true,502);pump();};main.postDelayed(sendDeadline,10000);
        try{messages.sendMessage(node,payload.getBytes(StandardCharsets.UTF_8)).addOnSuccessListener(v->main.post(()->finishSend(g,token,true))).addOnFailureListener(error->main.post(()->finishSend(g,token,false)));}
        catch(Exception unavailable){finishSend(g,token,false);}
    }
    private void finishSend(long g,long token,boolean success){
        if(!alive||g!=generation||token!=sendSerial)return;if(sendDeadline!=null)main.removeCallbacks(sendDeadline);sendDeadline=null;sending=false;
        if(success){txPackets++;lastSent=SystemClock.elapsedRealtime();}else lastError=501;
        publish();pump();
    }
    void close(){
        if(!closing.compareAndSet(false,true))return;
        // Reject work already posted by the disk result before returning to the caller.
        alive=false;ready=false;
        Runnable retire=()->{enabled=false;invalidate();cancelRecovery();if(registered)try{service.unregisterServiceConnectionListener(connection);}catch(Exception ignored){}registered=false;phase="closed";publish();};
        if(Looper.myLooper()==Looper.getMainLooper())retire.run();else main.post(retire);
    }
}
