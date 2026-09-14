from pathlib import Path
import inspect

from product_mapper.models import POSProduct, ProductImage
from product_mapper.pipeline import resolve_image_evidence
from product_mapper.vision.provider import ImageAttributes, NoOpVisionProvider, OCRLine


def product(pid: str, name: str, barcode: str) -> POSProduct:
    return POSProduct(
        product_id=pid,
        sku=f"SKU-{pid}",
        barcode=barcode,
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


class FixedProvider:
    def __init__(self, attributes: ImageAttributes):
        self.attributes = attributes
        self.calls = 0

    def analyze(self, image_path: Path) -> ImageAttributes:
        self.calls += 1
        return self.attributes


def test_valid_unique_gtin_is_primary_identity_and_auto_matches():
    target = product("1", "Coconut Milk 400ml", "4006381333931")
    barcode_reader = FixedProvider(ImageAttributes(
        barcode="4006381333931",
        barcode_candidates=["4006381333931", "4006381333931"],
        barcode_checksum_valid=True,
    ))

    result = resolve_image_evidence(
        image("totally unrelated filename"),
        [target],
        barcode_reader,
        NoOpVisionProvider(),
    )

    assert result.status == "AUTO_MATCHED"
    assert result.match_method == "exact_barcode"
    assert result.candidate.product.product_id == "1"


def test_invalid_gtin_blocks_filename_auto_match_and_requires_review():
    target = product("1", "Sesame Oil 500ml", "4006381333931")
    barcode_reader = FixedProvider(ImageAttributes(
        barcode="4006381333932",
        barcode_candidates=["4006381333932"],
        barcode_checksum_valid=False,
    ))

    result = resolve_image_evidence(
        image("Sesame Oil 500ml"),
        [target],
        barcode_reader,
        NoOpVisionProvider(),
    )

    assert result.status == "NEED_REVIEW"
    assert result.match_method == "barcode_conflict"
    assert "INVALID_GTIN_CHECK_DIGIT" in result.reason


def test_missing_barcode_can_use_unique_deterministic_filename_without_fuzzy():
    target = product("1", "Aroy-D Coconut Milk 400 ml", "4006381333931")
    barcode_reader = FixedProvider(ImageAttributes())

    result = resolve_image_evidence(
        image("AROY D Coconut Milk 400ml"),
        [target],
        barcode_reader,
        NoOpVisionProvider(),
    )

    assert result.status == "AUTO_MATCHED"
    assert result.match_method == "deterministic_filename"


def test_ocr_only_identity_is_review_candidate_not_auto_match():
    apple = product("1", "Green Tea Apple 500ml", "4006381333931")
    lemon = product("2", "Green Tea Lemon 500ml", "036000291452")
    barcode_reader = FixedProvider(ImageAttributes())
    ocr = FixedProvider(ImageAttributes(ocr_lines=[
        OCRLine("GREEN TEA APPLE", 0.99),
        OCRLine("500 ML", 0.98),
    ]))

    result = resolve_image_evidence(
        image("camera 0001"),
        [apple, lemon],
        barcode_reader,
        ocr,
    )

    assert result.status == "NEED_REVIEW"
    assert result.match_method == "deterministic_ocr_review"
    assert [candidate.product.product_id for candidate in result.top_candidates] == ["1"]


def test_ocr_exact_identity_conflict_blocks_barcode_auto_match():
    apple = product("1", "Green Tea Apple 500ml", "4006381333931")
    lemon = product("2", "Green Tea Lemon 500ml", "036000291452")
    barcode_reader = FixedProvider(ImageAttributes(
        barcode="036000291452",
        barcode_candidates=["036000291452", "036000291452"],
        barcode_checksum_valid=True,
    ))
    ocr = FixedProvider(ImageAttributes(ocr_lines=[
        OCRLine("GREEN TEA APPLE", 0.99),
        OCRLine("500 ML", 0.98),
    ]))

    result = resolve_image_evidence(
        image("camera 0002"),
        [apple, lemon],
        barcode_reader,
        ocr,
    )

    assert result.status == "NEED_REVIEW"
    assert result.match_method == "barcode_ocr_conflict"
    assert result.reason == "OCR_IDENTITY_CONFLICT"


def test_production_pipeline_source_does_not_import_fuzzy_matcher():
    import product_mapper.pipeline as pipeline

    source = inspect.getsource(pipeline)
    assert "from .matching.matcher import match_image" not in source
    assert "CandidateGenerator" not in source
    assert 'match_method="fuzzy_name"' not in source
