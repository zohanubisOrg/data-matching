import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import sys

sys.path.insert(0, 'src')
sys.path.insert(0, 'scripts')
from product_mapper.vision.barcode_side_splitter import scan_file

data = json.loads(Path('output/catalog_pairs/review/errors_39_analysis.json').read_text(encoding='utf-8'))

out_dir = Path('output/catalog_pairs/review/debug_39_inspect')
out_dir.mkdir(parents=True, exist_ok=True)

for idx, item in enumerate(data, 1):
    bc = item['barcode']
    src = item.get('source')
    if not src or not Path(src).exists():
        continue
    img = ImageOps.exif_transpose(Image.open(src))
    w, h = img.size
    
    # Barcode center
    bc_c = item.get('bc_center')
    old_mode = item.get('old_mode')
    
    # Save a small preview of the source image with barcode marked
    preview = img.copy()
    preview.thumbnail((800, 800))
    pw, ph = preview.size
    sx, sy = pw / w, ph / h
    
    draw = ImageDraw.Draw(preview)
    if bc_c:
        bx, by = bc_c[0] * sx, bc_c[1] * sy
        draw.ellipse((bx - 15, by - 15, bx + 15, by + 15), outline='red', width=4)
    
    preview.save(out_dir / f"{idx:02d}_{bc}_{old_mode}.jpg", quality=85)

print("Saved all 39 previews to", out_dir)
