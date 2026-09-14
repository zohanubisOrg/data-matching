from __future__ import annotations

from collections.abc import Callable, Iterable
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

    def _variants(self, image: Image.Image) -> list[Image.Image]:
        rgb = image.convert("RGB")
        gray = ImageOps.autocontrast(ImageOps.grayscale(rgb)).convert("RGB")
        variants = [
            rgb,
            gray,
            rgb.resize((rgb.width * 2, rgb.height * 2), Image.Resampling.LANCZOS),
            gray.resize((gray.width * 3, gray.height * 3), Image.Resampling.LANCZOS),
            rgb.rotate(90, expand=True),
            rgb.rotate(180, expand=True),
            rgb.rotate(270, expand=True),
        ]
        if self._max_passes is not None:
            return variants[: max(0, self._max_passes)]
        return variants

    def analyze(self, path: Path) -> ImageAttributes:
        if self._decoder is None:
            return ImageAttributes(warnings=["barcode_decoder_unavailable"])

        decoded_values: list[str] = []
        warnings: list[str] = []
        with Image.open(path) as source:
            for index, variant in enumerate(self._variants(source), 1):
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
