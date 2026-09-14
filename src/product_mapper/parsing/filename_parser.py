import re
from pathlib import Path

from ..models import ProductImage
from .attributes import parse_packaging
from .text_normalizer import normalize_text

_ID = re.compile(r"^\d{3,}[A-Za-z]{0,3}$")
_CAPTURE_SUFFIX = re.compile(r"^(?P<capture>.+?)[_-](?P<side>front|back)$", re.I)
_CAPTURE_PREFIX = re.compile(r"^(?P<side>front|back)[_-](?P<capture>.+)$", re.I)


def _clean_product_name(raw: str) -> str:
    tokens = raw.split("_")
    if tokens and re.match(r"^(\d{1,3}|[a-z0-9]{1,4}vp|[a-z0-9]{1,4}mp)$", tokens[0], re.I):
        tokens = tokens[1:]
    return "_".join(tokens)


def _capture_parts(stem: str) -> tuple[str | None, str | None]:
    match = _CAPTURE_SUFFIX.fullmatch(stem) or _CAPTURE_PREFIX.fullmatch(stem)
    if not match:
        return None, None
    capture_id = match.group("capture").strip("_-")
    side = match.group("side").casefold()
    return (capture_id or None), side


def _legacy_parts(stem: str) -> tuple[str, str, str] | None:
    parts = stem.split("_")
    indexes = [i for i, part in enumerate(parts) if 0 < i < len(parts) - 1 and _ID.fullmatch(part)]
    if not indexes:
        return None
    index = indexes[0]
    raw = "_".join(parts[index + 1 :])
    return "_".join(parts[:index]).casefold(), parts[index], raw


def parse_filename(path: Path) -> ProductImage:
    """Parse legacy supplier names and modern front/back camera captures safely.

    A capture suffix/prefix is metadata, not product-name text. If the capture stem is
    also a legacy supplier filename, its supplier id and product-name evidence are
    preserved. Generic valid images are never discarded merely for naming format.
    """
    capture_id, image_side = _capture_parts(path.stem)
    evidence_stem = capture_id if capture_id is not None else path.stem
    legacy = _legacy_parts(evidence_stem)

    if legacy is not None:
        source, source_product_id, raw = legacy
        cleaned_raw = _clean_product_name(raw)
        return ProductImage(
            path=path,
            filename=path.name,
            source=source,
            source_product_id=source_product_id,
            raw_name=cleaned_raw,
            normalized_name=normalize_text(cleaned_raw),
            packaging=parse_packaging(raw),
            capture_id=capture_id,
            image_side=image_side,
        )

    if capture_id is not None:
        return ProductImage(
            path=path,
            filename=path.name,
            source=path.parent.name.casefold() or "capture",
            source_product_id=capture_id,
            raw_name="",
            normalized_name="",
            packaging=parse_packaging(""),
            capture_id=capture_id,
            image_side=image_side,
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
