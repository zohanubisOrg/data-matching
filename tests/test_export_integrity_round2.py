from pathlib import Path

from product_mapper.models import MatchCandidate, MatchResult, POSProduct, ProductImage
from product_mapper.reporting import image_exporter


def product(pid: str = "1", barcode: str = "4006381333931") -> POSProduct:
    return POSProduct(
        product_id=pid,
        sku=f"SKU-{pid}",
        barcode=barcode,
        product_name="Green Tea Apple",
        official_name="Green Tea Apple",
    )


def result(path: Path, p: POSProduct) -> MatchResult:
    candidate = MatchCandidate(product=p, score=1.0)
    return MatchResult(
        image=ProductImage(path=path, filename=path.name),
        status="AUTO_MATCHED",
        candidate=candidate,
        top_candidates=[candidate],
        confidence=1.0,
        match_method="exact_barcode",
    )


def test_failed_matched_image_export_is_not_reported_as_delivered_match(tmp_path, monkeypatch):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    item = result(source, product())

    monkeypatch.setattr(image_exporter, "_export_matched_jpeg", lambda *args, **kwargs: False)
    summary = image_exporter.export_standard_deliverables([item], tmp_path / "out", total_pos_count=1)

    assert item.status == "ERROR"
    assert summary["matched_count"] == 0
    assert summary["error_count"] == 1
    csv_text = (tmp_path / "out" / "result.csv").read_text(encoding="utf-8-sig")
    assert "MATCHED" not in csv_text
    assert "ERROR" in csv_text


def test_matched_pos_count_uses_pos_identity_not_unique_barcode(tmp_path, monkeypatch):
    source1 = tmp_path / "a.jpg"
    source2 = tmp_path / "b.jpg"
    source1.write_bytes(b"a")
    source2.write_bytes(b"b")
    first = product("1")
    second = product("2")

    monkeypatch.setattr(image_exporter, "_export_matched_jpeg", lambda *args, **kwargs: True)
    summary = image_exporter.export_standard_deliverables(
        [result(source1, first), result(source2, second)],
        tmp_path / "out",
        total_pos_count=2,
    )

    assert summary["matched_pos_count"] == 2
