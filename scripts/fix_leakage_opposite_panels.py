#!/usr/bin/env python3
"""
scripts/fix_leakage_opposite_panels.py
--------------------------------------
Trích xuất chính xác mặt trước đối diện (opposite panel) cho các ảnh
trước đó bị dính barcode do nhận diện nhầm thành 'back_only'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image, ImageOps
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.smart_packshot import make_smart_packshot

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
AUDIT_PATH = ROOT / "output/catalog_pairs/front_v2_comprehensive_audit.json"


def get_opposite_front_crop(img: Image.Image, barcode_hit) -> Image.Image | None:
    w, h = img.size
    p = barcode_hit.position
    cx = (p.top_left.x + p.top_right.x + p.bottom_right.x + p.bottom_left.x) / 4.0
    cy = (p.top_left.y + p.top_right.y + p.bottom_right.y + p.bottom_left.y) / 4.0
    rx = cx / float(w)
    ry = cy / float(h)

    # 1. Barcode nằm ở nửa phải -> Mặt trước nằm ở nửa trái
    if rx >= 0.52 and w >= h * 0.8:
        # Front crop ở bên trái
        x0 = int(w * 0.02)
        x1 = int(min(w * 0.52, cx - w * 0.05))
        y0 = int(h * 0.05)
        y1 = int(h * 0.95)
        if (x1 - x0) > w * 0.25:
            return img.crop((x0, y0, x1, y1))

    # 2. Barcode nằm ở nửa trái -> Mặt trước nằm ở nửa phải
    elif rx <= 0.48 and w >= h * 0.8:
        x0 = int(max(w * 0.48, cx + w * 0.05))
        x1 = int(w * 0.98)
        y0 = int(h * 0.05)
        y1 = int(h * 0.95)
        if (x1 - x0) > w * 0.25:
            return img.crop((x0, y0, x1, y1))

    # 3. Barcode nằm ở nửa dưới -> Mặt trước nằm ở nửa trên (ảnh xếp dọc)
    elif ry >= 0.52 and h > w * 0.8:
        x0 = int(w * 0.05)
        x1 = int(w * 0.95)
        y0 = int(h * 0.02)
        y1 = int(min(h * 0.52, cy - h * 0.05))
        if (y1 - y0) > h * 0.25:
            return img.crop((x0, y0, x1, y1))

    # 4. Barcode nằm ở nửa trên -> Mặt trước nằm ở nửa dưới
    elif ry <= 0.48 and h > w * 0.8:
        x0 = int(w * 0.05)
        x1 = int(w * 0.95)
        y0 = int(max(h * 0.48, cy + h * 0.05))
        y1 = int(h * 0.98)
        if (y1 - y0) > h * 0.25:
            return img.crop((x0, y0, x1, y1))

    return None


def main():
    with open(AUDIT_PATH, encoding="utf-8") as f:
        d = json.load(f)

    leakage = [c for c in d["front_critical_items"] if "has-barcode-leakage" in c["issues"]]
    print(f"Bắt đầu xử lý {len(leakage)} sản phẩm dính mã vạch trên mặt trước...")

    resolved = 0
    for item in leakage:
        bc = item["barcode"]
        dest = FRONT_DIR / f"{bc}-front.jpg"
        src_info = item.get("source_info") or {}
        src = src_info.get("source")
        if not src or not Path(src).exists():
            continue

        try:
            raw_img = open_image_safely(Path(src))
            hits = zxingcpp.read_barcodes(raw_img)
            if not hits:
                continue

            best_hit = max(hits, key=lambda x: (x.position.top_right.x - x.position.top_left.x)**2 + (x.position.top_right.y - x.position.top_left.y)**2)
            front_crop = get_opposite_front_crop(raw_img, best_hit)
            if front_crop is not None:
                # Kiểm tra lại xem front_crop có còn barcode không
                remaining_hits = zxingcpp.read_barcodes(front_crop)
                has_code = any("".join(c for c in str(h.text or "") if c.isdigit()) == bc for h in remaining_hits)
                if not has_code:
                    packshot = make_smart_packshot(front_crop, target_side=2400)
                    save_image_high_quality(packshot, dest, quality=95, save_webp=False)
                    resolved += 1
                    print(f"  [Thành công] {bc}: Đã tách chuẩn mặt trước đối diện không dính mã vạch ({dest.name})")
        except Exception as e:
            print(f"  [Lỗi] {bc}: {e}")

    print(f"\n==> Đã giải quyết thành công {resolved}/{len(leakage)} ảnh mặt trước bị dính barcode!")


if __name__ == "__main__":
    main()
