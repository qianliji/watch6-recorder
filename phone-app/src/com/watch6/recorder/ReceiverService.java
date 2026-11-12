package com.watch6.recorder;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.*;
import android.os.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

/** Connected-device receive service. No phone microphone or cloud calls. */
public final class ReceiverService extends Service implements PhoneLink.Listener {
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static final ThreadPoolExecutor WORKER=new ThreadPoolExecutor(1,1,0L,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(12),r->{Thread t=new Thread(r,"recorder-disk");t.setDaemon(true);return t;});
    private static volatile ReceiverService current;
    private static ArchiveStore store;
    private static volatile String records="[]";
    private volatile PhoneLink link;private String storageId;
    private volatile String connection="等待连接手表",transferId="",transferState="idle",error="";
    private volatile long next,total;
    private volatile String lastStorageFailure="",lastStorageAction="";
    private volatile boolean connected,enabled;
    private PowerManager.WakeLock wake;private long renewed;
    private Runnable expiry;private MediaPlayer player;private volatile String playingId="",playback="idle";private volatile int positionMs,durationMs;private long playerGeneration;
    private final Runnable playerTick=new Runnable(){public void run(){if(current!=ReceiverService.this||player==null)return;cachePosition();if("playing".equals(playback))MAIN.postDelayed(this,500);}};
    private void cachePosition(){if(player!=null)try{positionMs=player.getCurrentPosition();durationMs=player.getDuration();}catch(Exception ignored){}}
    private AudioManager manager;private AudioFocusRequest focus;
    private static final int NOTIFICATION=6402;
    private static synchronized ArchiveStore archive(Context context) throws IOException {if(store==null)store=new ArchiveStore(new File(context.getFilesDir(),"recordings"),new AndroidDirectorySync());return store;}
    static File audio(Context context,String id) throws IOException{return archive(context).audio(id);}
    static void submit(Runnable job){try{WORKER.execute(job);}catch(RejectedExecutionException busy){MAIN.post(()->MainActivity.notice("保存队列繁忙，请稍后重试"));}}
    static void refresh(Context context){Context app=context.getApplicationContext();submit(()->{try{JSONArray rows=new JSONArray();for(ArchiveStore.Progress p:archive(app).list())rows.put(new JSONObject().put("id",p.id).put("created",p.created).put("bytes",p.next).put("total",p.total).put("sample_rate",p.rate).put("complete",p.complete).put("sha256",p.sha256));records=rows.toString();}catch(Exception ignored){}MAIN.post(MainActivity::refreshSoon);});}
    static String snapshot(){
        try{
            ReceiverService s=current;JSONObject p=new JSONObject().put("connection",s==null?"尚未开启无线接收":s.connection).put("connected",s!=null&&s.connected).put("enabled",s!=null&&s.enabled).put("records",new JSONArray(records));
            if(s!=null){p.put("transfer_id",s.transferId).put("transfer_state",s.transferState).put("durable",s.next).put("total",s.total).put("error",s.error).put("playing_id",s.playingId).put("playback",s.playback);
                p.put("position",s.positionMs).put("duration",s.durationMs).put("connection_phase",s.link==null?"idle":new JSONObject(s.link.diagnostics()).optString("phase","idle"));
            }
            return p.toString();
        }catch(Exception ignored){return "{\"records\":[],\"connection\":\"状态暂不可用\"}";}
    }
    static String diagnostics(){ReceiverService s=current;try{return new JSONObject(s!=null&&s.link!=null?s.link.diagnostics():"{\"transport\":\"mifitness_sdk\",\"enabled\":false,\"identity_required\":true,\"contains_audio\":false}").put("last_storage_error_kind",s==null?"":s.lastStorageFailure).put("last_storage_action",s==null?"":s.lastStorageAction).toString();}catch(Exception unavailable){return "{\"contains_audio\":false}";}}
    static void command(Context context,String action,String id){
        Intent intent=new Intent(context,ReceiverService.class).setAction(action);if(id!=null)intent.putExtra("id",id);
        try{context.startForegroundService(intent);}catch(Exception error){MainActivity.notice("请返回手机页面开启接收，并允许附近设备权限");}
    }
    public void onCreate(){
        super.onCreate();current=this;enabled=getSharedPreferences("recorder",0).getBoolean("enabled",false);manager=(AudioManager)getSystemService(AUDIO_SERVICE);
        NotificationManager nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("recorder_receive","手表录音接收",NotificationManager.IMPORTANCE_LOW));
        try{startForeground(NOTIFICATION,notification(),baseForegroundType());}catch(Exception denied){connection="请允许附近设备权限后开启接收";stopSelf();return;}
        storageId=getSharedPreferences("recorder",0).getString("storage_id","");
        if(storageId.isEmpty()){storageId=UUID.randomUUID().toString();if(!getSharedPreferences("recorder",0).edit().putString("storage_id",storageId).commit()){error="手机存储身份尚未保存";stopSelf();return;}}
        wake=((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,getPackageName()+":file-receive");wake.setReferenceCounted(false);
        link=new PhoneLink(this,this);refresh(this);
    }
    private int baseForegroundType(){return checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED?ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE:ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK;}
    private Notification notification(){
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,ReceiverService.class).setAction("disable"),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this,"recorder_receive").setContentTitle("Watch6 录音").setContentText("playing".equals(playback)?"正在完整回听录音":enabled?"手机待命 · 接收手表录音":"本地录音回听").setSmallIcon(android.R.drawable.ic_btn_speak_now).setContentIntent(open).setOngoing(true).addAction(new Notification.Action.Builder(null,"关闭接收",stop).build()).build();
    }
    private void notifyPlayback(){
        try{int type=baseForegroundType();if(player!=null)type|=ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK;startForeground(NOTIFICATION,notification(),type);}catch(Exception ignored){}
        MainActivity.refreshSoon();
    }
    public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null&&"disable".equals(intent.getAction())){enabled=false;connected=false;connection="无线接收已关闭";getSharedPreferences("recorder",0).edit().putBoolean("enabled",false).apply();if(link!=null){link.close();link=new PhoneLink(this,this);}releaseWake();MainActivity.refreshSoon();stopSelf();return START_NOT_STICKY;}
        if(link==null)return START_NOT_STICKY;
        String action=intent==null?"restore":intent.getAction();String id=intent==null?"":intent.getStringExtra("id");
        if("finish".equals(action))finishRecording(id);
        else if("play".equals(action))play(id);
        else if("pause".equals(action))pause();
        else if("resume".equals(action))resume();
        else if("stop_playback".equals(action))releasePlayer("idle");
        else if("seek".equals(action)&&player!=null&&intent!=null){try{player.seekTo(Math.max(0,Math.min(intent.getIntExtra("position",0),player.getDuration())));cachePosition();}catch(Exception ignored){}}
        else if("connect".equals(action)||"restore".equals(action)){
            if("restore".equals(action)&&!enabled){if(player==null)stopSelf();return START_NOT_STICKY;}
            if(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED){enabled=true;getSharedPreferences("recorder",0).edit().putBoolean("enabled",true).apply();link.connect("connect".equals(action));notifyPlayback();}
            else{connection="请允许附近设备权限后开启接收";if(player==null)stopSelf();}
        }
        return enabled?START_STICKY:START_NOT_STICKY;
    }
    public void state(String text,boolean ready){if(current!=this||!enabled)return;connection=text;connected=ready;MainActivity.refreshSoon();}
    private void renewWake(){
        long now=SystemClock.elapsedRealtime();if(wake!=null&&(!wake.isHeld()||now-renewed>60000)){wake.acquire(180000);renewed=now;}
        if(expiry!=null)MAIN.removeCallbacks(expiry);expiry=()->{if(wake!=null&&wake.isHeld())wake.release();if(current==this&&enabled&&"receiving".equals(transferState)){transferState="paused";connection="接收暂时中断，重新导出会自动续传";MainActivity.refreshSoon();}};MAIN.postDelayed(expiry,150000);
    }
    private void releaseWake(){if(wake!=null&&wake.isHeld())wake.release();if(expiry!=null)MAIN.removeCallbacks(expiry);expiry=null;}
    private boolean accepts(PhoneLink session,long lease){return current==this&&enabled&&link==session&&session!=null&&session.accepts(lease);}
    public void message(byte[] bytes,long lease){
        PhoneLink session=link;if(!accepts(session,lease))return;
        try{WORKER.execute(()->{
            if(!accepts(session,lease))return;
            JSONObject request=null;
            try{
                request=Protocol.decode(bytes);
                if(!accepts(session,lease))return;
                String action=request.optString("action");if(!"recorder_hello".equals(action))MAIN.post(()->{if(accepts(session,lease))renewWake();});
                JSONObject reply=Protocol.handle(archive(this),request,storageId);
                String recording=request.optString("recording_id");
                MAIN.post(()->{
                    if(!accepts(session,lease))return;
                    session.confirmed(lease);
                    if(!"recorder_hello".equals(action)){
                        transferId=recording;next=reply.optLong("durable");total=reply.optLong("total_bytes");transferState=reply.optBoolean("complete")?"saved":"receiving";error="";
                        if(reply.optBoolean("complete")){releaseWake();refresh(this);}else if("recorder_offer".equals(action))refresh(this);
                    }
                    session.send(reply.toString(),lease);MainActivity.refreshSoon();
                });
            }catch(Exception rejected){
                JSONObject failed=request;
                MAIN.post(()->{
                    if(!accepts(session,lease))return;lastStorageFailure=rejected.getClass().getSimpleName();lastStorageAction=failed==null?"decode":("recorder_finish".equals(failed.optString("action"))?"finish":"receive");transferState="error";error="保存未完成，已收到的音频保留。可在录音卡上重试保存。";releaseWake();refresh(this);MainActivity.refreshSoon();
                    if(failed!=null)try{JSONObject response=Protocol.reply(failed,storageId).put("ok",false).put("phase","error").put("next",0).put("durable",0).put("complete",false).put("error",error);session.send(response.toString(),lease);}catch(Exception ignored){}
                });
            }
        });}catch(RejectedExecutionException busy){connection="正在保存上一个数据包，请稍候重试";MainActivity.refreshSoon();}
    }
    private void finishRecording(String id){
        if(!ArchiveStore.validId(id)||("saving".equals(transferState)&&id.equals(transferId)))return;
        transferId=id;transferState="saving";error="";MainActivity.refreshSoon();
        try{WORKER.execute(()->{
            try{
                ArchiveStore.Progress p=archive(this).status(id);
                if(p.next!=p.total)throw new IOException("Audio not fully received");
                ArchiveStore.Progress saved=archive(this).finish(id,p.total,p.archiveHash,p.pcmCrc32);
                MAIN.post(()->{if(current!=this)return;next=saved.next;total=saved.total;transferState="saved";error="";refresh(this);MainActivity.refreshSoon();if(!enabled&&player==null)stopSelf();});
            }catch(Exception failed){MAIN.post(()->{if(current!=this)return;lastStorageFailure=failed.getClass().getSimpleName();lastStorageAction="phone_finish";transferState="error";error="暂未完成保存，原音和接收进度保留。未收齐时请从手表继续发送。";refresh(this);MainActivity.refreshSoon();if(!enabled&&player==null)stopSelf();});}
        });}catch(RejectedExecutionException busy){transferState="error";error="保存队列繁忙，请稍后再试。原音保留。";MainActivity.refreshSoon();}
    }
    private void play(String id){
        if(!ArchiveStore.validId(id))return;long generation=++playerGeneration;releasePlayerInternal();positionMs=durationMs=0;playback="preparing";playingId=id;notifyPlayback();
        submit(()->{File file=null;try{file=audio(this,id);}catch(Exception ignored){}File verified=file;
            MAIN.post(()->{if(current!=this||generation!=playerGeneration)return;if(verified==null){playback="error";error="录音完整性检查未通过，原文件保留";notifyPlayback();return;}
                try{
                    MediaPlayer candidate=new MediaPlayer();player=candidate;candidate.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());candidate.setDataSource(verified.getAbsolutePath());
                    candidate.setOnPreparedListener(p->{if(current!=this||generation!=playerGeneration||p!=player)return;try{if(!gainFocus()){releasePlayer("error");error="其他应用正在使用音频，请稍后回听";return;}p.start();playback="playing";cachePosition();MAIN.post(playerTick);notifyPlayback();}catch(Exception unavailable){releasePlayer("error");error="音频播放暂不可用，原录音保留";}});
                    candidate.setOnCompletionListener(p->{if(p==player){releasePlayer("completed");}});
                    candidate.setOnErrorListener((p,what,extra)->{if(p==player){releasePlayer("error");error="播放失败，录音文件保留";}return true;});notifyPlayback();candidate.prepareAsync();
                }catch(Exception error){releasePlayer("error");ReceiverService.this.error="无法打开录音，原文件保留";}
            });
        });
    }
    private boolean gainFocus(){
        if(focus==null)focus=new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT).setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()).setOnAudioFocusChangeListener(value->{if(value<0)pause();}).build();
        try{return manager.requestAudioFocus(focus)==AudioManager.AUDIOFOCUS_REQUEST_GRANTED;}catch(Exception unavailable){return false;}
    }
    private void pause(){if(player!=null&&"playing".equals(playback))try{player.pause();playback="paused";cachePosition();MAIN.removeCallbacks(playerTick);notifyPlayback();}catch(Exception ignored){}}
    private void resume(){if(player!=null&&"paused".equals(playback)&&gainFocus())try{player.start();playback="playing";cachePosition();MAIN.post(playerTick);notifyPlayback();}catch(Exception ignored){}}
    private void releasePlayerInternal(){MAIN.removeCallbacks(playerTick);if(player!=null){try{player.reset();player.release();}catch(Exception ignored){}player=null;}if(focus!=null&&manager!=null)manager.abandonAudioFocusRequest(focus);}
    private void releasePlayer(String state){playerGeneration++;releasePlayerInternal();playback=state;notifyPlayback();if(!enabled)stopSelf();}
    public IBinder onBind(Intent intent){return null;}
    public void onDestroy(){enabled=false;connected=false;if(current==this)current=null;if(link!=null)link.close();releaseWake();releasePlayerInternal();MAIN.removeCallbacksAndMessages(this);MainActivity.refreshSoon();super.onDestroy();}
}
