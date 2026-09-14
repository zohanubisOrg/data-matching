from __future__ import annotations

from collections.abc import Iterable

from ..matching.no_fuzzy import _extract_item_size, _identity
from ..vision.provider import OCRLine


def _accepted_texts(lines: Iterable[OCRLine], min_confidence: float = 0.50) -> list[str]:
    accepted: list[str] = []
    for line in lines:
        text = str(line.text).strip()
        if not text:
            continue
        if line.confidence > 0 and line.confidence < min_confidence:
            continue
        accepted.append(text)
    return accepted


def ocr_text(lines: Iterable[OCRLine], min_confidence: float = 0.50) -> str:
    """Join observable OCR lines without guessing missing text.

    A confidence of 0 is treated as unknown rather than rejected so providers that
    cannot expose scores still remain usable for human-review candidate generation.
    """
    return " ".join(_accepted_texts(lines, min_confidence))


def parse_ocr_identity(lines: Iterable[OCRLine]) -> dict:
    """Build conservative structured OCR evidence for deterministic review.

    Packaging backs commonly contain both the real pack size and nutrition reference
    sizes such as ``100 ml``. When multiple different measurements are visible, size is
    marked ambiguous and is not used as a hard candidate filter. Exact high-confidence
    label windows used for barcode conflict checks are handled separately.
    """
    accepted = _accepted_texts(lines)
    identity = _identity(" ".join(accepted))

    observed: list[tuple[str, float]] = []
    seen: set[tuple[str, float]] = set()
    for text in accepted:
        item_size = _extract_item_size(text)
        if item_size and item_size not in seen:
            observed.append(item_size)
            seen.add(item_size)

    identity["observed_sizes"] = observed
    identity["size_ambiguous"] = len(observed) > 1
    if len(observed) == 1:
        identity["item_size"] = observed[0]
    elif len(observed) > 1:
        identity["item_size"] = None
    return identity
