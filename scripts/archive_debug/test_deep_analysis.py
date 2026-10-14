import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageOps
import pandas as pd
from google import genai
from google.genai import types

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely

# Setup Gemini API clients
raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
for k, v in os.environ.items():
    if (k.startswith("GEMINI_API_KEY_") or k.startswith("GOOGLE_API_KEY_")) and v.strip() not in keys:
        keys.append(v.strip())

print(f"Loaded {len(keys)} API keys.")
clients = [genai.Client(api_key=k, http_options={"timeout": 60000}) for k in keys]
key_idx = 0

def get_client():
    global key_idx
    c = clients[key_idx % len(clients)]
    key_idx += 1
    return c

PROMPT_ANALYSIS = """
You are an expert AI for retail grocery product cataloging and computer vision.
Analyze this photo of imported supermarket products (which may show dual-sided packaging, front/back, multiple packages, or single products).

Your tasks:
1. **FULL PRODUCT FRONT DETECTION**:
   - Locate the **FRONT retail display face** of the product (the side with the main brand logo, product title, and food/hero graphics).
   - Return the tight bounding box `front_box_2d: [ymin, xmin, ymax, xmax]` (coordinates normalized 0-1000) that encloses the **ENTIRE PHYSICAL PRODUCT PACKAGE** of that front face (from top rim/seal/cap down to the very bottom base, and full width).
   - CRITICAL REQUIREMENT: NEVER crop only a label, tag, or small rectangle! The bounding box must contain the ENTIRE retail package container (bottle, can, box, bag).
   - If front and back are side-by-side (left vs right, or top vs bottom), enclose the ENTIRE FRONT product.
   - If only one product package is present, enclose the ENTIRE product package.
   - Determine `front_rotation_to_upright`: degrees clockwise (0, 90, 180, 270) to orient the front packaging upright so text is read normally.

2. **BARCODE & PRODUCT DATA EXTRACTION**:
   - Read the exact barcode digits (EAN-13, EAN-8, UPC-A, etc.) visible anywhere in this photo (under barcode stripes or stickers).
   - If clearly visible, extract digits only. If no barcode is visible at all, return null.
   - Extract the full commercial product name in English/Danish (e.g. "Royal Thai Glutinous Rice 1kg").
   - Extract brand, net quantity, unit, variant, and country of origin if visible.

Return strictly valid JSON:
{
  "barcode": "string digits only or null",
  "product_name": "Full descriptive commercial name",
  "brand": "Brand name",
  "net_weight": "e.g. 500g, 1kg, 250ml",
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "front_description": "short note explaining what is in front_box_2d"
}
"""

def analyze_photo(img_path: Path):
    pil_im = open_image_safely(img_path)
    # Convert to RGB and resize for API
    max_dim = 1600
    w, h = pil_im.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        pil_im = pil_im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    
    import io
    buf = io.BytesIO()
    pil_im.convert("RGB").save(buf, format="JPEG", quality=90)
    img_bytes = buf.getvalue()

    client = get_client()
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            PROMPT_ANALYSIS
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    return json.loads(response.text)

if __name__ == "__main__":
    # Test on the specific samples mentioned by user
    sample_photos = [
        # User samples
        PROJECT_ROOT / "source-import/G3_Original/IMG_5080.HEIC",  # 8716789006523
        PROJECT_ROOT / "source-import/G3_Original/IMG_1339.jpeg",  # 12415762
        PROJECT_ROOT / "source-import/G3_Original/IMG_1447.jpeg",  # 4016337900254
        PROJECT_ROOT / "source-import/G3_Original/IMG_1312.jpeg",  # 8858306001489
        PROJECT_ROOT / "source-import/G5_Nyt" if (PROJECT_ROOT / "source-import/G5_Nyt").exists() else PROJECT_ROOT / "source-import/Nyt25.09.26/IMG_5452.HEIC",
        PROJECT_ROOT / "source-import/Nyt25.09.26/IMG_5454.HEIC",  # 8888296019010
        PROJECT_ROOT / "source-import/G3_Original/IMG_1283.jpeg",  # 8901161105066
        PROJECT_ROOT / "source-import/Nyt25.09.26/IMG_5482.HEIC",  # 8934563138165
        PROJECT_ROOT / "source-import/G3_Original/IMG_1474.jpeg",  # 8936116500610
        # NO_BARCODE samples
        PROJECT_ROOT / "source-import/G2_original/IMG_0427.jpeg",
        PROJECT_ROOT / "source-import/G2_original/IMG_0809.jpeg",
        PROJECT_ROOT / "source-import/G3_Original/IMG_1185.jpeg",
        PROJECT_ROOT / "source-import/G3_Original/IMG_5086.HEIC",
        PROJECT_ROOT / "source-import/G3_Original/IMG_5156.HEIC",
    ]

    for p in sample_photos:
        if not p.exists():
            print(f"File not found: {p}")
            continue
        print(f"\n==================== {p.name} ====================")
        try:
            res = analyze_photo(p)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error analyzing {p.name}: {e}")
