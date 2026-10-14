import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image, ImageOps
import pandas as pd
from google import genai
from google.genai import types

load_dotenv()

# Add project root and src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely, SUPPORTED_EXTENSIONS
from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_DIR = Path("output/shopify_import")
WEB_FRONT_DIR = OUTPUT_DIR / "web_front_images"
IMAGES_DIR = OUTPUT_DIR / "images"
FRONT_BOX_CACHE = OUTPUT_DIR / "g2_g5_front_boxes.json"

WEB_FRONT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# API Keys setup
raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
for k, v in os.environ.items():
    if (k.startswith("GEMINI_API_KEY_") or k.startswith("GOOGLE_API_KEY_")) and v.strip() not in keys:
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
Analyze this photo which shows imported grocery packaging (which often shows FRONT and BACK sides, top/bottom stacked packages, side panels with shipping symbols, or multiple angles).

Task: Locate ONLY the FRONT packaging face (the primary commercial retail display face showing the main BRAND LOGO, PRODUCT NAME, and HERO GRAPHIC / FOOD ILLUSTRATION).

RULES:
1. Do NOT select the BACK side (the back side contains dense text, nutrition tables per 100g, barcode stripes, multi-language ingredients, or white stick-on importer stickers).
2. Do NOT select shipping/box sides (e.g. umbrella/fragile icons, warehouse barcodes, carton flaps).
3. If FRONT and BACK are side-by-side (left vs right, or top vs bottom), return the exact tight bounding box [ymin, xmin, ymax, xmax] (coordinates normalized 0-1000) around ONLY the FRONT retail display face.
4. Determine the exact clockwise rotation (0, 90, 180, or 270 degrees) needed to make the FRONT packaging face completely UPRIGHT with its brand and title text readable normally from left to right.

