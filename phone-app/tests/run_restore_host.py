"""Execute the real boot/update receiver against deterministic Android edges."""
from pathlib import Path
import argparse,json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
STUBS={
 'android/Manifest.java':'package android;public final class Manifest{public static final class permission{public static final String BLUETOOTH_CONNECT="connect";}}',
 'android/content/pm/PackageManager.java':'package android.content.pm;public class PackageManager{public static final int PERMISSION_GRANTED=0;}',
 'android/content/Intent.java':'package android.content;public class Intent{public static final String ACTION_BOOT_COMPLETED="boot",ACTION_MY_PACKAGE_REPLACED="replace";private final String action;public Intent(String a){action=a;}public String getAction(){return action;}}',
 'android/content/SharedPreferences.java':'package android.content;public class SharedPreferences{public boolean enabled;public boolean getBoolean(String key,boolean fallback){return enabled;}}',
 'android/content/Context.java':'package android.content;public class Context{public final SharedPreferences prefs=new SharedPreferences();public boolean granted;public SharedPreferences getSharedPreferences(String name,int mode){return prefs;}public int checkSelfPermission(String permission){return granted?0:-1;}}',
 'android/content/BroadcastReceiver.java':'package android.content;public abstract class BroadcastReceiver{public abstract void onReceive(Context context,Intent intent);}',
 'com/watch6/recorder/ReceiverService.java':'package com.watch6.recorder;import android.content.Context;public class ReceiverService{static int calls;static String action;static void command(Context c,String a,String id){calls++;action=a;if(id!=null)throw new AssertionError("boot may not export audio");}}',
 'com/watch6/recorder/RestoreHostTest.java':'''package com.watch6.recorder;import android.content.*;public class RestoreHostTest{
 static int assertions;static void check(boolean b){assertions++;if(!b)throw new AssertionError("restore assertion "+assertions);}
 public static void main(String[] args){RestoreReceiver r=new RestoreReceiver();Context c=new Context();
 for(String action:new String[]{Intent.ACTION_BOOT_COMPLETED,Intent.ACTION_MY_PACKAGE_REPLACED}){
  for(boolean enabled:new boolean[]{false,true})for(boolean permission:new boolean[]{false,true}){
   c.prefs.enabled=enabled;c.granted=permission;int before=ReceiverService.calls;r.onReceive(c,new Intent(action));
   check(ReceiverService.calls-before==(enabled&&permission?1:0));if(enabled&&permission)check("restore".equals(ReceiverService.action));
  }
 }
 c.prefs.enabled=true;c.granted=true;int before=ReceiverService.calls;r.onReceive(c,null);r.onReceive(c,new Intent("unrelated"));check(before==ReceiverService.calls);
 System.out.println("{\\"passed\\":true,\\"cases\\":9,\\"assertions\\":"+assertions+",\\"physical_verified\\":false}");}}
'''
}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();c=json.loads((ROOT/'.local-build.json').read_text(encoding='utf-8-sig'));java=Path(os.environ.get('JAVA_HOME',c.get('java_home','')));suffix='.exe'if os.name=='nt'else''
 with tempfile.TemporaryDirectory(prefix='w6r-restore-host-')as td:
  out=Path(td);files=[]
  for name,content in STUBS.items():
   f=out/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(content,encoding='utf-8');files.append(f)
  proc=subprocess.run([str(java/('bin/javac'+suffix)),'-encoding','UTF-8','-d',str(out),str(ROOT/'src/com/watch6/recorder/RestoreReceiver.java'),*map(str,files)],capture_output=True,text=True,encoding='utf-8');assert proc.returncode==0,proc.stderr
  proc=subprocess.run([str(java/('bin/java'+suffix)),'-cp',str(out),'com.watch6.recorder.RestoreHostTest'],capture_output=True,text=True,encoding='utf-8',timeout=20);assert proc.returncode==0,proc.stderr;report=json.loads(proc.stdout);report['scope']='production RestoreReceiver with synthetic Android intents, preferences and permission edges; no system boot or device access'
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report))
if __name__=='__main__':main()
