# -*- coding: utf-8 -*-
"""
Dual-Engine Barcode Deep Scanner for 104 Review Images
Engine 1: OpenCV 5.0 BarcodeDetector with Multi-Scale & Multi-Rotation & CLAHE
Engine 2: Google Gemini Vision High-Resolution Package Inspection
"""

import sys
import os
import re
import json
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
import openpyxl
from google import genai
from google.genai import types

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
CUSTOMER_SRC = os.path.join(SOURCE_DIR, "new_source_from_customer")
OUT_CACHE = os.path.join(BASE_DIR, "output", "shopify_import", "deep_104_scan_cache.json")

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

# 2. Load 104 review items
review_file = os.path.join(BASE_DIR, r"output\shopify_import_final\Customer_Review_Unmatched_Images.xlsx")
wb = openpyxl.load_workbook(review_file, data_only=True)
ws = wb.active
headers = [c.value for c in ws[3]]
review_rows = []
for r in list(ws.iter_rows(min_row=4, values_only=True)):
    review_rows.append(dict(zip(headers, r)))

print(f"Loaded {len(review_rows)} review items.")

# Batch folder map
folder_map = {
    "G1": os.path.join(SOURCE_DIR, "G1_original"),
    "G2": os.path.join(SOURCE_DIR, "G2_original"),
    "G3": os.path.join(SOURCE_DIR, "G3_Original"),
    "G4": os.path.join(SOURCE_DIR, "G4-original"),
    "G5": os.path.join(SOURCE_DIR, "Nyt25.09.26"),
}

# OpenCV Detector
detector = cv2.barcode.BarcodeDetector()

