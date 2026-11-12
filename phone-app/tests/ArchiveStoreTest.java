package com.watch6.recorder;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Executes production durable-storage code against synthetic audio. */
public final class ArchiveStoreTest {
    static int assertions,cases;
    static String ID="0123456789abcdef",HASH="01234567abcdef89";
    static void check(boolean value,String reason){assertions++;if(!value)throw new AssertionError(reason);}
    interface Operation{void run() throws Exception;}
    static void rejected(Operation op,String reason) throws Exception {boolean threw=false;try{op.run();}catch(IOException|IllegalArgumentException expected){threw=true;}check(threw,reason);}
    static byte[] audio(){byte[] raw=new byte[70000];for(int n=0;n<raw.length;n++)raw[n]=(byte)(n%251);return raw;}
    static ArchiveStore create(File root) throws IOException{return new ArchiveStore(root,d->{if(!d.isDirectory())throw new IOException("missing");});}
    static void upload(ArchiveStore store,byte[] raw) throws Exception {
        for(int offset=(int)store.status(ID).next;offset<raw.length;){int end=Math.min(offset+2048,raw.length);byte[] part=Arrays.copyOfRange(raw,offset,end);ArchiveStore.Progress progress=store.chunk(ID,offset,part,ArchiveStore.checksum(part));check(progress.next==end,"ACK only exact durable frontier");offset=end;}
    }
    static void test(File base) throws Exception {
        byte[] raw=audio();String crc=ArchiveStore.checksum(raw);File root=new File(base,"recordings");ArchiveStore store=create(root);
        ArchiveStore.Progress first=store.offer(ID,8000,raw.length,HASH,crc);check(first.next==0&&!first.complete,"new recording starts at zero");cases++;
        rejected(()->store.offer("../bad",8000,70000,HASH,crc),"path escape rejected");cases++;
        rejected(()->store.offer(ID,16000,raw.length,HASH,crc),"rate conflict preserves original");cases++;
        rejected(()->store.offer(ID,8000,raw.length,"ffffffffffffffff",crc),"archive identity conflict rejected");cases++;
        rejected(()->store.offer(ID,8000,raw.length,HASH,"ffffffff"),"whole PCM fingerprint conflict rejected");cases++;
        byte[] part=Arrays.copyOfRange(raw,0,2048);store.chunk(ID,0,part,ArchiveStore.checksum(part));
        check(store.chunk(ID,0,part,ArchiveStore.checksum(part)).next==2048,"same packet idempotent");cases++;
        byte[] changed=part.clone();changed[0]^=1;rejected(()->store.chunk(ID,0,changed,ArchiveStore.checksum(changed)),"conflicting duplicate rejected");cases++;
        rejected(()->store.chunk(ID,4096,part,ArchiveStore.checksum(part)),"offset gap rejected");cases++;
        rejected(()->store.chunk(ID,2048,part,"00000000"),"bad packet CRC rejected");cases++;
        rejected(()->store.chunk(ID,2049,part,ArchiveStore.checksum(part)),"odd offset rejected");cases++;
        rejected(()->store.chunk(ID,2048,new byte[3],ArchiveStore.checksum(new byte[3])),"odd PCM rejected");cases++;
        rejected(()->store.finish(ID,raw.length,HASH,crc),"incomplete transfer never saved");cases++;
        File pcm=new File(root,ID+"/receiving.pcm");try(RandomAccessFile file=new RandomAccessFile(pcm,"rw")){file.seek(file.length());file.write(new byte[512]);file.getFD().sync();}
        ArchiveStore resumed=create(root);check(resumed.offer(ID,8000,raw.length,HASH,crc).next==2048&&pcm.length()==2048,"power interruption beyond ledger rolled back");cases++;
        upload(resumed,raw);ArchiveStore.Progress done=resumed.finish(ID,raw.length,HASH,crc);check(done.complete&&done.next==raw.length&&done.sha256.length()==64,"full WAV checkpoint saved");
        File wav=resumed.audio(ID);byte[] result=Files.readAllBytes(wav.toPath());check(result.length==44+raw.length,"WAV has entire recording");check(Arrays.equals(Arrays.copyOfRange(result,44,result.length),raw),"full original PCM retained bit-for-bit");
        check(result[0]=='R'&&result[8]=='W'&&(result[24]&255)==(8000&255),"valid WAV header");check(!pcm.exists(),"receive temporary reclaimed only after final WAV safe");cases++;
        check(resumed.finish(ID,raw.length,HASH,crc).complete,"finish idempotent");cases++;
        check(create(root).offer(ID,8000,raw.length,HASH,crc).complete,"restart recognizes saved WAV");cases++;
        check(resumed.list().size()==1&&resumed.list().get(0).complete,"saved list contains recording");cases++;
        try(RandomAccessFile f=new RandomAccessFile(wav,"rw")){f.seek(50);f.write(3);f.getFD().sync();}
        rejected(()->resumed.audio(ID),"playback refuses damaged saved WAV");cases++;
        rejected(()->resumed.offer(ID,8000,raw.length,HASH,crc),"saved receipt not returned for damaged WAV");cases++;
        File badRoot=new File(base,"bad-whole");ArchiveStore wrong=create(badRoot);wrong.offer(ID,8000,raw.length,HASH,"00000000");upload(wrong,raw);rejected(()->wrong.finish(ID,raw.length,HASH,"00000000"),"wrong complete CRC never seals WAV");check(new File(badRoot,ID+"/receiving.pcm").isFile(),"bad whole CRC keeps PCM");cases++;
        File failRoot=new File(base,"fail-sync");failRoot.mkdir();ArchiveStore failing=new ArchiveStore(failRoot,d->{throw new IOException("synthetic directory sync failure");});rejected(()->failing.offer(ID,8000,raw.length,HASH,crc),"directory sync failure returns no ACK");cases++;
        File failCheckpointRoot=new File(base,"fail-checkpoint");ArchiveStore initial=create(failCheckpointRoot);initial.offer(ID,8000,raw.length,HASH,crc);ArchiveStore afterFailure=new ArchiveStore(failCheckpointRoot,d->{throw new IOException("synthetic sync failure");});
        rejected(()->afterFailure.chunk(ID,0,part,ArchiveStore.checksum(part)),"checkpoint sync failure returns no success");
        rejected(()->afterFailure.chunk(ID,0,part,ArchiveStore.checksum(part)),"duplicate ACK also requires successful directory sync");
        check(create(failCheckpointRoot).offer(ID,8000,raw.length,HASH,crc).next==2048,"later explicit sync can confirm durable checkpoint");cases++;
        File completeRoot=new File(base,"complete-sync");ArchiveStore complete=create(completeRoot);complete.offer(ID,8000,part.length,HASH,ArchiveStore.checksum(part));complete.chunk(ID,0,part,ArchiveStore.checksum(part));complete.finish(ID,part.length,HASH,ArchiveStore.checksum(part));ArchiveStore completedFailure=new ArchiveStore(completeRoot,d->{throw new IOException("synthetic saved sync failure");});
        rejected(()->completedFailure.offer(ID,8000,part.length,HASH,ArchiveStore.checksum(part)),"saved offer still requires directory sync");rejected(()->completedFailure.finish(ID,part.length,HASH,ArchiveStore.checksum(part)),"saved finish still requires directory sync");cases++;
        rejected(()->new ArchiveStore(new File(base,"unconfirmed-root"),d->{throw new IOException("synthetic parent sync failure");}),"new archive root must sync parent");cases++;
        File conflictRoot=new File(base,"conflict-wav");ArchiveStore conflict=create(conflictRoot);conflict.offer(ID,8000,raw.length,HASH,crc);upload(conflict,raw);File badWav=new File(conflictRoot,ID+"/recording.wav");byte[] fake=new byte[44+raw.length];System.arraycopy(raw,0,fake,44,raw.length);Files.write(badWav.toPath(),fake);
        rejected(()->conflict.finish(ID,raw.length,HASH,crc),"wrong WAV header not silently adopted");check(Files.readAllBytes(badWav.toPath())[0]==0,"conflicting WAV not overwritten");cases++;
        File corruptRoot=new File(base,"corrupt-prefix");ArchiveStore corrupt=create(corruptRoot);corrupt.offer(ID,8000,raw.length,HASH,crc);corrupt.chunk(ID,0,part,ArchiveStore.checksum(part));File prefix=new File(corruptRoot,ID+"/receiving.pcm");try(RandomAccessFile f=new RandomAccessFile(prefix,"rw")){f.write(9);}
        rejected(()->create(corruptRoot).offer(ID,8000,raw.length,HASH,crc),"resume verifies durable prefix");cases++;
        File orphanRoot=new File(base,"orphan");File orphan=new File(orphanRoot,ID);orphan.mkdirs();File old=new File(orphan,"receiving.pcm");Files.write(old.toPath(),part);rejected(()->create(orphanRoot).offer(ID,8000,raw.length,HASH,crc),"unindexed original not overwritten");check(Arrays.equals(Files.readAllBytes(old.toPath()),part),"unindexed original unchanged");cases++;
    }
    public static void main(String[] args) throws Exception {File root=new File(args[0]).getCanonicalFile();if(!root.isDirectory()&&!root.mkdirs())throw new IOException("test path unavailable");test(root);System.out.println("{\"passed\":true,\"cases\":"+cases+",\"assertions\":"+assertions+",\"real_microphone_started\":false,\"network_calls\":0}");}
}
