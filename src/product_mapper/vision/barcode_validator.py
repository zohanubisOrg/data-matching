from __future__ import annotations

import re


def validate_ean_upc_checksum(code: str) -> bool:
    """Validates the standard Modulo-10 checksum for EAN-13, UPC-A (12 digits), or EAN-8."""
    digits_only = re.sub(r"[^\d]", "", str(code))
    length = len(digits_only)

    if length not in (8, 12, 13, 14):
        return False

    digits = [int(c) for c in digits_only]
    check_digit = digits[-1]
    data_digits = digits[:-1]

    # Calculate checksum from right to left
    # The weight alternates between 3 and 1 starting from the digit immediately before the check digit
    total = 0
    weight = 3
    for d in reversed(data_digits):
        total += d * weight
        weight = 1 if weight == 3 else 3

    calc_check = (10 - (total % 10)) % 10
    return calc_check == check_digit


def get_barcode_lookup_variants(code: str) -> list[str]:
    """Generates standard canonical lookup variants (e.g. 12-digit UPC <-> 13-digit EAN)."""
    digits = re.sub(r"[^\d]", "", str(code))
    if not digits:
        return []

    variants = [digits]
    # If 12 digits (UPC-A), 13-digit EAN-13 equivalent starts with '0'
    if len(digits) == 12:
        variants.append("0" + digits)
    # If 13 digits starting with '0', 12-digit UPC equivalent removes leading '0'
    elif len(digits) == 13 and digits.startswith("0"):
        variants.append(digits[1:])

    return list(dict.fromkeys(variants))
