from product_mapper.vision.barcode_utils import (
    choose_barcode_consensus,
    is_gtin_like,
    normalize_barcode,
    validate_gtin,
)


def test_normalize_barcode_preserves_leading_zeroes_and_removes_layout_noise():
    assert normalize_barcode(" 0360 0029 1452 ") == "036000291452"
    assert normalize_barcode("4006-3813-3393-1") == "4006381333931"


def test_validate_gtin_accepts_standard_lengths_and_check_digits():
    assert validate_gtin("12345670") is True       # GTIN-8
    assert validate_gtin("036000291452") is True   # UPC-A / GTIN-12
    assert validate_gtin("4006381333931") is True  # EAN-13 / GTIN-13
    assert validate_gtin("10012345678902") is True # GTIN-14


def test_validate_gtin_rejects_wrong_check_digit_and_non_gtin_value():
    assert validate_gtin("4006381333932") is False
    assert validate_gtin("SKU-001") is False
    assert is_gtin_like("4006381333932") is True
    assert is_gtin_like("SKU-001") is False


def test_choose_barcode_consensus_requires_unique_winner():
    assert choose_barcode_consensus([
        "4006381333931",
        "4006381333931",
        "036000291452",
    ]) == "4006381333931"

    assert choose_barcode_consensus([
        "4006381333931",
        "036000291452",
    ]) is None


def test_choose_barcode_consensus_ignores_blank_values_and_normalizes():
    assert choose_barcode_consensus(["", " 4006 3813 3393 1 ", None]) == "4006381333931"
