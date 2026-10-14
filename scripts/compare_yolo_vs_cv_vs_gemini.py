#!/usr/bin/env python3
"""
scripts/compare_yolo_vs_cv_vs_gemini.py
----------------------------------------
So sánh hiệu năng và chất lượng nhận diện mặt trước/sau giữa 3 phương pháp:
1. OpenCV Heuristic (cv_front_detector.py)
2. Cached Gemini Vision AI (g2_g5_front_boxes.json)
3. YOLO Packaging Detector (src/product_mapper/vision/yolo_detector.py)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from PIL import Image

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from scripts.cv_front_detector import detect_front_box_cv
from src.product_mapper.vision.yolo_detector import YOLOPackagingDetector

def calculate_iou(boxA: list[int], boxB: list[int]) -> float:
    """Tính Intersection over Union giữa 2 box [ymin, xmin, ymax, xmax]"""
    if not boxA or not boxB or len(boxA) != 4 or len(boxB) != 4:
        return 0.0
    yA = max(boxA[0], boxB[0])
    xA = max(boxA[1], boxB[1])
    yB = min(boxA[2], boxB[2])
    xB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return max(0.0, min(1.0, iou))

def run_comparison():
    print("===============================================================================")
    print("           BẢNG ĐỐI SOÁT HIỆU NĂNG: OPENCV vs GEMINI AI vs YOLO               ")
    print("===============================================================================\n")

    # Tải cache Gemini
    g2_cache = {}
    p_cache = root / "output" / "shopify_import" / "g2_g5_front_boxes.json"
    if p_cache.exists():
        g2_cache = json.load(open(p_cache, encoding="utf-8"))

    # Khởi tạo YOLO detector
    print("--> Đang khởi tạo YOLOPackagingDetector...")
    t0 = time.time()
    yolo_det = YOLOPackagingDetector()
    init_time = (time.time() - t0) * 1000
    print(f"    Khởi tạo xong trong {init_time:.1f}ms\n")

    test_samples = [
        ("STT 1 Dorkbua Stick", "source-import/G1_original/IMG_0002.jpeg"),
        ("STT 704 Hảo Hảo Gà", "source-import/G2_original/IMG_0680.jpeg"),
        ("STT 747 Hảo Hảo Tôm chua cay", "source-import/G2_original/IMG_0725.jpeg"),
        ("STT 668 A-Kuan Noodle", "source-import/G2_original/IMG_0642.jpeg"),
        ("Sample G1 #3", "source-import/G1_original/IMG_0004.jpeg")
    ]

    for label, rel_path in test_samples:
        img_p = root / rel_path
        if not img_p.exists():
            print(f"[-] Bỏ qua {label}: Không tìm thấy file {img_p}")
            continue

        with Image.open(img_p) as im:
            w, h = im.size
        fname = img_p.name

        print(f"-------------------------------------------------------------------------------")
        print(f"📦 MẪU: {label} ({fname}) | Kích thước ảnh: {w}x{h}")
        print(f"-------------------------------------------------------------------------------")

        # 1. OpenCV Heuristic
        t_cv_start = time.time()
        cv_box, cv_rot, cv_lbl = detect_front_box_cv(img_p)
        t_cv = (time.time() - t_cv_start) * 1000

        # 2. Cached Gemini
        gem_item = g2_cache.get(fname, {})
        gem_box = gem_item.get("front_box_2d")

        # 3. YOLO Inference
        t_yolo_start = time.time()
        yolo_res = yolo_det.detect(img_p)
        t_yolo = (time.time() - t_yolo_start) * 1000

        y_box = yolo_res.front_box_2d

        # In kết quả
        print(f"  [1] OpenCV CV-Detector : {cv_box} | Thời gian: {t_cv:.1f}ms | Mode: {cv_lbl}")
        print(f"  [2] Gemini Vision AI   : {gem_box} | Thời gian: ~1200-2500ms (API Cloud)")
        print(f"  [3] YOLO Detector      : {y_box} | Thời gian: {t_yolo:.1f}ms | Conf: {yolo_res.confidence_front:.2f} ({yolo_res.mode})")

        if gem_box and y_box:
            iou_yolo_gemini = calculate_iou(y_box, gem_box)
            print(f"  --> Độ tương đồng IoU (YOLO vs Gemini): {iou_yolo_gemini*100:.1f}%")
        if cv_box and y_box:
            iou_yolo_cv = calculate_iou(y_box, cv_box)
            print(f"  --> Độ tương đồng IoU (YOLO vs OpenCV): {iou_yolo_cv*100:.1f}%\n")

if __name__ == "__main__":
    run_comparison()
