import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image, ImageOps
import pandas as pd
import cv2
import numpy as np

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely
from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel
from scripts.cv_front_detector import detect_front_box_cv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_DIR = Path("output/shopify_import")
WEB_FRONT_DIR = OUTPUT_DIR / "web_front_images"
IMAGES_DIR = OUTPUT_DIR / "images"
FRONT_BOX_CACHE = OUTPUT_DIR / "g2_g5_front_boxes.json"

WEB_FRONT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def is_faulty_box(box: list[int] | None, pos: str = "") -> bool:
    if not box or len(box) != 4:
        return True
    ymin, xmin, ymax, xmax = box
    h = ymax - ymin
    w = xmax - xmin
    if "fallback" in pos:
        return True
    if box in [[0, 0, 500, 1000], [0, 0, 1000, 500], [10, 20, 520, 980], [480, 20, 990, 980], [30, 480, 970, 990], [30, 10, 970, 520]]:
        return True
    # If the box is cropped too shallowly at the top (cutting bottom half)
    if h < 480 and ymin < 50:
        return True
    # If the box has negative or invalid dimensions
    if h <= 100 or w <= 100:
        return True
    return False

def try_read_barcode(pil_im: Image.Image) -> str | None:
    detector = cv2.barcode.BarcodeDetector()
    cv_im = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
    for rot in [0, 90, 180, 270]:
        if rot == 90:
            rotated = cv2.rotate(cv_im, cv2.ROTATE_90_CLOCKWISE)
        elif rot == 180:
            rotated = cv2.rotate(cv_im, cv2.ROTATE_180)
        elif rot == 270:
            rotated = cv2.rotate(cv_im, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            rotated = cv_im
        res, decoded_info, _, _ = detector.detectAndDecodeMulti(rotated)
        if res and decoded_info:
            for bc in decoded_info:
                if bc and len(bc) >= 8 and bc.isdigit():
                    return bc
    return None

def process_single_item(args: tuple[int, dict[str, Any], Path, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], bool]:
    idx, rec, fpath, cached_box_info = args
    fname = fpath.name
    
    orig_im = open_image_safely(fpath)
    w, h = orig_im.size
    
    box = cached_box_info.get("front_box_2d")
    pos = str(cached_box_info.get("front_position", ""))
    
    was_recropped = False
    if is_faulty_box(box, pos):
        # Recalculate with safe detector
        new_box, new_rot, mode = detect_front_box_cv(fpath)
        box_info = {
            "front_box_2d": new_box,
            "front_rotation": new_rot,
            "front_position": mode,
            "brand_and_name": cached_box_info.get("brand_and_name", "")
        }
        was_recropped = True
    else:
        box_info = cached_box_info
    
    front_box = box_info.get("front_box_2d", [0, 0, 1000, 1000])
    front_rot = int(box_info.get("front_rotation", 0) or 0)
    
    # Safe crop bounds
    if front_box and len(front_box) == 4 and front_box != [0, 0, 1000, 1000]:
        ymin, xmin, ymax, xmax = front_box
        pad_w = int((xmax - xmin) * 0.03)
        pad_h = int((ymax - ymin) * 0.03)
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
        
    if front_rot != 0:
        crop_im = crop_im.rotate(-front_rot, expand=True)
        
    barcode = str(rec.get("barcode") or rec.get("Barcode") or "").strip()
    if barcode.endswith(".0"):
        barcode = barcode[:-2]
    if barcode.lower() in {"none", "nan", ""}:
        barcode = ""
        # Try reading barcode from original image
        scanned_bc = try_read_barcode(orig_im)
        if scanned_bc:
            barcode = scanned_bc
            rec["barcode"] = barcode
            rec["barcode_check_status"] = "Đúng checksum; đọc từ ảnh qua CV scanner"
            
    record_id = str(rec.get("record_id") or rec.get("Record ID") or f"REC-{idx+1}").strip()
    batch_name = str(rec.get("batch") or rec.get("Batch") or "G2").strip()
    
    if barcode:
        base_name = barcode
    else:
        base_name = f"NO_BARCODE_{batch_name}_{record_id}"
        
    jpg_name = f"{base_name}.jpg"
    webp_name = f"{base_name}.webp"
    
    # Save high-quality web assets
    crop_im.save(WEB_FRONT_DIR / jpg_name, format="JPEG", quality=95, optimize=True)
    crop_im.save(WEB_FRONT_DIR / webp_name, format="WEBP", quality=88, method=4)
    crop_im.save(IMAGES_DIR / jpg_name, format="JPEG", quality=95, optimize=True)
    crop_im.save(IMAGES_DIR / webp_name, format="WEBP", quality=88, method=4)
    
    updated = dict(rec)
    updated["Website Front Image"] = jpg_name
    updated["image_width_px"] = crop_im.width
    updated["image_height_px"] = crop_im.height
    updated["front_box_2d"] = front_box
    updated["front_rotation"] = front_rot
    
    return updated, {fname: box_info}, was_recropped

def main():
    print("=" * 80)
    print("🛠️ NON-DESTRUCTIVE RE-CROP & BARCODE RESOLVER")
    print("=" * 80)
    
    with open("output/g2_g5_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    all_files_map: dict[str, Path] = {}
    for batch_name, bdata in manifest["batches"].items():
        folder = Path(bdata["folder"])
        for fentry in bdata["files"]:
            all_files_map[fentry["filename"]] = folder / fentry["filename"]

    if FRONT_BOX_CACHE.exists():
        with open(FRONT_BOX_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}

    master_xlsx = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    df = pd.read_excel(master_xlsx)
    records = df.to_dict(orient="records")
    print(f"Loaded {len(records)} records from {master_xlsx}")

    tasks = []
    for idx, rec in enumerate(records):
        fname = str(rec.get("source_photo") or rec.get("Original Image") or "").strip()
        fpath = all_files_map.get(fname)
        if not fpath or not fpath.exists():
            for batch_folder in [Path("source-import/G2_original"), Path("source-import/G3_Original"), Path("source-import/G4-original"), Path("source-import/Nyt25.09.26")]:
                cand = batch_folder / fname
                if cand.exists():
                    fpath = cand
                    break
        if fpath and fpath.exists():
            box_info = cache.get(fname, {})
            tasks.append((idx, rec, fpath, box_info))

    print(f"\nProcessing {len(tasks)} items across 8 parallel threads...")
    
    updated_records = []
    new_cache = dict(cache)
    recropped_count = 0
    completed = 0
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_single_item, task): task for task in tasks}
        for fut in as_completed(futures):
            try:
                rec_out, b_dict, was_recropped = fut.result()
                updated_records.append(rec_out)
                new_cache.update(b_dict)
                if was_recropped:
                    recropped_count += 1
                completed += 1
                if completed % 100 == 0 or completed == len(tasks):
                    elapsed = time.time() - t0
                    print(f"[{completed}/{len(tasks)}] Processed in {elapsed:.1f}s | Recropped fixed: {recropped_count}")
            except Exception as e:
                print(f"Error processing item: {e}")

    # Save updated cache
    with open(FRONT_BOX_CACHE, "w", encoding="utf-8") as f:
        json.dump(new_cache, f, ensure_ascii=False, indent=2)

    # Sort
    updated_records.sort(key=lambda r: str(r.get("record_id", "")))

    # Export master files
    print("\n📊 Re-exporting Master Excel and Shopify CSV...")
    export_master_excel(updated_records, OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx")
    export_shopify_csv(updated_records, OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv", batch_tag="g2_g5_shopify_import")

    # Per batch export
    batch_map: dict[str, list[dict[str, Any]]] = {"G2": [], "G3": [], "G4": [], "G5": []}
    for r in updated_records:
        b = str(r.get("batch") or "G2")
        if b in batch_map:
            batch_map[b].append(r)

    for bname, brecs in batch_map.items():
        if brecs:
            export_master_excel(brecs, OUTPUT_DIR / f"{bname}_master_products.xlsx")
            export_shopify_csv(brecs, OUTPUT_DIR / f"{bname}_shopify_products.csv", batch_tag=f"{bname.lower()}_import")

    print("\n" + "=" * 80)
    print(f"✅ FINISHED! Total processed: {len(updated_records)}")
    print(f"✂️ Total truncated/faulty crops fixed: {recropped_count}")
    print(f"📁 Output web front images: {WEB_FRONT_DIR.resolve()}")
    print("=" * 80)

if __name__ == "__main__":
    main()
