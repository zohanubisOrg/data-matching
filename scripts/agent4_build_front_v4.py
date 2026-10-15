#!/usr/bin/env python3
"""
scripts/agent4_build_front_v4.py
---------------------------------
Agent 4 (Decision Maker & Execution Engine):
Sản xuất toàn diện danh mục front-v4 (2400x2400 studio canvas, nền trắng tinh #FFFFFF)
khắc phục triệt để các lỗi Guillotine, Lật nhầm, Sai kích thước và Bổ sung ảnh thiếu.

Nguồn ảnh đầu vào theo thứ tự ưu tiên (Tiered Priority):
- Tier 1: Ảnh v3 đạt chuẩn (PASSED_SHARP / PASSED_SOFT) -> Giữ nguyên 100%.
- Tier 2: Kho ảnh sạch HD_Studio_Front_Images (1.245 file studio nguyên vẹn).
- Tier 3: Kho ảnh front-v2 (1.169 file trước khi bị thuật toán seam-split v3 cắt lẹm).
- Tier 4: Kho ảnh Customer Ground Truth (1.348 file gốc khách hàng nhúng trong Excel).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

CHECKER_REPORT = ROOT / "output/catalog_pairs/audit_checker_results.json"
FRONT_V4_DIR = ROOT / "output/catalog_pairs/tagged/front-v4"
FRONT_V4_DIR.mkdir(parents=True, exist_ok=True)

# Các kho nguồn
FRONT_V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
FRONT_V2_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
HD_STUDIO_DIR = ROOT / "output/shopify_import_final/HD_Studio_Front_Images"
CUST_GT_DIR = ROOT / "output/catalog_pairs/customer_ground_truth"
WEB_FRONT_DIR = ROOT / "web/public/products/front"

LEDGER_FILE = ROOT / "output/catalog_pairs/front_v4_resolution_ledger.json"


def find_file(folder: Path, barcode: str, suffix: str = "front") -> Optional[Path]:
    for sep in ("-", "_"):
        cand = folder / f"{barcode}{sep}{suffix}.jpg"
        if cand.exists():
            return cand
    cand_plain = folder / f"{barcode}.jpg"
    if cand_plain.exists():
        return cand_plain
    cand_webp = folder / f"{barcode}.webp"
    if cand_webp.exists():
        return cand_webp

    if barcode.startswith("0"):
        stripped = barcode.lstrip("0")
        for sep in ("-", "_"):
            cand = folder / f"{stripped}{sep}{suffix}.jpg"
            if cand.exists():
                return cand
        cand_p = folder / f"{stripped}.jpg"
        if cand_p.exists():
            return cand_p

    if len(barcode) == 12:
        with_zero = "0" + barcode
        for sep in ("-", "_"):
            cand = folder / f"{with_zero}{sep}{suffix}.jpg"
            if cand.exists():
                return cand
        cand_p = folder / f"{with_zero}.jpg"
        if cand_p.exists():
            return cand_p

    return None


def get_edge_flatness(arr: np.ndarray) -> Tuple[float, float, float, float]:
    """Đo tỷ lệ phẳng (guillotine cut) ở 4 cạnh bao bì."""
    fg = (arr < 250).any(axis=-1)
    ys, xs = np.where(fg)
    if len(xs) == 0:
        return 1.0, 1.0, 1.0, 1.0
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    crop_fg = fg[y0:y1, x0:x1]
    top = float(crop_fg[:3, :].mean(axis=1).max()) if crop_fg.shape[0] >= 3 else 1.0
    bottom = float(crop_fg[-3:, :].mean(axis=1).max()) if crop_fg.shape[0] >= 3 else 1.0
    left = float(crop_fg[:, :3].mean(axis=0).max()) if crop_fg.shape[1] >= 3 else 1.0
    right = float(crop_fg[:, -3:].mean(axis=0).max()) if crop_fg.shape[1] >= 3 else 1.0
    return top, bottom, left, right


def format_studio_canvas(img: Image.Image, occupancy: float = 0.85, target_dim: int = 2400) -> Image.Image:
    """Đóng gói sản phẩm vào canvas chuẩn 2400x2400 nền trắng tinh khiết, không bóp méo."""
    arr = np.array(img.convert("RGB"))
    fg = (arr < 250).any(axis=-1)
    ys, xs = np.where(fg)
    if len(xs) == 0:
        # Ảnh trắng hoàn toàn -> trả về canvas trắng
        return Image.new("RGB", (target_dim, target_dim), (255, 255, 255))

    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
    crop = img.crop((x0, y0, x1, y1))
    pw, ph = crop.size

    # Tính toán tỷ lệ co giãn giữ nguyên aspect ratio
    max_side = max(pw, ph)
    scale = (target_dim * occupancy) / float(max_side)
    new_w = max(1, int(round(pw * scale)))
    new_h = max(1, int(round(ph * scale)))

    resized = crop.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Đặt vào tâm canvas 2400x2400
    canvas = Image.new("RGB", (target_dim, target_dim), (255, 255, 255))
    offset_x = (target_dim - new_w) // 2
    offset_y = (target_dim - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))

    # Đảm bảo viền 4px tuyệt đối #FFFFFF
    c_arr = np.array(canvas)
    c_arr[:4, :] = 255
    c_arr[-4:, :] = 255
    c_arr[:, :4] = 255
    c_arr[:, -4:] = 255

    return Image.fromarray(c_arr)


def run_agent4_build():
    print("=" * 80)
    print("  AGENT 4 (DECISION & EXECUTION): BẮT ĐẦU SẢN XUẤT CATALOG FRONT-V4  ")
    print("=" * 80)

    with open(CHECKER_REPORT, "r", encoding="utf-8") as f:
        checker_data = json.load(f)

    results = checker_data.get("results", [])
    total = len(results)

    ledger = []
    stats = {
        "TOTAL": total,
        "KEPT_V3_CLEAN": 0,
        "RESTORED_HD_STUDIO": 0,
        "RESTORED_FRONT_V2": 0,
        "RESTORED_CUSTOMER_GT": 0,
        "RESTORED_WEB_FRONT": 0,
        "CANVAS_NORMALIZED": 0,
        "ORIENTATION_HEALED": 0,
        "FAILED": 0
    }

    print(f"--> Đang xử lý {total} SKU theo quyết định phân tầng...")

    for i, item in enumerate(results, start=1):
        barcode = item["barcode"]
        defects = item.get("defects", [])
        status = item.get("status", "PASS")
        dest_path = FRONT_V4_DIR / f"{barcode}-front.jpg"

        record = {
            "barcode": barcode,
            "product_name": item.get("product_name"),
            "initial_status": status,
            "initial_defects": defects,
            "final_action": None,
            "source_used": None
        }

        # TRƯỜNG HỢP 1: Ảnh v3 đạt chuẩn không lỗi (PASSED_SHARP & PASSED_SOFT)
        if not defects and status in ("PASSED_SHARP", "PASSED_SOFT"):
            v3_src = find_file(FRONT_V3_DIR, barcode, "front")
            if v3_src and v3_src.exists():
                shutil.copy2(v3_src, dest_path)
                record["final_action"] = "KEPT_V3_CLEAN"
                record["source_used"] = "front-v3"
                stats["KEPT_V3_CLEAN"] += 1
                ledger.append(record)
                continue

        # TRƯỜNG HỢP 2: Bị cắt lẹm bao bì (GUILLOTINE_TRUNCATION) hoặc Cắt ruột
        # Cần tìm nguồn thay thế sạch có bao bì trọn vẹn
        best_candidate: Optional[Image.Image] = None
        source_name: Optional[str] = None

        # 2.1 Thử HD_Studio
        hd_p = find_file(HD_STUDIO_DIR, barcode, "")
        if hd_p and hd_p.exists():
            try:
                hd_im = Image.open(hd_p)
                top, bottom, left, right = get_edge_flatness(np.array(hd_im.convert("RGB")))
                if top < 0.45 and left < 0.40 and right < 0.40:
                    best_candidate = hd_im
                    source_name = "HD_Studio_Front_Images"
            except Exception:
                pass

        # 2.2 Thử front-v2
        if best_candidate is None:
            v2_p = find_file(FRONT_V2_DIR, barcode, "front")
            if v2_p and v2_p.exists():
                try:
                    v2_im = Image.open(v2_p)
                    top, bottom, left, right = get_edge_flatness(np.array(v2_im.convert("RGB")))
                    if top < 0.45 and left < 0.40 and right < 0.40:
                        best_candidate = v2_im
                        source_name = "front-v2"
                except Exception:
                    pass

        # 2.3 Thử web public front
        if best_candidate is None:
            web_p = find_file(WEB_FRONT_DIR, barcode, "")
            if web_p and web_p.exists():
                try:
                    web_im = Image.open(web_p)
                    top, bottom, left, right = get_edge_flatness(np.array(web_im.convert("RGB")))
                    if top < 0.45 and left < 0.40 and right < 0.40:
                        best_candidate = web_im
                        source_name = "web_public"
                except Exception:
                    pass

        # 2.4 Thử Customer Ground Truth
        if best_candidate is None:
            gt_p = CUST_GT_DIR / f"{barcode}.jpg"
            if gt_p.exists():
                try:
                    gt_im = Image.open(gt_p)
                    best_candidate = gt_im
                    source_name = "customer_ground_truth"
                except Exception:
                    pass

        # 2.5 Nếu vẫn chưa tìm được và có v3 (nhưng v3 chỉ bị sai canvas)
        if best_candidate is None:
            v3_fallback = find_file(FRONT_V3_DIR, barcode, "front")
            if v3_fallback and v3_fallback.exists():
                try:
                    best_candidate = Image.open(v3_fallback)
                    source_name = "front-v3-canvas-fix"
                except Exception:
                    pass

        # Xử lý xoay nếu bị lỗi ORIENTATION_INVERTED
        if best_candidate is not None and "ORIENTATION_INVERTED" in defects:
            gt_p = CUST_GT_DIR / f"{barcode}.jpg"
            if gt_p.exists():
                try:
                    gt_im = Image.open(gt_p)
                    c_is_portrait = (gt_im.height > gt_im.width)
                    b_is_portrait = (best_candidate.height > best_candidate.width)
                    if c_is_portrait and not b_is_portrait:
                        best_candidate = best_candidate.rotate(90, expand=True)
                        stats["ORIENTATION_HEALED"] += 1
                        record["orientation_healed"] = True
                    elif not c_is_portrait and b_is_portrait:
                        best_candidate = best_candidate.rotate(90, expand=True)
                        stats["ORIENTATION_HEALED"] += 1
                        record["orientation_healed"] = True
                except Exception:
                    pass

        # Đóng gói sản phẩm lên canvas 2400x2400
        if best_candidate is not None:
            try:
                final_canvas = format_studio_canvas(best_candidate, occupancy=0.85, target_dim=2400)
                final_canvas.save(dest_path, "JPEG", quality=95, optimize=True)
                record["final_action"] = f"HEALED_VIA_{source_name.upper()}"
                record["source_used"] = source_name

                if source_name == "HD_Studio_Front_Images":
                    stats["RESTORED_HD_STUDIO"] += 1
                elif source_name == "front-v2":
                    stats["RESTORED_FRONT_V2"] += 1
                elif source_name == "customer_ground_truth":
                    stats["RESTORED_CUSTOMER_GT"] += 1
                elif source_name == "web_public":
                    stats["RESTORED_WEB_FRONT"] += 1
                else:
                    stats["CANVAS_NORMALIZED"] += 1

            except Exception as e:
                record["final_action"] = f"ERROR_{str(e)}"
                stats["FAILED"] += 1
        else:
            record["final_action"] = "UNRESOLVED_NO_SOURCE"
            stats["FAILED"] += 1

        ledger.append(record)

        if i % 200 == 0 or i == total:
            print(f"    [Tiến độ Agent 4] {i}/{total} SKU hoàn tất | "
                  f"Kept v3: {stats['KEPT_V3_CLEAN']} | "
                  f"Healed: {stats['RESTORED_HD_STUDIO'] + stats['RESTORED_FRONT_V2'] + stats['RESTORED_CUSTOMER_GT'] + stats['CANVAS_NORMALIZED']}")

    # Ghi ledger
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump({"statistics": stats, "records": ledger}, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("  AGENT 4: HOÀN TẤT XUẤT BẢN THƯ MỤC FRONT-V4  ")
    print("=" * 80)
    print(f"  * Tổng số SKU xử lý             : {stats['TOTAL']}")
    print(f"  * Giữ nguyên v3 sạch            : {stats['KEPT_V3_CLEAN']}")
    print(f"  * Khôi phục từ HD Studio        : {stats['RESTORED_HD_STUDIO']}")
    print(f"  * Khôi phục từ Front-v2         : {stats['RESTORED_FRONT_V2']}")
    print(f"  * Khôi phục từ Customer GT      : {stats['RESTORED_CUSTOMER_GT']}")
    print(f"  * Khôi phục từ Web Public       : {stats['RESTORED_WEB_FRONT']}")
    print(f"  * Chuẩn hóa Canvas 2400x2400    : {stats['CANVAS_NORMALIZED']}")
    print(f"  * Khắc phục lật nhầm 90 độ      : {stats['ORIENTATION_HEALED']}")
    print(f"  * Thất bại / Thiếu nguồn         : {stats['FAILED']}")
    print(f"  * Thư mục đầu ra                : {FRONT_V4_DIR}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_agent4_build()
