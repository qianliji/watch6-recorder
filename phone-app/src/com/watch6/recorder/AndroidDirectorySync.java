package com.watch6.recorder;
import android.system.Os;
import android.system.OsConstants;
import java.io.*;
final class AndroidDirectorySync implements ArchiveStore.DirectorySync {
    public void sync(File directory) throws IOException {
        FileDescriptor fd=null;
        try{fd=Os.open(directory.getAbsolutePath(),OsConstants.O_RDONLY,0);Os.fsync(fd);}
        catch(Exception error){throw new IOException("手机保存确认未完成，手表原音保留");}
        finally{if(fd!=null)try{Os.close(fd);}catch(Exception ignored){}}
    }
}
