#!/usr/bin/env python3
"""
Pipeline processing for G4-original dataset.
Complies with customer requirements:
1. Single-face products: export barcode image for both front and back to synchronize quantity.
2. Deduplication: skip barcodes already processed in previous datasets (G1, G2, G3).
3. Non-matching barcodes: delete front, back, and original image for barcodes not in customer Excel.
4. Update Excel file with embedded images.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from PIL import Image

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "src"), str(ROOT / "scripts")])

from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import (
    enhance_back,
    packshot_front,
    panel_halves,
    predict_split,
    read_retail_barcodes,
    scan_file,
    split_sides,
)
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants
from retry_g2_missing_barcodes import hard_read, _excel_barcode

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
G4_DIR = ROOT / "source-import/G4-original"
FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
MANIFEST_PATH = ROOT / "output/catalog_pairs/manifest_G4-original_v2.json"

FRONT_DIR.mkdir(parents=True, exist_ok=True)
BACK_DIR.mkdir(parents=True, exist_ok=True)


def parse_timestamp(filename: str) -> datetime | None:
    try:
        parts = filename.split("_")
        ts_str = parts[0] + "_" + parts[1][:6]
        return datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
    except Exception:
        return None


def run_g4_pipeline():
    print("=" * 80)
    print("STARTING G4-ORIGINAL PIPELINE EXECUTION")
    print("=" * 80)

    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    product_by_barcode = {p["barcode"]: p for p in products}
    print(f"Loaded {len(products)} products from {EXCEL_SOURCE.name}")

    existing_back_v2 = {
        p.stem.replace("-back", "").replace("_back", "")
        for p in BACK_DIR.glob("*.jpg")
    }
    existing_front_v2 = {
        p.stem.replace("-front", "").replace("_front", "")
        for p in FRONT_DIR.glob("*.jpg")
    }
    print(f"Existing in v2: {len(existing_front_v2)} front, {len(existing_back_v2)} back")

    all_files = sorted(list(G4_DIR.glob("*.*")))
    print(f"Total files in G4-original: {len(all_files)}")

    # Step 1: Scan all files
    print("\n[Step 1] Scanning barcodes...")
    scanned_records = {}
    for f in all_files:
        rec = scan_file(f, set(lookup.keys()))
        bc = rec.get("barcode")
        if not bc:
            # Try hard read
            h = hard_read(f)
            if h:
                bc = h["text"]
                rec["barcode"] = bc
                rec["center"] = h["center"]
        
        xl_bc = lookup.get(bc) if bc else None
        if bc and not xl_bc:
            for v in get_barcode_lookup_variants(bc):
                if v in lookup:
                    xl_bc = lookup[v]
                    break
        rec["excel_barcode"] = xl_bc
        rec["ts"] = parse_timestamp(f.name)
        scanned_records[f.name] = rec

    # Step 2: Delete barcodes not in Excel
    print("\n[Step 2] Identifying barcodes NOT in Excel...")
    not_in_excel_files = []
    for f_name, rec in scanned_records.items():
        bc = rec.get("barcode")
        xl_bc = rec.get("excel_barcode")
        if bc and not xl_bc:
            not_in_excel_files.append((f_name, bc))

    deleted_not_in_excel = []
    for f_name, bc in not_in_excel_files:
        print(f"  --> Barcode {bc} in {f_name} NOT in Excel! Deleting...")
        # Delete front and back if exists
        for v in set(get_barcode_lookup_variants(bc)) | {bc}:
            f_img = FRONT_DIR / f"{v}-front.jpg"
            b_img = BACK_DIR / f"{v}-back.jpg"
            if f_img.exists():
                f_img.unlink()
                print(f"      Deleted {f_img.name}")
            if b_img.exists():
                b_img.unlink()
                print(f"      Deleted {b_img.name}")
        # Delete original file
        orig_file = G4_DIR / f_name
        if orig_file.exists():
            orig_file.unlink()
            print(f"      Deleted original {f_name}")
            deleted_not_in_excel.append({"file": f_name, "barcode": bc})

    # Refresh remaining files after deletion
    remaining_files = sorted(list(G4_DIR.glob("*.*")))
    print(f"Remaining files in G4-original: {len(remaining_files)}")

    # Step 3: Find tight front-back pairs (separate front photo taken within 10s of back photo)
    print("\n[Step 3] Detecting adjacent front/back photo pairs...")
    file_list = [f.name for f in remaining_files]
    tight_pairs = {}  # excel_barcode -> front_file_name
    
    for idx, f_name in enumerate(file_list):
        rec = scanned_records[f_name]
        if rec.get("barcode"):
            continue  # It's a back/barcoded photo
        # It's a photo without barcode. Check neighbors
        cur_ts = rec.get("ts")
        if not cur_ts:
            continue
        prev_name = file_list[idx - 1] if idx > 0 else None
        next_name = file_list[idx + 1] if idx < len(file_list) - 1 else None
        
        prev_rec = scanned_records.get(prev_name) if prev_name else None
        next_rec = scanned_records.get(next_name) if next_name else None
        
        prev_diff = abs((cur_ts - prev_rec["ts"]).total_seconds()) if prev_rec and prev_rec.get("ts") else 999
        next_diff = abs((next_rec["ts"] - cur_ts).total_seconds()) if next_rec and next_rec.get("ts") else 999

        closest_rec = None
        closest_name = None
        min_diff = min(prev_diff, next_diff)

        if min_diff <= 10:
            if prev_diff <= next_diff and prev_rec and prev_rec.get("excel_barcode"):
                closest_rec = prev_rec
                closest_name = prev_name
            elif next_rec and next_rec.get("excel_barcode"):
                closest_rec = next_rec
                closest_name = next_name

        if closest_rec and closest_name:
            xl_bc = closest_rec["excel_barcode"]
            if xl_bc not in tight_pairs:
                tight_pairs[xl_bc] = f_name
                print(f"  Paired front {f_name} with back {closest_name} (barcode {xl_bc}, diff {min_diff:.1f}s)")

    # Step 4: Group remaining barcoded records by excel_barcode
    by_barcode = defaultdict(list)
    for f_name in file_list:
        rec = scanned_records[f_name]
        xl_bc = rec.get("excel_barcode")
        if xl_bc:
            by_barcode[xl_bc].append(rec)

    print(f"\nTotal unique Excel barcodes found in G4: {len(by_barcode)}")

    # Step 5: Process and Export (Handling duplicates, 1-face synchronization)
    print("\n[Step 5] Exporting front-v2 and back-v2...")
    skipped_duplicates = []
    exported_products = {}

    for barcode, photos in sorted(by_barcode.items()):
        # Check if already exists in previous back-v2
        if barcode in existing_back_v2:
            skipped_duplicates.append(barcode)
            print(f"  [SKIPPED DUP] Barcode {barcode} already present in previous v2 data")
            continue

        # Select best photo for back (largest area / resolution)
        best_photo = max(photos, key=lambda r: float(r.get("area") or 0))
        img_path = Path(best_photo["path"])
        image = open_image_safely(img_path)
        cx = float(best_photo.get("center", [image.size[0] / 2, image.size[1] / 2])[0])
        cy = float(best_photo.get("center", [image.size[0] / 2, image.size[1] / 2])[1])

        front_path = FRONT_DIR / f"{barcode}-front.jpg"
        back_path = BACK_DIR / f"{barcode}-back.jpg"

        # Case A: Separate front photo paired
        if barcode in tight_pairs:
            front_file_name = tight_pairs[barcode]
            front_img_path = G4_DIR / front_file_name
            front_img = open_image_safely(front_img_path)
            front_result = packshot_front(front_img)
            save_image_high_quality(front_result, front_path, quality=95, save_webp=False)
            front_img.close()

            # Back is full or enhanced crop
            back_result = enhance_back(image)
            save_image_high_quality(back_result, back_path, quality=94, save_webp=False)
            image.close()

            status = {
                "barcode": barcode,
                "mode": "separate_paired_photos",
                "front_source": str(front_img_path),
                "back_source": str(img_path),
                "front_ok": True,
                "back_ok": True,
            }
            exported_products[barcode] = status
            print(f"  [EXPORTED PAIRED] {barcode} -> separate front ({front_file_name}) + back")
            continue

        # Case B: Try panel split on the photo
        sides = split_sides(image, cx, cy, 0)
        back_crop = image.crop(sides.back)
        back_result = enhance_back(back_crop)
        
        expected_forms = set(get_barcode_lookup_variants(barcode)) | {barcode}
        hits = read_retail_barcodes(back_result)
        if not any(h.text in expected_forms for h in hits):
            half = panel_halves(image, cx, cy, 0)
            candidate = enhance_back(image.crop(half.back))
            if any(h.text in expected_forms for h in read_retail_barcodes(candidate)):
                back_result = candidate
                sides = half
            else:
                back_result = enhance_back(image)
        save_image_high_quality(back_result, back_path, quality=94, save_webp=False)

        if sides.mode != "back_only" and sides.front is not None:
            # 2 panels detected in single photo
            front_crop = image.crop(sides.front)
            front_result = packshot_front(front_crop)
            save_image_high_quality(front_result, front_path, quality=95, save_webp=False)
            status = {
                "barcode": barcode,
                "mode": sides.mode,
                "source": str(img_path),
                "front_ok": True,
                "back_ok": True,
            }
            exported_products[barcode] = status
            print(f"  [EXPORTED SPLIT] {barcode} -> split mode {sides.mode}")
        else:
            # Case C: Single-face product (1 mặt)
            # Rule: "nếu nhận diện chỉ có 1 mặt xuất ảnh barcode cho cả front và back để đồng bộ số lượng"
            # Export the high-quality enhanced barcode image for BOTH front and back
            save_image_high_quality(back_result, front_path, quality=95, save_webp=False)
            status = {
                "barcode": barcode,
                "mode": "single_face_mirrored_to_front",
                "source": str(img_path),
                "front_ok": True,
                "back_ok": True,
            }
            exported_products[barcode] = status
            print(f"  [EXPORTED 1-FACE SYNC] {barcode} -> synced barcode image to both front & back")

        image.close()

    # Step 6: Write manifest report
    manifest_data = {
        "dataset": "G4-original",
        "total_files_initial": len(all_files),
        "deleted_not_in_excel": deleted_not_in_excel,
        "remaining_files": len(remaining_files),
        "skipped_duplicates_from_prev_v2": skipped_duplicates,
        "new_products_exported": exported_products,
        "total_exported": len(exported_products),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nManifest saved to {MANIFEST_PATH}")
    print(f"Total new products exported from G4: {len(exported_products)}")
    print(f"Total duplicates skipped: {len(skipped_duplicates)}")
    print(f"Total non-Excel images deleted: {len(deleted_not_in_excel)}")

    # Step 7: Embed images into customer Excel
    print("\n[Step 7] Updating Rabuta_12_10_Delivery_Embedded_v2.xlsx with all v2 images...")
    from embed_v2_images_to_excel import embed_catalog_images
    embed_catalog_images()


if __name__ == "__main__":
    run_g4_pipeline()
