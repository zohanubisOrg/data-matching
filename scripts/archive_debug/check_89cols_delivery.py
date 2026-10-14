# -*- coding: utf-8 -*-
import sys
import os
import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
f = os.path.join(BASE_DIR, r"output\shopify_import_final\Master_All_Products_89cols_With_Images.xlsx")

print("Checking:", f, "Exists:", os.path.exists(f))
if os.path.exists(f):
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    print("Total rows in 89cols file:", len(rows))
    if len(rows) > 4:
        print("Headers row (row 5):", [str(c).strip() if c is not None else "" for c in rows[4]])
        print("Sample data row 6:", len(rows[5]) if len(rows) > 5 else 0)
