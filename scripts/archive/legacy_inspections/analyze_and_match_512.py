# -*- coding: utf-8 -*-
import sys
import os
import json
import re
import difflib
import openpyxl
import pandas as pd
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
CUSTOMER_SRC = os.path.join(BASE_DIR, "source-import", "new_source_from_customer")

# 1. Load POS
pos_file = os.path.join(CUSTOMER_SRC, "27.09.26.POS_ACTIVE_FINAL.xlsx")
wb_pos = openpyxl.load_workbook(pos_file, data_only=True)
ws_pos = wb_pos.active
pos_rows = list(ws_pos.iter_rows(values_only=True))[1:]

def clean_bc(v):
    s = str(v or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return re.sub(r"[^\w]", "", s)

def normalize_text(t):
    s = str(t or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())

pos_list = []
pos_by_bc = {}
for r in pos_rows:
    raw_bc = str(r[7] or "").strip()
    c_bc = clean_bc(raw_bc)
    p_name = str(r[1] or "").strip()
    off_name = str(r[2] or "").strip()
    sku = str(r[8] or "").strip()
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
        "norm_name": normalize_text(f"{p_name} {off_name}"),
    }
    pos_list.append(item)
    if c_bc:
        pos_by_bc[c_bc] = item

# 2. Load Categories
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

# 3. Load Master
wb_m = openpyxl.load_workbook(os.path.join(BASE_DIR, r"output\shopify_import_final\Master_All_1659_Products_With_Images.xlsx"), data_only=True)
ws_m = wb_m.active
headers = [c.value for c in ws_m[3]]

# 4. Load Caches
caches = {}
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"] = json.load(f)
for b in ["g2", "g3", "g4", "g5"]:
    with open(os.path.join(BASE_DIR, f"output\\shopify_import\\{b}_vision_cache.json"), "r", encoding="utf-8") as f:
        caches[b.upper()] = json.load(f)

unverified = []
for row_idx, row in enumerate(ws_m.iter_rows(min_row=4, values_only=True), start=4):
    d = dict(zip(headers, row))
    status = str(d.get("Trạng thái đối soát") or "").strip()
    sku = str(d.get("POS SKU") or "").strip()
    bc = str(d.get("Barcode") or "").strip()
    if "CHƯA XÁC MINH" in status or not sku or not bc:
        unverified.append((row_idx, d))

print(f"Total unverified rows to process: {len(unverified)}")

matched_pos_by_name = 0
has_full_ocr = 0
missing_cache = 0

matched_examples = []
unmatched_ocr_examples = []

for idx, d in unverified:
    batch = d.get("Thư mục nguồn (Batch)")
    photo = d.get("Tên file ảnh gốc")
    stem = os.path.splitext(photo)[0] if photo else ""
    
    b_cache = caches.get(batch, {})
    c_data = b_cache.get(photo) or b_cache.get(stem) or b_cache.get(photo.lower())
    if not c_data:
        for k, v in b_cache.items():
            if os.path.splitext(k)[0] == stem:
                c_data = v
                break
                
    if not c_data:
        missing_cache += 1
        continue
        
    brand = str(c_data.get("brand") or "").strip()
    pname = str(c_data.get("product_name") or c_data.get("literal_label_name") or "").strip()
    fuldt_da = str(c_data.get("fuldt_navn_da") or "").strip()
    full_en = str(c_data.get("full_name_en") or "").strip()
    net_q = str(c_data.get("net_quantity") or c_data.get("net_weight") or "").strip()
    
    # Check if we can find a high confidence match in POS
    query = normalize_text(f"{brand} {pname} {fuldt_da} {full_en}")
    best_match = None
    best_score = 0.0
    
    for pos_item in pos_list:
        p_norm = pos_item["norm_name"]
        # Exact token match score
        ratio = difflib.SequenceMatcher(None, query, p_norm).ratio()
        if ratio > best_score:
            best_score = ratio
            best_match = pos_item
            
    if best_score >= 0.75 and best_match:
        matched_pos_by_name += 1
        if len(matched_examples) < 8:
            matched_examples.append((photo, brand, pname, best_match["product_name"], best_match["sku"], best_match["barcode"], best_score))
    else:
        has_full_ocr += 1
        if len(unmatched_ocr_examples) < 8:
            unmatched_ocr_examples.append((photo, brand, pname, fuldt_da, net_q, c_data.get("category")))

print(f"Results of Analysis on 512 items:")
print(f"  - High Confidence POS Name Match (>=0.75): {matched_pos_by_name}")
print(f"  - Independent Label OCR Available (New Product / Special): {has_full_ocr}")
print(f"  - Missing cache completely: {missing_cache}")

print("\n--- SAMPLE HIGH-CONFIDENCE POS MATCHES ---")
for ex in matched_examples:
    print(f"File: {ex[0]} | Query: {ex[1]} - {ex[2]} => POS: {ex[3]} (SKU: {ex[4]}, BC: {ex[5]}, Score: {ex[6]:.2f})")

print("\n--- SAMPLE INDEPENDENT LABEL OCR (SẢN PHẨM MỚI TỪ NHÃN) ---")
for ex in unmatched_ocr_examples:
    print(f"File: {ex[0]} | Brand: {ex[1]} | Name: {ex[2]} | DA: {ex[3]} | Qty: {ex[4]} | Cat: {ex[5]}")
