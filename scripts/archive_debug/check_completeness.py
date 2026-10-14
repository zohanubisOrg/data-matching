# -*- coding: utf-8 -*-
import sys
import os
import json
import pandas as pd
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"

# Load G1
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    g1_cache = json.load(f)

# Load G2-G5
dfs = {}
for b in ["G2", "G3", "G4", "G5"]:
    dfs[b] = pd.read_excel(os.path.join(BASE_DIR, "output\\shopify_import", f"{b}_master_products.xlsx"))

# Merge all 1659
all_items = []
for fname, item in g1_cache.items():
    d = dict(item)
    d["batch"] = "G1"
    d["source_photo"] = fname
    all_items.append(d)

for b in ["G2", "G3", "G4", "G5"]:
    for _, row in dfs[b].iterrows():
        d = row.to_dict()
        d["batch"] = b
        all_items.append(d)

print(f"Total items loaded: {len(all_items)}")

# Count non-empty fields
has_brand = 0
has_title_da = 0
has_title_en = 0
has_net_qty = 0
has_ing = 0
has_nutrition = 0

def not_empty(v):
    if v is None or pd.isna(v):
        return False
    s = str(v).strip()
    return s not in {"", "None", "nan", "null"}

for d in all_items:
    if not_empty(d.get("brand")):
        has_brand += 1
    if not_empty(d.get("fuldt_navn_da")) or not_empty(d.get("product_name")):
        has_title_da += 1
    if not_empty(d.get("full_name_en")) or not_empty(d.get("product_name")):
        has_title_en += 1
    if not_empty(d.get("net_quantity")) or not_empty(d.get("net_weight")):
        has_net_qty += 1
    if not_empty(d.get("ingredienser_da")) or not_empty(d.get("ingredients_en")):
        has_ing += 1
    if not_empty(d.get("energy_kcal")) or not_empty(d.get("energy_kj")):
        has_nutrition += 1

print("\nCompleteness across all 1,659 records:")
print(f"  - Brand: {has_brand} / 1659 ({has_brand/1659*100:.1f}%)")
print(f"  - Danish Title: {has_title_da} / 1659 ({has_title_da/1659*100:.1f}%)")
print(f"  - English Title: {has_title_en} / 1659 ({has_title_en/1659*100:.1f}%)")
print(f"  - Net Quantity: {has_net_qty} / 1659 ({has_net_qty/1659*100:.1f}%)")
print(f"  - Ingredients: {has_ing} / 1659 ({has_ing/1659*100:.1f}%)")
print(f"  - Nutrition: {has_nutrition} / 1659 ({has_nutrition/1659*100:.1f}%)")
