#!/usr/bin/env python3
"""
scripts/audit_front_comprehensive.py
-----------------------------------
Audits the entire front-v2 folder, cross-references with back-v2 and the customer Excel:
1. Inspects all front-v2 images for:
   - Barcode leakage (front contains barcode = back face mistakenly used as front)
   - Extreme slivers / over-cropped
   - Two-packs unsplit
   - Transparent packaging erosion / holes / missing packaging borders
   - Tiny / undersized subject
2. Identifies all 217 back-v2 items missing in front-v2:
   - Identifies source photo and layout (single-face vs dual-panel)
3. Identifies all 180 Excel items missing in both front and back
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup
from product_mapper.vision.barcode_validator import (
    get_barcode_lookup_variants,
    validate_ean_upc_checksum,
)

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
REPORT_PATH = ROOT / "output/catalog_pairs/front_v2_comprehensive_audit.json"


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


def audit_front_image(path_str: str) -> dict:
    path = Path(path_str)
    raw_barcode = path.stem.replace("-front", "").replace("_front", "")

    try:
        orig_img = Image.open(path)
        orig_w, orig_h = orig_img.size
        if orig_w == 0 or orig_h == 0:
            return {
                "file": path.name,
                "barcode": raw_barcode,
                "issues": ["corrupted-zero-size"],
                "severity": "CRITICAL",
            }
    except Exception as exc:
        return {
            "file": path.name,
            "barcode": raw_barcode,
            "issues": [f"cannot-open: {exc}"],
            "severity": "CRITICAL",
        }

    # 1. Barcode leakage check
    barcode_hits = check_barcode(orig_img)
    has_barcode = len(barcode_hits) > 0

    # 2. Thumbnail geometric & coverage analysis
    thumb = orig_img.convert("RGB")
    thumb.thumbnail((600, 600))
    rgb = np.asarray(thumb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # Detect non-white content
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    white = (rgb.min(axis=2) > 240) & (spread < 18)
    mask = ~white
    th_h, th_w = mask.shape
    frame_area = th_w * th_h

    coverage = float(mask.mean())
    issues = []

    if coverage < 0.05:
        issues.append("blank-or-near-empty")
    else:
        ys, xs = np.where(mask)
        bx0, by0 = int(xs.min()), int(ys.min())
        bx1, by1 = int(xs.max() + 1), int(ys.max() + 1)
        bw = max(1, bx1 - bx0)
        bh = max(1, by1 - by0)
        aspect_ratio = bw / float(bh)

        # Slivers
        if aspect_ratio > 2.5:
            issues.append("extreme-landscape-strip")
        elif aspect_ratio < 0.32:
            issues.append("extreme-vertical-sliver")

        # Tiny subject
        if coverage < 0.12 and (bw < th_w * 0.35 and bh < th_h * 0.35):
            issues.append("tiny-subject")

        # Multi-object check (two-packs)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        blobs = []
        for idx in range(1, count):
            area = int(stats[idx, cv2.CC_STAT_AREA])
            if area >= frame_area * 0.03:
                blobs.append(area / frame_area)
        if len(blobs) >= 2 and blobs[1] >= 0.08:
            issues.append("two-packs-unsplit")

        # Check for transparent packaging erosion / jagged borders / missing edges:
        # A transparent package often has an internal hole or significant convex-hull hollows
        hull_mask = np.zeros_like(mask, dtype=np.uint8)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cv2.drawContours(hull_mask, contours, -1, 1, thickness=-1)
            hull_area = float(hull_mask.sum())
            solid_ratio = float(mask.sum()) / max(1.0, hull_area)
            # If solid ratio is low (< 0.65) and not a doughnut or bottle neck, it indicates missing transparent packaging inside or eroded borders
            if solid_ratio < 0.62 and aspect_ratio > 0.45 and aspect_ratio < 1.8:
                issues.append("suspicious-transparent-erosion")

    if has_barcode:
        issues.append("has-barcode-leakage")

    severity = "OK"
    if any(i in ("has-barcode-leakage", "blank-or-near-empty", "corrupted-zero-size", "two-packs-unsplit") for i in issues):
        severity = "CRITICAL"
    elif issues:
        severity = "WARNING"

    return {
        "file": path.name,
        "barcode": raw_barcode,
        "width": orig_w,
        "height": orig_h,
        "coverage": round(coverage, 3),
        "aspect_ratio": round(aspect_ratio if 'aspect_ratio' in locals() else 1.0, 2),
        "barcode_hits": barcode_hits,
        "issues": issues,
        "severity": severity,
    }


def main():
    print("--> 1. Đang nạp danh mục Excel khách 12.10...")
    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    excel_by_bc = {p["barcode"]: p for p in products}

    print(f"    Tổng sản phẩm Excel: {len(products)}")

    # Load manifests
    manifest_files = [
        ROOT / "output/catalog_pairs/manifest_G1_original_v2.json",
        ROOT / "output/catalog_pairs/manifest_G2_original_v2.json",
        ROOT / "output/catalog_pairs/manifest_G3_Original_v2.json",
        ROOT / "output/catalog_pairs/manifest_G4-original_v2.json",
        ROOT / "output/catalog_pairs/manifest_Nyt25.09.26_v2.json",
        ROOT / "output/catalog_pairs/manifest.json",
    ]
    manifest_products = {}
    for mf in manifest_files:
        if mf.exists():
            with open(mf, encoding="utf-8") as f:
                d = json.load(f)
                for k, v in d.get("products", {}).items():
                    if k not in manifest_products or not manifest_products[k].get("source"):
                        manifest_products[k] = v

    # 2. Audit front-v2 files
    front_files = sorted(FRONT_DIR.glob("*-front.jpg"))
    if not front_files:
        front_files = sorted(FRONT_DIR.glob("*.jpg"))

    print(f"--> 2. Đang audit {len(front_files)} ảnh trong front-v2...")
    front_results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(audit_front_image, str(p)): p for p in front_files}
        for done, fut in enumerate(as_completed(futures), start=1):
            res = fut.result()
            bc = res["barcode"]
            res["excel_info"] = excel_by_bc.get(bc)
            res["source_info"] = manifest_products.get(bc)
            front_results.append(res)

    front_results.sort(key=lambda r: (0 if r["severity"] == "CRITICAL" else 1 if r["severity"] == "WARNING" else 2, r["file"]))

    # 3. Check back-v2 matching
    back_files = sorted(BACK_DIR.glob("*-back.jpg"))
    if not back_files:
        back_files = sorted(BACK_DIR.glob("*.jpg"))

    back_bcs = {b.stem.replace("-back", "").replace("_back", ""): b for b in back_files}
    front_bcs = {r["barcode"]: r for r in front_results}

    missing_front_bcs = sorted(list(set(back_bcs.keys()) - set(front_bcs.keys())))
    missing_front_items = []
    for bc in missing_front_bcs:
        item = {
            "barcode": bc,
            "back_file": str(back_bcs[bc].name),
            "excel_info": excel_by_bc.get(bc),
            "manifest_info": manifest_products.get(bc),
        }
        missing_front_items.append(item)

    # 4. Barcodes missing in both back and front
    excel_all_bcs = set(excel_by_bc.keys())
    present_bcs = set(back_bcs.keys()) | set(front_bcs.keys())
    missing_both_bcs = sorted(list(excel_all_bcs - present_bcs))
    missing_both_items = [
        {"barcode": bc, "excel_info": excel_by_bc.get(bc)}
        for bc in missing_both_bcs
    ]

    report = {
        "front_v2_total": len(front_results),
        "front_clean": sum(1 for r in front_results if r["severity"] == "OK"),
        "front_critical": sum(1 for r in front_results if r["severity"] == "CRITICAL"),
        "front_warning": sum(1 for r in front_results if r["severity"] == "WARNING"),
        "back_v2_total": len(back_files),
        "missing_front_in_back_count": len(missing_front_items),
        "missing_both_count": len(missing_both_items),
        "front_critical_items": [r for r in front_results if r["severity"] == "CRITICAL"],
        "front_warning_items": [r for r in front_results if r["severity"] == "WARNING"],
        "missing_front_items": missing_front_items,
        "missing_both_items": missing_both_items,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n===============================================================================")
    print("               KẾT QUẢ AUDIT TOÀN DIỆN FRONT-V2, BACK-V2 & EXCEL              ")
    print("===============================================================================")
    print(f"  * Tổng số ảnh front-v2 hiện có : {len(front_results)}")
    print(f"    - Đạt chuẩn (Clean)         : {report['front_clean']}")
    print(f"    - Lỗi nặng (Critical)       : {report['front_critical']}")
    print(f"    - Cần xem xét (Warning)     : {report['front_warning']}")
    print(f"  * Tổng số ảnh back-v2          : {len(back_files)}")
    print(f"  * Số barcode có Back nhưng THIẾU Front : {len(missing_front_items)}")
    print(f"  * Số barcode Excel THIẾU CẢ Back & Front : {len(missing_both_items)}")
    print("===============================================================================")
    print(f"  Báo cáo chi tiết: {REPORT_PATH}\n")


if __name__ == "__main__":
    main()
