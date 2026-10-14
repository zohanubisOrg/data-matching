#!/usr/bin/env python3
"""
scripts/fix_remaining_38.py
---------------------------
Giải quyết triệt để toàn bộ 38 ảnh còn lại:
- Đối với 20 sản phẩm xếp dọc (stacked_vertical): trích xuất chính xác gói mặt trước phía TRÊN (Top pack).
- Đối với 8 sản phẩm xếp ngang (side_by_side): trích xuất chính xác gói/chai mặt trước đối diện mã vạch.
- Đối với 10 sản phẩm đơn lẻ: chuẩn hóa padding 8%, bảo toàn 100% bao bì từ đỉnh đến đáy.
"""

from __future__ import annotations

import json
import os
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


def fix_single_item(bc: str, src_path: str | None) -> bool:
    front_file = FRONT_DIR / f"{bc}-front.jpg"
    raw_img = None

    if src_path and Path(src_path).exists():
        try:
            raw_img = ImageOps.exif_transpose(open_image_safely(Path(src_path)))
        except Exception:
            pass

    if raw_img is None and front_file.exists():
        raw_img = Image.open(front_file).convert("RGB")

    if raw_img is None:
        return False

    w, h = raw_img.size

    # Phân tích connected components trên ảnh hiện tại
    thumb = raw_img.copy()
    thumb.thumbnail((500, 500))
    arr = np.asarray(thumb)
    spread = arr.max(axis=2) - arr.min(axis=2)
    mask = ~((arr.min(axis=2) > 240) & (spread < 18))
    tw, th = thumb.size
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    big = []
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] > (tw * th * 0.05):
            big.append({
                "x": stats[i, cv2.CC_STAT_LEFT] / float(tw),
                "y": stats[i, cv2.CC_STAT_TOP] / float(th),
                "w": stats[i, cv2.CC_STAT_WIDTH] / float(tw),
                "h": stats[i, cv2.CC_STAT_HEIGHT] / float(th),
            })

    target_crop = None

    # Trường hợp 1: Hai sản phẩm xếp dọc (Top / Bottom)
    if len(big) >= 2 and abs(big[0]["y"] - big[1]["y"]) > abs(big[0]["x"] - big[1]["x"]):
        # Lấy gói phía TRÊN (Front packshot)
        top_blob = min(big, key=lambda b: b["y"])
        y0 = max(0, int((top_blob["y"] - 0.03) * h))
        y1 = min(h, int((top_blob["y"] + top_blob["h"] + 0.03) * h))
        x0 = max(0, int((top_blob["x"] - 0.03) * w))
        x1 = min(w, int((top_blob["x"] + top_blob["w"] + 0.03) * w))
        target_crop = raw_img.crop((x0, y0, x1, y1))

    # Trường hợp 2: Hai sản phẩm xếp ngang (Side-by-side)
    elif len(big) >= 2:
        # Tìm barcode
        hits = zxingcpp.read_barcodes(raw_img)
        left_blob = min(big, key=lambda b: b["x"])
        right_blob = max(big, key=lambda b: b["x"])

        # Nếu barcode ở nửa phải -> lấy blob trái
        chosen = left_blob
        if hits:
            cx = (hits[0].position.top_left.x + hits[0].position.bottom_right.x) / (2.0 * w)
            if cx < 0.5:
                chosen = right_blob

        x0 = max(0, int((chosen["x"] - 0.03) * w))
        x1 = min(w, int((chosen["x"] + chosen["w"] + 0.03) * w))
        y0 = max(0, int((chosen["y"] - 0.03) * h))
        y1 = min(h, int((chosen["y"] + chosen["h"] + 0.03) * h))
        target_crop = raw_img.crop((x0, y0, x1, y1))

    # Trường hợp 3: Một sản phẩm đơn lẻ nhưng cần căn giữa lề padding và làm sạch
    else:
        ys, xs = np.where(mask)
        if len(xs):
            x0 = max(0, int((xs.min() / float(tw) - 0.02) * w))
            x1 = min(w, int((xs.max() / float(tw) + 0.02) * w))
            y0 = max(0, int((ys.min() / float(th) - 0.02) * h))
            y1 = min(h, int((ys.max() / float(th) + 0.02) * h))
            target_crop = raw_img.crop((x0, y0, x1, y1))
        else:
            target_crop = raw_img

    if target_crop is not None:
        packshot = make_smart_packshot(
            target_crop,
            target_side=2400,
            pad_ratio=0.08,
            fill_holes=True,
            sharpness_factor=1.15,
        )
        save_image_high_quality(packshot, front_file, quality=95, save_webp=False)
        return True

    return False


def main():
    print("===============================================================================")
    print("        KHỞI CHẠY KHẮC PHỤC TRIỆT ĐỂ 38 ẢNH CHƯA ĐẠT (FINAL POLISH)            ")
    print("===============================================================================\n")

    d = json.loads(AUDIT_SUMMARY.read_text(encoding="utf-8"))
    failed_items = []
    for b in d["batches"]:
        failed_items.extend(b["failed_items"])

    sources = load_sources_map()
    print(f"Tổng số ảnh xử lý: {len(failed_items)}")

    success_cnt = 0
    for idx, item in enumerate(failed_items, start=1):
        bc = item["barcode"]
        src = sources.get(bc)
        ok = fix_single_item(bc, src)
        if ok:
            success_cnt += 1
            print(f"  [{idx:02d}/{len(failed_items)}] {bc}: Đã chuẩn hóa thành công 1 chủ thể duy nhất")
        else:
            print(f"  [{idx:02d}/{len(failed_items)}] {bc}: Bỏ qua hoặc không thể tải")

    print(f"\n==> Hoàn tất xử lý {success_cnt}/{len(failed_items)} ảnh!")


if __name__ == "__main__":
    main()
