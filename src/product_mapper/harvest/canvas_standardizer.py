"""
Lightweight 2048x2048 Studio Canvas Standardizer and 4-Layer HD Enhancer.
Applies auto-bounding-box detection, Lanczos-4 scaling, Bilateral denoise, Unsharp Masking,
Chroma 4:4:4 saving, and post-save Laplacian sharpness inspection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageFilter

from .visual_anchor import compute_content_bounding_box

logger = logging.getLogger(__name__)


class CanvasStandardizerAndEnhancer:
    """Standardizes pre-matted packshot images onto 2048x2048 studio canvases with HD sharpening."""

    TARGET_DIM = 2048
    FILL_RATIO = 0.84  # Product occupies 84% (1720px) of 2048px canvas
    MIN_LAPLACIAN_SCORE = 50.0

    def __init__(
        self,
        target_dim: int = TARGET_DIM,
        fill_ratio: float = FILL_RATIO,
        min_laplacian: float = MIN_LAPLACIAN_SCORE,
    ):
        self.target_dim = target_dim
        self.fill_ratio = fill_ratio
        self.min_laplacian = min_laplacian

    def auto_crop_content(self, img: Image.Image) -> Image.Image:
        """Trims empty white/transparent margins around the product."""
        bbox = compute_content_bounding_box(img, threshold=248)
        if not bbox:
            return img
        min_x, min_y, max_x, max_y = bbox
        return img.crop((min_x, min_y, max_x + 1, max_y + 1))

    def standardize_and_enhance(
        self,
        img: Image.Image,
        barcode: str,
        output_dir: Path,
    ) -> Tuple[bool, Optional[Path], float, str]:
        """
        Processes image through the 4-layer quality pipeline and saves to output_dir/{barcode}-front.jpg.
        Returns: (is_success, output_path or None, laplacian_score, status_message)
        """
        clean_bc = str(barcode or "").strip()
        if not clean_bc:
            return False, None, 0.0, "Missing barcode"

        output_dir.mkdir(parents=True, exist_ok=True)
        dest_file = output_dir / f"{clean_bc}-front.jpg"

        try:
            # 1. Auto-crop margin
            cropped = self.auto_crop_content(img)
            cw, ch = cropped.size

            # 2. Scale product to 84% target dimension using Lanczos-4
            max_prod_dim = int(self.target_dim * self.fill_ratio)
            scale = max_prod_dim / max(cw, ch)
            new_w = max(1, int(cw * scale))
            new_h = max(1, int(ch * scale))

            resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 3. Canvas placement on pure white (2048x2048)
            canvas = Image.new("RGBA", (self.target_dim, self.target_dim), (255, 255, 255, 255))
            x_offset = (self.target_dim - new_w) // 2
            y_offset = (self.target_dim - new_h) // 2

            if resized.mode in ("RGBA", "LA") or (resized.mode == "P" and "transparency" in resized.info):
                canvas.paste(resized, (x_offset, y_offset), mask=resized.convert("RGBA"))
            else:
                canvas.paste(resized, (x_offset, y_offset))

            rgb_img = canvas.convert("RGB")

            # 4. Bilateral Denoise (Suppress JPEG compression noise without edge blurring)
            arr = np.array(rgb_img)
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            denoised_bgr = cv2.bilateralFilter(bgr, d=5, sigmaColor=35, sigmaSpace=35)
            denoised_rgb = Image.fromarray(cv2.cvtColor(denoised_bgr, cv2.COLOR_BGR2RGB))

            # 5. Adaptive Unsharp Masking for crisp label typography
            sharpened = denoised_rgb.filter(
                ImageFilter.UnsharpMask(radius=1.2, percent=130, threshold=2)
            )

            # 6. Save with Chroma 4:4:4 and Quality 95
            sharpened.save(
                dest_file,
                format="JPEG",
                quality=95,
                subsampling=0,  # 4:4:4 no color subsampling
                optimize=True,
                progressive=True,
            )

            # 7. Post-save Laplacian sharpness inspection
            gray = cv2.imread(str(dest_file), cv2.IMREAD_GRAYSCALE)
            if gray is None:
                if dest_file.exists():
                    dest_file.unlink()
                return False, None, 0.0, "Failed to read saved image for QA inspection"

            laplacian_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if laplacian_score < self.min_laplacian:
                if dest_file.exists():
                    dest_file.unlink()
                msg = f"Rejected: Laplacian sharpness score {laplacian_score:.1f} < threshold {self.min_laplacian:.1f}"
                return False, None, laplacian_score, msg

            return True, dest_file, laplacian_score, f"PASS (Sharpness: {laplacian_score:.1f})"

        except Exception as e:
            if dest_file.exists():
                try:
                    dest_file.unlink()
                except Exception:
                    pass
            logger.error(f"Failed to standardize {clean_bc}: {e}")
            return False, None, 0.0, f"Error: {e}"
