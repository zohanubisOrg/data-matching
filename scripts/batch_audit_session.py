#!/usr/bin/env python3
"""
scripts/batch_audit_session.py
------------------------------
Audit toàn bộ 1.169 ảnh mặt trước theo từng phiên 100 ảnh:
- Phân loại rõ từng ảnh: ĐẠT / CHƯA ĐẠT
- Chỉ rõ lỗi cụ thể (dính 2 gói/chai, dính mã vạch, cắt lố, bao bì trong suốt bị lẹm, mờ...)
- Tổng hợp bài học kinh nghiệm sau từng batch để chuẩn hóa kho ảnh.
"""

from __future__ import annotations

import json
import math
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
from PIL import Image
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
REPORT_DIR = ROOT / "output/catalog_pairs/audit_batches"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_JSON = ROOT / "output/catalog_pairs/audit_1169_summary.json"


def audit_image(path: Path, expected_barcode: str, product_name: str) -> dict:
    issues = []

    try:
        im = Image.open(path)
        w, h = im.size
        if w < 100 or h < 100:
            return {
                "file": path.name,
                "barcode": expected_barcode,
                "name": product_name,
                "status": "CHƯA ĐẠT",
                "errors": ["Ảnh rỗng hoặc hỏng (zero size)"],
            }
    except Exception as exc:
        return {
            "file": path.name,
            "barcode": expected_barcode,
            "name": product_name,
            "status": "CHƯA ĐẠT",
            "errors": [f"Không thể đọc file: {exc}"],
        }

    # 1. Kiểm tra độ phân giải
    if w < 1200 or h < 1200:
        issues.append(f"Độ phân giải thấp ({w}x{h} < 1200x1200)")

    # 2. Kiểm tra dính mã vạch trên mặt trước (Barcode leakage)
    hits = zxingcpp.read_barcodes(im)
    if any("".join(c for c in str(h_hit.text or "") if c.isdigit()) == expected_barcode for h_hit in hits):
        issues.append("Mặt trước còn dính mã vạch (chưa tách đúng mặt)")

    # 3. Phân tích nền và khung hình
    thumb = im.convert("RGB")
    thumb.thumbnail((600, 600))
    rgb = np.asarray(thumb)
    tw, th = thumb.size

    spread = rgb.max(axis=2) - rgb.min(axis=2)
    mask = ~((rgb.min(axis=2) > 240) & (spread < 18))
    coverage = float(mask.mean())

    if coverage < 0.08:
        issues.append("Chủ thể quá nhỏ hoặc ảnh trắng trơn (< 8% khung hình)")
    else:
        ys, xs = np.where(mask)
        bx0, by0 = int(xs.min()), int(ys.min())
        bx1, by1 = int(xs.max() + 1), int(ys.max() + 1)
        bw = max(1, bx1 - bx0)
        bh = max(1, by1 - by0)
        aspect = bw / float(bh)

        # 4. Kiểm tra cắt lố / chạm sát mép khung hình
        touch_border = (bx0 <= 3) or (by0 <= 3) or (bx1 >= tw - 3) or (by1 >= th - 3)
        if touch_border:
            issues.append("Cắt lố / chạm sát mép khung hình (thiếu lề padding)")

        # 5. Tỷ lệ méo mó bất thường
        if aspect < 0.20:
            issues.append(f"Tỷ lệ dải dọc bất thường (aspect ratio {aspect:.2f} < 0.20)")
        elif aspect > 2.8:
            issues.append(f"Tỷ lệ dải ngang bất thường (aspect ratio {aspect:.2f} > 2.80)")

        # 6. Kiểm tra dính 2 gói/chai chưa tách rời (Two-packs / Multi-subject)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        frame_area = tw * th
        big_blobs = []
        for i in range(1, count):
            area = stats[i, cv2.CC_STAT_AREA]
            if area > frame_area * 0.07:
                big_blobs.append({
                    "area": area / frame_area,
                    "x": stats[i, cv2.CC_STAT_LEFT],
                    "y": stats[i, cv2.CC_STAT_TOP],
                    "w": stats[i, cv2.CC_STAT_WIDTH],
                    "h": stats[i, cv2.CC_STAT_HEIGHT],
                })
        big_blobs.sort(key=lambda x: x["area"], reverse=True)

        if len(big_blobs) >= 2:
            gap_x = (big_blobs[0]["x"] > big_blobs[1]["x"] + big_blobs[1]["w"]) or (big_blobs[1]["x"] > big_blobs[0]["x"] + big_blobs[0]["w"])
            gap_y = (big_blobs[0]["y"] > big_blobs[1]["y"] + big_blobs[1]["h"]) or (big_blobs[1]["y"] > big_blobs[0]["y"] + big_blobs[0]["h"])
            if gap_x or gap_y:
                issues.append("Dính 2 sản phẩm/chai chưa tách rời")

        # 7. Kiểm tra bao bì trong suốt bị đục thủng
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            hull = cv2.convexHull(max(contours, key=cv2.contourArea))
            hull_mask = np.zeros_like(mask, dtype=np.uint8)
            cv2.drawContours(hull_mask, [hull], -1, 1, thickness=-1)
            hull_area = float(hull_mask.sum())
            solid_ratio = float(mask.sum()) / max(1.0, hull_area)
            if solid_ratio < 0.45 and 0.4 < aspect < 1.8:
                issues.append("Bao bì trong suốt bị đục thủng / xé vụn (solid ratio < 0.45)")

    status = "ĐẠT" if len(issues) == 0 else "CHƯA ĐẠT"

    return {
        "file": path.name,
        "barcode": expected_barcode,
        "name": product_name,
        "width": w,
        "height": h,
        "status": status,
        "errors": issues,
    }


