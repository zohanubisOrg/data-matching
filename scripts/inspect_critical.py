import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from product_mapper.vision.barcode_side_splitter import scan_file, split_sides

items = [
    ("4045198900905", "source-import/G3_Original/IMG_1496.jpeg"),
    ("4045198903944", "source-import/G3_Original/IMG_1491.jpeg"),
    ("4045198927490", "source-import/G3_Original/IMG_1502.jpeg"),
    ("6920339004118", "source-import/G1_original/IMG_9986.jpeg"),
    ("6947593021071", "source-import/G1_original/IMG_0229.jpeg"),
    ("8720812773849", "source-import/G1_original/IMG_9955.jpeg"),
    ("8936116500610", "source-import/G3_Original/IMG_1474.jpeg"),
    ("8990044000017", "source-import/G1_original/IMG_9997.jpeg"),
]

for barcode, rel_path in items:
    src_p = ROOT / rel_path
    if not src_p.exists():
        print(f"Missing source: {src_p}")
        continue
    img = Image.open(src_p)
    w, h = img.size
    print(f"\n=======================================================")
    print(f"Barcode: {barcode} | Source: {rel_path} | Size: {w}x{h}")
    scan_res = scan_file(src_p)
    print(f"Scan barcode: {scan_res.get('barcode')}, center={scan_res.get('center')}, angle={scan_res.get('angle')}")
    
    # Check what is currently in front-v2
    front_p = ROOT / f"output/catalog_pairs/tagged/front-v2/{barcode}-front.jpg"
    if front_p.exists():
        f_im = Image.open(front_p)
        hits = zxingcpp.read_barcodes(f_im, formats=zxingcpp.BarcodeFormat.EANUPC)
        b_hits = [h.text for h in hits]
        print(f"Current front-v2 size: {f_im.size}, barcodes found on front: {b_hits}")
