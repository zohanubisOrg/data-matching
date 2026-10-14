"""Compatibility renderer: an independent whole-package mask is now mandatory.
Legacy padding/hole/sharpness arguments no longer delete packaging or alter text.
Use reprocess_rabuta_verified.py for identity-bound processing.
"""
from PIL import Image
from .package_packshot import render_verified_packshot


def make_smart_packshot(image: Image.Image, target_side=2400, pad_ratio=.08,
                        fill_holes=True, sharpness_factor=1.15, *, package_mask=None,
                        shape='auto') -> Image.Image:
    return render_verified_packshot(image, package_mask, target_side, shape)[0]
