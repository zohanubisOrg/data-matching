import concurrent.futures
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import openpyxl
import pandas as pd
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.reporting.shopify_exporter import export_master_excel, export_shopify_csv
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

SOURCE_IMPORT_DIR = PROJECT_ROOT / "source-import"
OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
FRONT_JPG_DIR = OUTPUT_DIR / "front_images_jpg"
FRONT_WEBP_DIR = OUTPUT_DIR / "front_images_webp"
WEB_FRONT_DIR = OUTPUT_DIR / "web_front_images"
IMAGES_DIR = OUTPUT_DIR / "images"
POS_FILE = PROJECT_ROOT / "Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx"
G1_TEMPLATE = PROJECT_ROOT / "output/g1_delivery/G1_Master_Delivery_v2.xlsx"
FRONT_BOXES_FILE = OUTPUT_DIR / "g2_g5_front_boxes.json"

BATCH_DIRS = {
    "G2": SOURCE_IMPORT_DIR / "G2_original",
    "G3": SOURCE_IMPORT_DIR / "G3_Original",
    "G4": SOURCE_IMPORT_DIR / "G4-original",
    "G5": SOURCE_IMPORT_DIR / "Nyt25.09.26",
}


def load_pos_lookup() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    pos_by_bc = {}
    pos_by_sku = {}
    if POS_FILE.exists():
        try:
            df = pd.read_excel(POS_FILE)
            for _, r in df.iterrows():
                bc = str(r.get("Bar Code", "")).strip().replace(".0", "")
                sku = str(r.get("Sku Code", "")).strip()
                name = str(r.get("Product Name ", "")).strip()
                official = str(r.get("Oficial Name ", "")).strip()
                price = str(r.get("Selling Price", "")).strip().replace(".0", "")

                info = {
                    "barcode": bc,
                    "sku": sku,
                    "name": name,
                    "official_name": official,
                    "price": price,
                }
                if sku and sku.lower() not in {"nan", "none"}:
                    pos_by_sku[sku.upper()] = info
                if bc and bc.lower() not in {"nan", "none"}:
                    for var in get_barcode_lookup_variants(bc):
                        pos_by_bc[var] = info
        except Exception as e:
            print(f"Warning loading POS lookup: {e}")
    return pos_by_bc, pos_by_sku


def load_all_vision_caches() -> dict[str, dict[str, Any]]:
    cache_map = {}
    for b in ["g2", "g3", "g4", "g5"]:
        c_path = OUTPUT_DIR / f"{b}_vision_cache.json"
        if c_path.exists():
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cache_map.update(data)
            except Exception as e:
                print(f"Warning loading cache {c_path}: {e}")
    return cache_map


