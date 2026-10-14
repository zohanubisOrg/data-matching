import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd
import json

df = pd.read_excel("output/reconciliation/Shopify_Live_Catalog_Full_Audit.xlsx")
print(f"Total live audit rows: {len(df)}")
print("Sample of 15 products with image URLs:")
for idx, r in df.head(15).iterrows():
    p_id = r.get("Product_ID")
    title = r.get("Title")
    bc = r.get("Variant_Barcode")
    img_url = r.get("Primary_Image_URL")
    print(f"[{idx+1}] ID: {p_id} | BC: {bc} | Title: {title[:45]}")
    print(f"    Image URL: {img_url}")
