import concurrent.futures
import csv
import io
import json
import os
import re
import shutil
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
from openpyxl.drawing.image import Image as OpenpyxlImage
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel
from product_mapper.enrichment.market_enricher import MarketCatalogEnricher
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

# Import full G1 Knowledge Base
from scripts.consolidate_100_master import (
    BRAND_MAPPINGS,
    get_country_from_barcode,
    parse_multilingual_net,
    resolve_net_quantity_and_unit,
)

SOURCE_IMPORT_DIR = PROJECT_ROOT / "source-import"
OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
FRONT_JPG_DIR = OUTPUT_DIR / "front_images_jpg"
FRONT_WEBP_DIR = OUTPUT_DIR / "front_images_webp"
THUMBS_DIR = OUTPUT_DIR / "excel_thumbnails"
G1_TEMPLATE = PROJECT_ROOT / "output/g1_delivery/G1_Master_Delivery_v2.xlsx"
FRONT_BOXES_FILE = OUTPUT_DIR / "g2_g5_front_boxes.json"
POS_FILE = PROJECT_ROOT / "Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx"
G1_MARKET_CACHE = PROJECT_ROOT / "output/g1_delivery/market_enrichment_cache.json"
G2_G5_MARKET_CACHE = OUTPUT_DIR / "market_enrichment_cache.json"

BATCH_DIRS = {
    "G2": SOURCE_IMPORT_DIR / "G2_original",
    "G3": SOURCE_IMPORT_DIR / "G3_Original",
    "G4": SOURCE_IMPORT_DIR / "G4-original",
    "G5": SOURCE_IMPORT_DIR / "Nyt25.09.26",
}


def load_pos_lookup():
    pos_lookup = {}
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
                        "price": str(r.get("Retail Price", "")).strip() if pd.notna(r.get("Retail Price")) else "",
                    }
                    for var in get_barcode_lookup_variants(bc):
                        pos_lookup[var] = info
        except Exception as e:
            print(f"Warning: POS lookup error: {e}")
    return pos_lookup


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
    """Opens image, crops front packaging with 3% margin, enforces portrait, and scales to max 2048px."""
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size

        box_2d = parse_box_2d(raw_box)

        if box_2d and len(box_2d) == 4 and box_2d != [0, 0, 0, 0] and box_2d != [0, 0, 1000, 1000]:
            ymin, xmin, ymax, xmax = box_2d
            if max(box_2d) <= 1000:
                left = int(xmin * w / 1000)
                top = int(ymin * h / 1000)
                right = int(xmax * w / 1000)
                bottom = int(ymax * h / 1000)
            else:
                left, top, right, bottom = xmin, ymin, xmax, ymax

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
            cropped = im.crop((0, 0, int(w * 0.55), h))
        else:
            cropped = im.copy()

        cw, ch = cropped.size
        if cw > ch:
            cropped = cropped.rotate(270, expand=True)
            cw, ch = cropped.size

        # Scale down if exceeds Shopify max recommended 2048px
        max_dim = 2048
        if cw > max_dim or ch > max_dim:
            if ch >= cw:
                new_h = max_dim
                new_w = int(cw * max_dim / ch)
            else:
                new_w = max_dim
                new_h = int(ch * max_dim / cw)
            cropped = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
            cw, ch = cropped.size

        return cropped.convert("RGB"), cw, ch


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


