import cv2
import numpy as np
from pathlib import Path

ROOT = Path(r"D:\Work\shopify")
CHECK_DIR = ROOT / "output/catalog_pairs/tagged/g2-barcode-check"
OUT_DIR = ROOT / "output/catalog_pairs/review/g2_special_crops"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Define crops for each item: (file, barcode, front_box_frac, back_box_frac, rotate_back_180)
# box_frac = (ymin, xmin, ymax, xmax)
CROP_SPECS = [
    {
        "file": "IMG_0443.jpeg",
        "barcode": "4316734096117",
        "name": "Cholimex Chili Sauce with Garlic",
        # Center bottle: front
        "front_box": (0.10, 0.33, 0.94, 0.65),
        # Right bottle: back
        "back_box": (0.10, 0.65, 0.94, 0.98),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0445.jpeg",
        "barcode": "8936147330170",
        "name": "Double Panda Mild Spring Roll Dipping Sauce",
        # Left bottle: front
        "front_box": (0.09, 0.15, 0.96, 0.48),
        # Right bottle: back
        "back_box": (0.09, 0.51, 0.96, 0.83),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0588.jpeg",
        "barcode": "8850030035082",
        "name": "Lobo Roast Red Pork Seasoning Mix",
        # Left pouch: front
        "front_box": (0.07, 0.02, 0.86, 0.45),
        # Right pouch: back
        "back_box": (0.04, 0.48, 0.93, 0.97),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0659.jpeg",
        "barcode": "8850100003713",
        "name": "Wai Wai Quick Shrimp chilli lime flavour noodles",
        # Left package: front
        "front_box": (0.16, 0.01, 0.73, 0.51),
        # Right package: back (upside down, rotate 180)
        "back_box": (0.19, 0.51, 0.75, 0.98),
        "rotate_back": 180,
    },
    {
        "file": "IMG_0665.jpeg",
        "barcode": "8850987128158",
        "name": "MAMA Tom Yum Pork Flavour Instant Noodles",
        # Right package: front
        "front_box": (0.21, 0.55, 0.90, 0.97),
        # Left package: back
        "back_box": (0.19, 0.05, 0.88, 0.49),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0772.jpeg",
        "barcode": "8936007820544",
        "name": "Bamboo Tree fine rice vermicelli",
        # Right package: front
        "front_box": (0.04, 0.57, 0.97, 0.92),
        # Left package: back
        "back_box": (0.02, 0.16, 0.93, 0.51),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0825.jpeg",
        "barcode": "8850931040680",
        "name": "Madame Wong long life noodles with turmeric",
        # Right package: front
        "front_box": (0.14, 0.46, 0.79, 0.98),
        # Left package: back
        "back_box": (0.17, 0.01, 0.78, 0.46),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0835.jpeg",
        "barcode": "8936062107994",
        "name": "Dafood cinnamon, star anise and black cardamom",
        # Right pouch: front
        "front_box": (0.04, 0.49, 0.98, 0.99),
        # Left pouch: back
        "back_box": (0.06, 0.01, 0.95, 0.48),
        "rotate_back": 0,
    },
    {
        "file": "IMG_0839.jpeg",
        "barcode": "8717624005060",
        "name": "Nature's Best Harvest dried lotus seeds",
        # Right pouch: front
        "front_box": (0.06, 0.48, 0.95, 0.98),
        # Left pouch: back
        "back_box": (0.06, 0.01, 0.96, 0.47),
        "rotate_back": 0,
    },
]

def crop_box(img, box_frac):
    h, w = img.shape[:2]
    ymin, xmin, ymax, xmax = box_frac
    y0 = max(0, int(ymin * h))
    x0 = max(0, int(xmin * w))
    y1 = min(h, int(ymax * h))
    x1 = min(w, int(xmax * w))
    return img[y0:y1, x0:x1]

for spec in CROP_SPECS:
    fname = spec["file"]
    bc = spec["barcode"]
    src_path = CHECK_DIR / fname
    if not src_path.exists():
        print(f"File not found: {src_path}")
        continue
    img = cv2.imread(str(src_path))
    h, w = img.shape[:2]
    
    # Crop front
    front = crop_box(img, spec["front_box"])
    # Crop back
    back = crop_box(img, spec["back_box"])
    if spec["rotate_back"] == 180:
        back = cv2.rotate(back, cv2.ROTATE_180)
        
    # Save review previews
    f_prev = OUT_DIR / f"{bc}-front-preview.jpg"
    b_prev = OUT_DIR / f"{bc}-back-preview.jpg"
    
    # Resize preview if too large
    cv2.imwrite(str(f_prev), front)
    cv2.imwrite(str(b_prev), back)
    print(f"Generated preview for {bc} ({spec['name']}): Front={front.shape[1]}x{front.shape[0]}, Back={back.shape[1]}x{back.shape[0]}")

print("All previews generated in", OUT_DIR)
