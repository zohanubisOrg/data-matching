"""Detail-preserving matting engine using BiRefNet with topological outer-contour protection."""
from __future__ import annotations

from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageOps
import rembg


class MattingEngine:
    """Deep packshot matting engine with topological hole-filling for translucent packaging."""

    def __init__(self, model_name: str = "birefnet-general"):
        self.model_name = model_name
        try:
            self.session = rembg.new_session(model_name)
        except Exception:
            # Fallback if specific model fails
            self.session = rembg.new_session("u2net")

    @staticmethod
    def apply_topological_hole_filling(
        alpha: np.ndarray, min_contour_area_ratio: float = 0.03
    ) -> np.ndarray:
        """Protects interior transparent packaging windows from hollow-punching.

        Finds external product contours and locks everything within the closed outer perimeter
        to solid foreground while preserving soft edge transitions along the true outer boundary.
        """
        h, w = alpha.shape
        img_area = h * w

        # Threshold low-confidence foreground to find outer shell
        _, bin_mask = cv2.threshold(alpha, 15, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return alpha

        # Find the single primary hero contour by area
        primary_cnt = max(contours, key=cv2.contourArea)

        # Draw filled solid interior mask for hero product only
        solid_interior = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(solid_interior, [primary_cnt], -1, 255, thickness=cv2.FILLED)

        # Inset solid mask slightly (by 3px) so boundary anti-aliasing from BiRefNet is retained
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        core_solid = cv2.erode(solid_interior, kernel, iterations=1)

        # Inside the product body, ensure alpha is 100% solid (no punch-through on clear windows)
        enhanced_alpha = np.where(core_solid == 255, np.maximum(alpha, 255), alpha)
        # Outside the outer shell, force background to 0
        enhanced_alpha = np.where(solid_interior == 0, 0, enhanced_alpha)

        return enhanced_alpha

    def remove_background(
        self, img: Image.Image, enable_hole_protection: bool = True
    ) -> Tuple[Image.Image, np.ndarray]:
        """Removes background from an image.

        Returns:
            (rgba_image, final_alpha_mask)
        """
        if img.mode != "RGB":
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        max_dim = max(orig_w, orig_h)
        if max_dim > 1800:
            scale = 1800.0 / max_dim
            proc_img = img.resize((int(orig_w * scale), int(orig_h * scale)), Image.Resampling.BILINEAR)
        else:
            proc_img = img

        # Run deep neural matting via rembg BiRefNet session
        # Use only_mask=True to inspect and enhance the alpha channel directly
        raw_mask_pil = rembg.remove(proc_img, session=self.session, only_mask=True)
        if raw_mask_pil.size != (orig_w, orig_h):
            raw_mask_pil = raw_mask_pil.resize((orig_w, orig_h), Image.Resampling.BILINEAR)
        raw_alpha = np.array(raw_mask_pil)

        if enable_hole_protection:
            final_alpha = self.apply_topological_hole_filling(raw_alpha)
        else:
            final_alpha = raw_alpha

        # Construct final RGBA image
        r, g, b = img.split()
        alpha_channel = Image.fromarray(final_alpha, mode="L")
        rgba = Image.merge("RGBA", (r, g, b, alpha_channel))

        import gc
        gc.collect()

        return rgba, final_alpha
