from pathlib import Path
from typing import Protocol

from ..models import Packaging


class ImageAttributes:
    def __init__(self, barcode: str | None = None):
        self.barcode = barcode


class VisionProvider(Protocol):
    def analyze(self, image_path: Path) -> ImageAttributes: ...


class NoOpVisionProvider:
    def analyze(self, image_path: Path) -> ImageAttributes:
        return ImageAttributes()

