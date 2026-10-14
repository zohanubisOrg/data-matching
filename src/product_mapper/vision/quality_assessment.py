"""
src/product_mapper/vision/quality_assessment.py
------------------------------------------------
Module Đánh giá Chất lượng Hình ảnh (Image Quality Assessment - IQA).
Đo lường chất lượng cục bộ TRÊN VÙNG SẢN PHẨM (ROI) thay vì toàn bộ nền kho.
Cung cấp 2 bộ tiêu chí đánh giá độc lập:
1. assess_front_quality: Tối ưu cho ảnh bán hàng (Độ nét, chính diện, không lẹm viền, không lóa).
2. assess_back_quality: Tối ưu cho trích xuất thông tin (Độ rõ của chữ, bảng nutrition, barcode).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass
class FrontQualityResult:
    total_score: float  # 0.0 - 100.0
    sharpness_score: float  # Tenengrad + Laplacian kết hợp
    glare_penalty: float  # Điểm trừ do bóng lóa
    framing_completeness: float  # Độ trọn vẹn bao bì (không cắt cụt mép)
    color_vibrance: float  # Độ sống động/bão hòa màu của mặt trước
    is_acceptable: bool  # Đạt chuẩn webshop (> 60.0)
    details: dict[str, Any]


@dataclass
class BackQualityResult:
    total_score: float  # 0.0 - 100.0
    text_readability_score: float  # Độ sắc nét các cạnh viền chữ nhỏ
    glare_penalty: float  # Trừ điểm nếu lóa trên vùng văn bản
    has_valid_barcode: bool  # Thưởng điểm nếu chứa barcode đọc được
    nutrition_visibility_score: float  # Khả năng nhìn rõ bảng dinh dưỡng/thành phần
    is_acceptable: bool  # Đạt chuẩn đọc thông tin (> 55.0)
    details: dict[str, Any]


class ImageQualityAssessor:
    def __init__(self, yolo_detector: Any | None = None):
        self.yolo_detector = yolo_detector

    def _get_yolo_detector(self):
        if self.yolo_detector is None:
            try:
                from .yolo_detector import YOLOPackagingDetector
                self.yolo_detector = YOLOPackagingDetector()
            except Exception:
                self.yolo_detector = None
        return self.yolo_detector

    def _extract_roi(self, pil_img: Image.Image, box_1000: list[int] | None) -> tuple[np.ndarray, np.ndarray]:
        """Trích xuất vùng BGR và Grayscale của sản phẩm từ tọa độ 0-1000."""
        w, h = pil_img.size
        if box_1000 and len(box_1000) == 4:
            ymin, xmin, ymax, xmax = box_1000
            py0 = max(0, int(ymin * h / 1000.0))
            px0 = max(0, int(xmin * w / 1000.0))
            py1 = min(h, int(ymax * h / 1000.0))
            px1 = min(w, int(xmax * w / 1000.0))
            if px1 > px0 + 20 and py1 > py0 + 20:
                crop = pil_img.crop((px0, py0, px1, py1))
                bgr = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                return bgr, gray

        # Toàn ảnh nếu không có box
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        return bgr, gray

    def compute_tenengrad(self, gray: np.ndarray) -> float:
        """Đo độ sắc nét cạnh dựa trên Tenengrad gradient (chống nhiễu tốt hơn Laplacian)."""
        if gray.size == 0:
            return 0.0
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        mag_sq = gx**2 + gy**2
        return float(np.mean(mag_sq))

    def compute_laplacian_var(self, gray: np.ndarray) -> float:
        """Đo phương sai Laplacian."""
        if gray.size == 0:
            return 0.0
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def compute_glare_ratio(self, bgr: np.ndarray) -> float:
        """Đo tỷ lệ pixel bị chói lóa ánh sáng (Value cao > 245, Saturation thấp < 35)."""
        if bgr.size == 0:
            return 0.0
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2]
        s = hsv[:, :, 1]
        glare_mask = (v >= 248) & (s <= 35)
        return float(np.sum(glare_mask) / glare_mask.size)

    def compute_framing_completeness(self, box_1000: list[int] | None) -> float:
        """
        Đánh giá độ trọn vẹn bao bì:
        Nếu box chạm sát mép (0 hoặc 1000) một cách bất thường -> Có thể bị lẹm góc/mất viền.
        """
        if not box_1000 or len(box_1000) != 4:
            return 75.0  # Mặc định trung bình nếu không có box
        ymin, xmin, ymax, xmax = box_1000
        score = 100.0

        # Kiểm tra lẹm 4 cạnh
        if ymin <= 5: score -= 15.0
        if xmin <= 5: score -= 15.0
        if ymax >= 995: score -= 15.0
        if xmax >= 995: score -= 15.0

        # Kiểm tra tỷ lệ kích thước hợp lý (không quá bé < 15% diện tích)
        bw = (xmax - xmin) / 1000.0
        bh = (ymax - ymin) / 1000.0
        area_ratio = bw * bh
        if area_ratio < 0.12:
            score -= 25.0

        return max(0.0, score)

    def assess_front(self, img_input: str | Path | Image.Image, box_1000: list[int] | None = None) -> FrontQualityResult:
        """
        Đánh giá chất lượng ẢNH MẶT TRƯỚC (Bán hàng):
        - Ưu tiên: Độ nét cao, màu sắc tươi tắn, không bị chói sáng, không bị mất cạnh.
        """
        if isinstance(img_input, (str, Path)):
            pil_img = ImageOps.exif_transpose(Image.open(img_input))
        else:
            pil_img = ImageOps.exif_transpose(img_input)

        if box_1000 is None:
            det = self._get_yolo_detector()
            if det:
                res = det.detect(pil_img)
                box_1000 = res.front_box_2d

        bgr, gray = self._extract_roi(pil_img, box_1000)

        # 1. Đo độ nét
        tenengrad = self.compute_tenengrad(gray)
        lap_var = self.compute_laplacian_var(gray)
        # Chuẩn hóa Tenengrad về thang 0-100 (thực nghiệm: > 500 là rất nét)
        sharpness_norm = min(100.0, (math.sqrt(max(0, tenengrad)) / 25.0) * 100.0)

        # 2. Đo bóng lóa (Glare)
        glare_ratio = self.compute_glare_ratio(bgr)
        # Tỷ lệ lóa > 8% bị trừ điểm mạnh
        glare_penalty = min(40.0, glare_ratio * 400.0)

        # 3. Đo trọn vẹn khung hình (Framing)
        framing_score = self.compute_framing_completeness(box_1000)

        # 4. Độ bão hòa màu sắc (Mặt trước bao bì thường rực rỡ)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        sat_score = min(100.0, (sat_mean / 120.0) * 100.0)

        # Tổng hợp điểm mặt trước
        # Trọng số: 40% Sharpness, 25% Framing, 20% Color, -Glare
        total = (sharpness_norm * 0.40) + (framing_score * 0.25) + (sat_score * 0.20) + 15.0 - glare_penalty
        total = max(0.0, min(100.0, round(total, 2)))

        return FrontQualityResult(
            total_score=total,
            sharpness_score=round(sharpness_norm, 2),
            glare_penalty=round(glare_penalty, 2),
            framing_completeness=round(framing_score, 2),
            color_vibrance=round(sat_score, 2),
            is_acceptable=total >= 58.0,
            details={
                "tenengrad": round(tenengrad, 1),
                "laplacian_var": round(lap_var, 1),
                "glare_ratio_pct": round(glare_ratio * 100, 2),
                "box_1000": box_1000
            }
        )

    def assess_back(
        self,
        img_input: str | Path | Image.Image,
        box_1000: list[int] | None = None,
        has_barcode: bool = False
    ) -> BackQualityResult:
        """
        Đánh giá chất lượng ẢNH MẶT SAU (Thông tin nhãn & Dinh dưỡng):
        - Ưu tiên: Độ rõ nét của các khối chữ nhỏ, mật độ chi tiết cao, có barcode hợp lệ, không chói lóa trên nhãn chữ.
        """
        if isinstance(img_input, (str, Path)):
            pil_img = ImageOps.exif_transpose(Image.open(img_input))
        else:
            pil_img = ImageOps.exif_transpose(img_input)

        if box_1000 is None:
            det = self._get_yolo_detector()
            if det:
                res = det.detect(pil_img)
                box_1000 = res.back_box_2d or res.barcode_box_2d

        bgr, gray = self._extract_roi(pil_img, box_1000)

        # 1. Độ rõ nét của chữ nhỏ (Edge density qua Canny)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.mean(edges > 0))  # Tỷ lệ pixel là cạnh chữ
        # Văn bản dinh dưỡng/thành phần dày đặc có edge_density khoảng 0.08 - 0.20
        readability_norm = min(100.0, (edge_density / 0.15) * 100.0)

        # 2. Tenengrad sharpness cho chữ
        tenengrad = self.compute_tenengrad(gray)
        sharpness_norm = min(100.0, (math.sqrt(max(0, tenengrad)) / 22.0) * 100.0)

        # 3. Lóa trên vùng chữ (Rất có hại cho OCR)
        glare_ratio = self.compute_glare_ratio(bgr)
        glare_penalty = min(50.0, glare_ratio * 500.0)

        # 4. Thưởng điểm nếu barcode đọc được
        barcode_bonus = 25.0 if has_barcode else 0.0

        # Tổng hợp điểm mặt sau
        # Trọng số: 35% Sharpness, 25% Readability/Edge density, 25% Barcode bonus, 15% Base - Glare
        total = (sharpness_norm * 0.35) + (readability_norm * 0.25) + barcode_bonus + 15.0 - glare_penalty
        total = max(0.0, min(100.0, round(total, 2)))

        return BackQualityResult(
            total_score=total,
            text_readability_score=round(readability_norm, 2),
            glare_penalty=round(glare_penalty, 2),
            has_valid_barcode=has_barcode,
            nutrition_visibility_score=round(sharpness_norm, 2),
            is_acceptable=total >= 50.0,
            details={
                "edge_density": round(edge_density, 4),
                "tenengrad": round(tenengrad, 1),
                "glare_ratio_pct": round(glare_ratio * 100, 2),
                "box_1000": box_1000
            }
        )
