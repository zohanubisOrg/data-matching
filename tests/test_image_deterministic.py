from pathlib import Path

from product_mapper.models import POSProduct, ProductImage
from product_mapper.matching.image_deterministic import (
    find_ocr_review_candidates,
    match_filename_deterministic,
    ocr_conflict_reason,
    parse_ocr_identity,
)
from product_mapper.vision.provider import OCRLine


def product(pid: str, name: str, barcode: str | None = None) -> POSProduct:
    return POSProduct(
        product_id=pid,
        sku=f"SKU-{pid}",
        barcode=barcode or f"40063813339{pid}",
        product_name=name,
        official_name=name,
    )


def image(name: str) -> ProductImage:
    return ProductImage(
        path=Path(f"/tmp/{name}.jpg"),
        filename=f"{name}.jpg",
        source="test",
        source_product_id="10001",
        raw_name=name,
        normalized_name=name.casefold(),
    )


def test_filename_match_uses_existing_no_fuzzy_rules_and_requires_unique_pos_identity():
    result = match_filename_deterministic(
        image("AROY D Coconut Milk 400ml"),
        [product("1", "Aroy-D Coconut Milk 400 ml")],
    )

    assert result is not None
    assert result.status == "AUTO_MATCHED"
    assert result.match_method == "deterministic_filename"
    assert result.candidate.product.product_id == "1"


def test_filename_match_downgrades_ambiguous_duplicate_pos_identity_to_review():
    result = match_filename_deterministic(
        image("Sesame Oil 500 ml"),
        [product("1", "Sesame Oil 500ml"), product("2", "Sesame Oil 500 ml")],
    )

    assert result is not None
    assert result.status == "NEED_REVIEW"
    assert result.candidate is None
    assert len(result.top_candidates) == 2


def test_strict_image_path_does_not_auto_match_safe_subset_name():
    result = match_filename_deterministic(
        image("Aloe Vera Drink Lychee 500ml"),
        [product("1", "Aloe Vera Drink")],
    )

    assert result is not None
    assert result.status == "NEED_REVIEW"
    assert result.candidate is None
    assert result.top_candidates[0].product.product_id == "1"


def test_core_name_match_with_missing_size_is_review_not_auto_match():
    result = match_filename_deterministic(
        image("Sesame Oil 500ml"),
        [product("1", "Sesame Oil")],
    )

    assert result is not None
    assert result.status == "NEED_REVIEW"
    assert result.candidate is None


def test_ocr_parser_and_candidates_use_exact_tokens_not_similarity():
    lines = [OCRLine("GREEN TEA APPLE", 0.99), OCRLine("500 ML", 0.97)]
    products = [
        product("1", "Green Tea Apple 500ml"),
        product("2", "Green Tea Lemon 500ml"),
    ]

    identity = parse_ocr_identity(lines)
    candidates = find_ocr_review_candidates(lines, products)

    assert identity["item_size"] == ("volume", 500.0)
    assert [candidate.product.product_id for candidate in candidates] == ["1"]
    assert candidates[0].score == 1.0


def test_ocr_size_conflict_blocks_candidate():
    lines = [OCRLine("COCONUT MILK", 0.99), OCRLine("400 ML", 0.98)]
    products = [product("1", "Coconut Milk 1 L")]

    assert find_ocr_review_candidates(lines, products) == []


def test_ocr_unique_exact_identity_can_conflict_with_barcode_selected_product():
    lines = [OCRLine("GREEN TEA APPLE", 0.99), OCRLine("500 ML", 0.97)]
    apple = product("1", "Green Tea Apple 500ml")
    lemon = product("2", "Green Tea Lemon 500ml")

    assert ocr_conflict_reason(lines, lemon, [apple, lemon]) == "OCR_IDENTITY_CONFLICT"
    assert ocr_conflict_reason(lines, apple, [apple, lemon]) is None


def test_ocr_name_without_required_size_does_not_overrule_valid_barcode():
    lines = [OCRLine("GREEN TEA APPLE", 0.99)]
    apple = product("1", "Green Tea Apple 500ml")
    lemon = product("2", "Green Tea Lemon 500ml")

    assert ocr_conflict_reason(lines, lemon, [apple, lemon]) is None


def test_ocr_unknown_confidence_never_creates_hard_barcode_conflict():
    lines = [OCRLine("GREEN TEA APPLE", 0.0), OCRLine("500 ML", 0.0)]
    apple = product("1", "Green Tea Apple 500ml")
    lemon = product("2", "Green Tea Lemon 500ml")

    assert ocr_conflict_reason(lines, lemon, [apple, lemon]) is None
