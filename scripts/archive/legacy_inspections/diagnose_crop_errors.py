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
import pandas as pd
from PIL import Image

# Load g2_g5_front_boxes.json to compare
box_cache = {}
if os.path.exists("output/shopify_import/g2_g5_front_boxes.json"):
    with open("output/shopify_import/g2_g5_front_boxes.json", "r", encoding="utf-8") as f:
        box_cache = json.load(f)
print(f"Loaded box_cache with {len(box_cache)} items")

# Load HD studio summary
summary_path = "output/reconciliation/HD_Studio_Crop_QC_Summary.json"
hd_summary = {}
if os.path.exists(summary_path):
    with open(summary_path, "r", encoding="utf-8") as f:
        hd_summary = json.load(f)
print(f"Loaded hd_summary with {len(hd_summary.get('results', []))} sample results")

# Check a sample of cropped images
crop_dir = Path("output/shopify_import_final/HD_Studio_Front_Images")
files = list(crop_dir.glob("*.jpg"))
print(f"Total cropped files in HD_Studio_Front_Images: {len(files)}")

# Look at box_cache vs cv_front_detector for some items
sys.path.insert(0, ".")
from scripts.cv_front_detector import detect_front_box_cv
from scripts.hd_studio_crop_pipeline import build_raw_file_index, load_master_items

raw_index = build_raw_file_index()
print(f"Total raw files indexed: {len(raw_index)}")

items = load_master_items(0)
print(f"Total master items: {len(items)}")

# Let's inspect 20 items where box_cache exists
mismatches = []
for item in items[:200]:
    raw_p = Path(item["raw_path"])
    fname = raw_p.name
    cv_box, _, cv_label = detect_front_box_cv(raw_p)
    cached = box_cache.get(fname, {})
    cached_box = cached.get("front_box_2d")
    cached_pos = cached.get("front_position")
    
    if cached_box:
        # Check IoU or difference
        # cached_box is [ymin, xmin, ymax, xmax]
        # cv_box is [ymin, xmin, ymax, xmax]
        diff_x = abs(cv_box[1] - cached_box[1]) + abs(cv_box[3] - cached_box[3])
        if diff_x > 300: # large difference on horizontal panel!
            mismatches.append({
                "stt": item["stt"],
                "barcode": item["barcode"],
                "fname": fname,
                "cv_box": cv_box,
                "cv_label": cv_label,
                "cached_box": cached_box,
                "cached_pos": cached_pos,
                "brand_and_name": cached.get("brand_and_name")
            })

print(f"\nFound {len(mismatches)} severe box mismatches in first 200 items:")
for m in mismatches[:15]:
    print(f"  STT {m['stt']} | {m['barcode']} | File: {m['fname']}")
    print(f"    CV Label:   {m['cv_label']} -> box: {m['cv_box']}")
    print(f"    Cached AI:  pos: {m['cached_pos']} -> box: {m['cached_box']} ({m['brand_and_name']})")
