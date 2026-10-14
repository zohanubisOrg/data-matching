#!/usr/bin/env python3
"""
scripts/audit_front_v2.py
-------------------------
Audit toàn diện 782 ảnh trong thư mục output/catalog_pairs/tagged/front-v2:
1. File hợp lệ / Không bị trắng trơn (blank/corrupted)
2. Barcode leakage: Mặt trước có còn bị dính Barcode không (nếu có barcode => nhầm mặt sau)
3. Hướng xoay (Sideways/Landscape): Sản phẩm có bị xoay ngang / text dọc bất thường không
4. Dính 2 gói (Two-packs / Multi-subject): Còn sót cả 2 bao bì cạnh nhau chưa tách rời
5. Cắt lẹm / Dải mỏng (Strip / Slivers / Over-cropped): Tỷ lệ méo mó bất thường, bị cắt cụt
6. Tỷ lệ chiếm khung hình (Coverage): Quá nhỏ (tiny < 12%) hoặc quá mép
7. Đối chiếu với Excel gốc Rabuta 12.10
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
import zxingcpp
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup
from product_mapper.vision.barcode_validator import (
    get_barcode_lookup_variants,
    validate_ean_upc_checksum,
)

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
REPORT_PATH = ROOT / "output/catalog_pairs/front_v2_audit_report.json"
REVIEW_DIR = ROOT / "output/catalog_pairs/front_v2_flagged"


def content_mask(rgb: np.ndarray) -> np.ndarray:
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    white = (rgb.min(axis=2) > 240) & (spread < 16)
    return ~white


def text_score(gray: np.ndarray, mask: np.ndarray) -> float:
    if int(mask.sum()) < 80:
        return 1.0
    vertical = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    horizontal = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    energy = vertical + horizontal
    if int(mask.sum()) == 0:
        return 1.0
    threshold = np.percentile(energy[mask], 60)
    strong = mask & (energy > threshold)
    if int(strong.sum()) < 40:
        strong = mask
    h_mean = max(float(horizontal[strong].mean()), 1.0)
    v_mean = float(vertical[strong].mean())
    return v_mean / h_mean


def check_barcode(image: Image.Image) -> list[str]:
    hits = zxingcpp.read_barcodes(
        image,
        formats=zxingcpp.BarcodeFormat.EANUPC,
        try_rotate=True,
        try_downscale=True,
    )
    valid_codes = []
    for hit in hits:
        text = "".join(ch for ch in str(hit.text or "") if ch.isdigit())
        if validate_ean_upc_checksum(text):
            valid_codes.append(text)
    return valid_codes


def audit_single_image(path_str: str) -> dict:
    path = Path(path_str)
    raw_barcode = path.stem.replace("-front", "").replace("_front", "")
    
    try:
        orig_img = Image.open(path)
        orig_w, orig_h = orig_img.size
        if orig_w == 0 or orig_h == 0:
            return {
                "file": path.name,
                "barcode": raw_barcode,
                "reasons": ["corrupted-zero-size"],
                "severity": "CRITICAL",
            }
    except Exception as exc:
        return {
            "file": path.name,
            "barcode": raw_barcode,
            "reasons": [f"cannot-open: {exc}"],
            "severity": "CRITICAL",
        }

    # 1. Kiểm tra Barcode trên ảnh Mặt Trước
    barcode_hits = check_barcode(orig_img)
    has_barcode = len(barcode_hits) > 0

    # 2. Thu nhỏ để phân tích hình học & độ phủ
    thumb = orig_img.convert("RGB")
    thumb.thumbnail((500, 500))
    rgb = np.asarray(thumb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mask = content_mask(rgb)
    th_h, th_w = mask.shape
    frame_area = th_w * th_h

    coverage = float(mask.mean())
    
    # Bounding box của sản phẩm
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return {
            "file": path.name,
            "barcode": raw_barcode,
            "reasons": ["blank-white"],
            "severity": "CRITICAL",
            "coverage": 0.0,
            "aspect_ratio": 1.0,
            "barcode_hits": barcode_hits,
        }

    bx0, by0 = int(xs.min()), int(ys.min())
    bx1, by1 = int(xs.max() + 1), int(ys.max() + 1)
    bw = max(1, bx1 - bx0)
    bh = max(1, by1 - by0)
    aspect_ratio = bw / float(bh)

    # Connected components kiểm tra 2 sản phẩm chưa tách (two-packs)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    blobs = []
    for idx in range(1, count):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area >= frame_area * 0.03:
            blobs.append({
                "area": area / frame_area,
                "x": int(stats[idx, cv2.CC_STAT_LEFT]),
                "y": int(stats[idx, cv2.CC_STAT_TOP]),
                "w": int(stats[idx, cv2.CC_STAT_WIDTH]),
                "h": int(stats[idx, cv2.CC_STAT_HEIGHT]),
            })
    blobs.sort(key=lambda item: item["area"], reverse=True)

    t_score = text_score(gray, mask)

    reasons: list[str] = []

    # Tiêu chí 1: Barcode leakage
    if has_barcode:
        reasons.append("has-barcode-leakage")

    # Tiêu chí 2: Trắng trơn hoặc quá nhỏ
    if coverage < 0.09:
        reasons.append("tiny-content")
    elif coverage < 0.15 and (bw < th_w * 0.35 and bh < th_h * 0.35):
        reasons.append("undersized-subject")

    # Tiêu chí 3: Cắt lẹm dạng dải (Strip / Sliver)
    if aspect_ratio > 2.6:
        reasons.append("extreme-landscape-strip")
    elif aspect_ratio < 0.30:
        reasons.append("extreme-vertical-sliver")

    # Tiêu chí 4: Xoay ngang (Sideways orientation)
    if t_score >= 1.45 and aspect_ratio > 1.25:
        reasons.append("likely-sideways-text")
    elif aspect_ratio > 1.85 and coverage > 0.35:
        reasons.append("wide-landscape-packaging")

    # Tiêu chí 5: Dính 2 gói chưa tách rời
    if len(blobs) >= 2 and blobs[1]["area"] >= 0.09:
        gap_x = blobs[0]["x"] > (blobs[1]["x"] + blobs[1]["w"]) or blobs[1]["x"] > (blobs[0]["x"] + blobs[0]["w"])
        gap_y = blobs[0]["y"] > (blobs[1]["y"] + blobs[1]["h"]) or blobs[1]["y"] > (blobs[0]["y"] + blobs[0]["h"])
        if gap_x or gap_y:
            reasons.append("two-packs-unsplit")

    severity = "OK"
    if any(r in ("has-barcode-leakage", "blank-white", "corrupted-zero-size", "two-packs-unsplit") for r in reasons):
        severity = "CRITICAL"
    elif reasons:
        severity = "WARNING"

    return {
        "file": path.name,
        "barcode": raw_barcode,
        "width": orig_w,
        "height": orig_h,
        "coverage": round(coverage, 3),
        "aspect_ratio": round(aspect_ratio, 2),
        "text_score": round(t_score, 2),
        "blobs": len(blobs),
        "barcode_hits": barcode_hits,
        "reasons": reasons,
        "severity": severity,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit front-v2 packshot images")
    parser.add_argument("--front-dir", type=Path, default=FRONT_DIR)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    files = sorted(args.front_dir.glob("*-front.jpg"))
    if not files:
        files = sorted(args.front_dir.glob("*.jpg"))

    print(f"--> Bắt đầu audit {len(files)} ảnh trong: {args.front_dir}", flush=True)

    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit_single_image, str(p)): p for p in files}
        total = len(futures)
        for done, fut in enumerate(as_completed(futures), start=1):
            res = fut.result()
            # Đối chiếu Excel
            bc = res["barcode"]
            excel_bc = lookup.get(bc)
            if not excel_bc:
                for var in get_barcode_lookup_variants(bc):
                    if var in lookup:
                        excel_bc = lookup[var]
                        break
            res["excel_barcode"] = excel_bc or ""
            if not excel_bc:
                res["reasons"].append("not-in-excel-12.10")
                if res["severity"] == "OK":
                    res["severity"] = "WARNING"

            results.append(res)
            if done % 100 == 0 or done == total:
                flagged_count = sum(1 for r in results if r["severity"] != "OK")
                print(f"  Đã audit {done}/{total} ảnh  |  Phát hiện nghi vấn: {flagged_count}", flush=True)

    # Phân loại và tổng kết
    results.sort(key=lambda r: (0 if r["severity"] == "CRITICAL" else 1 if r["severity"] == "WARNING" else 2, r["file"]))

    critical_list = [r for r in results if r["severity"] == "CRITICAL"]
    warning_list = [r for r in results if r["severity"] == "WARNING"]
    clean_list = [r for r in results if r["severity"] == "OK"]

    # Thống kê nguyên nhân
    reason_counts: dict[str, int] = {}
    for r in results:
        for reason in r["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    report = {
        "total_audited": len(results),
        "clean_count": len(clean_list),
        "critical_count": len(critical_list),
        "warning_count": len(warning_list),
        "reason_summary": reason_counts,
        "critical_items": critical_list,
        "warning_items": warning_list,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===============================================================================")
    print("                    KẾT QUẢ AUDIT ẢNH MẶT TRƯỚC FRONT-V2                       ")
    print("===============================================================================")
    print(f"  * Tổng số ảnh audit      : {len(results)}")
    print(f"  * Ảnh ĐẠT CHUẨN (Clean)  : {len(clean_list)} ({len(clean_list)/len(results)*100:.1f}%)")
    print(f"  * Ảnh LỖI NẶNG (Critical): {len(critical_list)}")
    print(f"  * Cần xem xét (Warning)  : {len(warning_list)}")
    print("-------------------------------------------------------------------------------")
    print("  Chi tiết các lỗi phát hiện:")
    for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    - {reason:<28}: {count} ảnh")
    print("===============================================================================")
    print(f"Báo cáo chi tiết đã lưu tại: {REPORT_PATH}\n", flush=True)


if __name__ == "__main__":
    main()
