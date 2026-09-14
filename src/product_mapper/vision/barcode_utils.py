from __future__ import annotations

from collections import Counter
import re
from typing import Iterable


_GTIN_LENGTHS = {8, 12, 13, 14}
_SEPARATOR_RE = re.compile(r"[\s-]+")


def normalize_barcode(value: object) -> str:
    """Normalize presentation noise without inventing or truncating barcode data."""
    if value is None:
        return ""
    return _SEPARATOR_RE.sub("", str(value).strip())


def is_gtin_like(value: str) -> bool:
    normalized = normalize_barcode(value)
    return normalized.isdigit() and len(normalized) in _GTIN_LENGTHS


def validate_gtin(value: str) -> bool:
    """Validate GTIN-8, UPC-A/GTIN-12, EAN/GTIN-13 and GTIN-14 check digits."""
    normalized = normalize_barcode(value)
    if not is_gtin_like(normalized):
        return False

    digits = [int(char) for char in normalized]
    body, expected_check = digits[:-1], digits[-1]
    weighted_sum = 0
    for index, digit in enumerate(reversed(body)):
        weighted_sum += digit * (3 if index % 2 == 0 else 1)
    calculated_check = (10 - weighted_sum % 10) % 10
    return calculated_check == expected_check


def choose_barcode_consensus(values: Iterable[object]) -> str | None:
    """Return the unique most frequently decoded normalized value, otherwise None."""
    normalized = [normalize_barcode(value) for value in values]
    normalized = [value for value in normalized if value]
    if not normalized:
        return None

    counts = Counter(normalized)
    top_count = max(counts.values())
    winners = [value for value, count in counts.items() if count == top_count]
    return winners[0] if len(winners) == 1 else None
