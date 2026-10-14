import json
from pathlib import Path
from PIL import Image, ImageOps
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parent.parent

# Let's inspect the 21 source images
data = json.loads((ROOT / "output/catalog_pairs/review/analysis_21_errors.json").read_text(encoding="utf-8"))

for d in data:
    bc = d["barcode"]
    src_name = d["source_file"]
    # find path
    src_path = None
    for folder in ["G1_original", "G2_original", "G3_Original", "G4-original"]:
        p = ROOT / "source-import" / folder / src_name
        if p.exists():
            src_path = p
            break
    if not src_path:
        print(f"Could not find {src_name}")
        continue
    
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    
    det = d["barcode_detected"]
    cx_pct = det["cx_pct"] if det else 0.5
    cy_pct = det["cy_pct"] if det else 0.5
    
    print(f"[{bc}] {src_name} ({w}x{h}) barcode at ({cx_pct}, {cy_pct})")
    img.close()
