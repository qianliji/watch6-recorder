"""Validate COPIED Watch6 Recorder extents and stream them into a new WAV.

No watch connection, Bluetooth, microphone or delete operation is provided.
The user must obtain a filesystem copy with a tool they are authorized to use.
"""
from pathlib import Path
import argparse,json,math,os,re,tempfile,wave,zlib

class ArchiveError(ValueError):pass
def safe_file(root,name):
    p=root/name
    if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(root):raise ArchiveError('Missing, linked or unsafe archive file: '+name)
    return p
def metadata(root,name,nonce,kind=None):
    p=safe_file(root,name);raw=p.read_bytes()
    if len(raw)!=512 or raw[:6]!=b'VSMC1\n' or raw[14:30]!=nonce.encode() or raw[480:496]!=nonce.encode() or raw[496:507]!=b'\nend=VSMC1\n':raise ArchiveError('Invalid immutable metadata: '+name)
    try:good=int(raw[472:480],16)==zlib.crc32(raw[:472])
    except ValueError:good=False
    if not good or kind and raw[6:14]!=kind:raise ArchiveError('Metadata checksum/type mismatch: '+name)
    return raw
def number(raw,start,length):
    text=raw[start:start+length]
    if not re.fullmatch(rb'[0-9a-f]+',text):raise ArchiveError('Invalid numeric metadata')
    return int(text,16)
def inspect(source,nonce,allow_partial=False,recover_sealed=False):
    root=Path(source).resolve()
    if not re.fullmatch('[0-9a-f]{16}',nonce) or nonce=='0'*16:raise ArchiveError('Recording ID must be 16 lowercase hexadecimal characters')
    prefix='vs-mc-'+nonce+'-'
    session=metadata(root,prefix+'00000000.session',nonce,b'SESSION ');rate=number(session,32,8)
    if rate not in (8000,16000):raise ArchiveError('Unsupported sample rate')
    tail_unknown=False
    if recover_sealed and not (root/(prefix+'00000000.end')).exists():
        complete=False;tail_unknown=True;total=0
        entries=sorted(root.glob(prefix+'*.meta'))
        if not entries or len(entries)>2050:raise ArchiveError('No bounded sealed extents to recover')
        for seq,p in enumerate(entries,1):
            if p.name!=prefix+f'{seq:08x}.meta':raise ArchiveError('Recovery extent gap')
            raw=metadata(root,p.name,nonce,b'SEALED  ');size=number(raw,56,8)
            if number(raw,32,8)!=seq or number(raw,40,16)!=total or number(raw,72,8)!=rate or size<2 or size>65536 or size%2 or seq<len(entries) and size!=65536:raise ArchiveError('Invalid sealed recovery extent')
            total+=size
    else:
        end=metadata(root,prefix+'00000000.end',nonce)
        complete=end[6:14]==b'CLOSED  '
        if not complete and (end[6:14]!=b'PARTIAL ' or not allow_partial):raise ArchiveError('Partial recording requires --allow-partial; raw files are preserved')
        total=number(end,32,16)
        if number(end,56,8)!=rate:raise ArchiveError('Invalid final sample rate')
    if total%2 or total>134348800:raise ArchiveError('Invalid final recording length')
    parts=[];offset=0
    for seq in range(1,math.ceil(total/65536)+1):
        name=prefix+f'{seq:08x}'
        raw=metadata(root,name+'.meta',nonce,b'SEALED  ')
        start,size,crc,sample=number(raw,40,16),number(raw,56,8),number(raw,64,8),number(raw,72,8)
        if number(raw,32,8)!=seq or start!=offset or size!=min(65536,total-offset) or sample!=rate:raise ArchiveError('Extent gap, wrong rate or length: '+name)
        p=safe_file(root,name+'.pcm')
        if p.stat().st_size!=size:raise ArchiveError('PCM length mismatch: '+name)
        check=0
        with p.open('rb') as f:
            while block:=f.read(16384):check=zlib.crc32(block,check)
        if check!=crc:raise ArchiveError('PCM checksum mismatch: '+name)
        parts.append(dict(name=name+'.pcm',bytes=size,crc=crc));offset+=size
    return dict(id=nonce,sample_rate=rate,bytes=total,complete=complete,tail_unknown=tail_unknown,seconds=total/rate/2,parts=parts)
def export(source,nonce,output,allow_partial=False,recover_sealed=False):
    root=Path(source).resolve();output=Path(output).resolve()
    if output.exists() or output.is_relative_to(root):raise ArchiveError('Choose a new output file outside the source directory')
    report=inspect(root,nonce,allow_partial,recover_sealed);output.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=output.name+'.',suffix='.pending',dir=output.parent);os.close(fd);pending=Path(temp)
    try:
        with wave.open(str(pending),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(report['sample_rate'])
            for part in report['parts']:
                check=0;copied=0
                with safe_file(root,part['name']).open('rb') as f:
                    while block:=f.read(16384):check=zlib.crc32(block,check);copied+=len(block);wav.writeframesraw(block)
                if copied!=part['bytes'] or check!=part['crc']:raise ArchiveError('Source changed during export')
        again=inspect(root,nonce,allow_partial,recover_sealed)
        if again!=report:raise ArchiveError('Archive metadata changed during export')
        with pending.open('r+b') as f:f.flush();os.fsync(f.fileno())
        # Both files are siblings on one volume. A hard link publishes the
        # fully validated file atomically and refuses an existing destination.
        # On filesystems without links, fail rather than publish a partial WAV.
        os.link(pending,output)
        return report
    finally:pending.unlink(missing_ok=True)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--id',required=True);p.add_argument('--output',type=Path);p.add_argument('--allow-partial',action='store_true');p.add_argument('--recover-sealed',action='store_true',help='Recover verified sealed extents without an end ledger; never claim complete audio');a=p.parse_args()
    try:
        report=export(a.source,a.id,a.output,a.allow_partial,a.recover_sealed) if a.output else inspect(a.source,a.id,a.allow_partial,a.recover_sealed)
        print(json.dumps({k:v for k,v in report.items() if k!='parts'},ensure_ascii=False))
    except (ArchiveError,OSError) as e:p.exit(1,'Export failed: '+str(e)+'\n')
if __name__=='__main__':main()
