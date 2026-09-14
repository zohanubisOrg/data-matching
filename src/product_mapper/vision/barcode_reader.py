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
        """Yield bounded decoding passes suitable for large phone photos."""
        # Respect phone-camera EXIF orientation before creating deterministic variants.
        oriented = ImageOps.exif_transpose(image)
        original = oriented.convert("RGB")
        longest = max(original.size)
        if longest < 1600:
            scale = min(2.0, 1600 / max(1, longest))
            size = (max(1, round(original.width * scale)), max(1, round(original.height * scale)))
            rgb = original.resize(size, Image.Resampling.LANCZOS)
        else:
            rgb = self._resize_max(original, 2600)
        gray = ImageOps.autocontrast(ImageOps.grayscale(rgb)).convert("RGB")

        yield rgb
        yield gray

        compact_rgb = self._resize_max(rgb, 1800)
        compact_gray = ImageOps.autocontrast(ImageOps.grayscale(compact_rgb)).convert("RGB")
        yield compact_rgb
        yield compact_gray

        rotation_base = self._resize_max(rgb, 2200)
        yield rotation_base.rotate(90, expand=True)
        yield rotation_base.rotate(180, expand=True)
        yield rotation_base.rotate(270, expand=True)

    @staticmethod
    def _select_barcode(decoded_values: list[str]) -> str | None:
        """Prefer checksum-valid GTIN evidence before generic decode frequency."""
        valid_gtins = [
            value
            for value in decoded_values
            if is_gtin_like(value) and validate_gtin(value)
        ]
        valid_consensus = choose_barcode_consensus(valid_gtins)
        if valid_consensus:
            return valid_consensus
        if len(set(valid_gtins)) > 1:
            return None
        return choose_barcode_consensus(decoded_values)

    def _analyze(self, path: Path, pass_limit: int | None) -> ImageAttributes:
        if self._decoder is None:
            return ImageAttributes(warnings=["barcode_decoder_unavailable"])

        decoded_values: list[str] = []
        warnings: list[str] = []
        with Image.open(path) as source:
            for index, variant in enumerate(self._variants(source), 1):
                if pass_limit is not None and index > max(0, pass_limit):
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

        barcode = self._select_barcode(decoded_values)
        checksum_valid = None
        if barcode and is_gtin_like(barcode):
            checksum_valid = validate_gtin(barcode)

        return ImageAttributes(
            barcode=barcode,
            barcode_candidates=decoded_values,
            barcode_checksum_valid=checksum_valid,
            warnings=warnings,
        )

    def analyze(self, path: Path) -> ImageAttributes:
        return self._analyze(path, self._max_passes)

    def analyze_quick(self, path: Path) -> ImageAttributes:
        """Use only the first RGB/grayscale passes for secondary-side conflict checks."""
        limit = 2 if self._max_passes is None else min(max(0, self._max_passes), 2)
        return self._analyze(path, limit)
