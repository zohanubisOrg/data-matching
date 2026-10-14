import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pillow_heif
pillow_heif.register_heif_opener()

data = json.loads(Path('output/catalog_pairs/review/errors_39_analysis.json').read_text(encoding='utf-8'))
out_dir = Path('output/catalog_pairs/review/debug_39_grid')
out_dir.mkdir(parents=True, exist_ok=True)

for idx, item in enumerate(data, 1):
    bc = item['barcode']
    src = item.get('source')
    if not src or not Path(src).exists():
        continue
    img = ImageOps.exif_transpose(Image.open(src))
    preview = img.copy()
    preview.thumbnail((900, 900))
    pw, ph = preview.size
    
    draw = ImageDraw.Draw(preview)
    # Draw 10% grid lines
    for pct in range(10, 100, 10):
        gx = int(pw * pct / 100)
        gy = int(ph * pct / 100)
        draw.line([(gx, 0), (gx, ph)], fill=(200, 200, 200, 128), width=1)
        draw.line([(0, gy), (pw, gy)], fill=(200, 200, 200, 128), width=1)
        draw.text((gx + 2, 5), f"{pct}%", fill="yellow")
        draw.text((5, gy + 2), f"{pct}%", fill="yellow")
    
    # Mark barcode if present
    bc_c = item.get('bc_center')
    if bc_c:
        w, h = img.size
        bx, by = int(bc_c[0] * pw / w), int(bc_c[1] * ph / h)
        draw.rectangle([bx - 15, by - 15, bx + 15, by + 15], outline="red", width=3)
        draw.text((bx + 20, by - 10), "BC", fill="red")
        
    draw.text((10, ph - 25), f"#{idx:02d} | {bc} | {Path(src).name}", fill="lime")
    preview.save(out_dir / f"{idx:02d}_{bc}.jpg", quality=85)

print("Saved all 39 grid images to", out_dir)
