import os
import sys
import shutil
import json
import re
from pathlib import Path
from PIL import Image
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely
from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
JPG_FRONT_DIR = OUTPUT_DIR / "front_images_jpg"
WEBP_FRONT_DIR = OUTPUT_DIR / "front_images_webp"
WEB_PUBLIC_DIR = PROJECT_ROOT / "web/public/products/front"

# Create clean directories
for d in [JPG_FRONT_DIR, WEBP_FRONT_DIR, WEB_PUBLIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

excel_path = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
df = pd.read_excel(excel_path)
print(f"Loaded Master Excel with {len(df)} records.")

source_dirs = [
    PROJECT_ROOT / "source-import/G2_original",
    PROJECT_ROOT / "source-import/G3_Original",
    PROJECT_ROOT / "source-import/G4-original",
    PROJECT_ROOT / "source-import/Nyt25.09.26"
]

def find_source_image(photo_name: str) -> Path | None:
    for sdir in source_dirs:
        p = sdir / photo_name
        if p.exists():
            return p
        for f in sdir.iterdir():
            if f.name.lower() == photo_name.lower():
                return f
    # Fallback to output/shopify_import/images
    alt_p = OUTPUT_DIR / "images" / (Path(photo_name).stem + ".jpg")
    if alt_p.exists():
        return alt_p
    alt_p2 = OUTPUT_DIR / "images" / (Path(photo_name).stem + ".webp")
    if alt_p2.exists():
        return alt_p2
    return None

SPECIFIC_MANUAL_BOXES = {
    "IMG_0427.jpeg": ([205, 645, 955, 935], 0),  # FaThai lime juice: right front single bottle
    "IMG_5156.HEIC": ([50, 20, 980, 980], 0),    # Asian Pearl Bonito fish: whole fish bag
    "IMG_5080.HEIC": ([50, 20, 980, 950], 0),    # Asian Pearl Mekong Catfish: whole fish bag
    "IMG_5086.HEIC": ([50, 50, 980, 980], 0),    # Asian Choice Shrimp: whole frozen shrimp bag
    "20260916_110956474_iOS.heic": ([150, 80, 980, 850], 0),  # Fresh Mangosteen
    "20260916_111433112_iOS.heic": ([80, 150, 995, 750], 0),  # Fresh Coriander with roots
    "20260916_111402964_iOS.heic": ([80, 80, 1000, 800], 0),  # Fresh Culantro
}

def crop_and_save_both(img_path: Path, box_1000: list[int], rotation: int, file_stem: str):
    pil_im = open_image_safely(img_path)
    w, h = pil_im.size
    ymin, xmin, ymax, xmax = box_1000
    
    ymin = max(0, min(1000, ymin))
    xmin = max(0, min(1000, xmin))
    ymax = max(0, min(1000, ymax))
    xmax = max(0, min(1000, xmax))

    if ymax <= ymin or xmax <= xmin or (ymax - ymin < 50) or (xmax - xmin < 50):
        ymin, xmin, ymax, xmax = 0, 0, 1000, 1000

    left = int(xmin * w / 1000.0)
    top = int(ymin * h / 1000.0)
    right = int(xmax * w / 1000.0)
    bottom = int(ymax * h / 1000.0)

    cropped = pil_im.crop((left, top, right, bottom))
    
    if rotation == 90:
        cropped = cropped.rotate(270, expand=True)
    elif rotation == 180:
        cropped = cropped.rotate(180, expand=True)
    elif rotation == 270:
        cropped = cropped.rotate(90, expand=True)

    jpg_path = JPG_FRONT_DIR / f"{file_stem}.jpg"
    webp_path = WEBP_FRONT_DIR / f"{file_stem}.webp"
    public_webp = WEB_PUBLIC_DIR / f"{file_stem}.webp"

    # Save high-quality JPG (front) and optimized WEBP (front)
    cropped.save(jpg_path, format="JPEG", quality=92)
    cropped.save(webp_path, format="WEBP", quality=90)
    cropped.save(public_webp, format="WEBP", quality=90)

    return f"{file_stem}.webp", cropped.size

print("Starting export to dual front folders: front_images_jpg and front_images_webp...")

processed = 0
for idx, row in df.iterrows():
    photo_name = str(row.get('source_photo', '')).strip()
    barcode = str(row.get('barcode', '')).strip()
    if barcode.endswith('.0'):
        barcode = barcode[:-2]
        df.at[idx, 'barcode'] = barcode

    src_p = find_source_image(photo_name)
    if not src_p:
        print(f"[{idx}] Missing source: {photo_name}")
        continue

    file_stem = barcode if barcode and not barcode.startswith('NO_BARCODE') else f"NO_BARCODE_{Path(photo_name).stem}"

    box = [0, 0, 1000, 1000]
    rot = int(row.get('front_rotation', 0)) if pd.notna(row.get('front_rotation')) else 0

    if photo_name in SPECIFIC_MANUAL_BOXES:
        box, rot = SPECIFIC_MANUAL_BOXES[photo_name]
    else:
        raw_box = str(row.get('front_box_2d', '')).strip()
        if raw_box.startswith('['):
            try:
                parsed = json.loads(raw_box)
                if len(parsed) == 4:
                    box = parsed
            except Exception:
                pass

    webp_name, img_size = crop_and_save_both(src_p, box, rot, file_stem)
    
    df.at[idx, 'front_box_2d'] = json.dumps(box)
    df.at[idx, 'front_rotation'] = rot
    df.at[idx, 'Website Front Image'] = webp_name
    df.at[idx, 'image_width_px'] = img_size[0]
    df.at[idx, 'image_height_px'] = img_size[1]
    
    processed += 1
    if processed % 150 == 0:
        print(f"Processed {processed} / {len(df)} images...")

# Save master files
df.to_excel(excel_path, index=False)
csv_path = OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv"
export_shopify_csv(df.to_dict(orient="records"), csv_path, batch_tag="G2_G5_BATCH")

print("\n================ DUAL FOLDERS READY ================")
print(f"1. JPG Front Folder: {JPG_FRONT_DIR} ({len(list(JPG_FRONT_DIR.glob('*.jpg')))} items)")
print(f"2. WEBP Front Folder: {WEBP_FRONT_DIR} ({len(list(WEBP_FRONT_DIR.glob('*.webp')))} items)")
print(f"3. Shopify Import CSV: {csv_path}")
print(f"4. Master Excel: {excel_path}")
print("====================================================")
