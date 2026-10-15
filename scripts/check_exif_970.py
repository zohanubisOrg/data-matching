import json
from pathlib import Path
from PIL import Image, ImageOps
import sys

ROOT = Path("D:/Work/shopify")
src_970 = ROOT / "output/catalog_pairs/originals/8855790000028/G3_Original_IMG_1263.jpeg"
cand_970 = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/8855790000028__G3-0080__row0970-front.png"

with Image.open(src_970) as img:
    print("Raw source size:", img.size)
    transposed = ImageOps.exif_transpose(img)
    print("Exif transposed size:", transposed.size)
    print("Raw exif orientation:", img.getexif().get(274))

# Let's check candidate 970
with Image.open(cand_970) as img:
    print("Cand size:", img.size)
