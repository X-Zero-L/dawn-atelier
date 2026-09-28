"""Build local catalogues and artwork from a supported installed copy of ThePiper."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from app_paths import APP_ROOT as ROOT, task_command, read_config, write_config
from compatibility import inspect_game, install_schema, begin_preparation, complete_preparation

ART_BUNDLES={'assets_gameres_arts_logo.bundle','assets_gameres_arts_ui_common_startwindow.bundle','assets_gameres_arts_atlas.bundle'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,help='Folder containing ThePiper.exe')
    parser.add_argument('--skip-art',action='store_true',help='Prepare save editing and catalogues without artwork')
    args=parser.parse_args()
    if args.game_dir:os.environ['PIPER_GAME_DIR']=str(args.game_dir.resolve())
    from app_config import GAME_DIR,DATA_ROOT,SCHEMA_ROOT
    report=inspect_game(GAME_DIR)
    begin_preparation(DATA_ROOT)
    install_schema(report,DATA_ROOT)
    print('Compatibility: '+report['package_version']+' / '+report['message'],flush=True)
    local=read_config()
    local['game_dir']=str(GAME_DIR)
    write_config(local)
    print('[1/3] Reading manifest and preparing gameplay tables…',flush=True)
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    subprocess.run(task_command('unpack'),cwd=ROOT,check=True,**options)
    print('[2/3] Building readable catalogues…',flush=True)
    with (DATA_ROOT/'catalogue-build.log').open('w',encoding='utf-8') as output:
        subprocess.run(task_command('catalogue'),cwd=ROOT,stdout=output,check=True,**options)
    manifest=json.loads((DATA_ROOT/'bundles/manifest.json').read_text(encoding='utf-8'))
    resources=DATA_ROOT/'resources'
    resources.mkdir(exist_ok=True)
    records=[]
    if not args.skip_art:
        print('[3/3] Preparing local artwork…',flush=True)
        sys.path.insert(0,str(ROOT/'research/bundles'))
        from decode_bundles import recover_constants,decode_bundle
        from unpack_unity import bundle_files,serialized_objects,safe_name
        master,_=recover_constants()
        source=GAME_DIR/'ThePiper_Data/StreamingAssets/yoo/Main'
        for bundle in manifest['bundles']:
            if bundle['name'] not in ART_BUNDLES:continue
            encrypted=(source/(bundle['hash']+'.bundle')).read_bytes()
            info,contents=bundle_files(decode_bundle(encrypted,bundle['name'],master))
            if info['uncompressed_crc32']!=bundle['unity_crc']:
                raise ValueError('Artwork CRC mismatch: '+bundle['name'])
            folder=resources/safe_name(bundle['name']);folder.mkdir(exist_ok=True)
            record={'name':bundle['name'],'bundle_id':bundle['bundle_id'],'files':[]}
            for entry,data in contents:
                output=folder/safe_name(entry['name']);output.write_bytes(data)
                descriptor={**entry,'path':str(output.relative_to(DATA_ROOT))}
                if not entry['name'].endswith(('.resS','.resource')):
                    metadata,objects,_=serialized_objects(data)
                    descriptor.update(metadata);descriptor['objects']=objects
                record['files'].append(descriptor)
            records.append(record)
        (resources/'index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        subprocess.run(task_command('art'),cwd=ROOT,check=True,**options)
    else:print('[3/3] Artwork skipped; the interface will use its built-in illustrations.',flush=True)
    summary={'bundles':len(manifest['bundles']),'fully_extracted_art_bundles':len(records),
             'serialized_objects':sum(len(f.get('objects',[])) for r in records for f in r['files']),
             'package_version':manifest['package_version'],'mode':'selective','selected_crc_matched':True,
             'compatibility':report}
    (resources/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    complete_preparation(report,DATA_ROOT,GAME_DIR)
    print('Ready. Run: python launch.py',flush=True)


if __name__=='__main__':main()
