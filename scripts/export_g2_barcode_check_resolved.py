import sys, os
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import enhance_back, packshot_front

CHECK_DIR = ROOT / "output/catalog_pairs/tagged/g2-barcode-check"
FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"

FRONT_DIR.mkdir(parents=True, exist_ok=True)
BACK_DIR.mkdir(parents=True, exist_ok=True)

# List of items to export:
SPECS = [
    {
        "file": "IMG_0443.jpeg",
        "barcode": "4316734096117",
        "name": "Cholimex Chili Sauce with Garlic 750 ml",
        "front_box": (0.10, 0.33, 0.94, 0.65),
        "back_box": (0.10, 0.65, 0.94, 0.98),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0445.jpeg",
        "barcode": "8936147330170",
        "name": "Double Panda Mild Spring Roll Dipping Sauce 500 ml",
        "front_box": (0.09, 0.15, 0.96, 0.48),
        "back_box": (0.09, 0.51, 0.96, 0.83),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0588.jpeg",
        "barcode": "8850030035082",
        "name": "Lobo Roast Red Pork Seasoning Mix 400 g",
        "front_box": (0.07, 0.02, 0.86, 0.45),
        "back_box": (0.04, 0.48, 0.93, 0.97),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0659.jpeg",
        "barcode": "8850100003713",
        "name": "Wai Wai Quick Shrimp chilli lime flavour noodles 55 g",
        "front_box": (0.16, 0.01, 0.73, 0.51),
        "back_box": (0.19, 0.51, 0.75, 0.98),
        "rotate_back": 180,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0665.jpeg",
        "barcode": "8850987128158",
        "name": "MAMA Tom Yum Pork Flavour Instant Noodles 60 g",
        "front_box": (0.21, 0.55, 0.90, 0.97),
        "back_box": (0.19, 0.05, 0.88, 0.49),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0772.jpeg",
        "barcode": "8936007820544",
        "name": "Bamboo Tree fine rice vermicelli (bánh hỏi) 340 g",
        "front_box": (0.04, 0.57, 0.97, 0.92),
        "back_box": (0.02, 0.16, 0.93, 0.51),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0825.jpeg",
        "barcode": "8850931040680",
        "name": "Madame Wong long life noodles with turmeric 400 g",
        "front_box": (0.14, 0.46, 0.79, 0.98),
        "back_box": (0.17, 0.01, 0.78, 0.46),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0835.jpeg",
        "barcode": "8936062107994",
        "name": "Dafood cinnamon, star anise and black cardamom 100 g",
        "front_box": (0.04, 0.49, 0.98, 0.99),
        "back_box": (0.06, 0.01, 0.95, 0.48),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
    {
        "file": "IMG_0839.jpeg",
        "barcode": "8717624005060",
        "name": "Nature's Best Harvest dried lotus seeds 150 g",
        "front_box": (0.06, 0.48, 0.95, 0.98),
        "back_box": (0.06, 0.01, 0.96, 0.47),
        "rotate_back": 0,
        "export_front": True,
        "export_back": True,
    },
]

def crop_box_pil(img: Image.Image, box_frac: tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    ymin, xmin, ymax, xmax = box_frac
    x0 = max(0, int(xmin * w))
    y0 = max(0, int(ymin * h))
    x1 = min(w, int(xmax * w))
    y1 = min(h, int(ymax * h))
    return img.crop((x0, y0, x1, y1))

print("=== EXPORTING RESOLVED G2 SPECIAL CROPS ===")
results = []
for spec in SPECS:
    fname = spec["file"]
    bc = spec["barcode"]
    src_path = CHECK_DIR / fname
    if not src_path.exists():
        print(f"File missing: {src_path}")
        continue
    
    img = open_image_safely(src_path)
    
    # 1. FRONT
    if spec["export_front"]:
        f_crop = crop_box_pil(img, spec["front_box"])
        f_packshot = packshot_front(f_crop)
        f_dest = FRONT_DIR / f"{bc}-front.jpg"
        save_image_high_quality(f_packshot, f_dest, quality=95, save_webp=False)
        print(f"  [FRONT] {bc} -> {f_dest.name} ({f_packshot.size[0]}x{f_packshot.size[1]})")
        
    # 2. BACK
    if spec["export_back"]:
        b_crop = crop_box_pil(img, spec["back_box"])
        if spec["rotate_back"] == 180:
            b_crop = b_crop.rotate(180, expand=True)
        b_enhanced = enhance_back(b_crop)
        b_dest = BACK_DIR / f"{bc}-back.jpg"
        save_image_high_quality(b_enhanced, b_dest, quality=94, save_webp=False)
        print(f"  [BACK]  {bc} -> {b_dest.name} ({b_enhanced.size[0]}x{b_enhanced.size[1]})")
        
    img.close()
    results.append(spec)

print(f"\nSuccessfully exported {len(results)} products to front-v2 and back-v2.")
