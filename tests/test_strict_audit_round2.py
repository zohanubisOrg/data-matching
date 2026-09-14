from pathlib import Path

from PIL import Image

from product_mapper.ingestion.capture_group import group_product_images
from product_mapper.matching.image_deterministic import ocr_conflict_reason
from product_mapper.matching.product_index import ProductEvidenceIndex
from product_mapper.models import MatchCandidate, MatchResult, POSProduct, ProductImage
from product_mapper.pipeline import build_barcode_index, resolve_capture_evidence
from product_mapper.reporting.html_report import write_html
from product_mapper.vision.provider import ImageAttributes, OCRLine


EAN_A = "4006381333931"
EAN_B = "036000291452"


def product(pid: str, name: str, barcode: str, sku: str | None = None) -> POSProduct:
    return POSProduct(
        product_id=pid,
        sku=sku or f"SKU-{pid}",
        barcode=barcode,
        product_name=name,
        official_name=name,
    )


def image(path: Path, capture_id: str | None = None, side: str | None = None) -> ProductImage:
    return ProductImage(
        path=path,
        filename=path.name,
        capture_id=capture_id,
        image_side=side,
        raw_name="",
        normalized_name="",
    )


def test_unique_front_back_capture_can_group_across_front_back_folders(tmp_path):
    front_dir = tmp_path / "front"
    back_dir = tmp_path / "back"
    front_dir.mkdir()
    back_dir.mkdir()
    front = image(front_dir / "000123_front.jpg", "000123", "front")
    back = image(back_dir / "000123_back.jpg", "000123", "back")

    groups = group_product_images([front, back])

    assert len(groups) == 1
    assert {item.image_side for item in groups[0]} == {"front", "back"}


def test_duplicate_capture_id_pairs_in_multiple_folders_do_not_cross_pair(tmp_path):
    images = []
    for pack in ("pack1", "pack2"):
        folder = tmp_path / pack
        folder.mkdir()
        images.extend([
            image(folder / "000123_front.jpg", "000123", "front"),
            image(folder / "000123_back.jpg", "000123", "back"),
        ])

    groups = group_product_images(images)

    assert len(groups) == 2
    assert all(len(group) == 2 for group in groups)
    assert all(len({item.path.parent for item in group}) == 1 for group in groups)


def test_front_back_different_valid_gtins_block_auto_match(tmp_path):
    front_path = tmp_path / "000123_front.jpg"
    back_path = tmp_path / "000123_back.jpg"
    Image.new("RGB", (16, 16), "white").save(front_path)
    Image.new("RGB", (16, 16), "white").save(back_path)
    front = image(front_path, "000123", "front")
    back = image(back_path, "000123", "back")
    products = [
        product("1", "Green Tea Apple 500ml", EAN_A),
        product("2", "Green Tea Lemon 500ml", EAN_B),
    ]

    class Reader:
        def analyze(self, path: Path) -> ImageAttributes:
            barcode = EAN_A if path.name.endswith("_back.jpg") else EAN_B
            return ImageAttributes(
                barcode=barcode,
                barcode_candidates=[barcode],
                barcode_checksum_valid=True,
            )

    results = resolve_capture_evidence(
        [front, back],
        products,
        Reader(),
        barcode_index=build_barcode_index(products),
    )

    assert {result.status for result in results} == {"NEED_REVIEW"}
    assert {result.reason for result in results} == {"MULTIPLE_VALID_GTIN_VALUES"}


def test_barcode_verification_does_not_fallback_to_back_label_ocr(tmp_path):
    front_path = tmp_path / "000123_front.jpg"
    back_path = tmp_path / "000123_back.jpg"
    Image.new("RGB", (16, 16), "white").save(front_path)
    Image.new("RGB", (16, 16), "white").save(back_path)
    front = image(front_path, "000123", "front")
    back = image(back_path, "000123", "back")
    target = product("1", "Green Tea Apple 500ml", EAN_A)

    class Reader:
        def analyze(self, _: Path) -> ImageAttributes:
            return ImageAttributes(
                barcode=EAN_A,
                barcode_candidates=[EAN_A],
                barcode_checksum_valid=True,
            )

    class OCR:
        def __init__(self):
            self.calls = []

        def analyze(self, path: Path) -> ImageAttributes:
            self.calls.append(path.name)
            if path.name.endswith("_back.jpg"):
                return ImageAttributes(ocr_lines=[OCRLine("GREEN TEA LEMON 500 ML", 0.99)])
            return ImageAttributes()

    ocr = OCR()
    result = resolve_capture_evidence(
        [front, back],
        [target],
        Reader(),
        ocr,
        barcode_index=build_barcode_index([target]),
    )[0]

    assert result.status == "AUTO_MATCHED"
    assert ocr.calls == ["000123_front.jpg"]


def test_ocr_conflict_compares_pos_row_identity_not_only_product_id():
    selected = product("1", "Green Tea Lemon 500ml", EAN_A, sku="SKU-LEMON")
    different_row_same_id = product("1", "Green Tea Apple 500ml", EAN_B, sku="SKU-APPLE")
    lines = [OCRLine("GREEN TEA APPLE 500 ML", 0.99)]
    products = [selected, different_row_same_id]

    assert ocr_conflict_reason(
        lines,
        selected,
        products,
        ProductEvidenceIndex(products),
    ) == "OCR_IDENTITY_CONFLICT"


def test_product_index_can_prune_ocr_rows_by_exact_token_overlap():
    products = [
        product("1", "Green Tea Apple 500ml", EAN_A),
        product("2", "Sesame Oil 500ml", EAN_B),
        product("3", "Coconut Jam 340g", "8938505974194"),
    ]
    index = ProductEvidenceIndex(products)

    rows = index.candidate_row_indexes({"green", "tea", "apple", "500"}, min_overlap=2)

    assert rows == {0}


def test_html_report_uses_evidence_language_not_fuzzy_percentages(tmp_path):
    path = tmp_path / "product.jpg"
    Image.new("RGB", (16, 16), "white").save(path)
    p = product("1", "Green Tea Apple 500ml", EAN_A)
    candidate = MatchCandidate(product=p, score=1.0)
    result = MatchResult(
        image=image(path),
        status="NEED_REVIEW",
        top_candidates=[candidate],
        match_method="deterministic_ocr_review",
        reason="exact OCR evidence produced deterministic review candidates",
    )

    write_html([result], tmp_path)
    html = (tmp_path / "review_report.html").read_text(encoding="utf-8").casefold()

    assert "tương đồng" not in html
    assert "ngưỡng" not in html
    assert "khớp tự động 100%" not in html
    assert "deterministic" in html or "bằng chứng" in html
