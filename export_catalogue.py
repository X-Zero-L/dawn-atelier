"""Decode all extracted configuration tables and build a localized data catalogue."""

import csv
import json
from pathlib import Path
import struct

from save_codec import ROOT, Schema, element_type, wire_fields
from app_config import DATA_ROOT

TABLES = DATA_ROOT / 'bundles' / 'tables-decoded'
OUTPUT = DATA_ROOT / 'configs'


def raw_message(data):
    result = {}
    for field in wire_fields(data):
        value = field['value']
        if isinstance(value, bytes):
            try:
                value = {'text': value.decode('utf-8'), 'wire': field['wire']}
            except UnicodeDecodeError:
                value = {'hex': value.hex(), 'wire': field['wire']}
        result.setdefault(str(field['tag']), []).append(value)
    return result


def fields_by_tag(schema, name):
    return {tag: field['name'] for tag, field in schema.confirmed('Example.' + name).items()}


def main():
    schema = Schema()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalogues = {}
    summary = []
    for path in sorted(TABLES.glob('*.bytes')):
        data = path.read_bytes()
        count = struct.unpack_from('<I', data)[0]
        records = wire_fields(data[4:])
        ids = [f['value'].decode('utf-8') if f['wire'] == 2 else f['value']
               for f in records if f['tag'] == 1 and f['wire'] in (0, 2)]
        row_bytes = [f['value'] for f in records if f['tag'] == 2 and f['wire'] == 2]
        if not count == len(ids) == len(row_bytes):
            raise ValueError(f'{path.name}: declared count / IDs / rows disagree')
        typ = 'Example.' + path.stem
        named = typ in schema.types
        rows = [schema.decode(row, typ) if named else raw_message(row) for row in row_bytes]
        unknown_count = sum(sum(key.startswith('@') for key in row) for row in rows) if named else len(rows)
        document = {'table': path.stem, 'count': count, 'schema_type': typ if named else None,
                    'ids': ids, 'rows': rows, 'unknown_top_level_fields': unknown_count,
                    'source': str(path.relative_to(DATA_ROOT))}
        catalogues[path.stem] = document
        (OUTPUT / (path.stem + '.json')).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        summary.append({key: document[key] for key in ('table', 'count', 'schema_type', 'unknown_top_level_fields')})

    language_fields = fields_by_tag(schema, 'Language')
    lang = {row[language_fields[1]]: row for row in catalogues['Language']['rows']}

    def translate(value, language=2):
        row = lang.get(value)
        return row.get(language_fields[language], '') if row else ''

    item_fields = fields_by_tag(schema, 'ItemConfig')
    items = []
    for row in catalogues['ItemConfig']['rows']:
        ident = row.get(item_fields[1])
        name_id = row.get(item_fields[2])
        desc_id = row.get(item_fields[3])
        items.append({'id': ident, 'name': translate(name_id), 'description': translate(desc_id),
                      'name_en': translate(name_id, 4), 'name_language_id': name_id,
                      'description_language_id': desc_id, 'raw': row})
    names = {item['id']: item['name'] for item in items}
    (OUTPUT / '物品目录.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUTPUT / '物品目录.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['id', 'name', 'description', 'name_en', 'name_language_id', 'description_language_id'])
        writer.writeheader()
        writer.writerows({key: value for key, value in item.items() if key != 'raw'} for item in items)

    # These labels follow the localized name-reference column, corroborated by
    # the row's debug name and/or asset name; raw obfuscated fields remain intact.
    friendly = {}
    for table in ('AttributesConfig', 'BuildingConfig', 'FarmGeneConfig', 'SkillConfig',
                  'UnitConfig', 'AlchemyTalentConfig', 'RelicEffectConfig', 'RecipeConfig',
                  'FishConfig', 'FarmCropConfig', 'BuffConfig'):
        fields = fields_by_tag(schema, table)
        view = []
        for row in catalogues.get(table, {}).get('rows', []):
            ident = row.get(fields.get(1))
            name_tag = 3 if table == 'RecipeConfig' else 2
            reference = row.get(fields.get(name_tag))
            title = translate(reference) if isinstance(reference, int) else reference if isinstance(reference, str) else ''
            if not title:
                title = names.get(ident, '')
            if not title:
                title = next((v for v in row.values() if isinstance(v, str) and any('\u4e00' <= ch <= '\u9fff' for ch in v) and not v.startswith('Assets/')), '')
            view.append({'id': ident, 'name': title, 'raw': row})
        friendly[table] = view
    (OUTPUT / '分类目录.json').write_text(json.dumps(friendly, ensure_ascii=False, indent=2), encoding='utf-8')
    index = {'tables': summary, 'table_count': len(summary),
             'row_count': sum(entry['count'] for entry in summary),
             'item_count': len(items), 'language_entries': len(lang),
             'notes': ['Raw game field names remain obfuscated; readable titles are joined through the language table.',
                       'Only native-confirmed protobuf fields receive names; unconfirmed fields retain @tag_N.']}
    (OUTPUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 游戏配置目录', '', f"共 {len(summary)} 张配置表、{index['row_count']} 行。物品 {len(items)} 种；语言条目 {len(lang)} 条。", '',
             '| 配置表 | 行数 | 字段映射 |', '| --- | ---: | --- |']
    for entry in summary:
        status = '具名字段' if entry['schema_type'] else '原始字段编号'
        if entry['unknown_top_level_fields']:
            status += f"；{entry['unknown_top_level_fields']} 处待确认"
        lines.append(f"| [{entry['table']}]({entry['table']}.json) | {entry['count']} | {status} |")
    lines += ['', '## 常用文件', '', '- [物品目录 CSV](物品目录.csv)：ID、中文名、英文名、描述。',
              '- [物品目录 JSON](物品目录.json)：同时保留每行完整原始字段。',
              '- [分类目录](分类目录.json)：建筑、基因、技能、角色、天赋、配方等的 ID 和名称。',
              '', '名称映射来自本地语言表。混淆字段的业务意义尚未全部恢复，原始字段和值均保留。']
    (OUTPUT / '目录.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(index, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
