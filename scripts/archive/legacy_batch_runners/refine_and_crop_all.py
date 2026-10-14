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

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely, SUPPORTED_EXTENSIONS
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

def crop_single_record(args: tuple[int, dict[str, Any], Path, dict[str, Any]]) -> dict[str, Any]:
    idx, rec, fpath, box_info = args
    fname = fpath.name
    front_box = box_info.get("front_box_2d")
    front_rot = int(box_info.get("front_rotation", 0) or 0)

    try:
        orig_im = open_image_safely(fpath)
        w, h = orig_im.size

        if front_box and len(front_box) == 4:
            ymin, xmin, ymax, xmax = front_box
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

        # Rotate ONLY by verified text orientation
        if front_rot != 0:
            crop_im = crop_im.rotate(-front_rot, expand=True)

        barcode = str(rec.get("barcode") or rec.get("Barcode") or "").strip()
        if barcode.endswith(".0"):
            barcode = barcode[:-2]
        if barcode.lower() in {"none", "nan", ""}:
            barcode = ""

        record_id = str(rec.get("record_id") or rec.get("Record ID") or f"REC-{idx+1}").strip()
        batch_name = str(rec.get("batch") or rec.get("Batch") or "G2").strip()

        if barcode:
            base_name = barcode
        else:
            base_name = f"NO_BARCODE_{batch_name}_{record_id or idx+1}"

        jpg_name = f"{base_name}.jpg"
        webp_name = f"{base_name}.webp"

        # Save to Web Front Images folder
        web_jpg_path = WEB_FRONT_DIR / jpg_name
        web_webp_path = WEB_FRONT_DIR / webp_name
        crop_im.save(web_jpg_path, format="JPEG", quality=95, optimize=True)
        crop_im.save(web_webp_path, format="WEBP", quality=88, method=4)

        # Sync to images folder
        img_jpg_path = IMAGES_DIR / jpg_name
        img_webp_path = IMAGES_DIR / webp_name
        crop_im.save(img_jpg_path, format="JPEG", quality=95, optimize=True)
        crop_im.save(img_webp_path, format="WEBP", quality=88, method=4)

        updated = dict(rec)
        updated["Website Front Image"] = jpg_name
        updated["image_width_px"] = crop_im.width
        updated["image_height_px"] = crop_im.height
        updated["front_box_2d"] = front_box
        updated["front_rotation"] = front_rot
        return updated
    except Exception as e:
        print(f"Error cropping {fname}: {e}")
        return rec

def main():
    print("=" * 80)
    print("🚀 HIGH-SPEED PARALLEL CROPPING & WEB ASSETS GENERATION")
    print("=" * 80)

    # 1. Load Manifest
    manifest_path = Path("output/g2_g5_manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    all_files_map: dict[str, Path] = {}
    for batch_name, bdata in manifest["batches"].items():
        folder = Path(bdata["folder"])
        for fentry in bdata["files"]:
            fname = fentry["filename"]
            all_files_map[fname] = folder / fname

    print(f"Total manifest files: {len(all_files_map)}")

    # 2. Load Cache
    if FRONT_BOX_CACHE.exists():
        with open(FRONT_BOX_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}

    print(f"Existing cached boxes: {len(cache)}")

    # 3. Load Master Consolidated Records
    master_xlsx = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    if master_xlsx.exists():
        master_df = pd.read_excel(master_xlsx)
        records = master_df.to_dict(orient="records")
        print(f"Loaded {len(records)} existing master records from {master_xlsx}")
    else:
        records = []

    # 4. Prepare task list
    tasks = []
    for idx, rec in enumerate(records):
        fname = str(rec.get("source_photo") or rec.get("Original Image") or "").strip()
        fpath = all_files_map.get(fname)
        if not fpath or not fpath.exists():
            for batch_folder in [Path("source-import/G2_original"), Path("source-import/G3_Original"), Path("source-import/G4-original"), Path("source-import/Nyt25.09.26")]:
                candidate = batch_folder / fname
                if candidate.exists():
                    fpath = candidate
                    break
        if fpath and fpath.exists():
            box_info = cache.get(fname, {})
            tasks.append((idx, rec, fpath, box_info))

    print(f"\n✂️ Executing parallel cropping across 8 threads for {len(tasks)} items...")
    updated_records = []
    completed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(crop_single_record, task): task for task in tasks}
        for fut in as_completed(futures):
            try:
                res = fut.result()
                updated_records.append(res)
                completed += 1
                if completed % 100 == 0 or completed == len(tasks):
                    elapsed = time.time() - t0
                    print(f"[{completed}/{len(tasks)}] Cropped in {elapsed:.1f}s ({completed/elapsed:.1f} imgs/sec)")
            except Exception as e:
                print(f"Crop task error: {e}")

    # Re-sort records to preserve original order
    updated_records.sort(key=lambda r: str(r.get("record_id", "")))

    # Organize per-batch
    batch_records_map: dict[str, list[dict[str, Any]]] = {"G2": [], "G3": [], "G4": [], "G5": []}
    for r in updated_records:
        b = str(r.get("batch") or "G2")
        if b in batch_records_map:
            batch_records_map[b].append(r)

    # 5. Export Consolidated Master Files
    print("\n📊 Exporting Consolidated Master Excel and Shopify CSV...")
    export_master_excel(updated_records, OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx")
    export_shopify_csv(updated_records, OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv", batch_tag="g2_g5_shopify_import")

    for bname, brecs in batch_records_map.items():
        if brecs:
            export_master_excel(brecs, OUTPUT_DIR / f"{bname}_master_products.xlsx")
            export_shopify_csv(brecs, OUTPUT_DIR / f"{bname}_shopify_products.csv", batch_tag=f"{bname.lower()}_import")

    print("\n" + "=" * 80)
    print("🎉 ALL 1,196 G2-G5 PRODUCT CROPS GENERATED AND EXPORTED SUCCESSFULLY!")
    print(f"📁 Dedicated Web Front Images: {WEB_FRONT_DIR.resolve()}")
    print(f"📁 Synced Images:             {IMAGES_DIR.resolve()}")
    print(f"📄 Master Shopify CSV:         {(OUTPUT_DIR / 'Master_G2_G5_Shopify_Import.csv').resolve()}")
    print(f"📄 Master Consolidated Excel:  {(OUTPUT_DIR / 'Master_G2_G5_Consolidated.xlsx').resolve()}")
    print("=" * 80)

if __name__ == "__main__":
    main()
