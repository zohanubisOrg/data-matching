"""Hero object isolation module to eliminate companion jars and secondary clutter objects."""
from __future__ import annotations

from typing import List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image


class HeroCropper:
    """Detects multi-object compositions and crops the single primary hero object."""

    def __init__(self, min_area_ratio: float = 0.04):
        # Components with area < 4% of image area are treated as minor noise/shadows
        self.min_area_ratio = min_area_ratio

    @staticmethod
    def _get_foreground_mask(cv_bgr: np.ndarray) -> np.ndarray:
        """Simple, fast foreground mask using Otsu threshold on saturation + inverted brightness."""
        hsv = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        # Products differ from white/gray studio background in either higher saturation or darker value
        inv_val = cv2.bitwise_not(val)
        cue = cv2.addWeighted(sat, 0.6, inv_val, 0.4, 0)
        _, mask = cv2.threshold(cue, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Morphological close to bridge internal details
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def find_object_boxes(self, img: Image.Image) -> List[Tuple[int, int, int, int]]:
        """Finds bounding boxes (x, y, w, h) of significant foreground objects."""
        w_orig, h_orig = img.size
        # Work on a 512px downscaled proxy for sub-millisecond detection
        scale = 512.0 / max(w_orig, h_orig)
        small_w, small_h = int(w_orig * scale), int(h_orig * scale)
        small_pil = img.resize((small_w, small_h), Image.Resampling.BILINEAR)

        cv_img = cv2.cvtColor(np.array(small_pil), cv2.COLOR_RGB2BGR)
        mask = self._get_foreground_mask(cv_img)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img_area = small_w * small_h
        boxes: List[Tuple[int, int, int, int]] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= img_area * self.min_area_ratio:
                x, y, w, h = cv2.boundingRect(cnt)
                # Rescale back to original image coordinates
                orig_x = max(0, int(x / scale))
                orig_y = max(0, int(y / scale))
                orig_w = min(w_orig - orig_x, int(w / scale))
                orig_h = min(h_orig - orig_y, int(h / scale))
                boxes.append((orig_x, orig_y, orig_w, orig_h))

        return boxes

    def isolate_hero(
        self, img: Image.Image, target_aspect_ratio: Optional[float] = None
    ) -> Tuple[Image.Image, bool]:
        """Isolates the primary hero object if multiple objects (companion jars/bottles) are present.
        
        Returns:
            (cropped_img, was_isolated): The isolated image and whether a crop occurred.
        """
        boxes = self.find_object_boxes(img)
        # If 0 or 1 significant object, return image as is
        if len(boxes) <= 1:
            return img, False

        w_orig, h_orig = img.size
        center_x = w_orig / 2.0
        center_y = h_orig / 2.0

        best_box = None
        best_score = -1e9

        for x, y, w, h in boxes:
            box_area = w * h
            box_cx = x + w / 2.0
            box_cy = y + h / 2.0
            box_aspect = float(w) / max(1, float(h))

            # Metric 1: Centrality penalty (hero products are centered in shot)
            dist_norm = np.hypot(box_cx - center_x, box_cy - center_y) / max(w_orig, h_orig)
            centrality_score = 1.0 - dist_norm

            # Metric 2: Area score (larger object preferred)
            area_score = box_area / float(w_orig * h_orig)

            # Metric 3: Aspect ratio compatibility with demo thumbnail if provided
            if target_aspect_ratio is not None and target_aspect_ratio > 0:
                aspect_diff = abs(box_aspect - target_aspect_ratio) / target_aspect_ratio
                aspect_score = max(0.0, 1.0 - aspect_diff)
            else:
                aspect_score = 1.0

            # Composite score favoring centered, primary, aspect-aligned object
            total_score = (area_score * 0.45) + (centrality_score * 0.40) + (aspect_score * 0.15)
            if total_score > best_score:
                best_score = total_score
                best_box = (x, y, w, h)

        if best_box is None:
            return img, False

        # Add 5% comfortable margin around hero object
        bx, by, bw, bh = best_box
        pad_x = int(bw * 0.05)
        pad_y = int(bh * 0.05)

        crop_x1 = max(0, bx - pad_x)
        crop_y1 = max(0, by - pad_y)
        crop_x2 = min(w_orig, bx + bw + pad_x)
        crop_y2 = min(h_orig, by + bh + pad_y)

        # Only crop if it removes a noticeable extraneous part (at least 15% width or height reduction)
        if (crop_x2 - crop_x1) < w_orig * 0.85 or (crop_y2 - crop_y1) < h_orig * 0.85:
            cropped = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            return cropped, True

        return img, False

    def isolate_front(
        self,
        raw_img: Image.Image,
        demo_img: Optional[Image.Image] = None,
        barcode_center: Optional[Tuple[float, float]] = None,
        strategy: str = "STANDARD",
    ) -> Tuple[Image.Image, bool]:
        """Isolates the front packshot hero from a multi-view raw studio photo.
        
        1. If strategy is SEQUENTIAL_PAIR, CARTON_BOX, or SINGLE_SURFACE, the image
           is already an intact standalone shot. Returns (raw_img, False).
        2. If demo_img (Column 23) is provided, uses multi-scale SIFT feature matching
           to isolate the exact bounding box of the front packshot (e.g. Deconstructed Cartons).
        3. If SIFT does not isolate, executes the 5-Archetype Layout Classifier:
           - Archetype A: TRIPLE_VERTICAL_PANEL (Shan Masala, White Rabbit, PAN 3 boxes)
           - Archetype B: HORIZONTAL_STACK (Kikkoman 1L, FaThai 3 bottles, horizontal pouches)
           - Archetype C: STACKED_TUBS_GRID (Mae Pranom 2x3 tubs)
           - Archetype D: DUAL_TRAY_WRAPPED & Standard Dual-Hero (Wonton dual trays, standard 2-item)
        4. Returns (cropped_img, was_isolated).
        """
        # Sequential pairs, carton boxes, and single-surface produce are standalone shots
        if strategy in ("SEQUENTIAL_PAIR", "CARTON_BOX", "SINGLE_SURFACE"):
            return raw_img, False

        w, h = raw_img.size

        # 1. Try SIFT Feature Anchoring with Demo Image (Archetype E: Deconstructed Carton or strong demo match)
        if demo_img is not None:
            try:
                # Pre-downscale proxy using PIL to prevent Windows ArrayMemoryError on 4K/5K images
                scale = 1200.0 / float(w)
                target_h = max(1, int(h * scale))
                raw_small_pil = raw_img.resize((1200, target_h), Image.Resampling.BILINEAR)
                raw_small = cv2.cvtColor(np.array(raw_small_pil), cv2.COLOR_RGB2BGR)
                raw_gray = cv2.cvtColor(raw_small, cv2.COLOR_BGR2GRAY)
                del raw_small_pil, raw_small

                demo_small_pil = demo_img.copy()
                demo_small_pil.thumbnail((800, 800), Image.Resampling.BILINEAR)
                demo_cv = cv2.cvtColor(np.array(demo_small_pil), cv2.COLOR_RGB2BGR)
                demo_gray = cv2.cvtColor(demo_cv, cv2.COLOR_BGR2GRAY)
                del demo_small_pil, demo_cv

                sift = cv2.SIFT_create()
                kp1, des1 = sift.detectAndCompute(demo_gray, None)
                kp2, des2 = sift.detectAndCompute(raw_gray, None)

                if des1 is not None and des2 is not None and len(kp1) >= 5 and len(kp2) >= 5:
                    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
                    matches = bf.match(des1, des2)
                    if len(matches) >= 10:
                        matches = sorted(matches, key=lambda m: m.distance)
                        pts = [kp2[m.trainIdx].pt for m in matches[:100]]
                        xs = [p[0] / scale for p in pts]
                        ys = [p[1] / scale for p in pts]

                        x_min = max(0, int(np.percentile(xs, 1)))
                        x_max = min(w, int(np.percentile(xs, 99)))
                        y_min = max(0, int(np.percentile(ys, 1)))
                        y_max = min(h, int(np.percentile(ys, 99)))

                        bw = x_max - x_min
                        bh = y_max - y_min
                        pad_x = int(bw * 0.05)
                        pad_y = int(bh * 0.05)

                        fx1 = max(0, x_min - pad_x)
                        fy1 = max(0, y_min - pad_y)
                        fx2 = min(w, x_max + pad_x)
                        fy2 = min(h, y_max + pad_y)

                        if (fx2 - fx1) < w * 0.88 or (fy2 - fy1) < h * 0.88:
                            return raw_img.crop((fx1, fy1, fx2, fy2)), True
            except Exception:
                pass

        # 2. Multi-Archetype Layout Classifier
        bc_x, bc_y = barcode_center if barcode_center is not None else (0.5, 0.5)

        # Build 512px downscaled mask to analyze foreground layout
        proxy_scale = 512.0 / max(w, h)
        pw, ph = max(1, int(w * proxy_scale)), max(1, int(h * proxy_scale))
        small_pil = raw_img.resize((pw, ph), Image.Resampling.BILINEAR)
        small_cv = cv2.cvtColor(np.array(small_pil), cv2.COLOR_RGB2BGR)
        mask = self._get_foreground_mask(small_cv)

        if w > h:  # Landscape studio composition
            # Archetype A: TRIPLE_VERTICAL_PANEL (Shan Masala, White Rabbit, PAN 3 boxes)
            # Barcode is located in the left or right third, and there is central product mass
            if (bc_x < 0.33 or bc_x > 0.67) and (0.12 <= bc_y <= 0.88):
                cx1 = int(w * 0.34)
                cx2 = int(w * 0.66)
                # Analyze vertical product extent in central column to discard top shipping carton
                center_mask = mask[:, int(pw * 0.34):int(pw * 0.66)]
                ys = np.where(center_mask > 0)[0]
                if len(ys) > 0:
                    cy1 = max(0, int((ys.min() / proxy_scale) - h * 0.02))
                    cy2 = min(h, int((ys.max() / proxy_scale) + h * 0.02))
                else:
                    cy1 = max(0, int(h * 0.22))
                    cy2 = min(h, int(h * 0.95))
                return raw_img.crop((cx1, cy1, cx2, cy2)), True

            # Archetype C: STACKED_TUBS_GRID (Mae Pranom 2x3 tubs)
            # Barcodes sit on top row lids (bc_y < 0.38)
            if bc_y < 0.38 and (0.15 <= bc_x <= 0.85):
                # Isolate single centered tub from bottom row
                return raw_img.crop((int(w * 0.32), int(h * 0.46), int(w * 0.68), min(h, int(h * 0.96)))), True

            # Archetype B: HORIZONTAL_STACK (Kikkoman 1L bottles, FaThai 3 bottles, horizontal pouches)
            # Bottles lie horizontally, stacked vertically along Y-axis
            if bc_y > 0.60:
                # Top bottle is the front packshot
                return raw_img.crop((int(w * 0.04), int(h * 0.08), int(w * 0.96), int(h * 0.52))), True

            # Check if components are predominantly horizontal (aspect > 1.6)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            horiz_cnt = sum(1 for c in contours if (cv2.boundingRect(c)[2] / max(1, cv2.boundingRect(c)[3])) > 1.6)
            if horiz_cnt >= 1:
                # 3 horizontal bottles (FaThai) or 2 horizontal bottles
                return raw_img.crop((int(w * 0.04), int(h * 0.04), int(w * 0.96), int(h * 0.42))), True

            # Archetype D: DUAL_TRAY_WRAPPED & Standard Dual-Hero (Horizontal Split)
            if bc_x > 0.50:
                return raw_img.crop((0, 0, int(w * 0.52), h)), True
            else:
                return raw_img.crop((int(w * 0.48), 0, w, h)), True

        else:  # Portrait composition
            if bc_y > 0.50:
                return raw_img.crop((0, 0, w, int(h * 0.52))), True
            else:
                return raw_img.crop((0, int(h * 0.48), w, h)), True

        # 3. Fallback to general hero isolation
        return self.isolate_hero(raw_img)

    def isolate_back(
        self,
        raw_img: Image.Image,
        barcode_center: Optional[Tuple[float, float]] = None,
        strategy: str = "STANDARD",
    ) -> Tuple[Image.Image, bool]:
        """Isolates the back packshot hero from a multi-view raw photo for 'Ảnh mặt sau'."""
        if strategy in ("SEQUENTIAL_PAIR", "CARTON_BOX", "SINGLE_SURFACE"):
            return raw_img, False

        w, h = raw_img.size
        bc_x, bc_y = barcode_center if barcode_center is not None else (0.5, 0.5)

        if w > h:
            # Triple Vertical: Back is the side panel holding the barcode
            if (bc_x < 0.33 or bc_x > 0.67) and (0.12 <= bc_y <= 0.88):
                if bc_x < 0.33:
                    return raw_img.crop((0, int(h * 0.22), int(w * 0.36), min(h, int(h * 0.95)))), True
                else:
                    return raw_img.crop((int(w * 0.64), int(h * 0.22), w, min(h, int(h * 0.95)))), True

            # Stacked Tubs: Back is the top row lid containing the barcode
            if bc_y < 0.38 and (0.15 <= bc_x <= 0.85):
                return raw_img.crop((int(w * 0.20), 0, int(w * 0.55), int(h * 0.50))), True

            # Horizontal Stack: Back is the bottom bottle holding the barcode
            if bc_y > 0.60:
                return raw_img.crop((int(w * 0.04), int(h * 0.60), int(w * 0.96), h)), True

            # Standard Dual: Crop side containing barcode
            if bc_x > 0.50:
                return raw_img.crop((int(w * 0.48), 0, w, h)), True
            else:
                return raw_img.crop((0, 0, int(w * 0.52), h)), True

        else:
            if bc_y > 0.50:
                return raw_img.crop((0, int(h * 0.48), w, h)), True
            else:
                return raw_img.crop((0, 0, w, int(h * 0.52))), True

