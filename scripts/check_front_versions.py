import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("D:/Work/shopify")

barcodes = [
    ("4045198753174", 850),
    ("7178600000140", 886),
    ("5017689097905", 894),
    ("6922163623848", 926),
    ("8855790000028", 970)
]

print("=== Checking live front-v3 ===")
front_v3 = ROOT / "output/catalog_pairs/tagged/front-v3"
for bc, row in barcodes:
    p = front_v3 / f"{bc}-front.jpg"
    if p.exists():
        with Image.open(p) as img:
            print(f"Row {row} ({bc}): exists, size={img.size}")
    else:
        print(f"Row {row} ({bc}): DOES NOT EXIST in front-v3")

print("\n=== Checking live front-v4 ===")
front_v4 = ROOT / "output/catalog_pairs/tagged/front-v4"
for bc, row in barcodes:
    p = front_v4 / f"{bc}-front.jpg"
    if p.exists():
        with Image.open(p) as img:
            print(f"Row {row} ({bc}): exists, size={img.size}")
    else:
        print(f"Row {row} ({bc}): DOES NOT EXIST in front-v4")
