"""
src/product_mapper/vision/multipass_barcode.py
-----------------------------------------------
Bộ giải mã Barcode Đa Tầng (Multi-pass Barcode Decoder) kết hợp:
1. Native ZXing-C++ quét toàn khung hình
2. YOLO Barcode ROI Crop từ ảnh gốc độ phân giải cao
3. Căn chỉnh góc nghiêng (Multi-angle Deskew: ±15°, 90°, 180°, 270°)
4. Tối ưu tương phản thích ứng (CLAHE, Otsu Binarization, Invert polarity)
5. Xác thực chuẩn kiểm tra Modulo-10 của GS1 (EAN-13, EAN-8, UPC-A), bảo toàn chuỗi số 0 đầu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageOps

from .barcode_validator import validate_ean_upc_checksum, get_barcode_lookup_variants

RETAIL_FORMATS = (
    zxingcpp.BarcodeFormat.EANUPC
    | zxingcpp.BarcodeFormat.EAN13
    | zxingcpp.BarcodeFormat.EAN8
    | zxingcpp.BarcodeFormat.UPCA
    | zxingcpp.BarcodeFormat.UPCE
    | zxingcpp.BarcodeFormat.Code128
)

@dataclass
class DecodedBarcode:
    text: str
    format: str
    is_valid_checksum: bool
    pass_name: str
    box: list[int] | None = None  # [ymin, xmin, ymax, xmax] 0-1000
    angle: float = 0.0


class MultiPassBarcodeDecoder:
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

    def decode(self, img_input: str | Path | Image.Image) -> DecodedBarcode | None:
        """
        Thực hiện tuần tự 4 pass giải mã barcode với độ tin cậy tối đa.
        """
        # 1. Chuẩn hóa đầu vào PIL & OpenCV
        if isinstance(img_input, (str, Path)):
            p = Path(img_input)
            if not p.exists():
                return None
            pil_img = ImageOps.exif_transpose(Image.open(p))
        else:
            pil_img = ImageOps.exif_transpose(img_input)

        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        orig_w, orig_h = pil_img.size

        # -------------------------------------------------------------
        # PASS 1: Native Full-Frame Scan bằng ZXing-C++
        # -------------------------------------------------------------
        hit = self._scan_zxing(pil_img, pass_name="pass1_full_frame")
        if hit and hit.is_valid_checksum:
            return hit

        # -------------------------------------------------------------
        # PASS 2: YOLO Barcode ROI Crop (Crop từ ảnh gốc độ nét cao)
        # -------------------------------------------------------------
        roi_pil, roi_box_1000 = self._extract_yolo_barcode_roi(pil_img)
        if roi_pil is not None:
            hit = self._scan_zxing(roi_pil, pass_name="pass2_yolo_roi")
            if hit and hit.is_valid_checksum:
                hit.box = roi_box_1000
                return hit

        # -------------------------------------------------------------
        # PASS 3: Multi-angle Rotation & Deskew trên vùng ROI
        # -------------------------------------------------------------
        target_pil = roi_pil if roi_pil is not None else pil_img
        for angle in [-15, 15, -10, 10, -5, 5, 90, 180, 270]:
            rotated = target_pil.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
            hit = self._scan_zxing(rotated, pass_name=f"pass3_rotate_{angle}deg")
            if hit and hit.is_valid_checksum:
                hit.angle = float(angle)
                hit.box = roi_box_1000
                return hit

        # -------------------------------------------------------------
        # PASS 4: Contrast & Binarization (CLAHE, Otsu, Invert)
        # -------------------------------------------------------------
        cv_target = cv2.cvtColor(np.array(target_pil), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_target, cv2.COLOR_BGR2GRAY)

        # 4a. CLAHE (Cân bằng sáng thích ứng cục bộ)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        clahe_img = clahe.apply(gray)
        hit = self._scan_zxing(Image.fromarray(clahe_img), pass_name="pass4_clahe")
        if hit and hit.is_valid_checksum:
            hit.box = roi_box_1000
            return hit

        # 4b. Otsu Thresholding (Tách ngưỡng tự động nhị phân)
        _, otsu = cv2.threshold(clahe_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        hit = self._scan_zxing(Image.fromarray(otsu), pass_name="pass4_otsu")
        if hit and hit.is_valid_checksum:
            hit.box = roi_box_1000
            return hit

        # 4c. Invert polarity (Đảo màu âm bản cho bao bì in trắng trên nền đen)
        inverted = cv2.bitwise_not(otsu)
        hit = self._scan_zxing(Image.fromarray(inverted), pass_name="pass4_invert")
        if hit and hit.is_valid_checksum:
            hit.box = roi_box_1000
            return hit

        # 4d. Morphological gradient để làm rõ thanh vạch mờ
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        opened = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel)
        hit = self._scan_zxing(Image.fromarray(opened), pass_name="pass4_morph")
        if hit and hit.is_valid_checksum:
            hit.box = roi_box_1000
            return hit

        # Nếu có hit từ Pass 1 nhưng checksum không vượt qua, trả về nhưng cờ False để đưa vào Review
        if hit:
            return hit

        return None

    def _scan_zxing(self, img: Image.Image, pass_name: str) -> DecodedBarcode | None:
        """Thực thi thư viện ZXing-C++ trên ảnh PIL và chuẩn hóa kết quả."""
        try:
            results = zxingcpp.read_barcodes(img, formats=RETAIL_FORMATS)
            for res in results:
                raw_text = res.text.strip()
                digits = re.sub(r"[^\d]", "", raw_text)
                if not digits:
                    continue
                # Bảo toàn chuỗi số (String) để không mất số 0 đầu
                is_valid = validate_ean_upc_checksum(digits)
                return DecodedBarcode(
                    text=digits,
                    format=str(res.format).replace("BarcodeFormat.", ""),
                    is_valid_checksum=is_valid,
                    pass_name=pass_name
                )
        except Exception:
            pass
        return None

    def _extract_yolo_barcode_roi(self, pil_img: Image.Image) -> tuple[Image.Image | None, list[int] | None]:
        """Trích xuất vùng Bounding Box Barcode bằng YOLO với lề an toàn 15%."""
        detector = self._get_yolo_detector()
        if detector is None:
            return None, None

        res = detector.detect(pil_img)
        box = res.barcode_box_2d or res.back_box_2d
        if not box:
            return None, None

        orig_w, orig_h = pil_img.size
        ymin, xmin, ymax, xmax = box

        # Tọa độ pixel thực tế
        px_ymin = int(ymin * orig_h / 1000.0)
        px_xmin = int(xmin * orig_w / 1000.0)
        px_ymax = int(ymax * orig_h / 1000.0)
        px_xmax = int(xmax * orig_w / 1000.0)

        bw = px_xmax - px_xmin
        bh = px_ymax - px_ymin
        if bw <= 10 or bh <= 10:
            return None, None

        # Thêm 15% padding an toàn xung quanh barcode quiet zone
        pad_x = int(bw * 0.15)
        pad_y = int(bh * 0.15)

        c_xmin = max(0, px_xmin - pad_x)
        c_ymin = max(0, px_ymin - pad_y)
        c_xmax = min(orig_w, px_xmax + pad_x)
        c_ymax = min(orig_h, px_ymax + pad_y)

        cropped = pil_img.crop((c_xmin, c_ymin, c_xmax, c_ymax))
        return cropped, box
