from PIL import Image

from product_mapper.models import MatchCandidate, MatchResult, POSProduct, ProductImage
from product_mapper.reporting.image_exporter import export_standard_deliverables


def test_empty_export_is_reconciled_without_division_by_zero(tmp_path):
    summary = export_standard_deliverables([], tmp_path, total_pos_count=0)

    assert summary["total_images"] == 0
    report = (tmp_path / "reconciliation_report.txt").read_text(encoding="utf-8")
    assert "Reconciled Check:" in report
    assert "NOT MEASURED" in report
    assert "Final Matched Accuracy:             100%" not in report


def test_invalid_input_files_are_included_in_accounting(tmp_path):
    summary = export_standard_deliverables(
        [],
        tmp_path,
        total_pos_count=0,
        invalid_input_count=2,
    )

    assert summary["invalid_input_count"] == 2
    assert summary["total_input_images"] == 2
    report = (tmp_path / "reconciliation_report.txt").read_text(encoding="utf-8")
    assert "Invalid input files:               2" in report
    assert "Reconciled Check:                 2 / 2 [PASS]" in report


def test_reconciliation_report_does_not_claim_copy_or_accuracy_pass_without_measurement(tmp_path):
    export_standard_deliverables([], tmp_path, total_pos_count=10)

    report = (tmp_path / "reconciliation_report.txt").read_text(encoding="utf-8")
    assert "Gold-dataset accuracy" in report
    assert "NOT MEASURED" in report


def test_matched_non_jpeg_source_is_exported_as_canonical_jpg(tmp_path):
    source = tmp_path / "front.png"
    Image.new("RGBA", (20, 20), (255, 255, 255, 128)).save(source)
    product = POSProduct(
        product_id="1",
        sku="SKU-1",
        barcode="4006381333931",
        product_name="Green Tea Apple 500ml",
        official_name="Green Tea Apple 500ml",
    )
    image = ProductImage(path=source, filename=source.name)
    candidate = MatchCandidate(product=product, score=1.0)
    result = MatchResult(
        image=image,
        status="AUTO_MATCHED",
        candidate=candidate,
        top_candidates=[candidate],
        confidence=1.0,
        match_method="exact_barcode",
    )

    export_standard_deliverables([result], tmp_path / "output", total_pos_count=1)

    exported = tmp_path / "output" / "matched-images" / "4006381333931.jpg"
    assert exported.exists()
    with Image.open(exported) as final_image:
        assert final_image.format == "JPEG"
