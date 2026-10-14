# -*- coding: utf-8 -*-
import sys
import os
import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
f = os.path.join(BASE_DIR, r"output\shopify_import_final\Master_All_1659_Products_With_Images.xlsx")

wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))

print("Total rows in file:", len(rows))
headers = rows[2] # row 3
print(f"Total columns in file: {len(headers)}")
print(f"Headers 1 to 10: {headers[:10]}")
print(f"Headers 40 to 50 (Nutrition): {headers[40:50]}")
print(f"Headers last 10 (POS & Delivery): {headers[-10:]}")
print("\nSample Data Row 4:")
print("  STT:", rows[3][0])
print("  Barcode:", rows[3][2])
print("  EN Name:", rows[3][3])
print("  DA Name:", rows[3][4])
print("  Brand:", rows[3][5])
print("  SKU Code:", rows[3][88])
print("  Price:", rows[3][87])
print("  Category:", rows[3][86])
