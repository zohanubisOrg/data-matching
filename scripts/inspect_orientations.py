import json
from pathlib import Path
from PIL import Image

ROOT = Path("D:/Work/shopify")

# Inspect Carabao 970
cand_970 = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/8855790000028__G3-0080__row0970-front.png"
src_970 = ROOT / "output/catalog_pairs/originals/8855790000028/G3_Original_IMG_1263.jpeg"

with Image.open(src_970) as img:
    print(f"Source 970 size: {img.size}")
    # check EXIF orientation if any
    exif = img.getexif()
    print("Source EXIF tags:", {k: exif[k] for k in exif if k in (274, 305, 306)})

with Image.open(cand_970) as img:
    print(f"Cand 970 size: {img.size}")

# Let's save a crop of the top and bottom of Carabao candidate to check if text is upside down
cand_img = Image.open(cand_970)
# crop non-white area
cand_cropped = cand_img.crop((524, 487, 1874, 1912))
cand_cropped.save(ROOT / "output/catalog_pairs/review/carabao_crop.jpg", quality=90)

# Check Oolong tea 926
cand_926 = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/render_native_scale_scan_926_970_v2/6922163623848__G3-0025__row0926-front.png"
cand_img_926 = Image.open(cand_926)
cand_cropped_926 = cand_img_926.crop((651, 553, 1747, 1845))
cand_cropped_926.save(ROOT / "output/catalog_pairs/review/oolong_crop.jpg", quality=90)

print("Saved carabao_crop.jpg and oolong_crop.jpg")
