"""Run actual Fitness PhoneLink/WatchListenerLease with deterministic SDK edges.

The SDK Tasks, Android handler clock and permission boundary are doubles. No
radio, MiFitness service, microphone, Android device or production method is
reimplemented. Every scenario runs in a fresh JVM to isolate the static lease.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
STUBS={
'android.Manifest':'''public final class Manifest {public static final class permission {public static final String BLUETOOTH_CONNECT="connect";}}''',
'android.content.pm.PackageManager':'''public final class PackageManager {public static final int PERMISSION_GRANTED=0,PERMISSION_DENIED=-1;}''',
'android.os.SystemClock':'''public final class SystemClock {public static long now=100;public static long elapsedRealtime(){return now;}}''',
'android.os.Looper':'''public final class Looper {
 static final class Event {long when,order;Runnable task;Handler owner;Event(Handler h,Runnable r,long t){owner=h;task=r;when=t;order=++serial;}}
 static long serial;static final Thread OWNER=Thread.currentThread();static final Looper MAIN=new Looper();static final java.util.ArrayList<Event> tasks=new java.util.ArrayList<>();
 public static Looper getMainLooper(){return MAIN;}
 public static Looper myLooper(){return Thread.currentThread()==OWNER?MAIN:null;}
 public static void drain(){until(SystemClock.now);}
 public static void once(){Event next=null;for(Event e:tasks)if(e.when<=SystemClock.now&&(next==null||e.when<next.when||e.when==next.when&&e.order<next.order))next=e;if(next!=null){tasks.remove(next);next.task.run();}}
 public static void advance(long ms){until(SystemClock.now+ms);}
 private static void until(long end){for(int n=0;n<20000;n++){Event next=null;for(Event e:tasks)if(e.when<=end&&(next==null||e.when<next.when||e.when==next.when&&e.order<next.order))next=e;if(next==null){SystemClock.now=end;return;}tasks.remove(next);SystemClock.now=Math.max(SystemClock.now,next.when);next.task.run();}throw new AssertionError("unbounded task loop");}
 public static int pending(){return tasks.size();}}
''',
'android.os.Handler':'''public final class Handler {public Handler(Looper l){}public boolean post(Runnable r){return postDelayed(r,0);}public boolean postDelayed(Runnable r,long ms){Looper.tasks.add(new Looper.Event(this,r,SystemClock.now+ms));return true;}public void removeCallbacks(Runnable r){Looper.tasks.removeIf(e->e.owner==this&&e.task==r);}public void removeCallbacksAndMessages(Object o){if(o==null)Looper.tasks.removeIf(e->e.owner==this);}}''',
'android.content.SharedPreferences':'''public interface SharedPreferences {String getString(String k,String d);Editor edit();interface Editor {Editor putString(String k,String v);boolean commit();void apply();}}''',
'android.content.Context':'''public final class Context {public boolean granted=true;private final java.util.Map<String,String> data=new java.util.HashMap<>();private final SharedPreferences prefs=new SharedPreferences(){public String getString(String k,String d){return data.getOrDefault(k,d);}public Editor edit(){return new Editor(){public Editor putString(String k,String v){data.put(k,v);return this;}public boolean commit(){return true;}public void apply(){}};}};public Context getApplicationContext(){return this;}public int checkSelfPermission(String p){return granted?0:-1;}public SharedPreferences getSharedPreferences(String n,int m){return prefs;}}''',
'com.xiaomi.xms.wearable.Task':'''public final class Task<T> {
 private final java.util.List<java.util.function.Consumer<T>> success=new java.util.ArrayList<>();private final java.util.List<java.util.function.Consumer<Exception>> failure=new java.util.ArrayList<>();
 public Task<T> addOnSuccessListener(java.util.function.Consumer<T> l){success.add(l);return this;}public Task<T> addOnFailureListener(java.util.function.Consumer<Exception> l){failure.add(l);return this;}
 public void success(T value){for(java.util.function.Consumer<T> l:new java.util.ArrayList<>(success))l.accept(value);}public void fail(Exception error){for(java.util.function.Consumer<Exception> l:new java.util.ArrayList<>(failure))l.accept(error);}}
''',
'com.xiaomi.xms.wearable.node.Node':'''public final class Node {public String id;public Node(String id){this.id=id;}}''',
'com.xiaomi.xms.wearable.node.NodeApi':'''public final class NodeApi {
 public final java.util.List<com.xiaomi.xms.wearable.Task<java.util.List<Node>>> queries=new java.util.ArrayList<>();public final java.util.List<com.xiaomi.xms.wearable.Task<Boolean>> installs=new java.util.ArrayList<>();public final java.util.List<String> installTargets=new java.util.ArrayList<>();
 public com.xiaomi.xms.wearable.Task<java.util.List<Node>> getConnectedNodes(){com.xiaomi.xms.wearable.Task<java.util.List<Node>> t=new com.xiaomi.xms.wearable.Task<>();queries.add(t);return t;}
 public com.xiaomi.xms.wearable.Task<Boolean> isWearAppInstalled(String node){installTargets.add(node);com.xiaomi.xms.wearable.Task<Boolean> t=new com.xiaomi.xms.wearable.Task<>();installs.add(t);return t;}}
''',
'com.xiaomi.xms.wearable.auth.Permission':'''public final class Permission {public static final Permission DEVICE_MANAGER=new Permission("device_manager");private final String name;public Permission(String n){name=n;}public String getName(){return name;}}''',
'com.xiaomi.xms.wearable.auth.AuthApi':'''public final class AuthApi {
 public int throwRequests;
 public final java.util.List<com.xiaomi.xms.wearable.Task<Boolean>> checks=new java.util.ArrayList<>();public final java.util.List<com.xiaomi.xms.wearable.Task<java.util.List<Permission>>> requests=new java.util.ArrayList<>();
 public com.xiaomi.xms.wearable.Task<Boolean> checkPermission(String node,Permission p){com.xiaomi.xms.wearable.Task<Boolean> t=new com.xiaomi.xms.wearable.Task<>();checks.add(t);return t;}
 public com.xiaomi.xms.wearable.Task<java.util.List<Permission>> requestPermission(String node,Permission p){if(throwRequests>0){throwRequests--;throw new IllegalStateException("test synchronous authorization failure");}com.xiaomi.xms.wearable.Task<java.util.List<Permission>> t=new com.xiaomi.xms.wearable.Task<>();requests.add(t);return t;}}
''',
'com.xiaomi.xms.wearable.message.OnMessageReceivedListener':'''public interface OnMessageReceivedListener {void onMessageReceived(String sender,byte[] bytes);}''',
'com.xiaomi.xms.wearable.message.MessageApi':'''public final class MessageApi {
 public static final class Add {public final String node;public final OnMessageReceivedListener listener;public final com.xiaomi.xms.wearable.Task<Void> task=new com.xiaomi.xms.wearable.Task<>();Add(String n,OnMessageReceivedListener l){node=n;listener=l;}}
 public static final class Remove {public final String node;public final com.xiaomi.xms.wearable.Task<Void> task=new com.xiaomi.xms.wearable.Task<>();Remove(String n){node=n;}}
 public static final class Send {public final String node;public final byte[] bytes;public final com.xiaomi.xms.wearable.Task<Void> task=new com.xiaomi.xms.wearable.Task<>();Send(String n,byte[] b){node=n;bytes=b.clone();}}
 public final java.util.List<Add> adds=new java.util.ArrayList<>();public final java.util.List<Remove> removes=new java.util.ArrayList<>();public final java.util.List<Send> sends=new java.util.ArrayList<>();
 public com.xiaomi.xms.wearable.Task<Void> addListener(String n,OnMessageReceivedListener l){Add a=new Add(n,l);adds.add(a);return a.task;}
 public com.xiaomi.xms.wearable.Task<Void> removeListener(String n){Remove r=new Remove(n);removes.add(r);return r.task;}
 public com.xiaomi.xms.wearable.Task<Void> sendMessage(String n,byte[] b){Send s=new Send(n,b);sends.add(s);return s.task;}}
''',
'com.xiaomi.xms.wearable.service.OnServiceConnectionListener':'''public interface OnServiceConnectionListener {void onServiceConnected();void onServiceDisconnected();}''',
'com.xiaomi.xms.wearable.service.ServiceApi':'''public final class ServiceApi {public final java.util.List<OnServiceConnectionListener> listeners=new java.util.ArrayList<>();public int registrations,unregistrations,failRegistrations;public void registerServiceConnectionListener(OnServiceConnectionListener l){registrations++;if(failRegistrations>0){failRegistrations--;throw new IllegalStateException("test registration failure");}listeners.add(l);}public void unregisterServiceConnectionListener(OnServiceConnectionListener l){unregistrations++;listeners.remove(l);}}''',
'com.xiaomi.xms.wearable.Wearable':'''public final class Wearable {public static final com.xiaomi.xms.wearable.message.MessageApi messages=new com.xiaomi.xms.wearable.message.MessageApi();public static final com.xiaomi.xms.wearable.node.NodeApi nodes=new com.xiaomi.xms.wearable.node.NodeApi();public static final com.xiaomi.xms.wearable.auth.AuthApi auth=new com.xiaomi.xms.wearable.auth.AuthApi();public static final com.xiaomi.xms.wearable.service.ServiceApi service=new com.xiaomi.xms.wearable.service.ServiceApi();public static boolean unavailable;public static int getters;private static void check(){getters++;if(unavailable)throw new IllegalStateException("test unavailable");}public static com.xiaomi.xms.wearable.message.MessageApi getMessageApi(android.content.Context c){check();return messages;}public static com.xiaomi.xms.wearable.node.NodeApi getNodeApi(android.content.Context c){check();return nodes;}public static com.xiaomi.xms.wearable.auth.AuthApi getAuthApi(android.content.Context c){check();return auth;}public static com.xiaomi.xms.wearable.service.ServiceApi getServiceApi(android.content.Context c){check();return service;}}''',
}
SCENARIOS=['restore_no_authorization','explicit_authorization','nearby_permission','identity_missing','duplicate_connect','backoff','stale_discovery','receive_ownership','close_pending_listener','listener_timeout_late_success','reply_queue_bound','stale_send_token','stale_send_generation','receive_queue_bound','health_frequency','health_timeout','service_registration_retry','permission_revoked','authorization_throw','authorization_intent_consumed','listener_is_not_handshake','authorization_intent_not_replayed','listener_explicit_recheck']
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--scenario',choices=SCENARIOS);args=parser.parse_args()
 path=ROOT/'.local-build.json';config=json.loads(path.read_text(encoding='utf-8-sig'))if path.is_file()else{}
 java=Path(os.environ.get('JAVA_HOME',config.get('java_home','')));jar=Path(os.environ.get('W6R_JSON_TEST_JAR',config.get('json_test_jar','')));suffix='.exe'if os.name=='nt'else''
 if not jar.is_file():raise SystemExit('Provide authorized W6R_JSON_TEST_JAR for JVM tests')
 production=[ROOT/'src/com/watch6/recorder'/n for n in ['PhoneLink.java','WatchListenerLease.java']]
 with tempfile.TemporaryDirectory(prefix='w6r-fitness-callback-')as directory:
  out=Path(directory);files=[]
  for name,code in STUBS.items():
   package,_=name.rsplit('.',1);target=out/(name.replace('.','/')+'.java');target.parent.mkdir(parents=True,exist_ok=True);target.write_text('package '+package+';\n'+code,encoding='utf-8');files.append(target)
  files+=production+[ROOT/'tests/FitnessPhoneLinkHostTest.java']
  result=subprocess.run([str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-classpath',str(jar),'-d',str(out),*map(str,files)],capture_output=True,text=True,encoding='utf-8',errors='replace');assert result.returncode==0,result.stderr
  reports=[]
  for scenario in [args.scenario]if args.scenario else SCENARIOS:
   result=subprocess.run([str(java/('bin/java'+suffix)),'-cp',os.pathsep.join([str(out),str(jar)]),'com.watch6.recorder.FitnessPhoneLinkHostTest',scenario],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
   assert result.returncode==0,scenario+'\n'+result.stderr
   reports.append(json.loads(result.stdout))
 report=dict(passed=True,cases=len(reports),assertions=sum(r['assertions']for r in reports),scenarios=reports,actual_phone_link=True,actual_listener_lease=True,sdk_callbacks_mocked=True,device_accessed=False,radio_simulated=False,physical_verified=False,production_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in production})
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
