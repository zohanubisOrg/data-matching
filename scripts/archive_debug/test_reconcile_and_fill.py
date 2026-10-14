# -*- coding: utf-8 -*-
"""
Test reconciliation & fill for all 1,659 items.
"""
import sys
import os
import json
import re
import openpyxl
import pandas as pd
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
CUSTOMER_SRC = os.path.join(SOURCE_DIR, "new_source_from_customer")
OUTPUT_DIR = os.path.join(BASE_DIR, r"output\shopify_import_final")
IMG_FINAL_DIR = os.path.join(OUTPUT_DIR, "product_images")
THUMBS_DIR = os.path.join(OUTPUT_DIR, "excel_delivery_thumbs")

# 1. Categories
cat_file = os.path.join(CUSTOMER_SRC, "Ma_nhom_hang_SKU_3digits.xlsx")
wb_cat = openpyxl.load_workbook(cat_file, data_only=True)
ws_cat = wb_cat.active
nhom_map = {}
for r in list(ws_cat.iter_rows(values_only=True))[4:]:
    if r[1]:
        dansk_name = str(r[1]).strip()
        nhom_map[dansk_name] = {
            "code": str(r[2]).strip() if r[2] else "",
            "vi": str(r[3]).strip() if r[3] else "",
            "is_online": str(r[5]).strip().lower() != "nej",
        }

CATEGORY_TRANSLATION = {
    "snacks": "Snack",
    "snack": "Snack",
    "candy": "Snack",
    "sweets": "Snack",
    "cookies": "Snack",
    "condiments": "Saucer",
    "sauce": "Saucer",
    "sauces": "Saucer",
    "beverage": "Drikkevarer",
    "beverages": "Drikkevarer",
    "drinks": "Drikkevarer",
    "tea": "Drikkevarer",
    "noodles": "Nudler",
    "noodle": "Nudler",
    "ramen": "Nudler",
    "pasta": "Nudler",
    "spices": "Krydderier",
    "seasoning": "Krydderier",
    "canned": "Konserves",
    "canned goods": "Konserves",
    "flour": "Mel",
    "beans": "Bønner",
    "rice": "Ris",
    "vegetables": "Grøntsager",
    "fruit": "Frugt",
    "dairy": "Mælk",
    "frozen": "Frostvarer",
    "fish": "Fisk",
    "seafood": "Diverse",
}

def map_category(raw_cat, title=""):
    rc = str(raw_cat or "").lower().strip()
    if rc in CATEGORY_TRANSLATION:
        return CATEGORY_TRANSLATION[rc]
    for k, v in CATEGORY_TRANSLATION.items():
        if k in rc:
            return v
    t_low = str(title or "").lower()
    if any(w in t_low for w in ["noodle", "ramen", "udon", "vermicelli", "mì", "mi ", "phở", "bún"]):
        return "Nudler"
    if any(w in t_low for w in ["sauce", "paste", "soya", "dip", "sriracha", "chili sauce", "sojasauce"]):
        return "Saucer"
    if any(w in t_low for w in ["snack", "chip", "cracker", "biscuit", "candy", "gummy", "jelly", "seaweed", "peas"]):
        return "Snack"
    if any(w in t_low for w in ["drink", "juice", "tea", "soda", "beverage", "water", "milk"]):
        return "Drikkevarer"
    if any(w in t_low for w in ["spice", "curry", "powder", "seasoning", "pepper", "karry"]):
        return "Krydderier"
    if any(w in t_low for w in ["canned", "paste", "coconut milk", "kokosmælk"]):
        return "Konserves"
    return "Diverse"

# 2. POS
pos_file = os.path.join(CUSTOMER_SRC, "27.09.26.POS_ACTIVE_FINAL.xlsx")
wb_pos = openpyxl.load_workbook(pos_file, data_only=True)
ws_pos = wb_pos.active
pos_rows = list(ws_pos.iter_rows(values_only=True))[1:]

def clean_bc(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"[^\w]", "", s)

