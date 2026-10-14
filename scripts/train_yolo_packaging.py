#!/usr/bin/env python3
"""
scripts/train_yolo_packaging.py
--------------------------------
Huấn luyện mô hình YOLO (YOLOv8n / YOLO11n) nhận diện Mặt trước, Mặt sau và Mã vạch.
Tối ưu hóa tài nguyên cho GPU 4GB VRAM (GTX 1650) hoặc CPU.
"""

from __future__ import annotations

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path

import argparse

def train():
    try:
        from ultralytics import YOLO
        import torch
    except ImportError:
        print("Lỗi: Chưa cài đặt thư viện 'ultralytics' hoặc 'torch'. Vui lòng chạy: pip install ultralytics")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Huấn luyện YOLO Packaging")
    parser.add_argument("--epochs", type=int, default=15, help="Số epochs")
    parser.add_argument("--batch", type=int, default=8, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--device", type=str, default="", help="Device: '0' hoặc 'cpu'")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    data_yaml = root / "data" / "yolo_packaging" / "packaging.yaml"

    if not data_yaml.exists():
        print(f"Lỗi: Không tìm thấy file {data_yaml}. Hãy chạy scripts/prepare_yolo_dataset.py trước.")
        sys.exit(1)

    # Kiểm tra GPU CUDA hoặc CPU
    if args.device:
        device = args.device
    else:
        device = "0" if torch.cuda.is_available() else "cpu"

    print(f"=== BẮT ĐẦU HUẤN LUYỆN YOLO PACKAGING ===")
    print(f"Thiết bị: {'GPU ' + torch.cuda.get_device_name(0) if device == '0' and torch.cuda.is_available() else 'CPU'}")
    print(f"Cấu hình: {args.epochs} epochs, batch {args.batch}, imgsz {args.imgsz}")
    print(f"Dataset: {data_yaml}")

    model = YOLO("yolo11n.pt")
    project_dir = root / "output" / "yolo_training"
    project_dir.mkdir(parents=True, exist_ok=True)

    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        project=str(project_dir),
        name="packaging_detector",
        exist_ok=True,
        workers=2,
        optimizer="auto",
        verbose=True,
        plots=True
    )

    print("\n=== HUẤN LUYỆN HOÀN TẤT ===")
    best_weights = project_dir / "packaging_detector" / "weights" / "best.pt"
    print(f"Trọng số tốt nhất đã lưu tại: {best_weights}")

    # Xuất sang định dạng ONNX để phục vụ suy luận siêu tốc không cần PyTorch
    try:
        print("\n--> Đang xuất mô hình sang ONNX format...")
        onnx_model = YOLO(str(best_weights))
        onnx_model.export(format="onnx", imgsz=640)
        print("--> Xuất ONNX thành công!")
    except Exception as e:
        print(f"Lưu ý khi xuất ONNX: {e}")

if __name__ == "__main__":
    train()
