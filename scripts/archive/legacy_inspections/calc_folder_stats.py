# -*- coding: utf-8 -*-
import sys
import os
import openpyxl
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
f = os.path.join(BASE_DIR, r"output\shopify_import_final\Master_All_1659_Products_With_Images.xlsx")

wb = openpyxl.load_workbook(f, data_only=True)
ws = wb.active
headers = [c.value for c in ws[3]]
rows = list(ws.iter_rows(min_row=4, values_only=True))

batch_counts = Counter()
batch_verified = Counter()
batch_reshoot = Counter()
batch_online = Counter()

for r in rows:
    d = dict(zip(headers, r))
    batch = d.get("Thư mục nguồn (Batch)")
    bc = str(d.get("Barcode") or "").strip()
    sku = str(d.get("POS SKU") or "").strip()
    status = str(d.get("Trạng thái đối soát") or "").strip()
    is_online = (d.get("Trạng thái Online") == "Online")
    
    batch_counts[batch] += 1
    if "KHÔNG CÓ MÃ VẠCH" in status or not bc:
        batch_reshoot[batch] += 1
    else:
        batch_verified[batch] += 1
        
    if is_online and bc and sku:
        batch_online[batch] += 1

print(f"{'Folder / Batch':<15} | {'Tổng ảnh':<10} | {'Có Barcode & SKU':<20} | {'Cần chụp lại':<15} | {'Bán Online':<12} | {'Tỷ lệ khớp'}")
print("-" * 90)
for b in ["G1", "G2", "G3", "G4", "G5"]:
    tot = batch_counts[b]
    ver = batch_verified[b]
    res = batch_reshoot[b]
    onl = batch_online[b]
    rate = (ver / tot * 100) if tot else 0
    print(f"{b:<15} | {tot:<10} | {ver:<20} | {res:<15} | {onl:<12} | {rate:.1f}%")

print("-" * 90)
tot_all = sum(batch_counts.values())
ver_all = sum(batch_verified.values())
res_all = sum(batch_reshoot.values())
onl_all = sum(batch_online.values())
print(f"{'TỔNG CỘNG':<15} | {tot_all:<10} | {ver_all:<20} | {res_all:<15} | {onl_all:<12} | {ver_all/tot_all*100:.1f}%")
