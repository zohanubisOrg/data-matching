import os
import sys
import json
import time
import re
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageOps
import pandas as pd
import cv2
import numpy as np
import zxingcpp
from google import genai
from google.genai import types

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely
from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

# Directories
OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
WEB_FRONT_DIR = OUTPUT_DIR / "web_front_images"
IMAGES_DIR = OUTPUT_DIR / "images"
WEB_PUBLIC_DIR = PROJECT_ROOT / "web/public/products/front"

WEB_FRONT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
WEB_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

# API Keys setup
raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
for k, v in os.environ.items():
    if (k.startswith("GEMINI_API_KEY_") or k.startswith("GOOGLE_API_KEY_")) and v.strip() not in keys:
        keys.append(v.strip())

print(f"Loaded {len(keys)} Gemini API keys.")
clients = [genai.Client(api_key=k, http_options={"timeout": 60000}) for k in keys]
key_idx = 0

def get_client():
    global key_idx
    c = clients[key_idx % len(clients)]
    key_idx += 1
    return c

CANDIDATE_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"]

PROMPT_ANALYSIS = """
You are an expert AI for retail grocery product cataloging and computer vision.
Analyze this photo of imported supermarket products (which may show dual-sided packaging, front/back, multiple packages, or single products).

Your tasks:
1. **FULL PRODUCT FRONT DETECTION**:
   - Locate the **FRONT retail display face** of the product (the primary commercial face with brand logo, main product title, and food/hero graphics).
   - Return the tight bounding box `front_box_2d: [ymin, xmin, ymax, xmax]` (coordinates normalized 0-1000) that encloses the **ENTIRE PHYSICAL PRODUCT PACKAGE** of that front face (from top rim/seal/cap down to the very bottom base, and full width).
   - CRITICAL REQUIREMENT: NEVER crop only a label, tag, barcode, or small cropped patch! The bounding box must contain the ENTIRE retail package container (bottle, can, box, bag, pouch).
   - If front and back are side-by-side (left vs right, or top vs bottom), enclose the ENTIRE FRONT product.
   - If only one product package is present, enclose the ENTIRE product package.
   - Determine `front_rotation_to_upright`: degrees clockwise (0, 90, 180, 270) to orient the front packaging upright so brand and title text are readable horizontally from left to right.

2. **BARCODE & PRODUCT DATA EXTRACTION**:
   - Read the exact barcode digits (EAN-13, EAN-8, UPC-A, 8-14 digits) visible anywhere in this photo.
   - Extract the full commercial product name in English/Danish (e.g. "Royal Thai Glutinous Rice 1kg").
   - Extract brand, net weight/quantity, category.

Return strictly valid JSON:
{
  "barcode": "string digits only or null",
  "product_name": "Full descriptive commercial name",
  "brand": "Brand name or null",
  "net_weight": "e.g. 500g, 1kg, 250ml",
  "category": "e.g. Rice, Noodles, Snacks, Beverages, Frozen, Sauces, Produce",
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "front_description": "short note explaining what is in front_box_2d"
}
"""