def run_batch_audit():
    print("===============================================================================")
    print("     AUDIT ĐỘC LẬP TOÀN BỘ 1.169 ẢNH MẶT TRƯỚC THEO TỪNG PHIÊN 100 ẢNH        ")
    print("===============================================================================\n")

    products = load_ground_truth(EXCEL_SOURCE)
    prod_by_bc = {p["barcode"]: p for p in products}

    files = sorted(FRONT_DIR.glob("*-front.jpg"))
    total_files = len(files)
    print(f"Tổng số ảnh kiểm tra: {total_files} ảnh.")

    batch_size = 100
    total_batches = math.ceil(total_files / batch_size)

    all_results = []
    batch_summaries = []

    for b_idx in range(total_batches):
        start_i = b_idx * batch_size
        end_i = min(start_i + batch_size, total_files)
        batch_files = files[start_i:end_i]

        batch_name = f"Phiên {b_idx + 1:02d} (Ảnh {start_i + 1:04d} - {end_i:04d})"
        print(f"\n---> BẮT ĐẦU {batch_name} ({len(batch_files)} ảnh):")

        batch_results = []
        for f in batch_files:
            bc = f.stem.replace("-front", "")
            p = prod_by_bc.get(bc, {})
            name = p.get("name_en", "")
            res = audit_image(f, bc, name)
            batch_results.append(res)
            all_results.append(res)

        passed = sum(1 for r in batch_results if r["status"] == "ĐẠT")
        failed = len(batch_results) - passed

        print(f"     Kết quả: ĐẠT: {passed}/{len(batch_results)} ({passed/len(batch_results)*100:.1f}%) | CHƯA ĐẠT: {failed}")

        # Thống kê các lỗi trong phiên
        err_counts: dict[str, int] = {}
        failed_items = [r for r in batch_results if r["status"] == "CHƯA ĐẠT"]
        for r in failed_items:
            for err in r["errors"]:
                err_counts[err] = err_counts.get(err, 0) + 1

        if failed_items:
            print("     Các lỗi chính phát hiện trong phiên này:")
            for err, cnt in sorted(err_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"       * {err}: {cnt} ảnh")
            print("     Mẫu ảnh chưa đạt tiêu biểu:")
            for item in failed_items[:3]:
                print(f"       - {item['file']} ({item['barcode']}): {', '.join(item['errors'])}")

        batch_summaries.append({
            "batch_index": b_idx + 1,
            "batch_name": batch_name,
            "total": len(batch_results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(batch_results) * 100, 1),
            "error_distribution": err_counts,
            "failed_items": failed_items,
        })

    # Tổng kết toàn bộ
    total_passed = sum(1 for r in all_results if r["status"] == "ĐẠT")
    total_failed = len(all_results) - total_passed

    overall_errors: dict[str, int] = {}
    for r in all_results:
        for err in r["errors"]:
            overall_errors[err] = overall_errors.get(err, 0) + 1

    summary_data = {
        "total_audited": len(all_results),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "pass_rate": round(total_passed / len(all_results) * 100, 1),
        "overall_error_distribution": overall_errors,
        "batches": batch_summaries,
    }

    SUMMARY_JSON.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===============================================================================")
    print("                     TỔNG KẾT TOÀN BỘ 1.169 ẢNH MẶT TRƯỚC                      ")
    print("===============================================================================")
    print(f"  * Tổng số ảnh audit               : {len(all_results)}")
    print(f"  * Số ảnh ĐẠT TIÊU CHUẨN           : {total_passed} ({total_passed/len(all_results)*100:.1f}%)")
    print(f"  * Số ảnh CHƯA ĐẠT (CẦN TỐI ƯU)    : {total_failed} ({total_failed/len(all_results)*100:.1f}%)")
    print("-------------------------------------------------------------------------------")
    print("  Phân bố lỗi trên toàn hệ thống:")
    for err, cnt in sorted(overall_errors.items(), key=lambda x: x[1], reverse=True):
        print(f"    - {err:<45}: {cnt} ảnh")
    print("===============================================================================")
    print(f"  Báo cáo chi tiết từng phiên đã lưu tại: {SUMMARY_JSON}\n")


if __name__ == "__main__":
    run_batch_audit()
