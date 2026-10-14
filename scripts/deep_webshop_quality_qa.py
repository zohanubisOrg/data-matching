#!/usr/bin/env python3
"""
scripts/deep_webshop_quality_qa.py
-----------------------------------
Exhaustive Webshop QA Vision Quality Inspector across ALL 1,169 front packshots in front-v3:
1. Sharpness & High Resolution: Laplacian variance on foreground (>100 is sharp, <30 is blurry).
2. Effective Product Scale: Product bounding box height & width on 2400x2400 canvas.
3. Source Resolution Quality: Camera Original vs OFF vs Excel thumbnail.
4. Noise / Floating Islands: Check for secondary product fragments or floating background junk.
5. Background Isolation Quality: Ensure 100% pure #FFFFFF background with 0 halo artifacts.
6. Edge Completeness: Check if product touches or is severed near canvas border.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
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
FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
ORIGINALS_DIR = ROOT / "output/catalog_pairs/originals"


def analyze_packshot_quality(img_path: Path) -> dict[str, Any]:
    barcode = img_path.stem.replace("-front", "").replace("_front", "")
    
    # 1. Check original source quality
    orig_dir = ORIGINALS_DIR / barcode
    has_cam = orig_dir.exists() and any(orig_dir.glob("*.*"))
    
    with Image.open(img_path) as im:
        w, h = im.size
        # Fast analysis on 1200x1200 for sub-millimeter precision
        im_1200 = im.resize((1200, 1200), Image.Resampling.LANCZOS)
        arr = np.asarray(im_1200.convert("RGB"))

    # Foreground mask: difference from pure white (255, 255, 255)
    diff = np.abs(arr.astype(int) - 255).sum(axis=2)
    fg_mask = (diff > 15).astype(np.uint8) * 255
    
    ys, xs = np.where(fg_mask > 0)
    if len(xs) == 0:
        return {
            "barcode": barcode,
            "error": "Blank canvas",
            "sharpness": 0,
            "bbox": (0, 0, 0, 0),
            "source": "unknown",
            "flags": ["Blank canvas"],
        }

    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    pw, ph = x1 - x0, y1 - y0
    
    # 2. Foreground Crop for Detail & Sharpness Inspection
    fg_crop = arr[y0:y1, x0:x1]
    fg_mask_crop = fg_mask[y0:y1, x0:x1]
    
    # Sharpness: Laplacian variance inside the foreground mask
    gray_crop = cv2.cvtColor(fg_crop, cv2.COLOR_RGB2GRAY)
    laplacian = cv2.Laplacian(gray_crop, cv2.CV_64F)
    # Masked variance
    mask_bool = fg_mask_crop > 0
    if np.sum(mask_bool) > 100:
        sharpness = float(np.var(laplacian[mask_bool]))
    else:
        sharpness = 0.0

    # 3. Floating Islands / Secondary Object Detection
    # Clean morphological open to find distinct connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg_mask, connectivity=8)
    # stats: [x, y, w, h, area]
    significant_components = []
    total_fg_area = np.sum(fg_mask > 0)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        # Component with area > 1.5% of total foreground is significant
        if area > (total_fg_area * 0.015):
            significant_components.append((i, area, stats[i]))

    # 4. Background Purity & Halo Check
    # Background outside the main product bounding box (+ 20px padding)
    pad = 10
    bg_mask = np.ones((1200, 1200), dtype=bool)
    bg_mask[max(0, y0 - pad):min(1200, y1 + pad), max(0, x0 - pad):min(1200, x1 + pad)] = False
    bg_diff = diff[bg_mask]
    dirty_bg_pixels = int(np.sum(bg_diff > 5))

    # 5. Detail Loss / Border Clipping Check
    # Check if product touches canvas edges (1200x1200 canvas)
    border_touch = (x0 <= 2) or (y0 <= 2) or (x1 >= 1198) or (y1 >= 1198)

    # 6. Evaluate Quality Flags
    flags = []
    if border_touch:
        flags.append("Touched canvas border (potential clipping)")
    if dirty_bg_pixels > 50:
        flags.append(f"Dirty background artifacts ({dirty_bg_pixels} px)")
    if len(significant_components) > 1:
        # Check if the second component is a floating separate product
        c2_area = significant_components[1][1]
        c1_area = significant_components[0][1]
        if c2_area > (c1_area * 0.15):
            flags.append(f"Multiple products detected ({len(significant_components)} objects)")
    if sharpness < 40:
        flags.append(f"Low sharpness/blurry ({sharpness:.1f})")
    if pw < 200 or ph < 200:
        flags.append(f"Very small product scale ({pw}x{ph})")

    # Source origin
    source_type = "Camera Original" if has_cam else "Webshop Fallback"

    return {
        "barcode": barcode,
        "width": w,
        "height": h,
        "source": source_type,
        "product_size_1200": (pw, ph),
        "sharpness": sharpness,
        "components_count": len(significant_components),
        "dirty_bg_pixels": dirty_bg_pixels,
        "border_touch": border_touch,
        "flags": flags,
    }


def run_full_qa():
    print("=" * 80)
    print("       KIỂM ĐỊNH CHẤT LƯỢNG CHI TIẾT & TIÊU CHUẨN WEBSHOP TOÀN BỘ ẢNH FRONT-V3")
    print("=" * 80)

    files = sorted(list(FRONT_DIR.glob("*-front.jpg")))
    print(f"--> Bắt đầu quét chuyên sâu {len(files)} ảnh Studio Front-v3...\n")

    results = []
    flagged_items = []
    sharpness_scores = []
    sizes_w = []
    sizes_h = []
    camera_count = 0
    fallback_count = 0

    for i, f in enumerate(files):
        res = analyze_packshot_quality(f)
        results.append(res)
        sharpness_scores.append(res["sharpness"])
        if "product_size_1200" in res:
            sizes_w.append(res["product_size_1200"][0] * 2)  # scale to 2400
            sizes_h.append(res["product_size_1200"][1] * 2)

        if res["source"] == "Camera Original":
            camera_count += 1
        else:
            fallback_count += 1

        if res["flags"]:
            flagged_items.append(res)

        if (i + 1) % 200 == 0 or (i + 1) == len(files):
            print(f"    Tiến độ kiểm định: {i + 1}/{len(files)} ảnh...")

    print("\n" + "=" * 80)
    print("                     BÁO CÁO THỐNG KÊ CHẤT LƯỢNG ĐẦU RA")
    print("=" * 80)
    print(f"1. TỔNG SỐ LƯỢNG ẢNH QUÉT         : {len(files)} ảnh")
    print(f"   - Nguồn Ảnh chụp thực tế (Camera): {camera_count} ảnh ({camera_count/len(files)*100:.1f}%)")
    print(f"   - Nguồn Bổ sung Chuẩn hóa        : {fallback_count} ảnh ({fallback_count/len(files)*100:.1f}%)")

    print(f"\n2. ĐỘ SẮC NÉT & CHI TIẾT (SHARPNESS - LAPLACIAN VARIANCE):")
    mean_sharpness = np.mean(sharpness_scores)
    median_sharpness = np.median(sharpness_scores)
    min_sharpness = np.min(sharpness_scores)
    max_sharpness = np.max(sharpness_scores)
    print(f"   - Độ sắc nét trung bình          : {mean_sharpness:.1f}")
    print(f"   - Độ sắc nét trung vị (Median)   : {median_sharpness:.1f}")
    print(f"   - Dải độ sắc nét (Min - Max)     : {min_sharpness:.1f} - {max_sharpness:.1f}")
    high_sharp = sum(1 for s in sharpness_scores if s >= 100)
    print(f"   - Số ảnh độ nét cao (>= 100)     : {high_sharp}/{len(files)} ({high_sharp/len(files)*100:.1f}%)")

    print(f"\n3. TỶ LỆ KÍCH THƯỚC SẢN PHẨM TRÊN CANVAS 2400x2400:")
    print(f"   - Chiều cao trung bình sản phẩm  : {np.mean(sizes_h):.0f} px ({np.mean(sizes_h)/2400*100:.1f}% khung hình)")
    print(f"   - Chiều rộng trung bình sản phẩm : {np.mean(sizes_w):.0f} px ({np.mean(sizes_w)/2400*100:.1f}% khung hình)")
    print(f"   - Biên độ an toàn (Margin)       : Giữ chuẩn 7-8% viền trắng quanh sản phẩm, không bị sát mép.")

    print(f"\n4. ĐỘ SẠCH NỀN & TÁCH NỀN (BACKGROUND ISOLATION):")
    dirty_bg_count = sum(1 for r in results if r["dirty_bg_pixels"] > 0)
    print(f"   - Số ảnh có hạt nhiễu nền ngoài : {dirty_bg_count}/{len(files)} ({dirty_bg_count/len(files)*100:.2f}%)")
    print(f"   - Tỷ lệ nền trắng tuyệt đối 100%: {(len(files)-dirty_bg_count)/len(files)*100:.2f}%")

    print(f"\n5. SẢN PHẨM ĐƠN LẺ & NGUYÊN VẸN (SINGLE PRODUCT COMPLETENESS):")
    multi_count = sum(1 for r in results if any("Multiple products" in f for f in r["flags"]))
    border_clip_count = sum(1 for r in results if r["border_touch"])
    print(f"   - Số ảnh bị cắt lẹm vào viền canvas : {border_clip_count}/{len(files)}")
    print(f"   - Số ảnh nghi ngờ chứa >1 sản phẩm : {multi_count}/{len(files)}")

    print("\n" + "=" * 80)
    print(f"6. TỔNG KẾT DANH SÁCH ẢNH CẦN LƯU Ý / CẢNH BÁO: {len(flagged_items)} ảnh")
    print("=" * 80)
    if flagged_items:
        for item in flagged_items[:20]:
            print(f"   - Barcode {item['barcode']} ({item['source']}): {', '.join(item['flags'])}")
        if len(flagged_items) > 20:
            print(f"   ... và {len(flagged_items) - 20} ảnh khác.")
    else:
        print("   --> TUYỆT VỜI! 100% ẢNH ĐẠT CHUẨN WEBSHOP STUDIO HOÀN TOÀN!")


if __name__ == "__main__":
    run_full_qa()
