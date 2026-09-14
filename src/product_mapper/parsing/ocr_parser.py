from __future__ import annotations

from collections.abc import Iterable

from ..matching.no_fuzzy import _identity
from ..vision.provider import OCRLine


def ocr_text(lines: Iterable[OCRLine], min_confidence: float = 0.50) -> str:
    """Join observable OCR lines without guessing missing text.

    A confidence of 0 is treated as unknown rather than rejected so providers that
    cannot expose scores still remain usable.
    """
    accepted: list[str] = []
    for line in lines:
        text = str(line.text).strip()
        if not text:
            continue
        if line.confidence > 0 and line.confidence < min_confidence:
            continue
        accepted.append(text)
    return " ".join(accepted)


def parse_ocr_identity(lines: Iterable[OCRLine]) -> dict:
    """Build the same deterministic canonical identity used by the no-fuzzy matcher."""
    return _identity(ocr_text(lines))
