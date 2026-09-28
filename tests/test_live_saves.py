"""Exercise newly created and overwritten saves in a disposable demo folder."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LiveSaveIndex(unittest.TestCase):
    def test_current_list_and_stale_snapshot_protection(self):
        script = '''
from app_config import SAVE_DIR
import hashlib
import web_server as app
source=(SAVE_DIR/'SAVE_PIPER_0.bytes').read_bytes()
first=app.save_index()
assert len(first)==1
assert first[0]['gold']=='128500'
new=SAVE_DIR/'SAVE_PIPER_8.bytes'
new.write_bytes(source)
assert len(app.save_index())==2
assert any(row['name']==new.name for row in app.save_index())
old_sha=hashlib.sha256(source).hexdigest()
updated=app.SCHEMA.edit(source,'AllAttributeSaveData.AttributeParams[0].Value',900000000)
new.write_bytes(updated)
row=next(row for row in app.save_index() if row['name']==new.name)
assert row['sha256']!=old_sha and row['gold']=='900000'
snapshot=app.describe_save(new.name,True)
assert snapshot['sha256']==row['sha256'] and snapshot['gold']=='900000'
try:
    app.plan_preset({'save':new.name,'sha256':old_sha,'actions':[{'id':'favor_max'}]})
except ValueError:pass
else:raise AssertionError('Stale snapshot was accepted')
assert app.plan_preset({'save':new.name,'sha256':row['sha256'],'actions':[{'id':'favor_max'}]})['count']>0
new.write_bytes(b'\\x80')
assert next(row for row in app.save_index() if row['name']==new.name)['error']
new.write_bytes(updated)
assert not next(row for row in app.save_index() if row['name']==new.name).get('error')
new.unlink()
assert len(app.save_index())==1
assert (SAVE_DIR/'SAVE_PIPER_0.bytes').read_bytes()==source
print('created, overwritten, partial, restored and removed save index states passed')
'''
        with tempfile.TemporaryDirectory(prefix='dawn-live-saves-') as directory:
            env={**os.environ,'DAWN_DEMO':'1','DAWN_HOME':directory,'DAWN_DATA_DIR':str(Path(directory)/'data')}
            result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=Path(__file__).resolve().parents[1],
                                  env=env,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
