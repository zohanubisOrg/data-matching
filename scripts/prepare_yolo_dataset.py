#!/usr/bin/env python3
"""
scripts/prepare_yolo_dataset.py
--------------------------------
Tự động chuyển đổi cache nhãn và ảnh kho thành tập dữ liệu chuẩn huấn luyện YOLO.
Classes:
  0: product_front (Mặt trước bao bì)
  1: product_back  (Mặt sau bao bì)
  2: barcode       (Vùng mã vạch)
"""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path
from PIL import Image

def box_1000_to_yolo(box: list[int]) -> tuple[float, float, float, float] | None:
    """
    Chuyển đổi [ymin, xmin, ymax, xmax] (0-1000) sang (xc, yc, w, h) chuẩn YOLO (0.0-1.0).
    """
    if not box or len(box) != 4:
        return None
    ymin, xmin, ymax, xmax = [max(0.0, min(1.0, float(c) / 1000.0)) for c in box]
    w = xmax - xmin
    h = ymax - ymin
    if w <= 0.01 or h <= 0.01:
        return None
    xc = xmin + w / 2.0
    yc = ymin + h / 2.0
    return (round(xc, 6), round(yc, 6), round(w, 6), round(h, 6))

def derive_back_box(front_box: list[int], position: str) -> list[int] | None:
    """
    Trong ảnh chụp 2 mặt đặt cạnh nhau, ước lượng tọa độ mặt sau đối xứng.
    """
    if not front_box or len(front_box) != 4:
        return None
    ymin, xmin, ymax, xmax = front_box
    pos = (position or "").lower()

    if pos == "left" or (pos == "" and xmax <= 520):
        # Front is on the left -> Back is on the right
        return [ymin, min(990, xmax + 10), ymax, 990]
    elif pos == "right" or (pos == "" and xmin >= 480):
        # Front is on the right -> Back is on the left
        return [ymin, 10, ymax, max(10, xmin - 10)]
    elif pos == "top" or (pos == "" and ymax <= 520):
        # Front is on top -> Back is on bottom
        return [min(990, ymax + 10), xmin, 990, xmax]
    elif pos == "bottom" or (pos == "" and ymin >= 480):
        # Front is on bottom -> Back is on top
        return [10, xmin, max(10, ymin - 10), xmax]
    return None

