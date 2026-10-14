import pandas as pd
import json
import os
from pathlib import Path

excel_path = "output/shopify_import/Master_G2_G5_Consolidated.xlsx"
df = pd.read_excel(excel_path)
print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")

no_bc = df[df['barcode'].astype(str).str.contains('NO_BARCODE|nan|^$', case=False, na=True)]
print(f"\n--- NO_BARCODE COUNT: {len(no_bc)} ---")
for idx, r in no_bc.iterrows():
    print(f"Batch: {r.get('batch')}, Barcode: {r.get('barcode')}, Photo: {r.get('source_photo')}, Name: {r.get('product_name')}")

test_codes = ['8716789006523', '12415762', '4016337900254', '8858306001489', '8888296019010', '8901161105066', '8934563138165', '8936116500610']
print("\n--- SPECIFIC TARGET BARCODES CHECK ---")
for tc in test_codes:
    matched = df[df['barcode'].astype(str).str.contains(tc)]
    if len(matched) > 0:
        for _, row in matched.iterrows():
            print(f"Matched {tc}: Batch={row.get('batch')}, Photo={row.get('source_photo')}, Name={row.get('product_name')}, FrontBox={row.get('front_box_2d')}, BackBox={row.get('back_box_2d')}, BarcodeBox={row.get('barcode_box_2d')}")
    else:
        print(f"Barcode {tc} NOT FOUND in Master Excel")
