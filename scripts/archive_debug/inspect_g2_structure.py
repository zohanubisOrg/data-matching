# -*- coding: utf-8 -*-
import sys
import os
import json
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"

with open(os.path.join(BASE_DIR, r"output\shopify_import\g2_vision_cache.json"), "r", encoding="utf-8") as f:
    g2_cache = json.load(f)

print(f"Total entries in g2_vision_cache: {len(g2_cache)}")
k0 = list(g2_cache.keys())[0]
print(f"Sample key: {k0}")
print(f"Sample data: {json.dumps(g2_cache[k0], indent=2, ensure_ascii=False)}")

df_g2 = pd.read_excel(os.path.join(BASE_DIR, r"output\shopify_import\G2_master_products.xlsx"))
print("\nG2_master_products columns:", list(df_g2.columns))
print("G2 sample row 0:", df_g2.iloc[0].to_dict())
