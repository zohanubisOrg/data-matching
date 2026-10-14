import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pillow_heif
pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent

data = json.loads((ROOT / "output/catalog_pairs/review/analysis_21_errors.json").read_text(encoding="utf-8"))
out_dir = ROOT / "output/catalog_pairs/review/grid_21"
out_dir.mkdir(parents=True, exist_ok=True)

for idx, d in enumerate(data, 1):
    bc = d["barcode"]
    src_name = d["source_file"]
    src_path = None
    for folder in ["G1_original", "G2_original", "G3_Original", "G4-original"]:
        p = ROOT / "source-import" / folder / src_name
        if p.exists():
            src_path = p
            break
    if not src_path: continue
    
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    
    # Draw barcode position if detected
    draw = ImageDraw.Draw(img)
    det = d["barcode_detected"]
    if det:
        cx = int(det["cx_pct"] * w)
        cy = int(det["cy_pct"] * h)
        draw.rectangle([cx-50, cy-50, cx+50, cy+50], outline="red", width=10)
    
    # Resize source for preview
    thumb_src = img.copy()
    thumb_src.thumbnail((800, 800))
    
    # Load error back image
    err_back_p = ROOT / f"output/catalog_pairs/image-error-resolve-again/{bc}-back.jpg"
    thumb_err = Image.open(err_back_p) if err_back_p.exists() else Image.new("RGB", (200, 200), "gray")
    thumb_err.thumbnail((800, 800))
    
    # Load front image if exists
    front_p = ROOT / f"output/catalog_pairs/tagged/front-v2/{bc}-front.jpg"
    thumb_front = Image.open(front_p) if front_p.exists() else Image.new("RGB", (200, 200), "gray")
    thumb_front.thumbnail((800, 800))

    # Create comparison canvas
    max_h = max(thumb_src.height, thumb_err.height, thumb_front.height)
    tot_w = thumb_src.width + thumb_err.width + thumb_front.width + 40
    canvas = Image.new("RGB", (tot_w, max_h + 50), "white")
    canvas.paste(thumb_src, (0, 40))
    canvas.paste(thumb_err, (thumb_src.width + 20, 40))
    canvas.paste(thumb_front, (thumb_src.width + thumb_err.width + 40, 40))
    
    draw_c = ImageDraw.Draw(canvas)
    draw_c.text((10, 10), f"#{idx:02d} {bc} [{src_name}] - Left: Source (Red=BC) | Mid: Err Back | Right: Front", fill="black")
    canvas.save(out_dir / f"{idx:02d}_{bc}.jpg", quality=90)
    img.close()

print(f"Generated comparison previews for all 21 items in {out_dir}")
