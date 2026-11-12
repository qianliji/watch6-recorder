package com.watch6.recorder;

import android.Manifest;
import android.app.Activity;
import android.content.*;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
import android.webkit.*;
import android.widget.Toast;
import java.io.*;
import java.lang.ref.WeakReference;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.*;

public final class MainActivity extends Activity {
    private static WeakReference<MainActivity> visible=new WeakReference<>(null);
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private WebView web;private boolean alive,refreshPending;
    static void notice(String text){MAIN.post(()->{MainActivity a=visible.get();if(a!=null&&a.alive)Toast.makeText(a,text,Toast.LENGTH_LONG).show();});}
    static void refreshSoon(){MAIN.post(()->{MainActivity a=visible.get();if(a==null||!a.alive||a.refreshPending)return;a.refreshPending=true;MAIN.postDelayed(()->{a.refreshPending=false;if(a.alive&&a.web!=null)a.web.evaluateJavascript("window.refresh&&window.refresh()",null);},250);});}
    public void onCreate(Bundle state){
        super.onCreate(state);getWindow().setStatusBarColor(0xff090909);getWindow().setNavigationBarColor(0xff090909);
        web=new WebView(this);web.setBackgroundColor(0xff090909);web.getSettings().setJavaScriptEnabled(true);web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);web.getSettings().setDomStorageEnabled(false);
        web.addJavascriptInterface(new Bridge(),"Recorder");web.setWebViewClient(new WebViewClient(){public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return !"file:///android_asset/index.html".equals(request.getUrl().toString());}public void onPageFinished(WebView view,String url){view.evaluateJavascript("window.setHostVisible&&window.setHostVisible("+alive+")",null);}});setContentView(web);web.loadUrl("file:///android_asset/index.html");
        ReceiverService.refresh(this);
    }
    protected void onResume(){super.onResume();alive=true;visible=new WeakReference<>(this);if(web!=null)web.evaluateJavascript("window.setHostVisible&&window.setHostVisible(true)",null);ReceiverService.refresh(this);if(getSharedPreferences("recorder",0).getBoolean("enabled",false)&&checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED)ReceiverService.command(this,"restore",null);refreshSoon();}
    protected void onPause(){alive=false;if(web!=null)web.evaluateJavascript("window.setHostVisible&&window.setHostVisible(false)",null);super.onPause();}
    protected void onDestroy(){alive=false;if(web!=null){web.removeJavascriptInterface("Recorder");web.destroy();web=null;}super.onDestroy();}
    private void connect(){
        ArrayList<String> missing=new ArrayList<>();if(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)!=PackageManager.PERMISSION_GRANTED)missing.add(Manifest.permission.BLUETOOTH_CONNECT);
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)missing.add(Manifest.permission.POST_NOTIFICATIONS);
        if(!missing.isEmpty()){requestPermissions(missing.toArray(new String[0]),61);return;}ReceiverService.command(this,"connect",null);
    }
    public void onRequestPermissionsResult(int code,String[] names,int[] granted){super.onRequestPermissionsResult(code,names,granted);if(code==61){if(checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED)ReceiverService.command(this,"connect",null);else notice("需要附近设备权限才能接收手表录音；不申请手机麦克风");}}
    private void openSettings(){
        try{startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())));}catch(Exception unavailable){notice("请在手机设置中检查本应用的附近设备与后台运行权限");}
    }
    private void openFitness(){
        for(String name:new String[]{"com.mi.health","com.xiaomi.wearable"})try{Intent launch=getPackageManager().getLaunchIntentForPackage(name);if(launch!=null){startActivity(launch);return;}}catch(Exception ignored){}
        notice("请先安装并打开小米运动健康，确认手表已连接");
    }
    private void saveDiagnostics(){
        final byte[] bytes=ReceiverService.diagnostics().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        ReceiverService.submit(()->{Uri pending=null;try{
            ContentValues values=new ContentValues();values.put(MediaStore.Downloads.DISPLAY_NAME,"Watch6-connection-diagnostic-"+System.currentTimeMillis()+".json");values.put(MediaStore.Downloads.MIME_TYPE,"application/json");values.put(MediaStore.Downloads.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/Watch6Recorder");values.put(MediaStore.Downloads.IS_PENDING,1);
            pending=getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);if(pending==null)throw new IOException("diagnostic row");
            ParcelFileDescriptor fd=getContentResolver().openFileDescriptor(pending,"w");if(fd==null)throw new IOException("diagnostic descriptor");
            try(ParcelFileDescriptor.AutoCloseOutputStream out=new ParcelFileDescriptor.AutoCloseOutputStream(fd)){out.write(bytes);out.flush();out.getFD().sync();}
            ContentValues done=new ContentValues();done.put(MediaStore.Downloads.IS_PENDING,0);if(getContentResolver().update(pending,done,null,null)!=1)throw new IOException("diagnostic publish");pending=null;notice("连接诊断已保存到 Download/Watch6Recorder");
        }catch(Exception error){notice("诊断保存失败，请稍后重试");}finally{if(pending!=null)try{getContentResolver().delete(pending,null,null);}catch(Exception ignored){}}});
    }
    private void share(String id){
        ReceiverService.submit(()->{try{ReceiverService.audio(this,id);MAIN.post(()->{if(!alive)return;Uri uri=RecordingProvider.uri(id);Intent send=new Intent(Intent.ACTION_SEND).setType("audio/wav").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);send.setClipData(ClipData.newRawUri("Watch6 recording",uri));startActivity(Intent.createChooser(send,"分享完整录音"));});}catch(Exception error){notice("录音尚未完整保存或校验失败，原文件保留");}});
    }
    private void saveDownload(String id){
        ReceiverService.submit(()->{Uri pending=null;
            try{
                File file=ReceiverService.audio(this,id);String expected=ArchiveStore.digest(file);ContentValues values=new ContentValues();
                values.put(MediaStore.Downloads.DISPLAY_NAME,"Watch6-"+new SimpleDateFormat("yyyyMMdd-HHmmss",Locale.ROOT).format(new Date())+"-"+id.substring(8)+".wav");values.put(MediaStore.Downloads.MIME_TYPE,"audio/wav");values.put(MediaStore.Downloads.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/Watch6Recorder");values.put(MediaStore.Downloads.IS_PENDING,1);
                pending=getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);if(pending==null)throw new IOException("Download row unavailable");
                MessageDigest hash=MessageDigest.getInstance("SHA-256");long copied=0;
                ParcelFileDescriptor descriptor=getContentResolver().openFileDescriptor(pending,"w");if(descriptor==null)throw new IOException("Download descriptor unavailable");
                try(FileInputStream in=new FileInputStream(file);ParcelFileDescriptor.AutoCloseOutputStream out=new ParcelFileDescriptor.AutoCloseOutputStream(descriptor)){
                    byte[] buffer=new byte[32768];int n;while((n=in.read(buffer))!=-1){out.write(buffer,0,n);hash.update(buffer,0,n);copied+=n;}out.flush();out.getFD().sync();
                }
                StringBuilder actual=new StringBuilder();for(byte b:hash.digest())actual.append(String.format(Locale.ROOT,"%02x",b&255));if(copied!=file.length()||!actual.toString().equals(expected))throw new IOException("Copy verification failed");
                ContentValues done=new ContentValues();done.put(MediaStore.Downloads.IS_PENDING,0);if(getContentResolver().update(pending,done,null,null)!=1)throw new IOException("Download publish failed");pending=null;notice("已保存到 Download/Watch6Recorder");
            }catch(Exception error){notice("保存下载未完成，应用内原录音仍保留");}
            finally{if(pending!=null)try{getContentResolver().delete(pending,null,null);}catch(Exception ignored){}}
        });
    }
    private final class Bridge {
        @JavascriptInterface public String snapshot(){return ReceiverService.snapshot();}
        @JavascriptInterface public void connect(){MAIN.post(MainActivity.this::connect);}
        @JavascriptInterface public void openSettings(){MAIN.post(MainActivity.this::openSettings);}
        @JavascriptInterface public void openFitness(){MAIN.post(MainActivity.this::openFitness);}
        @JavascriptInterface public void diagnostics(){MAIN.post(MainActivity.this::saveDiagnostics);}
        @JavascriptInterface public void disable(){MAIN.post(()->ReceiverService.command(MainActivity.this,"disable",null));}
        @JavascriptInterface public void refresh(){ReceiverService.refresh(MainActivity.this);}
        @JavascriptInterface public void finish(String id){if(ArchiveStore.validId(id))MAIN.post(()->ReceiverService.command(MainActivity.this,"finish",id));}
        @JavascriptInterface public void play(String id){if(ArchiveStore.validId(id))MAIN.post(()->ReceiverService.command(MainActivity.this,"play",id));}
        @JavascriptInterface public void pause(){MAIN.post(()->ReceiverService.command(MainActivity.this,"pause",null));}
        @JavascriptInterface public void resume(){MAIN.post(()->ReceiverService.command(MainActivity.this,"resume",null));}
        @JavascriptInterface public void stop(){MAIN.post(()->ReceiverService.command(MainActivity.this,"stop_playback",null));}
        @JavascriptInterface public void seek(int position){MAIN.post(()->{Intent i=new Intent(MainActivity.this,ReceiverService.class).setAction("seek").putExtra("position",position);try{startForegroundService(i);}catch(Exception ignored){}});}
        @JavascriptInterface public void share(String id){if(ArchiveStore.validId(id))MainActivity.this.share(id);}
        @JavascriptInterface public void download(String id){if(ArchiveStore.validId(id))MainActivity.this.saveDownload(id);}
    }
}
