from product_mapper.reporting.image_exporter import export_standard_deliverables


def test_empty_export_is_reconciled_without_division_by_zero(tmp_path):
    summary = export_standard_deliverables([], tmp_path, total_pos_count=0)

    assert summary["total_images"] == 0
    report = (tmp_path / "reconciliation_report.txt").read_text(encoding="utf-8")
    assert "Reconciled Check:" in report
    assert "NOT MEASURED" in report
    assert "Final Matched Accuracy:             100%" not in report


def test_reconciliation_report_does_not_claim_copy_or_accuracy_pass_without_measurement(tmp_path):
    export_standard_deliverables([], tmp_path, total_pos_count=10)

    report = (tmp_path / "reconciliation_report.txt").read_text(encoding="utf-8")
    assert "Gold-dataset accuracy" in report
    assert "NOT MEASURED" in report
