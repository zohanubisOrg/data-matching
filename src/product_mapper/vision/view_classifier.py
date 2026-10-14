"""
src/product_mapper/vision/view_classifier.py
---------------------------------------------
Module phân loại góc nhìn & bề mặt bao bì (View Classifier).
Gán nhãn đa tín hiệu:
  FRONT   : Mặt trước (Logo thương hiệu, tên chính diện, minh họa món ăn, ít chữ nhỏ)
  BACK    : Mặt sau (Bảng dinh dưỡng, thành phần, barcode, khối chữ đen trắng dày đặc)
  SIDE    : Mặt hông (Góc nhìn hẹp của hộp/chai, thông tin phụ)
  DETAIL  : Chi tiết cận cảnh (Hạn sử dụng, nắp chai, mã lô, tem phụ phóng to)
  UNKNOWN : Trường hợp mờ hoặc không xác định rõ
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from .multipass_barcode import MultiPassBarcodeDecoder


class PackagingView(str, Enum):
    FRONT = "FRONT"
    BACK = "BACK"
    SIDE = "SIDE"
    DETAIL = "DETAIL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ViewClassificationResult:
    view: PackagingView
    confidence: float
    evidence: list[str]
    has_barcode: bool
    barcode_text: str | None
    is_dual_panel: bool
    details: dict[str, Any]


class ViewClassifier:
    def __init__(
        self,
        barcode_decoder: MultiPassBarcodeDecoder | None = None,
        yolo_detector: Any | None = None
    ):
        self.barcode_decoder = barcode_decoder or MultiPassBarcodeDecoder()
        self.yolo_detector = yolo_detector

    def _get_yolo_detector(self):
        if self.yolo_detector is None:
            try:
                from .yolo_detector import YOLOPackagingDetector
                self.yolo_detector = YOLOPackagingDetector()
            except Exception:
                self.yolo_detector = None
        return self.yolo_detector

    def classify(self, img_input: str | Path | Image.Image) -> ViewClassificationResult:
        """
        Phân loại bề mặt/góc nhìn ảnh dựa trên kết hợp đa tín hiệu.
        """
        if isinstance(img_input, (str, Path)):
            pil_img = ImageOps.exif_transpose(Image.open(img_input))
        else:
            pil_img = ImageOps.exif_transpose(img_input)

        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        w, h = pil_img.size
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        evidence: list[str] = []

        # 1. Tín hiệu Barcode
        bc_hit = self.barcode_decoder.decode(pil_img)
        has_barcode = bool(bc_hit and bc_hit.is_valid_checksum)
        bc_text = bc_hit.text if has_barcode else (bc_hit.text if bc_hit else None)
        if has_barcode:
            evidence.append(f"barcode_detected ({bc_text})")

        # 2. Tín hiệu YOLO Bounding Boxes
        det = self._get_yolo_detector()
        yolo_res = None
        is_dual_panel = False
        if det:
            yolo_res = det.detect(pil_img)
            if yolo_res.front_box_2d and yolo_res.back_box_2d:
                is_dual_panel = True
                evidence.append("yolo_dual_panel_detected")

        # 3. Phân tích hình thái & Mật độ cạnh văn bản (Edge density)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.mean(edges > 0))  # Mật độ viền
        sat_mean = float(np.mean(hsv[:, :, 1]))    # Độ bão hòa màu

        # 4. Kiểm tra tỷ lệ khung hình & khía cạnh vật thể (Aspect Ratio)
        aspect = w / max(1, h)
        if aspect < 0.35 or aspect > 2.8:
            # Góc nhìn cực kỳ hẹp hoặc cực kỳ dẹt -> thường là SIDE hoặc DETAIL
            evidence.append(f"extreme_aspect_ratio ({aspect:.2f})")
            return ViewClassificationResult(
                view=PackagingView.SIDE,
                confidence=0.82,
                evidence=evidence,
                has_barcode=has_barcode,
                barcode_text=bc_text,
                is_dual_panel=is_dual_panel,
                details={"edge_density": edge_density, "sat_mean": sat_mean, "aspect": aspect}
            )

        # 5. Phân loại theo trọng số đa tín hiệu
        # Tín hiệu MẶT SAU: Có barcode + mật độ chữ cao + màu sắc ít bão hòa
        back_score = 0.0
        front_score = 0.0

        if has_barcode:
            back_score += 45.0

        if edge_density > 0.09:
            back_score += 35.0
            evidence.append(f"dense_text_texture ({edge_density:.3f})")
        elif edge_density < 0.06:
            front_score += 30.0
            evidence.append(f"clean_open_artwork ({edge_density:.3f})")

        if sat_mean > 85.0:
            front_score += 35.0
            evidence.append(f"vibrant_colors ({sat_mean:.1f})")
        elif sat_mean < 45.0:
            back_score += 20.0
            evidence.append(f"monochrome_nutrition_label ({sat_mean:.1f})")

        # Đánh giá kết quả
        if is_dual_panel:
            # Ảnh chứa cả 2 mặt -> coi là DUAL (có thể trích xuất cả front lẫn back)
            view = PackagingView.FRONT  # Ưu tiên front vì chứa cả 2
            conf = 0.90
            evidence.append("dual_front_back_in_single_photo")
        elif back_score >= 60.0 and back_score > front_score + 15.0:
            view = PackagingView.BACK
            conf = min(0.98, back_score / 100.0)
        elif front_score >= 50.0 and front_score > back_score + 10.0:
            view = PackagingView.FRONT
            conf = min(0.95, front_score / 100.0)
        elif has_barcode:
            # Dù màu sắc sặc sỡ nhưng có barcode rõ ràng -> Thường là BACK của gói bánh kẹo
            view = PackagingView.BACK
            conf = 0.85
            evidence.append("barcode_overrides_vibrant_colors")
        else:
            view = PackagingView.FRONT if front_score >= back_score else PackagingView.UNKNOWN
            conf = 0.65

        return ViewClassificationResult(
            view=view,
            confidence=round(conf, 2),
            evidence=evidence,
            has_barcode=has_barcode,
            barcode_text=bc_text,
            is_dual_panel=is_dual_panel,
            details={"edge_density": edge_density, "sat_mean": sat_mean, "back_score": back_score, "front_score": front_score}
        )
