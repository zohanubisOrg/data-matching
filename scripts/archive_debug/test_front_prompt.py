import json, os, sys, io, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from PIL import Image, ImageOps
from google import genai
from google.genai import types

raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
print(f"Available Gemini keys: {len(keys)}")

PROMPT_FRONT_ONLY = """
You are an expert computer vision system for retail grocery product packaging.
Analyze this photo which shows imported grocery packaging (often showing both FRONT and BACK sides, or a bottle/bag lying down).

Task: Locate ONLY the FRONT packaging face (the primary commercial retail display face showing the main BRAND LOGO, PRODUCT NAME, and HERO GRAPHIC/ILLUSTRATION).

RULES:
1. Do NOT select the BACK side (the back side contains dense text, nutrition facts per 100g, barcode stripes, ingredients, or white stick-on importer labels).
2. If FRONT and BACK are side-by-side (left vs right, or top vs bottom), return the exact bounding box [ymin, xmin, ymax, xmax] (normalized 0-1000) that tightly crops ONLY the FRONT item.
3. Determine the clockwise rotation (0, 90, 180, or 270 degrees) needed to make the FRONT view UPRIGHT with text readable horizontally.

Return strictly JSON:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "front_side_position": "left, right, top, bottom, or center",
  "brand_detected": "string"
}
"""

test_files = ['IMG_0044.jpeg', 'IMG_0324.jpeg', 'IMG_0328.jpeg', 'IMG_0330.jpeg', 'IMG_0335.jpeg', 'IMG_0336.jpeg', 'IMG_0337.jpeg', 'IMG_0344.jpeg', 'IMG_0364.jpeg', 'IMG_0374.jpeg']

for idx, fname in enumerate(test_files):
    fpath = Path("G1_original") / fname
    if not fpath.exists():
        continue
    with Image.open(fpath) as im:
        im_t = ImageOps.exif_transpose(im)
        w, h = im_t.size
        
        buf = io.BytesIO()
        im_t.resize((1200, int(1200 * h / w))).save(buf, format="JPEG", quality=85)
        
        key = keys[idx % len(keys)]
        client = genai.Client(api_key=key, http_options={"timeout": 60000})
        
        try:
            resp = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[
                    types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                    PROMPT_FRONT_ONLY,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            data = json.loads(resp.text)
            print(f"{fname} -> box={data.get('front_box_2d')} | rot={data.get('front_rotation_to_upright')} | pos={data.get('front_side_position')} | brand={data.get('brand_detected')}")
        except Exception as e:
            print(f"Error on {fname}: {e}")
