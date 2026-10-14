# -*- coding: utf-8 -*-
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

client = genai.Client(api_key=keys[0])

PROMPT_FRONT_PERFECT = """
You are a precision computer vision system for e-commerce packaging.
You are given a photo of imported retail grocery packaging.

CRITICAL TASK:
Detect the commercial FRONT face of the primary product packaging (the retail display face shown on store shelves).

STRICT RULES TO DISTINGUISH FRONT VS BACK:
1. FRONT FACE (SELECT THIS):
   - Features the main prominent BRAND LOGO (e.g. Aroy-D, Mama, Lee Kum Kee, FaThai, UFC, etc.)
   - Features high-contrast FOOD ILLUSTRATIONS / HERO GRAPHICS / COOKED DISH IMAGERY
   - Features the main commercial PRODUCT TITLE in large font.
2. BACK FACE (DO NOT SELECT):
   - Contains dense multilingual ingredient text (e.g. Ingredients: ..., Zutaten: ..., Ingredienser: ...)
   - Contains the structured NUTRITION TABLE (Energy kJ/kcal, Fat, Salt per 100g)
   - Contains BARCODE STRIPES (black and white vertical bars)
   - Contains white stick-on importer translation labels.
3. If Front and Back are side-by-side (left vs right, or top vs bottom), return the exact bounding box [ymin, xmin, ymax, xmax] (normalized 0-1000) around ONLY the FRONT face.
4. ROTATION: Determine the clockwise rotation (0, 90, 180, or 270 degrees) required to make the front face completely upright and readable from left to right.

Return strictly valid JSON:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "face_detected": "FRONT" or "BACK_ONLY" or "BOTH_PRESENT",
  "brand": "string",
  "product_title": "string"
}
"""

def test_samples():
    sample_files = [
        r"D:\Work\shopify\source-import\G1_original\IMG_0002.jpeg",
        r"D:\Work\shopify\source-import\G1_original\IMG_0003.jpeg",
        r"D:\Work\shopify\source-import\G2_original\IMG_0427.jpeg",
        r"D:\Work\shopify\source-import\G2_original\IMG_0429.jpeg",
        r"D:\Work\shopify\source-import\G4-original\20260916_110807255_iOS.heic",
        r"D:\Work\shopify\source-import\Nyt25.09.26\10.jpg"
    ]
    
    for sp in sample_files:
        if not os.path.exists(sp):
            continue
        fname = Path(sp).name
        with Image.open(sp) as raw_im:
            img = ImageOps.exif_transpose(raw_im)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            w, h = img.size
            
            # Send resized image to Gemini
            max_d = 1200
            scale = min(1.0, max_d / max(w, h))
            proc_img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            
            res = client.models.generate_content(
                model='gemini-3.7-flash',
                contents=[PROMPT_FRONT_PERFECT, proc_img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            print(f"\n--- Result for {fname} ({w}x{h}) ---")
            print(res.text.strip())

if __name__ == "__main__":
    test_samples()
