import json, os, sys, io, time, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from dotenv import load_dotenv
load_dotenv()

from PIL import Image, ImageOps
from google import genai
from google.genai import types

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE_FILE = Path("output/g1_delivery/front_layout_boxes.json")
CUSTOMER_SAMPLE_FILE = Path("customer-send-me.xlsx")
G1_DIR = Path("G1_original")

raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
for k, v in os.environ.items():
    if k.startswith("GEMINI_API_KEY_") or k.startswith("GOOGLE_API_KEY_"):
        if v.strip() and v.strip() not in keys:
            keys.append(v.strip())

print(f"Loaded {len(keys)} Gemini API keys.")

clients = {k: genai.Client(api_key=k, http_options={"timeout": 60000}) for k in keys}
lock = threading.Lock()
key_counter = 0

def get_next_client():
    global key_counter
    with lock:
        key = keys[key_counter % len(keys)]
        key_counter += 1
        return clients[key], key

PROMPT_FRONT_ONLY = """
You are an expert computer vision system for retail grocery product packaging.
Analyze this photo showing imported grocery packaging (which usually contains both FRONT and BACK views, or multiple sides).

Task: Locate ONLY the FRONT packaging face (the primary commercial retail display face showing the main BRAND LOGO, PRODUCT NAME, and HERO GRAPHIC/FOOD ILLUSTRATION).

RULES:
1. Do NOT select the BACK side (the back side contains nutrition tables per 100g, barcode stripes, multi-language ingredient text, or white stick-on importer labels).
2. If FRONT and BACK are side-by-side (left vs right, or top vs bottom), return the exact tight bounding box [ymin, xmin, ymax, xmax] (coordinates normalized 0-1000) around ONLY the FRONT view.
3. Determine the clockwise rotation (0, 90, 180, or 270 degrees) needed to make the FRONT view UPRIGHT with text readable horizontally from left to right.

Return strictly JSON:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "front_side_position": "left, right, top, bottom, or center",
  "brand_detected": "string"
}
"""

def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    with lock:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

def detect_single(img_path: Path, existing_cache: dict) -> tuple[str, dict]:
    fname = img_path.name
    if fname in existing_cache and existing_cache[fname].get("front_box_2d"):
        return fname, existing_cache[fname]

    with Image.open(img_path) as im:
        im_t = ImageOps.exif_transpose(im)
        w, h = im_t.size
        buf = io.BytesIO()
        im_t.resize((1200, int(1200 * h / w))).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

    models_to_try = ["gemini-3.8-flash", "gemini-flash-lite-latest"]
    
    for attempt in range(6):
        client, used_key = get_next_client()
        model_name = models_to_try[attempt % len(models_to_try)]
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    PROMPT_FRONT_ONLY,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            raw = resp.text or "{}"
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            
            box = data.get("front_box_2d")
            if box and isinstance(box, list) and len(box) == 4:
                res = {
                    "front_box_2d": [int(round(float(x))) for x in box],
                    "front_rotation": int(data.get("front_rotation_to_upright", 0) or 0),
                    "front_side_position": str(data.get("front_side_position", "")),
                    "brand": str(data.get("brand_detected", "")),
                }
                return fname, res
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                time.sleep(1.5 * (attempt + 1))
            else:
                time.sleep(0.5)

    # Fallback heuristic if API failed: Left half for wide images, Top half for tall
    fallback_box = [0, 0, 1000, 500] if w > h else [0, 0, 500, 1000]
    return fname, {"front_box_2d": fallback_box, "front_rotation": 0, "front_side_position": "fallback"}

def main():
    print("=" * 70)
    print("🔍 RUNNING PRECISE FRONT PACKAGING DETECTOR FOR ALL 467 IMAGES")
    print("=" * 70)

    cache = load_cache()
    all_images = sorted(list(G1_DIR.glob("*.jpeg")) + list(G1_DIR.glob("*.jpg")))
    print(f"Total images to process: {len(all_images)}. Already cached: {len(cache)}")

    to_process = [p for p in all_images if p.name not in cache or not cache[p.name].get("front_box_2d")]
    print(f"Images needing detection: {len(to_process)}")

    if not to_process:
        print("All front boxes are already detected and cached!")
        return

    workers = min(4, len(keys) * 2)
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(detect_single, p, cache): p for p in to_process}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                fname, res = fut.result()
                cache[fname] = res
                completed += 1
                if completed % 10 == 0 or completed == len(to_process):
                    save_cache(cache)
                    print(f"[{completed}/{len(to_process)}] Processed {fname} -> box={res.get('front_box_2d')} rot={res.get('front_rotation')}")
            except Exception as e:
                print(f"Error on {p.name}: {e}")

    save_cache(cache)
    print("=" * 70)
    print(f"✅ COMPLETED! Total cached front layout boxes: {len(cache)}/467")
    print("=" * 70)

if __name__ == "__main__":
    main()