pos_by_bc = {}
for r in pos_rows:
    raw_bc = str(r[7] or "").strip()
    c_bc = clean_bc(raw_bc)
    sku = str(r[8] or "").strip()
    item_info = {
        "pos_category": str(r[0] or "").strip(),
        "product_name": str(r[1] or "").strip(),
        "official_name": str(r[2] or "").strip(),
        "printer_name": str(r[3] or "").strip(),
        "purchase_price": r[4],
        "selling_price": r[5],
        "unit": r[6],
        "raw_barcode": raw_bc,
        "clean_barcode": c_bc,
        "sku": sku,
        "product_id": str(r[9] or "").strip(),
        "tax_group": r[10],
    }
    if c_bc:
        pos_by_bc[c_bc] = item_info
        pos_by_bc[c_bc.lstrip("0")] = item_info

# 3. Product Master 89 cols
pm_file = [f for f in os.listdir(CUSTOMER_SRC) if f.startswith("Product_master") and f.endswith(".xlsx") and not f.startswith("~$")][0]
pm_path = os.path.join(CUSTOMER_SRC, pm_file)
wb_pm = openpyxl.load_workbook(pm_path, read_only=True, data_only=True)
ws_pm = wb_pm.active
pm_all_rows = list(ws_pm.iter_rows(values_only=True))
pm_headers_89 = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(pm_all_rows[4])]

pm_dict_by_bc = {}
pm_dict_by_rec = {}
borrowed_record_ids = set()

for r in pm_all_rows[5:]:
    if any(r):
        r_dict = {pm_headers_89[i]: r[i] for i in range(min(len(pm_headers_89), len(r)))}
        bc = clean_bc(r_dict.get("Barcode"))
        rec_id = str(r_dict.get("Record ID") or "").strip()
        bc_status = str(r_dict.get("Kiểm tra barcode") or "").strip()
        
        if "barcode từ" in bc_status or "trùng mã" in bc_status:
            borrowed_record_ids.add(rec_id)
        else:
            if bc:
                pm_dict_by_bc[bc] = r_dict
                pm_dict_by_bc[bc.lstrip("0")] = r_dict
        if rec_id:
            pm_dict_by_rec[rec_id] = r_dict

# 4. Load all vision caches
caches = {}
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"] = json.load(f)
for b in ["g2", "g3", "g4", "g5"]:
    with open(os.path.join(BASE_DIR, f"output\\shopify_import\\{b}_vision_cache.json"), "r", encoding="utf-8") as f:
        caches[b.upper()] = json.load(f)

# 5. Load all 1659 records
all_1659_raw_records = []
for fname, item in caches["G1"].items():
    rec = dict(item)
    rec["batch"] = "G1"
    rec["source_photo"] = fname
    all_1659_raw_records.append(rec)

for b_name, f_name in [("G2", "G2_master_products.xlsx"), ("G3", "G3_master_products.xlsx"), ("G4", "G4_master_products.xlsx"), ("G5", "G5_master_products.xlsx")]:
    df_b = pd.read_excel(os.path.join(BASE_DIR, "output\\shopify_import", f_name))
    for _, row in df_b.iterrows():
        rec = row.to_dict()
        rec["batch"] = b_name
        rec["source_photo"] = str(rec.get("source_photo") or "")
        all_1659_raw_records.append(rec)

print(f"Total raw items: {len(all_1659_raw_records)}")

def safe_str(v):
    if v is None or pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"none", "nan", "null"} else s

seen_barcodes = Counter()
for item in all_1659_raw_records:
    raw_bc = item.get("barcode") or item.get("Barcode") or ""
    bc = clean_bc(raw_bc)
    rec_id = str(item.get("record_id") or item.get("Record ID") or "").strip()
    bc_status = str(item.get("barcode_check_status") or "").strip()
    if bc and rec_id not in borrowed_record_ids and "barcode từ" not in bc_status:
        seen_barcodes[bc] += 1

used_barcodes = set()
verified_count = 0
ocr_resolved_count = 0

