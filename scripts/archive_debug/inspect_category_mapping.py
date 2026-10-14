# -*- coding: utf-8 -*-
import sys
import os
import json
import re
import openpyxl
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\Work\shopify"
CUSTOMER_SRC = os.path.join(BASE_DIR, "source-import", "new_source_from_customer")

# Load Categories
cat_file = os.path.join(CUSTOMER_SRC, "Ma_nhom_hang_SKU_3digits.xlsx")
wb_cat = openpyxl.load_workbook(cat_file, data_only=True)
ws_cat = wb_cat.active
nhom_map = {}
for r in list(ws_cat.iter_rows(values_only=True))[4:]:
    if r[1]:
        dansk_name = str(r[1]).strip()
        nhom_map[dansk_name] = {
            "code": str(r[2]).strip() if r[2] else "",
            "vi": str(r[3]).strip() if r[3] else "",
            "is_online": str(r[5]).strip().lower() != "nej",
        }

print("16 POS Categories:", list(nhom_map.keys()))

CATEGORY_TRANSLATION = {
    "snacks": "Snack",
    "snack": "Snack",
    "candy": "Snack",
    "sweets": "Snack",
    "cookies": "Snack",
    "condiments": "Saucer",
    "sauce": "Saucer",
    "sauces": "Saucer",
    "beverage": "Drikkevarer",
    "beverages": "Drikkevarer",
    "drinks": "Drikkevarer",
    "tea": "Drikkevarer",
    "noodles": "Nudler",
    "noodle": "Nudler",
    "ramen": "Nudler",
    "pasta": "Nudler",
    "spices": "Krydderier",
    "seasoning": "Krydderier",
    "canned": "Konserves",
    "canned goods": "Konserves",
    "flour": "Mel",
    "beans": "Bønner",
    "rice": "Ris",
    "vegetables": "Grøntsager",
    "fruit": "Frugt",
    "dairy": "Mælk",
    "frozen": "Frostvarer",
    "fish": "Fisk",
    "seafood": "Diverse",
}

def map_category(raw_cat, title=""):
    if not raw_cat:
        raw_cat = ""
    rc = str(raw_cat).lower().strip()
    if rc in CATEGORY_TRANSLATION:
        return CATEGORY_TRANSLATION[rc]
    for k, v in CATEGORY_TRANSLATION.items():
        if k in rc:
            return v
    # Check title hints
    t_low = str(title).lower()
    if any(w in t_low for w in ["noodle", "ramen", "udon", "vermicelli", "mì", "mi ", "phở", "bún"]):
        return "Nudler"
    if any(w in t_low for w in ["sauce", "paste", "soya", "dip", "sriracha", "chili sauce"]):
        return "Saucer"
    if any(w in t_low for w in ["snack", "chip", "cracker", "biscuit", "candy", "gummy", "jelly", "seaweed"]):
        return "Snack"
    if any(w in t_low for w in ["drink", "juice", "tea", "soda", "beverage", "water", "milk"]):
        return "Drikkevarer"
    if any(w in t_low for w in ["spice", "curry", "powder", "seasoning", "pepper"]):
        return "Krydderier"
    if any(w in t_low for w in ["canned", "paste", "coconut milk"]):
        return "Konserves"
    return "Diverse"

print("Category test mapping:")
for test in ["Snacks", "Condiments", "Beverages", "Instant Noodles", "Canned Food", "Unknown"]:
    print(f"  {test} -> {map_category(test)}")
