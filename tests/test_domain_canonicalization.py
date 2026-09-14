from product_mapper.matching.no_fuzzy import match_import_names_no_fuzzy
from product_mapper.models import POSProduct, SupplierProduct


def product(name: str) -> POSProduct:
    return POSProduct(
        product_id="1",
        sku="SKU-1",
        barcode="4006381333931",
        product_name=name,
        official_name=name,
    )


def source(name: str) -> SupplierProduct:
    return SupplierProduct(name=name, supplier="image")


def match(pos_name: str, source_name: str) -> dict:
    return match_import_names_no_fuzzy([product(pos_name)], [source(source_name)])[0]


def test_compact_case_pack_preserves_item_size():
    row = match("Green Tea Apple 500 ml", "Green Tea Apple 24x500ml")

    assert row["item_size"] == "500 ml"
    assert row["status"] == "AUTO_MATCHED"


def test_ube_and_purple_yam_are_domain_aliases_not_fuzzy():
    row = match("Purple Yam Fruit Spread", "Ube Fruit Spread")

    assert row["status"] == "AUTO_MATCHED"
    assert row["match_method"] == "canonical_exact"


def test_atchara_and_papaya_pickle_are_domain_aliases_not_fuzzy():
    row = match("Papaya Pickle", "Atchara")

    assert row["status"] == "AUTO_MATCHED"


def test_observed_sirup_spelling_normalizes_to_syrup():
    row = match("Nata de Coco Green in Heavy Syrup", "Nata de Coco Green in Heavy Sirup")

    assert row["status"] == "AUTO_MATCHED"


def test_observed_suger_spelling_keeps_no_added_sugar_semantics():
    row = match("Dried Mango No Added Sugar", "Dried Mango No Added Suger")

    assert row["status"] == "AUTO_MATCHED"
