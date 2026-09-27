from pathlib import Path
import struct,json,sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app_config import GAME_DIR
ROOT=GAME_DIR
meta=(ROOT/'ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat').read_bytes()
hdr=struct.unpack_from('<64I',meta)
H=[hdr[2+i*2:4+i*2] for i in range(31)]
strings=meta[H[2][0]:sum(H[2])]
def s(i): return strings[i:strings.find(b'\0',i)].decode(errors='replace') if 0<=i<len(strings) else '?'+str(i)
def td(i): return struct.unpack_from('<16i8H2I',meta,H[19][0]+i*88)
def fields(i):
 d=td(i)
 return [(j,*struct.unpack_from('<3i',meta,H[11][0]+j*12)) for j in range(d[8],d[8]+d[18])]
def methods(i):
 d=td(i)
 return [(j,*struct.unpack_from('<7i4H',meta,H[5][0]+j*36)) for j in range(d[9],d[9]+d[16])]
def name(i):
 d=td(i);return '.'.join(x for x in [s(d[1]),s(d[0])] if x)
pe=(ROOT/'GameAssembly.dll').read_bytes()
peoff=struct.unpack_from('<I',pe,60)[0]
num=struct.unpack_from('<H',pe,peoff+6)[0]
optsz=struct.unpack_from('<H',pe,peoff+20)[0]
imagebase=struct.unpack_from('<Q',pe,peoff+24+24)[0]
sections=[]
for i in range(num):
 off=peoff+24+optsz+i*40
 nm=pe[off:off+8].rstrip(b'\0').decode();vsize,rva,rsize,raw=struct.unpack_from('<4I',pe,off+8)
 sections.append((nm,rva,vsize,raw,rsize))
def vaoff(va):
 for nm,rva,vs,raw,rs in sections:
  if imagebase+rva<=va<imagebase+rva+rs:return raw+va-imagebase-rva
 raise ValueError(hex(va))
def offva(off):
 for nm,rva,vs,raw,rs in sections:
  if raw<=off<raw+rs:return imagebase+rva+off-raw
 raise ValueError(hex(off))
def readva(va,fmt):return struct.unpack_from(fmt,pe,vaoff(va))
def finds(data,needle):
 p=-1
 while True:
  p=data.find(needle,p+1)
  if p<0:return
  yield p
if __name__=='__main__':
 print('base',hex(imagebase),'sections',sections)
 n=H[19][1]//88
 for p in finds(pe,struct.pack('<Q',n)):
  if pe[p+16:p+24]==struct.pack('<Q',n):print('metadata reg',hex(p-80),[hex(x) for x in struct.unpack_from('<16Q',pe,p-80)])
 for p in finds(pe,b'Assembly-CSharp.dll\0'):
  print('module name',hex(p),hex(offva(p)))
  for ref in finds(pe,struct.pack('<Q',offva(p))):print('module',hex(ref),[hex(x) for x in struct.unpack_from('<20Q',pe,ref)])
 for i in range(n):
  if s(td(i)[0]) in ['Int32','Int64','Double','Single','ItemData','UserData','PlayerData','GameData','BagData']:
   print('TYPE',i,name(i),td(i)[2])
