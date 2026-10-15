from PIL import Image
import numpy as np
from pathlib import Path

ROOT = Path("D:/Work/shopify")
cand_970 = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/8855790000028__G3-0080__row0970-front.png"

img = Image.open(cand_970).convert("RGB")
arr = np.asarray(img)

# Product is between y: 487 to 1912, x: 524 to 1874
top_quarter = arr[487:487+350, 524:1874]
bottom_quarter = arr[1912-350:1912, 524:1874]

# Can opening/rim is metallic silver / circular or pull tab, let's see colors
print("Top quarter mean RGB:", top_quarter.mean(axis=(0,1)))
print("Bottom quarter mean RGB:", bottom_quarter.mean(axis=(0,1)))

# Let's save small top and bottom slices
Image.fromarray(top_quarter).save(ROOT / "output/catalog_pairs/review/carabao_top.jpg")
Image.fromarray(bottom_quarter).save(ROOT / "output/catalog_pairs/review/carabao_bottom.jpg")
print("Saved carabao_top.jpg and carabao_bottom.jpg")
