"""Actual SDK callback -> ReceiverService -> Protocol -> ArchiveStore -> SDK ACK.

Android lifecycle/SDK Tasks and directory fsync are deterministic host edges.
File contents, file fsync, protocol validation and checkpoints use production
code. Synthetic PCM only; no device, radio, microphone or real recording access.
"""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, tempfile
from run_fitness_host import STUBS as LINK_STUBS

ROOT = Path(__file__).resolve().parents[1]
STUBS = dict(LINK_STUBS)
STUBS['android.os.Looper'] = STUBS['android.os.Looper'].replace('java.util.ArrayList<Event>', 'java.util.concurrent.CopyOnWriteArrayList<Event>').replace('new java.util.ArrayList<>()', 'new java.util.concurrent.CopyOnWriteArrayList<>()')
STUBS.update({
'android.content.SharedPreferences': '''public interface SharedPreferences {String getString(String k,String d);boolean getBoolean(String k,boolean d);Editor edit();interface Editor {Editor putString(String k,String v);Editor putBoolean(String k,boolean v);boolean commit();void apply();}}''',
'android.content.Context': '''public class Context {
 public static final String AUDIO_SERVICE="audio",POWER_SERVICE="power";public static boolean granted=true;private static final java.util.Map<String,String> data=new java.util.concurrent.ConcurrentHashMap<>();
 private static final SharedPreferences prefs=new SharedPreferences(){public String getString(String k,String d){return data.getOrDefault(k,d);}public boolean getBoolean(String k,boolean d){return Boolean.parseBoolean(data.getOrDefault(k,""+d));}public Editor edit(){return new Editor(){public Editor putString(String k,String v){data.put(k,v);return this;}public Editor putBoolean(String k,boolean v){data.put(k,""+v);return this;}public boolean commit(){return true;}public void apply(){}};}};
 public Context getApplicationContext(){return this;}public int checkSelfPermission(String p){return granted?0:-1;}public SharedPreferences getSharedPreferences(String n,int m){return prefs;}
 public java.io.File getFilesDir(){return new java.io.File(System.getProperty("test.files"));}public String getPackageName(){return "com.watch6.recorder";}
 public Object getSystemService(String n){return AUDIO_SERVICE.equals(n)?new android.media.AudioManager():new android.os.PowerManager();}public <T>T getSystemService(Class<T> c){try{return c.getDeclaredConstructor().newInstance();}catch(Exception e){throw new RuntimeException(e);}}
 public void startForegroundService(Intent i){}
}''',
'android.content.Intent': '''public class Intent {private String action;private final java.util.Map<String,Object> extra=new java.util.HashMap<>();public Intent(Context c,Class<?> t){}public Intent setAction(String a){action=a;return this;}public String getAction(){return action;}public Intent putExtra(String k,String v){extra.put(k,v);return this;}public String getStringExtra(String k){return (String)extra.get(k);}public int getIntExtra(String k,int d){return extra.containsKey(k)?(Integer)extra.get(k):d;}}''',
'android.content.pm.ServiceInfo': '''public final class ServiceInfo {public static final int FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE=16,FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK=2;}''',
'android.app.Service': '''public class Service extends android.content.Context {public static final int START_STICKY=1,START_NOT_STICKY=2;public boolean stopped;public void onCreate(){}public void onDestroy(){}public void startForeground(int n,Notification v,int t){}public void stopSelf(){stopped=true;}}''',
'android.app.Notification': '''public class Notification {public static class Builder {public Builder(android.content.Context c,String s){}public Builder setContentTitle(String s){return this;}public Builder setContentText(String s){return this;}public Builder setSmallIcon(int n){return this;}public Builder setContentIntent(PendingIntent p){return this;}public Builder setOngoing(boolean b){return this;}public Builder addAction(Action a){return this;}public Notification build(){return new Notification();}}public static class Action {public static class Builder {public Builder(Object o,String s,PendingIntent p){}public Action build(){return new Action();}}}}''',
'android.app.NotificationManager': '''public class NotificationManager {public static final int IMPORTANCE_LOW=2;public void createNotificationChannel(NotificationChannel c){}}''',
'android.app.NotificationChannel': '''public class NotificationChannel {public NotificationChannel(String a,String b,int c){}}''',
'android.app.PendingIntent': '''public class PendingIntent {public static final int FLAG_UPDATE_CURRENT=1,FLAG_IMMUTABLE=2;public static PendingIntent getActivity(android.content.Context c,int n,android.content.Intent i,int f){return new PendingIntent();}public static PendingIntent getService(android.content.Context c,int n,android.content.Intent i,int f){return new PendingIntent();}}''',
'android.R': '''public final class R {public static class drawable {public static final int ic_btn_speak_now=1;}}''',
'android.os.IBinder': '''public interface IBinder {}''',
'android.os.PowerManager': '''public class PowerManager {public static final int PARTIAL_WAKE_LOCK=1;public WakeLock newWakeLock(int i,String s){return new WakeLock();}public static class WakeLock {private volatile boolean held;public void setReferenceCounted(boolean b){}public void acquire(long ms){held=true;}public boolean isHeld(){return held;}public void release(){held=false;}}}''',
'android.media.AudioAttributes': '''public class AudioAttributes {public static final int USAGE_MEDIA=1,CONTENT_TYPE_SPEECH=1;public static class Builder {public Builder setUsage(int v){return this;}public Builder setContentType(int v){return this;}public AudioAttributes build(){return new AudioAttributes();}}}''',
'android.media.AudioFocusRequest': '''public class AudioFocusRequest {public static class Builder {public Builder(int i){}public Builder setAudioAttributes(AudioAttributes a){return this;}public Builder setOnAudioFocusChangeListener(java.util.function.IntConsumer l){return this;}public AudioFocusRequest build(){return new AudioFocusRequest();}}}''',
'android.media.AudioManager': '''public class AudioManager {public static final int AUDIOFOCUS_GAIN_TRANSIENT=2,AUDIOFOCUS_REQUEST_GRANTED=1;public int requestAudioFocus(AudioFocusRequest r){return 1;}public void abandonAudioFocusRequest(AudioFocusRequest r){}}''',
'android.media.MediaPlayer': '''public class MediaPlayer {public interface OnErrorListener{boolean onError(MediaPlayer p,int a,int b);}public int getCurrentPosition(){return 0;}public int getDuration(){return 0;}public void setAudioAttributes(AudioAttributes a){}public void setDataSource(String s){}public void setOnPreparedListener(java.util.function.Consumer<MediaPlayer> l){}public void setOnCompletionListener(java.util.function.Consumer<MediaPlayer> l){}public void setOnErrorListener(OnErrorListener l){}public void prepareAsync(){}public void start(){}public void pause(){}public void seekTo(int n){}public void reset(){}public void release(){}}''',
'com.watch6.recorder.MainActivity': '''public class MainActivity {static void notice(String s){}static void refreshSoon(){}}''',
'com.watch6.recorder.AndroidDirectorySync': '''final class AndroidDirectorySync implements ArchiveStore.DirectorySync {static volatile int calls;static volatile boolean fail;static volatile java.util.concurrent.CountDownLatch entered,release;public void sync(java.io.File d)throws java.io.IOException {calls++;java.util.concurrent.CountDownLatch pause=entered;if(pause!=null){entered=null;pause.countDown();try{if(!release.await(5,java.util.concurrent.TimeUnit.SECONDS))throw new java.io.IOException("synthetic sync pause timed out");}catch(InterruptedException e){throw new java.io.IOException(e);}}if(fail)throw new java.io.IOException("synthetic directory sync failure");}}''',
})
SCENARIOS=['finish_from_phone','first_authorization_roundtrip','listener_and_invalid_frames','restore_roundtrip','disable_queued_frame','disable_after_durable_write','disable_reconnect_same_service','disable_after_ack_queued','stale_session_queued_frame','durability_failure']

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--scenario',choices=SCENARIOS);a=p.parse_args()
    c=json.loads((ROOT/'.local-build.json').read_text(encoding='utf-8-sig'));java=Path(os.environ.get('JAVA_HOME',c.get('java_home','')));jar=Path(os.environ.get('W6R_JSON_TEST_JAR',c.get('json_test_jar','')));suffix='.exe'if os.name=='nt'else''
    production=[ROOT/'src/com/watch6/recorder'/n for n in ['PhoneLink.java','WatchListenerLease.java','ReceiverService.java','Protocol.java','ArchiveStore.java']]
    with tempfile.TemporaryDirectory(prefix='w6r-receiver-host-')as td:
        out=Path(td);files=[]
        for name,code in STUBS.items():
            package,_=name.rsplit('.',1);f=out/(name.replace('.','/')+'.java');f.parent.mkdir(parents=True,exist_ok=True);f.write_text('package '+package+';\n'+code,encoding='utf-8');files.append(f)
        proc=subprocess.run([str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-classpath',str(jar),'-d',str(out),*map(str,files+production+[ROOT/'tests/ReceiverServiceHostTest.java'])],capture_output=True,text=True,encoding='utf-8',errors='replace');assert proc.returncode==0,proc.stderr
        reports=[]
        for scenario in [a.scenario]if a.scenario else SCENARIOS:
            root=out/('files-'+scenario);root.mkdir()
            proc=subprocess.run([str(java/('bin/java'+suffix)),'-Dtest.files='+str(root),'-cp',os.pathsep.join([str(out),str(jar)]),'com.watch6.recorder.ReceiverServiceHostTest',scenario],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30);assert proc.returncode==0,scenario+'\n'+proc.stderr
            reports.append(json.loads(proc.stdout))
    report=dict(passed=True,cases=len(reports),assertions=sum(r['assertions']for r in reports),scenarios=reports,actual_receiver_service=True,actual_phone_link=True,actual_protocol=True,actual_archive_store=True,file_fsync=True,directory_fsync='injected host edge',android_lifecycle_and_sdk_mocked=True,physical_verified=False,device_accessed=False,synthetic_pcm_only=True,production_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest()for f in production})
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
