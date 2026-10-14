import os
import sys
import shutil
import json
import re
from pathlib import Path
from PIL import Image, ImageOps
import pandas as pd
import cv2
import numpy as np

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
ORIGINAL_PHOTOS_DIR = OUTPUT_DIR / "original_photos"
SHOPIFY_WEB_DIR = OUTPUT_DIR / "shopify_web_images"
WEB_PUBLIC_DIR = PROJECT_ROOT / "web/public/products/front"

ORIGINAL_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
SHOPIFY_WEB_DIR.mkdir(parents=True, exist_ok=True)
WEB_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

excel_path = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
df = pd.read_excel(excel_path)
print(f"Loaded Master Excel: {len(df)} records.")

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

def crop_and_export(img_path: Path, box_1000: list[int], rotation: int, target_name: str):
    pil_im = open_image_safely(img_path)
    w, h = pil_im.size
    ymin, xmin, ymax, xmax = box_1000
    
    # clamp
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

    webp_file = SHOPIFY_WEB_DIR / f"{target_name}.webp"
    jpg_file = SHOPIFY_WEB_DIR / f"{target_name}.jpg"
    public_webp = WEB_PUBLIC_DIR / f"{target_name}.webp"

    cropped.save(webp_file, format="WEBP", quality=90)
    cropped.save(jpg_file, format="JPEG", quality=90)
    cropped.save(public_webp, format="WEBP", quality=90)

    return f"{target_name}.webp", cropped.size

# Specific fixes for multi-item and tag-only items
SPECIFIC_MANUAL_BOXES = {
    # FaThai lime juice: 3 bottles side-by-side -> isolate single right front bottle
    "IMG_0427.jpeg": ([205, 645, 955, 935], 0),
    # Asian Pearl Bonito fish: whole frozen fish bag
    "IMG_5156.HEIC": ([50, 20, 980, 980], 0),
    # Asian Pearl Catfish: whole fish bag
    "IMG_5080.HEIC": ([50, 20, 980, 950], 0),
    # Asian Choice Shrimp: whole frozen shrimp bag
    "IMG_5086.HEIC": ([50, 50, 980, 980], 0),
    # Fresh Mangosteen: whole bag of mangosteens
    "20260916_110956474_iOS.heic": ([150, 80, 980, 850], 0),
    # Fresh Coriander with roots: whole bunch
    "20260916_111433112_iOS.heic": ([80, 150, 995, 750], 0),
    # Fresh Culantro: whole bag
    "20260916_111402964_iOS.heic": ([80, 80, 1000, 800], 0),
}

# 1. Clean old obsolete files in SHOPIFY_WEB_DIR
print("Cleaning old files in web output folders...")
for f in SHOPIFY_WEB_DIR.glob("*"):
    try:
        f.unlink()
    except Exception:
        pass

# 2. Process all records
processed_count = 0
for idx, row in df.iterrows():
    photo_name = str(row.get('source_photo', '')).strip()
    barcode = str(row.get('barcode', '')).strip()
    
    if barcode.endswith('.0'):
        barcode = barcode[:-2]
        df.at[idx, 'barcode'] = barcode

    src_p = find_source_image(photo_name)
    if not src_p:
        print(f"[{idx}] Source photo missing: {photo_name}")
        continue

    # Copy to original_photos folder
    dest_orig = ORIGINAL_PHOTOS_DIR / src_p.name
    if not dest_orig.exists():
        try:
            shutil.copy2(src_p, dest_orig)
        except Exception:
            pass

    # Determine target filename for Shopify web image
    target_slug = barcode if barcode and not barcode.startswith('NO_BARCODE') else f"NO_BARCODE_{Path(photo_name).stem}"
    
    # Get box and rotation
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

    # Save to shopify_web_images
    img_name, img_size = crop_and_export(src_p, box, rot, target_slug)
    
    df.at[idx, 'front_box_2d'] = json.dumps(box)
    df.at[idx, 'front_rotation'] = rot
    df.at[idx, 'Website Front Image'] = img_name
    df.at[idx, 'image_width_px'] = img_size[0]
    df.at[idx, 'image_height_px'] = img_size[1]
    
    processed_count += 1
    if processed_count % 100 == 0:
        print(f"Processed {processed_count} / {len(df)} images...")

# 3. Save Master Excel & Shopify CSV
df.to_excel(excel_path, index=False)
print(f"\nSaved updated Master Excel to {excel_path}")

csv_path = OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv"
export_shopify_csv(df.to_dict(orient="records"), csv_path, batch_tag="G2_G5_BATCH")
print(f"Saved updated Shopify Import CSV to {csv_path}")

print("\n================== STRUCTURE CREATED ==================")
print(f"1. Original Photos Folder: {ORIGINAL_PHOTOS_DIR} ({len(list(ORIGINAL_PHOTOS_DIR.glob('*')))} files)")
print(f"2. Shopify Web Images Folder: {SHOPIFY_WEB_DIR} ({len(list(SHOPIFY_WEB_DIR.glob('*.webp')))} webp, {len(list(SHOPIFY_WEB_DIR.glob('*.jpg')))} jpg)")
print("=======================================================")
