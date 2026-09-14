from __future__ import annotations

from collections import defaultdict

from ..models import ProductImage


def group_product_images(images: list[ProductImage]) -> list[list[ProductImage]]:
    """Group explicit front/back captures while leaving legacy images independent.

    Only images with an explicit ``capture_id`` are grouped. Legacy supplier images
    may share source ids for unrelated reasons, so they are never implicitly merged.
    Output order follows the first appearance of each capture in the input list.
    """
    groups: dict[str, list[ProductImage]] = defaultdict(list)
    order: list[str] = []

    for index, image in enumerate(images):
        if image.capture_id:
            key = f"capture:{image.path.parent.resolve()}:{image.capture_id}"
        else:
            key = f"image:{index}:{image.path.resolve()}"
        if key not in groups:
            order.append(key)
        groups[key].append(image)

    return [groups[key] for key in order]


def preferred_ocr_images(images: list[ProductImage]) -> list[ProductImage]:
    """Prefer front-label OCR to avoid ingredient/back-label false conflicts."""
    fronts = [image for image in images if image.image_side == "front"]
    return fronts or images[:1]
