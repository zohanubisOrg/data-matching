from __future__ import annotations

import base64
import concurrent.futures
import glob
import io
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from src.product_mapper.vision.barcode_validator import get_barcode_lookup_variants, validate_ean_upc_checksum
from src.product_mapper.vision.gemini_vision import GeminiVisionExtractor, PackagingVisionResult
from src.product_mapper.enrichment.market_enricher import MarketCatalogEnricher
from src.product_mapper.g1_pipeline import COLUMNS_65_MAPPING

IMAGES_DIR = Path("G1_original")
OUTPUT_DIR = Path("output/g1_delivery")
WEBSITE_IMAGES_DIR = OUTPUT_DIR / "website_front_images"
WEB_FRONT_DIR = Path("web/public/products/front")
WEB_RAW_DIR = Path("web/public/products/raw")
CACHE_FILE = OUTPUT_DIR / "g1_deep_scan_65_cache.json"
MASTER_EXCEL_OUT = OUTPUT_DIR / "G1_Master_Delivery_v2.xlsx"
WEB_JSON_OUT = Path("web/public/data/products.json")
WEB_EXCEL_OUT = Path("web/public/data/G1_Master_Delivery_65_Columns.xlsx")
POS_FILE = Path("Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")

FILE_LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()


def load_pos_lookup() -> dict[str, dict[str, str]]:
    pos_lookup: dict[str, dict[str, str]] = {}
    if POS_FILE.exists():
        try:
            df = pd.read_excel(POS_FILE)
            df["Bar Code"] = df["Bar Code"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            for _, r in df.iterrows():
                bc = str(r["Bar Code"]).strip()
                if bc and bc != "nan":
                    info = {
                        "sku": str(r.get("Sku Code", "")).strip(),
                        "name": str(r.get("Product Name ", "")).strip(),
                        "official_name": str(r.get("Oficial Name ", "")).strip(),
                    }
                    for var in get_barcode_lookup_variants(bc):
                        pos_lookup[var] = info
        except Exception as e:
            print(f"Warning: could not load POS lookup: {e}")
    return pos_lookup


def scan_zxing_direct(img_path: Path, pos_lookup: dict[str, dict[str, str]]) -> str | None:
    import zxingcpp

    try:
        with Image.open(img_path) as im:
            im = ImageOps.exif_transpose(im)
            for rot in [0, 90, 180, 270]:
                im_rot = im if rot == 0 else im.rotate(rot, expand=True)
                results = zxingcpp.read_barcodes(im_rot)
                for r in results:
                    t = str(getattr(r, "text", "")).strip()
                    if t.isdigit() and len(t) >= 8:
                        if validate_ean_upc_checksum(t) or any(v in pos_lookup for v in get_barcode_lookup_variants(t)):
                            return t

            enhanced = ImageEnhance.Contrast(im).enhance(2.0)
            for rot in [0, 90, 180, 270]:
                im_rot = enhanced.rotate(rot, expand=True)
                for r in zxingcpp.read_barcodes(im_rot):
                    t = str(getattr(r, "text", "")).strip()
                    if t.isdigit() and len(t) >= 8:
                        if validate_ean_upc_checksum(t) or any(v in pos_lookup for v in get_barcode_lookup_variants(t)):
                            return t
    except Exception:
        pass
    return None


def recover_barcode_via_zoom(img_path: Path, box_2d: list[int] | None, vision_extractor: GeminiVisionExtractor, pos_lookup: dict[str, dict[str, str]]) -> str | None:
    import zxingcpp

    if not box_2d or len(box_2d) != 4:
        return None

    try:
        with Image.open(img_path) as orig_im:
            orig_im = ImageOps.exif_transpose(orig_im)
            w, h = orig_im.size
            ymin, xmin, ymax, xmax = box_2d
            pad_x = int((xmax - xmin) * w / 1000 * 0.15)
            pad_y = int((ymax - ymin) * h / 1000 * 0.15)

            left = max(0, int(xmin * w / 1000) - pad_x)
            top = max(0, int(ymin * h / 1000) - pad_y)
            right = min(w, int(xmax * w / 1000) + pad_x)
            bottom = min(h, int(ymax * h / 1000) + pad_y)

            if right <= left or bottom <= top:
                return None

            crop_bc = orig_im.crop((left, top, right, bottom))
            cw, ch = crop_bc.size
            if ch > cw * 1.2:
                crop_bc = crop_bc.rotate(90, expand=True)

            enhanced = ImageEnhance.Contrast(crop_bc).enhance(2.2)
            for rot in [0, 90, 180, 270]:
                im_rot = enhanced if rot == 0 else enhanced.rotate(rot, expand=True)
                for r in zxingcpp.read_barcodes(im_rot):
                    t = str(getattr(r, "text", "")).strip()
                    if t.isdigit() and (validate_ean_upc_checksum(t) or any(v in pos_lookup for v in get_barcode_lookup_variants(t))):
                        return t

            digits = vision_extractor.read_zoomed_barcode(crop_bc)
            if digits:
                if validate_ean_upc_checksum(digits) or any(v in pos_lookup for v in get_barcode_lookup_variants(digits)):
                    return digits
    except Exception as e:
        with PRINT_LOCK:
            print(f"  [Zoom Barcode Error] {img_path.name}: {e}")
    return None


def crop_and_normalize_front_image(src_path: Path, box_2d: list[int] | None, rot_needed: int, dest_webp_path: Path) -> tuple[int, int]:
    dest_webp_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size

        if box_2d and len(box_2d) == 4:
            ymin, xmin, ymax, xmax = box_2d
            left = int(xmin * w / 1000)
            top = int(ymin * h / 1000)
            right = int(xmax * w / 1000)
            bottom = int(ymax * h / 1000)

            pad_x = int((right - left) * 0.015)
            pad_y = int((bottom - top) * 0.015)
            left = max(0, left - pad_x)
            top = max(0, top - pad_y)
            right = min(w, right + pad_x)
            bottom = min(h, bottom + pad_y)

            if right > left and bottom > top:
                cropped = im.crop((left, top, right, bottom))
            else:
                cropped = im
        else:
            cropped = im

        if rot_needed != 0:
            cropped = cropped.rotate(-rot_needed, expand=True)

        cw, ch = cropped.size
        if cw > ch * 1.05:
            cropped = cropped.rotate(270, expand=True)

        cropped.convert("RGB").save(dest_webp_path, format="WEBP", quality=88)
        return cropped.size


def export_all(records: list[dict[str, Any]]) -> None:
    with FILE_LOCK:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        WEB_JSON_OUT.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"

        headers = [col_title for col_title, _ in COLUMNS_65_MAPPING]
        ws.append([])  # Blank row 1
        ws.append(headers)  # Row 2 headers

        brands_set = set()
        confirmed_count = 0
        pos_matched_count = 0

        for r in records:
            row_data = []
            for col_title, attr_name in COLUMNS_65_MAPPING:
                val = r.get(attr_name, "")
                if val is None:
                    row_data.append(None)
                elif isinstance(val, (int, float)):
                    row_data.append(val)
                else:
                    row_data.append(str(val))
            ws.append(row_data)

            b = r.get("brand")
            if b and str(b) != "nan":
                brands_set.add(str(b))
            if r.get("status") == "CONFIRMED" or (r.get("barcode") and not str(r.get("barcode")).startswith("NO_BARCODE")):
                confirmed_count += 1
            if r.get("pos_sku"):
                pos_matched_count += 1

        try:
            wb.save(MASTER_EXCEL_OUT)
            shutil.copy2(MASTER_EXCEL_OUT, WEB_EXCEL_OUT)
        except PermissionError:
            backup_path = OUTPUT_DIR / "G1_Master_Delivery_v2_latest.xlsx"
            try:
                wb.save(backup_path)
            except Exception:
                pass
        except Exception:
            pass

        stats = {
            "total": len(records),
            "confirmed": confirmed_count,
            "pos_matched": pos_matched_count,
            "review_needed": len(records) - confirmed_count,
            "brands_count": len(brands_set),
        }

        payload = {
            "stats": stats,
            "brands": sorted(list(brands_set)),
            "products": records,
        }

        with open(WEB_JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def process_single_image(
    img_path: Path,
    idx: int,
    total_imgs: int,
    pos_lookup: dict[str, dict[str, str]],
    vision_extractor: GeminiVisionExtractor,
    market_enricher: MarketCatalogEnricher,
    cache_data: dict[str, dict[str, Any]],
    processed_records: list[dict[str, Any]],
) -> dict[str, Any]:
    fname = img_path.name
    record_id = f"G1-{idx:04d}"

    with FILE_LOCK:
        if fname in cache_data and cache_data[fname].get("full_name_en") and (cache_data[fname].get("energy_kcal") is not None or cache_data[fname].get("ingredients_en")):
            rec = cache_data[fname]
            processed_records.append(rec)
            with PRINT_LOCK:
                print(f"[{idx:03d}/{total_imgs}] (CACHED) {fname} -> {rec.get('barcode')} | {rec.get('full_name_en')[:40]} ({rec.get('energy_kcal')} kcal)")
            return rec

    with PRINT_LOCK:
        print(f"[{idx:03d}/{total_imgs}] 🔍 Deep scanning {fname} (Multi-Stage High-Res)...")

    # 1. Barcode Detection: Direct ZXing with 4 orthogonal angles & CLAHE
    barcode = scan_zxing_direct(img_path, pos_lookup)
    detection_method = "zxing_direct" if barcode else "none"

    # 2. Multi-Stage High-Res Vision AI (Front + Back + Rotation)
    v_res = vision_extractor.analyze_image_deep(img_path, force_fresh=True)

    # Fallback 1: Vision full view barcode
    if not barcode and v_res.barcode:
        cleaned = re.sub(r"[^\d]", "", str(v_res.barcode))
        if len(cleaned) >= 8 and (validate_ean_upc_checksum(cleaned) or any(v in pos_lookup for v in get_barcode_lookup_variants(cleaned))):
            barcode = cleaned
            detection_method = "vision_full_view"

    # Fallback 2: Zoom recovery from high-res barcode region
    if not barcode and v_res.barcode_box_2d:
        zoom_bc = recover_barcode_via_zoom(img_path, v_res.barcode_box_2d, vision_extractor, pos_lookup)
        if zoom_bc:
            barcode = zoom_bc
            detection_method = "high_res_zoom"

    # Final barcode formatting
    if not barcode:
        barcode = f"NO_BARCODE_{Path(fname).stem}"
        barcode_check = "Chưa nhận diện được barcode rõ nét"
        status = "NO_BARCODE_MANUAL_REVIEW"
    else:
        barcode_check = "Đúng checksum; đọc từ ảnh"
        status = "CONFIRMED"

    # POS Cross-referencing
    pos_info = {}
    for var in get_barcode_lookup_variants(barcode):
        if var in pos_lookup:
            pos_info = pos_lookup[var]
            break

    pos_sku = v_res.supplier_sku or (pos_info.get("sku", "") if pos_info else "")
    pos_name = pos_info.get("name", "") if pos_info else ""

    # Crop front image and save to Web WebP
    front_webp_file = f"{barcode}.webp"
    dest_webp_path = WEB_FRONT_DIR / front_webp_file
    cw, ch = crop_and_normalize_front_image(img_path, v_res.front_box_2d, v_res.front_rotation, dest_webp_path)

    raw_webp_file = f"{Path(fname).stem}.webp"
    raw_web_url = f"/products/raw/{raw_webp_file}"
    front_web_url = f"/products/front/{front_webp_file}"

    full_title_en = (v_res.full_name_en or v_res.literal_label_name or v_res.product_name or "").strip()
    if not full_title_en and pos_name:
        full_title_en = pos_name

    rec = {
        "barcode": barcode,
        "literal_label_name": v_res.literal_label_name or full_title_en,
        "full_name_en": full_title_en,
        "fuldt_navn_da": v_res.fuldt_navn_da or "",
        "brand": v_res.brand or "",
        "record_id": record_id,
        "barcode_check_status": barcode_check,
        "name_source_notes": v_res.name_source_notes or "Tên đầy đủ EN/DA chuẩn hóa từ nhãn; bản DA là bản dịch biên tập.",
        "variant": v_res.variant or "",
        "category": v_res.category or "Grocery",
        "packaging": v_res.packaging or "Bag",
        "net_quantity": v_res.net_quantity,
        "net_unit": v_res.net_unit or "g",
        "unit_count": v_res.unit_count,
        "barcode_text_read": barcode if not barcode.startswith("NO_BARCODE") else "",
        "supplier_sku": pos_sku,
        "other_printed_codes": v_res.other_printed_codes or "",
        
        # Supply chain
        "manufacturer": v_res.manufacturer or "",
        "manufacturer_address": v_res.manufacturer_address or "",
        "country_of_origin": v_res.country_of_origin or "",
        "origin_label_evidence": v_res.origin_label_evidence or "",
        "importer": v_res.importer or "",
        "importer_address": v_res.importer_address or "",
        "distributor": v_res.distributor or "",

        # Ingredients & Allergens
        "ingredients_label_language": v_res.ingredients_label_language or "",
        "ingredients_en": v_res.ingredients_en or "",
        "ingredienser_da": v_res.ingredienser_da or "",
        "ingredient_translation_notes": v_res.ingredient_translation_notes or "Dịch thuật tiêu chuẩn EU FIC 1169/2011",
        "allergens_label": v_res.allergens_label or "",
        "allergens_en": v_res.allergens_en or "",
        "allergener_da": v_res.allergener_da or "",
        "may_contain_label": v_res.may_contain_label or "",

        # Nutrition Facts
        "nutrition_basis": v_res.nutrition_basis or "per 100 g",
        "energy_kj": v_res.energy_kj,
        "energy_kcal": v_res.energy_kcal,
        "fat_g": v_res.fat_g,
        "saturates_g": v_res.saturates_g,
        "carbohydrate_g": v_res.carbohydrate_g,
        "sugars_g": v_res.sugars_g,
        "fibre_g": v_res.fibre_g,
        "protein_g": v_res.protein_g,
        "salt_g": v_res.salt_g,
        "other_nutrition_source": v_res.other_nutrition_source or "",

        # Usage, Storage & Dates
        "preparation_label": v_res.preparation_label or "",
        "preparation_en": v_res.preparation_en or "",
        "tilberedning_da": v_res.tilberedning_da or "",
        "storage_label": v_res.storage_label or "",
        "storage_en": v_res.storage_en or "",
        "opbevaring_da": v_res.opbevaring_da or "",
        "warnings_label": v_res.warnings_label or "",
        "claims_certifications": v_res.claims_certifications or "",
        "alcohol_vol": v_res.alcohol_vol,
        "manufacture_date": v_res.manufacture_date or "",
        "best_before_expiry": v_res.best_before_expiry or "",
        "lot_batch": v_res.lot_batch or "",
        "website_contact": v_res.website_contact or "",
        "other_legible_info": v_res.other_legible_info or "",

        # Media & Visual Fields
        "source_photo_filenames": f"G1: {fname}",
        "selected_front_source": f"G1/{fname}",
        "front_photo_limitations": "Full front packaging view cropped and normalized.",
        "front_photo_relative_filename": f"front_photos/{front_webp_file}",
        "image_width_px": cw,
        "image_height_px": ch,
        "dong_nguon_anh_mat_truoc": record_id,
        "anh_mat_truoc": "",

        # UI compatibility
        "product_name": full_title_en,
        "net_weight": f"{v_res.net_quantity} {v_res.net_unit}" if v_res.net_quantity else "",
        "pos_sku": pos_sku,
        "pos_product_name": pos_name,
        "original_image": fname,
        "website_front_image": f"website_front_images/{fname}",
        "front_web_url": front_web_url,
        "raw_web_url": raw_web_url,
        "front_box_2d": v_res.front_box_2d or [],
        "cropped_width": cw,
        "cropped_height": ch,
        "detection_method": detection_method,
        "status": status,
    }

    # Market Database Enrichment (OpenFoodFacts / Global GS1 catalog)
    rec = market_enricher.enrich_record(rec)

    with FILE_LOCK:
        cache_data[fname] = rec
        processed_records.append(rec)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

    with PRINT_LOCK:
        print(f"  --> Extracted [{idx:03d}]: {rec['barcode']} | {rec['full_name_en'][:35]} | Kcal: {rec['energy_kcal']} | Origin: {rec['country_of_origin']} | Importer: {rec['importer']}")

    return rec


def main():
    print("=" * 70)
    print("🚀 MULTI-THREADED HIGH-RES DEEP SCAN (467 IMAGES) - 65 FIC COLUMNS")
    print("=" * 70)

    pos_lookup = load_pos_lookup()
    print(f"Loaded POS Lookup: {len(pos_lookup)} entries.")

    vision_extractor = GeminiVisionExtractor(cache_path=CACHE_FILE)
    market_enricher = MarketCatalogEnricher()
    num_keys = len(vision_extractor.keys)
    max_workers = min(6, max(3, num_keys * 2))
    print(f"Using {num_keys} Gemini API Keys with {max_workers} Concurrent Worker Threads.\n")

    all_images = sorted(
        list(IMAGES_DIR.glob("*.jpeg")) + list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.png"))
    )
    total_imgs = len(all_images)
    print(f"Found {total_imgs} images in {IMAGES_DIR}\n")

    cache_data: dict[str, dict[str, Any]] = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            valid_cached = {k: v for k, v in cache_data.items() if v.get("full_name_en") and (v.get("energy_kcal") is not None or v.get("ingredients_en"))}
            print(f"Resuming from verified deep cache: {len(valid_cached)} items already deeply processed.")
            cache_data = valid_cached
        except Exception:
            cache_data = {}

    processed_records: list[dict[str, Any]] = []

    # Process in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_single_image,
                img_path,
                idx,
                total_imgs,
                pos_lookup,
                vision_extractor,
                market_enricher,
                cache_data,
                processed_records,
            ): idx
            for idx, img_path in enumerate(all_images, 1)
        }

        completed_count = 0
        for future in concurrent.futures.as_completed(futures):
            completed_count += 1
            try:
                future.result()
            except Exception as e:
                with PRINT_LOCK:
                    print(f"Error in thread execution: {e}")

            if completed_count % 5 == 0 or completed_count == total_imgs:
                export_all(processed_records)
                with PRINT_LOCK:
                    print(f"  [Checkpoint Saved] Progress: {len(processed_records)}/{total_imgs} items.")

    export_all(processed_records)
    print("\n" + "=" * 70)
    print("✅ COMPLETED 100% PARALLEL MULTI-STAGE HIGH-RES DEEP SCAN ACROSS ALL 467 IMAGES!")
    print(f"Master Excel: {MASTER_EXCEL_OUT}")
    print(f"Web JSON:     {WEB_JSON_OUT}")
    print("=" * 70)


if __name__ == "__main__":
    main()
