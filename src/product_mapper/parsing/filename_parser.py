import re
from pathlib import Path

from ..models import ProductImage
from .attributes import parse_packaging
from .text_normalizer import normalize_text

_ID = re.compile(r"^\d{3,}[A-Za-z]{0,3}$")
_CAPTURE_SIDE = re.compile(r"^(?P<capture>.+?)[_-](?P<side>front|back)$", re.I)


def _clean_product_name(raw: str) -> str:
    tokens = raw.split("_")
    if tokens and re.match(r"^(\d{1,3}|[a-z0-9]{1,4}vp|[a-z0-9]{1,4}mp)$", tokens[0], re.I):
        tokens = tokens[1:]
    return "_".join(tokens)


def _capture_filename(path: Path) -> ProductImage | None:
    match = _CAPTURE_SIDE.fullmatch(path.stem)
    if not match:
        return None
    capture_id = match.group("capture").strip()
    side = match.group("side").casefold()
    if not capture_id:
        return None
    return ProductImage(
        path=path,
        filename=path.name,
        source=path.parent.name.casefold() or "capture",
        source_product_id=capture_id,
        raw_name="",
        normalized_name="",
        packaging=parse_packaging(""),
        capture_id=capture_id,
        image_side=side,
    )


def parse_filename(path: Path) -> ProductImage:
    """Parse legacy supplier names while keeping every valid image account-able.

    Legacy names still expose supplier/source/name evidence. New camera captures such
    as ``000123_front.jpg`` / ``000123_back.jpg`` share a capture id but deliberately
    do not invent a product name. Any other valid image falls back to its stem instead
    of being discarded solely because the filename does not match a supplier pattern.
    """
    capture = _capture_filename(path)
    if capture is not None:
        return capture

    parts = path.stem.split("_")
    indexes = [i for i, part in enumerate(parts) if 0 < i < len(parts) - 1 and _ID.fullmatch(part)]
    if indexes:
        index = indexes[0]
        raw = "_".join(parts[index + 1 :])
        cleaned_raw = _clean_product_name(raw)
        return ProductImage(
            path=path,
            filename=path.name,
            source="_".join(parts[:index]).casefold(),
            source_product_id=parts[index],
            raw_name=cleaned_raw,
            normalized_name=normalize_text(cleaned_raw),
            packaging=parse_packaging(raw),
        )

    raw = path.stem.strip()
    return ProductImage(
        path=path,
        filename=path.name,
        source=path.parent.name.casefold() or None,
        raw_name=raw,
        normalized_name=normalize_text(raw),
        packaging=parse_packaging(raw),
    )
