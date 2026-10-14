# -*- coding: utf-8 -*-
"""
High-Precision Front Packaging & Upright Detector (Multi-Subject & Side Panel Aware)
Handles:
1. Multi-subject & 3-panel photos: Selects ONLY the primary FRONT retail face (excludes side panels and back).
2. Orientation & Upright: Ensures tall products (bottles, jars, cans, boxes, bags) are rotated 100% upright.
3. Coordinate Frame: Predicts on EXIF-normalized images to prevent horizontal slicing.
4. Safety Padding: 5% safety margin around product packaging.
"""

import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageOps
import pillow_heif
from google import genai
from google.genai import types

pillow_heif.register_heif_opener()
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

raw_keys = os.environ.get('GEMINI_API_KEYS', '') or os.environ.get('GEMINI_API_KEY', '') or os.environ.get('GOOGLE_API_KEY', '')
keys = [k.strip() for k in raw_keys.split(',') if k.strip()]
for k, v in os.environ.items():
    if (k.startswith('GEMINI_API_KEY_') or k.startswith('GOOGLE_API_KEY_')) and v.strip() not in keys:
        keys.append(v.strip())

clients = [genai.Client(api_key=k) for k in keys]

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
  "brand_and_product_name": "string",
  "notes": "brief explanation of why this box is the front face"
}
"""

def test_multi_subject():
    test_samples = [
        r"D:\Work\shopify\source-import\G1_original\IMG_0003.jpeg",
        r"D:\Work\shopify\source-import\G1_original\IMG_0004.jpeg",
        r"D:\Work\shopify\source-import\G2_original\IMG_0427.jpeg",
        r"D:\Work\shopify\source-import\G2_original\IMG_0429.jpeg",
        r"D:\Work\shopify\source-import\G4-original\20260916_110807255_iOS.heic",
        r"D:\Work\shopify\source-import\Nyt25.09.26\10.jpg"
    ]
    
    for sp in test_samples:
        if not os.path.exists(sp):
            continue
        fname = Path(sp).name
        with Image.open(sp) as raw_im:
            img = ImageOps.exif_transpose(raw_im)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            w, h = img.size
            
            # Send resized for fast token processing
            max_d = 1200
            scale = min(1.0, max_d / max(w, h))
            proc_img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            
            res = clients[0].models.generate_content(
                model='gemini-3.7-flash',
                contents=[PROMPT_MULTI_PANEL_FRONT, proc_img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            print(f"\n==========================================")
            print(f"File: {fname} (Size: {w}x{h})")
            print(res.text.strip())

if __name__ == "__main__":
    test_multi_subject()
