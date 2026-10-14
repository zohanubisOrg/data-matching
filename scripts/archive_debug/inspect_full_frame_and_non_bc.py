import os
import sys
import json
from pathlib import Path
import pandas as pd
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.ingestion.image_loader import open_image_safely

OUTPUT_DIR = PROJECT_ROOT / "output/shopify_import"
excel_path = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
df = pd.read_excel(excel_path)

# Check the 11 non-barcode items
no_bc = df[df['barcode'].astype(str).str.startswith('NO_BARCODE')]
print(f"--- 11 NON-BARCODE ITEMS ({len(no_bc)}) ---")
for idx, r in no_bc.iterrows():
    print(f"Row {idx} | Batch: {r['batch']} | Photo: {r['source_photo']} | Name: {r['product_name']} | Box: {r['front_box_2d']}")

# Check any other items with full frame [0, 0, 1000, 1000] that might have multiple objects side-by-side
full_frame = df[df['front_box_2d'].astype(str).str.contains('\\[0, 0, 1000, 1000\\]')]
print(f"\n--- FULL FRAME ITEMS ({len(full_frame)}) ---")
for idx, r in full_frame.iterrows():
    print(f"Row {idx} | Batch: {r['batch']} | BC: {r['barcode']} | Photo: {r['source_photo']} | Name: {r['product_name']}")
