from pathlib import Path
import hashlib,importlib.util,json,tempfile,unittest,wave,zlib
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('recorder_export',ROOT/'tools/export_wav.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ID='0123456789abcdef'
def frame(kind):
    data=bytearray(b' '*512);data[:6]=b'VSMC1\n';data[6:14]=kind;data[14:30]=ID.encode();data[30]=10;data[480:496]=ID.encode();data[496:507]=b'\nend=VSMC1\n';return data
def number(data,offset,value,digits=8):data[offset:offset+digits]=f'{value:0{digits}x}'.encode()
def write(root,name,data):number(data,472,zlib.crc32(data[:472]));(root/name).write_bytes(data)
def fixture(root,complete=True):
    raw=bytes(i%251 for i in range(70000));prefix='vs-mc-'+ID+'-'
    s=frame(b'SESSION ');number(s,32,8000);write(root,prefix+'00000000.session',s)
    offset=0
    for seq,start in enumerate(range(0,len(raw),65536),1):
        block=raw[start:start+65536];name=prefix+f'{seq:08x}';(root/(name+'.pcm')).write_bytes(block)
        s=frame(b'SEALED  ');number(s,32,seq);number(s,40,offset,16);number(s,56,len(block));number(s,64,zlib.crc32(block));number(s,72,8000);write(root,name+'.meta',s);offset+=len(block)
    s=frame(b'CLOSED  ' if complete else b'PARTIAL ');number(s,32,len(raw),16);number(s,48,1);number(s,56,8000);write(root,prefix+'00000000.end',s)
    return raw
class ExportTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.base=Path(self.t.name);self.source=self.base/'input';self.source.mkdir();self.raw=fixture(self.source);self.output=self.base/'output.wav'
    def tearDown(self):self.t.cleanup()
    def test_complete_stream(self):
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}
        report=m.export(self.source,ID,self.output);self.assertTrue(report['complete'])
        with wave.open(str(self.output),'rb') as w:self.assertEqual((w.getframerate(),w.getnchannels(),w.getsampwidth()),(8000,1,2));self.assertEqual(w.readframes(w.getnframes()),self.raw)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()})
    def test_no_overwrite(self):
        self.output.write_bytes(b'keep');self.assertRaises(m.ArchiveError,m.export,self.source,ID,self.output);self.assertEqual(self.output.read_bytes(),b'keep')
    def test_corrupt_pcm(self):
        (self.source/f'vs-mc-{ID}-00000001.pcm').write_bytes(b'x'*65536);self.assertRaises(m.ArchiveError,m.export,self.source,ID,self.output);self.assertFalse(self.output.exists())
    def test_bad_metadata(self):
        p=self.source/f'vs-mc-{ID}-00000001.meta';raw=bytearray(p.read_bytes());raw[32]^=1;p.write_bytes(raw);self.assertRaises(m.ArchiveError,m.inspect,self.source,ID)
    def test_gap(self):
        (self.source/f'vs-mc-{ID}-00000001.meta').unlink();self.assertRaises(m.ArchiveError,m.inspect,self.source,ID)
    def test_partial_explicit(self):
        fixture(self.source,False);self.assertRaises(m.ArchiveError,m.inspect,self.source,ID);self.assertFalse(m.export(self.source,ID,self.output,True)['complete'])
    def test_recover_sealed(self):
        (self.source/f'vs-mc-{ID}-00000000.end').unlink();self.assertRaises(m.ArchiveError,m.inspect,self.source,ID)
        (self.source/f'vs-mc-{ID}-00000003.pcm').write_bytes(b'unsealed')
        r=m.export(self.source,ID,self.output,recover_sealed=True);self.assertFalse(r['complete']);self.assertTrue(r['tail_unknown']);self.assertEqual(r['bytes'],70000)
    def test_no_output_inside_source(self):self.assertRaises(m.ArchiveError,m.export,self.source,ID,self.source/'export.wav')
    def test_invalid_id(self):self.assertRaises(m.ArchiveError,m.inspect,self.source,'../outside')
    def test_wrong_rate(self):
        p=self.source/f'vs-mc-{ID}-00000002.meta';s=bytearray(p.read_bytes());number(s,72,16000);write(self.source,p.name,s);self.assertRaises(m.ArchiveError,m.inspect,self.source,ID)
    def test_destination_race(self):
        original=m.os.link
        def race(a,b):Path(b).write_bytes(b'foreign');raise FileExistsError()
        m.os.link=race
        try:self.assertRaises(FileExistsError,m.export,self.source,ID,self.output)
        finally:m.os.link=original
        self.assertEqual(self.output.read_bytes(),b'foreign');self.assertFalse(list(self.base.glob('*.pending')))
if __name__=='__main__':unittest.main()
