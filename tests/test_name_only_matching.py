from product_mapper.models import POSProduct, SupplierProduct
from product_mapper.matching.name_only import match_import_names, summarize_name_matches


def p(pid, name, official="", printer=""):
    return POSProduct(product_id=str(pid), sku=f"SKU-{pid}", barcode=f"BC-{pid}", product_name=name, official_name=official, printer_name=printer)


def s(name, supplier="EUR", sheet="EUR"):
    return SupplierProduct(name=name, supplier=supplier, sheet=sheet)


def test_exact_normalized_name_auto_matches():
    rows = match_import_names([p(1, "Aroy-D Coconut Milk 400ml")], [s("Aroy D Coconut Milk 400ml")])
    assert rows[0]["status"] == "AUTO_MATCHED"
    assert rows[0]["score"] == 1.0
    assert rows[0]["pos_product_id"] == "1"


def test_clear_fuzzy_name_auto_matches_without_image_or_barcode_scoring():
    rows = match_import_names(
        [p(1, "Nongshim Shin Ramyun Noodle 120g"), p(2, "Aroy-D Coconut Milk 400ml")],
        [s("Nongshim Shin Ramen 120 g")],
        auto_threshold=0.84,
    )
    assert rows[0]["status"] == "AUTO_MATCHED"
    assert rows[0]["pos_product_id"] == "1"
    assert rows[0]["match_method"] == "name_only"


def test_duplicate_exact_pos_names_are_review_not_auto():
    rows = match_import_names(
        [p(1, "Sesame Oil 500ml"), p(2, "Sesame Oil 500ml")],
        [s("Sesame Oil 500ml")],
    )
    assert rows[0]["status"] == "REVIEW"
    assert rows[0]["margin"] == 0.0


def test_unrelated_name_is_unmatched():
    rows = match_import_names(
        [p(1, "Coconut Milk 400ml"), p(2, "Sesame Oil 500ml")],
        [s("Purple Yam Fruit Spread Ube 340g")],
        review_threshold=0.72,
    )
    assert rows[0]["status"] == "UNMATCHED"


def test_summary_reports_auto_and_candidate_coverage_rates():
    rows = [
        {"status": "AUTO_MATCHED"},
        {"status": "AUTO_MATCHED"},
        {"status": "REVIEW"},
        {"status": "UNMATCHED"},
    ]
    summary = summarize_name_matches(rows)
    assert summary == {
        "total_import_rows": 4,
        "auto_matched": 2,
        "review": 1,
        "unmatched": 1,
        "auto_match_rate_pct": 50.0,
        "candidate_coverage_pct": 75.0,
    }


def test_write_name_match_outputs_creates_auditable_files(tmp_path):
    from product_mapper.matching.name_only import write_name_match_outputs
    rows = [{
        "sheet": "EUR", "supplier": "Supplier", "import_name": "Sesame Oil 500ml", "supplier_sku": "",
        "status": "AUTO_MATCHED", "score": 1.0, "top2_score": 0.4, "margin": 0.6,
        "match_method": "name_only", "pos_product_id": "1", "pos_sku": "SKU-1", "pos_barcode": "BC-1",
        "pos_product_name": "Sesame Oil 500ml", "pos_official_name": "", "pos_printer_name": "",
    }]
    summary = summarize_name_matches(rows)
    paths = write_name_match_outputs(rows, summary, tmp_path)
    assert paths["xlsx"].exists()
    assert paths["csv"].exists()
    assert paths["summary_json"].exists()
