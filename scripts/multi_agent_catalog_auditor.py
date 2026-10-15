#!/usr/bin/env python3
"""
scripts/multi_agent_catalog_auditor.py
---------------------------------------
Engine quét đối chiếu định lượng & thị giác cho hệ thống 4 Subagents:
Agent 1 (Checker) -> Agent 2 (Reviewer) -> Agent 3 (QA) -> Agent 4 (Decision)

So sánh trên từng dòng sản phẩm của 3 cột ảnh:
- Cột W: Customer Ground Truth (output/catalog_pairs/customer_ground_truth/<barcode>.jpg)
- Cột X: Front-v3 (output/catalog_pairs/tagged/front-v3/<barcode>-front.jpg)
- Cột Y: Back-v2 (output/catalog_pairs/tagged/back-v2/<barcode>-back.jpg)
"""

from __future__ import annotations

import json
import os
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
import openpyxl
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

EXCEL_FILE = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.original_backup.xlsx"
CUST_DIR = ROOT / "output/catalog_pairs/customer_ground_truth"
FRONT_V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
BACK_V2_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"

CHECKER_REPORT = ROOT / "output/catalog_pairs/audit_checker_results.json"


def find_file(folder: Path, barcode: str, suffix: str) -> Optional[Path]:
    for sep in ("-", "_"):
        cand = folder / f"{barcode}{sep}{suffix}.jpg"
        if cand.exists():
            return cand
    if barcode.startswith("0"):
        stripped = barcode.lstrip("0")
        for sep in ("-", "_"):
            cand = folder / f"{stripped}{sep}{suffix}.jpg"
            if cand.exists():
                return cand
    if len(barcode) == 12:
        with_zero = "0" + barcode
        for sep in ("-", "_"):
            cand = folder / f"{with_zero}{sep}{suffix}.jpg"
            if cand.exists():
                return cand
    return None


def get_foreground_bbox(arr: np.ndarray, thresh: int = 250) -> Optional[Tuple[int, int, int, int]]:
    """Tìm bounding box của vùng sản phẩm (non-white)."""
    fg = (arr < thresh).any(axis=-1)
    ys, xs = np.where(fg)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def is_guillotine_cut(arr: np.ndarray, bbox: Tuple[int, int, int, int]) -> bool:
    """Kiểm tra xem sản phẩm có bị cắt phẳng lì một cạnh hay không."""
    x0, y0, x1, y1 = bbox
    pw, ph = x1 - x0, y1 - y0
    if pw < 30 or ph < 30:
        return True
    
    fg = (arr[y0:y1, x0:x1] < 250).any(axis=-1)
    # Cạnh trên (top)
    if fg[:3, :].mean(axis=1).max() > 0.55:
        return True
    # Cạnh trái (left)
    if fg[:, :3].mean(axis=0).max() > 0.50:
        return True
    # Cạnh phải (right)
    if fg[:, -3:].mean(axis=0).max() > 0.50:
        return True
    return False


