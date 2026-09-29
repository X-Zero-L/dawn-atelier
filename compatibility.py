"""Match reviewed builds or unchanged native serialization contracts."""

import hashlib
import json
from pathlib import Path
import shutil
import struct

from app_paths import APP_ROOT
from native_layout import NativeLayout

SCHEMAS = APP_ROOT / 'schemas'
BASELINE = SCHEMAS / 'thepiper-2026-09-25'
REPORT_VERSION = 1


def digest(data):
    return hashlib.sha256(data).hexdigest()


def profiles():
    return [json.loads(file.read_text(encoding='utf-8')) for file in sorted((SCHEMAS / 'compatibility').glob('*.json'))]


def schema_contract_hash(layout):
    return digest(json.dumps(layout.schema_contract(), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())


def match_structure(assembly, metadata, candidates, mismatches=None):
    layout = NativeLayout(assembly, metadata)
    contract = schema_contract_hash(layout)
    names = {layout.type_name(index): index for index in range(layout.type_count)}
    matched_contract = False
    for profile in candidates:
        if profile.get('contract_sha256') != contract or not profile.get('serializers'):
            continue
        matched_contract = True
        for probe in profile['serializers']:
            methods = layout.methods(names[probe['type']])
            if probe['ordinal'] >= len(methods):
                break
            method = methods[probe['ordinal']]
            if method['name'] != probe['method']:
                break
            offset = layout.offset(method['address'], probe['length'])
            if digest(assembly[offset:offset + probe['length']]) != probe['sha256']:
                break
        else:
            return profile
    if mismatches is not None:
        mismatches.append('存档序列化代码与已核对版本不同' if matched_contract else '关键存档结构或配置定义与已核对版本不同')
    return None


def inspect_game(game):
    game = Path(game).resolve()
    paths = [game / 'GameAssembly.dll', game / 'ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat']
    if not all(file.is_file() for file in paths):
        raise ValueError('游戏文件不完整，请选择包含 ThePiper.exe 的游戏目录。')
    version_file = game / 'ThePiper_Data/StreamingAssets/yoo/Main/PackageManifest_Main.version'
    package_version = version_file.read_text(encoding='utf-8-sig').strip() if version_file.is_file() else ''
    if not package_version or '/' in package_version or '\\' in package_version or '..' in package_version:
        raise ValueError('游戏资源版本文件无效。')
    manifest = version_file.parent / f'PackageManifest_Main_{package_version}.bytes'
    if not manifest.is_file():
        raise ValueError('当前版本的游戏资源清单缺失。')
    assembly, metadata = (file.read_bytes() for file in paths)
    hashes = [digest(assembly), digest(metadata)]
    candidates = profiles()
    selected = next((profile for profile in candidates if
                    [profile['GameAssembly_sha256'], profile['global_metadata_sha256']] == hashes), None)
    mode = 'reviewed'
    mismatches = []
    if selected is None:
        try:
            selected = match_structure(assembly, metadata, candidates, mismatches)
        except (ValueError, struct.error, IndexError, UnicodeError, KeyError):
            mismatches.append('当前游戏文件的存档结构尚不能识别')
            selected = None
        mode = 'structural'
    if selected is None:
        raise ValueError(f'检测到游戏版本 {package_version}。{mismatches[-1]}，当前工坊尚未完成兼容核对。请下载新版黎明工坊后重新准备。')
    return {'format': REPORT_VERSION, 'mode': mode, 'profile': selected['id'], 'schema': selected['schema'],
            'package_version': package_version, 'GameAssembly_sha256': hashes[0], 'global_metadata_sha256': hashes[1],
            'manifest_sha256': digest(manifest.read_bytes()), 'installation_stamp': installation_stamp(game),
            'serialized_contract_verified': True,
            'message': '已核对的游戏版本' if mode == 'reviewed' else '存档结构与序列化代码一致，可兼容使用'}


def install_schema(report, data_root):
    """Normalize config member names by native-confirmed table/tag/type mapping."""
    source = SCHEMAS / report['schema']
    if source.parent != SCHEMAS or not source.is_dir():
        raise ValueError('兼容规则中的存档结构不存在。')
    target = Path(data_root) / 'schema'
    target.mkdir(parents=True, exist_ok=True)
    canonical = json.loads((BASELINE / 'config_schema.json').read_text(encoding='utf-8'))
    baseline = {typ['name']: typ for typ in canonical['types']}
    current = json.loads((source / 'config_schema.json').read_text(encoding='utf-8'))
    for typ in current['types']:
        old = {field['protobuf_tag']: field for field in baseline.get(typ['name'], {}).get('fields', [])
               if field.get('protobuf_tag') is not None}
        for field in typ.get('fields', []):
            previous = old.get(field.get('protobuf_tag'))
            if previous is None:
                continue
            if previous['type_text'] != field['type_text'] or previous['wire_type'] != field['wire_type']:
                raise ValueError('配置字段类型发生变化，无法使用既有编辑规则：' + typ['name'])
            field['source_name'] = field['name']
            field['name'] = previous['name']
    current['naming'] = 'Canonical field aliases from native-confirmed table/tag/type; source_name retains the current name.'
    (target / 'config_schema.json').write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for filename in ('save_schema.json', 'enums.json'):
        shutil.copyfile(source / filename, target / filename)


def begin_preparation(data_root):
    Path(data_root).mkdir(parents=True, exist_ok=True)
    (Path(data_root) / 'compatibility.json').unlink(missing_ok=True)


def complete_preparation(report, data_root, game):
    if installation_stamp(game) != report['installation_stamp']:
        raise ValueError('准备过程中游戏文件发生更新，请重新准备。')
    required = ('configs/index.json', 'configs/物品目录.json', 'configs/分类目录.json', 'resources/summary.json',
                'schema/save_schema.json', 'schema/config_schema.json', 'schema/enums.json')
    if not all((Path(data_root) / file).is_file() for file in required):
        raise ValueError('准备资料缺少必要文件，未标记为完成。')
    complete = {**report, 'ready': True}
    temporary = Path(data_root) / 'compatibility.json.tmp'
    temporary.write_text(json.dumps(complete, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(Path(data_root) / 'compatibility.json')
    return complete


def installation_stamp(game):
    """Include resource-manifest identity, not just DLL timestamps."""
    game = Path(game)
    version = game / 'ThePiper_Data/StreamingAssets/yoo/Main/PackageManifest_Main.version'
    text = version.read_text(encoding='utf-8-sig').strip()
    if not text or '/' in text or '\\' in text or '..' in text:
        raise ValueError('资源版本标识无效。')
    files = [game / 'GameAssembly.dll', game / 'ThePiper_Data/il2cpp_data/Metadata/global-metadata.dat',
             version, version.parent / f'PackageManifest_Main_{text}.bytes']
    return [[file.stat().st_size, file.stat().st_mtime_ns] for file in files]


def require_prepared(game, data_root):
    try:
        report = json.loads((Path(data_root) / 'compatibility.json').read_text(encoding='utf-8'))
        profile = next((entry for entry in profiles() if entry['id'] == report.get('profile')), None)
        if not profile or report.get('ready') is not True or report.get('format') != REPORT_VERSION or report.get('schema') != profile['schema']:
            raise ValueError('Prepared compatibility profile is invalid.')
        if report.get('installation_stamp') != installation_stamp(game):
            raise ValueError('Game files changed.')
        for filename in ('save_schema.json', 'config_schema.json', 'enums.json'):
            if not (Path(data_root) / 'schema' / filename).is_file():
                raise ValueError('Prepared schemas are incomplete.')
        return report
    except (OSError, ValueError, StopIteration, KeyError):
        raise ValueError('游戏或准备资料已更新。请在启动设置重新准备，或运行 python prepare.py。') from None


def require_unchanged_install(game, data_root, startup_report):
    """Keep the running process bound to the contract it originally loaded."""
    current = require_prepared(game, data_root)
    fields = ('profile', 'schema', 'GameAssembly_sha256', 'global_metadata_sha256', 'manifest_sha256', 'installation_stamp')
    if any(current.get(field) != startup_report.get(field) for field in fields):
        raise ValueError('工作台运行期间游戏或资料已更新，请重新准备并重启工作台。')