Return strictly JSON:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "front_position": "left, right, top, bottom, center, or full",
  "brand_and_name": "string"
}
"""

def load_box_cache() -> dict[str, Any]:
    if FRONT_BOX_CACHE.exists():
        try:
            with open(FRONT_BOX_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_box_cache(cache: dict[str, Any]):
    with lock:
        FRONT_BOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(FRONT_BOX_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

def detect_front_box_single(img_path: Path, cache: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fname = img_path.name
    if fname in cache and cache[fname].get("front_box_2d"):
        return fname, cache[fname]

    try:
        orig_im = open_image_safely(img_path)
        w, h = orig_im.size
        buf = io.BytesIO()
        orig_im.resize((1200, int(1200 * h / w))).save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()
    except Exception as e:
        print(f"Error opening image {img_path}: {e}")
        fallback = [0, 0, 1000, 500]
        return fname, {"front_box_2d": fallback, "front_rotation": 0, "front_position": "fallback_error"}

    candidate_models = ["gemini-3-flash-preview", "gemini-3.6-flash", "gemini-3.1-flash-lite-preview", "gemini-flash-lite-latest"]
    
    for attempt in range(8):
        client, used_key = get_next_client()
        model_name = candidate_models[attempt % len(candidate_models)]
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
                    "front_position": str(data.get("front_position", "")),
                    "brand_and_name": str(data.get("brand_and_name", "")),
                }
                return fname, res
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                time.sleep(1.5 * (attempt + 1))
            else:
                time.sleep(0.5)

    # Smart fallback based on aspect ratio
    fallback = [0, 0, 1000, 500] if w > h else [0, 0, 500, 1000]
    return fname, {"front_box_2d": fallback, "front_rotation": 0, "front_position": "fallback"}

def crop_and_save_front_images(
    orig_im: Image.Image,
    front_box_2d: list[int] | None,
    front_rotation: int,
    barcode: str,
    record_id: str,
    batch_name: str
) -> tuple[str, int, int]:
    """Crops the front packaging at original native resolution with 4.5% adaptive margin and saves to web and images folders."""
    w, h = orig_im.size

    if front_box_2d and len(front_box_2d) == 4:
        ymin, xmin, ymax, xmax = front_box_2d
        pad_w = int((xmax - xmin) * 0.045)
        pad_h = int((ymax - ymin) * 0.045)
        left = max(0, int((xmin - pad_w) * w / 1000))
        top = max(0, int((ymin - pad_h) * h / 1000))
        right = min(w, int((xmax + pad_w) * w / 1000))
        bottom = min(h, int((ymax + pad_h) * h / 1000))
    else:
        left, top, right, bottom = 0, 0, w, h

    if right <= left or bottom <= top:
        crop_im = orig_im.copy()
    else:
        crop_im = orig_im.crop((left, top, right, bottom))

    # Apply detected text rotation to make packaging upright
    if front_rotation != 0:
        crop_im = crop_im.rotate(-front_rotation, expand=True)

    # Use clean barcode filename or slug fallback
    clean_bc = str(barcode).strip() if barcode and str(barcode).strip().lower() not in {"none", "nan", ""} else ""
    if clean_bc.endswith(".0"):
        clean_bc = clean_bc[:-2]

    if clean_bc:
        base_name = f"{clean_bc}"
    else:
        base_name = f"NO_BARCODE_{batch_name}_{record_id or int(time.time()*1000)}"

    jpg_name = f"{base_name}.jpg"
    webp_name = f"{base_name}.webp"

    # Save to dedicated web_front_images directory
    web_jpg_path = WEB_FRONT_DIR / jpg_name
    web_webp_path = WEB_FRONT_DIR / webp_name
    crop_im.save(web_jpg_path, format="JPEG", quality=95, optimize=True)
    crop_im.save(web_webp_path, format="WEBP", quality=88, method=4)

    # Also sync to images directory
    img_jpg_path = IMAGES_DIR / jpg_name
    img_webp_path = IMAGES_DIR / webp_name
    crop_im.save(img_jpg_path, format="JPEG", quality=95, optimize=True)
    crop_im.save(img_webp_path, format="WEBP", quality=88, method=4)

    return jpg_name, crop_im.width, crop_im.height

def main():
    print("=" * 80)
    print("🚀 G2-G5 HIGH-PRECISION FRONT PACKAGING DETECTOR & WEB IMAGE CROPPER")
    print("=" * 80)

    # 1. Load Manifest
    manifest_path = Path("output/g2_g5_manifest.json")
    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found!")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 2. Map all files by filename
    all_files_map: dict[str, Path] = {}
    for batch_name, bdata in manifest["batches"].items():
        folder = Path(bdata["folder"])
        for fentry in bdata["files"]:
            fname = fentry["filename"]
            all_files_map[fname] = folder / fname

    print(f"Total images found in manifest: {len(all_files_map)}")

    # 3. Load Master Consolidated Records
    master_xlsx = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    if master_xlsx.exists():
        master_df = pd.read_excel(master_xlsx)
        records = master_df.to_dict(orient="records")
        print(f"Loaded {len(records)} existing master records from {master_xlsx}")
    else:
        print("Warning: Master Excel not found, building from manifest.")
        records = []
        for fname, fpath in all_files_map.items():
            records.append({
                "source_photo": fname,
                "barcode": "",
                "batch": "G2" if "G2" in str(fpath) else "G3" if "G3" in str(fpath) else "G4" if "G4" in str(fpath) else "G5"
            })

    # 4. Detect Front Boxes
    cache = load_box_cache()
    print(f"Existing cached front boxes: {len(cache)}")

    to_detect = [p for fname, p in all_files_map.items() if fname not in cache or not cache[fname].get("front_box_2d")]
    print(f"Images needing front packaging detection: {len(to_detect)}")

    if to_detect:
        workers = 4
        completed = 0
        print(f"Starting detection with {workers} workers and dynamic pacing...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(detect_front_box_single, p, cache): p for p in to_detect}
            for fut in as_completed(futures):
                p = futures[fut]
                try:
                    fname, res = fut.result()
                    cache[fname] = res
                    completed += 1
                    save_box_cache(cache)
                    print(f"[{completed}/{len(to_detect)}] {fname} -> box={res.get('front_box_2d')} rot={res.get('front_rotation')} pos={res.get('front_position')}")
                except Exception as e:
                    print(f"Error detecting {p.name}: {e}")

        save_box_cache(cache)
        print(f"✅ Detection complete! Total cached boxes: {len(cache)}")

    # 5. Crop and Save all Front Images & Update Records
    print("\n✂️ Cropping and saving front images at native sensor resolution...")
    batch_records_map: dict[str, list[dict[str, Any]]] = {"G2": [], "G3": [], "G4": [], "G5": []}
    updated_records = []

    for idx, rec in enumerate(records):
        fname = str(rec.get("source_photo") or rec.get("Original Image") or "").strip()
        fpath = all_files_map.get(fname)
        if not fpath or not fpath.exists():
            # Try to find file by name
            for batch_folder in [Path("source-import/G2_original"), Path("source-import/G3_Original"), Path("source-import/G4-original"), Path("source-import/Nyt25.09.26")]:
                candidate = batch_folder / fname
                if candidate.exists():
                    fpath = candidate
                    break

        if not fpath or not fpath.exists():
            print(f"[{idx+1}/{len(records)}] Missing image file for {fname}")
            updated_records.append(rec)
            continue

        box_info = cache.get(fname, {})
        front_box = box_info.get("front_box_2d")
        front_rot = box_info.get("front_rotation", 0)

        orig_im = open_image_safely(fpath)
        barcode = str(rec.get("barcode") or rec.get("Barcode") or "").strip()
        record_id = str(rec.get("record_id") or rec.get("Record ID") or f"REC-{idx+1}").strip()
        batch_name = str(rec.get("batch") or rec.get("Batch") or "G2").strip()

        img_name, img_w, img_h = crop_and_save_front_images(
            orig_im=orig_im,
            front_box_2d=front_box,
            front_rotation=front_rot,
            barcode=barcode,
            record_id=record_id,
            batch_name=batch_name,
        )

        rec["Website Front Image"] = img_name
        rec["image_width_px"] = img_w
        rec["image_height_px"] = img_h
        rec["front_box_2d"] = front_box
        rec["front_rotation"] = front_rot

        updated_records.append(rec)
        if batch_name in batch_records_map:
            batch_records_map[batch_name].append(rec)

        if (idx + 1) % 50 == 0 or (idx + 1) == len(records):
            print(f"[{idx+1}/{len(records)}] Cropped {fname} -> {img_name} ({img_w}x{img_h}px, rot={front_rot}°)")

    # 6. Export Consolidations & Individual Batch Reports
    print("\n📊 Exporting Consolidated Master Excel and Shopify CSV...")
    export_master_excel(updated_records, OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx")
    export_shopify_csv(updated_records, OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv", batch_tag="g2_g5_shopify_import")

    for bname, brecs in batch_records_map.items():
        if brecs:
            export_master_excel(brecs, OUTPUT_DIR / f"{bname}_master_products.xlsx")
            export_shopify_csv(brecs, OUTPUT_DIR / f"{bname}_shopify_products.csv", batch_tag=f"{bname.lower()}_import")

    print("=" * 80)
    print("🎉 ALL G2-G5 FRONT IMAGES RE-CROPPED AND EXPORTED SUCCESSFULLY!")
    print(f"📁 Web front images folder: {WEB_FRONT_DIR.resolve()}")
    print(f"📁 Synced images folder:    {IMAGES_DIR.resolve()}")
    print(f"📄 Shopify CSV:            {(OUTPUT_DIR / 'Master_G2_G5_Shopify_Import.csv').resolve()}")
    print(f"📄 Master Excel:            {(OUTPUT_DIR / 'Master_G2_G5_Consolidated.xlsx').resolve()}")
    print("=" * 80)

if __name__ == "__main__":
    main()
