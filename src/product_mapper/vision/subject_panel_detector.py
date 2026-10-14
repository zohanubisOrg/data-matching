"""
src/product_mapper/vision/subject_panel_detector.py
---------------------------------------------------
Module nhận diện Bounding Boxes & Phân loại Đa Chủ Thể (Multi-Subject & Multi-Panel Detector).
Giải quyết dứt điểm các ca phức tạp:
1. Xác định số lượng chủ thể trong 1 ảnh (1, 2, hoặc 3 chủ thể / panels).
2. Phát hiện bounding box riêng biệt của từng chủ thể / panel mà không cắt lẹm bao bì.
3. Gán nhãn chính xác từng box:
   - FRONT : Mặt trước chính diện (Logo thương hiệu, tên, bao bì đẹp, định dạng đứng Portrait)
   - BACK  : Mặt sau (Bảng thành phần, dinh dưỡng Nutrition Facts, barcode chính)
   - SIDE  : Mặt cạnh/mặt hông (Thường hẹp, thông tin phụ, hướng dẫn sử dụng)
   - DETAIL: Tem phụ, cận cảnh
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from .multipass_barcode import DecodedBarcode, MultiPassBarcodeDecoder


class SubjectRole(str, Enum):
    FRONT = "FRONT"
    BACK = "BACK"
    SIDE = "SIDE"
    DETAIL = "DETAIL"
    UNKNOWN = "UNKNOWN"


@dataclass
class SubjectBox:
    box_1000: list[int]  # [ymin, xmin, ymax, xmax] theo thang 0-1000
    pixel_box: tuple[int, int, int, int]  # (xmin, ymin, xmax, ymax) pixel thực tế
    role: SubjectRole
    confidence: float
    has_barcode: bool = False
    barcode_text: str | None = None
    aspect_ratio: float = 1.0  # height / width
    relative_width: float = 1.0  # width / image_width
    edge_density: float = 0.0
    color_saturation: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class MultiSubjectDetectionResult:
    subject_count: int  # 1, 2, 3...
    mode: str  # "single_subject", "dual_panel", "three_panel", "cluster"
    upright_ccw: int
    subjects: list[SubjectBox]
    front_subject: SubjectBox | None = None
    back_subject: SubjectBox | None = None
    side_subjects: list[SubjectBox] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class SubjectPanelDetector:
    def __init__(
        self,
        yolo_detector: Any | None = None,
        barcode_decoder: MultiPassBarcodeDecoder | None = None,
    ):
        self.yolo_detector = yolo_detector
        self.barcode_decoder = barcode_decoder or MultiPassBarcodeDecoder()

    def _get_yolo_detector(self):
        if self.yolo_detector is None:
            try:
                from .yolo_detector import YOLOPackagingDetector
                self.yolo_detector = YOLOPackagingDetector()
            except Exception:
                self.yolo_detector = None
        return self.yolo_detector

    def detect_and_classify_subjects(
        self,
        img_input: str | Path | Image.Image,
        known_barcode: str | None = None,
    ) -> MultiSubjectDetectionResult:
        """
        Nhận diện toàn diện các chủ thể / panels trong ảnh, đếm số lượng và gán nhãn FRONT, BACK, SIDE.
        """
        if isinstance(img_input, (str, Path)):
            raw_pil = Image.open(img_input)
            raw_pil = ImageOps.exif_transpose(raw_pil)
        else:
            raw_pil = ImageOps.exif_transpose(img_input)

        if raw_pil.mode != "RGB":
            raw_pil = raw_pil.convert("RGB")

        # 1. Quét Barcode để xác định góc xoay Upright và tọa độ Barcode
        bc_hit: DecodedBarcode | None = None
        try:
            bc_hit = self.barcode_decoder.decode(raw_pil)
        except Exception:
            pass

        upright_ccw = 0
        bc_center_x = 0.0
        bc_center_y = 0.0
        has_bc = False
        bc_text = None

        if bc_hit and bc_hit.is_valid_checksum:
            has_bc = True
            bc_text = bc_hit.text
            upright_ccw = int(round(bc_hit.angle / 90.0) * 90) % 360

        # Xoay ảnh về phương thẳng đứng (Upright)
        if upright_ccw != 0:
            upright_pil = raw_pil.rotate(upright_ccw, expand=True, resample=Image.Resampling.BICUBIC)
        else:
            upright_pil = raw_pil

        up_w, up_h = upright_pil.size

        # Tính tọa độ tâm Barcode trên ảnh Upright
        if bc_hit and bc_hit.box:
            # box_2d thang 0-1000 trên ảnh gốc
            ymin, xmin, ymax, xmax = bc_hit.box
            orig_w, orig_h = raw_pil.size
            cx_orig = (xmin + xmax) / 2.0 * orig_w / 1000.0
            cy_orig = (ymin + ymax) / 2.0 * orig_h / 1000.0
            bc_center_x, bc_center_y = self._transform_point(cx_orig, cy_orig, orig_w, orig_h, upright_ccw)
        else:
            bc_center_x, bc_center_y = up_w * 0.5, up_h * 0.5

        # 2. Phân tích ranh giới Panels bằng Canny Edge Valley & Gap Analysis
        preview, scale = self._prepare_preview(upright_pil, max_size=900)
        arr = np.asarray(preview)
        prev_h, prev_w = arr.shape[:2]

        col_gaps = self._find_valleys(arr, axis="x")
        row_gaps = self._find_valleys(arr, axis="y")

        candidate_pixel_boxes: list[tuple[int, int, int, int]] = []
        mode = "single_subject"

        # Kiểm tra chế độ 3 panels (thường là xếp ngang: 2 rãnh dọc)
        if len(col_gaps) >= 2 and all(0.20 <= g <= 0.80 for g in col_gaps[:2]):
            mode = "three_panel"
            g1, g2 = sorted(col_gaps[:2])
            cut1 = int(round(g1 * up_w))
            cut2 = int(round(g2 * up_w))
            candidate_pixel_boxes = [
                (0, 0, cut1, up_h),
                (cut1, 0, cut2, up_h),
                (cut2, 0, up_w, up_h),
            ]
        elif len(row_gaps) >= 2 and all(0.20 <= g <= 0.80 for g in row_gaps[:2]):
            mode = "three_panel"
            g1, g2 = sorted(row_gaps[:2])
            cut1 = int(round(g1 * up_h))
            cut2 = int(round(g2 * up_h))
            candidate_pixel_boxes = [
                (0, 0, up_w, cut1),
                (0, cut1, up_w, cut2),
                (0, cut2, up_w, up_h),
            ]
        elif len(col_gaps) == 1 and 0.28 <= col_gaps[0] <= 0.72:
            mode = "dual_panel"
            cut = int(round(col_gaps[0] * up_w))
            candidate_pixel_boxes = [
                (0, 0, cut, up_h),
                (cut, 0, up_w, up_h),
            ]
        elif len(row_gaps) == 1 and 0.28 <= row_gaps[0] <= 0.72:
            mode = "dual_panel"
            cut = int(round(row_gaps[0] * up_h))
            candidate_pixel_boxes = [
                (0, 0, up_w, cut),
                (0, cut, up_w, up_h),
            ]
        else:
            # Fallback kiểm tra YOLO detections
            yolo_det = self._get_yolo_detector()
            yolo_boxes = []
            if yolo_det:
                try:
                    y_res = yolo_det.detect(upright_pil)
                    if y_res.front_box_2d:
                        yolo_boxes.append(y_res.front_box_2d)
                    if y_res.back_box_2d:
                        yolo_boxes.append(y_res.back_box_2d)
                except Exception:
                    pass

            if len(yolo_boxes) >= 2:
                mode = "dual_panel"
                for b1000 in yolo_boxes:
                    candidate_pixel_boxes.append(self._box_1000_to_pixel(b1000, up_w, up_h))
            else:
                mode = "single_subject"
                candidate_pixel_boxes = [(0, 0, up_w, up_h)]

        # 3. Phân loại từng Subject Box
        subjects: list[SubjectBox] = []

        for p_box in candidate_pixel_boxes:
            xmin, ymin, xmax, ymax = p_box
            bw = max(1, xmax - xmin)
            bh = max(1, ymax - ymin)

            box_1000 = [
                int(ymin * 1000 / up_h),
                int(xmin * 1000 / up_w),
                int(ymax * 1000 / up_h),
                int(xmax * 1000 / up_w),
            ]

            # Kiểm tra xem Barcode có nằm trong Box này không
            box_holds_bc = False
            if has_bc and (xmin <= bc_center_x <= xmax) and (ymin <= bc_center_y <= ymax):
                box_holds_bc = True

            # Crop ROI để đo đạc tín hiệu hình ảnh
            crop = upright_pil.crop(p_box)
            c_w, c_h = crop.size
            aspect = c_h / max(1, c_w)
            rel_w = c_w / float(up_w)

            # Đo mật độ cạnh & độ bão hòa màu sắc
            crop_cv = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(crop_cv, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(crop_cv, cv2.COLOR_BGR2HSV)

            edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
            edge_dens = float(np.mean(edges > 0))
            sat_mean = float(np.mean(hsv[:, :, 1]))

            # Gán nhãn sơ bộ
            role = SubjectRole.UNKNOWN
            conf = 0.70
            reasons = []

            # QUY TẮC PHÂN LOẠI MẶT CẠNH (SIDE):
            # Mặt cạnh thường hẹp hơn hẳn mặt chính (rel_w < 0.28 trong 3 panels, hoặc aspect > 2.8)
            is_narrow_panel = (mode == "three_panel" and rel_w < 0.28) or (aspect > 2.8 and rel_w < 0.35)

            if is_narrow_panel and not box_holds_bc:
                role = SubjectRole.SIDE
                conf = 0.88
                reasons.append(f"narrow_spine_panel (rel_w={rel_w:.2f}, aspect={aspect:.2f})")
            elif box_holds_bc:
                # Chứa Barcode -> Ứng viên số 1 cho MẶT SAU (BACK)
                role = SubjectRole.BACK
                conf = 0.95
                reasons.append("contains_active_barcode")
                if edge_dens > 0.08:
                    reasons.append(f"dense_nutrition_text ({edge_dens:.3f})")
            elif edge_dens > 0.09 and sat_mean < 55.0:
                # Text dày đặc, màu đơn sắc -> MẶT SAU (BACK)
                role = SubjectRole.BACK
                conf = 0.85
                reasons.append(f"dense_text_monochrome (dens={edge_dens:.3f}, sat={sat_mean:.1f})")
            else:
                # Ngược lại: Màu sắc sinh động, ít khối chữ đặc -> MẶT TRƯỚC (FRONT)
                role = SubjectRole.FRONT
                conf = 0.85
                reasons.append(f"artwork_and_brand_presentation (sat={sat_mean:.1f}, dens={edge_dens:.3f})")

            subjects.append(
                SubjectBox(
                    box_1000=box_1000,
                    pixel_box=p_box,
                    role=role,
                    confidence=conf,
                    has_barcode=box_holds_bc,
                    barcode_text=bc_text if box_holds_bc else None,
                    aspect_ratio=round(aspect, 2),
                    relative_width=round(rel_w, 2),
                    edge_density=round(edge_dens, 3),
                    color_saturation=round(sat_mean, 1),
                    reasons=reasons,
                )
            )

        # 4. Tinh chỉnh gán nhãn cho trường hợp 3 Panels (Tam hợp: FRONT, SIDE, BACK)
        if mode == "three_panel" and len(subjects) == 3:
            back_cand = next((s for s in subjects if s.has_barcode), None)
            if back_cand:
                back_cand.role = SubjectRole.BACK
                remaining = [s for s in subjects if s != back_cand]
                side_cand = min(remaining, key=lambda s: s.relative_width)
                front_cand = max(remaining, key=lambda s: s.relative_width)

                side_cand.role = SubjectRole.SIDE
                side_cand.reasons.append("narrowest_among_3_panels")
                front_cand.role = SubjectRole.FRONT
                front_cand.reasons.append("primary_display_panel_among_3")
            else:
                sorted_by_width = sorted(subjects, key=lambda s: s.relative_width)
                sorted_by_width[0].role = SubjectRole.SIDE
                p_a, p_b = sorted_by_width[1], sorted_by_width[2]
                if p_a.edge_density > p_b.edge_density:
                    p_a.role = SubjectRole.BACK
                    p_b.role = SubjectRole.FRONT
                else:
                    p_b.role = SubjectRole.BACK
                    p_a.role = SubjectRole.FRONT

        # 5. Xác định Front, Back và Sides
        front_sub = next((s for s in subjects if s.role == SubjectRole.FRONT), None)
        back_sub = next((s for s in subjects if s.role == SubjectRole.BACK), None)
        side_subs = [s for s in subjects if s.role == SubjectRole.SIDE]

        return MultiSubjectDetectionResult(
            subject_count=len(subjects),
            mode=mode,
            upright_ccw=upright_ccw,
            subjects=subjects,
            front_subject=front_sub,
            back_subject=back_sub,
            side_subjects=side_subs,
            details={
                "image_size": (up_w, up_h),
                "col_gaps": col_gaps,
                "row_gaps": row_gaps,
                "has_barcode": has_bc,
                "barcode_text": bc_text,
            },
        )

    def extract_clean_crops(
        self,
        image: Image.Image,
        detection_result: MultiSubjectDetectionResult,
        padding_ratio: float = 0.04,
    ) -> tuple[Image.Image | None, Image.Image | None]:
        """
        Trích xuất Mặt Trước (Front Portrait) và Mặt Sau (Back rõ nét) hoàn hảo,
        bảo toàn trọn vẹn bao bì (không cắt cụt nắp/đáy/mép chai lọ).
        """
        image = ImageOps.exif_transpose(image)
        if detection_result.upright_ccw != 0:
            upright_img = image.rotate(detection_result.upright_ccw, expand=True, resample=Image.Resampling.BICUBIC)
        else:
            upright_img = image

        up_w, up_h = upright_img.size

        front_crop = None
        back_crop = None

        if detection_result.front_subject:
            f_box = detection_result.front_subject.pixel_box
            padded_f = self._apply_safe_padding(f_box, up_w, up_h, padding_ratio)
            front_crop = upright_img.crop(padded_f)

        if detection_result.back_subject:
            b_box = detection_result.back_subject.pixel_box
            padded_b = self._apply_safe_padding(b_box, up_w, up_h, padding_ratio)
            back_crop = upright_img.crop(padded_b)
            back_crop = self._enhance_back_text(back_crop)

        return front_crop, back_crop

    def _apply_safe_padding(
        self,
        box: tuple[int, int, int, int],
        img_w: int,
        img_h: int,
        ratio: float,
    ) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        bw = x1 - x0
        bh = y1 - y0
        pad_x = int(bw * ratio)
        pad_y = int(bh * ratio)
        return (
            max(0, x0 - pad_x),
            max(0, y0 - pad_y),
            min(img_w, x1 + pad_x),
            min(img_h, y1 + pad_y),
        )

    def _enhance_back_text(self, img: Image.Image, max_side: int = 2400) -> Image.Image:
        w, h = img.size
        if max(w, h) > max_side:
            scale = max_side / float(max(w, h))
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        img = ImageEnhance.Sharpness(img).enhance(1.22)
        img = ImageEnhance.Contrast(img).enhance(1.06)
        return img

    def _prepare_preview(self, image: Image.Image, max_size: int = 900) -> tuple[Image.Image, float]:
        w, h = image.size
        longest = max(w, h)
        if longest <= max_size:
            return image, 1.0
        scale = max_size / float(longest)
        return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR), scale

    def _find_valleys(self, arr: np.ndarray, axis: str, min_depth: float = 0.35) -> list[float]:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
        profile = edges.mean(axis=0 if axis == "x" else 1)
        kernel = np.ones(15) / 15.0
        smooth = np.convolve(profile, kernel, mode="same")

        length = len(smooth)
        span = max(8, int(length * 0.08))
        valleys = []

        for idx in range(int(length * 0.18), int(length * 0.82)):
            if smooth[idx] > smooth[idx - 1] or smooth[idx] > smooth[idx + 1]:
                continue
            left = float(smooth[max(0, idx - span) : idx].mean())
            right = float(smooth[idx + 1 : min(length, idx + span)].mean())
            shoulders = (left + right) / 2.0
            if shoulders <= 1:
                continue
            depth = 1.0 - (float(smooth[idx]) / shoulders)
            if depth >= min_depth:
                valleys.append((idx / float(length), depth))

        valleys.sort(key=lambda x: x[1], reverse=True)
        kept: list[float] = []
        for frac, _ in valleys:
            if all(abs(frac - prev) >= 0.16 for prev in kept):
                kept.append(frac)
            if len(kept) >= 2:
                break
        kept.sort()
        return kept

    def _transform_point(self, x: float, y: float, w: int, h: int, ccw: int) -> tuple[float, float]:
        if ccw == 0:
            return x, y
        if ccw == 90:
            return y, w - 1 - x
        if ccw == 180:
            return w - 1 - x, h - 1 - y
        if ccw == 270:
            return h - 1 - y, x
        return x, y

    def _box_1000_to_pixel(self, box: list[int], w: int, h: int) -> tuple[int, int, int, int]:
        ymin, xmin, ymax, xmax = box
        return (
            int(xmin * w / 1000.0),
            int(ymin * h / 1000.0),
            int(xmax * w / 1000.0),
            int(ymax * h / 1000.0),
        )
