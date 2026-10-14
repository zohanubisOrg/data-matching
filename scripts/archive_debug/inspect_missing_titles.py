# -*- coding: utf-8 -*-
import sys
import os
import json
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"

with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    g1_cache = json.load(f)

dfs = {}
for b in ["G2", "G3", "G4", "G5"]:
    dfs[b] = pd.read_excel(os.path.join(BASE_DIR, "output\\shopify_import", f"{b}_master_products.xlsx"))

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

def not_empty(v):
    if v is None or pd.isna(v):
        return False
    s = str(v).strip()
    return s not in {"", "None", "nan", "null"}

missing_title = []
for idx, d in enumerate(all_items, start=1):
    has_t = not_empty(d.get("fuldt_navn_da")) or not_empty(d.get("product_name")) or not_empty(d.get("literal_label_name"))
    if not has_t:
        missing_title.append((idx, d.get("batch"), d.get("source_photo"), d))

print(f"Total items missing title: {len(missing_title)}")
for idx, batch, photo, d in missing_title:
    print(f"Row {idx:4d} | Batch: {batch} | Photo: {photo}")
