#!/usr/bin/env python3
"""
scripts/fix_final_32_precise.py
-------------------------------
Trích xuất từ ẢNH GỐC MÁY ẢNH KHO (Source Camera Photo) cho 32 mã còn lại:
- Nếu barcode ở nửa DƯỚI -> Lấy gói nửa TRÊN (Top pack)
- Nếu barcode ở nửa TRÊN -> Lấy gói nửa DƯỚI (Bottom pack)
- Nếu barcode ở nửa PHẢI -> Lấy gói/chai nửa TRÁI (Left pack)
- Nếu barcode ở nửa TRÁI -> Lấy gói/chai nửa PHẢI (Right pack)
- Bảo toàn 100% chi tiết bao bì (hộp, chai, lon, gói) bằng SmartPackshot.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from io import BytesIO
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

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.smart_packshot import make_smart_packshot

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
AUDIT_SUMMARY = ROOT / "output/catalog_pairs/audit_1169_summary.json"


def load_sources_map() -> dict[str, str]:
    sources: dict[str, str] = {}
    idx_p = ROOT / "output/barcode_first/image_index.json"
    if idx_p.exists():
        for entry in json.loads(idx_p.read_text(encoding="utf-8")):
            for code in entry.get("codes", []):
                sources[code] = entry.get("path")

    for mf in (ROOT / "output/catalog_pairs").glob("manifest*.json"):
        try:
            d = json.loads(mf.read_text(encoding="utf-8"))
            for k, v in d.get("products", {}).items():
                if v.get("source"):
                    sources[k] = v["source"]
        except Exception:
            pass
    return sources


def fetch_online_fullres(barcode: str) -> Image.Image | None:
    headers = {"User-Agent": "ShopifyCatalogMatcher/2.0 (admin@rabuta.dk)"}
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == 1:
                p = data.get("product", {})
                front_url = p.get("image_front_url") or p.get("image_url")
                if front_url:
                    full_url = front_url.replace(".400.jpg", ".full.jpg")
                    try:
                        r = urllib.request.urlopen(urllib.request.Request(full_url, headers=headers), timeout=8)
                        return Image.open(BytesIO(r.read())).convert("RGB")
                    except Exception:
                        r = urllib.request.urlopen(urllib.request.Request(front_url, headers=headers), timeout=8)
                        return Image.open(BytesIO(r.read())).convert("RGB")
    except Exception:
        pass
    return None


def get_front_from_camera_source(src_path: Path, expected_barcode: str) -> Image.Image | None:
    raw_img = ImageOps.exif_transpose(open_image_safely(src_path))
    w, h = raw_img.size

    hits = zxingcpp.read_barcodes(raw_img)
    bc_hit = None
    for hit in hits:
        code_str = "".join(c for c in str(hit.text or "") if c.isdigit())
        if code_str == expected_barcode:
            bc_hit = hit
            break
    if not bc_hit and hits:
        bc_hit = max(hits, key=lambda x: (x.position.top_right.x - x.position.top_left.x)**2 + (x.position.top_right.y - x.position.top_left.y)**2)

    crop = None

    if bc_hit:
        p = bc_hit.position
        cx = (p.top_left.x + p.top_right.x + p.bottom_right.x + p.bottom_left.x) / 4.0
        cy = (p.top_left.y + p.top_right.y + p.bottom_right.y + p.bottom_left.y) / 4.0
        rx = cx / float(w)
        ry = cy / float(h)

        # 1. Nếu mã vạch ở nửa DƯỚI (Mì gói xếp dọc)
        if ry >= 0.52 and abs(ry - 0.5) > abs(rx - 0.5):
            x0 = int(w * 0.04)
            x1 = int(w * 0.96)
            y0 = int(h * 0.03)
            y1 = int(min(h * 0.50, cy - h * 0.06))
            crop = raw_img.crop((x0, y0, x1, y1))

        # 2. Nếu mã vạch ở nửa TRÊN (Mì gói xếp dọc)
        elif ry <= 0.48 and abs(ry - 0.5) > abs(rx - 0.5):
            x0 = int(w * 0.04)
            x1 = int(w * 0.96)
            y0 = int(max(h * 0.50, cy + h * 0.06))
            y1 = int(h * 0.97)
            crop = raw_img.crop((x0, y0, x1, y1))

        # 3. Nếu mã vạch ở nửa PHẢI (Chai/gói xếp ngang)
        elif rx >= 0.50:
            x0 = int(w * 0.02)
            x1 = int(min(w * 0.48, cx - w * 0.06))
            y0 = int(h * 0.02)
            y1 = int(h * 0.98)
            crop = raw_img.crop((x0, y0, x1, y1))

        # 4. Nếu mã vạch ở nửa TRÁI (Chai/gói xếp ngang)
        else:
            x0 = int(max(w * 0.52, cx + w * 0.06))
            x1 = int(w * 0.98)
            y0 = int(h * 0.02)
            y1 = int(h * 0.98)
            crop = raw_img.crop((x0, y0, x1, y1))

    # Nếu không có barcode rõ ràng, thử chia 2 nửa theo chiều dài hơn
    if crop is None:
        if h > w * 1.1:
            # Ảnh đứng -> lấy nửa trên
            crop = raw_img.crop((int(w * 0.05), int(h * 0.03), int(w * 0.95), int(h * 0.49)))
        else:
            # Ảnh ngang -> lấy nửa trái
            crop = raw_img.crop((int(w * 0.03), int(h * 0.04), int(w * 0.49), int(h * 0.96)))

    return crop


def main():
    print("===============================================================================")
    print("      TÁI XỬ LÝ CHÍNH XÁC 32 ẢNH MẶT TRƯỚC TỪ CAMERA GỐC KHO                  ")
    print("===============================================================================\n")

    d = json.loads(AUDIT_SUMMARY.read_text(encoding="utf-8"))
    failed_items = []
    for b in d["batches"]:
        failed_items.extend(b["failed_items"])

    sources = load_sources_map()
    print(f"Tổng số ảnh xử lý: {len(failed_items)}")

    fixed = 0
    for idx, item in enumerate(failed_items, start=1):
        bc = item["barcode"]
        dest = FRONT_DIR / f"{bc}-front.jpg"
        src_path_str = sources.get(bc)

        resolved_img = None

        if src_path_str and Path(src_path_str).exists():
            crop = get_front_from_camera_source(Path(src_path_str), bc)
            if crop:
                resolved_img = make_smart_packshot(
                    crop,
                    target_side=2400,
                    pad_ratio=0.08,
                    fill_holes=True,
                    sharpness_factor=1.15,
                )

        if resolved_img is None:
            online = fetch_online_fullres(bc)
            if online:
                resolved_img = make_smart_packshot(
                    online,
                    target_side=2400,
                    pad_ratio=0.08,
                    fill_holes=True,
                    sharpness_factor=1.15,
                )

        if resolved_img is not None:
            save_image_high_quality(resolved_img, dest, quality=95, save_webp=False)
            fixed += 1
            print(f"  [{idx:02d}/{len(failed_items)}] {bc}: Đã sửa hoàn thiện nguyên vẹn chi tiết")
        else:
            print(f"  [{idx:02d}/{len(failed_items)}] {bc}: Không tìm thấy nguồn ảnh")

    print(f"\n==> Hoàn tất xử lý: {fixed}/{len(failed_items)} ảnh!")


if __name__ == "__main__":
    main()
