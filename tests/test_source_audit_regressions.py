from pathlib import Path

from PIL import Image

from product_mapper.models import POSProduct, ProductImage
from product_mapper.parsing.filename_parser import parse_filename
from product_mapper.pipeline import build_barcode_index, resolve_capture_evidence
from product_mapper.vision.barcode_reader import BarcodeReader
from product_mapper.vision.provider import ImageAttributes, NoOpVisionProvider, OCRLine


VALID_EAN13 = "4006381333931"
VALID_GTIN14_EQUIVALENT = "04006381333931"
INVALID_EAN13 = "4006381333932"


def product(pid: str = "1", barcode: str = VALID_EAN13) -> POSProduct:
    return POSProduct(
        product_id=pid,
        sku=f"SKU-{pid}",
        barcode=barcode,
        product_name="Green Tea Apple 500ml",
        official_name="Green Tea Apple 500 ml",
    )


def image(path: Path, capture_id: str | None = None, side: str | None = None) -> ProductImage:
    return ProductImage(
        path=path,
        filename=path.name,
        raw_name="",
        normalized_name="",
        capture_id=capture_id,
        image_side=side,
    )


def test_front_back_capture_filename_is_valid_without_supplier_name(tmp_path):
    path = tmp_path / "000123_front.jpg"
    Image.new("RGB", (16, 16), "white").save(path)

    parsed = parse_filename(path)

    assert parsed.capture_id == "000123"
    assert parsed.image_side == "front"
    assert parsed.raw_name == ""
    assert parsed.source_product_id == "000123"


def test_front_back_supplier_filename_keeps_product_name_evidence(tmp_path):
    path = tmp_path / "heuschen_11108_pineapple_in_heavy_syrup_front.jpg"
    Image.new("RGB", (16, 16), "white").save(path)

    parsed = parse_filename(path)

    assert parsed.capture_id == "heuschen_11108_pineapple_in_heavy_syrup"
    assert parsed.image_side == "front"
    assert parsed.source == "heuschen"
    assert parsed.source_product_id == "11108"
    assert parsed.raw_name == "pineapple_in_heavy_syrup"


def test_generic_valid_image_filename_is_not_rejected(tmp_path):
    path = tmp_path / "random-camera-photo.jpg"
    Image.new("RGB", (16, 16), "white").save(path)

    parsed = parse_filename(path)

    assert parsed.filename == path.name
    assert parsed.raw_name == "random-camera-photo"
    assert parsed.capture_id is None


def test_barcode_reader_prefers_checksum_valid_gtin_over_more_frequent_invalid_decode(tmp_path):
    path = tmp_path / "barcode.jpg"
    Image.new("RGB", (64, 64), "white").save(path)
    passes = iter([
        [INVALID_EAN13],
        [INVALID_EAN13],
        [VALID_EAN13],
        [INVALID_EAN13],
        [VALID_EAN13],
    ])

    reader = BarcodeReader(decoder=lambda _: next(passes, []), max_passes=5)
    evidence = reader.analyze(path)

    assert evidence.barcode == VALID_EAN13
    assert evidence.barcode_checksum_valid is True


def test_front_and_back_share_barcode_identity_when_only_back_decodes(tmp_path):
    front_path = tmp_path / "000123_front.jpg"
    back_path = tmp_path / "000123_back.jpg"
    Image.new("RGB", (16, 16), "white").save(front_path)
    Image.new("RGB", (16, 16), "white").save(back_path)
    front = image(front_path, "000123", "front")
    back = image(back_path, "000123", "back")
    pos = product()

    class Reader:
        def analyze(self, path: Path) -> ImageAttributes:
            if path.name.endswith("_back.jpg"):
                return ImageAttributes(
                    barcode=VALID_EAN13,
                    barcode_candidates=[VALID_EAN13],
                    barcode_checksum_valid=True,
                )
            return ImageAttributes()

    results = resolve_capture_evidence(
        [front, back],
        [pos],
        Reader(),
        NoOpVisionProvider(),
        barcode_index=build_barcode_index([pos]),
    )

    assert len(results) == 2
    assert {result.status for result in results} == {"AUTO_MATCHED"}
    assert {result.candidate.product.product_id for result in results if result.candidate} == {"1"}
    assert {result.match_method for result in results} == {"exact_barcode"}


def test_barcode_index_preserves_duplicate_pos_identity_for_review():
    first = product("1")
    second = product("2")

    index = build_barcode_index([first, second])

    assert [item.product_id for item in index[VALID_EAN13]] == ["1", "2"]


def test_duplicate_pos_rows_with_same_product_id_are_not_collapsed(tmp_path):
    path = tmp_path / "barcode.jpg"
    Image.new("RGB", (16, 16), "white").save(path)
    first = product("1")
    second = first.model_copy()

    class Reader:
        def analyze(self, _: Path) -> ImageAttributes:
            return ImageAttributes(
                barcode=VALID_EAN13,
                barcode_candidates=[VALID_EAN13],
                barcode_checksum_valid=True,
            )

    result = resolve_capture_evidence(
        [image(path)],
        [first, second],
        Reader(),
        NoOpVisionProvider(),
        barcode_index=build_barcode_index([first, second]),
    )[0]

    assert result.status == "NEED_REVIEW"
    assert result.reason == "DUPLICATE_OR_EQUIVALENT_POS_BARCODE"
    assert len(result.top_candidates) == 2


def test_checksum_valid_gtin13_matches_equivalent_zero_padded_gtin14(tmp_path):
    path = tmp_path / "barcode.jpg"
    Image.new("RGB", (16, 16), "white").save(path)
    pos = product(barcode=VALID_GTIN14_EQUIVALENT)

    class Reader:
        def analyze(self, _: Path) -> ImageAttributes:
            return ImageAttributes(
                barcode=VALID_EAN13,
                barcode_candidates=[VALID_EAN13],
                barcode_checksum_valid=True,
            )

    result = resolve_capture_evidence(
        [image(path)],
        [pos],
        Reader(),
        NoOpVisionProvider(),
        barcode_index=build_barcode_index([pos]),
    )[0]

    assert result.status == "AUTO_MATCHED"
    assert result.candidate is not None
    assert result.candidate.product.barcode == VALID_GTIN14_EQUIVALENT


def test_back_ocr_is_fallback_only_when_front_ocr_has_no_text(tmp_path):
    front_path = tmp_path / "000123_front.jpg"
    back_path = tmp_path / "000123_back.jpg"
    Image.new("RGB", (16, 16), "white").save(front_path)
    Image.new("RGB", (16, 16), "white").save(back_path)
    front = image(front_path, "000123", "front")
    back = image(back_path, "000123", "back")
    pos = product()

    class EmptyBarcodeReader:
        def analyze(self, _: Path) -> ImageAttributes:
            return ImageAttributes()

    class OCRProvider:
        def __init__(self):
            self.calls: list[str] = []

        def analyze(self, path: Path) -> ImageAttributes:
            self.calls.append(path.name)
            if path.name.endswith("_front.jpg"):
                return ImageAttributes()
            return ImageAttributes(ocr_lines=[
                OCRLine("GREEN TEA APPLE", 0.99),
                OCRLine("500 ML", 0.98),
            ])

    ocr = OCRProvider()
    results = resolve_capture_evidence(
        [front, back],
        [pos],
        EmptyBarcodeReader(),
        ocr,
        barcode_index=build_barcode_index([pos]),
    )

    assert {result.status for result in results} == {"NEED_REVIEW"}
    assert [candidate.product.product_id for candidate in results[0].top_candidates] == ["1"]
    assert ocr.calls == ["000123_front.jpg", "000123_back.jpg"]
