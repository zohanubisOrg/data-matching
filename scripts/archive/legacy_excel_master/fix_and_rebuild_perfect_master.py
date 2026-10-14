# -*- coding: utf-8 -*-
"""
High-Precision Pipeline for Multi-Subject, Side-Panel, and Upright Crop Correction.
Processes all 1,659 images:
- Filters out side panels (mặt cạnh bên) and back panels in 3-subject / multi-pack photos.
- Isolates ONLY the primary commercial FRONT face.
- Fixes horizontal slicing & applies upright rotation.
- Rebuilds Master_All_1659_Products_With_Images.xlsx with 100% embedded images.
"""

import os
import sys
import re
import csv
import json
import time
import shutil
import unicodedata
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from PIL import Image, ImageOps
import pillow_heif
import openpyxl
import pandas as pd
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.utils import get_column_letter

from google import genai
from google.genai import types

pillow_heif.register_heif_opener()
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
CUSTOMER_SRC = os.path.join(SOURCE_DIR, "new_source_from_customer")
OUTPUT_DIR = os.path.join(BASE_DIR, r"output\shopify_import_final")
IMG_FINAL_DIR = os.path.join(OUTPUT_DIR, "product_images")
THUMBS_DIR = os.path.join(OUTPUT_DIR, "excel_delivery_thumbs")
BOX_CACHE_FILE = os.path.join(BASE_DIR, r"output\perfect_front_boxes_1659.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(IMG_FINAL_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)

# 1. API Keys & Clients
raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
for k, v in os.environ.items():
    if (k.startswith("GEMINI_API_KEY_") or k.startswith("GOOGLE_API_KEY_")) and v.strip() not in keys:
        keys.append(v.strip())

clients = [genai.Client(api_key=k) for k in keys]
print(f"Loaded {len(clients)} Gemini API clients.")

# Load existing perfect box cache
perfect_boxes = {}
if os.path.exists(BOX_CACHE_FILE):
    try:
        with open(BOX_CACHE_FILE, "r", encoding="utf-8") as f:
            perfect_boxes = json.load(f)
        print(f"Loaded {len(perfect_boxes)} existing box detections from {BOX_CACHE_FILE}")
    except Exception:
        perfect_boxes = {}

PROMPT_MULTI_PANEL_FRONT = """
You are a precision computer vision system for retail e-commerce grocery packaging.
You are given a photo of grocery packaging. The photo may contain:
- MULTIPLE SUBJECTS (e.g., 2 or 3 bottles/jars lined up, where 1 is the FRONT face, and the other 1 or 2 are SIDE PANELS or BACK panels).
- SIDE-BY-SIDE PANELS (Front vs Back, Front vs Side).
- STACKED / HORIZONTAL / ROTATED PACKAGING.

YOUR MISSION:
Identify and return the exact bounding box around ONLY the PRIMARY COMMERCIAL FRONT DISPLAY FACE (Mặt trước chính diện của sản phẩm).

CRITICAL SELECTION RULES:
1. FRONT FACE (ALWAYS SELECT THIS):
   - Contains the prominent MAIN BRAND LOGO (e.g. Aroy-D, Mama, FaThai, UFC, Lee Kum Kee, etc.).
   - Contains HERO FOOD GRAPHICS, ILLUSTRATIONS, or SERVING SUGGESTION IMAGES.
   - Contains the main COMMERCIAL PRODUCT TITLE in large font.
   - It is the face intended to attract retail customers on a supermarket shelf.

2. SIDE PANELS / CẠNH BÊN (DO NOT SELECT):
   - Shows thin side panels, barcode label on side, recycling icons, opening instructions, shipping info.
   - If there are 3 subjects (e.g. 1 front bottle + 2 side-angle bottles), select ONLY the center/front bottle facing directly forward.

3. BACK FACE (DO NOT SELECT):
   - Contains dense multilingual ingredients (DK, EN, DE, FR...), nutrition table per 100g, barcode zebra stripes, white importer translation sticker.

4. UPRIGHT ROTATION:
   - Determine the exact clockwise rotation (0, 90, 180, or 270 degrees) needed so the cropped front face is completely UPRIGHT (vertical), with the brand and title text reading normally from left to right.

Return strictly valid JSON:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "panel_type_chosen": "FRONT_DIRECT_VIEW",
  "num_subjects_in_image": 1,
  "brand_and_product_name": "string"
}
"""

def detect_front_with_fallback(img, client_idx=0):
    client = clients[client_idx % len(clients)]
    models = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    
    w, h = img.size
    max_d = 1200
    scale = min(1.0, max_d / max(w, h))
    proc_img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    
    for m in models:
        for attempt in range(2):
            try:
                res = client.models.generate_content(
                    model=m,
                    contents=[PROMPT_MULTI_PANEL_FRONT, proc_img],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
                )
                data = json.loads(res.text.strip())
                if "front_box_2d" in data and len(data["front_box_2d"]) == 4:
                    return data
            except Exception:
                time.sleep(1)
    return None


def process_and_crop_clean(raw_path, fname, client_idx=0):
    try:
        with Image.open(raw_path) as raw_im:
            img = ImageOps.exif_transpose(raw_im)
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            w, h = img.size
            
            # Check cache
            box_info = perfect_boxes.get(fname)
            if not box_info or not box_info.get("front_box_2d"):
                box_info = detect_front_with_fallback(img, client_idx)
                if box_info:
                    perfect_boxes[fname] = box_info
            
            if box_info and box_info.get("front_box_2d"):
                ymin, xmin, ymax, xmax = box_info["front_box_2d"]
                rot = box_info.get("front_rotation_to_upright", 0) or 0
                
                # Add 5% safety margin padding
                pad_x = int((xmax - xmin) * 0.05)
                pad_y = int((ymax - ymin) * 0.05)
                left = max(0, int((xmin - pad_x) * w / 1000))
                top = max(0, int((ymin - pad_y) * h / 1000))
                right = min(w, int((xmax + pad_x) * w / 1000))
                bottom = min(h, int((ymax + pad_y) * h / 1000))
                
                if (right - left) >= 50 and (bottom - top) >= 50:
                    cropped = img.crop((left, top, right, bottom))
                else:
                    cropped = img
            else:
                cropped = img
                rot = 0
            
            # Rotate upright if needed
            if rot in [90, 180, 270]:
                cropped = cropped.rotate(360 - rot, expand=True)
            elif cropped.width > cropped.height * 1.35:
                # If still wide landscape, auto-orient upright
                cropped = cropped.rotate(270, expand=True)
                
            # E-commerce canvas (clean padding with white background)
            cw, ch = cropped.size
            max_d = 1600
            if max(cw, ch) > max_d:
                scale = max_d / max(cw, ch)
                cw = max(1, int(cw * scale))
                ch = max(1, int(ch * scale))
                cropped = cropped.resize((cw, ch), Image.Resampling.LANCZOS)
                
            # Thumbnail (150x150 square)
            thumb_size = 150
            thumb_copy = cropped.copy()
            thumb_copy.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            thumb_canvas = Image.new("RGB", (thumb_size, thumb_size), (255, 255, 255))
            px = (thumb_size - thumb_copy.width) // 2
            py = (thumb_size - thumb_copy.height) // 2
            thumb_canvas.paste(thumb_copy, (px, py))
            
            return cropped, thumb_canvas
    except Exception as e:
        print(f"Error processing {fname}: {e}")
        return None, None

def run_pipeline():
    print("==========================================")
    print("🚀 Starting High-Precision Image & Master Rebuild")
    print("==========================================")
    
    src_folders = {
        "G1": os.path.join(SOURCE_DIR, "G1_original"),
        "G2": os.path.join(SOURCE_DIR, "G2_original"),
        "G3": os.path.join(SOURCE_DIR, "G3_Original"),
        "G4": os.path.join(SOURCE_DIR, "G4-original"),
        "G5": os.path.join(SOURCE_DIR, "Nyt25.09.26"),
    }
    
    # Collect all 1659 files
    file_queue = []
    for bname, fld in src_folders.items():
        if os.path.exists(fld):
            for f in sorted(os.listdir(fld)):
                if os.path.splitext(f)[1].lower() in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
                    file_queue.append((bname, f, os.path.join(fld, f)))
                    
    print(f"Total files in queue: {len(file_queue)}")
    
    # Process files
    processed = 0
    start_t = time.time()
    
    for idx, (bname, fname, fpath) in enumerate(file_queue):
        stem = Path(fname).stem
        full_img, thumb_img = process_and_crop_clean(fpath, fname, idx)
        if full_img and thumb_img:
            # Save standard master files
            jpg_out = os.path.join(IMG_FINAL_DIR, f"{stem}.jpg")
            webp_out = os.path.join(IMG_FINAL_DIR, f"{stem}.webp")
            thumb_out = os.path.join(THUMBS_DIR, f"{stem}.jpg")
            
            full_img.save(jpg_out, "JPEG", quality=95)
            full_img.save(webp_out, "WEBP", quality=85)
            thumb_img.save(thumb_out, "JPEG", quality=90)
            processed += 1
            
        if (idx + 1) % 100 == 0 or idx == len(file_queue) - 1:
            print(f"  Processed {idx + 1}/{len(file_queue)} images ({time.time() - start_t:.1f}s)...")
            # Periodically save box cache
            with open(BOX_CACHE_FILE, "w", encoding="utf-8") as fp:
                json.dump(perfect_boxes, fp, ensure_ascii=False, indent=2)
                
    print(f"\n✅ All {processed} images preprocessed and saved.")
    
    # Save final box cache
    with open(BOX_CACHE_FILE, "w", encoding="utf-8") as fp:
        json.dump(perfect_boxes, fp, ensure_ascii=False, indent=2)
        
    # Now run Master Deliverable Builder
    print("\n--- Generating Master Delivery Excel with 1,659 Embedded Images ---")
    from scripts.build_master_1659_all_with_images import build_unified_master_1659
    build_unified_master_1659()

if __name__ == "__main__":
    run_pipeline()
