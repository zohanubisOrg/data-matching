"""Front Hero Selector for multi-container photographs.

Evaluates brand label saliency, color saturation, typography edge energy, and barcode
exclusions across candidate container columns to select exclusively the primary Front Hero.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


class FrontHeroSelector:
    """Selects the single front-facing hero container among isolated candidate columns."""

    def __init__(self, label_zone: Tuple[float, float, float, float] = (0.20, 0.20, 0.80, 0.80)):
        # (y1_ratio, x1_ratio, y2_ratio, x2_ratio) defining the central label region
        self.label_zone = label_zone

    def score_candidate(
        self,
        candidate_crop: Image.Image,
        barcode_in_box: bool = False,
    ) -> float:
        """Scores a candidate crop for front-view likelihood.
        
        Higher score indicates front view with brand typography and colorful graphics.
        """
        if barcode_in_box:
            # Barcode present in this box strongly indicates rear or nutrition panel
            return -1000.0

        w, h = candidate_crop.size
        if w < 50 or h < 50:
            return -500.0

        # Run direct BarcodeDetector on candidate crop: any barcode marks it as REAR view
        try:
            cv_img = cv2.cvtColor(np.array(candidate_crop), cv2.COLOR_RGB2BGR)
            bd = cv2.barcode.BarcodeDetector()
            ret, _, _ = bd.detectAndDecode(cv_img)
            if ret:
                return -1000.0
        except Exception:
            pass

        # 1. Extract central label region
        y1 = int(h * self.label_zone[0])
        x1 = int(w * self.label_zone[1])
        y2 = int(h * self.label_zone[2])
        x2 = int(w * self.label_zone[3])

        label_crop = candidate_crop.crop((x1, y1, x2, y2))
        np_label = np.array(label_crop.convert("RGB"))

        # 2. Text / Logo high-frequency edge energy
        gray = cv2.cvtColor(np_label, cv2.COLOR_RGB2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        edge_energy = float(np.mean(np.sqrt(gx**2 + gy**2)))

        # 3. Color saturation (front brand art is colorful, back ingredients are monochromatic text)
        hsv = cv2.cvtColor(np_label, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        mean_saturation = float(np.mean(sat))
        high_sat_pixels = float(np.sum(sat > 60) / float(sat.size))

        # 4. Composite front likelihood score
        score = edge_energy * 1.5 + mean_saturation * 1.0 + high_sat_pixels * 100.0
        return score

    def select_front_hero(
        self,
        image: Image.Image,
        boxes: List[Tuple[int, int, int, int]],
        barcode_centers: Optional[List[Tuple[float, float]]] = None,
    ) -> Tuple[Tuple[int, int, int, int], int, List[float]]:
        """Selects the best front hero among candidate boxes.
        
        Args:
            image: Full original image.
            boxes: List of candidate (x1, y1, x2, y2) bounding boxes.
            barcode_centers: Optional normalized (x, y) coordinates of detected barcodes.
            
        Returns:
            (best_box, best_index, all_scores)
        """
        if not boxes:
            return (0, 0, image.width, image.height), 0, [0.0]

        if len(boxes) == 1:
            return boxes[0], 0, [100.0]

        img_w, img_h = image.size
        scores: List[float] = []

        for b in boxes:
            bx1, by1, bx2, by2 = b
            crop = image.crop(b)

            # Check if any barcode center falls within this box
            has_bc = False
            if barcode_centers:
                for bc_x, bc_y in barcode_centers:
                    pixel_x = bc_x * img_w
                    pixel_y = bc_y * img_h
                    if bx1 <= pixel_x <= bx2 and by1 <= pixel_y <= by2:
                        has_bc = True
                        break

            s = self.score_candidate(crop, barcode_in_box=has_bc)
            scores.append(s)

        best_idx = int(np.argmax(scores))
        return boxes[best_idx], best_idx, scores