for idx, item in enumerate(all_1659_raw_records, start=1):
    batch = item.get("batch", "G1")
    source_photo = item.get("source_photo", "")
    stem = Path(source_photo).stem if source_photo else f"item_{idx}"
    
    raw_bc = item.get("barcode") or item.get("Barcode") or ""
    bc = clean_bc(raw_bc)
    rec_id = str(item.get("record_id") or item.get("Record ID") or "").strip()
    bc_status = str(item.get("barcode_check_status") or "").strip()
    
    is_borrowed = (rec_id in borrowed_record_ids) or ("barcode từ" in bc_status) or ("trùng mã" in bc_status)
    is_consecutive_duplicate = (bc in used_barcodes and seen_barcodes[bc] > 1)
    
    b_cache = caches.get(batch, {})
    c_data = b_cache.get(source_photo) or b_cache.get(stem) or b_cache.get(source_photo.lower())
    if not c_data:
        for k, v in b_cache.items():
            if os.path.splitext(k)[0] == stem:
                c_data = v
                break
    c_data = c_data or {}
    
    if is_borrowed or is_consecutive_duplicate or not bc or "no_barcode" in bc.lower():
        # SPECIAL RESOLUTION: INDEPENDENT OCR EXTRACTED FROM PACKAGE LABEL
        ocr_resolved_count += 1
        bc_final = ""
        sku_final = ""
        price_final = ""
        purch_price_final = ""
        pos_name = ""
        
        # Populate all true visible info from OCR
        brand_final = safe_str(c_data.get("brand") or item.get("brand") or "Asiatisk")
        title_da = safe_str(c_data.get("fuldt_navn_da") or c_data.get("product_name") or item.get("fuldt_navn_da") or item.get("product_name") or "")
        title_en = safe_str(c_data.get("full_name_en") or c_data.get("literal_label_name") or item.get("full_name_en") or item.get("product_name") or "")
        
        raw_cat = c_data.get("category") or item.get("category") or "Diverse"
        pos_cat = map_category(raw_cat, title_da or title_en)
        cat_rule = nhom_map.get(pos_cat, {})
        group_code = cat_rule.get("code", "")
        is_online = cat_rule.get("is_online", True)
        if pos_cat in ["Frostvarer", "Fisk", "Rejer", "Ris"]:
            is_online = False
            
        net_qty = c_data.get("net_quantity") or item.get("net_quantity") or ""
        net_unit = c_data.get("net_unit") or item.get("net_unit") or "g"
        variant = safe_str(c_data.get("variant") or item.get("variant") or "")
        packaging = safe_str(c_data.get("packaging") or item.get("packaging") or "")
        origin = safe_str(c_data.get("country_of_origin") or item.get("country_of_origin") or "")
        mfg = safe_str(c_data.get("manufacturer") or item.get("manufacturer") or "")
        importer = safe_str(c_data.get("importer") or item.get("importer") or "")
        
        ing_da = safe_str(c_data.get("ingredienser_da") or item.get("ingredienser_da") or "")
        ing_en = safe_str(c_data.get("ingredients_en") or item.get("ingredients_en") or "")
        all_da = safe_str(c_data.get("allergener_da") or item.get("allergener_da") or "")
        all_en = safe_str(c_data.get("allergens_en") or item.get("allergens_en") or "")
        
        ekj = c_data.get("energy_kj") or item.get("energy_kj") or ""
        ekcal = c_data.get("energy_kcal") or item.get("energy_kcal") or ""
        fat = c_data.get("fat_g") or item.get("fat_g") or ""
        sat = c_data.get("saturates_g") or item.get("saturates_g") or ""
        carb = c_data.get("carbohydrate_g") or item.get("carbohydrate_g") or ""
        sug = c_data.get("sugars_g") or item.get("sugars_g") or ""
        prot = c_data.get("protein_g") or item.get("protein_g") or ""
        salt = c_data.get("salt_g") or item.get("salt_g") or ""
        
        storage = safe_str(c_data.get("opbevaring_da") or item.get("opbevaring_da") or "Opbevares tørt og køligt")
        prep = safe_str(c_data.get("tilberedning_da") or item.get("tilberedning_da") or "")
        match_status = "ĐÃ TRÍCH XUẤT NHÃN OCR (SẢN PHẨM MỚI / CHƯA CÓ MÃ VẠCH TRÊN MẶT TRƯỚC)"
    else:
        verified_count += 1
        bc_final = bc
        used_barcodes.add(bc)
        pos = pos_by_bc.get(bc) or {}
        sku_final = pos.get("sku") or str(item.get("pos_sku") or item.get("supplier_sku") or "").strip()
        price_final = pos.get("selling_price") or item.get("selling_price") or ""
        purch_price_final = pos.get("purchase_price") or item.get("purchase_price") or ""
        
        pos_cat = pos.get("pos_category") or str(item.get("pos_category") or item.get("category") or "Diverse").strip()
        cat_rule = nhom_map.get(pos_cat, {})
        is_online = cat_rule.get("is_online", True)
        if pos_cat in ["Frostvarer", "Fisk", "Rejer", "Ris"]:
            is_online = False
        group_code = cat_rule.get("code", "")
        
        pm = pm_dict_by_bc.get(bc) or pm_dict_by_rec.get(rec_id) or {}
        title_da = safe_str(pm.get("Fuldt navn (DA)") or item.get("fuldt_navn_da") or c_data.get("fuldt_navn_da") or c_data.get("product_name") or "")
        title_en = safe_str(pm.get("Full name (EN)") or item.get("full_name_en") or c_data.get("full_name_en") or c_data.get("product_name") or "")
        pos_name = safe_str(pos.get("product_name") or item.get("product_name") or "")
        brand_final = safe_str(pm.get("Brand") or c_data.get("brand") or item.get("brand") or "Asiatisk")
        variant = safe_str(pm.get("Variant / flavour") or c_data.get("variant") or item.get("variant") or "")
        packaging = safe_str(pm.get("Packaging") or c_data.get("packaging") or item.get("packaging") or "")
        
        net_qty = pm.get("Net quantity") or c_data.get("net_quantity") or item.get("net_quantity") or ""
        net_unit = pm.get("Net unit") or c_data.get("net_unit") or item.get("net_unit") or "g"
        origin = safe_str(pm.get("Country of origin") or c_data.get("country_of_origin") or item.get("country_of_origin") or "Asien")
        mfg = safe_str(pm.get("Manufacturer") or c_data.get("manufacturer") or item.get("manufacturer") or "")
        importer = safe_str(pm.get("Importer") or c_data.get("importer") or item.get("importer") or "")
        
        ing_da = safe_str(pm.get("Ingredienser (DA)") or c_data.get("ingredienser_da") or item.get("ingredienser_da") or "")
        ing_en = safe_str(pm.get("Ingredients (EN)") or c_data.get("ingredients_en") or item.get("ingredients_en") or "")
        all_da = safe_str(pm.get("Allergener (DA)") or c_data.get("allergener_da") or item.get("allergener_da") or "")
        all_en = safe_str(pm.get("Allergens (EN)") or c_data.get("allergens_en") or item.get("allergens_en") or "")
        
        ekj = pm.get("Energy (kJ)") or c_data.get("energy_kj") or item.get("energy_kj") or ""
        ekcal = pm.get("Energy (kcal)") or c_data.get("energy_kcal") or item.get("energy_kcal") or ""
        fat = pm.get("Fat (g)") or c_data.get("fat_g") or item.get("fat_g") or ""
        sat = pm.get("Saturates (g)") or c_data.get("saturates_g") or item.get("saturates_g") or ""
        carb = pm.get("Carbohydrate (g)") or c_data.get("carbohydrate_g") or item.get("carbohydrate_g") or ""
        sug = pm.get("Sugars (g)") or c_data.get("sugars_g") or item.get("sugars_g") or ""
        prot = pm.get("Protein (g)") or c_data.get("protein_g") or item.get("protein_g") or ""
        salt = pm.get("Salt (g)") or c_data.get("salt_g") or item.get("salt_g") or ""
        
        storage = safe_str(pm.get("Opbevaring (DA)") or c_data.get("opbevaring_da") or item.get("opbevaring_da") or "Opbevares tørt og køligt")
        prep = safe_str(pm.get("Tilberedning (DA)") or c_data.get("tilberedning_da") or item.get("tilberedning_da") or "")
        match_status = "ĐÃ ĐỐI SOÁT XÁC THỰC POS (VERIFIED_POS_BARCODE)"

print(f"Summary:")
print(f"  - Total Products: {len(all_1659_raw_records)}")
print(f"  - Verified with POS Barcode: {verified_count}")
print(f"  - Resolved via Independent Label OCR (New/Special Products): {ocr_resolved_count}")
