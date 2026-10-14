#!/usr/bin/env python3
"""Retired automatic healing; render helper now requires a reviewed package mask.
Use reprocess_rabuta_verified.py for traceable candidates, not automatic QA PASS.
"""

from __future__ import annotations

import sys
from pathlib import Path
from io import BytesIO
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageEnhance
from rembg import remove, new_session

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
from scripts.studio_front_v3_extractor import load_excel_front_map


def isolate_customer_packshot(raw_im: Image.Image, session=None, target_size: int = 2400, *, package_mask=None, shape="auto") -> Image.Image:
    """Legacy bridge: independently verified whole-package mask is mandatory."""
    sys.path.insert(0, str(ROOT / "src"))
    from product_mapper.vision.package_packshot import render_verified_packshot
    return render_verified_packshot(raw_im, package_mask, target_size, shape)[0]


def heal_defects():
    print("=" * 80)
    print("       HEALING ALL DEFECTIVE PACKSHOTS VIA CUSTOMER FRONT PHOTO")
    print("=" * 80)

    excel_map = load_excel_front_map()
    files = sorted(list(FRONT_DIR.glob("*-front.jpg")))

    # Identify all defective barcodes
    to_heal = []
    for f in files:
        bc = f.stem.replace("-front", "")
        with Image.open(f) as im:
            thumb = im.resize((600, 600), Image.Resampling.LANCZOS)
        arr = np.asarray(thumb.convert("RGB"))
        diff = np.abs(arr.astype(int) - 255).sum(axis=2)
        fg = (diff > 20).astype(np.uint8)

        total_area = int(np.sum(fg))
        if total_area == 0:
            to_heal.append(bc)
            continue

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
        comps = []
        for l in range(1, num_labels):
            area = stats[l, cv2.CC_STAT_AREA]
            if area > (total_area * 0.05):
                comps.append((l, area, stats[l]))

        comps.sort(key=lambda x: x[1], reverse=True)

        # Flag if 2 products or stray slice
        if len(comps) >= 2:
            c1_area = comps[0][1]
            c2_area = comps[1][1]
            if c2_area > (c1_area * 0.10):
                to_heal.append(bc)
                continue

        ys, xs = np.where(fg > 0)
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        bbox_area = (bx1 - bx0) * (by1 - by0)
        solidity = total_area / max(1, bbox_area)
        aspect = (bx1 - bx0) / max(1, (by1 - by0))
        if 0.4 < aspect < 2.5 and solidity < 0.28:
            to_heal.append(bc)
            continue

    to_heal = sorted(list(set(to_heal)))
    print(f"Total packshots requiring healing: {len(to_heal)}")

    session = new_session("u2net")
    healed = 0

    for i, bc in enumerate(to_heal):
        dest_p = FRONT_DIR / f"{bc}-front.jpg"
        if bc in excel_map:
            try:
                raw_im = Image.open(BytesIO(excel_map[bc]._data()))
                pack = isolate_customer_packshot(raw_im, session, target_size=2400)
                pack.save(dest_p, "JPEG", quality=95)
                healed += 1
                if (i + 1) % 25 == 0 or (i + 1) == len(to_heal):
                    print(f"  [{i+1}/{len(to_heal)}] Healed {bc} (Single product, crystal clear)!")
            except Exception as e:
                print(f"  [!] Failed {bc}: {e}")
        else:
            print(f"  [-] Barcode {bc} not in customer Excel map")

    print("\n" + "=" * 80)
    print(f"HEALING COMPLETED: {healed}/{len(to_heal)} packshots successfully restored!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    raise SystemExit("Unsafe legacy auto-healing is retired. Use scripts/reprocess_rabuta_verified.py with reviewed source polygons; front-v3 is not overwritten.")
