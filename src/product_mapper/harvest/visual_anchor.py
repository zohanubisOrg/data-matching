"""
Visual Anchor Validator using Column W Demo Thumbnails.
Calculates bounding box aspect ratios (W/H) and rejects candidates with > 25% aspect drift.
"""

from __future__ import annotations

import io
import logging
from typing import Dict, Optional, Tuple
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def compute_content_bounding_box(img: Image.Image, threshold: int = 248) -> Optional[Tuple[int, int, int, int]]:
    """
    Computes the bounding box (min_x, min_y, max_x, max_y) of non-white, non-transparent content.
    Returns None if the image is entirely white or empty.
    """
    rgba = img.convert("RGBA")
    arr = np.array(rgba)

    # Content condition: alpha > 10 AND not pure white (any RGB < threshold)
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]

    is_opaque = alpha > 10
    is_non_white = np.any(rgb < threshold, axis=2)
    content_mask = is_opaque & is_non_white

    coords = np.argwhere(content_mask)
    if coords.size == 0:
        return None

    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    return (int(x_min), int(y_min), int(x_max), int(y_max))


def get_bounding_box_aspect_ratio(img: Image.Image) -> Optional[float]:
    """Calculates width / height ratio of the content bounding box."""
    bbox = compute_content_bounding_box(img)
    if not bbox:
        # Fallback to image aspect ratio if no bounding box found
        w, h = img.size
        return float(w) / float(h) if h > 0 else 1.0

    min_x, min_y, max_x, max_y = bbox
    w = max(1, max_x - min_x + 1)
    h = max(1, max_y - min_y + 1)
    return float(w) / float(h)


class VisualAnchorValidator:
    """Validates candidate packshots against the canonical Column W demo image."""

    def __init__(self, max_aspect_drift: float = 0.25):
        self.max_aspect_drift = max_aspect_drift

    def validate_candidate_against_demo(
        self,
        candidate_img: Image.Image,
        demo_img_bytes: Optional[bytes],
    ) -> Tuple[bool, float, str]:
        """
        Validates candidate aspect ratio against the demo thumbnail.
        Returns: (is_valid, drift_value, reason)
        """
        if not demo_img_bytes or len(demo_img_bytes) < 100:
            # If no demo image is available, pass by default with warning
            return True, 0.0, "No demo visual anchor available"

        try:
            demo_img = Image.open(io.BytesIO(demo_img_bytes))
            demo_ratio = get_bounding_box_aspect_ratio(demo_img)
            cand_ratio = get_bounding_box_aspect_ratio(candidate_img)

            if not demo_ratio or not cand_ratio:
                return True, 0.0, "Aspect ratio indeterminate"

            drift = abs(cand_ratio - demo_ratio) / demo_ratio
            if drift > self.max_aspect_drift:
                msg = f"Aspect ratio mismatch: candidate={cand_ratio:.2f} vs demo={demo_ratio:.2f} (drift={drift:.1%} > {self.max_aspect_drift:.0%})"
                return False, drift, msg

            return True, drift, f"Aspect match OK (drift={drift:.1%})"

        except Exception as e:
            logger.debug(f"Visual anchor comparison failed: {e}")
            return True, 0.0, f"Comparison error: {e}"
