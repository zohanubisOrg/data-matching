"""Studio standardizer module: 2048x2048 square canvas, auto-centering, contact shadow, sRGB."""
from __future__ import annotations

from typing import Tuple
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


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

    def standardize(self, rgba_img: Image.Image) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
        """Processes RGBA product into a clean 2048x2048 white packshot.
        
        Returns:
            (packshot_rgb_image, bounding_box_on_canvas)
        """
        # 1. Get tight bounding box of product
        alpha = np.array(rgba_img.split()[-1])
        y_indices, x_indices = np.where(alpha > 10)

        if len(x_indices) == 0 or len(y_indices) == 0:
            # Fallback for empty image
            blank = Image.new("RGB", (self.canvas_size, self.canvas_size), (255, 255, 255))
            return blank, (0, 0, 0, 0)

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
        scaled = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (self.canvas_size, self.canvas_size), (255, 255, 255))
        pos_x = (self.canvas_size - new_w) // 2
        pos_y = (self.canvas_size - new_h) // 2
        canvas.paste(scaled, (pos_x, pos_y))
        return canvas
