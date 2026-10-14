import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont

data = json.loads(Path('output/catalog_pairs/review/errors_39_analysis.json').read_text(encoding='utf-8'))

out_dir = Path('output/catalog_pairs/review/debug_39_inspect')

for idx, item in enumerate(data, 1):
    bc = item['barcode']
    src = item.get('source')
    name = item.get('name', '')
    old_mode = item.get('old_mode', '')
    src_name = Path(src).name if src else ''
    print(f"{idx:02d} | {bc} | {old_mode:<12} | {src_name:<15} | {name[:40]}")
