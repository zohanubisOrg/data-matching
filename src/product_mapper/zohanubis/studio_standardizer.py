import hashlib
import io
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


class AntiDuplicateGuard:
    """Guards against saving identical output images across partition deliverables."""

    def __init__(self):
        self._seen_hashes: Dict[str, str] = {}  # sha256 -> identifier (barcode or filename)

    def check_unique(self, img_bytes: bytes, identifier: str) -> Tuple[bool, Optional[str]]:
        """Checks if img_bytes is unique. Returns (is_unique, conflicting_identifier)."""
        h = hashlib.sha256(img_bytes).hexdigest()
        if h in self._seen_hashes:
            return False, self._seen_hashes[h]
        self._seen_hashes[h] = identifier
        return True, None

    def register_existing_file(self, file_path: Path, identifier: str) -> None:
        """Registers an already existing file to prevent duplicates from matching it."""
        try:
            if file_path.exists() and file_path.is_file():
                h = hashlib.sha256(file_path.read_bytes()).hexdigest()
                self._seen_hashes[h] = identifier
        except Exception:
            pass

    def check_image_unique(self, image: Image.Image, identifier: str, quality: int = 95) -> Tuple[bool, Optional[str]]:
        """Checks if a PIL Image encoded as JPEG is unique. Returns (is_unique, conflicting_identifier)."""
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=quality, optimize=True)
        return self.check_unique(buf.getvalue(), identifier)

    def reset(self) -> None:
        self._seen_hashes.clear()


