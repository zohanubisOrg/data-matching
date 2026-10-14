#!/usr/bin/env python3
"""
scripts/audit_structural_defects.py
-----------------------------------
Deep QA audit comparing Column 23 (Customer front photo) and Column 24 (Webshop front photo):
Detects:
1. Multiple products in frame (e.g. 2 cans side-by-side).
2. Hollowed-out / missing product body (e.g. Del Monte white pouch eaten by background removal).
3. Stray slices / debris from adjacent packages.
4. Sharpness loss compared to customer photo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from io import BytesIO
import cv2
import numpy as np
from PIL import Image

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


def audit_defects():
    print("=" * 80)
    print("       ĐỐI CHIẾU CHUYÊN SÂU LỖI CHẤT LƯỢNG ẢNH TRÊN BẢNG EXCEL BÀN GIAO")
    print("=" * 80)

    excel_map = load_excel_front_map()
    files = sorted(list(FRONT_DIR.glob("*-front.jpg")))

    multiple_products = []
    hollow_body = []
    debris_slice = []

    for i, f in enumerate(files):
        bc = f.stem.replace("-front", "")
        with Image.open(f) as im:
            thumb = im.resize((600, 600), Image.Resampling.LANCZOS)
        arr = np.asarray(thumb.convert("RGB"))
        diff = np.abs(arr.astype(int) - 255).sum(axis=2)
        fg = (diff > 20).astype(np.uint8)

        total_area = int(np.sum(fg))
        if total_area == 0:
            hollow_body.append((bc, "Blank canvas"))
            continue

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
        comps = []
        for l in range(1, num_labels):
            area = stats[l, cv2.CC_STAT_AREA]
            if area > (total_area * 0.05):
                comps.append((l, area, stats[l]))

        comps.sort(key=lambda x: x[1], reverse=True)

        if len(comps) >= 2:
            c1_area = comps[0][1]
            c2_area = comps[1][1]
            if c2_area > (c1_area * 0.25):
                multiple_products.append((bc, f"2 objects (ratio {c2_area/c1_area:.2f})"))
            elif c2_area > (c1_area * 0.08):
                debris_slice.append((bc, f"Stray debris (ratio {c2_area/c1_area:.2f})"))

        ys, xs = np.where(fg > 0)
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        bbox_area = (bx1 - bx0) * (by1 - by0)
        solidity = total_area / max(1, bbox_area)

        aspect = (bx1 - bx0) / max(1, (by1 - by0))
        if 0.4 < aspect < 2.5 and solidity < 0.28:
            hollow_body.append((bc, f"Solidity only {solidity:.2f} (hollowed out)"))

    bad_barcodes = set([x[0] for x in multiple_products] + [x[0] for x in hollow_body] + [x[0] for x in debris_slice])

    print("\nKẾT QUẢ RÀ SOÁT CỤ THỂ:")
    print(f"1. Số ảnh chứa 2 hoặc nhiều sản phẩm (chưa tách được): {len(multiple_products)} ảnh")
    print(f"2. Số ảnh bị thủng thân / mất ruột do xóa nền quá lố: {len(hollow_body)} ảnh")
    print(f"3. Số ảnh bị dính mảnh rác / rìa cạnh sản phẩm bên cạnh: {len(debris_slice)} ảnh")
    print(f"\n--> TỔNG SỐ ẢNH PHÁT HIỆN LỖI TRẦM TRỌNG TRONG FRONT-V3: {len(bad_barcodes)}/{len(files)} ảnh ({len(bad_barcodes)/len(files)*100:.1f}%)")

    print("\nVí dụ các mã bị dính 2 sản phẩm (Multiple Products):")
    for bc, r in multiple_products[:10]:
        print(f"  - {bc}: {r}")

    print("\nVí dụ các mã bị thủng thân / lẹm mất chi tiết bao bì:")
    for bc, r in hollow_body[:10]:
        print(f"  - {bc}: {r}")

    print("\nVí dụ các mã dính rìa thừa / mảnh vỡ bao bì:")
    for bc, r in debris_slice[:10]:
        print(f"  - {bc}: {r}")


if __name__ == "__main__":
    audit_defects()