def run_checker_scan():
    print("=" * 80)
    print("  AGENT 1 (CHECKER): BẮT ĐẦU QUÉT ĐỐI CHIẾU TOÀN DIỆN 3 CỘT ẢNH  ")
    print("=" * 80)

    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)
    ws = wb.active

    results = []
    stats = {
        "TOTAL": 0,
        "PASSED_SHARP": 0,
        "PASSED_SOFT": 0,
        "COLLISION_WITH_BACK": 0,
        "ORIENTATION_INVERTED": 0,
        "INTERNAL_DETAIL_ONLY": 0,
        "GUILLOTINE_TRUNCATION": 0,
        "STRUCTURAL_CANVAS": 0,
        "MISSING_FRONT_V3": 0,
    }

    print(f"--> Đang quét {ws.max_row - 3} sản phẩm...")

    for r in range(4, ws.max_row + 1):
        bc_val = ws.cell(r, 1).value
        if not bc_val:
            continue
        
        barcode = str(bc_val).strip()
        record_id = str(ws.cell(r, 5).value or "").strip()
        brand = str(ws.cell(r, 4).value or "").strip()
        product_name = str(ws.cell(r, 2).value or "").strip()

        stats["TOTAL"] += 1
        item = {
            "excel_row": r,
            "barcode": barcode,
            "record_id": record_id,
            "brand": brand,
            "product_name": product_name,
            "defects": [],
            "status": "PASS",
            "metrics": {}
        }

        # 1. Tìm 3 file ảnh tương ứng
        cust_p = CUST_DIR / f"{barcode}.jpg"
        f3_p = find_file(FRONT_V3_DIR, barcode, "front")
        b2_p = find_file(BACK_V2_DIR, barcode, "back")

        item["has_customer_ground_truth"] = cust_p.exists()
        item["has_front_v3"] = f3_p is not None
        item["has_back_v2"] = b2_p is not None

        if not f3_p:
            item["defects"].append("MISSING_FRONT_V3")
            item["status"] = "DEFECT"
            stats["MISSING_FRONT_V3"] += 1
            results.append(item)
            continue

        try:
            f3_im = Image.open(f3_p)
            f3_arr = np.array(f3_im.convert("RGB"))
            f3_w, f3_h = f3_im.size
        except Exception:
            item["defects"].append("CORRUPTED_FRONT_V3")
            item["status"] = "DEFECT"
            results.append(item)
            continue

        # 2. Kiểm tra Structural Canvas
        if (f3_w, f3_h) != (2400, 2400):
            item["defects"].append(f"CANVAS_SIZE_{f3_w}x{f3_h}")
            stats["STRUCTURAL_CANVAS"] += 1

        # Kiểm tra viền ngoài (outer border 4px)
        border_clean = (
            (f3_arr[:4, :] == 255).all() and
            (f3_arr[-4:, :] == 255).all() and
            (f3_arr[:, :4] == 255).all() and
            (f3_arr[:, -4:] == 255).all()
        )
        if not border_clean:
            item["defects"].append("DIRTY_BORDER")

        # 3. Tính độ nét Laplacian & Bounding Box
        bbox = get_foreground_bbox(f3_arr)
        if not bbox:
            item["defects"].append("BLANK_IMAGE")
            item["status"] = "DEFECT"
            results.append(item)
            continue

        x0, y0, x1, y1 = bbox
        pw, ph = x1 - x0, y1 - y0
        pkg_crop = f3_arr[y0:y1, x0:x1]
        gray_pkg = cv2.cvtColor(pkg_crop, cv2.COLOR_RGB2GRAY)
        lap_var = float(cv2.Laplacian(gray_pkg, cv2.CV_64F).var())
        item["metrics"]["laplacian"] = round(lap_var, 1)
        item["metrics"]["package_size"] = [pw, ph]

        # 4. Kiểm tra đứt gãy Guillotine Cut
        if is_guillotine_cut(f3_arr, bbox):
            item["defects"].append("GUILLOTINE_TRUNCATION")
            stats["GUILLOTINE_TRUNCATION"] += 1

        # 5. Đối chiếu với Ảnh mặt sau (Cột Y) - Phát hiện Collision / Tráo mặt
        if b2_p:
            try:
                b2_im = Image.open(b2_p).convert("RGB")
                b2_arr = np.array(b2_im)
                if b2_im.size == f3_im.size:
                    diff = np.abs(f3_arr.astype(int) - b2_arr.astype(int)).mean()
                    item["metrics"]["diff_from_back"] = round(float(diff), 2)
                    if diff < 8.0:
                        item["defects"].append("COLLISION_WITH_BACK_IDENTICAL")
                        stats["COLLISION_WITH_BACK"] += 1
            except Exception:
                pass

        # 6. Đối chiếu với Ground Truth Khách Hàng (Cột W)
        if cust_p.exists():
            try:
                c_im = Image.open(cust_p)
                c_w, c_h = c_im.size
                c_ratio = c_w / float(c_h)
                f3_pkg_ratio = pw / float(ph)

                # Phát hiện lật nhầm 90 độ (Orientation Inversion)
                if (c_ratio < 0.75 and f3_pkg_ratio > 1.25) or (c_ratio > 1.30 and f3_pkg_ratio < 0.70):
                    item["defects"].append("ORIENTATION_INVERTED")
                    stats["ORIENTATION_INVERTED"] += 1

                # Phát hiện cắt ruột (Internal Detail Only): Tỷ lệ khung hình thu nhỏ bất thường
                # Nếu ảnh khách là gói dài nhưng v3 lại bị cắt thành ô vuông nhỏ xíu
                if abs(c_ratio - f3_pkg_ratio) > 0.65:
                    item["defects"].append("ASPECT_RATIO_DISTORTION")

            except Exception:
                pass

        # Đánh giá tổng hợp cho Checker
        if item["defects"]:
            item["status"] = "DEFECT"
        else:
            if lap_var >= 400.0:
                item["status"] = "PASSED_SHARP"
                stats["PASSED_SHARP"] += 1
            else:
                item["status"] = "PASSED_SOFT"
                stats["PASSED_SOFT"] += 1

        results.append(item)

    summary = {
        "scanned_count": len(results),
        "statistics": stats,
        "results": results
    }

    with open(CHECKER_REPORT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("  AGENT 1 (CHECKER): BÁO CÁO KẾT THÚC QUÉT DỮ LIỆU")
    print("=" * 80)
    print(f"  * Tổng số SKU quét              : {stats['TOTAL']}")
    print(f"  * PASSED_SHARP (Đạt chuẩn sắc nét) : {stats['PASSED_SHARP']}")
    print(f"  * PASSED_SOFT (Đạt chuẩn mềm)   : {stats['PASSED_SOFT']}")
    print(f"  * GUILLOTINE (Bị cắt lẹm bao bì) : {stats['GUILLOTINE_TRUNCATION']}")
    print(f"  * ORIENTATION (Lật nhầm chiều)   : {stats['ORIENTATION_INVERTED']}")
    print(f"  * COLLISION (Gán nhầm mặt sau)   : {stats['COLLISION_WITH_BACK']}")
    print(f"  * STRUCTURAL (Lỗi canvas/viền)   : {stats['STRUCTURAL_CANVAS']}")
    print(f"  * MISSING (Thiếu ảnh v3)         : {stats['MISSING_FRONT_V3']}")
    print(f"  * File kết quả                   : {CHECKER_REPORT}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_checker_scan()
