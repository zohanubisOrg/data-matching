# -*- coding: utf-8 -*-
import sys
import os
import json
import pandas as pd
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"

caches = {}
with open(os.path.join(BASE_DIR, r"output\g1_delivery\g1_deep_scan_65_cache.json"), "r", encoding="utf-8") as f:
    caches["G1"] = json.load(f)
for b in ["g2", "g3", "g4", "g5"]:
    with open(os.path.join(BASE_DIR, f"output\\shopify_import\\{b}_vision_cache.json"), "r", encoding="utf-8") as f:
        caches[b.upper()] = json.load(f)

# Sample 20 OCR resolved items across batches
sample_rows = []
for batch in ["G1", "G2", "G3", "G4", "G5"]:
    for photo, c in list(caches[batch].items())[:5]:
        sample_rows.append((
            batch,
            photo,
            c.get("brand"),
            c.get("fuldt_navn_da") or c.get("product_name"),
            c.get("full_name_en") or c.get("product_name"),
            f"{c.get('net_quantity')} {c.get('net_unit')}",
            c.get("category"),
            c.get("energy_kcal") or c.get("energy_kj"),
            bool(c.get("ingredienser_da") or c.get("ingredients_en"))
        ))

print(f"{'Batch':<5} | {'Photo':<16} | {'Brand':<15} | {'Net W':<10} | {'Nutrition':<10} | {'Ing?':<5} | {'Danish Title'}")
print("-" * 110)
for r in sample_rows:
    print(f"{r[0]:<5} | {r[1]:<16} | {str(r[2])[:14]:<15} | {str(r[5])[:9]:<10} | {str(r[7])[:9]:<10} | {str(r[8]):<5} | {str(r[3])[:45]}")
