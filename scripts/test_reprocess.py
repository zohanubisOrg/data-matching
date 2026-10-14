import sys
from pathlib import Path
import numpy as np
import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from product_mapper.vision.barcode_side_splitter import (
    scan_file, packshot_front, enhance_back
)
from audit_front_v2 import audit_single_image

test_cases = [
    ("6947593021071", "source-import/G1_original/IMG_0229.jpeg"),
    ("8886390204011", "source-import/G1_original/IMG_0239.jpeg"),
    ("8990044000017", "source-import/G1_original/IMG_9997.jpeg"),
    ("6920339004118", "source-import/G1_original/IMG_9986.jpeg"),
    ("4045198903944", "source-import/G3_Original/IMG_1491.jpeg"),
]

def find_best_vertical_cut(im: Image.Image) -> int:
    w, h = im.size
    small = im.resize((600, int(600 * h / w)))
    arr = np.asarray(small)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    profile = np.convolve(edges.mean(axis=0), np.ones(15) / 15.0, mode="same")
    
    # Tìm thung lũng (min edge) trong khoảng 0.40 - 0.60
    sw = small.size[0]
    low = int(sw * 0.40)
    high = int(sw * 0.60)
    best_idx = low + int(np.argmin(profile[low:high]))
    return int(best_idx * (w / sw))

for bc, rel in test_cases:
    src_p = ROOT / rel
    im = Image.open(src_p)
    w, h = im.size
    res = scan_file(src_p)
    cx, cy = res.get("center", [w * 0.5, h * 0.5])
    
    cut_x = find_best_vertical_cut(im)
    
    if cx > cut_x:
        # Barcode ở bên phải => Mặt trước ở bên trái
        front_box = (0, 0, cut_x, h)
        back_box = (cut_x, 0, w, h)
        mode = "back_right"
    else:
        # Barcode ở bên trái => Mặt trước ở bên phải
        front_box = (cut_x, 0, w, h)
        back_box = (0, 0, cut_x, h)
        mode = "back_left"
    
    print(f"\n[{bc}] Cut X: {cut_x}/{w} ({round(cut_x/w, 2)}) | Mode: {mode}")
    front_crop = im.crop(front_box)
    print(f"Front crop size: {front_crop.size}, AR: {round(front_crop.size[0] / front_crop.size[1], 2)}")
    packshot = packshot_front(front_crop)
    print(f"Packshot size: {packshot.size}")
    
    # Test audit
    temp_path = ROOT / f"output/catalog_pairs/tagged/front-v2/_test_{bc}-front.jpg"
    packshot.save(temp_path, "JPEG", quality=95)
    audit_res = audit_single_image(str(temp_path))
    print(f"Audit result: severity={audit_res['severity']}, reasons={audit_res['reasons']}, AR={audit_res.get('aspect_ratio')}")
    temp_path.unlink()
