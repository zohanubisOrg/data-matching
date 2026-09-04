import re
from pathlib import Path

from ..models import ProductImage
from .attributes import parse_packaging
from .text_normalizer import normalize_text

_ID = re.compile(r"^\d{3,}[A-Za-z]{0,3}$")


def _clean_product_name(raw: str) -> str:
    tokens = raw.split("_")
    if tokens and re.match(r"^(\d{1,3}|[a-z0-9]{1,4}vp|[a-z0-9]{1,4}mp)$", tokens[0], re.I):
        tokens = tokens[1:]
    return "_".join(tokens)


def parse_filename(path: Path) -> ProductImage:
    parts = path.stem.split("_")
    indexes = [i for i, part in enumerate(parts) if 0 < i < len(parts) - 1 and _ID.fullmatch(part)]
    if not indexes:
        raise ValueError(f"no safe source product id in filename: {path.name}")
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