class StudioStandardizer:
    """Places masked product onto a standardized 2048x2048 webshop packshot."""

    def __init__(
        self,
        canvas_size: int = 2048,
        target_fill_ratio: float = 0.80,  # Product occupies ~80% of canvas dimension
        enable_contact_shadow: bool = True,
    ):
        self.canvas_size = canvas_size
        self.target_fill_ratio = target_fill_ratio
        self.enable_contact_shadow = enable_contact_shadow
        self.duplicate_guard = AntiDuplicateGuard()

    def standardize(
        self, rgba_img: Image.Image, is_container: bool = False
    ) -> Tuple[Image.Image, np.ndarray, Tuple[int, int, int, int]]:
        """Processes RGBA product into a clean 2048x2048 white packshot.
        
        Args:
            rgba_img: RGBA product image.
            is_container: If True, applies specialized glass/reflection suppression and container grounding.
            
        Returns:
            (packshot_rgb_image, canvas_alpha_mask, bounding_box_on_canvas)
        """
        # 1. Filter out floor reflection strips while preserving multi-piece product geometry
        alpha = np.array(rgba_img.split()[-1])
        _, bin_mask = cv2.threshold(alpha, 20, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img_h, img_w = rgba_img.height, rgba_img.width

        clutter_mask = np.zeros_like(alpha)
        has_clutter = False
        min_aspect_clutter = 2.5 if is_container else 4.5
        y_cutoff = 0.83 if is_container else 0.85

        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            centroid_y = cy + ch / 2.0
            aspect = float(cw) / max(1.0, float(ch))
            # Discard flat floor reflection bands at bottom edge
            if centroid_y > (img_h * y_cutoff) and aspect > min_aspect_clutter:
                cv2.drawContours(clutter_mask, [c], -1, 255, thickness=cv2.FILLED)
                has_clutter = True

        if has_clutter:
            alpha = np.where(clutter_mask == 255, 0, alpha)
            r, g, b, _ = rgba_img.split()
            rgba_img = Image.merge("RGBA", (r, g, b, Image.fromarray(alpha)))

        y_indices, x_indices = np.where(alpha > 10)

        if len(x_indices) == 0 or len(y_indices) == 0:
            # Fallback for empty image
            blank = Image.new("RGB", (self.canvas_size, self.canvas_size), (255, 255, 255))
            empty_mask = np.zeros((self.canvas_size, self.canvas_size), dtype=np.uint8)
            return blank, empty_mask, (0, 0, 0, 0)

        x_min, x_max = int(np.min(x_indices)), int(np.max(x_indices))
        y_min, y_max = int(np.min(y_indices)), int(np.max(y_indices))

        crop_w = max(1, x_max - x_min + 1)
        crop_h = max(1, y_max - y_min + 1)

        cropped_rgba = rgba_img.crop((x_min, y_min, x_max + 1, y_max + 1))

        # 2. Scale product to target fill ratio (e.g. 80% of 2048 = 1638px)
        max_target_dim = int(self.canvas_size * self.target_fill_ratio)
        scale = min(max_target_dim / float(crop_w), max_target_dim / float(crop_h))
        new_w = max(1, int(crop_w * scale))
        new_h = max(1, int(crop_h * scale))

        scaled_product = cropped_rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 3. Create 2048x2048 white canvas
        canvas = Image.new("RGB", (self.canvas_size, self.canvas_size), (255, 255, 255))

        # Position product centered horizontally and slightly grounded vertically (48% center)
        pos_x = (self.canvas_size - new_w) // 2
        pos_y = int((self.canvas_size - new_h) * 0.48)

        # 4. Optional subtle contact shadow at product base
        if self.enable_contact_shadow:
            shadow_h = max(8, int(new_h * 0.05))
            shadow_w = int(new_w * 0.85)
            shadow_x = (self.canvas_size - shadow_w) // 2
            shadow_y = pos_y + new_h - int(shadow_h * 0.4)

            # Create soft radial shadow ellipse
            shadow_canvas = Image.new("RGBA", (self.canvas_size, self.canvas_size), (255, 255, 255, 0))
            shadow_arr = np.zeros((self.canvas_size, self.canvas_size), dtype=np.uint8)
            cv2.ellipse(
                shadow_arr,
                (shadow_x + shadow_w // 2, shadow_y + shadow_h // 2),
                (shadow_w // 2, shadow_h // 2),
                0,
                0,
                360,
                40,  # Subtle 15% opacity
                -1,
            )
            # Blur shadow heavily
            shadow_blurred = cv2.GaussianBlur(shadow_arr, (45, 45), 0)
            shadow_rgba = Image.fromarray(shadow_blurred, mode="L")
            shadow_layer = Image.new("RGBA", (self.canvas_size, self.canvas_size), (0, 0, 0, 0))
            shadow_layer.putalpha(shadow_rgba)

            # Paste shadow
            canvas.paste(
                Image.new("RGB", (self.canvas_size, self.canvas_size), (210, 210, 210)),
                (0, 0),
                shadow_rgba,
            )

        # 5. Composite product onto canvas using its alpha channel
        prod_alpha = scaled_product.split()[-1]
        canvas.paste(scaled_product, (pos_x, pos_y), prod_alpha)

        # Create matching 2048x2048 alpha mask
        canvas_alpha = np.zeros((self.canvas_size, self.canvas_size), dtype=np.uint8)
        canvas_alpha[pos_y : pos_y + new_h, pos_x : pos_x + new_w] = np.array(prod_alpha)

        # 6. Apply mild unsharp sharpening to bring out sharp studio textures
        sharpened = canvas.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))

        bbox = (pos_x, pos_y, new_w, new_h)
        return sharpened, canvas_alpha, bbox

    def fit_to_canvas(self, rgb_img: Image.Image) -> Image.Image:
        """Resizes square or rectangular image to fit canvas_size with pure white background."""
        w, h = rgb_img.size
        if w == self.canvas_size and h == self.canvas_size:
            return rgb_img
        scale = min(self.canvas_size / float(w), self.canvas_size / float(h))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        scaled = rgb_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (self.canvas_size, self.canvas_size), (255, 255, 255))
        pos_x = (self.canvas_size - new_w) // 2
        pos_y = (self.canvas_size - new_h) // 2
        canvas.paste(scaled, (pos_x, pos_y))
        return canvas
