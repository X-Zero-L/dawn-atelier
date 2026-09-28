"""Read IL2CPP metadata and native generated serializers, without loading the game.

Requires only Python and the pre-existing objdump executable. Derived output only.
Version scoped to the installed GameAssembly represented by the output SHA256.
"""
from pathlib import Path
import bisect
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import os

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from inspect_meta import ROOT, meta, pe, H, td, fields, methods, name as raw_name, s, imagebase, readva, sections
from dump_currency import typesptr, methodptr, method_count, fo, ma

sys.path.insert(0, str(HERE.parent.parent))
from app_config import DATA_ROOT
OUT = DATA_ROOT / 'schema'
ASM = HERE / 'serializers'
PRIMITIVES = {1:'void',2:'bool',3:'char',4:'int8',5:'uint8',6:'int16',7:'uint16',8:'int32',9:'uint32',10:'int64',11:'uint64',12:'float',13:'double',14:'string',24:'intptr',25:'uintptr',28:'object'}
BYVAL={td(i)[2]:i for i in range(H[19][1]//88)}

def name(i):
    d=td(i)
    if d[3]>=0 and d[3] in BYVAL:
        return name(BYVAL[d[3]])+'.'+s(d[0])
    return raw_name(i)

def resolve_ptr(p, depth=0):
    if depth > 10:
        return {'kind':'unknown','name':'recursive','pointer':hex(p)}
    data, flags = readva(p, '<QI')
    k = (flags >> 16) & 255
    if k in PRIMITIVES:
        return {'kind':'primitive','name':PRIMITIVES[k]}
    if k in (0x11,0x12):
        return {'kind':'enum' if td(data)[24]&2 else 'message', 'name':name(data), 'type_index':data}
    if k == 0x15:
        generic_type, inst = readva(data, '<QQ')
        base = resolve_ptr(generic_type, depth+1)
        count, _pad, argv = readva(inst,'<IIQ')
        args = [resolve_ptr(readva(argv+8*j,'<Q')[0],depth+1) for j in range(count)]
        return {'kind':'generic','name':base['name'], 'args':args}
    if k in (0xf,0x10,0x1d):
        return {'kind':{0xf:'pointer',0x10:'byref',0x1d:'array'}[k], 'element':resolve_ptr(data,depth+1)}
    if k == 0x14:
        elem, rank = readva(data,'<QB')
        return {'kind':'array','rank':rank,'element':resolve_ptr(elem,depth+1)}
    return {'kind':'unresolved','il2cpp_kind':hex(k),'data':hex(data)}

def resolve(i):
    return resolve_ptr(readva(typesptr+i*8,'<Q')[0])

def type_text(t):
    if t['kind']=='generic':
        return t['name'].split('`')[0]+'<'+', '.join(type_text(a) for a in t['args'])+'>'
    if 'element' in t:
        return type_text(t['element'])+'[]'
    return t.get('name',t['kind'])

DEFAULTS={}
for p in range(H[7][0],sum(H[7]),12):
    field, typ, offset = struct.unpack_from('<iii',meta,p)
    DEFAULTS[field] = (typ,offset)

def compressed(data, p):
    x=data[p];p+=1
    if x<128:return x,p
    if x<192:return ((x&63)<<8)|data[p],p+1
    if x<224:return ((x&31)<<24)|(data[p]<<16)|(data[p+1]<<8)|data[p+2],p+3
    if x==240:return struct.unpack_from('<I',data,p)[0],p+4
    if x==254:return 0xfffffffe,p
    if x==255:return 0xffffffff,p
    raise ValueError('unsupported metadata compressed integer '+hex(x))

def field_default(field):
    if field not in DEFAULTS:return None
    typ, offset=DEFAULTS[field]
    if offset<0:return None
    p=H[8][0]+offset
    rt=resolve(typ)
    n=rt.get('name')
    if n in ('int32','uint32'):
        x,end=compressed(meta,p)
        if n=='int32':x=(x>>1)^-(x&1)
        return {'value':x,'raw_hex':meta[p:end].hex(),'encoding':'metadata_compressed_'+n}
    fmt={'bool':'<?','int8':'<b','uint8':'<B','int16':'<h','uint16':'<H','int64':'<q','uint64':'<Q','float':'<f','double':'<d'}.get(n)
    if fmt:return {'value':struct.unpack_from(fmt,meta,p)[0],'raw_hex':meta[p:p+struct.calcsize(fmt)].hex(),'encoding':n}
    return {'raw_hex':meta[p:p+16].hex(),'encoding':'unresolved','type':rt}

PDA=[]
for sec,rva,vs,raw,rs in sections:
    if sec=='.pdata':
        for off in range(raw,raw+rs-11,12):
            start,end,unwind=struct.unpack_from('<III',pe,off)
            if start and end>start:PDA.append((start,end))
PDA.sort()
PDSTART=[a for a,b in PDA]
# Discover the method count from the installed Assembly-CSharp module.
# A method may span multiple adjacent .pdata records (unwind regions), so a
# single RUNTIME_FUNCTION end is insufficient for the complete serializer.
METHOD_STARTS=sorted({p for p in readva(methodptr,'<'+str(method_count)+'Q') if imagebase<p<imagebase+0x4000000})

def function_end(va):
    ni=bisect.bisect_right(METHOD_STARTS,va)
    if ni<len(METHOD_STARTS):return METHOD_STARTS[ni]
    i=bisect.bisect_right(PDSTART,va-imagebase)-1
    if i>=0 and PDA[i][0]<=va-imagebase<PDA[i][1]:
        return imagebase+PDA[i][1]
    return va+0x100

def instructions(text):
    result=[]
    for line in text.splitlines():
        m=re.match(r'\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*([a-z][a-z0-9]+)\s*(.*)',line)
        if m:
            result.append({'va':int(m[1],16),'op':m[3],'args':m[4].split('#')[0].strip(),'line':line.strip()})
    return result

def disassemble(va, label):
    end=function_end(va)
    path=ASM/(label+'.asm')
    marker='# extracted_stop_address='+hex(end)
    if not path.exists() or marker not in path.read_text(encoding='utf-8'):
        executable=os.environ.get('OBJDUMP') or shutil.which('objdump')
        command=[executable,'-d','-M','intel',f'--start-address={hex(va)}',f'--stop-address={hex(end)}',str(ROOT/'GameAssembly.dll')] if executable else ['wsl','-e','objdump','-d','-M','intel',f'--start-address={hex(va)}',f'--stop-address={hex(end)}','/mnt/'+ROOT.drive[0].lower()+ROOT.as_posix()[2:]+'/GameAssembly.dll']
        result=subprocess.run(command,capture_output=True,text=True,check=True)
        path.write_text(result.stdout+'\n'+marker+'\n',encoding='utf-8')
    return instructions(path.read_text(encoding='utf-8')),path

def serializer_method(i):
    ms=methods(i)
    direct=[m for m in ms if s(m[1])=='Serialize' and m[8]&16 and m[11]==2]
    if direct:return direct[0]
    # Example configuration classes have the same twelve generated methods.
    # The ninth has (Stream, Config)->void; the eleventh is length delimited.
    if name(i).startswith('Example.') and len(ms) in (9,12):
        m=ms[-4]
        if resolve(m[3]).get('name')=='void' and m[8]&16 and m[11]==2:return m
    return None

def infer_serializer(i, flds):
    m=serializer_method(i)
    if m is None:return None
    va=ma(m)
    ins,path=disassemble(va,str(i)+'_'+name(i).replace('.','_').replace('`','_'))
    # The second static argument is the object. Follow its preserved register.
    object_regs=[]
    for x in ins[:60]:
        q=re.fullmatch(r'(rbx|rsi|rdi|rbp|r1[2-5]),rdx',x['args']) if x['op']=='mov' else None
        if q:object_regs.append(q[1])
    obj=object_regs[0] if object_regs else None
    refs=[]
    if obj:
        for j,x in enumerate(ins):
            q=re.search(r'\['+obj+r'\+0x([0-9a-f]+)\]',x['args'])
            if q and int(q[1],16) in {f['offset'] for f in flds}:
                refs.append({'idx':j,'offset':int(q[1],16),'rva':hex(x['va']-imagebase),'instruction':x['line']})
    # Generated serializer emits each protobuf key with Stream.WriteByte.
    # Retain constant-byte locations to keep every tag auditable.
    byte_ops=[]
    for j,x in enumerate(ins):
        q=re.fullmatch(r'dl,0x([0-9a-f]+)',x['args']) if x['op']=='mov' else None
        if q:
            byte_ops.append({'idx':j,'value':int(q[1],16),'rva':hex(x['va']-imagebase),'instruction':x['line']})
        elif x['op']=='xor' and x['args']=='edx,edx' and any('+0x338]' in p['args'] for p in ins[max(0,j-3):j]):
            # Four game messages explicitly serialize a field-zero key.
            # This is a game-specific deviation from the protobuf standard.
            byte_ops.append({'idx':j,'value':0,'rva':hex(x['va']-imagebase),'instruction':x['line']})
    tags=[]
    pos=0
    while pos<len(byte_ops):
        parts=[byte_ops[pos]];v=parts[0]['value'];pos+=1
        if v&128:
            shift=7;v&=127
            while pos<len(byte_ops):
                p=byte_ops[pos];pos+=1;parts.append(p);v|=(p['value']&127)<<shift
                if not p['value']&128:break
                shift+=7
        tags.append({'tag':v>>3,'wire_type':v&7,'bytes':[p['value'] for p in parts], 'idx':parts[0]['idx'],'last_idx':parts[-1]['idx'],'rva':parts[0]['rva'],'instructions':[p['instruction'] for p in parts]})
    # Field reads occur in serializer order, independently of declarations.
    # Collapse repeated accesses to the same object field.
    ordered=[]
    for ref in refs:
        if not ordered or ordered[-1]['offset']!=ref['offset']:
            ordered.append({'offset':ref['offset'],'refs':[ref]})
        else:ordered[-1]['refs'].append(ref)
    # Keep only reads, not stores. These generated serializers are pure reads.
    result={'method':s(m[1]),'rva':hex(va-imagebase),'end_rva':hex(function_end(va)-imagebase),'object_register':obj,'assembly_path':str(path.relative_to(HERE.parent.parent)),'tag_sequence':tags,'field_access_sequence':ordered,'status':'needs_review'}
    if len(tags)==len(ordered) and len({x['offset'] for x in ordered})==len(ordered):
        possible=True
        byoffset={f['offset']:f for f in flds}
        for tag,access in zip(tags,ordered):
            # Each field access must fall between its key and adjacent keys,
            # allowing list enumerator setup immediately before its own key.
            k=tags.index(tag)
            lo=tags[k-1]['last_idx'] if k else -1
            hi=tags[k+1]['idx'] if k+1<len(tags) else len(ins)
            local=[r for r in access['refs'] if lo<r['idx']<hi]
            if not local or tag['tag']<0 or tag['wire_type'] not in (0,1,2,5):possible=False
        if possible:
            for tag,access in zip(tags,ordered):
                f=byoffset[access['offset']]
                f.update(protobuf_tag=tag['tag'],wire_type=tag['wire_type'],tag_status='native_serializer_confirmed',evidence={'serializer_rva':result['rva'],'tag_rva':tag['rva'],'tag_bytes':tag['bytes'],'field_access_rvas':[r['rva'] for r in access['refs']]})
            result['status']='complete_native_mapping'
            used={a['offset'] for a in ordered}
            for f in flds:
                if f['offset'] not in used:f['tag_status']='not_written_by_serializer'
            if any(tag['tag']==0 for tag in tags):
                result['format_note']='Game-specific field zero is explicitly written; standard protobuf libraries may reject this message.'
    return result

def export():
    OUT.mkdir(parents=True,exist_ok=True);ASM.mkdir(parents=True,exist_ok=True)
    selected=[];all_enums=[]
    for i in range(H[19][1]//88):
        nm=name(i)
        if nm.startswith(('SaveLoadSystem.','Example.')) or (i<3000 and td(i)[24]&2):
            flds=[]
            for j,f in enumerate(fields(i)):
                t=resolve(f[2])
                fld={'name':s(f[1]),'field_index':f[0],'declaration_index':j,'type':t,'type_text':type_text(t),'offset':fo(i,j),'offset_hex':hex(fo(i,j)),'protobuf_tag':None,'tag_status':'unconfirmed'}
                d=field_default(f[0])
                if d is not None:fld['default']=d
                flds.append(fld)
            obj={'name':nm,'type_index':i,'is_enum':bool(td(i)[24]&2),'fields':flds}
            if obj['is_enum']:
                obj['values']=[{'name':f['name'],**f['default']} for f in flds if 'default' in f]
                all_enums.append(obj)
            else:
                obj['serializer']=infer_serializer(i,flds)
                selected.append(obj)
    base={'source':{'game_root':str(ROOT),'metadata_version':struct.unpack_from('<I',meta,4)[0],'GameAssembly_sha256':hashlib.sha256(pe).hexdigest(),'global_metadata_sha256':hashlib.sha256(meta).hexdigest(),'image_base':hex(imagebase),'types_pointer_va':hex(typesptr)},'notes':['All offsets and RVAs are version-specific.','protobuf_tag is only assigned when matched to native serialized key bytes and object field accesses; declaration order alone is not evidence.','Unconfirmed fields must not be edited by field number.','Names from obfuscated configuration members are retained unchanged.']}
    for filename,types in [('save_schema.json',[x for x in selected if x['name'].startswith('SaveLoadSystem.')]),('config_schema.json',[x for x in selected if x['name'].startswith('Example.')]),('enums.json',all_enums)]:
        (OUT/filename).write_text(json.dumps({**base,'types':types},ensure_ascii=False,indent=2),encoding='utf-8')
    pending=[(x['type_index'],x['name'],len(x['fields']),len(x['serializer']['tag_sequence']),len(x['serializer']['field_access_sequence'])) for x in selected if x['serializer'] and x['serializer']['status']!='complete_native_mapping']
    print(json.dumps({'save_types':sum(x['name'].startswith('SaveLoadSystem.') for x in selected),'config_types':sum(x['name'].startswith('Example.') for x in selected),'enum_types':len(all_enums),'pending':pending},ensure_ascii=False,indent=2))

if __name__=='__main__':export()
