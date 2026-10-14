from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent

out_debug = ROOT / "output/catalog_pairs/review/debug_8"
out_debug.mkdir(parents=True, exist_ok=True)

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

import pillow_heif
pillow_heif.register_heif_opener()

for bc, p in items:
    img = Image.open(p)
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    # Save a low-res preview of the full source
    thumb = img.copy()
    thumb.thumbnail((800, 800))
    thumb.save(out_debug / f"{bc}_full.jpg")
    
    # Save left half and right half, top half and bottom half
    left = img.crop((0, 0, w//2, h))
    left.thumbnail((600, 600))
    left.save(out_debug / f"{bc}_left.jpg")
    
    right = img.crop((w//2, 0, w, h))
    right.thumbnail((600, 600))
    right.save(out_debug / f"{bc}_right.jpg")

    top = img.crop((0, 0, w, h//2))
    top.thumbnail((600, 600))
    top.save(out_debug / f"{bc}_top.jpg")

    bottom = img.crop((0, h//2, w, h))
    bottom.thumbnail((600, 600))
    bottom.save(out_debug / f"{bc}_bottom.jpg")
    
    img.close()

print("Saved previews to output/catalog_pairs/review/debug_8")
