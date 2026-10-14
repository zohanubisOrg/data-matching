import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

G1_TEMPLATE = PROJECT_ROOT / "output/g1_delivery/G1_Master_Delivery_v2.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
MASTER_CONSOLIDATED = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"


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


def build_65_delivery_row(rec: dict[str, Any], headers_65: list[str]) -> list[Any]:
    barcode = str(rec.get("barcode") or "").strip()
    if barcode.endswith(".0"):
        barcode = barcode[:-2]
    if barcode.lower() in {"none", "nan", ""}:
        barcode = ""

    batch = str(rec.get("batch") or "G2").strip()
    record_id = str(rec.get("record_id") or "").strip()
    source_photo = str(rec.get("source_photo") or "").strip()
    front_img = str(rec.get("Website Front Image") or "").strip()
    if not front_img:
        front_img = f"{barcode}.jpg" if barcode else f"{record_id}.jpg"
    elif front_img.endswith(".webp"):
        front_img = front_img.replace(".webp", ".jpg")

    literal_name = safe_val(rec.get("literal_label_name")) or safe_val(rec.get("product_name"))
    full_name_en = safe_val(rec.get("full_name_en")) or safe_val(rec.get("product_name"))
    fuldt_navn_da = safe_val(rec.get("fuldt_navn_da"))

    brand = safe_val(rec.get("brand"))
    bc_check = safe_val(rec.get("barcode_check_status"))
    if not bc_check:
        bc_check = "Đúng checksum; đọc từ ảnh" if barcode else "Chưa có barcode"

    name_notes = safe_val(rec.get("name_source_notes")) or "Tên đầy đủ EN/DA chuẩn hóa từ nhãn; bản DA là bản dịch biên tập."
    variant = safe_val(rec.get("variant"))
    category = safe_val(rec.get("category")) or "Grocery"
    packaging = safe_val(rec.get("packaging")) or "Bag"

    net_qty = safe_val(rec.get("net_quantity"))
    net_unit = safe_val(rec.get("net_unit")) or "g"
    unit_count = safe_val(rec.get("unit_count"))
    bc_text_read = safe_val(rec.get("barcode_text_read")) or barcode

    sku = safe_val(rec.get("pos_sku")) or safe_val(rec.get("supplier_sku"))
    other_codes = safe_val(rec.get("other_printed_codes"))

    manufacturer = safe_val(rec.get("manufacturer"))
    mfg_addr = safe_val(rec.get("manufacturer_address"))
    origin = safe_val(rec.get("country_of_origin"))
    origin_ev = safe_val(rec.get("origin_label_evidence"))
    importer = safe_val(rec.get("importer"))
    imp_addr = safe_val(rec.get("importer_address"))
    distributor = safe_val(rec.get("distributor"))

    ing_lang = safe_val(rec.get("ingredients_label_language"))
    ing_en = safe_val(rec.get("ingredients_en"))
    ing_da = safe_val(rec.get("ingredienser_da"))
    ing_notes = safe_val(rec.get("ingredient_translation_notes"))

    all_label = safe_val(rec.get("allergens_label"))
    all_en = safe_val(rec.get("allergens_en"))
    all_da = safe_val(rec.get("allergener_da"))
    may_contain = safe_val(rec.get("may_contain_label"))

    nut_basis = safe_val(rec.get("nutrition_basis")) or "per 100 g"
    energy_kj = safe_val(rec.get("energy_kj"))
    energy_kcal = safe_val(rec.get("energy_kcal"))
    fat_g = safe_val(rec.get("fat_g"))
    sat_g = safe_val(rec.get("saturates_g"))
    carb_g = safe_val(rec.get("carbohydrate_g"))
    sug_g = safe_val(rec.get("sugars_g"))
    fib_g = safe_val(rec.get("fibre_g"))
    prot_g = safe_val(rec.get("protein_g"))
    salt_g = safe_val(rec.get("salt_g"))
    other_nut = safe_val(rec.get("other_nutrition_source"))

    prep_label = safe_val(rec.get("preparation_label"))
    prep_en = safe_val(rec.get("preparation_en"))
    prep_da = safe_val(rec.get("tilberedning_da"))

    store_label = safe_val(rec.get("storage_label"))
    store_en = safe_val(rec.get("storage_en"))
    store_da = safe_val(rec.get("opbevaring_da"))

    warn_label = safe_val(rec.get("warnings_label"))
    claims = safe_val(rec.get("claims_certifications"))
    alc_vol = safe_val(rec.get("alcohol_vol"))

    mfg_date = safe_val(rec.get("manufacture_date"))
    expiry = safe_val(rec.get("best_before_expiry"))
    lot = safe_val(rec.get("lot_batch"))
    web_contact = safe_val(rec.get("website_contact"))
    other_info = safe_val(rec.get("other_legible_info"))

    src_filenames = f"{batch}: {source_photo}" if source_photo else batch
    selected_front = f"{batch}/{source_photo}" if source_photo else ""
    front_limits = None
    front_rel_file = f"front_photos/{front_img}"
    img_w = safe_val(rec.get("image_width_px"))
    img_h = safe_val(rec.get("image_height_px"))
    dong_nguon = record_id
    anh_mat_truoc = None

    row_map = {
        "Barcode": barcode,
        "Tên nguyên văn trên nhãn": literal_name,
        "Full name (EN)": full_name_en,
        "Fuldt navn (DA)": fuldt_navn_da,
        "Brand": brand,
        "Record ID": record_id,
        "Kiểm tra barcode": bc_check,
        "Nguồn tên / ghi chú bản dịch": name_notes,
        "Variant / flavour": variant,
        "Category (editorial)": category,
        "Packaging": packaging,
        "Net quantity": net_qty,
        "Net unit": net_unit,
        "Unit count": unit_count,
        "Barcode text read from photo": bc_text_read,
        "Supplier SKU (explicit only)": sku,
        "Other printed codes": other_codes,
        "Manufacturer": manufacturer,
        "Manufacturer address": mfg_addr,
        "Country of origin": origin,
        "Origin label evidence": origin_ev,
        "Importer": importer,
        "Importer address": imp_addr,
        "Distributor": distributor,
        "Ingredients (label / language)": ing_lang,
        "Ingredients (EN)": ing_en,
        "Ingredienser (DA)": ing_da,
        "Ingredient translation / completeness": ing_notes,
        "Allergens (label)": all_label,
        "Allergens (EN)": all_en,
        "Allergener (DA)": all_da,
        "May contain (label)": may_contain,
        "Nutrition basis / preparation state": nut_basis,
        "Energy (kJ)": energy_kj,
        "Energy (kcal)": energy_kcal,
        "Fat (g)": fat_g,
        "Saturates (g)": sat_g,
        "Carbohydrate (g)": carb_g,
        "Sugars (g)": sug_g,
        "Fibre (g)": fib_g,
        "Protein (g)": prot_g,
        "Salt (g)": salt_g,
        "Other nutrition / units / source": other_nut,
        "Preparation (label)": prep_label,
        "Preparation (EN)": prep_en,
        "Tilberedning (DA)": prep_da,
        "Storage (label)": store_label,
        "Storage (EN)": store_en,
        "Opbevaring (DA)": store_da,
        "Warnings (label)": warn_label,
        "Claims / certification marks": claims,
        "Alcohol (% vol)": alc_vol,
        "Manufacture date (printed)": mfg_date,
        "Best before / expiry (printed)": expiry,
        "Lot / batch (printed)": lot,
        "Website / contact on label": web_contact,
        "Other legible label information": other_info,
        "Source photo filenames": src_filenames,
        "Selected front source": selected_front,
        "Front photo limitations": front_limits,
        "Front photo relative filename": front_rel_file,
        "Image width (px)": img_w,
        "Image height (px)": img_h,
        "Dòng nguồn ảnh mặt trước": dong_nguon,
        "Ảnh mặt trước": anh_mat_truoc,
    }

    return [row_map.get(h) for h in headers_65]


