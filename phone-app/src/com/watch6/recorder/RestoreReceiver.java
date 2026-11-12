package com.watch6.recorder;
import android.Manifest;
import android.content.*;
import android.content.pm.PackageManager;
public final class RestoreReceiver extends BroadcastReceiver {
    public void onReceive(Context context,Intent intent){
        if(intent==null||!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())&&!Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()))return;
        if(context.getSharedPreferences("recorder",0).getBoolean("enabled",false)&&context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)==PackageManager.PERMISSION_GRANTED)ReceiverService.command(context,"restore",null);
    }
}
