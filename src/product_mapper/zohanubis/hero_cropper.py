"""Hero object isolation module to eliminate companion jars and secondary clutter objects."""
from __future__ import annotations

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

from typing import List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image


class HeroCropper:
    """Detects multi-object compositions and crops the single primary hero object."""

    def __init__(self, min_area_ratio: float = 0.03):
        # Components with area < 3% of image area are treated as minor noise/shadows
        self.min_area_ratio = min_area_ratio
        self.last_crop_box: Optional[Tuple[int, int, int, int]] = None
        self.last_crop_uncertain: bool = False
        self.last_crop_confidence: float = 1.0
        self.last_crop_reason: str = ""

    @staticmethod
    def _get_foreground_mask(cv_bgr: np.ndarray) -> np.ndarray:
        """Fast, robust foreground mask using border background estimation and color distance."""
        h, w = cv_bgr.shape[:2]
        # Sample border pixels to detect studio backdrop color
        border_h = max(2, int(h * 0.03))
        border_w = max(2, int(w * 0.03))
        border_pixels = np.concatenate([
            cv_bgr[:border_h, :].reshape(-1, 3),
            cv_bgr[-border_h:, :].reshape(-1, 3),
            cv_bgr[:, :border_w].reshape(-1, 3),
            cv_bgr[:, -border_w:].reshape(-1, 3),
        ], axis=0)
        bg_median = np.median(border_pixels, axis=0)

        # Color difference from background with safe clipping to prevent uint8 modulo overflow
        diff = np.abs(cv_bgr.astype(np.int16) - bg_median.astype(np.int16)).sum(axis=-1)
        diff_clipped = np.clip(diff, 0, 255).astype(np.uint8)
        _, mask = cv2.threshold(diff_clipped, 35, 255, cv2.THRESH_BINARY)

        # Morphological close with small kernel (5x5) to bridge internal packaging details
        # without merging distinct adjacent objects
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def find_object_boxes(self, img: Image.Image) -> List[Tuple[int, int, int, int]]:
        """Finds bounding boxes (x, y, w, h) of significant foreground objects."""
        w_orig, h_orig = img.size
        scale = 640.0 / max(w_orig, h_orig)
        small_w, small_h = max(1, int(w_orig * scale)), max(1, int(h_orig * scale))
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
                orig_x = max(0, int(x / scale))
                orig_y = max(0, int(y / scale))
                orig_w = min(w_orig - orig_x, int(w / scale))
                orig_h = min(h_orig - orig_y, int(h / scale))
                boxes.append((orig_x, orig_y, orig_w, orig_h))

        return boxes

    @staticmethod
    def find_optimal_seam(
        cv_bgr: np.ndarray,
        axis: str = "vertical",
        search_range: Tuple[float, float] = (0.35, 0.65),
    ) -> float:
        """Finds the lowest-energy seam (whitespace valley) between adjacent objects.
        
        Returns the split coordinate as a normalized ratio (0.0 to 1.0).
        """
        gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 120)
        h, w = edges.shape

        if axis == "vertical":
            proj = edges.sum(axis=0)  # Profile across X
            total_len = w
        else:
            proj = edges.sum(axis=1)  # Profile across Y
            total_len = h

        start_idx = max(0, int(total_len * search_range[0]))
        end_idx = min(total_len, int(total_len * search_range[1]))

        if end_idx <= start_idx:
            return 0.50

        sub_proj = proj[start_idx:end_idx]
        min_idx = start_idx + int(np.argmin(sub_proj))
        return float(min_idx) / float(total_len)

    def find_demo_homography_crop(
        self,
        raw_img: Image.Image,
        demo_img: Image.Image,
        min_inliers: int = 12,
    ) -> Optional[Tuple[Tuple[int, int, int, int], int, float]]:
        """Isolates the exact physical bounding box of the front hero using SIFT + RANSAC Homography.
        
        Projects the 4 true physical corners of the Column W demo image into the raw photo scene.
        Returns:
            ((x1, y1, x2, y2), inliers_count, confidence_score) or None
        """
        try:
            w_raw, h_raw = raw_img.size
            scale = 1000.0 / max(w_raw, h_raw)
            pw, ph = max(1, int(w_raw * scale)), max(1, int(h_raw * scale))
            raw_proxy = raw_img.resize((pw, ph), Image.Resampling.BILINEAR)

            raw_cv = cv2.cvtColor(np.array(raw_proxy), cv2.COLOR_RGB2BGR)
            raw_gray = cv2.cvtColor(raw_cv, cv2.COLOR_BGR2GRAY)

            dw, dh = demo_img.size
            d_scale = 500.0 / max(dw, dh)
            demo_proxy = demo_img.resize((max(1, int(dw * d_scale)), max(1, int(dh * d_scale))), Image.Resampling.BILINEAR)
            demo_cv = cv2.cvtColor(np.array(demo_proxy), cv2.COLOR_RGB2BGR)
            demo_gray = cv2.cvtColor(demo_cv, cv2.COLOR_BGR2GRAY)

            sift = cv2.SIFT_create()
            kp1, des1 = sift.detectAndCompute(demo_gray, None)
            kp2, des2 = sift.detectAndCompute(raw_gray, None)
            if des1 is None or des2 is None or len(kp1) < 5 or len(kp2) < 5:
                return None

            bf = cv2.BFMatcher()
            matches = bf.knnMatch(des1, des2, k=2)
            good = [m for m, n in matches if m.distance < 0.75 * n.distance]
            if len(good) < min_inliers:
                return None

            src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if H is None:
                return None

            inliers = mask.ravel().tolist().count(1)
            if inliers < min_inliers:
                return None

            w_d, h_d = demo_proxy.size
            pts = np.float32([[0, 0], [0, h_d - 1], [w_d - 1, h_d - 1], [w_d - 1, 0]]).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, H)

            # Check convexity of projected quadrilateral
            if not cv2.isContourConvex(np.int32(dst)):
                return None

            # Project corners back to full original image coordinates
            dst_full = dst / scale
            xs = dst_full[:, 0, 0]
            ys = dst_full[:, 0, 1]

            x1, x2 = max(0, int(np.min(xs))), min(w_raw, int(np.max(xs)))
            y1, y2 = max(0, int(np.min(ys))), min(h_raw, int(np.max(ys)))
            bw, bh = x2 - x1, y2 - y1

            # Validate area bounds (object should occupy between 1.5% and 95% of full frame)
            area_ratio = (bw * bh) / float(w_raw * h_raw)
            if area_ratio < 0.015 or area_ratio > 0.95:
                return None

            # Verify aspect ratio compatibility with demo thumbnail (accounting for 90-deg orientation)
            demo_aspect = float(dw) / max(1.0, float(dh))
            box_aspect = float(bw) / max(1.0, float(bh))
            aspect_diff = min(
                abs(box_aspect - demo_aspect) / demo_aspect,
                abs(box_aspect - (1.0 / demo_aspect)) / (1.0 / demo_aspect),
            )
            if aspect_diff > 0.40:
                return None

            # Add comfortable 4% margin around product to ensure zero border truncation
            pad_x = int(bw * 0.04)
            pad_y = int(bh * 0.04)
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(w_raw, x2 + pad_x)
            cy2 = min(h_raw, y2 + pad_y)

            confidence = min(1.0, 0.50 + (inliers / 100.0) - (aspect_diff * 0.2))
            return (cx1, cy1, cx2, cy2), inliers, confidence
        except Exception:
            return None

    @staticmethod
    def check_aspect_ratio_anomaly(
        box_w: int, box_h: int, demo_w: int, demo_h: int, threshold_ratio: float = 1.6
    ) -> Tuple[bool, float]:
        """Checks if a bounding box is anomalously wide compared to Column W demo ground-truth.
        
        Returns:
            (is_anomaly, ratio_diff)
        """
        box_ar = float(box_w) / max(1.0, float(box_h))
        demo_ar = float(demo_w) / max(1.0, float(demo_h))
        canonical_demo_ar = demo_ar if (box_ar >= 1.0 and demo_ar >= 1.0) or (box_ar < 1.0 and demo_ar < 1.0) else (1.0 / demo_ar)
        ratio_multiplier = box_ar / max(1e-4, canonical_demo_ar)
        is_anomaly = ratio_multiplier >= threshold_ratio
        return is_anomaly, ratio_multiplier

    def cleave_touching_cluster(
        self,
        raw_img: Image.Image,
        cluster_box: Tuple[int, int, int, int],
        k_items: int = 2,
        strategy: str = "STANDARD",
    ) -> List[Tuple[int, int, int, int]]:
        """Cleaves a single touching bounding box into k candidate individual item boxes."""
        cx1, cy1, cx2, cy2 = cluster_box
        cw, ch = cx2 - cx1, cy2 - cy1
        if k_items < 2:
            return [cluster_box]

        crop_pil = raw_img.crop((cx1, cy1, cx2, cy2))
        cv_crop = cv2.cvtColor(np.array(crop_pil), cv2.COLOR_RGB2BGR)

        # 1. Box Archetype (Hộp): Sobel-X vertical seam peak detection
        strat_upper = strategy.upper()
        if "CARTON" in strat_upper or "BOX" in strat_upper:
            gray = cv2.cvtColor(cv_crop, cv2.COLOR_BGR2GRAY)
            sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3))
            vert_proj = sobel_x.sum(axis=0)

            split_xs = []
            for i in range(1, k_items):
                target_x = int(cw * (i / float(k_items)))
                w_range = max(2, int(cw * 0.12))
                r_start, r_end = max(1, target_x - w_range), min(cw - 1, target_x + w_range)
                if r_end > r_start:
                    split_x = r_start + int(np.argmax(vert_proj[r_start:r_end]))
                    split_xs.append(split_x)
                else:
                    split_xs.append(target_x)

        # 2. Bottle Archetype (Chai): Upper 35% shoulder V-groove concavity detection
        elif "BOTTLE" in strat_upper or "BOTTLES" in strat_upper or (cw / max(1.0, float(ch))) < 1.4:
            upper_h = max(5, int(ch * 0.35))
            upper_crop = cv_crop[:upper_h, :]
            gray_u = cv2.cvtColor(upper_crop, cv2.COLOR_BGR2GRAY)
            edges_u = cv2.Canny(gray_u, 30, 100)
            vert_proj = edges_u.sum(axis=0)

            split_xs = []
            for i in range(1, k_items):
                target_x = int(cw * (i / float(k_items)))
                w_range = max(2, int(cw * 0.15))
                r_start, r_end = max(1, target_x - w_range), min(cw - 1, target_x + w_range)
                if r_end > r_start:
                    split_x = r_start + int(np.argmin(vert_proj[r_start:r_end]))
                    split_xs.append(split_x)
                else:
                    split_xs.append(target_x)

        # 3. Can / Pouch / General Archetype: Seam carving / intensity valley
        else:
            gray = cv2.cvtColor(cv_crop, cv2.COLOR_BGR2GRAY)
            prof = gray.mean(axis=0)
            split_xs = []
            for i in range(1, k_items):
                target_x = int(cw * (i / float(k_items)))
                w_range = max(2, int(cw * 0.15))
                r_start, r_end = max(1, target_x - w_range), min(cw - 1, target_x + w_range)
                if r_end > r_start:
                    split_x = r_start + int(np.argmin(prof[r_start:r_end]))
                    split_xs.append(split_x)
                else:
                    split_xs.append(target_x)

        split_bounds = [0] + sorted(split_xs) + [cw]
        candidates = []
        for i in range(len(split_bounds) - 1):
            sub_x1 = cx1 + split_bounds[i]
            sub_x2 = cx1 + split_bounds[i + 1]
            sub_w = sub_x2 - sub_x1
            pad_x = int(sub_w * 0.04)
            candidates.append((max(0, sub_x1 - pad_x), cy1, min(raw_img.width, sub_x2 + pad_x), cy2))

        return candidates

    def select_best_candidate_against_demo(
        self,
        raw_img: Image.Image,
        candidate_boxes: List[Tuple[int, int, int, int]],
        demo_img: Image.Image,
    ) -> Tuple[Tuple[int, int, int, int], float, int]:
        """Evaluates candidate bounding boxes against Column W demo image.
        
        Returns:
            (best_box, best_score, best_inliers)
        """
        best_box = candidate_boxes[0]
        best_score = -1.0
        best_inliers = 0

        demo_128 = demo_img.resize((128, 128), Image.Resampling.BILINEAR).convert("RGB")
        demo_cv = cv2.cvtColor(np.array(demo_128), cv2.COLOR_RGB2BGR)
        hist_d = cv2.calcHist([demo_cv], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        cv2.normalize(hist_d, hist_d)

        sift = cv2.SIFT_create()
        kp_d, des_d = sift.detectAndCompute(cv2.cvtColor(demo_cv, cv2.COLOR_BGR2GRAY), None)

        for box in candidate_boxes:
            bx1, by1, bx2, by2 = box
            if bx2 <= bx1 or by2 <= by1:
                continue
            cand_crop = raw_img.crop((bx1, by1, bx2, by2))
            cand_128 = cand_crop.resize((128, 128), Image.Resampling.BILINEAR).convert("RGB")
            cand_cv = cv2.cvtColor(np.array(cand_128), cv2.COLOR_RGB2BGR)

            hist_c = cv2.calcHist([cand_cv], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist_c, hist_c)
            sim_hist = float(cv2.compareHist(hist_d, hist_c, cv2.HISTCMP_CORREL))

            inliers = 0
            if des_d is not None and len(kp_d) >= 5:
                cand_gray = cv2.cvtColor(cand_cv, cv2.COLOR_BGR2GRAY)
                kp_c, des_c = sift.detectAndCompute(cand_gray, None)
                if des_c is not None and len(kp_c) >= 5:
                    bf = cv2.BFMatcher()
                    matches = bf.knnMatch(des_d, des_c, k=2)
                    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
                    inliers = len(good)

            composite_score = max(0.0, sim_hist) * 0.60 + min(1.0, inliers / 20.0) * 0.40
            if composite_score > best_score:
                best_score = composite_score
                best_box = box
                best_inliers = inliers

        return best_box, best_score, best_inliers

    def isolate_front_coords(
        self,
        raw_img: Image.Image,
        demo_img: Optional[Image.Image] = None,
        barcode_center: Optional[Tuple[float, float]] = None,
        strategy: str = "STANDARD",
    ) -> Tuple[Tuple[int, int, int, int], bool, bool, float, str]:
        """Calculates exact crop coordinates on raw_img.
        
        Returns:
            (crop_box, was_isolated, is_uncertain, confidence, reason)
        """
        w, h = raw_img.size
        full_box = (0, 0, w, h)

        # 1. Standalone / single-surface shooting modes
        if strategy in ("SEQUENTIAL_PAIR", "CARTON_BOX", "SINGLE_SURFACE"):
            return full_box, False, False, 1.0, "STANDALONE_SHOT"

        # 2. SIFT Homography matching whenever demo image is available
        if demo_img is not None:
            homography_res = self.find_demo_homography_crop(raw_img, demo_img, min_inliers=12)
            if homography_res is not None:
                crop_box, inliers, conf = homography_res
                # Only apply crop if it genuinely isolates a sub-region (< 92% of either dimension)
                if (crop_box[2] - crop_box[0]) < w * 0.92 or (crop_box[3] - crop_box[1]) < h * 0.92:
                    return crop_box, True, False, conf, f"SIFT_HOMOGRAPHY_MATCH (inliers={inliers})"

        # 3. Object-aware boundary detection
        boxes = self.find_object_boxes(raw_img)
        bc_x, bc_y = barcode_center if barcode_center is not None else (0.5, 0.5)
        px, py = bc_x * w, bc_y * h

        # If only 0 or 1 significant object, evaluate touching cluster aspect ratio anomaly
        if len(boxes) <= 1:
            if demo_img is not None and boxes:
                bx, by, bw_b, bh_b = boxes[0]
                is_anomaly, ratio_mult = self.check_aspect_ratio_anomaly(bw_b, bh_b, demo_img.width, demo_img.height)
                if is_anomaly:
                    k_est = max(2, min(4, int(round(ratio_mult))))
                    cluster_box = (bx, by, bx + bw_b, by + bh_b)
                    cleaved = self.cleave_touching_cluster(raw_img, cluster_box, k_items=k_est, strategy=strategy)
                    best_box, score, inliers = self.select_best_candidate_against_demo(raw_img, cleaved, demo_img)
                    return best_box, True, False, score, f"TOUCHING_CLUSTER_CLEAVED_K{k_est} (inliers={inliers})"

            if demo_img is not None and strategy == "DECONSTRUCTED_CARTON":
                return full_box, False, True, 0.40, "UNCERTAIN_MULTI_VIEW_MISSING_DEMO_MATCH"
            return full_box, False, False, 0.90, "SINGLE_INTACT_HERO"

        # Downscale proxy for seam finding
        scale = 640.0 / max(w, h)
        small_pil = raw_img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
        cv_small = cv2.cvtColor(np.array(small_pil), cv2.COLOR_RGB2BGR)

        # Archetype C: STACKED_TUBS_GRID (Round tubs in grid)
        if strategy == "STACKED_TUBS_GRID":
            bottom_boxes = [b for b in boxes if (b[1] + b[3]) >= h * 0.60]
            if bottom_boxes:
                best_tub = min(bottom_boxes, key=lambda b: abs((b[0] + b[2] / 2.0) - w / 2.0))
                bx, by, bw_b, bh_b = best_tub
                pad_x = int(bw_b * 0.08)
                pad_y = int(bh_b * 0.08)
                crop_box = (max(0, bx - pad_x), max(0, by - pad_y), min(w, bx + bw_b + pad_x), min(h, by + bh_b + pad_y))
                return crop_box, True, False, 0.85, "STACKED_TUBS_OBJECT_CONTOUR"

        # Archetype B: HORIZONTAL_STACK (Bottles lying horizontally across Y)
        is_horizontal_objs = any(b[2] / max(1, b[3]) > 1.6 for b in boxes)
        if is_horizontal_objs and bc_y > 0.55:
            split_y = self.find_optimal_seam(cv_small, axis="horizontal", search_range=(0.40, 0.65))
            cy2 = min(h, int(h * (split_y + 0.03)))
            return (0, 0, w, cy2), True, False, 0.85, "HORIZONTAL_STACK_OPTIMAL_SEAM"

        # Archetype A: Multi-bottle / Multi-object with Demo Guidance (discarding hardcoded center_x)
        back_box = None
        for b in boxes:
            bx, by, bw_b, bh_b = b
            if bx <= px <= bx + bw_b and by <= py <= by + bh_b:
                back_box = b
                break

        front_candidates = [b for b in boxes if b != back_box]
        if front_candidates:
            if demo_img is not None:
                cand_boxes_coords = []
                for b in front_candidates:
                    pad_x = int(b[2] * 0.08)
                    pad_y = int(b[3] * 0.08)
                    cand_boxes_coords.append((max(0, b[0] - pad_x), max(0, b[1] - pad_y), min(w, b[0] + b[2] + pad_x), min(h, b[1] + b[3] + pad_y)))
                best_box, score, inliers = self.select_best_candidate_against_demo(raw_img, cand_boxes_coords, demo_img)
                return best_box, True, False, score, f"MULTI_OBJECT_DEMO_MATCHED (inliers={inliers})"
            else:
                best_box = max(front_candidates, key=lambda b: b[2] * b[3])
                fx, fy, fw_b, fh_b = best_box
                pad_x = int(fw_b * 0.10)
                pad_y = int(fh_b * 0.10)
                crop_box = (max(0, fx - pad_x), max(0, fy - pad_y), min(w, fx + fw_b + pad_x), min(h, fy + fh_b + pad_y))
                return crop_box, True, False, 0.85, "OBJECT_AWARE_DUAL_HERO"

            fx, fy, fw_b, fh_b = best_box
            pad_x = int(fw_b * 0.10)
            pad_y = int(fh_b * 0.10)
            crop_box = (max(0, fx - pad_x), max(0, fy - pad_y), min(w, fx + fw_b + pad_x), min(h, fy + fh_b + pad_y))
            return crop_box, True, False, 0.85, "OBJECT_AWARE_DUAL_HERO"

    @staticmethod
    def choose_best_half_against_demo(
        raw_img: Image.Image,
        box_a: Tuple[int, int, int, int],
        box_b: Tuple[int, int, int, int],
        demo_img: Image.Image,
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        """Compares visual color histograms of candidate box A and box B against Column W demo.
        Returns (front_box, back_box).
        """
        try:
            half_a = np.array(raw_img.crop(box_a).resize((128, 128)).convert("RGB"))
            half_b = np.array(raw_img.crop(box_b).resize((128, 128)).convert("RGB"))
            demo_rgb = np.array(demo_img.resize((128, 128)).convert("RGB"))

            # Calculate 3D color histograms
            hist_d = cv2.calcHist([demo_rgb], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist_d, hist_d)

            hist_a = cv2.calcHist([half_a], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist_a, hist_a)

            hist_b = cv2.calcHist([half_b], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist_b, hist_b)

            sim_a = cv2.compareHist(hist_d, hist_a, cv2.HISTCMP_CORREL)
            sim_b = cv2.compareHist(hist_d, hist_b, cv2.HISTCMP_CORREL)

            if sim_a >= sim_b:
                return box_a, box_b
            else:
                return box_b, box_a
        except Exception:
            return box_a, box_b

        # Fallback: Optimal seam split based on barcode location and demo ground truth
        if w > h:
            split_x = self.find_optimal_seam(cv_small, axis="vertical", search_range=(0.40, 0.60))
            box_left = (0, 0, min(w, int(w * (split_x + 0.03))), h)
            box_right = (max(0, int(w * (split_x - 0.03))), 0, w, h)

            if demo_img is not None:
                front_box, _ = self.choose_best_half_against_demo(raw_img, box_left, box_right, demo_img)
                return front_box, True, False, 0.88, "SEAM_SPLIT_DEMO_VERIFIED_LANDSCAPE"
            elif bc_x >= 0.50:
                return box_left, True, False, 0.80, "SEAM_SPLIT_LANDSCAPE"
            else:
                return box_right, True, False, 0.80, "SEAM_SPLIT_LANDSCAPE"
        else:
            split_x = self.find_optimal_seam(cv_small, axis="vertical", search_range=(0.35, 0.65))
            box_left = (0, 0, min(w, int(w * (split_x + 0.02))), h)
            box_right = (max(0, int(w * (split_x - 0.02))), 0, w, h)

            if demo_img is not None:
                front_box, _ = self.choose_best_half_against_demo(raw_img, box_left, box_right, demo_img)
                return front_box, True, False, 0.88, "SEAM_SPLIT_DEMO_VERIFIED_PORTRAIT"
            elif bc_x < 0.50:
                return box_right, True, False, 0.80, "SEAM_SPLIT_PORTRAIT"
            else:
                return box_left, True, False, 0.80, "SEAM_SPLIT_PORTRAIT"

    def isolate_front(
        self,
        raw_img: Image.Image,
        demo_img: Optional[Image.Image] = None,
        barcode_center: Optional[Tuple[float, float]] = None,
        strategy: str = "STANDARD",
    ) -> Tuple[Image.Image, bool]:
        """Isolates the front packshot hero from a multi-view raw studio photo."""
        crop_box, was_isolated, is_unc, conf, reason = self.isolate_front_coords(
            raw_img, demo_img=demo_img, barcode_center=barcode_center, strategy=strategy
        )
        self.last_crop_box = crop_box
        self.last_crop_uncertain = is_unc
        self.last_crop_confidence = conf
        self.last_crop_reason = reason

        if was_isolated:
            return raw_img.crop(crop_box), True
        return raw_img, False

    def isolate_back_coords(
        self,
        raw_img: Image.Image,
        barcode_center: Optional[Tuple[float, float]] = None,
        strategy: str = "STANDARD",
    ) -> Tuple[Tuple[int, int, int, int], bool, bool, float, str]:
        """Calculates exact crop coordinates for the back packshot hero on raw_img."""
        w, h = raw_img.size
        full_box = (0, 0, w, h)

        if strategy in ("SEQUENTIAL_PAIR", "CARTON_BOX", "SINGLE_SURFACE"):
            return full_box, False, False, 1.0, "STANDALONE_SHOT"

        bc_x, bc_y = barcode_center if barcode_center is not None else (0.5, 0.5)
        px, py = bc_x * w, bc_y * h
        boxes = self.find_object_boxes(raw_img)

        # Archetype C: STACKED_TUBS_GRID (Back is the top container with nutrition/barcode)
        if strategy == "STACKED_TUBS_GRID":
            top_boxes = [b for b in boxes if (b[1] + b[3]) <= h * 0.55]
            if top_boxes:
                best_box = min(top_boxes, key=lambda b: abs((b[0] + b[2] / 2.0) - w / 2.0))
                bx, by, bw_b, bh_b = best_box
                pad_x = int(bw_b * 0.08)
                pad_y = int(bh_b * 0.08)
                crop_box = (max(0, bx - pad_x), max(0, by - pad_y), min(w, bx + bw_b + pad_x), min(h, by + bh_b + pad_y))
                return crop_box, True, False, 0.85, "STACKED_TUBS_BACK_OBJECT"

        # Horizontal Stack
        is_horizontal_objs = any(b[2] / max(1, b[3]) > 1.6 for b in boxes)
        if is_horizontal_objs and bc_y > 0.55:
            scale = 640.0 / max(w, h)
            small_pil = raw_img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
            cv_small = cv2.cvtColor(np.array(small_pil), cv2.COLOR_RGB2BGR)
            split_y = self.find_optimal_seam(cv_small, axis="horizontal", search_range=(0.40, 0.65))
            cy1 = max(0, int(h * (split_y - 0.03)))
            return (0, cy1, w, h), True, False, 0.85, "HORIZONTAL_STACK_BACK_SEAM"

        # Triple Vertical Panel: Back is the side panel holding barcode
        center_boxes = [b for b in boxes if 0.28 <= (b[0] + b[2] / 2.0) / w <= 0.72 and b[2] < w * 0.50]
        if len(boxes) >= 2 and center_boxes and (bc_x < 0.35 or bc_x > 0.65):
            cb = max(center_boxes, key=lambda b: b[2] * b[3])
            if bc_x < 0.35:
                crop_box = (0, max(0, int(cb[1] * 0.90)), int(cb[0] + cb[2] * 0.05), min(h, int((cb[1] + cb[3]) * 1.10)))
            else:
                crop_box = (max(0, int(cb[0] + cb[2] * 0.95)), max(0, int(cb[1] * 0.90)), w, min(h, int((cb[1] + cb[3]) * 1.10)))
            return crop_box, True, False, 0.88, "TRIPLE_VERTICAL_BACK_PANEL"

        # Object-Aware Back Isolation
        back_box = None
        for b in boxes:
            bx, by, bw_b, bh_b = b
            if bx <= px <= bx + bw_b and by <= py <= by + bh_b:
                back_box = b
                break

        if back_box:
            bx, by, bw_b, bh_b = back_box
            pad_x = int(bw_b * 0.10)
            pad_y = int(bh_b * 0.10)
            crop_box = (max(0, bx - pad_x), max(0, by - pad_y), min(w, bx + bw_b + pad_x), min(h, by + bh_b + pad_y))
            return crop_box, True, False, 0.88, "OBJECT_AWARE_BACK_HERO"

        # Fallback seam split
        scale = 640.0 / max(w, h)
        small_pil = raw_img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
        cv_small = cv2.cvtColor(np.array(small_pil), cv2.COLOR_RGB2BGR)

        if w > h:
            split_x = self.find_optimal_seam(cv_small, axis="vertical", search_range=(0.40, 0.60))
            if bc_x >= 0.50:
                crop_box = (max(0, int(w * (split_x - 0.03))), 0, w, h)
            else:
                crop_box = (0, 0, min(w, int(w * (split_x + 0.03))), h)
            return crop_box, True, False, 0.80, "SEAM_SPLIT_BACK_LANDSCAPE"
        else:
            split_x = self.find_optimal_seam(cv_small, axis="vertical", search_range=(0.35, 0.65))
            if bc_x < 0.50:
                crop_box = (0, 0, min(w, int(w * (split_x + 0.02))), h)
            else:
                crop_box = (max(0, int(w * (split_x - 0.02))), 0, w, h)
            return crop_box, True, False, 0.80, "SEAM_SPLIT_BACK_PORTRAIT"

    def isolate_back(
        self,
        raw_img: Image.Image,
        barcode_center: Optional[Tuple[float, float]] = None,
        strategy: str = "STANDARD",
    ) -> Tuple[Image.Image, bool]:
        """Isolates the back packshot hero from a multi-view raw photo for 'Ảnh mặt sau'."""
        crop_box, was_isolated, is_unc, conf, reason = self.isolate_back_coords(
            raw_img, barcode_center=barcode_center, strategy=strategy
        )
        self.last_crop_box = crop_box
        self.last_crop_uncertain = is_unc
        self.last_crop_confidence = conf
        self.last_crop_reason = reason

        if was_isolated:
            return raw_img.crop(crop_box), True
        return raw_img, False
