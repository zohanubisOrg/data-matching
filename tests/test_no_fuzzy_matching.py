from product_mapper.models import POSProduct, SupplierProduct
from product_mapper.matching.no_fuzzy import match_import_names_no_fuzzy, summarize_no_fuzzy_matches


def p(pid, name, official="", printer=""):
    return POSProduct(
        product_id=str(pid), sku=f"SKU-{pid}", barcode=f"BC-{pid}",
        product_name=name, official_name=official, printer_name=printer,
    )


def s(name, supplier="EUR", sheet="EUR"):
    return SupplierProduct(name=name, supplier=supplier, sheet=sheet)


def test_exact_name_matches_after_basic_normalization():
    rows = match_import_names_no_fuzzy(
        [p(1, "Aroy-D Coconut Milk 500 ml")],
        [s("AROY D Coconut Milk 500ml")],
    )
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["match_method"] == "normalized_exact_name"
    assert rows[0]["pos_product_id"] == "1"


def test_official_name_can_match_exactly():
    rows = match_import_names_no_fuzzy(
        [p(1, "Coriander", official="Koriander")],
        [s("KORIANDER")],
    )
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["matched_field"] == "official_name"


def test_similar_but_not_exact_name_does_not_match():
    rows = match_import_names_no_fuzzy(
        [p(1, "Nongshim Shin Ramyun Noodle 120g")],
        [s("Nongshim Shin Ramen 120 g")],
    )
    assert rows[0]["status"] == "UNMATCHED"


def test_containment_is_not_a_match():
    rows = match_import_names_no_fuzzy(
        [p(1, "Chili Mango")],
        [s("MANGO")],
    )
    assert rows[0]["status"] == "UNMATCHED"


def test_duplicate_exact_pos_names_are_name_matched_but_identity_ambiguous():
    rows = match_import_names_no_fuzzy(
        [p(1, "Sesame Oil 500ml"), p(2, "Sesame Oil 500 ml")],
        [s("Sesame Oil 500 ml")],
    )
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["matched_pos_rows"] == 2
    assert rows[0]["pos_identity_ambiguous"] is True
    assert rows[0]["pos_product_id"] == ""


def test_summary_reports_strict_match_rate():
    summary = summarize_no_fuzzy_matches([
        {"status": "MATCHED"}, {"status": "MATCHED"}, {"status": "UNMATCHED"}
    ])
    assert summary == {
        "total_import_rows": 3,
        "matched": 2,
        "unmatched": 1,
        "match_rate_pct": 66.67,
    }
