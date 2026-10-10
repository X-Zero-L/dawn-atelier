"""Generated example data, independent of any real game save or account."""

from pathlib import Path

from atelier import GameDescriptor
from blazblue_adapter import BlazBlueAdapter
from blazblue_codec import SaveDocument, encode_varint


def sample():
    def scalar(tag,value):
        return encode_varint(tag<<3)+encode_varint(value)
    def message(tag,value):
        return encode_varint((tag<<3)|2)+encode_varint(len(value))+value
    def pack(values,item=False):
        return message(1,b''.join(message(1,scalar(1,ident)+message(2,scalar(1,ident)+scalar(2,count)+(scalar(3,0) if item else b''))) for ident,count in values))
    models={'ModelPlayer':message(1,b'AutoSave'),'ModelPlayerNewCurrencyPack':pack([(1,12500)]),
            'ModelPlayerNewItemPack':pack([(4001,3),(9001,12),(4091,1),(4092,1),(6001,2)],True),
            'ExampleUnknownData':b'preserve this model'}
    payload=message(1,b'AutoSave')+b''.join(message(2,message(1,key.encode())+message(2,value)) for key,value in models.items())
    return SaveDocument(b'',b'',0x7c,0x40).encode(payload)


class BlazBlueDemoAdapter(BlazBlueAdapter):
    descriptor=GameDescriptor('blazblue-demo','苍翼：混沌效应 · 合成演示','1',BlazBlueAdapter.descriptor.capabilities,synthetic=True)

    def compatibility(self,snapshot):
        self._parse(snapshot.data)
        return {'format':'blazblue-split-packs-demo-v1','synthetic':True}

    def runtime(self,snapshot,mode):
        if mode=='apply':
            raise ValueError('演示模式仅可导出合成副本。')


def prepare(root):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    path=root/'1'
    if not path.exists():
        path.write_bytes(sample())
    return path
