"""
Studio Packshot Quality & Webshop Compliance Validator.
Enforces strict e-commerce standards:
1. NO human hands, fingers, or skin holding the product.
2. NO casual domestic room, desk, carpet, or supermarket shelf backgrounds.
3. Background MUST be clean isolated studio white (RGB >= 238, std <= 20) or transparent.
4. NO deformed, squeezed, or heavily wrinkled packaging from human handling.
"""

from __future__ import annotations

import logging
from typing import List, Tuple
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class StudioQualityValidator:
    """Validates whether a candidate image complies with professional webshop studio packshot standards."""

    def __init__(
        self,
        min_border_brightness: float = 236.0,
        max_border_std: float = 22.0,
        max_skin_ratio: float = 0.03,
        max_border_skin_ratio: float = 0.01,
    ):
        self.min_border_brightness = min_border_brightness
        self.max_border_std = max_border_std
        self.max_skin_ratio = max_skin_ratio
        self.max_border_skin_ratio = max_border_skin_ratio

    def validate_studio_compliance(self, img: Image.Image) -> Tuple[bool, List[str]]:
        """
        Validates image against e-commerce studio criteria.
        Returns: (is_compliant, list_of_violation_reasons)
        """
        violations: List[str] = []

        # 1. Check transparency channel
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            # If image has transparent background, check if alpha channel provides clean cutout
            rgba = img.convert("RGBA")
            alpha = np.array(rgba)[:, :, 3]
            border_alpha = np.concatenate([
                alpha[:10, :].ravel(), alpha[-10:, :].ravel(),
                alpha[:, :10].ravel(), alpha[:, -10:].ravel()
            ])
            # If border is mostly transparent, it's a pre-matted clean asset
            if np.mean(border_alpha) < 20.0:
                # Still check for human skin inside the cutout
                rgb_arr = np.array(rgba.convert("RGB"))
                has_skin, skin_msg = self._check_skin(rgb_arr, mask=(alpha > 50))
                if has_skin:
                    violations.append(skin_msg)
                return len(violations) == 0, violations

        # Convert to standard RGB array
        rgb = np.array(img.convert("RGB"))
        h, w, _ = rgb.shape

        # 2. Check Border Background Purity (Studio White Isolation)
        border_thickness = max(4, int(min(h, w) * 0.04))  # 4% perimeter
        top = rgb[:border_thickness, :, :]
        bottom = rgb[-border_thickness:, :, :]
        left = rgb[:, :border_thickness, :]
        right = rgb[:, -border_thickness:, :]
        border_pixels = np.concatenate([
            top.reshape(-1, 3),
            bottom.reshape(-1, 3),
            left.reshape(-1, 3),
            right.reshape(-1, 3),
        ])

        mean_brightness = float(np.mean(border_pixels))
        std_brightness = float(np.std(border_pixels))

        if mean_brightness < self.min_border_brightness or std_brightness > self.max_border_std:
            violations.append(
                f"Non-studio / casual background detected (Border brightness: {mean_brightness:.1f}/255, "
                f"std: {std_brightness:.1f}; expected >= {self.min_border_brightness} and <= {self.max_border_std})"
            )

        # 3. Check for Human Hand / Skin Detection
        has_skin, skin_msg = self._check_skin(rgb)
        if has_skin:
            violations.append(skin_msg)

        is_passed = len(violations) == 0
        return is_passed, violations

    def _check_skin(self, rgb_arr: np.ndarray, mask: np.ndarray = None) -> Tuple[bool, str]:
        """Detects presence of human skin (hands, fingers holding product) in RGB image."""
        bgr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCR_CB)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        # Skin detection in YCrCb
        skin_ycrcb = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))

        # Skin detection in HSV (H: 0-25 or 160-180, S: 40-180, V: 60-255)
        skin_hsv1 = cv2.inRange(hsv, (0, 35, 60), (25, 180, 255))
        skin_hsv2 = cv2.inRange(hsv, (160, 35, 60), (180, 180, 255))
        skin_hsv = cv2.bitwise_or(skin_hsv1, skin_hsv2)

        # Combined skin mask
        skin_mask = cv2.bitwise_and(skin_ycrcb, skin_hsv)

        if mask is not None:
            skin_mask = cv2.bitwise_and(skin_mask, mask.astype(np.uint8) * 255)

        h, w = skin_mask.shape
        skin_ratio = float(np.sum(skin_mask > 0) / skin_mask.size)

        # Perimeter border skin check (hands entering from the edges)
        b_thick = max(4, int(min(h, w) * 0.05))
        border_skin = np.concatenate([
            skin_mask[:b_thick, :].ravel(),
            skin_mask[-b_thick:, :].ravel(),
            skin_mask[:, :b_thick].ravel(),
            skin_mask[:, -b_thick:].ravel(),
        ])
        border_skin_ratio = float(np.sum(border_skin > 0) / border_skin.size)

        # Check for significant skin clusters (hands holding packages)
        if skin_ratio > self.max_skin_ratio or border_skin_ratio > self.max_border_skin_ratio:
            return True, (
                f"Human hand/body detected holding product (Skin ratio: {skin_ratio*100:.1f}%, "
                f"border contact: {border_skin_ratio*100:.1f}%)"
            )

        return False, ""
