from pathlib import Path
import struct,json,lzma
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app_config import DATA_ROOT
OUT=DATA_ROOT / 'bundles'
class Reader:
 def __init__(self,d,endian='>'):self.d=d;self.p=0;self.e=endian
 def n(self,n):
  r=self.d[self.p:self.p+n]
  if len(r)!=n:raise ValueError('truncated data')
  self.p+=n;return r
 def u(self,f):return struct.unpack(self.e+f,self.n(struct.calcsize(f)))[0]
 def z(self):
  end=self.d.index(0,self.p);r=self.d[self.p:end].decode();self.p=end+1;return r
 def align(self,n=4):self.p=(self.p+n-1)&~(n-1)
 def string(self):
  s=self.n(self.u('i')).decode();self.align();return s

def lz4(d,size):
 out=bytearray();p=0
 while p<len(d):
  token=d[p];p+=1;lit=token>>4
  if lit==15:
   while True:
    n=d[p];p+=1;lit+=n
    if n!=255:break
  out+=d[p:p+lit];p+=lit
  if p==len(d):break
  offset=int.from_bytes(d[p:p+2],'little');p+=2
  if not 0<offset<=len(out):raise ValueError('invalid LZ4 offset')
  count=(token&15)+4
  if (token&15)==15:
   while True:
    n=d[p];p+=1;count+=n
    if n!=255:break
  start=len(out)-offset
  if count<=offset:out+=out[start:start+count]
  else:out+=(out[start:]*((count+offset-1)//offset))[:count]
 if len(out)!=size:raise ValueError(f'LZ4 size: {len(out)} != {size}')
 return bytes(out)
def unpack(d):
 r=Reader(d)
 assert r.z()=='UnityFS';version=r.u('I');unity=r.z();revision=r.z();size=r.u('Q');cs=r.u('I');us=r.u('I');flags=r.u('I')
 assert size==len(d)
 if version>=7:r.align(16)
 info=r.n(cs) if not flags&0x80 else d[-cs:]
 comp=flags&0x3f
 if comp in [2,3]:info=lz4(info,us)
 elif comp!=0:raise ValueError(comp)
 ir=Reader(info);ihash=ir.n(16);blocks=[(ir.u('I'),ir.u('I'),ir.u('H')) for _ in range(ir.u('I'))];nodes=[(ir.u('Q'),ir.u('Q'),ir.u('I'),ir.z()) for _ in range(ir.u('I'))]
 assert ir.p==len(info)
 if flags&0x200:r.align(16)
 out=bytearray()
 for us,cs,bf in blocks:
  bd=r.n(cs)
  if bf&63 in [2,3]:out+=lz4(bd,us)
  elif bf&63==0:out+=bd
  else:raise ValueError(bf)
 print('bundle',version,revision,hex(flags),'blocks',len(blocks),'nodes',nodes)
 return {nm:bytes(out[off:off+n]) for off,n,fl,nm in nodes}

def textassets(d):
 r=Reader(d);ms=r.u('I');fs=r.u('I');ver=r.u('I');do=r.u('I');endian=r.u('B');r.n(3)
 if ver>=22:ms=r.u('I');fs=r.u('Q');do=r.u('Q');r.n(8)
 r.e='>' if endian else '<'
 unity=r.z();target=r.u('i');trees=r.u('B');types=[]
 for _ in range(r.u('i')):
  cls=r.u('i');strip=r.u('B');script=r.u('h')
  if cls==114:r.n(16)
  thash=r.n(16)
  if trees:
   count=r.u('i');ss=r.u('i');r.n(count*(32 if ver>=19 else 24));r.n(ss)
  if ver>=21:r.n(r.u('i')*4)
  types.append(cls)
 objects=[]
 for _ in range(r.u('i')):
  r.align();pid=r.u('q');start=r.u('q') if ver>=22 else r.u('I');size=r.u('I');tid=r.u('i');objects.append((pid,start+do,size,tid))
 print('serialized',unity,ver,'size',len(d),'types',types,'objects',len(objects),'metadata-position',r.p)
 out=[]
 for pid,start,size,tid in objects:
  if types[tid]==49:
   obj=Reader(d[start:start+size],r.e);nm=obj.string();content=obj.n(obj.u('i'));out.append((nm,content,pid))
 return out
if __name__=='__main__':
 src=OUT/'assets_gameres_table.bundle';dest=OUT/'tables';dest.mkdir(exist_ok=True)
 rec=[]
 for nm,d in unpack(src.read_bytes()).items():
  (OUT/nm).write_bytes(d)
  for name,content,pid in textassets(d):
   (dest/(name+'.bytes')).write_bytes(content);rec.append({'name':name,'size':len(content),'path_id':pid,'header_hex':content[:40].hex()})
 (OUT/'textassets.json').write_text(json.dumps(rec,indent=2),encoding='utf8')
 print('TextAssets',len(rec));print(rec[:10])
