from pathlib import Path

from .provider import ImageAttributes, NoOpVisionProvider


class BarcodeReader:
    def __init__(self):
        try:
            import zxingcpp  # type: ignore
            self._zxing = zxingcpp
        except ImportError:
            self._zxing = None

    @property
    def available(self) -> bool:
        return self._zxing is not None

    def analyze(self, path: Path) -> ImageAttributes:
        if self._zxing is None:
            return NoOpVisionProvider().analyze(path)
        from PIL import Image
        results = self._zxing.read_barcodes(Image.open(path))
        values = [str(x.text).strip() for x in results if getattr(x, "text", None)]
        return ImageAttributes(values[0] if len(values) == 1 else None)

