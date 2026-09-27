"""Export selected installed game artwork and inventory sprites for the local UI."""

import json
from pathlib import Path
import re
import struct
from PIL import Image

from app_config import APP_ROOT as ROOT, DATA_ROOT, ASSET_ROOT
OUT = ASSET_ROOT


def object_name(data):
    length = struct.unpack_from('<I', data)[0]
    return data[4:4 + length].decode('utf-8'), (length + 7) // 4 * 4


def texture_image(data, folder):
    name, base = object_name(data)
    width, height, _, _, kind, _ = struct.unpack_from('<6I', data, base + 8)
    archive = data.index(b'archive:/')
    offset, size, path_length = struct.unpack_from('<QII', data, archive - 16)
    path = data[archive:archive + path_length].decode().rsplit('/', 1)[-1]
    with (folder / path).open('rb') as source:
        source.seek(offset)
        pixels = source.read(size)
    if kind in (10, 12, 25):
        image = Image.frombytes('RGBA', (width, height), pixels, 'bcn', {10: 1, 12: 3, 25: 7}[kind])
    elif kind == 4:
        image = Image.frombytes('RGBA', (width, height), pixels[:width * height * 4])
    else:
        raise ValueError(f'Unsupported texture format {kind}')
    return name, image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'items').mkdir(exist_ok=True)
    index = json.loads((DATA_ROOT / 'resources/index.json').read_text())
    wanted = {'assets_gameres_arts_logo.bundle', 'assets_gameres_arts_ui_common_startwindow.bundle', 'assets_gameres_arts_atlas.bundle'}
    report = []
    for bundle in index:
        if bundle['name'] not in wanted:
            continue
        for entry in bundle['files']:
            if not entry.get('objects'):
                continue
            path = DATA_ROOT / entry['path']
            serialized = path.read_bytes()
            images = {}
            objects = entry['objects']
            for obj in objects:
                if obj['class_id'] != 28:
                    continue
                data = serialized[obj['offset']:obj['offset'] + obj['size']]
                name, _ = object_name(data)
                selected = name in ('People', 'BGsky', 'FG', 'CloudLeft', 'GameIcon')
                if bundle['name'].endswith('_atlas.bundle'):
                    selected = name in ('CropSeed', 'ItemIcon1', 'ItemIcon2', 'ItemIcon3', 'AlchemyItem1', 'AlchemyItem2', 'FishIcon', 'NpcIcon01', 'Crop1', 'Crop2', 'Crop3', 'Crop4')
                if not selected:
                    continue
                name, image = texture_image(data, path.parent)
                images[obj['path_id']] = image
                if name in ('People', 'BGsky', 'FG', 'CloudLeft', 'GameIcon'):
                    image.thumbnail((1600, 1000), Image.Resampling.LANCZOS)
                    image.save(OUT / (name.lower() + '.webp'), quality=90)
            if not bundle['name'].endswith('_atlas.bundle'):
                continue
            for obj in objects:
                if obj['class_id'] != 213:
                    continue
                data = serialized[obj['offset']:obj['offset'] + obj['size']]
                name, position = object_name(data)
                match = re.fullmatch(r'Icon_(\d+)', name)
                if not match:
                    continue
                x, y, width, height = struct.unpack_from('<4f', data, position)
                sources = [ident for ident in images if struct.pack('<iq', 0, ident) in data]
                if len(sources) != 1:
                    continue
                image = images[sources[0]]
                if not (0 <= x < image.width and 0 <= y < image.height and width > 0 and height > 0 and x + width <= image.width + 1 and y + height <= image.height + 1):
                    continue
                crop = image.crop((round(x), round(image.height - y - height), round(x + width), round(image.height - y)))
                crop.thumbnail((144, 144), Image.Resampling.LANCZOS)
                target = OUT / 'items' / (match[1] + '.webp')
                crop.save(target, quality=90)
                report.append({'id': int(match[1]), 'sprite': name, 'file': str(target.relative_to(OUT))})
    (OUT / 'art-index.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'item_sprites': len(report), 'assets': str(OUT)}))


if __name__ == '__main__':
    main()
