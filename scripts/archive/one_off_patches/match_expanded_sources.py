# -*- coding: utf-8 -*-
import sys
import os
import re
import json
import openpyxl
import pandas as pd
from collections import Counter
import difflib

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"

f1 = os.path.join(BASE_DIR, r"source-import\Ten_hang_nhap.xlsx")
f2 = os.path.join(BASE_DIR, r"source-import\Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")

def clean_bc(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"[^\w]", "", s)

def normalize_text(t):
    s = str(t or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())

# 1. Load 5424 POS items from Ten_ban
wb2 = openpyxl.load_workbook(f2, data_only=True)
ws_pos_full = wb2["Ten_ban"]
rows_pos_full = list(ws_pos_full.iter_rows(values_only=True))[1:]

pos_full_by_bc = {}
pos_full_list = []
for r in rows_pos_full:
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
    }
    pos_full_list.append(item)
    if c_bc:
        pos_full_by_bc[c_bc] = item
        pos_full_by_bc[c_bc.lstrip("0")] = item

print(f"Loaded {len(pos_full_list)} items from Shopbox Full (Ten_ban). Unique Barcodes: {len(pos_full_by_bc)}")

# 2. Load Supplier data
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
print(f"Loaded {len(supplier_items)} supplier import items.")

# 3. Load Master 1659 items
wb_m = openpyxl.load_workbook(os.path.join(BASE_DIR, r"output\shopify_import_final\Master_All_1659_Products_With_Images.xlsx"), data_only=True)
ws_m = wb_m.active
headers = [c.value for c in ws_m[3]]
master_items = []
for row_idx, row in enumerate(ws_m.iter_rows(min_row=4, values_only=True), start=4):
    d = dict(zip(headers, row))
    master_items.append((row_idx, d))

print(f"Loaded {len(master_items)} Master items.")

# Check how many unverified items match by Barcode (if barcode in raw/cache) or by Name in Shopbox Full
matched_by_barcode = 0
matched_by_name = 0
new_matches = []

# Load raw caches
caches = {}
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"] = json.load(f)
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_47_missing_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"].update(json.load(f))
for b in ["g2", "g3", "g4", "g5"]:
    with open(os.path.join(BASE_DIR, f"output\\shopify_import\\{b}_vision_cache.json"), "r", encoding="utf-8") as f:
        caches[b.upper()] = json.load(f)

for row_idx, d in master_items:
    curr_bc = clean_bc(d.get("Barcode"))
    curr_sku = str(d.get("POS SKU") or "").strip()
    status = str(d.get("Trạng thái đối soát") or "").strip()
    
    batch = d.get("Thư mục nguồn (Batch)")
    photo = d.get("Tên file ảnh gốc")
    stem = os.path.splitext(photo)[0] if photo else ""
    
    b_cache = caches.get(batch, {})
    c_data = b_cache.get(photo) or b_cache.get(stem) or {}
    if not c_data:
        for k, v in b_cache.items():
            if os.path.splitext(k)[0] == stem:
                c_data = v
                break
                
    raw_bc_cache = clean_bc(c_data.get("barcode") or c_data.get("barcode_text_read") or "")
    
    # Check if this item was unverified but has a barcode in cache that exists in Shopbox Full
    if (not curr_bc or not curr_sku) and raw_bc_cache and "no_barcode" not in raw_bc_cache.lower():
        if raw_bc_cache in pos_full_by_bc:
            matched_by_barcode += 1
            pos_match = pos_full_by_bc[raw_bc_cache]
            new_matches.append((photo, "BARCODE_MATCH", raw_bc_cache, pos_match["sku"], pos_match["product_name"], pos_match["selling_price"]))
            continue
            
    # If no barcode match, try fuzzy name matching against 5,424 POS items
    if not curr_bc or not curr_sku:
        brand = str(d.get("Thương hiệu (Brand)") or c_data.get("brand") or "").strip()
        name_da = str(d.get("Tên tiếng Đan Mạch (Fuldt navn DA)") or "").strip()
        name_en = str(d.get("Tên tiếng Anh (Full name EN)") or "").strip()
        query = normalize_text(f"{brand} {name_en} {name_da}")
        
        best_match = None
        best_score = 0.0
        for pos_item in pos_full_list:
            # Fast token overlap filter
            p_tokens = set(pos_item["norm_name"].split())
            q_tokens = set(query.split())
            overlap = len(p_tokens.intersection(q_tokens))
            if overlap >= 2:
                score = difflib.SequenceMatcher(None, query, pos_item["norm_name"]).ratio()
                if score > best_score:
                    best_score = score
                    best_match = pos_item
                    
        if best_score >= 0.80 and best_match:
            matched_by_name += 1
            new_matches.append((photo, f"NAME_MATCH_{best_score:.2f}", best_match["barcode"], best_match["sku"], best_match["product_name"], best_match["selling_price"]))

print(f"\nNew matches found with expanded 5,424 Shopbox POS database:")
print(f"  - Matched by Barcode in Shopbox Full: {matched_by_barcode}")
print(f"  - High Confidence Matched by Name (>=0.80): {matched_by_name}")
print(f"  - Total New Recovered Matches: {len(new_matches)}")

print("\n--- SAMPLE NEW RECOVERED MATCHES ---")
for m in new_matches[:25]:
    print(f"File: {m[0]:<20} | Type: {m[1]:<16} | BC: {m[2]:<14} | SKU: {m[3]:<10} | Price: {m[5]} | Name: {m[4]}")
