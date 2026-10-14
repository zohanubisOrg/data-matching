# -*- coding: utf-8 -*-
import os
import sys
import json
import openpyxl
import pandas as pd
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

src_folders = {
    'G1': r'D:\Work\shopify\source-import\G1_original',
    'G2': r'D:\Work\shopify\source-import\G2_original',
    'G3': r'D:\Work\shopify\source-import\G3_Original',
    'G4': r'D:\Work\shopify\source-import\G4-original',
    'G5': r'D:\Work\shopify\source-import\Nyt25.09.26',
}

# 1. Load POS
pos_path = r'D:\Work\shopify\source-import\new_source_from_customer\27.09.26.POS_ACTIVE_FINAL.xlsx'
df_pos = pd.read_excel(pos_path)

def clean_bc(v):
    s = str(v or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s

pos_by_bc = {}
for idx, r in df_pos.iterrows():
    bc = clean_bc(r.get('Bar Code'))
    sku = str(r.get('Sku Code') or '').strip()
    pname = str(r.get('Product Name') or '').strip()
    cat = str(r.get('Category Name') or '').strip()
    price = r.get('Selling Price')
    if bc:
        info = {'barcode': bc, 'sku': sku, 'product_name': pname, 'category': cat, 'price': price}
        pos_by_bc[bc] = info
        pos_by_bc[bc.lstrip('0')] = info

# 2. Load PM
pm_file = [f for f in os.listdir(r'D:\Work\shopify\source-import\new_source_from_customer') if f.startswith('Product_master')][0]
pm_path = os.path.join(r'D:\Work\shopify\source-import\new_source_from_customer', pm_file)
wb_pm = openpyxl.load_workbook(pm_path, read_only=True, data_only=True)
ws_pm = wb_pm.active
pm_rows = list(ws_pm.iter_rows(values_only=True))
headers = [str(c).strip() if c is not None else f'col_{i}' for i, c in enumerate(pm_rows[4])]

pm_by_rec = {}
pm_by_bc = {}
for r in pm_rows[5:]:
    if any(r):
        row_dict = {headers[i]: r[i] for i in range(min(len(headers), len(r)))}
        rec_id = str(row_dict.get('Record ID') or '').strip()
        bc = clean_bc(row_dict.get('Barcode'))
        if rec_id:
            pm_by_rec[rec_id] = row_dict
        if bc:
            pm_by_bc[bc] = row_dict
            pm_by_bc[bc.lstrip('0')] = row_dict

# 3. Load all vision caches
vision_data = {}
# G1 deep scan
with open('output/g1_delivery/g1_deep_scan_65_cache.json', 'r', encoding='utf-8') as f:
    g1_data = json.load(f)
    for k, v in g1_data.items():
        vision_data[k] = v

# G2 - G5
for b in ['g2', 'g3', 'g4', 'g5']:
    cpath = f'output/shopify_import/{b}_vision_cache.json'
    if os.path.exists(cpath):
        with open(cpath, 'r', encoding='utf-8') as f:
            v_dict = json.load(f)
            for k, v in v_dict.items():
                vision_data[k] = v

print(f'Total vision cached items: {len(vision_data)}')

# 4. Classify all 1659 files
matched_images = []
review_images = []

for batch, folder in src_folders.items():
    if not os.path.exists(folder):
        continue
    for fname in sorted(os.listdir(folder)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.heic']:
            continue
        v_info = vision_data.get(fname, {})
        bc = clean_bc(v_info.get('barcode'))
        rec_id = str(v_info.get('record_id') or '').strip()
        
        # Check in PM or POS
        pm_match = pm_by_bc.get(bc) or pm_by_rec.get(rec_id) or {}
        if not bc and pm_match:
            bc = clean_bc(pm_match.get('Barcode'))
        if not rec_id and pm_match:
            rec_id = str(pm_match.get('Record ID') or '').strip()

        pos_match = pos_by_bc.get(bc) or {}
        sku = pos_match.get('sku') or v_info.get('supplier_sku') or ''

        # Condition for Matched: has Barcode AND has SKU (or in PM + POS)
        if bc and sku and (pos_match or pm_match):
            matched_images.append({
                'batch': batch,
                'filename': fname,
                'barcode': bc,
                'sku': sku,
                'record_id': rec_id,
                'product_name': pos_match.get('product_name') or pm_match.get('Full name (EN)') or v_info.get('product_name'),
                'category': pos_match.get('category') or pm_match.get('Category (editorial)') or v_info.get('category')
            })
        else:
            reason = []
            if not bc:
                reason.append('Thiếu Barcode / Không đọc được mã vạch trên ảnh')
            if not sku:
                reason.append('Chưa có mã SKU trong hệ thống POS')
            if not pos_match and not pm_match:
                reason.append('Sản phẩm không có trong danh mục Master/POS')
            
            review_images.append({
                'batch': batch,
                'filename': fname,
                'barcode': bc,
                'sku': sku,
                'record_id': rec_id,
                'reason': ' & '.join(reason) if reason else 'Cần kiểm tra đối soát',
                'raw_name': v_info.get('literal_label_name') or v_info.get('product_name') or ''
            })

print(f'=== TOTAL ACCOUNTING OF 1659 RAW PHOTOS ===')
print(f'Total Raw Images Scanned: {len(matched_images) + len(review_images)}')
print(f'  1. MATCHED (Có Barcode + SKU POS/PM): {len(matched_images)}')
print(f'  2. REVIEW / UNMATCHED (Tách riêng kiểm tra): {len(review_images)}')

print('\nReview breakdown by batch:')
rev_by_b = Counter([r['batch'] for r in review_images])
for b, c in rev_by_b.items():
    print(f'  {b}: {c} review files')

print('\nSample 5 Review Images:')
for r in review_images[:5]:
    print(f'  [{r["batch"]}] {r["filename"]} -> BC: "{r["barcode"]}" | SKU: "{r["sku"]}" | Lý do: {r["reason"]}')
