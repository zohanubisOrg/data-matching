# -*- coding: utf-8 -*-
"""
Deep Reconcile with 5,424 Shopbox POS + Supplier Tables + Vision Caches
"""
import sys
import os
import re
import json
import difflib
import openpyxl
import pandas as pd
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SOURCE_DIR = os.path.join(BASE_DIR, "source-import")
CUSTOMER_SRC = os.path.join(SOURCE_DIR, "new_source_from_customer")

f1 = os.path.join(SOURCE_DIR, "Ten_hang_nhap.xlsx")
f2 = os.path.join(SOURCE_DIR, "Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
pos_active_file = os.path.join(CUSTOMER_SRC, "27.09.26.POS_ACTIVE_FINAL.xlsx")

def clean_bc(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"[^\w]", "", s)

def normalize_text(t):
    s = str(t or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())

# 1. Load All POS Data (Merging 5,424 POS and Active POS)
all_pos_by_bc = {}
all_pos_by_clean_bc = {}
all_pos_list = []

# Load 5424
wb2 = openpyxl.load_workbook(f2, data_only=True)
ws2 = wb2["Ten_ban"]
for r in list(ws2.iter_rows(values_only=True))[1:]:
    raw_bc = str(r[7] or "").strip()
    c_bc = clean_bc(raw_bc)
    sku = str(r[8] or "").strip()
    p_name = str(r[1] or "").strip()
    off_name = str(r[2] or "").strip()
    item = {
        "pos_category": str(r[0] or "").strip(),
        "product_name": p_name,
        "official_name": off_name,
        "printer_name": str(r[3] or "").strip(),
        "purchase_price": r[4],
        "selling_price": r[5],
        "unit": r[6],
        "barcode": c_bc,
        "sku": sku,
        "product_id": str(r[9] or "").strip(),
        "tax_group": r[10],
        "norm_name": normalize_text(f"{p_name} {off_name}"),
        "source": "Shopbox_5424",
    }
    all_pos_list.append(item)
    if c_bc:
        all_pos_by_bc[c_bc] = item
        all_pos_by_clean_bc[c_bc.lstrip("0")] = item

# Overlay active 1350 (newer prices/status)
wb_act = openpyxl.load_workbook(pos_active_file, data_only=True)
for r in list(wb_act.active.iter_rows(values_only=True))[1:]:
    raw_bc = str(r[7] or "").strip()
    c_bc = clean_bc(raw_bc)
    sku = str(r[8] or "").strip()
    p_name = str(r[1] or "").strip()
    off_name = str(r[2] or "").strip()
    item = {
        "pos_category": str(r[0] or "").strip(),
        "product_name": p_name,
        "official_name": off_name,
        "printer_name": str(r[3] or "").strip(),
        "purchase_price": r[4],
        "selling_price": r[5],
        "unit": r[6],
        "barcode": c_bc,
        "sku": sku,
        "product_id": str(r[9] or "").strip(),
        "tax_group": r[10],
        "norm_name": normalize_text(f"{p_name} {off_name}"),
        "source": "POS_Active_1350",
    }
    if c_bc:
        all_pos_by_bc[c_bc] = item
        all_pos_by_clean_bc[c_bc.lstrip("0")] = item

print(f"Total Unified POS Barcodes: {len(all_pos_by_bc)}")

# 2. Load Supplier Purchase Items
supplier_items = []
wb1 = openpyxl.load_workbook(f1, data_only=True)
for sheet in ["EUR", "SEK", "Hàng mua tại Đan Mạch"]:
    ws = wb1[sheet]
    for r in list(ws.iter_rows(values_only=True))[1:]:
        if r and len(r) >= 4 and r[1]:
            supplier_items.append({
                "supplier_name": str(r[1]).strip(),
                "vendor": str(r[2]).strip() if r[2] else "",
                "supplier_sku": str(r[3]).strip() if r[3] else "",
                "norm_name": normalize_text(r[1]),
            })
print(f"Total Supplier Import Items: {len(supplier_items)}")

# 3. Load All 1659 Raw Records
caches = {}
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"] = json.load(f)
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_47_missing_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"].update(json.load(f))
for b in ["g2", "g3", "g4", "g5"]:
    with open(os.path.join(BASE_DIR, f"output\\shopify_import\\{b}_vision_cache.json"), "r", encoding="utf-8") as f:
        caches[b.upper()] = json.load(f)

# Load G2-G5 master dfs for fallback fields
g_dfs = {}
for b in ["G2", "G3", "G4", "G5"]:
    g_dfs[b] = pd.read_excel(os.path.join(BASE_DIR, f"output\\shopify_import\\{b}_master_products.xlsx"))

all_1659 = []
for fname, item in caches["G1"].items():
    rec = dict(item)
    rec["batch"] = "G1"
    rec["source_photo"] = fname
    all_1659.append(rec)

for b in ["G2", "G3", "G4", "G5"]:
    for _, row in g_dfs[b].iterrows():
        rec = row.to_dict()
        rec["batch"] = b
        rec["source_photo"] = str(rec.get("source_photo") or "")
        all_1659.append(rec)

print(f"Total raw items: {len(all_1659)}")

# Match Analysis
matched_direct_pos_bc = 0
matched_vision_bc = 0
matched_fuzzy_name = 0
ocr_only_items = 0

resolved_records = []

for idx, item in enumerate(all_1659, start=1):
    batch = item.get("batch", "G1")
    photo = item.get("source_photo", "")
    stem = os.path.splitext(photo)[0] if photo else f"item_{idx}"
    
    b_cache = caches.get(batch, {})
    c_data = b_cache.get(photo) or b_cache.get(stem) or {}
    if not c_data:
        for k, v in b_cache.items():
            if os.path.splitext(k)[0] == stem:
                c_data = v
                break
    c_data = c_data or {}
    
    raw_bc_item = clean_bc(item.get("barcode") or item.get("Barcode"))
    raw_bc_cache = clean_bc(c_data.get("barcode") or c_data.get("barcode_text_read"))
    rec_id = str(item.get("record_id") or item.get("Record ID") or "").strip()
    bc_status = str(item.get("barcode_check_status") or "").strip()
    
    is_borrowed = ("barcode từ" in bc_status) or ("trùng mã" in bc_status)
    
    # Priority 1: Verified Barcode in item
    pos_match = None
    match_method = None
    
    if not is_borrowed and raw_bc_item and raw_bc_item in all_pos_by_bc:
        pos_match = all_pos_by_bc[raw_bc_item]
        match_method = "DIRECT_POS_BARCODE"
        matched_direct_pos_bc += 1
    elif not is_borrowed and raw_bc_item and raw_bc_item.lstrip("0") in all_pos_by_clean_bc:
        pos_match = all_pos_by_clean_bc[raw_bc_item.lstrip("0")]
        match_method = "DIRECT_POS_BARCODE"
        matched_direct_pos_bc += 1
    # Priority 2: Barcode read from Vision OCR (e.g. from photo label)
    elif raw_bc_cache and "no_barcode" not in raw_bc_cache.lower() and raw_bc_cache in all_pos_by_bc:
        pos_match = all_pos_by_bc[raw_bc_cache]
        match_method = "VISION_OCR_BARCODE_MATCH"
        matched_vision_bc += 1
    elif raw_bc_cache and "no_barcode" not in raw_bc_cache.lower() and raw_bc_cache.lstrip("0") in all_pos_by_clean_bc:
        pos_match = all_pos_by_clean_bc[raw_bc_cache.lstrip("0")]
        match_method = "VISION_OCR_BARCODE_MATCH"
        matched_vision_bc += 1
    # Priority 3: Fuzzy name matching against Shopbox POS (High confidence >= 0.82)
    else:
        brand = str(c_data.get("brand") or item.get("brand") or "").strip()
        name_en = str(c_data.get("full_name_en") or c_data.get("literal_label_name") or item.get("full_name_en") or item.get("product_name") or "").strip()
        name_da = str(c_data.get("fuldt_navn_da") or item.get("fuldt_navn_da") or "").strip()
        query = normalize_text(f"{brand} {name_en} {name_da}")
        
        best_pos = None
        best_score = 0.0
        q_tokens = set(query.split())
        for p_item in all_pos_list:
            p_tokens = set(p_item["norm_name"].split())
            if len(p_tokens.intersection(q_tokens)) >= 2:
                sc = difflib.SequenceMatcher(None, query, p_item["norm_name"]).ratio()
                if sc > best_score:
                    best_score = sc
                    best_pos = p_item
                    
        if best_score >= 0.82 and best_pos:
            pos_match = best_pos
            match_method = f"POS_NAME_MATCH_{best_score:.2f}"
            matched_fuzzy_name += 1
        else:
            match_method = "INDEPENDENT_LABEL_OCR"
            ocr_only_items += 1
            
    resolved_records.append({
        "idx": idx,
        "batch": batch,
        "photo": photo,
        "match_method": match_method,
        "pos_match": pos_match,
        "raw_item": item,
        "cache": c_data,
    })

print(f"\nDeep Matching Summary across all 1,659 items:")
print(f"  - Direct POS Barcode Match: {matched_direct_pos_bc}")
print(f"  - Vision OCR Barcode Match: {matched_vision_bc}")
print(f"  - High Confidence POS Name Match (>=0.82): {matched_fuzzy_name}")
print(f"  - Total POS Matched: {matched_direct_pos_bc + matched_vision_bc + matched_fuzzy_name} ({((matched_direct_pos_bc + matched_vision_bc + matched_fuzzy_name)/1659)*100:.1f}%)")
print(f"  - Independent Label OCR Only (New/Special Items): {ocr_only_items} ({(ocr_only_items/1659)*100:.1f}%)")
