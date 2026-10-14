# -*- coding: utf-8 -*-
import sys
import os
import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
SRC_DIR = os.path.join(BASE_DIR, "source-import", "new_source_from_customer")

pm_file = [f for f in os.listdir(SRC_DIR) if f.startswith("Product_master") and f.endswith(".xlsx") and not f.startswith("~$")][0]
pm_path = os.path.join(SRC_DIR, pm_file)
wb_pm = openpyxl.load_workbook(pm_path, read_only=True, data_only=True)
ws_pm = wb_pm.active

rows_pm = list(ws_pm.iter_rows(values_only=True))
headers_89 = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(rows_pm[4])]

print(f"89 Standard Headers from {pm_file}:")
for i, h in enumerate(headers_89):
    print(f"Col {i+1:2d} (Index {i:2d}): {h}")
