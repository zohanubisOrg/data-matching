from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from PIL import Image, ImageOps

from .barcode_utils import (
    choose_barcode_consensus,
    is_gtin_like,
    normalize_barcode,
    validate_gtin,
)
from .provider import ImageAttributes


Decoder = Callable[[Image.Image], Iterable[object]]


class BarcodeReader:
    def __init__(self, decoder: Decoder | None = None, max_passes: int | None = None):
        self._decoder = decoder
        self._max_passes = max_passes
        if self._decoder is None:
            try:
                import zxingcpp  # type: ignore

                def zxing_decoder(image: Image.Image) -> list[str]:
                    results = zxingcpp.read_barcodes(image)
                    return [str(item.text).strip() for item in results if getattr(item, "text", None)]

                self._decoder = zxing_decoder
            except ImportError:
                self._decoder = None

    @property
    def available(self) -> bool:
        return self._decoder is not None

    @staticmethod
    def _resize_max(image: Image.Image, max_side: int) -> Image.Image:
        longest = max(image.size)
        if longest <= max_side:
            return image.copy()
        scale = max_side / longest
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        return image.resize(size, Image.Resampling.LANCZOS)

    def _variants(self, image: Image.Image) -> Iterator[Image.Image]:
        """Yield decoding passes without creating 2x/3x copies of large phone photos."""
        rgb = image.convert("RGB")
        gray = ImageOps.autocontrast(ImageOps.grayscale(rgb)).convert("RGB")

        yield rgb
        yield gray

        # Upscaling helps small supplier images, but expanding a 12MP phone photo is
        # expensive and usually adds no decoding information. Cap working resolution.
        longest = max(rgb.size)
        if longest < 1600:
            scale = min(2.0, 1600 / max(1, longest))
            size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
            yield rgb.resize(size, Image.Resampling.LANCZOS)
            yield gray.resize(size, Image.Resampling.LANCZOS)
        else:
            yield self._resize_max(gray, 2200)

        rotation_base = self._resize_max(rgb, 2200)
        yield rotation_base.rotate(90, expand=True)
        yield rotation_base.rotate(180, expand=True)
        yield rotation_base.rotate(270, expand=True)

    def analyze(self, path: Path) -> ImageAttributes:
        if self._decoder is None:
            return ImageAttributes(warnings=["barcode_decoder_unavailable"])

        decoded_values: list[str] = []
        warnings: list[str] = []
        with Image.open(path) as source:
            for index, variant in enumerate(self._variants(source), 1):
                if self._max_passes is not None and index > max(0, self._max_passes):
                    break
                try:
                    values = self._decoder(variant)
                    decoded_values.extend(
                        normalized
                        for normalized in (normalize_barcode(value) for value in values)
                        if normalized
                    )
                except Exception as exc:
                    warnings.append(f"barcode_pass_{index}_failed:{type(exc).__name__}")

        barcode = choose_barcode_consensus(decoded_values)
        checksum_valid = None
        if barcode and is_gtin_like(barcode):
            checksum_valid = validate_gtin(barcode)

        return ImageAttributes(
            barcode=barcode,
            barcode_candidates=decoded_values,
            barcode_checksum_valid=checksum_valid,
            warnings=warnings,
        )
