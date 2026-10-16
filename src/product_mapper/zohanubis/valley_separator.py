"""Multi-Column Valley Separator for adjacent standing bottles, jars, and boxes.

Uses 1D horizontal density projections to locate low-density valleys (gaps) between
prominent container peaks, isolating individual items without slicing through bodies.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


class MultiColumnValleySeparator:
    """Detects and isolates 1, 2, or 3 adjacent upright containers in a single studio photo."""

    def __init__(self, smoothing_sigma: float = 12.0, min_peak_prominence: float = 0.20):
        self.smoothing_sigma = smoothing_sigma
        self.min_peak_prominence = min_peak_prominence

    def separate_columns(
        self,
        image: Image.Image,
        fg_mask: Optional[np.ndarray] = None,
        matting_engine: Optional[Any] = None,
    ) -> List[Tuple[int, int, int, int]]:
        """Splits an image into bounding boxes of individual container columns.
        
        Args:
            image: PIL Image (normalized RGB).
            fg_mask: Optional 2D binary mask where 255 = product, 0 = background.
            matting_engine: Optional MattingEngine to generate fast preview alpha mask if fg_mask is None.
            
        Returns:
            List of (x1, y1, x2, y2) bounding boxes in original image coordinates.
        """
        w, h = image.size
        # Work at standardized scale for consistent density profiling
        proc_w = 800
        proc_h = max(1, int(proc_w * h / float(w)))

        if fg_mask is None and matting_engine is not None:
            thumb = image.resize((512, max(1, int(512 * h / float(w)))))
            _, thumb_alpha = matting_engine.remove_background(thumb, allow_escalation=False)
            bin_mask = cv2.resize(thumb_alpha, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
        elif fg_mask is None:
            # Estimate foreground using combined gradient magnitude and Otsu thresholding
            small = image.resize((proc_w, proc_h), Image.Resampling.BILINEAR)
            small_gray = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2GRAY)
            gx = cv2.Sobel(small_gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(small_gray, cv2.CV_32F, 0, 1, ksize=3)
            grad = np.sqrt(gx**2 + gy**2)
            grad_norm = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            _, grad_bin = cv2.threshold(grad_norm, 20, 255, cv2.THRESH_BINARY)
            _, otsu_bin = cv2.threshold(small_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            bin_mask = cv2.bitwise_or(grad_bin, otsu_bin)
        else:
            bin_mask = cv2.resize(fg_mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)

        # 1. Compute horizontal density projection (sum of active pixels per column)
        col_density = np.sum(bin_mask > 0, axis=0).astype(np.float32)

        # 2. Smooth density profile with 1D Gaussian kernel
        ksize = int(self.smoothing_sigma * 6) | 1  # ensure odd
        smoothed = cv2.GaussianBlur(col_density.reshape(1, -1), (ksize, 1), self.smoothing_sigma)[0]

        max_density = np.max(smoothed)
        if max_density < proc_h * 0.10:
            # Empty or almost empty image
            return [(0, 0, w, h)]

        # 3. Detect candidate active column regions
        active_thresh = max_density * 0.15
        is_active = smoothed > active_thresh
        active_indices = np.where(is_active)[0]
        if len(active_indices) == 0:
            return [(0, 0, w, h)]

        x_start, x_end = int(active_indices[0]), int(active_indices[-1])

        # 4. Search for internal valleys (local minima) between peaks
        # A valley is a local minimum between x_start + 10% and x_end - 10%
        margin = int((x_end - x_start) * 0.12)
        search_start = x_start + margin
        search_end = x_end - margin

        if search_end <= search_start:
            return [(0, 0, w, h)]

        # Find all local minima in search range
        valleys: List[int] = []
        for x in range(search_start, search_end):
            # Check local minimum in window of +- 20px
            w_min = max(x_start, x - 25)
            w_max = min(x_end, x + 25)
            if smoothed[x] == np.min(smoothed[w_min:w_max]):
                # Must be substantially lower than surrounding peaks
                left_peak = np.max(smoothed[w_min:x]) if x > w_min else smoothed[x]
                right_peak = np.max(smoothed[x:w_max]) if w_max > x else smoothed[x]
                peak_ref = min(left_peak, right_peak)
                if smoothed[x] < (peak_ref * 0.75):
                    # Avoid duplicate valleys in close proximity
                    if not valleys or (x - valleys[-1]) > (proc_w * 0.10):
                        valleys.append(x)

        # Limit to at most 2 cut valleys (supporting up to 3 containers)
        if len(valleys) > 2:
            # Sort by lowest density (deepest valleys first)
            valleys.sort(key=lambda vx: smoothed[vx])
            valleys = sorted(valleys[:2])

        if not valleys:
            # Single container
            return [(0, 0, w, h)]

        # 5. Build column bounding boxes
        cut_points_x = [0] + valleys + [proc_w]
        scale_x = float(w) / float(proc_w)

        boxes: List[Tuple[int, int, int, int]] = []
        for i in range(len(cut_points_x) - 1):
            cx1 = int(cut_points_x[i] * scale_x)
            cx2 = int(cut_points_x[i + 1] * scale_x)

            # Add small padding to prevent cutting labels at borders
            pad = int(w * 0.015)
            bx1 = max(0, cx1 - (pad if i > 0 else 0))
            bx2 = min(w, cx2 + (pad if i < len(cut_points_x) - 2 else 0))

            # Only accept segments with reasonable width (> 10% of image width)
            if (bx2 - bx1) >= (w * 0.10):
                boxes.append((bx1, 0, bx2, h))

        return boxes if boxes else [(0, 0, w, h)]
