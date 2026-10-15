from PIL import Image
from pathlib import Path

ROOT = Path("D:/Work/shopify")

overlay_p = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/ready_for_user_qa_388_760_run_20261015_01/8936089503175__G2-0064__row0525-source-overlay.jpg"
cand_p = ROOT / "output/catalog_pairs/reprocess-v4/full-catalog-resolved-20261015/review/ready_for_user_qa_388_760_run_20261015_01/8936089503175__G2-0064__row0525-front.png"

if overlay_p.exists() and cand_p.exists():
    with Image.open(overlay_p) as oimg:
        print("Overlay size:", oimg.size)
    with Image.open(cand_p) as cimg:
        print("Cand size:", cimg.size)
        crop = cimg.crop((699, 144, 1700, 2255))
        crop.save(ROOT / "output/catalog_pairs/review/row525_crop.jpg", quality=90)
        print("Saved row525_crop.jpg")