def cv2_detect_barcode(img_path):
    try:
        pil_img = Image.open(img_path)
        pil_img = ImageOps.exif_transpose(pil_img)
        cv_img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
        
        # Test rotations: 0, 90, 180, 270
        for rot in [0, 90, 180, 270]:
            if rot == 90:
                rotated = cv2.rotate(cv_img, cv2.ROTATE_90_CLOCKWISE)
            elif rot == 180:
                rotated = cv2.rotate(cv_img, cv2.ROTATE_180)
            elif rot == 270:
                rotated = cv2.rotate(cv_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            else:
                rotated = cv_img
                
            ok, decoded_info, decoded_type, corners = detector.detectAndDecode(rotated)
            if ok and decoded_info:
                for bc in decoded_info:
                    if bc and len(str(bc).strip()) >= 8:
                        return str(bc).strip(), f"CV2_ROT_{rot}"
                        
            # CLAHE enhanced
            gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
            ok, decoded_info, decoded_type, corners = detector.detectAndDecode(enhanced_bgr)
            if ok and decoded_info:
                for bc in decoded_info:
                    if bc and len(str(bc).strip()) >= 8:
                        return str(bc).strip(), f"CV2_CLAHE_{rot}"
    except Exception as e:
        pass
    return None, None

PROMPT_BARCODE_FOCUS = """You are an expert OCR and retail packaging quality inspector.
Inspect this high-resolution product package photo carefully.
Your mission:
1. Examine every label, sticker, corner, barcode box, side panel, or bottom of the package to find ANY printed barcode digits (EAN-13, EAN-8, UPC-A, UPC-E, ITF-14, Code 128).
2. If you can see the barcode digits clearly or partially legible, extract the exact numeric digits.
3. If there is NO barcode visible in the photo (e.g. only front face was photographed and barcode is on the back/bottom, or obscured), explain clearly why.

Return valid JSON ONLY in this format:
{
  "barcode_found": true/false,
  "barcode_digits": "exact digits or null",
  "barcode_legibility": "clear" / "partially_readable" / "unreadable" / "not_visible",
  "visible_brand": "exact brand name on package",
  "visible_product_title": "exact title on package",
  "net_weight_volume": "exact weight/volume e.g. 500g, 200ml",
  "barcode_location": "front / back / bottom / side / sticker / not_present_in_photo",
  "reshoot_required": true/false,
  "reshoot_reason": "Clear explanation in Vietnamese why customer needs to take another photo if no barcode is visible (e.g. 'Mã vạch nằm ở mặt sau, ảnh chỉ chụp mặt trước - Cần chụp thêm mặt sau', 'Ảnh bị mờ nhãn dinh dưỡng')"
}
"""

scan_results = {}
if os.path.exists(OUT_CACHE):
    try:
        with open(OUT_CACHE, "r", encoding="utf-8") as f:
            scan_results = json.load(f)
    except Exception:
        scan_results = {}

print(f"Already cached: {len(scan_results)} / {len(review_rows)}")

for idx, r_data in enumerate(review_rows, start=1):
    batch = r_data.get("Thư mục nguồn (Batch)")
    photo = r_data.get("Tên file ảnh gốc")
    
    if photo in scan_results and scan_results[photo].get("status") == "COMPLETED":
        continue
        
    folder = folder_map.get(batch, "")
    img_path = os.path.join(folder, photo)
    if not os.path.exists(img_path):
        alt = [f for f in os.listdir(folder) if f.lower() == photo.lower()] if os.path.exists(folder) else []
        if alt:
            img_path = os.path.join(folder, alt[0])
            
    if not os.path.exists(img_path):
        print(f"[{idx}/{len(review_rows)}] File not found: {photo} in {folder}")
        continue
        
    print(f"[{idx}/{len(review_rows)}] Deep scanning {batch} - {photo}...")
    
    # 1. Run CV2 Detector
    cv_bc, cv_method = cv2_detect_barcode(img_path)
    if cv_bc:
        print(f"  -> [OpenCV 5.0] Found barcode: {cv_bc} ({cv_method})")
        
    # 2. Run Gemini Vision Deep Inspector
    gemini_res = {}
    if client:
        try:
            # Load preprocessed high res jpeg or convert
            prep_path = os.path.join(BASE_DIR, "output", "shopify_import_final", "product_images", f"{Path(photo).stem}.jpg")
            if os.path.exists(prep_path):
                with open(prep_path, "rb") as f:
                    img_bytes = f.read()
            else:
                pil_img = Image.open(img_path)
                pil_img = ImageOps.exif_transpose(pil_img)
                import io
                buf = io.BytesIO()
                pil_img.convert("RGB").save(buf, format="JPEG", quality=95)
                img_bytes = buf.getvalue()
                
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    PROMPT_BARCODE_FOCUS
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            gemini_res = json.loads(response.text)
            if isinstance(gemini_res, list):
                gemini_res = gemini_res[0]
            print(f"  -> [Gemini Vision] BC: {gemini_res.get('barcode_digits')} | Reshoot: {gemini_res.get('reshoot_required')} | Reason: {gemini_res.get('reshoot_reason')}")
        except Exception as e:
            print(f"  -> [Gemini Error]: {e}")
            time.sleep(1)
            
    final_bc = cv_bc or gemini_res.get("barcode_digits")
    if final_bc:
        final_bc = re.sub(r"[^\d]", "", str(final_bc))
        
    scan_results[photo] = {
        "status": "COMPLETED",
        "batch": batch,
        "photo": photo,
        "cv2_barcode": cv_bc,
        "cv2_method": cv_method,
        "gemini_data": gemini_res,
        "final_barcode": final_bc if final_bc and len(final_bc) >= 8 else None,
        "reshoot_required": gemini_res.get("reshoot_required", True if not final_bc else False),
        "reshoot_reason": gemini_res.get("reshoot_reason", "Không thấy mã vạch trên ảnh, cần chụp lại mặt sau có mã vạch."),
        "visible_brand": gemini_res.get("visible_brand"),
        "visible_title": gemini_res.get("visible_product_title"),
    }
    
    time.sleep(0.5)

with open(OUT_CACHE, "w", encoding="utf-8") as f:
    json.dump(scan_results, f, ensure_ascii=False, indent=2)

print(f"\nDeep scanning finished! Total records: {len(scan_results)}")
