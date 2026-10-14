import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from PIL import Image
import glob

test_barcodes = ["8934563709150", "8934563107161", "6926410320160", "8850157516457", "8809705070521"]

# find raw photos for these barcodes in source-import
for bc in test_barcodes:
    print(f"\n================ BARCODE: {bc} ================")
    # find cropped image
    cropped_p = f"output/shopify_import_final/HD_Studio_Front_Images/{bc}.jpg"
    if os.path.exists(cropped_p):
        with Image.open(cropped_p) as im:
            print(f"  Cropped Studio Image: {cropped_p} (size: {im.size})")
    else:
        print(f"  Cropped Studio Image: NOT FOUND")

    # find raw images
    raw_matches = []
    for root, _, files in os.walk("source-import"):
        for f in files:
            if bc in f:
                raw_matches.append(os.path.join(root, f))
    print(f"  Raw matches by barcode string ({len(raw_matches)}):")
    for r in raw_matches[:5]:
        with Image.open(r) as im:
            print(f"    - {r} (size: {im.size})")
