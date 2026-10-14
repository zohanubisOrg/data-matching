import json, sys, os
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from src.product_mapper.vision.barcode_validator import get_barcode_lookup_variants

CUSTOMER_EXCEL = Path("customer-send-me.xlsx")
POS_FILE = Path("Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
OUTPUT_EXCEL = Path("output/g1_delivery/G1_Master_Delivery_v2.xlsx")
OUTPUT_JSON = Path("web/public/data/products.json")
FRONT_WEB_DIR = Path("web/public/products/front")
RAW_WEB_DIR = Path("web/public/products/raw")


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
                    }
                    for var in get_barcode_lookup_variants(bc):
                        pos_lookup[var] = info
        except Exception as e:
            print(f"Warning: POS lookup error: {e}")
    return pos_lookup


def sync_all():
    print("Reading customer-send-me.xlsx...")
    df_raw = pd.read_excel(CUSTOMER_EXCEL, header=1)
    pos_lookup = load_pos_lookup()

    products = []
    brands_set = set()
    confirmed_count = 0
    pos_matched_count = 0

    for idx, row in df_raw.iterrows():
        barcode = str(row.get("Barcode", "")).strip().replace(".0", "")
        if not barcode or barcode == "nan":
            barcode = f"NO_BARCODE_G1_{idx+1:04d}"

        raw_img_source = str(row.get("Selected front source", "")).strip()
        # e.g. "G1/IMG_0002.jpeg" or "G1: IMG_0002.jpeg"
        img_name = Path(raw_img_source.replace("G1:", "").replace("G1/", "").strip()).name
        if not img_name.endswith((".jpeg", ".jpg", ".png", ".webp")):
            img_name = f"IMG_{idx+1:04d}.jpeg"

        # Web URLs
        raw_stem = Path(img_name).stem
        front_web_url = f"/products/front/{barcode}.webp"
        raw_web_url = f"/products/raw/{raw_stem}.webp"

        # If front webp doesn't exist under barcode, look up if there's an image under raw_stem
        if not (Path("web/public") / front_web_url.lstrip("/")).exists():
            candidate = f"/products/front/{raw_stem}.webp"
            if (Path("web/public") / candidate.lstrip("/")).exists():
                front_web_url = candidate

        # POS lookup
        pos_info = {}
        for var in get_barcode_lookup_variants(barcode):
            if var in pos_lookup:
                pos_info = pos_lookup[var]
                break

        pos_sku = str(row.get("Supplier SKU (explicit only)", "")).strip() if pd.notna(row.get("Supplier SKU (explicit only)")) else ""
        if not pos_sku and pos_info:
            pos_sku = pos_info.get("sku", "")

        pos_name = pos_info.get("name", "") if pos_info else ""

        full_name_en = str(row.get("Full name (EN)", "")).strip() if pd.notna(row.get("Full name (EN)")) else ""
        literal_name = str(row.get("Tên nguyên văn trên nhãn", "")).strip() if pd.notna(row.get("Tên nguyên văn trên nhãn")) else ""
        brand = str(row.get("Brand", "")).strip() if pd.notna(row.get("Brand")) else ""
        if brand and brand != "nan":
            brands_set.add(brand)

        net_qty = row.get("Net quantity")
        net_quantity = float(net_qty) if pd.notna(net_qty) and isinstance(net_qty, (int, float)) else None
        net_unit = str(row.get("Net unit", "g")).strip() if pd.notna(row.get("Net unit")) else "g"
        net_weight_str = f"{net_quantity} {net_unit}" if net_quantity else ""

        def clean_val(val, as_float=False):
            if pd.isna(val) or val is None:
                return None if as_float else ""
            if as_float:
                try:
                    return float(val)
                except Exception:
                    return None
            s = str(val).strip()
            return "" if s == "nan" else s

        prod = {
            "barcode": barcode,
            "literal_label_name": literal_name,
            "full_name_en": full_name_en,
            "fuldt_navn_da": clean_val(row.get("Fuldt navn (DA)")),
            "brand": brand,
            "record_id": clean_val(row.get("Record ID")),
            "barcode_check_status": clean_val(row.get("Kiểm tra barcode")),
            "name_source_notes": clean_val(row.get("Nguồn tên / ghi chú bản dịch")),
            "variant": clean_val(row.get("Variant / flavour")),
            "category": clean_val(row.get("Category (editorial)")) or "Grocery",
            "packaging": clean_val(row.get("Packaging")) or "Bag",
            "net_quantity": net_quantity,
            "net_unit": net_unit,
            "unit_count": clean_val(row.get("Unit count"), as_float=True),
            "barcode_text_read": clean_val(row.get("Barcode text read from photo")),
            "supplier_sku": clean_val(row.get("Supplier SKU (explicit only)")),
            "other_printed_codes": clean_val(row.get("Other printed codes")),
            
            # Supply Chain & Origin
            "manufacturer": clean_val(row.get("Manufacturer")),
            "manufacturer_address": clean_val(row.get("Manufacturer address")),
            "country_of_origin": clean_val(row.get("Country of origin")),
            "origin_label_evidence": clean_val(row.get("Origin label evidence")),
            "importer": clean_val(row.get("Importer")),
            "importer_address": clean_val(row.get("Importer address")),
            "distributor": clean_val(row.get("Distributor")),

            # Ingredients & Allergens
            "ingredients_label_language": clean_val(row.get("Ingredients (label / language)")),
            "ingredients_en": clean_val(row.get("Ingredients (EN)")),
            "ingredienser_da": clean_val(row.get("Ingredienser (DA)")),
            "ingredient_translation_notes": clean_val(row.get("Ingredient translation / completeness")),
            "allergens_label": clean_val(row.get("Allergens (label)")),
            "allergens_en": clean_val(row.get("Allergens (EN)")),
            "allergener_da": clean_val(row.get("Allergener (DA)")),
            "may_contain_label": clean_val(row.get("May contain (label)")),

            # Nutrition Facts
            "nutrition_basis": clean_val(row.get("Nutrition basis / preparation state")) or "per 100 g",
            "energy_kj": clean_val(row.get("Energy (kJ)"), as_float=True),
            "energy_kcal": clean_val(row.get("Energy (kcal)"), as_float=True),
            "fat_g": clean_val(row.get("Fat (g)"), as_float=True),
            "saturates_g": clean_val(row.get("Saturates (g)"), as_float=True),
            "carbohydrate_g": clean_val(row.get("Carbohydrate (g)"), as_float=True),
            "sugars_g": clean_val(row.get("Sugars (g)"), as_float=True),
            "fibre_g": clean_val(row.get("Fibre (g)"), as_float=True),
            "protein_g": clean_val(row.get("Protein (g)"), as_float=True),
            "salt_g": clean_val(row.get("Salt (g)"), as_float=True),
            "other_nutrition_source": clean_val(row.get("Other nutrition / units / source")),

            # Usage, Storage & Compliance
            "preparation_label": clean_val(row.get("Preparation (label)")),
            "preparation_en": clean_val(row.get("Preparation (EN)")),
            "tilberedning_da": clean_val(row.get("Tilberedning (DA)")),
            "storage_label": clean_val(row.get("Storage (label)")),
            "storage_en": clean_val(row.get("Storage (EN)")),
            "opbevaring_da": clean_val(row.get("Opbevaring (DA)")),
            "warnings_label": clean_val(row.get("Warnings (label)")),
            "claims_certifications": clean_val(row.get("Claims / certification marks")),
            "alcohol_vol": clean_val(row.get("Alcohol (% vol)"), as_float=True),
            "manufacture_date": clean_val(row.get("Manufacture date (printed)")),
            "best_before_expiry": clean_val(row.get("Best before / expiry (printed)")),
            "lot_batch": clean_val(row.get("Lot / batch (printed)")),
            "website_contact": clean_val(row.get("Website / contact on label")),
            "other_legible_info": clean_val(row.get("Other legible label information")),

            # Media & UI fields
            "source_photo_filenames": clean_val(row.get("Source photo filenames")),
            "selected_front_source": clean_val(row.get("Selected front source")),
            "front_photo_limitations": clean_val(row.get("Front photo limitations")),
            "front_photo_relative_filename": clean_val(row.get("Front photo relative filename")),
            "image_width_px": int(row.get("Image width (px)")) if pd.notna(row.get("Image width (px)")) else 0,
            "image_height_px": int(row.get("Image height (px)")) if pd.notna(row.get("Image height (px)")) else 0,
            "dong_nguon_anh_mat_truoc": clean_val(row.get("Dòng nguồn ảnh mặt trước")),
            "anh_mat_truoc": clean_val(row.get("Ảnh mặt trước")),

            # UI compatibility fields
            "product_name": full_name_en or literal_name,
            "net_weight": net_weight_str,
            "pos_sku": pos_sku,
            "pos_product_name": pos_name,
            "original_image": img_name,
            "website_front_image": f"website_front_images/{barcode}.jpeg",
            "front_web_url": front_web_url,
            "raw_web_url": raw_web_url,
            "front_box_2d": [],
            "cropped_width": int(row.get("Image width (px)")) if pd.notna(row.get("Image width (px)")) else 0,
            "cropped_height": int(row.get("Image height (px)")) if pd.notna(row.get("Image height (px)")) else 0,
            "detection_method": "customer_gold_master",
            "status": "CONFIRMED",
        }

        confirmed_count += 1
        if pos_sku:
            pos_matched_count += 1
        products.append(prod)

    # Save to JSON
    stats = {
        "total": len(products),
        "confirmed": confirmed_count,
        "pos_matched": pos_matched_count,
        "review_needed": 0,
        "brands_count": len(brands_set),
    }

    payload = {
        "stats": stats,
        "brands": sorted(list(brands_set)),
        "products": products,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Exported JSON to {OUTPUT_JSON} ({len(products)} products, {stats['brands_count']} brands)")

    # Save to Excel G1_Master_Delivery_v2.xlsx
    OUTPUT_EXCEL.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(CUSTOMER_EXCEL, OUTPUT_EXCEL)
    print(f"Exported 65-column Master Delivery Excel to {OUTPUT_EXCEL}")


if __name__ == "__main__":
    sync_all()
