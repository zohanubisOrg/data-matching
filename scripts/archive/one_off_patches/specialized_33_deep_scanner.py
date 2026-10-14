# -*- coding: utf-8 -*-
"""
Specialized Deep Inspection Pipeline for 33 Target Images
- High-res multi-region patch extraction (Bottom, Left, Right, Shelf Tag, Full)
- Multi-scale contrast enhancement & OpenCV Barcode Detector
- Gemini 3.7 Flash High-Resolution Deep Inspector
- Match against 5,424 Shopbox POS + Supplier Database
"""

import sys
import os
import re
import json
import time
import io
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageEnhance
import openpyxl
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
CUSTOMER_SRC = os.path.join(SOURCE_DIR, "new_source_from_customer")
OUT_FILE = os.path.join(BASE_DIR, "output", "shopify_import", "specialized_33_results.json")

# 1. Load API Key
api_key = None
env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY") and "AIza" in line:
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

client = genai.Client(api_key=api_key) if api_key else None

# 2. Load 5424 POS
f_pos_full = os.path.join(SOURCE_DIR, "Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
pos_by_bc = {}
pos_list = []
wb_full = openpyxl.load_workbook(f_pos_full, data_only=True)
for r in list(wb_full["Ten_ban"].iter_rows(values_only=True))[1:]:
    raw_bc = str(r[7] or "").strip()
    c_bc = re.sub(r"[^\w]", "", raw_bc.replace(".0", ""))
    sku = str(r[8] or "").strip()
    item_info = {
        "pos_category": str(r[0] or "").strip(),
        "product_name": str(r[1] or "").strip(),
        "official_name": str(r[2] or "").strip(),
        "printer_name": str(r[3] or "").strip(),
        "purchase_price": r[4],
        "selling_price": r[5],
        "unit": r[6],
        "barcode": c_bc,
        "sku": sku,
    }
    pos_list.append(item_info)
    if c_bc:
        pos_by_bc[c_bc] = item_info
        pos_by_bc[c_bc.lstrip("0")] = item_info

print(f"Loaded POS items: {len(pos_by_bc)} barcodes.")

# 3. Load 33 Target Photos
folder_map = {
    "G1": os.path.join(SOURCE_DIR, "G1_original"),
    "G2": os.path.join(SOURCE_DIR, "G2_original"),
    "G3": os.path.join(SOURCE_DIR, "G3_Original"),
    "G4": os.path.join(SOURCE_DIR, "G4-original"),
    "G5": os.path.join(SOURCE_DIR, "Nyt25.09.26"),
}

f_resheet = os.path.join(BASE_DIR, r"output\shopify_import_final\Danh_sach_san_pham_can_chup_lai_Barcode.xlsx")
wb_r = openpyxl.load_workbook(f_resheet, data_only=True)
ws_r = wb_r.active
r_headers = [c.value for c in ws_r[3]]
target_items = []
for r in list(ws_r.iter_rows(min_row=4, values_only=True)):
    target_items.append(dict(zip(r_headers, r)))

print(f"Loaded {len(target_items)} target items to scan.")

detector = cv2.barcode.BarcodeDetector()

def extract_regions_and_scan_cv(pil_img):
    w, h = pil_img.size
    regions = [
        ("full", pil_img),
        ("bottom_half", pil_img.crop((0, int(h * 0.5), w, h))),
        ("bottom_third", pil_img.crop((0, int(h * 0.65), w, h))),
        ("left_half", pil_img.crop((0, 0, int(w * 0.5), h))),
        ("right_half", pil_img.crop((int(w * 0.5), 0, w, h))),
        ("shelf_bottom", pil_img.crop((0, int(h * 0.75), w, h))),
    ]
    
    for r_name, r_img in regions:
        cv_img = cv2.cvtColor(np.array(r_img.convert("RGB")), cv2.COLOR_RGB2BGR)
        for rot in [0, 90, 180, 270]:
            if rot == 90:
                rotated = cv2.rotate(cv_img, cv2.ROTATE_90_CLOCKWISE)
            elif rot == 180:
                rotated = cv2.rotate(cv_img, cv2.ROTATE_180)
            elif rot == 270:
                rotated = cv2.rotate(cv_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            else:
                rotated = cv_img
                
            res = detector.detectAndDecode(rotated)
            if len(res) == 4:
                ok, decoded_info, decoded_type, corners = res
            elif len(res) == 3:
                decoded_info, decoded_type, corners = res
                ok = bool(decoded_info)
            else:
                ok, decoded_info = False, None
                
            if ok and decoded_info:
                for bc in decoded_info:
                    clean_b = re.sub(r"[^\d]", "", str(bc).strip())
                    if len(clean_b) >= 8:
                        return clean_b, f"CV_{r_name}_ROT_{rot}"
                        
            # CLAHE
            gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
            res_c = detector.detectAndDecode(enhanced_bgr)
            if len(res_c) == 4:
                ok, decoded_info, decoded_type, corners = res_c
            elif len(res_c) == 3:
                decoded_info, decoded_type, corners = res_c
                ok = bool(decoded_info)
            else:
                ok, decoded_info = False, None
                
            if ok and decoded_info:
                for bc in decoded_info:
                    clean_b = re.sub(r"[^\d]", "", str(bc).strip())
                    if len(clean_b) >= 8:
                        return clean_b, f"CV_CLAHE_{r_name}_ROT_{rot}"
    return None, None

PROMPT_ZOOM_INSPECTOR = """You are a senior computer vision expert specialized in reading difficult, skewed, tiny, or reflected retail barcodes on product packaging in Asian supermarkets.

Task:
Analyze this raw high-resolution supermarket photo in extreme detail:
1. Examine the packaging from top to bottom, the side edges, the bottom edge, any transparent windows showing the back label, AND any shelf price tag/label in front of the product.
2. Look for ANY sequence of 8, 12, 13, or 14 digits corresponding to a retail EAN/UPC barcode.
3. Read the exact brand name, product name in Danish and English, net quantity and unit.
4. If a barcode is visible (even partially or faintly), report the exact digits.
5. If NO barcode is visible after exhaustive inspection, explain precisely where on the physical package the barcode is located (e.g., 'Barcode is on the back panel of the plastic bag, not visible from the front').

Return JSON only:
{
  "barcode_found": true/false,
  "barcode_digits": "exact numeric digits (8-14 digits) or null",
  "barcode_confidence": "high" / "medium" / "low" / "none",
  "barcode_source": "packaging_front / packaging_side / packaging_bottom / shelf_tag / back_label_visible",
  "brand": "Exact brand name",
  "product_title_en": "Natural English name",
  "product_title_da": "Natural Danish name",
  "net_weight": "Weight with unit e.g. 500 g",
  "flavor_variant": "Flavor or variant",
  "reshoot_verdict": "DEFINITELY_NEEDS_RESHOOT" or "BARCODE_RECOVERED",
  "reshoot_reason_vi": "Clear Vietnamese explanation why customer must take a photo of the back/bottom"
}
"""

results = {}
if os.path.exists(OUT_FILE):
    try:
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)
    except Exception:
        results = {}

for idx, t in enumerate(target_items, start=1):
    batch = t.get("Thư mục nguồn (Batch)")
    photo = t.get("Tên file ảnh gốc")
    
    if photo in results and results[photo].get("status") == "DONE":
        continue
        
    folder = folder_map.get(batch, "")
    img_p = os.path.join(folder, photo)
    if not os.path.exists(img_p):
        alt = [f for f in os.listdir(folder) if f.lower() == photo.lower()] if os.path.exists(folder) else []
        if alt:
            img_p = os.path.join(folder, alt[0])
            
    if not os.path.exists(img_p):
        print(f"[{idx}/33] Not found: {photo}")
        continue
        
    print(f"\n[{idx}/33] Scanning {batch} - {photo}...")
    
    # Load PIL image
    try:
        pil_img = Image.open(img_p)
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception as e:
        # If HEIC fails with PIL, load preprocessed jpeg
        prep_path = os.path.join(BASE_DIR, "output", "shopify_import_final", "product_images", f"{Path(photo).stem}.jpg")
        pil_img = Image.open(prep_path)
        
    # 1. Run OpenCV multi-region detector
    cv_bc, cv_method = extract_regions_and_scan_cv(pil_img)
    if cv_bc:
        print(f"  -> [OpenCV Detected]: {cv_bc} ({cv_method})")
        
    # 2. Run Gemini Vision Zoom Inspector
    gem_res = {}
    if client:
        # Resize to max 2048 for high-res gemini processing
        max_dim = 2048
        w, h = pil_img.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            resized_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        else:
            resized_img = pil_img
            
        buf = io.BytesIO()
        resized_img.convert("RGB").save(buf, format="JPEG", quality=95)
        img_bytes = buf.getvalue()
        
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        PROMPT_ZOOM_INSPECTOR
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                gem_res = json.loads(response.text)
                if isinstance(gem_res, list):
                    gem_res = gem_res[0]
                print(f"  -> [Gemini]: BC={gem_res.get('barcode_digits')} | Verdict={gem_res.get('reshoot_verdict')} | Brand={gem_res.get('brand')}")
                break
            except Exception as e:
                print(f"  -> [Gemini error]: {e}")
                time.sleep(1)
                
    final_bc = cv_bc or gem_res.get("barcode_digits")
    if final_bc:
        final_bc = re.sub(r"[^\d]", "", str(final_bc))
        if len(final_bc) < 8:
            final_bc = None
            
    # Check POS match
    pos_match = None
    if final_bc:
        pos_match = pos_by_bc.get(final_bc) or pos_by_bc.get(final_bc.lstrip("0"))
        if pos_match:
            print(f"  -> [POS MATCH FOUND!]: SKU={pos_match['sku']}, Name={pos_match['product_name']}, Price={pos_match['selling_price']}")
            
    results[photo] = {
        "status": "DONE",
        "batch": batch,
        "photo": photo,
        "cv_barcode": cv_bc,
        "cv_method": cv_method,
        "gemini_data": gem_res,
        "final_barcode": final_bc,
        "pos_match": pos_match,
        "reshoot_verdict": gem_res.get("reshoot_verdict", "DEFINITELY_NEEDS_RESHOOT" if not final_bc else "BARCODE_RECOVERED"),
        "reshoot_reason_vi": gem_res.get("reshoot_reason_vi", "Mã vạch nằm ở mặt sau bao bì, ảnh chỉ chụp mặt trước - Cần chụp bổ sung mặt sau."),
    }
    
    time.sleep(0.5)

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nFinished scanning all 33 images! Results saved to {OUT_FILE}")
