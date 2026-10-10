"""Synthetic fixtures only: confirmed local packs and generic workbench."""

from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from atelier import Editor, Snapshot
from blazblue_adapter import BlazBlueAdapter, discover_saves
from blazblue_codec import MAGIC, SaveDocument, decode_save, encode_varint, read_modules, read_pack, xxh32
from game_workbench import Workbench


def number(tag,value):
    return encode_varint(tag<<3)+encode_varint(value)


def message(tag,value):
    return encode_varint((tag<<3)|2)+encode_varint(len(value))+value


def pack(values,item=False):
    entries=b''
    for ident,count in values:
        row=number(1,ident)+number(2,count)+(number(3,123456789) if item else b'')+number(99,65536)
        entries+=message(1,number(1,ident)+message(2,row))
    return message(1,entries)+number(98,42)


def sample():
    models={'ModelPlayer':number(30,999),'ModelPlayerNewCurrencyPack':pack([(1,255),(100,77)]),
            'ModelPlayerNewItemPack':pack([(4001,1),(4091,0),(9001,5),(6001,2),(8001,9)],True),
            'UnknownModel':b'untouched bytes'}
    payload=message(1,b'AutoSave')+b''.join(message(2,message(1,name.encode())+message(2,value)) for name,value in models.items())+number(90,555)
    # Use every standard frame checksum; the identity path retains original bytes.
    return SaveDocument(b'',b'',0x7c,0x40).encode(payload)


class BlazBlueChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atelier-blazblue-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'1';self.original=sample();self.source.write_bytes(self.original)
        self.adapter=BlazBlueAdapter(self.root/'game')
        self.contract={'contract':'synthetic-confirmed-contract','resources':{'fixture':'abc'}}
        self.patch=patch('blazblue_install.inspect_installation',return_value=self.contract)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.editor=Editor(self.adapter,self.root/'backups')

    def operations(self):
        return [{'action':'set','target':'currency:1','value':100000},
                {'action':'set','target':'item:4001','value':99}]

    def test_lz4_identity_checksums_and_unknown_bytes(self):
        document=decode_save(self.original)
        self.assertTrue(self.original.startswith(MAGIC))
        self.assertEqual(document.encode(document.payload),self.original)
        output=self.adapter.transform(self.original,self.operations())
        new=read_modules(decode_save(output).payload)
        old=read_modules(document.payload)
        self.assertEqual(new['ModelPlayer'],old['ModelPlayer'])
        self.assertEqual(new['UnknownModel'],old['UnknownModel'])
        inverse=[{'action':'set','target':'currency:1','value':255},{'action':'set','target':'item:4001','value':1}]
        self.assertEqual(decode_save(self.adapter.transform(output,inverse)).payload,document.payload)
        self.assertEqual(read_pack(new['ModelPlayerNewItemPack'])[0]['count'],99)
        self.adapter.validate(self.original,output,self.operations())

    def test_xxh32_reference_and_corrupt_frames(self):
        self.assertEqual(xxh32(b''),0x02cc5d05)
        self.assertEqual(xxh32(b'a'),0x550d7456)
        for offset in (4,14,len(self.original)-1):
            data=bytearray(self.original);data[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                decode_save(data)
        with self.assertRaises(ValueError):
            decode_save(self.original[:-1])
        with self.assertRaises(ValueError):
            decode_save(self.original+b'junk')

    def test_linked_lz4_blocks_can_reference_previous_dictionary(self):
        descriptor=b'\x48\x40'+struct.pack('<Q',8)
        frame=MAGIC+descriptor+bytes([(xxh32(descriptor)>>8)&255])
        frame+=struct.pack('<I',0x80000004)+b'abcd'
        frame+=struct.pack('<I',3)+b'\x00\x04\x00'+b'\0'*4
        self.assertEqual(decode_save(frame).payload,b'abcdabcd')

    def test_only_existing_confirmed_fields_are_exposed(self):
        ids={row['id'] for row in self.adapter.inspect(self.original)['fields']}
        self.assertEqual(ids,{'currency:1','item:4001','item:4091','item:9001','item:6001'})
        for operation in [
            {'action':'set','target':'currency:100','value':999},
            {'action':'set','target':'item:8001','value':999},
            {'action':'set','target':'item:4092','value':99},
            {'action':'set','target':'currency:1','value':True},
            {'action':'set','target':'currency:1','value':-1},
            {'action':'set','target':'currency:1','value':100000000},
            {'action':'unlock','target':'actor:1','value':1},
        ]:
            with self.subTest(operation=operation),self.assertRaises(ValueError):
                self.adapter.transform(self.original,[operation])
        with self.assertRaises(ValueError):
            self.adapter.transform(self.original,[self.operations()[0]]*2)

    def test_install_change_and_running_game_reject_application(self):
        plan=self.editor.preview(Snapshot.capture(self.source),self.operations())
        with patch('blazblue_adapter.runtime_status',return_value={'can_apply':False}):
            with self.assertRaises(ValueError):
                self.editor.commit(plan,self.source,approval=plan.plan_id,mode='apply')
        self.assertEqual(self.source.read_bytes(),self.original)
        with patch('blazblue_install.inspect_installation',return_value={'contract':'new'}):
            with self.assertRaises(ValueError):
                self.editor.commit(plan,self.root/'out',approval=plan.plan_id)
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_host_review_export_reload_and_history(self):
        paths=lambda:list(self.root.glob('[1-9]'))
        host=Workbench(self.adapter,paths,lambda:{'can_apply':False},self.root/'workbench')
        ident=host.saves()[0]['id'];loaded=host.save(ident)
        body={'save':ident,'sha256':loaded['sha256'],'operations':self.operations()}
        plan=host.edit(body)
        with self.assertRaises(ValueError):
            host.edit(body,'export')
        result=host.edit({**body,'plan_id':plan['plan_id']},'export')
        self.assertTrue((host.exports/result['filename']).is_file())
        self.assertEqual((host.editor.backup_root/result['backup']).read_bytes(),self.original)
        self.assertEqual(host.history()['history'][0]['count'],2)
        (self.root/'2').write_bytes(self.original)
        self.assertEqual(len(host.saves()),2)
        self.source.write_bytes(self.original+b'new progress')
        with self.assertRaisesRegex(ValueError,'新的进度'):
            host.edit({**body,'plan_id':plan['plan_id']},'export')

    def test_discovery_does_not_pick_game_backups_or_cloud_sidecars(self):
        (self.root/'Backup').mkdir();(self.root/'Backup/2').write_bytes(self.original)
        for name in ('CloudData','1.bak','1.tmp','0'):
            (self.root/name).write_bytes(b'ignore')
        with patch.dict('os.environ',{'BLAZBLUE_SAVE_DIR':str(self.root)}):
            # Hosted Windows runners may provide TEMP through an 8.3 alias.
            self.assertEqual(discover_saves(),[self.source.resolve()])

    def test_actor_preparation_counts_remaining_characters_without_writing_ownership(self):
        from blazblue_demo import sample as actor_sample
        data=actor_sample()
        details=self.adapter.inspect(data)
        self.assertEqual((details['actor_plan']['owned'],details['actor_plan']['total']),(2,17))
        self.assertEqual(details['actor_plan']['targets']['item:4001'],9)
        self.assertEqual(len([r for r in details['actors'] if r['kind']=='DLC']),4)
        operations=[{'action':'set','target':key,'value':value} for key,value in details['actor_plan']['targets'].items()]
        modified=self.adapter.transform(data,operations)
        before=read_modules(decode_save(data).payload);after=read_modules(decode_save(modified).payload)
        self.assertEqual(before['ModelPlayerNewBaseActorPack'],after['ModelPlayerNewBaseActorPack'])
        self.assertEqual(before['ModelPlayerNewExtraState'],after['ModelPlayerNewExtraState'])
        self.assertEqual(self.adapter.inspect(modified)['actor_plan']['owned'],2)

    def test_used_exchange_with_missing_actor_is_reported_without_reset(self):
        from blazblue_demo import sample as actor_sample
        from blazblue_codec import replace_module
        document=decode_save(actor_sample())
        record=message(1,number(1,102501)+message(2,number(1,1)))
        payload=replace_module(document.payload,'ModelPlayerNewExtraState',message(1,record))
        details=self.adapter.inspect(document.encode(payload))
        row=next(r for r in details['actors'] if r['id']==102501)
        self.assertEqual(row['status'],'需在游戏内核对')
        self.assertEqual(details['actor_plan']['targets']['item:4001'],8)


if __name__=='__main__':
    unittest.main()
