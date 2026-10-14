import sys
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from product_mapper.vision.barcode_side_splitter import read_retail_barcodes
from product_mapper.ingestion.image_loader import open_image_safely

items = [
    ("084909006608", ROOT / "source-import/G1_original/IMG_0350.jpeg"),
    ("8720812774334", ROOT / "source-import/G1_original/IMG_0027.jpeg"),
    ("8850060110063", ROOT / "source-import/G4-original/20260916_112840856_iOS.heic"),
    ("8850060110551", ROOT / "source-import/G4-original/20260916_111222616_iOS.heic"),
    ("8850060110834", ROOT / "source-import/G4-original/20260916_111118920_iOS.heic"),
    ("8850060444458", ROOT / "source-import/G4-original/20260916_111329184_iOS.heic"),
    ("8854923313301", ROOT / "source-import/G1_original/IMG_0042.jpeg"),
    ("8938500969928", ROOT / "source-import/G1_original/IMG_0308.jpeg"),
]

for bc, src in items:
    print("=" * 70)
    print(f"Barcode: {bc}")
    print(f"Source file: {src} (exists: {src.exists()})")
    if not src.exists(): continue
    img = open_image_safely(src)
    w, h = img.size
    print(f"Image size: {w}x{h}")
    hits = read_retail_barcodes(img)
    for hit in hits:
        print(f"  Barcode found: {hit.text} at cx={hit.center_x:.1f} ({hit.center_x/w:.3f}), cy={hit.center_y:.1f} ({hit.center_y/h:.3f}), angle={hit.angle:.1f}, area={hit.area:.1f}")

    err_back = ROOT / f"output/catalog_pairs/image-error-resolve-again/{bc}-back.jpg"
    if err_back.exists():
        eb_img = open_image_safely(err_back)
        print(f"Error back image size: {eb_img.size}")
        eb_hits = read_retail_barcodes(eb_img)
        print(f"  Barcodes in error back: {[h.text for h in eb_hits]}")
        eb_img.close()

    front_img = ROOT / f"output/catalog_pairs/tagged/front-v2/{bc}-front.jpg"
    if front_img.exists():
        f_img = open_image_safely(front_img)
        print(f"Current front-v2 size: {f_img.size}")
        f_hits = read_retail_barcodes(f_img)
        print(f"  Barcodes in front-v2: {[h.text for h in f_hits]}")
        f_img.close()
    img.close()
