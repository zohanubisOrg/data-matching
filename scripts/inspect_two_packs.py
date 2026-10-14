import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from product_mapper.vision.barcode_side_splitter import scan_file, split_sides

items = [
    ("4045198903944", "source-import/G3_Original/IMG_1491.jpeg"),
    ("4045198927490", "source-import/G3_Original/IMG_1502.jpeg"),
    ("6920339004118", "source-import/G1_original/IMG_9986.jpeg"),
    ("6947593021071", "source-import/G1_original/IMG_0229.jpeg"),
    ("8720812773849", "source-import/G1_original/IMG_9955.jpeg"),
    ("8936116500610", "source-import/G3_Original/IMG_1474.jpeg"),
    ("8990044000017", "source-import/G1_original/IMG_9997.jpeg"),
]

for bc, rel in items:
    p = ROOT / rel
    im = Image.open(p)
    w, h = im.size
    res = scan_file(p)
    cx, cy = res.get("center", [0, 0])
    sides = split_sides(im, cx, cy, 0)
    print(f"=== {bc} ({rel}) {w}x{h} ===", flush=True)
    print(f"Barcode center: {cx}, {cy} ({round(cx/w, 2)}, {round(cy/h, 2)})", flush=True)
    print(f"Split mode: {sides.mode}, back: {sides.back}, front: {sides.front}", flush=True)
