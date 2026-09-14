from __future__ import annotations

from collections import Counter, defaultdict

from ..models import ProductImage


def _globally_safe_capture_ids(images: list[ProductImage]) -> set[str]:
    """Return capture ids that form exactly one unambiguous front/back pair.

    This supports common camera layouts where front/ and back/ are separate folders,
    while avoiding accidental cross-pairing when the same numeric capture id is reused
    by multiple packs or suppliers.
    """
    by_capture: dict[str, list[ProductImage]] = defaultdict(list)
    for image in images:
        if image.capture_id:
            by_capture[image.capture_id.casefold()].append(image)

    safe: set[str] = set()
    for capture_id, items in by_capture.items():
        side_counts = Counter((item.image_side or "").casefold() for item in items)
        if len(items) == 2 and side_counts == Counter({"front": 1, "back": 1}):
            safe.add(capture_id)
    return safe


def group_product_images(images: list[ProductImage]) -> list[list[ProductImage]]:
    """Group explicit product captures without guessing ambiguous capture identities.

    A globally unique front/back pair is grouped even when stored in separate front/
    and back/ folders. Reused capture ids are scoped back to their parent directory so
    different packs can never be merged accidentally. Legacy images stay independent.
    Output order follows first appearance in the input list.
    """
    groups: dict[str, list[ProductImage]] = defaultdict(list)
    order: list[str] = []
    global_pairs = _globally_safe_capture_ids(images)

    for index, image in enumerate(images):
        if image.capture_id:
            capture_id = image.capture_id.casefold()
            if capture_id in global_pairs:
                key = f"capture-global:{capture_id}"
            else:
                key = f"capture-parent:{image.path.parent.resolve()}:{capture_id}"
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