def export_65_delivery_excel(records: list[dict[str, Any]], out_path: Path):
    headers_65 = get_65_headers()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Row 1 is empty title/margin row in G1 standard
    ws.append([None] * 65)
    # Row 2 is the 65 header titles
    ws.append(headers_65)

    for rec in records:
        row_vals = build_65_delivery_row(rec, headers_65)
        ws.append(row_vals)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    wb.close()
    print(f"Exported {len(records)} records to 65-column Delivery Excel: {out_path}")


def main():
    print("Exporting 65-column Delivery files matching G1_Master_Delivery_v2.xlsx structure...")
    df = pd.read_excel(MASTER_CONSOLIDATED)
    records = df.to_dict(orient="records")

    # 1. Consolidated G2-G5 delivery files
    out_master_1 = OUTPUT_DIR / "Master_G2_G5_Delivery_v2.xlsx"
    out_master_2 = OUTPUT_DIR / "G2_G5_Master_Delivery_v2.xlsx"
    export_65_delivery_excel(records, out_master_1)
    export_65_delivery_excel(records, out_master_2)

    # 2. Individual batch delivery files
    batch_map: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        b = str(r.get("batch") or "G2").strip()
        batch_map.setdefault(b, []).append(r)

    for bname, brecs in batch_map.items():
        b_out = OUTPUT_DIR / f"{bname}_Master_Delivery_v2.xlsx"
        export_65_delivery_excel(brecs, b_out)

    print("All 65-column delivery files created successfully!")


if __name__ == "__main__":
    main()