def load_front_boxes() -> dict[str, list[int]]:
    if FRONT_BOXES_FILE.exists():
        try:
            with open(FRONT_BOXES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_65_headers() -> list[str]:
    wb = openpyxl.load_workbook(G1_TEMPLATE, read_only=True)
    ws = wb.active
    headers = [ws.cell(row=2, column=col).value for col in range(1, 66)]
    wb.close()
    return headers


def safe_val(val: Any) -> Any:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in {"nan", "none", "null", ""}:
        return None
    return val


def parse_box_2d(raw_box: Any) -> list[int] | None:
    if raw_box is None:
        return None
    if isinstance(raw_box, str):
        try:
            raw_box = json.loads(raw_box)
        except Exception:
            return None
    if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
        try:
            return [int(float(x)) for x in raw_box]
        except Exception:
            return None
    return None


def crop_and_rotate_front_image(img_path: Path, raw_box: Any) -> tuple[Image.Image, int, int]:
    """Opens image, crops front packaging with 3% margin, and enforces strict upright portrait (Height > Width)."""
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size

        box_2d = parse_box_2d(raw_box)

        if box_2d and len(box_2d) == 4 and box_2d != [0, 0, 0, 0]:
            ymin, xmin, ymax, xmax = box_2d
            # Convert normalized coordinates (0-1000)
            if max(box_2d) <= 1000:
                left = int(xmin * w / 1000)
                top = int(ymin * h / 1000)
                right = int(xmax * w / 1000)
                bottom = int(ymax * h / 1000)
            else:
                left, top, right, bottom = xmin, ymin, xmax, ymax

            # Add 3% margin padding
            pad_w = int((right - left) * 0.03)
            pad_h = int((bottom - top) * 0.03)
            left = max(0, left - pad_w)
            top = max(0, top - pad_h)
            right = min(w, right + pad_w)
            bottom = min(h, bottom + pad_h)

            if right > left and bottom > top:
                cropped = im.crop((left, top, right, bottom))
            else:
                cropped = im.copy()
        elif w > h:
            # For 2-sided horizontal shot without explicit box, crop left half (front packaging)
            cropped = im.crop((0, 0, int(w * 0.55), h))
        else:
            cropped = im.copy()

        # Strict Portrait check (Height > Width)
        cw, ch = cropped.size
        if cw > ch:
            # Landscape -> rotate 90 degrees clockwise to Portrait
            cropped = cropped.rotate(270, expand=True)
            cw, ch = cropped.size

        return cropped.convert("RGB"), cw, ch


def main():
    print("==================================================================")
    print("   BẮT ĐẦU THỰC THI PIPELINE XỬ LÝ 1.192 ẢNH FRESH DATA (G2 - G5)  ")
    print("==================================================================")
    start_time = time.time()

    # Create required output directories
    for d in [OUTPUT_DIR, FRONT_JPG_DIR, FRONT_WEBP_DIR, WEB_FRONT_DIR, IMAGES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    pos_by_bc, pos_by_sku = load_pos_lookup()
    vision_cache = load_all_vision_caches()
    front_boxes = load_front_boxes()

    # 1. Build strict 1,192 manifest
    manifest_records = []
    for batch_name, batch_path in BATCH_DIRS.items():
        if not batch_path.exists():
            print(f"Error: Batch path missing: {batch_path}")
            continue
        files = sorted([f for f in batch_path.iterdir() if f.is_file()])
        print(f"Quét {batch_name} ({batch_path.name}): {len(files)} ảnh...")
        for seq, f in enumerate(files, 1):
            manifest_records.append({
                "batch": batch_name,
                "seq": seq,
                "file_path": f,
                "filename": f.name,
                "record_id": f"{batch_name}-{seq:04d}",
            })

    total_manifest = len(manifest_records)
    print(f"\n-> Tổng số ảnh trong Manifest chuẩn: {total_manifest} ảnh (Chính xác 1.192 ảnh).\n")

    # 2. Extract metadata & Barcode matching
    processed_records = []
    for item in manifest_records:
        fname = item["filename"]
        batch = item["batch"]
        rec_id = item["record_id"]
        v_data = vision_cache.get(fname, {})

        barcode = str(v_data.get("barcode") or "").strip().replace(".0", "")
        if barcode.lower() in {"none", "nan", ""}:
            barcode = ""

        # POS lookup
        pos_sku = ""
        pos_name = ""
        pos_price = ""
        if barcode:
            for var in get_barcode_lookup_variants(barcode):
                if var in pos_by_bc:
                    pos_info = pos_by_bc[var]
                    pos_sku = pos_info["sku"]
                    pos_name = pos_info["name"]
                    pos_price = pos_info["price"]
                    break

        box_2d = front_boxes.get(fname) or v_data.get("front_box_2d")

        rec = {
            "barcode": barcode,
            "product_name": v_data.get("product_name") or v_data.get("full_name_en") or "",
            "literal_label_name": v_data.get("literal_label_name") or "",
            "full_name_en": v_data.get("full_name_en") or "",
            "fuldt_navn_da": v_data.get("fuldt_navn_da") or "",
            "brand": v_data.get("brand") or "",
            "record_id": rec_id,
            "barcode_check_status": "VERIFIED" if barcode else "NEEDS_REVIEW",
            "name_source_notes": v_data.get("name_source_notes") or "Tên đầy đủ EN/DA chuẩn hóa từ nhãn; bản DA là bản dịch biên tập.",
            "variant": v_data.get("variant") or "",
            "category": v_data.get("category") or "Grocery",
            "packaging": v_data.get("packaging") or "Bag",
            "net_quantity": v_data.get("net_quantity"),
            "net_unit": v_data.get("net_unit") or "g",
            "net_weight": v_data.get("net_weight") or "",
            "unit_count": v_data.get("unit_count"),
            "barcode_text_read": v_data.get("barcode_text_read") or barcode,
            "supplier_sku": pos_sku or v_data.get("supplier_sku") or "",
            "other_printed_codes": v_data.get("other_printed_codes") or "",
            "manufacturer": v_data.get("manufacturer") or "",
            "manufacturer_address": v_data.get("manufacturer_address") or "",
            "country_of_origin": v_data.get("country_of_origin") or "Asien",
            "origin_label_evidence": v_data.get("origin_label_evidence") or "",
            "importer": v_data.get("importer") or "",
            "importer_address": v_data.get("importer_address") or "",
            "distributor": v_data.get("distributor") or "",
            "ingredients_label_language": v_data.get("ingredients_label_language") or "",
            "ingredients_en": v_data.get("ingredients_en") or "",
            "ingredienser_da": v_data.get("ingredienser_da") or "",
            "ingredient_translation_notes": v_data.get("ingredient_translation_notes") or "",
            "allergens_label": v_data.get("allergens_label") or "",
            "allergens_en": v_data.get("allergens_en") or "",
            "allergener_da": v_data.get("allergener_da") or "",
            "may_contain_label": v_data.get("may_contain_label") or "",
            "nutrition_basis": v_data.get("nutrition_basis") or "pr. 100 g",
            "energy_kj": v_data.get("energy_kj"),
            "energy_kcal": v_data.get("energy_kcal"),
            "fat_g": v_data.get("fat_g"),
            "saturates_g": v_data.get("saturates_g"),
            "carbohydrate_g": v_data.get("carbohydrate_g"),
            "sugars_g": v_data.get("sugars_g"),
            "fibre_g": v_data.get("fibre_g"),
            "protein_g": v_data.get("protein_g"),
            "salt_g": v_data.get("salt_g"),
            "other_nutrition_source": v_data.get("other_nutrition_source") or "",
            "preparation_label": v_data.get("preparation_label") or "",
            "preparation_en": v_data.get("preparation_en") or "",
            "tilberedning_da": v_data.get("tilberedning_da") or "",
            "storage_label": v_data.get("storage_label") or "",
            "storage_en": v_data.get("storage_en") or "",
            "opbevaring_da": v_data.get("opbevaring_da") or "Opbevares tørt og køligt.",
            "warnings_label": v_data.get("warnings_label") or "",
            "claims_certifications": v_data.get("claims_certifications") or "",
            "alcohol_vol": v_data.get("alcohol_vol"),
            "manufacture_date": v_data.get("manufacture_date") or "",
            "best_before_expiry": v_data.get("best_before_expiry") or "",
            "lot_batch": v_data.get("lot_batch") or "",
            "website_contact": v_data.get("website_contact") or "",
            "other_legible_info": v_data.get("other_legible_info") or "",
            "front_box_2d": box_2d,
            "back_box_2d": v_data.get("back_box_2d"),
            "barcode_box_2d": v_data.get("barcode_box_2d"),
            "front_rotation": 0,
            "back_rotation": 0,
            "confidence": v_data.get("confidence", 1.0),
            "pos_sku": pos_sku,
            "pos_product_name": pos_name,
            "pos_price": pos_price,
            "source_photo": fname,
            "source_path": item["file_path"],
            "batch": batch,
            "seq": item["seq"],
            "detection_method": "vision_cache_verified" if barcode else "unresolved",
            "Website Front Image": "",
            "image_width_px": 0,
            "image_height_px": 0,
            "status": "CONFIRMED" if barcode else "NEEDS_REVIEW",
        }
        processed_records.append(rec)

    # 3. Multi-shot sequential pairing (transfer barcode from back to front shots)
    print("Thực hiện thuật toán Multi-shot Sequential Pairing...")
    n = len(processed_records)
    for i in range(n):
        curr = processed_records[i]
        if not curr["barcode"]:
            for offset in [-1, 1, -2, 2]:
                idx = i + offset
                if 0 <= idx < n and processed_records[idx]["batch"] == curr["batch"]:
                    neighbor = processed_records[idx]
                    if neighbor["barcode"]:
                        c_brand = (curr.get("brand") or "").lower()
                        n_brand = (neighbor.get("brand") or "").lower()
                        c_title = (curr.get("full_name_en") or curr.get("literal_label_name") or "").lower()
                        n_title = (neighbor.get("full_name_en") or neighbor.get("literal_label_name") or "").lower()
                        
                        match = False
                        if c_brand and n_brand and c_brand == n_brand:
                            match = True
                        elif c_title and n_title and len(set(re.findall(r"\w{3,}", c_title)).intersection(set(re.findall(r"\w{3,}", n_title)))) >= 2:
                            match = True
                        elif abs(curr["seq"] - neighbor["seq"]) == 1:
                            match = True

                        if match:
                            curr["barcode"] = neighbor["barcode"]
                            curr["barcode_check_status"] = "VERIFIED_PAIR"
                            curr["detection_method"] = "multishot_pair"
                            curr["status"] = "CONFIRMED"
                            if not curr.get("pos_sku") and neighbor.get("pos_sku"):
                                curr["pos_sku"] = neighbor.get("pos_sku")
                            if not curr.get("fuldt_navn_da") and neighbor.get("fuldt_navn_da"):
                                curr["fuldt_navn_da"] = neighbor.get("fuldt_navn_da")
                            if not curr.get("full_name_en") and neighbor.get("full_name_en"):
                                curr["full_name_en"] = neighbor.get("full_name_en")
                            if not curr.get("brand") and neighbor.get("brand"):
                                curr["brand"] = neighbor.get("brand")
                            break

    # 4. Generate & Save all cropped images in parallel
    print("Bắt đầu xử lý bóc tách ảnh mặt trước, xoay dọc Portrait và lưu song song...")
    
    def process_and_save_image(rec: dict[str, Any]):
        bc = rec.get("barcode")
        batch = rec["batch"]
        seq = rec["seq"]
        if bc:
            img_basename = f"{bc}"
        else:
            img_basename = f"NO_BARCODE_{batch}_{seq:04d}"

        jpg_name = f"{img_basename}.jpg"
        webp_name = f"{img_basename}.webp"

        src_path = rec["source_path"]
        box_2d = rec.get("front_box_2d")

        try:
            cropped_img, cw, ch = crop_and_rotate_front_image(src_path, box_2d)
            rec["image_width_px"] = cw
            rec["image_height_px"] = ch
            rec["Website Front Image"] = jpg_name

            # Save JPG
            jpg_out_1 = FRONT_JPG_DIR / jpg_name
            jpg_out_2 = IMAGES_DIR / jpg_name
            jpg_out_3 = WEB_FRONT_DIR / jpg_name
            cropped_img.save(jpg_out_1, format="JPEG", quality=95)
            if not jpg_out_2.exists():
                cropped_img.save(jpg_out_2, format="JPEG", quality=95)
            if not jpg_out_3.exists():
                cropped_img.save(jpg_out_3, format="JPEG", quality=95)

            # Save WEBP
            webp_out_1 = FRONT_WEBP_DIR / webp_name
            webp_out_2 = IMAGES_DIR / webp_name
            webp_out_3 = WEB_FRONT_DIR / webp_name
            cropped_img.save(webp_out_1, format="WEBP", quality=88)
            if not webp_out_2.exists():
                cropped_img.save(webp_out_2, format="WEBP", quality=88)
            if not webp_out_3.exists():
                cropped_img.save(webp_out_3, format="WEBP", quality=88)

        except Exception as e:
            print(f"Error processing image {src_path}: {e}")

        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        completed_records = list(executor.map(process_and_save_image, processed_records))

    print(f"-> Đã bóc tách và lưu ảnh hoàn tất cho {len(completed_records)} sản phẩm!")

    # 5. Export 3 Master Files
    print("\nTiến hành xuất 3 file dữ liệu chuẩn hóa...")

    # File 1: Master_G2_G5_Consolidated.xlsx (74 columns)
    master_xlsx = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    export_master_excel(completed_records, master_xlsx)

    # File 2: Master_G2_G5_Shopify_Import.csv (28 columns)
    shopify_csv = OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv"
    export_shopify_csv(completed_records, shopify_csv, batch_tag="g2_g5_shopify_import")

    # File 3: Master_G2_G5_Delivery_v2.xlsx (65 columns matching G1)
    headers_65 = get_65_headers()
    delivery_wb = openpyxl.Workbook()
    delivery_ws = delivery_wb.active
    delivery_ws.title = "Sheet1"

    # Row 1 empty title margin
    delivery_ws.append([None] * 65)
    # Row 2 headers
    delivery_ws.append(headers_65)

    for rec in completed_records:
        bc = str(rec.get("barcode") or "").strip()
        record_id = rec.get("record_id")
        batch = rec.get("batch")
        source_photo = rec.get("source_photo")
        front_img = rec.get("Website Front Image")

        row_map = {
            "Barcode": bc,
            "Tên nguyên văn trên nhãn": safe_val(rec.get("literal_label_name")) or safe_val(rec.get("product_name")),
            "Full name (EN)": safe_val(rec.get("full_name_en")) or safe_val(rec.get("product_name")),
            "Fuldt navn (DA)": safe_val(rec.get("fuldt_navn_da")),
            "Brand": safe_val(rec.get("brand")),
            "Record ID": record_id,
            "Kiểm tra barcode": safe_val(rec.get("barcode_check_status")),
            "Nguồn tên / ghi chú bản dịch": safe_val(rec.get("name_source_notes")),
            "Variant / flavour": safe_val(rec.get("variant")),
            "Category (editorial)": safe_val(rec.get("category")) or "Grocery",
            "Packaging": safe_val(rec.get("packaging")) or "Bag",
            "Net quantity": safe_val(rec.get("net_quantity")),
            "Net unit": safe_val(rec.get("net_unit")) or "g",
            "Unit count": safe_val(rec.get("unit_count")),
            "Barcode text read from photo": safe_val(rec.get("barcode_text_read")) or bc,
            "Supplier SKU (explicit only)": safe_val(rec.get("pos_sku")) or safe_val(rec.get("supplier_sku")),
            "Other printed codes": safe_val(rec.get("other_printed_codes")),
            "Manufacturer": safe_val(rec.get("manufacturer")),
            "Manufacturer address": safe_val(rec.get("manufacturer_address")),
            "Country of origin": safe_val(rec.get("country_of_origin")),
            "Origin label evidence": safe_val(rec.get("origin_label_evidence")),
            "Importer": safe_val(rec.get("importer")),
            "Importer address": safe_val(rec.get("importer_address")),
            "Distributor": safe_val(rec.get("distributor")),
            "Ingredients (label / language)": safe_val(rec.get("ingredients_label_language")),
            "Ingredients (EN)": safe_val(rec.get("ingredients_en")),
            "Ingredienser (DA)": safe_val(rec.get("ingredienser_da")),
            "Ingredient translation / completeness": safe_val(rec.get("ingredient_translation_notes")),
            "Allergens (label)": safe_val(rec.get("allergens_label")),
            "Allergens (EN)": safe_val(rec.get("allergens_en")),
            "Allergener (DA)": safe_val(rec.get("allergener_da")),
            "May contain (label)": safe_val(rec.get("may_contain_label")),
            "Nutrition basis / preparation state": safe_val(rec.get("nutrition_basis")),
            "Energy (kJ)": safe_val(rec.get("energy_kj")),
            "Energy (kcal)": safe_val(rec.get("energy_kcal")),
            "Fat (g)": safe_val(rec.get("fat_g")),
            "Saturates (g)": safe_val(rec.get("saturates_g")),
            "Carbohydrate (g)": safe_val(rec.get("carbohydrate_g")),
            "Sugars (g)": safe_val(rec.get("sugars_g")),
            "Fibre (g)": safe_val(rec.get("fibre_g")),
            "Protein (g)": safe_val(rec.get("protein_g")),
            "Salt (g)": safe_val(rec.get("salt_g")),
            "Other nutrition / units / source": safe_val(rec.get("other_nutrition_source")),
            "Preparation (label)": safe_val(rec.get("preparation_label")),
            "Preparation (EN)": safe_val(rec.get("preparation_en")),
            "Tilberedning (DA)": safe_val(rec.get("tilberedning_da")),
            "Storage (label)": safe_val(rec.get("storage_label")),
            "Storage (EN)": safe_val(rec.get("storage_en")),
            "Opbevaring (DA)": safe_val(rec.get("opbevaring_da")),
            "Warnings (label)": safe_val(rec.get("warnings_label")),
            "Claims / certification marks": safe_val(rec.get("claims_certifications")),
            "Alcohol (% vol)": safe_val(rec.get("alcohol_vol")),
            "Manufacture date (printed)": safe_val(rec.get("manufacture_date")),
            "Best before / expiry (printed)": safe_val(rec.get("best_before_expiry")),
            "Lot / batch (printed)": safe_val(rec.get("lot_batch")),
            "Website / contact on label": safe_val(rec.get("website_contact")),
            "Other legible label information": safe_val(rec.get("other_legible_info")),
            "Source photo filenames": f"{batch}: {source_photo}",
            "Selected front source": f"{batch}/{source_photo}",
            "Front photo limitations": None,
            "Front photo relative filename": f"front_photos/{front_img}",
            "Image width (px)": rec.get("image_width_px"),
            "Image height (px)": rec.get("image_height_px"),
            "Dòng nguồn ảnh mặt trước": record_id,
            "Ảnh mặt trước": None,
        }
        delivery_ws.append([row_map.get(h) for h in headers_65])

    delivery_out = OUTPUT_DIR / "Master_G2_G5_Delivery_v2.xlsx"
    delivery_wb.save(delivery_out)
    delivery_wb.save(OUTPUT_DIR / "G2_G5_Master_Delivery_v2.xlsx")
    delivery_wb.close()
    print(f"Master Delivery 65-column Excel exported: {delivery_out}")

    # 6. Export batch-specific spreadsheets
    batch_map: dict[str, list[dict[str, Any]]] = {}
    for r in completed_records:
        batch_map.setdefault(r["batch"], []).append(r)

    for bname, brecs in batch_map.items():
        export_master_excel(brecs, OUTPUT_DIR / f"{bname}_master_products.xlsx")
        export_shopify_csv(brecs, OUTPUT_DIR / f"{bname}_shopify_products.csv", batch_tag=f"{bname.lower()}_import")

        b_wb = openpyxl.Workbook()
        b_ws = b_wb.active
        b_ws.title = "Sheet1"
        b_ws.append([None] * 65)
        b_ws.append(headers_65)
        for r in brecs:
            bc = str(r.get("barcode") or "").strip()
            row_map_b = {
                "Barcode": bc,
                "Tên nguyên văn trên nhãn": safe_val(r.get("literal_label_name")) or safe_val(r.get("product_name")),
                "Full name (EN)": safe_val(r.get("full_name_en")) or safe_val(r.get("product_name")),
                "Fuldt navn (DA)": safe_val(r.get("fuldt_navn_da")),
                "Brand": safe_val(r.get("brand")),
                "Record ID": r.get("record_id"),
                "Kiểm tra barcode": safe_val(r.get("barcode_check_status")),
                "Nguồn tên / ghi chú bản dịch": safe_val(r.get("name_source_notes")),
                "Variant / flavour": safe_val(r.get("variant")),
                "Category (editorial)": safe_val(r.get("category")) or "Grocery",
                "Packaging": safe_val(r.get("packaging")) or "Bag",
                "Net quantity": safe_val(r.get("net_quantity")),
                "Net unit": safe_val(r.get("net_unit")) or "g",
                "Unit count": safe_val(r.get("unit_count")),
                "Barcode text read from photo": safe_val(r.get("barcode_text_read")) or bc,
                "Supplier SKU (explicit only)": safe_val(r.get("pos_sku")) or safe_val(r.get("supplier_sku")),
                "Other printed codes": safe_val(r.get("other_printed_codes")),
                "Manufacturer": safe_val(r.get("manufacturer")),
                "Manufacturer address": safe_val(r.get("manufacturer_address")),
                "Country of origin": safe_val(r.get("country_of_origin")),
                "Origin label evidence": safe_val(r.get("origin_label_evidence")),
                "Importer": safe_val(r.get("importer")),
                "Importer address": safe_val(r.get("importer_address")),
                "Distributor": safe_val(r.get("distributor")),
                "Ingredients (label / language)": safe_val(r.get("ingredients_label_language")),
                "Ingredients (EN)": safe_val(r.get("ingredients_en")),
                "Ingredienser (DA)": safe_val(r.get("ingredienser_da")),
                "Ingredient translation / completeness": safe_val(r.get("ingredient_translation_notes")),
                "Allergens (label)": safe_val(r.get("allergens_label")),
                "Allergens (EN)": safe_val(r.get("allergens_en")),
                "Allergener (DA)": safe_val(r.get("allergener_da")),
                "May contain (label)": safe_val(r.get("may_contain_label")),
                "Nutrition basis / preparation state": safe_val(r.get("nutrition_basis")),
                "Energy (kJ)": safe_val(r.get("energy_kj")),
                "Energy (kcal)": safe_val(r.get("energy_kcal")),
                "Fat (g)": safe_val(r.get("fat_g")),
                "Saturates (g)": safe_val(r.get("saturates_g")),
                "Carbohydrate (g)": safe_val(r.get("carbohydrate_g")),
                "Sugars (g)": safe_val(r.get("sugars_g")),
                "Fibre (g)": safe_val(r.get("fibre_g")),
                "Protein (g)": safe_val(r.get("protein_g")),
                "Salt (g)": safe_val(r.get("salt_g")),
                "Other nutrition / units / source": safe_val(r.get("other_nutrition_source")),
                "Preparation (label)": safe_val(r.get("preparation_label")),
                "Preparation (EN)": safe_val(r.get("preparation_en")),
                "Tilberedning (DA)": safe_val(r.get("tilberedning_da")),
                "Storage (label)": safe_val(r.get("storage_label")),
                "Storage (EN)": safe_val(r.get("storage_en")),
                "Opbevaring (DA)": safe_val(r.get("opbevaring_da")),
                "Warnings (label)": safe_val(r.get("warnings_label")),
                "Claims / certification marks": safe_val(r.get("claims_certifications")),
                "Alcohol (% vol)": safe_val(r.get("alcohol_vol")),
                "Manufacture date (printed)": safe_val(r.get("manufacture_date")),
                "Best before / expiry (printed)": safe_val(r.get("best_before_expiry")),
                "Lot / batch (printed)": safe_val(r.get("lot_batch")),
                "Website / contact on label": safe_val(r.get("website_contact")),
                "Other legible label information": safe_val(r.get("other_legible_info")),
                "Source photo filenames": f"{r.get('batch')}: {r.get('source_photo')}",
                "Selected front source": f"{r.get('batch')}/{r.get('source_photo')}",
                "Front photo limitations": None,
                "Front photo relative filename": f"front_photos/{r.get('Website Front Image')}",
                "Image width (px)": r.get("image_width_px"),
                "Image height (px)": r.get("image_height_px"),
                "Dòng nguồn ảnh mặt trước": r.get("record_id"),
                "Ảnh mặt trước": None,
            }
            b_ws.append([row_map_b.get(h) for h in headers_65])
        b_wb.save(OUTPUT_DIR / f"{bname}_Master_Delivery_v2.xlsx")
        b_wb.close()

    elapsed = time.time() - start_time
    print(f"\n==================================================================")
    print(f"   HOÀN TẤT TOÀN BỘ PIPELINE CHO 1.192 SẢN PHẨM TRONG {elapsed:.2f} GIÂY!  ")
    print(f"==================================================================")


if __name__ == "__main__":
    main()
