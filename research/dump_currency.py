from inspect_meta import *
typesptr=0x182b1c170
fieldoffptr=0x182e62000
methodptr=0x182eb2790
def ty(i):
 p=readva(typesptr+i*8,'<Q')[0]
 a,b=readva(p,'<QI')
 kind=(b>>16)&255
 if kind in [0x11,0x12]: label=name(a)
 else:label={1:'void',2:'bool',3:'char',4:'i8',5:'u8',6:'i16',7:'u16',8:'int',9:'uint',10:'long',11:'ulong',12:'float',13:'double',14:'string',28:'object'}.get(kind,hex(kind))
 return (label,hex(a),hex(b),hex(p))
def fo(i,j):
 p=readva(fieldoffptr+i*8,'<Q')[0]
 return readva(p+j*4,'<i')[0]
def ma(m):return readva(methodptr+((m[7]&0xffffff)-1)*8,'<Q')[0]
if __name__=='__main__':
 defaults={struct.unpack_from('<3i',meta,H[7][0]+j):None for j in []}
 for i in range(H[19][1]//88):
  ff=fields(i)
  hits=[f for f in ff if s(f[1]) in ['Money','E_Money','BagSaveData','ConfigId','Count']]
  if any(s(f[1]) in ['Money','E_Money'] for f in hits) or i in [532,586,1598]:
   print('TYPE',i,name(i),td(i))
   for j,f in enumerate(ff):
    print(' FIELD',f[0],s(f[1]),ty(f[2]),'offset',fo(i,j))
    for p in range(H[7][0],sum(H[7]),12):
     idx,t,v=struct.unpack_from('<3i',meta,p)
     if idx==f[0]:print(' DEFAULT',t,v,meta[H[8][0]+v:H[8][0]+v+16].hex())
   for m in methods(i):print(' METHOD',m[0],s(m[1]),'ret',ty(m[3]),'rva',hex(ma(m)-imagebase),'raw',m[4:])
