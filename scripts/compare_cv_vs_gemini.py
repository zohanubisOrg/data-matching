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
from PIL import Image

sys.path.insert(0, ".")
from scripts.cv_front_detector import detect_front_box_cv

box_cache = {}
if os.path.exists("output/shopify_import/g2_g5_front_boxes.json"):
    with open("output/shopify_import/g2_g5_front_boxes.json", "r", encoding="utf-8") as f:
        box_cache = json.load(f)

test_files = [
    ("STT 704 Hảo Hảo Gà", "source-import/G2_original/IMG_0680.jpeg"),
    ("STT 747 Hảo Hảo Tôm chua cay", "source-import/G2_original/IMG_0725.jpeg"),
    ("STT 668 A-Kuan", "source-import/G2_original/IMG_0642.jpeg"),
    ("STT 1 Dorkbua", "source-import/G1_original/IMG_0002.jpeg")
]

for label, p_str in test_files:
    p = Path(p_str)
    if not p.exists():
        print(f"File not found: {p}")
        continue
    with Image.open(p) as im:
        w, h = im.size
    fname = p.name
    cv_box, rot, cv_label = detect_front_box_cv(p)
    cached = box_cache.get(fname, {})
    
    print(f"\n=== {label} ({fname}) ===")
    print(f"  Image size: {w}x{h}")
    print(f"  CV Detector Box:     {cv_box} | Label: {cv_label}")
    print(f"  Cached Gemini AI:    {cached.get('front_box_2d')} | Pos: {cached.get('front_position')} | Upright Rot: {cached.get('front_rotation_to_upright')}")
    print(f"  Cached Brand/Name:   {cached.get('brand_and_name')}")
