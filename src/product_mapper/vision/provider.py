from __future__ import annotations

from pathlib import Path
from typing import Protocol


class OCRLine:
    def __init__(
        self,
        text: str,
        confidence: float = 0.0,
        polygon: list[list[float]] | None = None,
    ):
        self.text = str(text).strip()
        self.confidence = float(confidence)
        self.polygon = polygon or []


class ImageAttributes:
    def __init__(
        self,
        barcode: str | None = None,
        barcode_candidates: list[str] | None = None,
        barcode_checksum_valid: bool | None = None,
        ocr_lines: list[OCRLine] | None = None,
        warnings: list[str] | None = None,
    ):
        self.barcode = barcode
        self.barcode_candidates = barcode_candidates or []
        self.barcode_checksum_valid = barcode_checksum_valid
        self.ocr_lines = ocr_lines or []
        self.warnings = warnings or []


class VisionProvider(Protocol):
    def analyze(self, image_path: Path) -> ImageAttributes: ...


class NoOpVisionProvider:
    def analyze(self, image_path: Path) -> ImageAttributes:
        return ImageAttributes()
