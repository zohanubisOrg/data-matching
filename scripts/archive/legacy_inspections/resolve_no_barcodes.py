import os
import sys
import json
import time
import re
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageOps
import pandas as pd
from google import genai
from google.genai import types
from google.genai.errors import APIError

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely

# Setup API keys
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

PROMPT_ANALYSIS = """
You are an expert AI for retail grocery product cataloging and computer vision.
Analyze this photo of imported grocery products (which may show dual-sided packaging, front/back, multiple angles, or single products).

Your tasks:
1. **BARCODE & PRODUCT IDENTIFICATION**:
   - Read any visible barcode numbers (EAN-13, EAN-8, UPC-A, 8-14 digits) anywhere in this photo (on packaging, stickers, or barcodes).
   - If multiple barcodes, extract the primary retail product barcode. If none visible, return null.
   - Extract the full official product title/name in English/Danish (e.g. "Royal Thai Glutinous Rice 1kg", "East Asian Food IT Cake With Coconut Filling 500g").
   - Extract brand, variant, net quantity/weight (e.g. "500g", "1kg", "250ml", "100g x 5").

2. **FULL PRODUCT FRONT DETECTION & ORIENTATION**:
   - Locate the **FRONT retail display face** of the product (the side with the main brand logo, hero artwork, and product title).
   - Return the tight bounding box `front_box_2d: [ymin, xmin, ymax, xmax]` (coordinates normalized 0-1000) that encloses the **ENTIRE PHYSICAL PRODUCT PACKAGE** of that front face (from top rim/seal/cap down to the very bottom base, and full width).
   - CRITICAL REQUIREMENT: NEVER crop only a label, tag, barcode, or small rectangle! The bounding box must contain the ENTIRE retail package container (bottle, can, box, bag, pouch).
   - If front and back are side-by-side (left vs right, or top vs bottom), enclose the ENTIRE FRONT product.
   - If only one product package is present, enclose the ENTIRE product package.
   - Determine `front_rotation_to_upright`: degrees clockwise (0, 90, 180, 270) to orient the front packaging upright so brand and title are read horizontally from left to right.

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

CANDIDATE_MODELS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.5-pro"]

def analyze_photo_with_retry(img_path: Path, max_retries=5):
    pil_im = open_image_safely(img_path)
    max_dim = 1600
    w, h = pil_im.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        pil_im = pil_im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    
    import io
    buf = io.BytesIO()
    pil_im.convert("RGB").save(buf, format="JPEG", quality=90)
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
            # Clean markdown code blocks if present
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            data = json.loads(text.strip())
            return data
        except Exception as e:
            print(f"[{img_path.name}] Attempt {attempt+1} failed with {model_name}: {e}")
            time.sleep(2 * (attempt + 1))
            
    return None

if __name__ == "__main__":
    from deep_inspect_no_barcode import records
    results_file = PROJECT_ROOT / "output/shopify_import/no_barcode_resolved.json"
    
    resolved = {}
    if results_file.exists():
        try:
            with open(results_file, "r", encoding="utf-8") as f:
                resolved = json.load(f)
        except Exception:
            resolved = {}

    print(f"Starting processing of {len(records)} NO_BARCODE items...")
    
    for r in records:
        photo = r["source_photo"]
        path_str = r.get("found_path")
        if not path_str:
            # Check in output images
            alt_p = PROJECT_ROOT / "output/shopify_import/images" / (Path(photo).stem + ".jpg")
            if alt_p.exists():
                path_str = str(alt_p)
            else:
                alt_p2 = PROJECT_ROOT / "output/shopify_import/images" / (Path(photo).stem + ".webp")
                if alt_p2.exists():
                    path_str = str(alt_p2)

        if not path_str or not Path(path_str).exists():
            print(f"Skip {photo}: File not found anywhere.")
            continue
            
        print(f"\nProcessing {photo} ({r['batch']})...")
        p = Path(path_str)
        res = analyze_photo_with_retry(p)
        if res:
            res["source_photo"] = photo
            res["batch"] = r["batch"]
            resolved[photo] = res
            print(f"-> SUCCESS: Barcode={res.get('barcode')}, Name={res.get('product_name')}, Box={res.get('front_box_2d')}, Rot={res.get('front_rotation_to_upright')}")
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(resolved, f, indent=2, ensure_ascii=False)
        else:
            print(f"-> FAILED for {photo}")
        time.sleep(1)

    print("\nProcessing completed! Total resolved:", len(resolved))
