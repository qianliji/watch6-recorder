package com.watch6.recorder;
import android.content.*;
import android.database.*;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;
import java.util.*;
/** Only the user-selected finalized recording gets a read URI grant. */
public final class RecordingProvider extends ContentProvider {
    static Uri uri(String id){return Uri.parse("content://com.watch6.recorder.exports/recordings/"+id);}
    private File file(Uri uri) throws FileNotFoundException {
        try{List<String> parts=uri.getPathSegments();if(parts.size()!=2||!"recordings".equals(parts.get(0))||!ArchiveStore.validId(parts.get(1)))throw new IOException();return ReceiverService.audio(getContext(),parts.get(1));}
        catch(Exception error){throw new FileNotFoundException("Saved recording unavailable");}
    }
    public boolean onCreate(){return true;}
    public String getType(Uri uri){return "audio/wav";}
    public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {if(!"r".equals(mode))throw new FileNotFoundException("Read only");return ParcelFileDescriptor.open(file(uri),ParcelFileDescriptor.MODE_READ_ONLY);}
    public Cursor query(Uri uri,String[] projection,String selection,String[] args,String sort){try{File f=file(uri);String[] columns=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;MatrixCursor result=new MatrixCursor(columns);Object[] row=new Object[columns.length];for(int i=0;i<columns.length;i++)row[i]=OpenableColumns.DISPLAY_NAME.equals(columns[i])?"Watch6-Recording.wav":OpenableColumns.SIZE.equals(columns[i])?f.length():null;result.addRow(row);return result;}catch(FileNotFoundException error){return null;}}
    public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException("Read only");}
    public int delete(Uri uri,String selection,String[] args){throw new UnsupportedOperationException("Read only");}
    public int update(Uri uri,ContentValues values,String selection,String[] args){throw new UnsupportedOperationException("Read only");}
}
