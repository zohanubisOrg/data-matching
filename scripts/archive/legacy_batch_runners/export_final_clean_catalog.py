import os
import sys
import json
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
excel_path = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
csv_path = OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv"

df = pd.read_excel(excel_path)
print(f"Loaded Master Excel with {len(df)} records.")

# Clean barcode values: remove any .0 suffixes
df['barcode'] = df['barcode'].astype(str).apply(lambda x: x[:-2] if x.endswith('.0') else x)

# Save clean excel
df.to_excel(excel_path, index=False)

# Export Shopify CSV
records = df.to_dict(orient="records")
export_shopify_csv(records, csv_path, batch_tag="G2_G5_BATCH")

print("\n================== CATALOG SUMMARY ==================")
print(f"Total Products: {len(df)}")
no_bc = df[df['barcode'].astype(str).str.startswith('NO_BARCODE')]
verified_bc = df[~df['barcode'].astype(str).str.startswith('NO_BARCODE')]
print(f"Verified Barcode Count: {len(verified_bc)}")
print(f"Remaining Non-barcode (Fresh produce/Unlabeled): {len(no_bc)}")
print(f"Shopify CSV: {csv_path}")
print(f"Master Excel: {excel_path}")
print("=====================================================")
