#!/usr/bin/env python3
"""
scripts/run_and_audit_all_batches.py
------------------------------------
Executes extraction and multi-criteria audit for all 1,169 products in 100-item sessions.
Logs ĐẠT / CHƯA ĐẠT with exact error categorization for continuous learning.
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
sys.path.insert(0, str(ROOT / "scripts"))

from studio_front_v3_extractor import process_single_product

BACK_V2_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
FRONT_V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
REPORT_DIR = ROOT / "output/catalog_pairs/audit_batches"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

def audit_single_image(bc: str) -> dict:
    f_path = FRONT_V3_DIR / f"{bc}-front.jpg"
    if not f_path.exists():
        return {
            "barcode": bc,
            "status": "CHƯA ĐẠT",
            "errors": ["File không tồn tại"]
        }

    try:
        im = Image.open(f_path)
        w, h = im.size
    except Exception as exc:
        return {
            "barcode": bc,
            "status": "CHƯA ĐẠT",
            "errors": [f"Lỗi mở ảnh: {exc}"]
        }

    issues = []
    if w < 1200 or h < 1200:
        issues.append(f"Độ phân giải thấp ({w}x{h} < 1200x1200)")

    # Barcode check
    hits = zxingcpp.read_barcodes(im)
    if any("".join(c for c in str(h_hit.text or "") if c.isdigit()) == bc for h_hit in hits):
        issues.append("Mặt trước còn dính mã vạch")

    # Geometry & background analysis
    thumb = im.convert("RGB")
    thumb.thumbnail((600, 600))
    arr = np.asarray(thumb)
    tw, th = thumb.size
    spread = arr.max(axis=2) - arr.min(axis=2)
    mask = ~((arr.min(axis=2) > 240) & (spread < 18))

    cov = float(mask.mean())
    if cov < 0.08:
        issues.append("Chủ thể quá nhỏ (<8% khung hình)")
    else:
        ys, xs = np.where(mask)
        bx0, by0, bx1, by1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
        if bx0 <= 2 or by0 <= 2 or bx1 >= tw - 2 or by1 >= th - 2:
            issues.append("Chạm mép khung hình (thiếu lề an toàn)")

        bw = max(1, bx1 - bx0)
        bh = max(1, by1 - by0)
        aspect = bw / float(bh)
        if aspect < 0.20 or aspect > 3.0:
            issues.append(f"Tỷ lệ bất thường (aspect ratio {aspect:.2f})")

    status = "ĐẠT" if not issues else "CHƯA ĐẠT"
    return {
        "barcode": bc,
        "width": w,
        "height": h,
        "status": status,
        "errors": issues
    }

def run_all_batches(start_batch: int = 0, batch_size: int = 100, audit_only: bool = False):
    bcs = sorted([f.stem.replace("-back", "") for f in BACK_V2_DIR.glob("*-back.jpg")])
    total = len(bcs)
    num_batches = math.ceil(total / batch_size)

    print("===============================================================================")
    print(f"   TIẾN TRÌNH XỬ LÝ & AUDIT TOÀN DIỆN 1.169 ẢNH FRONT-V3 (MỖI ĐỢT {batch_size} ẢNH)   ")
    print(f"   Tổng số sản phẩm: {total} | Tổng số đợt: {num_batches} | Audit only: {audit_only}")
    print("===============================================================================\n")

    summary_records = []

    for b_idx in range(start_batch, num_batches):
        s_idx = b_idx * batch_size
        e_idx = min(total, s_idx + batch_size)
        batch_bcs = bcs[s_idx:e_idx]

        print(f"\n>>> [BẮT ĐẦU ĐỢT {b_idx + 1}/{num_batches}]: Xử lý mã {s_idx + 1} -> {e_idx} ({len(batch_bcs)} ảnh)...")
        
        # 1. Processing
        if not audit_only:
            ok_gen = 0
            for i, bc in enumerate(batch_bcs):
                # If already generated and valid, we can process or skip
                success = process_single_product(bc)
                if success:
                    ok_gen += 1
                if (i + 1) % 25 == 0 or (i + 1) == len(batch_bcs):
                    print(f"    Tiến độ sinh ảnh: {i + 1}/{len(batch_bcs)} (Thành công: {ok_gen})")

        # 2. Auditing
        print(f"    Đang audit đợt {b_idx + 1}...")
        batch_audit_results = []
        dat_count = 0
        chua_dat_count = 0
        error_stats: dict[str, int] = {}

        for bc in batch_bcs:
            res = audit_single_image(bc)
            batch_audit_results.append(res)
            if res["status"] == "ĐẠT":
                dat_count += 1
            else:
                chua_dat_count += 1
                for err in res["errors"]:
                    error_stats[err] = error_stats.get(err, 0) + 1

        batch_report = {
            "batch_index": b_idx + 1,
            "range": f"{s_idx + 1}..{e_idx}",
            "total": len(batch_bcs),
            "dat": dat_count,
            "chua_dat": chua_dat_count,
            "pass_rate": round(dat_count * 100.0 / len(batch_bcs), 1),
            "errors": error_stats,
            "details": batch_audit_results
        }

        # Save batch report
        report_file = REPORT_DIR / f"batch_{b_idx + 1:02d}_audit.json"
        with open(report_file, "w", encoding="utf-8") as rf:
            json.dump(batch_report, rf, ensure_ascii=False, indent=2)

        print(f"--- KẾT QUẢ AUDIT ĐỢT {b_idx + 1} ---")
        print(f"    ĐẠT: {dat_count}/{len(batch_bcs)} ({batch_report['pass_rate']}%)")
        print(f"    CHƯA ĐẠT: {chua_dat_count}/{len(batch_bcs)}")
        if error_stats:
            print(f"    Lỗi thống kê: {error_stats}")
        print(f"    Báo cáo lưu tại: {report_file.name}")

        summary_records.append({
            "batch": b_idx + 1,
            "range": f"{s_idx + 1}..{e_idx}",
            "total": len(batch_bcs),
            "dat": dat_count,
            "chua_dat": chua_dat_count,
            "pass_rate": batch_report["pass_rate"]
        })

    # Save grand summary
    with open(REPORT_DIR / "grand_audit_summary.json", "w", encoding="utf-8") as sf:
        json.dump(summary_records, sf, ensure_ascii=False, indent=2)

    print("\n===============================================================================")
    print("                      HOÀN TẤT TOÀN BỘ CÁC ĐỢT XỬ LÝ & AUDIT                   ")
    print("===============================================================================")

if __name__ == "__main__":
    audit_only = "--audit-only" in sys.argv
    clean_argv = [a for a in sys.argv[1:] if a != "--audit-only"]
    start = int(clean_argv[0]) if len(clean_argv) > 0 else 0
    run_all_batches(start_batch=start, audit_only=audit_only)
