import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path
import json
import openpyxl

# Load caches
g1_cache = {}
if os.path.exists("output/g1_delivery/front_layout_boxes.json"):
    with open("output/g1_delivery/front_layout_boxes.json", "r", encoding="utf-8") as f:
        g1_cache = json.load(f)

g2_g5_cache = {}
if os.path.exists("output/shopify_import/g2_g5_front_boxes.json"):
    with open("output/shopify_import/g2_g5_front_boxes.json", "r", encoding="utf-8") as f:
        g2_g5_cache = json.load(f)

print(f"G1 cache count:    {len(g1_cache)}")
print(f"G2-G5 cache count: {len(g2_g5_cache)}")

# Combine caches
combined_cache = {}
for k, v in g1_cache.items():
    combined_cache[k.lower()] = {
        "box": v.get("front_box_2d"),
        "rot": v.get("front_rotation", 0),
        "pos": v.get("front_side_position", "unknown"),
        "source": "G1_verified"
    }

for k, v in g2_g5_cache.items():
    combined_cache[k.lower()] = {
        "box": v.get("front_box_2d"),
        "rot": v.get("front_rotation_to_upright", 0),
        "pos": v.get("front_position", "unknown"),
        "source": "G2_G5_verified"
    }

print(f"Combined verified cache count: {len(combined_cache)}")

# Check against master 1659 items
sys.path.insert(0, ".")
from scripts.hd_studio_crop_pipeline import build_raw_file_index

raw_index = build_raw_file_index()
print(f"Raw index count: {len(raw_index)}")

wb = openpyxl.load_workbook("source-import/new_source_from_customer/11-10-new-requirment/Esbjerg_Asian_Market_Master_1659_updated.xlsx", data_only=True, read_only=True)
sheet = wb.active

found_in_cache = 0
missing_in_cache = []
items_by_group = {}

for r in list(sheet.iter_rows(values_only=True))[3:]:
    stt = r[0]
    bc = str(r[2] or "").strip()
    selected_front = str(r[67] or "").strip()
    fname = os.path.basename(selected_front).lower()
    
    group = selected_front.split("/")[0] if "/" in selected_front else "unknown"
    items_by_group[group] = items_by_group.get(group, 0) + 1
    
    if fname in combined_cache and combined_cache[fname]["box"]:
        found_in_cache += 1
    else:
        missing_in_cache.append((stt, bc, selected_front, fname))

print(f"\nMaster 1659 coverage with AI/Human-verified front boxes:")
print(f"  Total items:          1659")
print(f"  Found verified box:   {found_in_cache} ({found_in_cache/1659*100:.1f}%)")
print(f"  Missing verified box: {len(missing_in_cache)} ({len(missing_in_cache)/1659*100:.1f}%)")

if missing_in_cache:
    print(f"\nSample of missing items ({len(missing_in_cache)}):")
    for m in missing_in_cache[:10]:
        print(f"  STT {m[0]} | BC: {m[1]} | Selected: {m[2]} | Filename: {m[3]}")