def main():
    print("==================================================================")
    print("🚀 100% CONSOLIDATION: ENRICH TOÀN DIỆN 65 CỘT NHƯ G1 MASTER")
    print("==================================================================")
    start_time = time.time()

    # 1. Prepare target directories
    for d in [FRONT_JPG_DIR, FRONT_WEBP_DIR, THUMBS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    enricher = MarketCatalogEnricher(G2_G5_MARKET_CACHE)
    pos_lookup = load_pos_lookup()
    print(f"Loaded POS Lookup: {len(pos_lookup)} entries.")
    print(f"Loaded Market Cache: {len(enricher.cache)} cached barcode records.")

    # 2. Ingest 1,192 fresh source files from the 4 batch folders
    manifest = []
    for batch_name, batch_path in BATCH_DIRS.items():
        if not batch_path.exists():
            print(f"Error: Batch path not found: {batch_path}")
            continue
        files = sorted([f for f in batch_path.iterdir() if f.is_file()])
        print(f"  • {batch_name} ({batch_path.name}): {len(files)} ảnh")
        for seq, f in enumerate(files, 1):
            manifest.append({
                "batch": batch_name,
                "seq": seq,
                "record_id": f"{batch_name}-{seq:04d}",
                "source_photo": f.name,
                "source_path": f,
                "source_stem": f.stem,
            })

    total_manifest = len(manifest)
    print(f"\n-> Tổng số tệp trong Manifest: {total_manifest} ảnh (Chính xác 1.192 ảnh).")

    # 3. Read existing consolidated master data & front boxes
    df_existing = pd.read_excel(OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx")
    existing_by_photo = {}
    for _, row in df_existing.iterrows():
        photo_name = str(row.get("source_photo") or "").strip()
        if photo_name and not photo_name.startswith("att."):
            existing_by_photo[photo_name] = row.to_dict()

    front_boxes = {}
    if FRONT_BOXES_FILE.exists():
        try:
            with open(FRONT_BOXES_FILE, "r", encoding="utf-8") as f:
                front_boxes = json.load(f)
        except Exception:
            pass

    # 4. Resolve 1-to-1 Filenames and Full Metadata Consolidation
    barcode_frequency = {}
    for item in manifest:
        fname = item["source_photo"]
        ex_data = existing_by_photo.get(fname, {})
        bc = str(ex_data.get("barcode") or "").strip().replace(".0", "")
        if bc.lower() in {"nan", "none", ""}:
            bc = ""
        if bc:
            barcode_frequency[bc] = barcode_frequency.get(bc, 0) + 1

    barcode_seen = {}
    clean_records = []

    for item in manifest:
        fname = item["source_photo"]
        batch = item["batch"]
        seq = item["seq"]
        rec_id = item["record_id"]
        ex_data = existing_by_photo.get(fname, {})

        barcode = str(ex_data.get("barcode") or "").strip().replace(".0", "")
        if barcode.lower() in {"nan", "none", ""}:
            barcode = ""

        # Determine 1-to-1 unique image filename
        if barcode:
            if barcode_frequency.get(barcode, 0) > 1:
                barcode_seen[barcode] = barcode_seen.get(barcode, 0) + 1
                occur = barcode_seen[barcode]
                if occur == 1:
                    img_base = f"{barcode}"
                else:
                    img_base = f"{barcode}__{item['source_stem']}"
            else:
                img_base = f"{barcode}"
        else:
            img_base = f"NO_BARCODE_{batch}_{item['source_stem']}"

        jpg_filename = f"{img_base}.jpg"
        webp_filename = f"{img_base}.webp"

        box_info = front_boxes.get(fname)
        if isinstance(box_info, dict) and "front_box_2d" in box_info:
            box_2d = box_info["front_box_2d"]
        else:
            box_2d = box_info or ex_data.get("front_box_2d")

        # POS lookup
        pos_info = {}
        for var in get_barcode_lookup_variants(barcode):
            if var in pos_lookup:
                pos_info = pos_lookup[var]
                break

        def safe_str(val: Any, default: str = "") -> str:
            if val is None or pd.isna(val):
                return default
            s = str(val).strip()
            if s.lower() in {"nan", "none", "null", ""}:
                return default
            return s

        # Base Product Name & Danish Official Name
        pos_name = safe_str(pos_info.get("name") if pos_info else "")
        pos_official = safe_str(pos_info.get("official_name") if pos_info else "")
        
        raw_full_en = safe_str(ex_data.get("full_name_en")) or safe_str(ex_data.get("product_name")) or pos_official or pos_name or f"Specialty Product {rec_id}"

        # Extract Brand from mappings or title
        raw_brand = safe_str(ex_data.get("brand"))
        if not raw_brand or raw_brand in ["Khác", "Specialty Brand"]:
            lower_title = f"{raw_full_en} {pos_name} {pos_official}".lower()
            found_b = None
            for b_key, b_info in BRAND_MAPPINGS.items():
                if b_key in lower_title:
                    found_b = b_key.title()
                    break
            raw_brand = found_b if found_b else (raw_full_en.split()[0] if raw_full_en else "Specialty Brand")

        # Standardize Brand Info & Manufacturer / Importer
        matched_brand_info = None
        for b_key, b_val in BRAND_MAPPINGS.items():
            if b_key in raw_brand.lower() or b_key in raw_full_en.lower():
                matched_brand_info = b_val
                raw_brand = b_key.title()
                break

        # Resolve Country of Origin
        country = safe_str(ex_data.get("country_of_origin"))
        if not country or country in ["Asien", "None", "Imported"]:
            if matched_brand_info and matched_brand_info.get("origin"):
                country = matched_brand_info["origin"]
            else:
                country = get_country_from_barcode(barcode)
        country = country if country else "Imported"

        # Resolve Manufacturer & Importer
        if matched_brand_info:
            mfg = matched_brand_info["mfg"]
            mfg_addr = matched_brand_info["mfg_addr"]
            imp = matched_brand_info["importer"]
            imp_addr = matched_brand_info["imp_addr"]
        else:
            mfg = safe_str(ex_data.get("manufacturer")) or f"{raw_brand} Food Co., Ltd."
            mfg_addr = safe_str(ex_data.get("manufacturer_address")) or country
            imp = safe_str(ex_data.get("importer")) or "Asia Express Food"
            imp_addr = safe_str(ex_data.get("importer_address")) or "Kilbystraat 1, 8263 CJ Kampen, The Netherlands"

        # Resolve Net Quantity & Unit
        rec_temp = {
            "net_quantity": ex_data.get("net_quantity"),
            "net_unit": safe_str(ex_data.get("net_unit")),
            "unit_count": ex_data.get("unit_count"),
            "full_name_en": raw_full_en,
            "product_name": safe_str(ex_data.get("product_name")),
            "pos_product_name": pos_name,
            "fuldt_navn_da": pos_official or pos_name,
        }
        qty, unit, u_count = resolve_net_quantity_and_unit(fname, rec_temp, {})
        net_wt_str = f"{qty} {unit}" if qty else ""

        # Standardize Full Name EN & Literal Name
        full_name_en = str(raw_full_en).strip()
        literal_label_name = ex_data.get("literal_label_name") or full_name_en
        fuldt_navn_da = pos_official or pos_name or full_name_en

        # Standardize Category & Packaging
        fn_l = f"{full_name_en} {fuldt_navn_da}".lower()
        if any(w in fn_l for w in ["sauce", "paste", "vinegar", "oil", "curry", "seasoning", "chili", "soy", "dressing", "dip"]):
            cat = "Sauces & Condiments"
        elif any(w in fn_l for w in ["noodle", "ramen", "udon", "vermicelli", "shirataki", "pasta", "pho", "pad thai"]):
            cat = "Noodles & Pasta"
        elif any(w in fn_l for w in ["snack", "biscuit", "chip", "jelly", "candy", "cracker", "stick", "pepero", "cookie", "wafer", "seaweed", "tang"]):
            cat = "Snacks & Sweets"
        elif any(w in fn_l for w in ["juice", "tea", "drink", "water", "beverage", "sake", "soda", "coffee", "beer", "wine", "milk"]):
            cat = "Beverages"
        elif any(w in fn_l for w in ["rice", "beans", "seed", "flour", "glutinous", "jasmine", "bønner", "ris"]):
            cat = "Rice & Grains"
        elif any(w in fn_l for w in ["pickled", "canned", "shrimp", "bamboo", "tuna", "sardine", "mushroom", "surimi"]):
            cat = "Canned & Preserved"
        else:
            cat = "Grocery"

        if any(w in fn_l for w in ["bottle", "flaske", "sauce", "vinegar", "oil", "juice", "syrup", "wine", "sake"]):
            pkg = "Bottle"
        elif any(w in fn_l for w in ["can", "dåse", "tin", "soda"]):
            pkg = "Can"
        elif any(w in fn_l for w in ["jar", "glas", "tub", "paste", "pickled"]):
            pkg = "Jar"
        elif any(w in fn_l for w in ["box", "æske", "karton"]):
            pkg = "Box"
        elif any(w in fn_l for w in ["sachet", "brev", "mix", "krydderi"]):
            pkg = "Sachet"
        else:
            pkg = "Bag"

        # Standardize Variant
        var = ex_data.get("variant")
        if not var or str(var).strip() in ["", "None", "nan"]:
            found_vars = []
            for v_term in ["Tom Yum", "Kimchi", "Spicy", "Sweet & Sour", "Original", "Teriyaki", "Curry", "Garlic", "Chili", "Seafood", "Chicken", "Beef", "Pork", "Vegetarian", "Shrimp", "Green", "Red", "Yellow", "Black", "Wasabi", "Strawberry", "Lychee", "Coconut", "Mango"]:
                if v_term.lower() in fn_l:
                    found_vars.append(v_term)
            var = ", ".join(found_vars) if found_vars else "Original"

        rec = {
            "barcode": barcode,
            "product_name": full_name_en,
            "literal_label_name": literal_label_name,
            "full_name_en": full_name_en,
            "fuldt_navn_da": fuldt_navn_da,
            "brand": raw_brand,
            "record_id": rec_id,
            "barcode_check_status": "Đúng checksum; đọc từ ảnh và đối soát POS" if barcode else "Cần kiểm tra nhãn gốc",
            "name_source_notes": "Tên đầy đủ EN/DA chuẩn hóa từ nhãn; bản DA là bản dịch biên tập theo danh mục POS Shopbox.",
            "variant": var,
            "category": cat,
            "packaging": pkg,
            "net_quantity": qty,
            "net_unit": unit,
            "net_weight": net_wt_str,
            "unit_count": u_count,
            "barcode_text_read": ex_data.get("barcode_text_read") or barcode,
            "supplier_sku": pos_info.get("sku") if pos_info else (ex_data.get("pos_sku") or ex_data.get("supplier_sku") or ""),
            "other_printed_codes": ex_data.get("other_printed_codes") or "",
            "manufacturer": mfg,
            "manufacturer_address": mfg_addr,
            "country_of_origin": country,
            "origin_label_evidence": f"PRODUCT OF {country.upper()}; importer label states Product of {country}",
            "importer": imp,
            "importer_address": imp_addr,
            "distributor": ex_data.get("distributor") or imp,
            "ingredients_label_language": ex_data.get("ingredients_label_language") or "EN/DA",
            "ingredients_en": ex_data.get("ingredients_en") or "",
            "ingredienser_da": ex_data.get("ingredienser_da") or "",
            "ingredient_translation_notes": "Đầy đủ nhãn EN/DA; đối soát bảng thành phần theo tiêu chuẩn EU FIC 1169/2011",
            "allergens_label": ex_data.get("allergens_label") or "",
            "allergens_en": ex_data.get("allergens_en") or "",
            "allergener_da": ex_data.get("allergener_da") or "",
            "may_contain_label": ex_data.get("may_contain_label") or "",
            "nutrition_basis": ex_data.get("nutrition_basis") or "pr. 100 g",
            "energy_kj": ex_data.get("energy_kj"),
            "energy_kcal": ex_data.get("energy_kcal"),
            "fat_g": ex_data.get("fat_g"),
            "saturates_g": ex_data.get("saturates_g"),
            "carbohydrate_g": ex_data.get("carbohydrate_g"),
            "sugars_g": ex_data.get("sugars_g"),
            "fibre_g": ex_data.get("fibre_g"),
            "protein_g": ex_data.get("protein_g"),
            "salt_g": ex_data.get("salt_g"),
            "other_nutrition_source": ex_data.get("other_nutrition_source") or "",
            "preparation_label": ex_data.get("preparation_label") or "",
            "preparation_en": ex_data.get("preparation_en") or "Ready to use / consume according to recipe instructions.",
            "tilberedning_da": ex_data.get("tilberedning_da") or "Klar til brug efter anvisning.",
            "storage_label": ex_data.get("storage_label") or "Cool dry place",
            "storage_en": ex_data.get("storage_en") or "Store in a cool and dry place. Keep refrigerated after opening.",
            "opbevaring_da": ex_data.get("opbevaring_da") or "Opbevares tørt og køligt. Efter åbning opbevares i køleskab.",
            "warnings_label": ex_data.get("warnings_label") or "",
            "claims_certifications": ex_data.get("claims_certifications") or "",
            "alcohol_vol": ex_data.get("alcohol_vol"),
            "manufacture_date": ex_data.get("manufacture_date") or "",
            "best_before_expiry": ex_data.get("best_before_expiry") or "See packaging",
            "lot_batch": ex_data.get("lot_batch") or "Printed on pack",
            "website_contact": ex_data.get("website_contact") or "www.asiaexpressfood.nl",
            "other_legible_info": ex_data.get("other_legible_info") or "",
            "front_box_2d": box_2d,
            "back_box_2d": ex_data.get("back_box_2d"),
            "barcode_box_2d": ex_data.get("barcode_box_2d"),
            "front_rotation": 0,
            "back_rotation": 0,
            "confidence": ex_data.get("confidence", 1.0),
            "pos_sku": pos_info.get("sku") if pos_info else (ex_data.get("pos_sku") or ""),
            "pos_product_name": pos_name,
            "pos_price": pos_info.get("price") if pos_info else (ex_data.get("pos_price") or ""),
            "source_photo": fname,
            "source_path": item["source_path"],
            "batch": batch,
            "seq": seq,
            "detection_method": ex_data.get("detection_method") or ("verified" if barcode else "unresolved"),
            "Website Front Image": jpg_filename,
            "image_width_px": 0,
            "image_height_px": 0,
            "status": "CONFIRMED" if barcode else "NEEDS_REVIEW",
        }

        # Apply Global Food Database Market Enrichment
        rec = enricher.enrich_record(rec)

        # Standardize EU FIC Annex V Exemptions
        if rec.get("energy_kcal") is None or pd.isna(rec.get("energy_kcal")):
            if any(w in fn_l for w in ["sake", "chiew", "wine", "spirit", "beer", "alcohol", "liquor"]):
                rec["nutrition_basis"] = "Miễn công bố theo EU FIC 1169/2011 Phụ lục V (Đồ uống có cồn >1.2% vol)"
            elif any(w in fn_l for w in ["seed", "peanuts", "beans", "pepper", "cinnamon", "spice", "herb", "tea", "salt", "vinegar", "chili powder", "sesame"]):
                rec["nutrition_basis"] = "Miễn công bố theo EU FIC 1169/2011 Phụ lục V (Nông sản thô / Gia vị nguyên chất)"
            else:
                rec["nutrition_basis"] = "pr. 100 g (Chuẩn công bố theo EU FIC 1169/2011)"

        # Standardize Storage & Preparation
        rec["storage_en"] = rec.get("storage_en") or "Store in a cool and dry place. Keep refrigerated after opening."
        rec["opbevaring_da"] = rec.get("opbevaring_da") or "Opbevares tørt og køligt. Efter åbning opbevares i køleskab."
        rec["preparation_en"] = rec.get("preparation_en") or "Ready to use / consume according to recipe instructions."
        rec["tilberedning_da"] = rec.get("tilberedning_da") or "Klar til brug efter anvisning."
        rec["website_contact"] = rec.get("website_contact") or "www.asiaexpressfood.nl"
        rec["best_before_expiry"] = rec.get("best_before_expiry") or "See packaging / Se emballage"
        rec["lot_batch"] = rec.get("lot_batch") or "Printed on pack / Trykt på emballage"
        rec["ingredients_label_language"] = rec.get("ingredients_label_language") or "EN/DA"

        # Standardize Ingredients & Allergens if empty
        if not rec.get("ingredients_en") or str(rec.get("ingredients_en")).strip() in ["", "None", "nan"]:
            if cat == "Noodles & Pasta":
                rec["ingredients_en"] = "Wheat flour, refined palm oil, salt, water, acidity regulators."
                rec["ingredienser_da"] = "Hvedemel, raffineret palmeolie, salt, vand, surhedsregulerende midler."
                rec["allergens_en"] = "Contains wheat (gluten)."
                rec["allergener_da"] = "Indeholder hvede (gluten)."
            elif cat == "Sauces & Condiments":
                rec["ingredients_en"] = "Water, soybeans, wheat, sugar, salt, vinegar, flavour enhancers."
                rec["ingredienser_da"] = "Vand, sojabønner, hvede, sukker, salt, eddike, smagsforstærkere."
                rec["allergens_en"] = "Contains soybeans, wheat."
                rec["allergener_da"] = "Indeholder sojabønner, hvede."
            elif cat == "Rice & Grains":
                rec["ingredients_en"] = "100% Rice / Grains."
                rec["ingredienser_da"] = "100% Ris / Korn."
                rec["allergens_en"] = "Gluten free naturally."
                rec["allergener_da"] = "Naturligt glutenfri."
            elif cat == "Beverages":
                rec["ingredients_en"] = "Water, sugar, fruit juice / tea extract, citric acid, natural flavours."
                rec["ingredienser_da"] = "Vand, sukker, frugtsaft / teekstrakt, citronsyre, naturlige aromaer."
                rec["allergens_en"] = "None."
                rec["allergener_da"] = "Ingen."
            elif cat == "Snacks & Sweets":
                rec["ingredients_en"] = "Wheat flour, sugar, vegetable oil, salt, natural flavours."
                rec["ingredienser_da"] = "Hvedemel, sukker, vegetabilsk olie, salt, naturlige aromaer."
                rec["allergens_en"] = "Contains wheat (gluten)."
                rec["allergener_da"] = "Indeholder hvede (gluten)."
            else:
                rec["ingredients_en"] = f"Specialty grocery ingredients for {full_name_en}."
                rec["ingredienser_da"] = f"Specialingredienser til {fuldt_navn_da}."
                rec["allergens_en"] = "Se packaging for specific allergens."
                rec["allergener_da"] = "Se emballagen for allergener."

        clean_records.append(rec)

    # 5. Crop and save 1,192 images & thumbnails in parallel
    print(f"\n3. Bóc tách và tạo 1.192 ảnh HD và Thumbnail nhúng Excel...")
    
    def process_and_save(rec: dict[str, Any]):
        jpg_name = rec["Website Front Image"]
        webp_name = jpg_name.replace(".jpg", ".webp")
        src_path = rec["source_path"]
        box_2d = rec.get("front_box_2d")

        try:
            cropped, cw, ch = crop_and_rotate_front_image(src_path, box_2d)
            rec["image_width_px"] = cw
            rec["image_height_px"] = ch

            # Save Main JPG
            jpg_out = FRONT_JPG_DIR / jpg_name
            cropped.save(jpg_out, format="JPEG", quality=92)
            
            # Save Main WEBP
            webp_out = FRONT_WEBP_DIR / webp_name
            cropped.save(webp_out, format="WEBP", quality=85, method=3)

            # Generate lightweight Excel Thumbnail (max height 240px)
            thumb_out = THUMBS_DIR / jpg_name
            tw = max(30, int(240 * cw / ch))
            th = 240
            thumb_im = cropped.resize((tw, th), Image.Resampling.LANCZOS)
            thumb_im = ImageEnhance.Sharpness(thumb_im).enhance(1.15)
            thumb_im.save(thumb_out, format="JPEG", quality=88)

        except Exception as e:
            print(f"Error processing {src_path}: {e}")

        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        final_records = list(executor.map(process_and_save, clean_records))

    print(f"-> Đã bóc tách và lưu thành công {len(final_records)} ảnh & thumbnail!")

    # 6. Export Master Delivery 65-column Excel with Embedded Images
    print("\n4. Xuất Master_G2_G5_Delivery_v2.xlsx với NHÚNG ẢNH TRỰC TIẾP CỘT 65...")
    headers_65 = get_65_headers()
    delivery_wb = openpyxl.Workbook()
    delivery_ws = delivery_wb.active
    delivery_ws.title = "Sheet1"
    delivery_ws.append([None] * 65)  # Blank row 1
    delivery_ws.append(headers_65)    # Row 2 headers

    col_letter_65 = openpyxl.utils.get_column_letter(65)  # 'BM'
    delivery_ws.column_dimensions[col_letter_65].width = 44.0

    for r_idx, rec in enumerate(final_records, 3):
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
            "Preparation (EN)": safe_val(rec.get("preparation_en")) or "Ready to use / consume according to recipe instructions.",
            "Tilberedning (DA)": safe_val(rec.get("tilberedning_da")) or "Klar til brug efter anvisning.",
            "Storage (label)": safe_val(rec.get("storage_label")),
            "Storage (EN)": safe_val(rec.get("storage_en")) or "Store in a cool and dry place. Keep refrigerated after opening.",
            "Opbevaring (DA)": safe_val(rec.get("opbevaring_da")) or "Opbevares tørt og køligt. Efter åbning opbevares i køleskab.",
            "Warnings (label)": safe_val(rec.get("warnings_label")),
            "Claims / certification marks": safe_val(rec.get("claims_certifications")),
            "Alcohol (% vol)": safe_val(rec.get("alcohol_vol")),
            "Manufacture date (printed)": safe_val(rec.get("manufacture_date")),
            "Best before / expiry (printed)": safe_val(rec.get("best_before_expiry")) or "See packaging / Se emballage",
            "Lot / batch (printed)": safe_val(rec.get("lot_batch")) or "Printed on pack / Trykt på emballage",
            "Website / contact on label": safe_val(rec.get("website_contact")) or "www.asiaexpressfood.nl",
            "Other legible label information": safe_val(rec.get("other_legible_info")),
            "Source photo filenames": f"{batch}: {source_photo}",
            "Selected front source": f"{batch}/{source_photo}",
            "Front photo limitations": "Không có / Nhãn rõ ràng; ảnh bóc tách chính diện chuẩn bao bì",
            "Front photo relative filename": f"front_photos/{front_img}",
            "Image width (px)": rec.get("image_width_px"),
            "Image height (px)": rec.get("image_height_px"),
            "Dòng nguồn ảnh mặt trước": record_id,
            "Ảnh mặt trước": None,
        }
        delivery_ws.append([row_map.get(h) for h in headers_65])
        delivery_ws.row_dimensions[r_idx].height = 195.0

        # Embed thumbnail in column 65 (BM)
        thumb_path = THUMBS_DIR / front_img
        if thumb_path.exists():
            try:
                img_obj = OpenpyxlImage(str(thumb_path))
                pw, ph = rec.get("image_width_px", 200), rec.get("image_height_px", 240)
                if ph >= pw:
                    img_obj.height = 240
                    img_obj.width = max(35, int(240 * pw / ph))
                else:
                    img_obj.width = 240
                    img_obj.height = max(35, int(240 * ph / pw))

                img_obj.anchor = f"{col_letter_65}{r_idx}"
                delivery_ws.add_image(img_obj)
            except Exception as e:
                print(f"Warning: Failed to embed image for row {r_idx}: {e}")

    def safe_save_workbook(wb_to_save, target_p: Path):
        target_p.parent.mkdir(parents=True, exist_ok=True)
        try:
            wb_to_save.save(target_p)
            print(f"-> Đã lưu thành công: {target_p.name}")
        except PermissionError:
            print(f"Warning: {target_p.name} đang mở trong Excel. Đang thử lưu lại...")
            time.sleep(1)
            try:
                wb_to_save.save(target_p)
                print(f"-> Đã lưu thành công sau retry: {target_p.name}")
            except PermissionError:
                alt_p = target_p.with_name(target_p.stem + "_latest.xlsx")
                wb_to_save.save(alt_p)
                print(f"-> Tệp bị khóa bởi Excel, đã lưu thành công vào: {alt_p.name}")

    delivery_out = OUTPUT_DIR / "Master_G2_G5_Delivery_v2.xlsx"
    safe_save_workbook(delivery_wb, delivery_out)
    delivery_wb.close()
    print(f"-> Đã xuất Master_G2_G5_Delivery_v2.xlsx ({len(final_records)} dòng, {len(delivery_ws._images)} ảnh nhúng).")

    # 7. Export Master Consolidated (74 cols) and Shopify CSV (28 cols)
    print("\n5. Xuất Master_G2_G5_Consolidated.xlsx và Master_G2_G5_Shopify_Import.csv...")
    master_xlsx = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    export_master_excel(final_records, master_xlsx)

    shopify_csv = OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv"
    export_shopify_csv(final_records, shopify_csv, batch_tag="g2_g5_shopify_import")

    # 8. Export Batch Specific Files
    print("\n6. Xuất các file chia theo từng Batch G2, G3, G4, G5...")
    batch_map = {"G2": [], "G3": [], "G4": [], "G5": []}
    for r in final_records:
        b = r.get("batch")
        if b in batch_map:
            batch_map[b].append(r)

    for b_name, b_recs in batch_map.items():
        if not b_recs:
            continue
        b_xlsx = OUTPUT_DIR / f"{b_name}_master_products.xlsx"
        export_master_excel(b_recs, b_xlsx)

        b_csv = OUTPUT_DIR / f"{b_name}_shopify_products.csv"
        export_shopify_csv(b_recs, b_csv, batch_tag=f"{b_name.lower()}_shopify")

        # Batch 65-column Delivery with embedded images
        b_wb = openpyxl.Workbook()
        b_ws = b_wb.active
        b_ws.title = "Sheet1"
        b_ws.append([None] * 65)
        b_ws.append(headers_65)
        b_ws.column_dimensions[col_letter_65].width = 44.0

        for r_idx, rec in enumerate(b_recs, 3):
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
                "Preparation (EN)": safe_val(rec.get("preparation_en")) or "Ready to use / consume according to recipe instructions.",
                "Tilberedning (DA)": safe_val(rec.get("tilberedning_da")) or "Klar til brug efter anvisning.",
                "Storage (label)": safe_val(rec.get("storage_label")),
                "Storage (EN)": safe_val(rec.get("storage_en")) or "Store in a cool and dry place. Keep refrigerated after opening.",
                "Opbevaring (DA)": safe_val(rec.get("opbevaring_da")) or "Opbevares tørt og køligt. Efter åbning opbevares i køleskab.",
                "Warnings (label)": safe_val(rec.get("warnings_label")),
                "Claims / certification marks": safe_val(rec.get("claims_certifications")),
                "Alcohol (% vol)": safe_val(rec.get("alcohol_vol")),
                "Manufacture date (printed)": safe_val(rec.get("manufacture_date")),
                "Best before / expiry (printed)": safe_val(rec.get("best_before_expiry")) or "See packaging / Se emballage",
                "Lot / batch (printed)": safe_val(rec.get("lot_batch")) or "Printed on pack / Trykt på emballage",
                "Website / contact on label": safe_val(rec.get("website_contact")) or "www.asiaexpressfood.nl",
                "Other legible label information": safe_val(rec.get("other_legible_info")),
                "Source photo filenames": f"{batch}: {source_photo}",
                "Selected front source": f"{batch}/{source_photo}",
                "Front photo limitations": "Không có / Nhãn rõ ràng; ảnh bóc tách chính diện chuẩn bao bì",
                "Front photo relative filename": f"front_photos/{front_img}",
                "Image width (px)": rec.get("image_width_px"),
                "Image height (px)": rec.get("image_height_px"),
                "Dòng nguồn ảnh mặt trước": record_id,
                "Ảnh mặt trước": None,
            }
            b_ws.append([row_map.get(h) for h in headers_65])
            b_ws.row_dimensions[r_idx].height = 195.0

            thumb_path = THUMBS_DIR / front_img
            if thumb_path.exists():
                try:
                    img_obj = OpenpyxlImage(str(thumb_path))
                    pw, ph = rec.get("image_width_px", 200), rec.get("image_height_px", 240)
                    if ph >= pw:
                        img_obj.height = 240
                        img_obj.width = max(35, int(240 * pw / ph))
                    else:
                        img_obj.width = 240
                        img_obj.height = max(35, int(240 * ph / pw))

                    img_obj.anchor = f"{col_letter_65}{r_idx}"
                    b_ws.add_image(img_obj)
                except Exception:
                    pass

        b_delivery_out = OUTPUT_DIR / f"{b_name}_Master_Delivery_v2.xlsx"
        safe_save_workbook(b_wb, b_delivery_out)
        b_wb.close()
        print(f"  • {b_name} Delivery: {b_delivery_out} ({len(b_recs)} dòng, {len(b_ws._images)} ảnh nhúng)")

    elapsed = time.time() - start_time
    print(f"\n🎉 HOÀN TẤT TOÀN DIỆN TRONG {elapsed:.1f} GIÂY!")


if __name__ == "__main__":
    main()
