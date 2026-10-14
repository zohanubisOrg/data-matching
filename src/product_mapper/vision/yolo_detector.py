"""
src/product_mapper/vision/yolo_detector.py
-------------------------------------------
Module nhận diện bao bì sản phẩm bằng mô hình YOLO (YOLOv8 / YOLO11).
Tự động tách Mặt Trước, Mặt Sau và Vùng Barcode với độ chính xác cao (Pixel-perfect),
chuẩn hóa tọa độ [ymin, xmin, ymax, xmax] thang 0-1000 tương thích với hệ thống hiện tại.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from PIL import Image, ImageOps
import numpy as np
from pydantic import BaseModel, Field

class YOLOPackagingResult(BaseModel):
    front_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] (0-1000) của mặt trước")
    back_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] (0-1000) của mặt sau")
    barcode_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] (0-1000) của barcode")
    confidence_front: float = 0.0
    confidence_back: float = 0.0
    confidence_barcode: float = 0.0
    front_rotation: int = 0
    mode: str = "yolo_detector"


class YOLOPackagingDetector:
    def __init__(self, model_path: str | Path | None = None):
        """
        Khởi tạo detector. Tự động tìm trọng số tốt nhất đã train hoặc dùng pre-trained.
        """
        self.root = Path(__file__).resolve().parent.parent.parent.parent
        self.model = None
        self.is_custom_trained = False

        # Danh sách đường dẫn trọng số theo thứ tự ưu tiên
        candidate_weights = [
            model_path,
            self.root / "output" / "yolo_training" / "packaging_detector" / "weights" / "best.pt",
            self.root / "weights" / "packaging_yolo_best.pt",
            "yolo11n.pt",
            "yolov8n.pt"
        ]

        try:
            from ultralytics import YOLO
            for w in candidate_weights:
                if w and (isinstance(w, str) and (Path(w).exists() or not w.endswith(".pt") or w.startswith("yolo")) or (isinstance(w, Path) and w.exists())):
                    try:
                        self.model = YOLO(str(w))
                        if "best.pt" in str(w) or "packaging" in str(w):
                            self.is_custom_trained = True
                        print(f"[YOLO Detector] Đã tải model: {w} (Custom: {self.is_custom_trained})")
                        break
                    except Exception as load_err:
                        continue
        except ImportError:
            print("[YOLO Detector] Chưa cài đặt ultralytics. Sẽ dùng fallback CV heuristic.")

    def detect(self, img_input: str | Path | Image.Image) -> YOLOPackagingResult:
        """
        Nhận diện bao bì từ đường dẫn hoặc đối tượng PIL Image.
        """
        # Load PIL image safely
        if isinstance(img_input, (str, Path)):
            img_path = Path(img_input)
            if not img_path.exists():
                return YOLOPackagingResult(mode="error_file_not_found")
            pil_img = Image.open(img_path)
            pil_img = ImageOps.exif_transpose(pil_img)
        else:
            pil_img = ImageOps.exif_transpose(img_input)

        img_w, img_h = pil_img.size

        # Nếu model YOLO đã sẵn sàng
        if self.model is not None:
            try:
                results = self.model(pil_img, verbose=False, conf=0.25)
                if results and len(results) > 0:
                    r = results[0]
                    boxes = r.boxes
                    
                    front_box = None
                    back_box = None
                    bc_box = None
                    conf_f = 0.0
                    conf_b = 0.0
                    conf_bc = 0.0

                    if self.is_custom_trained and hasattr(r, "names"):
                        # Model tùy chỉnh với 3 class: 0: front, 1: back, 2: barcode
                        for box in boxes:
                            cls_id = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            xyxy = box.xyxy[0].tolist() # [xmin, ymin, xmax, ymax]
                            box_1000 = [
                                int(xyxy[1] * 1000 / img_h),
                                int(xyxy[0] * 1000 / img_w),
                                int(xyxy[3] * 1000 / img_h),
                                int(xyxy[2] * 1000 / img_w)
                            ]

                            if cls_id == 0 and conf > conf_f:
                                front_box = box_1000
                                conf_f = conf
                            elif cls_id == 1 and conf > conf_b:
                                back_box = box_1000
                                conf_b = conf
                            elif cls_id == 2 and conf > conf_bc:
                                bc_box = box_1000
                                conf_bc = conf
                    else:
                        # Model pre-trained COCO (class 'bottle', 'cup', 'bowl', 'box', 'packaged goods')
                        # Lấy bounding box bao quát lớn nhất làm vật thể chính
                        max_area = 0
                        for box in boxes:
                            xyxy = box.xyxy[0].tolist()
                            conf = float(box.conf[0].item())
                            bw = xyxy[2] - xyxy[0]
                            bh = xyxy[3] - xyxy[1]
                            area = bw * bh
                            if area > max_area and conf > 0.3:
                                max_area = area
                                conf_f = conf
                                front_box = [
                                    int(xyxy[1] * 1000 / img_h),
                                    int(xyxy[0] * 1000 / img_w),
                                    int(xyxy[3] * 1000 / img_h),
                                    int(xyxy[2] * 1000 / img_w)
                                ]

                    if front_box is not None:
                        return YOLOPackagingResult(
                            front_box_2d=front_box,
                            back_box_2d=back_box,
                            barcode_box_2d=bc_box,
                            confidence_front=conf_f,
                            confidence_back=conf_b,
                            confidence_barcode=conf_bc,
                            mode="yolo_inference"
                        )
            except Exception as e:
                print(f"[YOLO Detector] Lỗi suy luận YOLO: {e}")

        # Fallback về CV heuristic
        return self._fallback_cv(pil_img)

    def _fallback_cv(self, pil_img: Image.Image) -> YOLOPackagingResult:
        """
        Dự phòng bằng OpenCV Heuristic nếu YOLO chưa khả dụng
        """
        try:
            from scripts.cv_front_detector import detect_front_box_cv
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                tmp_path = Path(tf.name)
            pil_img.save(tmp_path, "JPEG")
            box, rot, label = detect_front_box_cv(tmp_path)
            tmp_path.unlink(missing_ok=True)
            return YOLOPackagingResult(
                front_box_2d=box,
                front_rotation=rot,
                confidence_front=0.7,
                mode=f"fallback_cv ({label})"
            )
        except Exception:
            return YOLOPackagingResult(
                front_box_2d=[0, 0, 1000, 1000],
                confidence_front=0.5,
                mode="fallback_full_frame"
            )

    def crop_front_portrait(self, img_input: str | Path | Image.Image, padding: float = 0.03) -> Image.Image:
        """
        Cắt ảnh mặt trước chất lượng cao, định dạng đứng Portrait Studio chuẩn đưa lên Shopify CDN.
        """
        if isinstance(img_input, (str, Path)):
            pil_img = ImageOps.exif_transpose(Image.open(img_input))
        else:
            pil_img = ImageOps.exif_transpose(img_input)

        res = self.detect(pil_img)
        box = res.front_box_2d or [0, 0, 1000, 1000]
        
        orig_w, orig_h = pil_img.size
        ymin, xmin, ymax, xmax = box

        # Tọa độ pixel thực tế
        px_ymin = int(ymin * orig_h / 1000.0)
        px_xmin = int(xmin * orig_w / 1000.0)
        px_ymax = int(ymax * orig_h / 1000.0)
        px_xmax = int(xmax * orig_w / 1000.0)

        # Thêm padding an toàn
        bw = px_xmax - px_xmin
        bh = px_ymax - px_ymin
        pad_x = int(bw * padding)
        pad_y = int(bh * padding)

        crop_xmin = max(0, px_xmin - pad_x)
        crop_ymin = max(0, px_ymin - pad_y)
        crop_xmax = min(orig_w, px_xmax + pad_x)
        crop_ymax = min(orig_h, px_ymax + pad_y)

        cropped = pil_img.crop((crop_xmin, crop_ymin, crop_xmax, crop_ymax))

        # Đảm bảo định dạng Portrait (Height >= Width) nếu cần
        cw, ch = cropped.size
        if cw > ch * 1.25 and res.front_rotation != 0:
            cropped = cropped.rotate(-res.front_rotation, expand=True)

        return cropped
