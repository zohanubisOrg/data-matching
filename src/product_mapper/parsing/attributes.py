import re

from ..models import Packaging
from .text_normalizer import number

_PACK = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)*\s*)(ml|cl|l|mg|g|kg|oz)\b", re.I)
_UNIT = {"ml": "ml", "cl": "ml", "l": "ml", "mg": "g", "g": "g", "kg": "g", "oz": "g"}
_MULT = {"ml": 1, "cl": 10, "l": 1000, "mg": 0.001, "g": 1, "kg": 1000, "oz": 28.349523125}


def parse_packaging(value: str) -> Packaging:
    match = _PACK.search(value.replace("_", " "))
    if not match:
        return Packaging(raw="")
    amounts = [number(x) for x in re.split(r"\s*[x×]\s*", match.group(1).strip()) if x]
    unit = match.group(2).casefold()
    canonical = _UNIT[unit]
    factor = _MULT[unit] / _MULT[canonical]
    return Packaging(levels=[(amounts[0] * factor, canonical), *[(x, "x") for x in amounts[1:]]], raw=match.group(0))


def packaging_conflict(left: Packaging, right: Packaging) -> str | None:
    if not left.levels or not right.levels:
        return None
    if left.levels[0][1] == right.levels[0][1] and left.levels[0][0] != right.levels[0][0]:
        return f"size conflict: {left.raw} vs {right.raw}"
    if len(left.levels) != len(right.levels):
        return f"packaging conflict: {left.raw} vs {right.raw}"
    return None

