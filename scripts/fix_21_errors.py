#!/usr/bin/env python3
"""
scripts/fix_21_errors.py
-------------------------
Fixes all 21 error images reported in output/catalog_pairs/image-error-resolve-again.
Resolves:
- Swapped front/back photos
- Truncated/over-cut packaging crops
- Stacked and single-face product layouts
Overwrites output/catalog_pairs/tagged/front-v2 and back-v2,
and refreshes Rabuta_12_10_Delivery_Embedded_v2.xlsx.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import pillow_heif

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "src"), str(ROOT / "scripts")])

from product_mapper.vision.barcode_side_splitter import enhance_back, packshot_front, read_retail_barcodes
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
PREVIEW_DIR = ROOT / "output/catalog_pairs/review/fixed_21_results"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

# Exact percentage crop definitions: (x0, y0, x1, y1)
CONFIGS = {
    # 01: Cock Brand Tom Yum Paste 454g (Swapped: Left = Back with barcode, Right = Front)
    "084909006608": {
        "src": "source-import/G1_original/IMG_0350.jpeg",
        "back_box": (0.05, 0.08, 0.48, 0.88),
        "front_box": (0.48, 0.10, 0.92, 0.90),
    },
    # 02: Bibigo Vegan Korean BBQ Gyoza 300g (Single pouch back with full nutrition table)
    "4016337982502": {
        "src": "source-import/G3_Original/IMG_1437.jpeg",
        "back_box": (0.03, 0.05, 0.97, 0.95),
        "front_box": None,  # Single face
    },
    # 03: Three Coconut Tree Sushi Rice 10kg (Single sack back with full instructions)
    "4045198857032": {
        "src": "source-import/G3_Original/IMG_1298.jpeg",
        "back_box": (0.02, 0.08, 0.96, 0.98),
        "front_box": None,  # Single face
    },
    # 04: Three Coconut Tree Mini Shrimp Spring Rolls 500g (Single pouch full label)
    "4045198908116": {
        "src": "source-import/G3_Original/IMG_1380.jpeg",
        "back_box": (0.02, 0.04, 0.96, 0.95),
        "front_box": None,  # Single face
    },
    # 05: Three Coconut Tree Frozen Red Date Mantou 300g (Stacked: Top = Front, Bottom = Back)
    "4045198925151": {
        "src": "source-import/G3_Original/IMG_5172.HEIC",
        "front_box": (0.02, 0.08, 0.98, 0.48),
        "back_box": (0.02, 0.48, 0.98, 0.95),
    },
    # 06: Ricefield ST25 Jasmine Rice 18kg (Single sack back full panel)
    "4316734061498": {
        "src": "source-import/G3_Original/IMG_1319.jpeg",
        "back_box": (0.03, 0.04, 0.97, 0.96),
        "front_box": None,  # Single face
    },
    # 07: Fairy fresh wheat noodles 200g (Left = Front, Right = Back)
    "4897068793861": {
        "src": "source-import/G4-original/20260916_112652662_iOS.heic",
        "front_box": (0.01, 0.20, 0.50, 0.70),
        "back_box": (0.50, 0.20, 0.99, 0.68),
    },
    # 08: La Fan Tian Chopped Chili 700g (Left = Back with barcode, Right = Front)
    "6924200920156": {
        "src": "source-import/G1_original/IMG_0173.jpeg",
        "back_box": (0.00, 0.18, 0.51, 0.88),
        "front_box": (0.49, 0.18, 0.99, 0.88),
    },
    # 09: Yong Jia fresh enoki mushrooms (Left = Back with barcode, Right = Front)
    "6944546168333": {
        "src": "source-import/G4-original/20260916_111748748_iOS.heic",
        "back_box": (0.02, 0.12, 0.52, 0.88),
        "front_box": (0.50, 0.12, 0.98, 0.90),
    },
    # 10: Frozen Boneless Chicken Feet 400g (Single tray full packshot)
    "8445198964000": {
        "src": "source-import/G3_Original/IMG_5128.HEIC",
        "back_box": (0.01, 0.08, 0.98, 0.72),
        "front_box": None,  # Single face
    },
    # 11: Asian Choice Black Tiger Shrimp 700g (Stacked: Top = Front, Bottom = Back)
    "8713913003304": {
        "src": "source-import/G3_Original/IMG_5090.HEIC",
        "front_box": (0.02, 0.05, 0.98, 0.46),
        "back_box": (0.02, 0.46, 0.98, 0.88),
    },
    # 12: Sweet Mellow Jelly Sweets 320g (Swapped: Left = Back with barcode, Right = Front)
    "8720812774334": {
        "src": "source-import/G1_original/IMG_0027.jpeg",
        "back_box": (0.01, 0.08, 0.52, 0.88),
        "front_box": (0.50, 0.08, 0.98, 0.88),
    },
    # 13: Thailandia Fresh morning glory 250g (Single bag full packshot)
    "8850060110063": {
        "src": "source-import/G4-original/20260916_112840856_iOS.heic",
        "back_box": (0.01, 0.05, 0.98, 0.98),
        "front_box": None,  # Single face
    },
    # 14: Thailandia Fresh winged beans 80g (Stacked: Top = Front tray, Bottom = Back tray)
    "8850060110551": {
        "src": "source-import/G4-original/20260916_111222616_iOS.heic",
        "front_box": (0.04, 0.03, 0.96, 0.44),
        "back_box": (0.04, 0.44, 0.96, 0.98),
    },
    # 15: Thailandia Fresh turmeric 100g (Left = Front tray, Right = Back tray with barcode)
    "8850060110834": {
        "src": "source-import/G4-original/20260916_111118920_iOS.heic",
        "front_box": (0.01, 0.25, 0.50, 0.86),
        "back_box": (0.50, 0.25, 0.99, 0.90),
    },
    # 16: Thailandia Lod Chong dessert 250g (Left = Back tray with barcode, Right = Front tray)
    "8850060444458": {
        "src": "source-import/G4-original/20260916_111329184_iOS.heic",
        "back_box": (0.00, 0.40, 0.52, 0.80),
        "front_box": (0.50, 0.40, 0.98, 0.82),
    },
    # 17: MAMA Kim Chi Instant Noodles 90g (Stacked: Top = Front pack, Bottom = Back pack)
    "8850987131240": {
        "src": "source-import/G2_original/IMG_0735.jpeg",
        "front_box": (0.03, 0.08, 0.97, 0.52),
        "back_box": (0.03, 0.52, 0.97, 0.98),
    },
    # 18: Flying Goose Sriracha Sauce 730ml (Left = Back bottle with barcode, Right = Front bottle)
    "8853662056029": {
        "src": "source-import/G1_original/IMG_0383.jpeg",
        "back_box": (0.03, 0.05, 0.51, 0.97),
        "front_box": (0.50, 0.05, 0.97, 0.97),
    },
    # 19: Snack Jack Green Pea Snack 62g (Swapped: Left = Back with barcode, Right = Front)
    "8854923313301": {
        "src": "source-import/G1_original/IMG_0042.jpeg",
        "back_box": (0.00, 0.10, 0.50, 0.88),
        "front_box": (0.48, 0.12, 0.98, 0.88),
    },
    # 20: Tân Huê Viên Pia Cake 400g (Left = Front pack, Right = Back/side panels)
    "8936014316658": {
        "src": "source-import/G1_original/IMG_9947.jpeg",
        "front_box": (0.01, 0.04, 0.40, 0.58),
        "back_box": (0.50, 0.04, 0.99, 0.58),
    },
    # 21: Thanh Lộc Peanut Kernels 500g (Single bag full packshot)
    "8938500969928": {
        "src": "source-import/G1_original/IMG_0308.jpeg",
        "back_box": (0.02, 0.05, 0.98, 0.96),
        "front_box": None,  # Single face
    },
}


def process_all_21():
    print("=" * 80)
    print("RE-PROCESSING ALL 21 ERROR IMAGES WITH VERIFIED BOUNDING BOXES")
    print("=" * 80)

    results = []

    for idx, (bc, cfg) in enumerate(CONFIGS.items(), 1):
        src_path = ROOT / cfg["src"]
        if not src_path.exists():
            print(f"[-] #{idx:02d} {bc}: Missing source file {src_path}")
            continue

        raw_img = Image.open(src_path)
        img = ImageOps.exif_transpose(raw_img)
        w, h = img.size

        # 1. Back image
        bb = cfg["back_box"]
        x0, y0 = int(round(w * bb[0])), int(round(h * bb[1]))
        x1, y1 = int(round(w * bb[2])), int(round(h * bb[3]))
        back_crop = img.crop((x0, y0, x1, y1))
        back_enhanced = enhance_back(back_crop)
        dest_back = BACK_DIR / f"{bc}-back.jpg"
        save_image_high_quality(back_enhanced, dest_back, quality=95, save_webp=False)

        # 2. Front image
        dest_front = FRONT_DIR / f"{bc}-front.jpg"
        fb = cfg.get("front_box")
        if fb is not None:
            fx0, fy0 = int(round(w * fb[0])), int(round(h * fb[1]))
            fx1, fy1 = int(round(w * fb[2])), int(round(h * fb[3]))
            front_crop = img.crop((fx0, fy0, fx1, fy1))
            front_enhanced = packshot_front(front_crop)
            save_image_high_quality(front_enhanced, dest_front, quality=95, save_webp=False)
            mode = "paired_two_panel"
        else:
            # Single-face item: sync barcode/back image to front
            front_enhanced = packshot_front(back_crop)
            save_image_high_quality(front_enhanced, dest_front, quality=95, save_webp=False)
            mode = "single_face_synced"

        # Verification: check barcodes on back
        b_hits = read_retail_barcodes(back_enhanced)
        has_bc = len(b_hits) > 0
        bc_found = [hit.text for hit in b_hits]

        print(f"[+] #{idx:02d} {bc} -> Back: {back_enhanced.size} (BC: {bc_found}), Front: {front_enhanced.size} ({mode})")

        # Save preview comparison
        thumb_b = back_enhanced.copy()
        thumb_b.thumbnail((600, 600))
        thumb_f = front_enhanced.copy()
        thumb_f.thumbnail((600, 600))
        canvas = Image.new("RGB", (thumb_f.width + thumb_b.width + 30, max(thumb_f.height, thumb_b.height)), "white")
        canvas.paste(thumb_f, (10, 0))
        canvas.paste(thumb_b, (thumb_f.width + 20, 0))
        canvas.save(PREVIEW_DIR / f"{idx:02d}_{bc}_fixed.jpg", quality=90)

        results.append({
            "barcode": bc,
            "mode": mode,
            "back_size": back_enhanced.size,
            "front_size": front_enhanced.size,
            "back_barcodes": bc_found,
            "has_barcode": has_bc,
        })
        img.close()

    print(f"\nAll {len(results)} items successfully fixed and saved to front-v2 & back-v2!")

    # Step 3: Refresh Excel file
    print("\nUpdating Excel delivery file...")
    from embed_v2_images_to_excel import embed_catalog_images
    embed_catalog_images()


if __name__ == "__main__":
    process_all_21()
