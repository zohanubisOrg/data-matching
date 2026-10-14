# -*- coding: utf-8 -*-
"""
Targeted Micro-Inspection for remaining items 24 to 49
"""

import sys
import os
import re
import json
import time
import io
from pathlib import Path
from PIL import Image, ImageOps
import openpyxl
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
CUSTOMER_SRC = os.path.join(SOURCE_DIR, "new_source_from_customer")
OUT_JSON = os.path.join(BASE_DIR, "output", "shopify_import", "resolved_1_to_23.json") # We will update this json to hold all 1 to 49

api_key = None
env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY") and "AIza" in line:
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

client = genai.Client(api_key=api_key)

f_pos_full = os.path.join(SOURCE_DIR, "Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
wb_full = openpyxl.load_workbook(f_pos_full, data_only=True)
pos_by_bc = {}
for r in list(wb_full["Ten_ban"].iter_rows(values_only=True))[1:]:
    raw_bc = str(r[7] or "").strip()
    c_bc = re.sub(r"[^\w]", "", raw_bc.replace(".0", ""))
    sku = str(r[8] or "").strip()
    item = {
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
    if c_bc:
        pos_by_bc[c_bc] = item
        pos_by_bc[c_bc.lstrip("0")] = item

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
target_all = list(ws_r.iter_rows(min_row=4, values_only=True))

PROMPT_MICRO_INSPECTION = """You are an ultra-high precision OCR and barcode reading system.
Look at this retail product package photo with extreme magnification:
1. Examine every corner, bottom edge, vertical edge, label margin, price sticker, or shelf tag.
2. Read the exact printed barcode number (EAN-13, EAN-8, UPC-A, Code 128) if any digits are visible anywhere in the photo.
3. Read the exact Brand name, Product title, net weight / volume, and flavor.
4. If you see ANY 8-14 digit sequence printed on the label, sticker, or barcode box, extract the exact digits.

Return JSON only:
{
  "barcode_found": true/false,
  "barcode_digits": "exact digits (8 to 14 digits) or null",
  "barcode_source_location": "bottom / back_edge / side / shelf_tag / front_label",
  "brand": "Exact Brand Name",
  "product_title_en": "Natural English Product Title",
  "product_title_da": "Natural Danish Product Title",
  "net_weight": "e.g. 500g, 227g, 700ml",
  "flavor": "Flavor or variant"
}
"""

resolved_dict = {}
if os.path.exists(OUT_JSON):
    try:
        with open(OUT_JSON, "r", encoding="utf-8") as f:
            resolved_dict = json.load(f)
    except Exception:
        resolved_dict = {}

for idx, r_row in enumerate(target_all[23:], start=24):
    d = dict(zip(r_headers, r_row))
    batch = d.get("Thư mục nguồn (Batch)")
    photo = d.get("Tên file ảnh gốc")
    
    if photo in resolved_dict and resolved_dict[photo].get("barcode_digits"):
        continue
        
    folder = folder_map.get(batch, "")
    img_p = os.path.join(folder, photo) if folder and photo else ""
    if not os.path.exists(img_p):
        alt = [f for f in os.listdir(folder) if f.lower() == photo.lower()] if os.path.exists(folder) else []
        if alt:
            img_p = os.path.join(folder, alt[0])
            
    if not os.path.exists(img_p):
        print(f"[{idx}/{len(target_all)}] File not found: {photo}")
        continue
        
    print(f"\n[{idx}/{len(target_all)}] Targeted Micro-Inspection: {batch} - {photo}...")
    
    try:
        pil_img = Image.open(img_p)
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        prep_path = os.path.join(BASE_DIR, "output", "shopify_import_final", "product_images", f"{Path(photo).stem}.jpg")
        pil_img = Image.open(prep_path)
        
    max_dim = 2560
    w, h = pil_img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        res_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    else:
        res_img = pil_img
        
    buf = io.BytesIO()
    res_img.convert("RGB").save(buf, format="JPEG", quality=98)
    img_bytes = buf.getvalue()
    
    gem_res = {}
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    PROMPT_MICRO_INSPECTION
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            gem_res = json.loads(response.text)
            if isinstance(gem_res, list):
                gem_res = gem_res[0]
            break
        except Exception as e:
            print(f"  Attempt {attempt+1} error: {e}")
            time.sleep(1)
            
    bc_extracted = gem_res.get("barcode_digits")
    if bc_extracted:
        bc_extracted = re.sub(r"[^\d]", "", str(bc_extracted))
        if len(bc_extracted) < 8:
            bc_extracted = None
            
    pos_match = None
    if bc_extracted:
        pos_match = pos_by_bc.get(bc_extracted) or pos_by_bc.get(bc_extracted.lstrip("0"))
        
    brand = gem_res.get("brand") or d.get("Thương hiệu (Brand)") or ""
    pname = gem_res.get("product_title_en") or d.get("Tên sản phẩm tiếng Anh (Full name EN)") or ""
    
    print(f"  Result: BC={bc_extracted} | Loc={gem_res.get('barcode_source_location')} | Brand={brand} | Name={pname[:35]}")
    if pos_match:
        print(f"  -> POS Match: SKU={pos_match['sku']}, POS Name={pos_match['product_name']}, Price={pos_match['selling_price']}")
        
    resolved_dict[photo] = {
        "batch": batch,
        "photo": photo,
        "barcode_digits": bc_extracted,
        "gemini_data": gem_res,
        "pos_match": pos_match,
    }
    
    time.sleep(0.5)

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(resolved_dict, f, ensure_ascii=False, indent=2)

print(f"\nSaved all 49 results to {OUT_JSON}")
