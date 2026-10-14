import json, os, sys, io
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from PIL import Image, ImageOps
from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from product_mapper.ingestion.image_loader import open_image_safely

raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
client = genai.Client(api_key=keys[0])

PROMPT_FRONT = """
You are an expert computer vision system for retail grocery packaging.
Analyze this photo which shows imported grocery packaging (which may show FRONT and BACK sides, top/bottom stacks, multiple angles, or a product lying on a surface).

Task: Locate ONLY the FRONT packaging face (the primary commercial retail display face with BRAND LOGO, PRODUCT NAME, and HERO FOOD GRAPHIC / ILLUSTRATION).

RULES:
1. Do NOT select the BACK side (the back side contains dense multi-language ingredients, nutrition table per 100g, barcode stripes, or white importer stickers).
2. Do NOT select shipping/box sides (e.g. umbrella/fragile icons, warehouse barcodes, cardboard flaps).
3. If FRONT and BACK are side-by-side (left vs right, or top vs bottom), return the exact tight bounding box [ymin, xmin, ymax, xmax] (coordinates normalized 0-1000) around ONLY the FRONT face.
4. Determine the exact clockwise rotation (0, 90, 180, or 270 degrees) needed to make the FRONT packaging face completely UPRIGHT with its text readable normally from left to right.

Return JSON:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "front_position": "left, right, top, bottom, center, or full",
  "brand_and_name": "string"
}
"""

test_files = [
    Path("source-import/Nyt25.09.26/Tofu.jpg"),
    Path("source-import/Nyt25.09.26/tofu2.jpg"),
    Path("source-import/G2_original/IMG_0863.jpeg"),
    Path("source-import/G3_Original/IMG_5053.HEIC"),
    Path("source-import/G4-original/20260916_112916662_iOS.heic")
]

for p in test_files:
    if not p.exists():
        print(f"Missing {p}")
        continue
    im = open_image_safely(p)
    w, h = im.size
    buf = io.BytesIO()
    im.resize((1200, int(1200 * h / w))).save(buf, format="JPEG", quality=85)
    
    models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview", "gemini-3.8-flash"]
    res_text = ""
    for m in models_to_try:
        try:
            resp = client.models.generate_content(
                model=m,
                contents=[
                    types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                    PROMPT_FRONT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            res_text = resp.text.strip()
            if res_text:
                break
        except Exception as e:
            time.sleep(1)
            continue
    print(f"{p.name} -> {res_text}")
