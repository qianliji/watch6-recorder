package com.watch6.recorder;

import java.io.*;
import java.nio.file.*;
import java.nio.channels.FileLock;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.CRC32;

/** Durable, resumable PCM receiver. No Android, network or microphone dependency. */
public final class ArchiveStore {
    public static final long MAX_BYTES=134348800L;
    public static final int CHUNK_BYTES=2048;
    public interface DirectorySync { void sync(File directory) throws IOException; }
    public static final class Progress {
        public final String id,archiveHash,sha256,pcmCrc32;
        public final int rate;
        public final long total,next,created;
        public final boolean complete;
        Progress(State s){id=s.id;archiveHash=s.archiveHash;pcmCrc32=hex(s.expectedCrc);rate=s.rate;total=s.total;next=s.next;created=s.created;complete=s.complete;sha256=s.sha256;}
    }
    private static final class State {
        String id,archiveHash,sha256="";int rate;long total,next,crc,expectedCrc,created;boolean complete;
    }
    private static final int[] TABLE=new int[256];
    static {for(int n=0;n<256;n++){int c=n;for(int k=0;k<8;k++)c=(c>>>1)^((c&1)!=0?0xedb88320:0);TABLE[n]=c;}}
    private final File root;
    private final DirectorySync durability;
    public ArchiveStore(File directory,DirectorySync sync) throws IOException {
        root=directory.getCanonicalFile();durability=Objects.requireNonNull(sync);
        boolean created=false;
        if(!root.isDirectory()){if(root.getParentFile()==null||!root.getParentFile().isDirectory()||!root.mkdir())throw new IOException("Cannot create recording storage");created=true;}
        if(!root.isDirectory()||Files.isSymbolicLink(directory.toPath()))throw new IOException("Unsafe recording storage");
        if(created)durability.sync(root.getParentFile());
    }
    public static boolean validId(String id){return id!=null&&id.matches("[0-9a-f]{16}")&&!id.equals("0000000000000000");}
    public static boolean validHash(String value){return value!=null&&value.matches("[0-9a-f]{16}");}
    private File folder(String id) throws IOException {
        if(!validId(id))throw new IOException("Invalid recording identity");
        File d=new File(root,id);
        if(Files.isSymbolicLink(d.toPath())||!d.getCanonicalPath().equals(root.getPath()+File.separator+id))throw new IOException("Unsafe recording path");
        return d;
    }
    private File member(File d,String name) throws IOException {
        File p=new File(d,name);
        if(Files.isSymbolicLink(p.toPath())||!p.getCanonicalPath().equals(d.getCanonicalPath()+File.separator+name))throw new IOException("Unsafe recording member");
        return p;
    }
    private static long decimal(Properties p,String key,long maximum) throws IOException {
        String value=p.getProperty(key,"");
        if(!value.matches("[0-9]{1,16}"))throw new IOException("Invalid checkpoint");
        try{long n=Long.parseLong(value);if(n>maximum)throw new IOException("Invalid checkpoint");return n;}
        catch(NumberFormatException error){throw new IOException("Invalid checkpoint");}
    }
    private State read(String id) throws IOException {
        File d=folder(id),p=member(d,"state.properties");
        if(!p.isFile()||p.length()>4096)throw new IOException("Recording checkpoint unavailable");
        Properties values=new Properties();try(InputStream in=new FileInputStream(p)){values.load(in);}
        State s=new State();s.id=id;s.rate=(int)decimal(values,"rate",16000);s.total=decimal(values,"total",MAX_BYTES);
        s.next=decimal(values,"next",MAX_BYTES);s.created=decimal(values,"created",9999999999999999L);
        s.archiveHash=values.getProperty("archive_hash","");s.complete="true".equals(values.getProperty("complete"));s.sha256=values.getProperty("sha256","");
        String crc=values.getProperty("crc32",""),expected=values.getProperty("expected_crc32","");if(!crc.matches("[0-9a-f]{8}")||!expected.matches("[0-9a-f]{8}"))throw new IOException("Invalid checkpoint checksum");s.crc=Long.parseLong(crc,16);s.expectedCrc=Long.parseLong(expected,16);
        if(!id.equals(values.getProperty("id"))||!validHash(s.archiveHash)||(s.rate!=8000&&s.rate!=16000)||s.total<2||(s.total&1)!=0||(s.next&1)!=0||s.next>s.total||s.complete&&(s.next!=s.total||!s.sha256.matches("[0-9a-f]{64}")))throw new IOException("Invalid recording checkpoint");
        return s;
    }
    private void write(State s) throws IOException {
        File d=folder(s.id);Properties p=new Properties();p.setProperty("id",s.id);p.setProperty("rate",""+s.rate);p.setProperty("total",""+s.total);
        p.setProperty("next",""+s.next);p.setProperty("created",""+s.created);p.setProperty("archive_hash",s.archiveHash);
        p.setProperty("complete",""+s.complete);p.setProperty("sha256",s.sha256);p.setProperty("crc32",hex(s.crc));p.setProperty("expected_crc32",hex(s.expectedCrc));
        File temp=member(d,"checkpoint.pending");
        try(FileOutputStream out=new FileOutputStream(temp)){p.store(out,"Watch6 Recorder durable transfer checkpoint");out.flush();out.getFD().sync();}
        try{Files.move(temp.toPath(),member(d,"state.properties").toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
        catch(AtomicMoveNotSupportedException unsupported){throw new IOException("Storage does not support atomic checkpoints");}
        durability.sync(d);
    }
    public static String hex(long value){return String.format(Locale.ROOT,"%08x",value&0xffffffffL);}
    private static long appendCrc(long previous,byte[] data){int c=(int)(previous^0xffffffffL);for(byte b:data)c=(c>>>8)^TABLE[(c^(b&255))&255];return (c^0xffffffffL)&0xffffffffL;}
    public static String checksum(byte[] data){return hex(appendCrc(0,data));}
    private long fileCrc(File p,long length) throws IOException {
        CRC32 crc=new CRC32();byte[] buffer=new byte[32768];long remaining=length;
        try(InputStream in=new FileInputStream(p)){while(remaining>0){int n=in.read(buffer,0,(int)Math.min(buffer.length,remaining));if(n<1)throw new IOException("Saved audio is incomplete");crc.update(buffer,0,n);remaining-=n;}}
        return crc.getValue();
    }
    public synchronized Progress offer(String id,int rate,long total,String archiveHash,String pcmCrc32) throws IOException {
        if(!validId(id)||!validHash(archiveHash)||pcmCrc32==null||!pcmCrc32.matches("[0-9a-f]{8}")||(rate!=8000&&rate!=16000)||total<2||total>MAX_BYTES||(total&1)!=0)throw new IOException("Invalid recording offer");
        File d=folder(id);if(!d.exists()){if(!d.mkdir())throw new IOException("Cannot create recording");durability.sync(root);}
        File metadata=member(d,"state.properties");State s;
        if(metadata.exists()){
            s=read(id);if(s.rate!=rate||s.total!=total||!s.archiveHash.equals(archiveHash)||!hex(s.expectedCrc).equals(pcmCrc32))throw new IOException("Recording identity conflict; original audio preserved");
            if(s.complete){verifiedAudio(s);durability.sync(folder(id));return new Progress(s);}
            File pcm=member(d,"receiving.pcm");if(!pcm.isFile()||pcm.length()<s.next)throw new IOException("Saved transfer is incomplete; original files preserved");
            if(fileCrc(pcm,s.next)!=s.crc)throw new IOException("Saved transfer checksum mismatch; original files preserved");
            if(pcm.length()!=s.next){try(RandomAccessFile f=new RandomAccessFile(pcm,"rw")){f.setLength(s.next);f.getFD().sync();}}
        }else{
            if(member(d,"recording.wav").exists()||member(d,"receiving.pcm").exists())throw new IOException("Unindexed audio preserved; recovery required");
            s=new State();s.id=id;s.rate=rate;s.total=total;s.archiveHash=archiveHash;s.expectedCrc=Long.parseLong(pcmCrc32,16);s.created=System.currentTimeMillis();
            try(RandomAccessFile f=new RandomAccessFile(member(d,"receiving.pcm"),"rw")){f.getFD().sync();}
            write(s);
        }
        durability.sync(d);return new Progress(s);
    }
    public synchronized Progress chunk(String id,long offset,byte[] data,String crc32) throws IOException {
        if(data==null||data.length<2||data.length>CHUNK_BYTES||(data.length&1)!=0||offset<0||(offset&1)!=0||!checksum(data).equals(crc32))throw new IOException("Audio packet checksum or length invalid");
        State s=read(id);if(s.complete)throw new IOException("Recording already saved");
        if(offset>s.next||offset+data.length>s.total)throw new IOException("Audio offset mismatch; resume from durable offset");
        File pcm=member(folder(id),"receiving.pcm");
        try(RandomAccessFile f=new RandomAccessFile(pcm,"rw")){
            if(f.length()<s.next)throw new IOException("Saved transfer truncated");
            if(offset<s.next){
                if(offset+data.length>s.next)throw new IOException("Overlapping transfer frontier");
                byte[] previous=new byte[data.length];f.seek(offset);f.readFully(previous);if(!Arrays.equals(data,previous))throw new IOException("Conflicting duplicate packet");durability.sync(folder(id));return new Progress(s);
            }
            if(root.getUsableSpace()<data.length+131072L)throw new IOException("Phone storage is full; watch original remains");
            // Discard only bytes beyond a known durable ledger, never acknowledged data.
            if(f.length()!=s.next)f.setLength(s.next);f.seek(s.next);f.write(data);f.getFD().sync();
        }
        s.next+=data.length;s.crc=appendCrc(s.crc,data);write(s);return new Progress(s);
    }
    private static void word(OutputStream out,long value,int bytes) throws IOException {for(int n=0;n<bytes;n++)out.write((int)(value>>>(n*8))&255);}
    private static void header(OutputStream out,long bytes,int rate) throws IOException {
        out.write(new byte[]{'R','I','F','F'});word(out,36+bytes,4);out.write(new byte[]{'W','A','V','E','f','m','t',' '});word(out,16,4);word(out,1,2);word(out,1,2);
        word(out,rate,4);word(out,rate*2,4);word(out,2,2);word(out,16,2);out.write(new byte[]{'d','a','t','a'});word(out,bytes,4);
    }
    public synchronized Progress finish(String id,long total,String archiveHash,String pcmCrc32) throws IOException {
        // Atomic rename is supported by Android app storage even when SELinux
        // refuses hard links. Serialize every publisher of this record before
        // checking the destination, so an existing WAV is never replaced.
        File d=folder(id);
        if(!d.isDirectory())throw new IOException("Recording checkpoint unavailable");
        try(RandomAccessFile lock=new RandomAccessFile(member(d,"publish.lock"),"rw");FileLock held=lock.getChannel().lock()){
            return finishLocked(id,total,archiveHash,pcmCrc32);
        }
    }
    private Progress finishLocked(String id,long total,String archiveHash,String pcmCrc32) throws IOException {
        State s=read(id);if(s.total!=total||!s.archiveHash.equals(archiveHash)||!hex(s.expectedCrc).equals(pcmCrc32)||s.next!=s.total)throw new IOException("Recording not fully received");
        if(s.complete){verifiedAudio(s);durability.sync(folder(id));return new Progress(s);}
        File d=folder(id),pcm=member(d,"receiving.pcm"),wav=member(d,"recording.wav");
        if(!pcm.isFile()||pcm.length()!=s.total||s.crc!=s.expectedCrc||fileCrc(pcm,s.total)!=s.expectedCrc)throw new IOException("Complete audio verification failed");
        if(wav.exists()){
            // An interrupted final checkpoint may leave an already durable WAV.
            ByteArrayOutputStream expectedHeader=new ByteArrayOutputStream();header(expectedHeader,s.total,s.rate);byte[] actualHeader=new byte[44];try(DataInputStream in=new DataInputStream(new FileInputStream(wav))){in.readFully(actualHeader);}
            if(wav.length()!=44+s.total||!Arrays.equals(expectedHeader.toByteArray(),actualHeader)||wavPcmCrc(wav,s.total)!=s.crc)throw new IOException("Conflicting WAV preserved");
        }else{
            if(root.getUsableSpace()<s.total+131072L)throw new IOException("Phone needs space to seal the complete recording; watch original remains");
            File temp=member(d,"wav-"+UUID.randomUUID()+".pending");
            try{
                try(FileOutputStream out=new FileOutputStream(temp);InputStream in=new FileInputStream(pcm)){
                    header(out,s.total,s.rate);byte[] buffer=new byte[32768];long copied=0;int count;CRC32 crc=new CRC32();
                    while((count=in.read(buffer))!=-1){copied+=count;if(copied>s.total)throw new IOException("Audio changed while saving");out.write(buffer,0,count);crc.update(buffer,0,count);}
                    if(copied!=s.total||crc.getValue()!=s.crc)throw new IOException("Audio changed while saving");out.flush();out.getFD().sync();
                }
                Files.move(temp.toPath(),wav.toPath(),StandardCopyOption.ATOMIC_MOVE);durability.sync(d);
            }finally{if(temp.exists())temp.delete();}
        }
        s.sha256=digest(wav);s.complete=true;write(s);
        // PCM is a receive temporary. The bit-identical finalized WAV remains.
        if(pcm.delete())durability.sync(d);
        return new Progress(s);
    }
    private long wavPcmCrc(File wav,long length) throws IOException {
        CRC32 crc=new CRC32();byte[] block=new byte[32768];long got=0;
        try(InputStream in=new FileInputStream(wav)){long skipped=0;while(skipped<44){long n=in.skip(44-skipped);if(n<1)throw new IOException("Invalid WAV");skipped+=n;}int n;while((n=in.read(block))!=-1){crc.update(block,0,n);got+=n;}}
        if(got!=length)throw new IOException("Invalid WAV length");return crc.getValue();
    }
    public static String digest(File file) throws IOException {
        try{MessageDigest hash=MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[32768];try(InputStream in=new FileInputStream(file)){int n;while((n=in.read(buffer))!=-1)hash.update(buffer,0,n);}StringBuilder text=new StringBuilder();for(byte b:hash.digest())text.append(String.format(Locale.ROOT,"%02x",b&255));return text.toString();}
        catch(java.security.NoSuchAlgorithmException impossible){throw new IOException("SHA-256 unavailable");}
    }
    private File verifiedAudio(State s) throws IOException {
        File file=member(folder(s.id),"recording.wav");if(!s.complete||!file.isFile()||file.length()!=44+s.total||!digest(file).equals(s.sha256))throw new IOException("Saved recording verification failed");return file;
    }
    public synchronized File audio(String id) throws IOException{return verifiedAudio(read(id));}
    public synchronized Progress status(String id) throws IOException{State s=read(id);if(s.complete)verifiedAudio(s);else{File p=member(folder(id),"receiving.pcm");if(!p.isFile()||p.length()<s.next)throw new IOException("Saved transfer incomplete");}durability.sync(folder(id));return new Progress(s);}
    public synchronized List<Progress> list() {
        List<Progress> rows=new ArrayList<>();File[] children=root.listFiles();if(children==null)return rows;
        for(File d:children){if(!validId(d.getName()))continue;try{rows.add(new Progress(read(d.getName())));}catch(IOException ignored){}}
        rows.sort((a,b)->Long.compare(b.created,a.created));return rows.size()>300?new ArrayList<>(rows.subList(0,300)):rows;
    }
}