def build_dataset():
    root = Path(__file__).resolve().parent.parent
    data_out = root / "data" / "yolo_packaging"
    
    # 1. Tìm tất cả ảnh gốc trong kho
    print("--> Quét toàn bộ ảnh gốc trong source-import...")
    source_imgs: dict[str, Path] = {}
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
        for p in (root / "source-import").rglob(ext):
            source_imgs[p.name] = p
    print(f"    Tìm thấy {len(source_imgs)} ảnh gốc.")

    # 2. Tải các nguồn nhãn cache
    labels_map: dict[str, list[tuple[int, tuple[float, float, float, float]]]] = {}

    # Nguồn 1: g2_g5_front_boxes.json
    p_g2_g5 = root / "output" / "shopify_import" / "g2_g5_front_boxes.json"
    if p_g2_g5.exists():
        d = json.load(open(p_g2_g5, encoding="utf-8"))
        for fname, item in d.items():
            if fname not in source_imgs:
                continue
            f_box = item.get("front_box_2d")
            pos = item.get("front_position", "")
            if f_box:
                yolo_f = box_1000_to_yolo(f_box)
                if yolo_f:
                    labels_map.setdefault(fname, []).append((0, yolo_f))
                    # Nếu có vị trí đối xứng rõ rệt, sinh pseudo-label cho back
                    b_box = derive_back_box(f_box, pos)
                    if b_box:
                        yolo_b = box_1000_to_yolo(b_box)
                        if yolo_b:
                            labels_map.setdefault(fname, []).append((1, yolo_b))

    # Nguồn 2: g1_delivery/front_layout_boxes.json
    p_g1 = root / "output" / "g1_delivery" / "front_layout_boxes.json"
    if p_g1.exists():
        d = json.load(open(p_g1, encoding="utf-8"))
        for fname, item in d.items():
            if fname not in source_imgs:
                continue
            f_box = item.get("front_box_2d")
            pos = item.get("front_side_position", "")
            if f_box and fname not in labels_map:
                yolo_f = box_1000_to_yolo(f_box)
                if yolo_f:
                    labels_map.setdefault(fname, []).append((0, yolo_f))
                    b_box = derive_back_box(f_box, pos)
                    if b_box:
                        yolo_b = box_1000_to_yolo(b_box)
                        if yolo_b:
                            labels_map.setdefault(fname, []).append((1, yolo_b))

    # Nguồn 3: g1_vision_cache.json (có barcode_box_2d)
    p_g1_vis = root / "output" / "g1_delivery" / "g1_vision_cache.json"
    if p_g1_vis.exists():
        d = json.load(open(p_g1_vis, encoding="utf-8"))
        for fname, item in d.items():
            if fname not in source_imgs:
                continue
            bc_box = item.get("barcode_box_2d")
            if bc_box:
                yolo_bc = box_1000_to_yolo(bc_box)
                if yolo_bc:
                    # Kiểm tra xem đã có barcode cho file này chưa
                    existing_classes = [c for c, _ in labels_map.get(fname, [])]
                    if 2 not in existing_classes:
                        labels_map.setdefault(fname, []).append((2, yolo_bc))

    # Nguồn 4: g4 / g5 vision caches (có cả front, back, barcode đầy đủ)
    for cache_p in [root / "output" / "shopify_import" / "g4_vision_cache.json", root / "output" / "shopify_import" / "g5_vision_cache.json"]:
        if cache_p.exists():
            d = json.load(open(cache_p, encoding="utf-8"))
            for fname, item in d.items():
                if fname not in source_imgs:
                    continue
                f_box = item.get("front_box_2d")
                b_box = item.get("back_box_2d")
                bc_box = item.get("barcode_box_2d")
                annos = []
                if f_box:
                    yf = box_1000_to_yolo(f_box)
                    if yf: annos.append((0, yf))
                if b_box:
                    yb = box_1000_to_yolo(b_box)
                    if yb: annos.append((1, yb))
                if bc_box:
                    ybc = box_1000_to_yolo(bc_box)
                    if ybc: annos.append((2, ybc))
                if annos:
                    labels_map[fname] = annos

    print(f"--> Đã trích xuất nhãn cho {len(labels_map)} ảnh.")

    # 3. Tạo thư mục train/val
    train_img_dir = data_out / "images" / "train"
    val_img_dir = data_out / "images" / "val"
    train_lbl_dir = data_out / "labels" / "train"
    val_lbl_dir = data_out / "labels" / "val"

    for d in [train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 4. Phân chia Train / Val (85% Train, 15% Val)
    all_keys = list(labels_map.keys())
    random.seed(42)
    random.shuffle(all_keys)

    split_idx = int(len(all_keys) * 0.85)
    train_keys = all_keys[:split_idx]
    val_keys = all_keys[split_idx:]

    print(f"--> Chia tập dữ liệu: {len(train_keys)} train, {len(val_keys)} val.")

    def copy_subset(keys: list[str], img_dir: Path, lbl_dir: Path):
        for fname in keys:
            src_img = source_imgs[fname]
            dst_img = img_dir / src_img.name
            
            # Copy image (symlink hoặc copy file nếu khác ổ)
            try:
                if not dst_img.exists():
                    shutil.copy2(src_img, dst_img)
            except Exception as e:
                print(f"Lỗi sao chép {fname}: {e}")
                continue

            # Ghi file nhãn .txt
            txt_name = src_img.stem + ".txt"
            dst_txt = lbl_dir / txt_name
            with open(dst_txt, "w", encoding="utf-8") as f:
                for cls_id, (xc, yc, w, h) in labels_map[fname]:
                    f.write(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

    print("--> Đang chuẩn bị tập train...")
    copy_subset(train_keys, train_img_dir, train_lbl_dir)
    print("--> Đang chuẩn bị tập val...")
    copy_subset(val_keys, val_img_dir, val_lbl_dir)

    # 5. Ghi file cấu hình packaging.yaml
    yaml_content = f"""# Cấu hình Dataset YOLO Bao Bì Thực Phẩm Siêu Thị
path: {data_out.as_posix()}
train: images/train
val: images/val

names:
  0: product_front
  1: product_back
  2: barcode
"""
    yaml_file = data_out / "packaging.yaml"
    with open(yaml_file, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print(f"--> Hoàn tất! File cấu hình đã lưu tại: {yaml_file}")
    return yaml_file

if __name__ == "__main__":
    build_dataset()