def scan_barcode_zxing(pil_im: Image.Image) -> str | None:
    try:
        cv_img = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                cur = cv_img
            elif angle == 90:
                cur = cv2.rotate(cv_img, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                cur = cv2.rotate(cv_img, cv2.ROTATE_180)
            elif angle == 270:
                cur = cv2.rotate(cv_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
            results = zxingcpp.read_barcodes(cur)
            for r in results:
                t = r.text.strip()
                if t.isdigit() and len(t) in [8, 12, 13, 14]:
                    return t
        
        # CLAHE
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        for angle in [0, 90, 180, 270]:
            if angle == 0:
                cur = enhanced
            elif angle == 90:
                cur = cv2.rotate(enhanced, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                cur = cv2.rotate(enhanced, cv2.ROTATE_180)
            elif angle == 270:
                cur = cv2.rotate(enhanced, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
            results = zxingcpp.read_barcodes(cur)
            for r in results:
                t = r.text.strip()
                if t.isdigit() and len(t) in [8, 12, 13, 14]:
                    return t
    except Exception:
        pass
    return None

def analyze_image_gemini(img_path: Path, max_retries=4) -> dict | None:
    pil_im = open_image_safely(img_path)
    max_dim = 1400
    w, h = pil_im.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        pil_im = pil_im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    
    import io
    buf = io.BytesIO()
    pil_im.convert("RGB").save(buf, format="JPEG", quality=88)
    img_bytes = buf.getvalue()

    for attempt in range(max_retries):
        model_name = CANDIDATE_MODELS[attempt % len(CANDIDATE_MODELS)]
        client = get_client()
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    PROMPT_ANALYSIS
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            data = json.loads(text.strip())
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            return data if isinstance(data, dict) else None
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
            
    return None

def crop_and_save(img_path: Path, box_1000: list[int], rotation: int, barcode_or_id: str):
    pil_im = open_image_safely(img_path)
    w, h = pil_im.size
    ymin, xmin, ymax, xmax = box_1000
    
    # clamp
    ymin = max(0, min(1000, ymin))
    xmin = max(0, min(1000, xmin))
    ymax = max(0, min(1000, ymax))
    xmax = max(0, min(1000, xmax))

    # check if box is valid
    if ymax <= ymin or xmax <= xmin or (ymax - ymin < 50) or (xmax - xmin < 50):
        ymin, xmin, ymax, xmax = 0, 0, 1000, 1000

    left = int(xmin * w / 1000.0)
    top = int(ymin * h / 1000.0)
    right = int(xmax * w / 1000.0)
    bottom = int(ymax * h / 1000.0)

    cropped = pil_im.crop((left, top, right, bottom))
    
    # Rotation
    if rotation == 90:
        cropped = cropped.rotate(270, expand=True)
    elif rotation == 180:
        cropped = cropped.rotate(180, expand=True)
    elif rotation == 270:
        cropped = cropped.rotate(90, expand=True)

    # Save webp and jpg
    webp_path = WEB_FRONT_DIR / f"{barcode_or_id}.webp"
    jpg_path = IMAGES_DIR / f"{barcode_or_id}.jpg"
    public_webp = WEB_PUBLIC_DIR / f"{barcode_or_id}.webp"

    cropped.save(webp_path, format="WEBP", quality=90)
    cropped.save(jpg_path, format="JPEG", quality=90)
    cropped.save(public_webp, format="WEBP", quality=90)

    return f"{barcode_or_id}.webp", cropped.size

if __name__ == "__main__":
    excel_path = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    df = pd.read_excel(excel_path)
    df['barcode'] = df['barcode'].astype(str)
    print(f"Loaded Master table with {len(df)} records.")

    source_dirs = [
        PROJECT_ROOT / "source-import/G2_original",
        PROJECT_ROOT / "source-import/G3_Original",
        PROJECT_ROOT / "source-import/G4-original",
        PROJECT_ROOT / "source-import/Nyt25.09.26"
    ]

    def find_photo_path(photo_name: str) -> Path | None:
        for sdir in source_dirs:
            p = sdir / photo_name
            if p.exists():
                return p
            for f in sdir.iterdir():
                if f.name.lower() == photo_name.lower():
                    return f
        # Output images fallback
        alt_p = IMAGES_DIR / (Path(photo_name).stem + ".jpg")
        if alt_p.exists():
            return alt_p
        return None

    # Identify items needing attention:
    # 1. NO_BARCODE items
    # 2. Specific test barcodes mentioned by user
    # 3. Items with suspicious small boxes (tag-only crops or narrow slivers)
    
    user_test_codes = ['8716789006523', '12415762', '4016337900254', '8858306001489', '8888296019010', '8901161105066', '8934563138165', '8936116500610']
    
    indices_to_fix = set()

    for idx, row in df.iterrows():
        bc_str = str(row.get('barcode', '')).strip()
        photo_str = str(row.get('source_photo', '')).strip()
        front_box = str(row.get('front_box_2d', '')).strip()

        # 1. NO_BARCODE
        if bc_str in ['nan', 'None', '', 'NO_BARCODE'] or 'NO_BARCODE' in bc_str:
            indices_to_fix.add(idx)
            continue

        # 2. User mentioned codes
        if any(tc in bc_str for tc in user_test_codes):
            indices_to_fix.add(idx)
            continue

        # 3. Suspicious boxes: check height / width
        try:
            box = json.loads(front_box) if front_box.startswith('[') else None
            if box and len(box) == 4:
                bh = box[2] - box[0]
                bw = box[3] - box[1]
                # If height is too small (< 25%) or width is too small (< 15%)
                if bh < 250 or bw < 150:
                    indices_to_fix.add(idx)
                    continue
        except Exception:
            pass

    print(f"Total rows identified for deep review & fix: {len(indices_to_fix)}")

    fixed_count = 0
    for idx in sorted(list(indices_to_fix)):
        row = df.loc[idx]
        photo_name = str(row.get('source_photo', '')).strip()
        orig_bc = str(row.get('barcode', '')).strip()
        photo_path = find_photo_path(photo_name)

        if not photo_path:
            print(f"[{idx}] Photo not found: {photo_name}")
            continue

        print(f"\n--- Processing row {idx}: {photo_name} (Current BC: {orig_bc}) ---")
        
        # 1. Fast ZXing Barcode check first
        pil_im = open_image_safely(photo_path)
        zx_barcode = scan_barcode_zxing(pil_im)
        
        # 2. Gemini Analysis for full front box + metadata + barcode
        gem_res = analyze_image_gemini(photo_path)
        
        final_bc = orig_bc
        if zx_barcode:
            final_bc = re.sub(r'\D', '', zx_barcode)
        elif gem_res and gem_res.get("barcode"):
            raw_b = str(gem_res.get("barcode")).strip()
            final_bc = re.sub(r'\D', '', raw_b) if re.sub(r'\D', '', raw_b) else raw_b
        
        # Strip trailing .0 from float conversions
        if final_bc.endswith('.0'):
            final_bc = final_bc[:-2]

        # If still no barcode, assign NO_BARCODE_<STEM>
        if final_bc in ['nan', 'None', '', 'NO_BARCODE'] or 'NO_BARCODE' in final_bc:
            final_bc = f"NO_BARCODE_{Path(photo_name).stem}"
            
        final_box = [0, 0, 1000, 1000]
        final_rot = 0
        
        if gem_res:
            g_box = gem_res.get("front_box_2d")
            if g_box and len(g_box) == 4:
                final_box = g_box
            final_rot = gem_res.get("front_rotation_to_upright", 0)
            
            # Update product name if missing or nan
            curr_name = str(row.get('product_name', '')).strip()
            if (curr_name in ['nan', 'None', ''] or 'NO_BARCODE' in curr_name) and gem_res.get('product_name'):
                df.at[idx, 'product_name'] = gem_res.get('product_name')
                df.at[idx, 'full_name_en'] = gem_res.get('product_name')
            
            if gem_res.get('brand') and (str(row.get('brand', '')).strip() in ['nan', 'None', '']):
                df.at[idx, 'brand'] = gem_res.get('brand')

            if gem_res.get('category') and (str(row.get('category', '')).strip() in ['nan', 'None', '']):
                df.at[idx, 'category'] = gem_res.get('category')

        # Crop and save web images
        saved_img_name, img_size = crop_and_save(photo_path, final_box, final_rot, final_bc)
        
        df.at[idx, 'barcode'] = final_bc
        df.at[idx, 'front_box_2d'] = json.dumps(final_box)
        df.at[idx, 'front_rotation'] = final_rot
        df.at[idx, 'Website Front Image'] = saved_img_name
        df.at[idx, 'image_width_px'] = img_size[0]
        df.at[idx, 'image_height_px'] = img_size[1]
        df.at[idx, 'barcode_check_status'] = 'VERIFIED' if not str(final_bc).startswith('NO_BARCODE') else 'NO_BARCODE'
        df.at[idx, 'status'] = 'READY'

        print(f" -> RESULT: BC={final_bc} | Box={final_box} | Rot={final_rot} | Name={df.at[idx, 'product_name']}")
        fixed_count += 1
        
        # Save every 5 items
        if fixed_count % 5 == 0:
            df.to_excel(excel_path, index=False)
            
        time.sleep(0.5)

    # Save updated Excel and CSV
    df.to_excel(excel_path, index=False)
    print(f"\nSaved updated Master Excel to {excel_path}")

    csv_path = OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv"
    export_shopify_csv(df, csv_path)
    print(f"Saved updated Shopify Import CSV to {csv_path}")
    print(f"Total fixed: {fixed_count} records.")
