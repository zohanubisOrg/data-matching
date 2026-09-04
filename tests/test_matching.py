from pathlib import Path

from product_mapper.matching.matcher import match_image
from product_mapper.models import POSProduct, ProductImage, SupplierProduct
from product_mapper.parsing.attributes import parse_packaging


def image(name: str) -> ProductImage:
    return ProductImage(path=Path(name), filename=name, source="heuschen", source_product_id="1", raw_name=name, normalized_name=name, packaging=parse_packaging(name))


def product(pid: str, name: str, barcode: str = "0201000000179") -> POSProduct:
    return POSProduct(product_id=pid, sku=f"S-{pid}", barcode=barcode, product_name=name, official_name=name, printer_name=name)


def test_duplicate_name_is_review_not_auto():
    result = match_image(image("sesame oil"), [product("1", "Sesame Oil"), product("2", "Sesame Oil")], [], .90, .65)
    assert result.status == "NEED_REVIEW"
    assert len(result.top_candidates) == 2


def test_unique_exact_name_is_auto():
    result = match_image(image("sesame oil"), [product("1", "Sesame Oil"), product("2", "Peanut Oil")], [], .90, .65)
    assert result.status == "AUTO_MATCHED"


def test_size_conflict_is_review():
    result = match_image(image("sesame oil 650ml"), [product("1", "Sesame Oil 150ml")], [], .90, .65)
    assert result.status == "NEED_REVIEW"
    assert result.candidate and result.candidate.conflicts


def test_low_confidence_is_unmatched():
    result = match_image(image("zzzzzzzz"), [product("1", "Sesame Oil")], [], .90, .65)
    assert result.status == "UNMATCHED"


def test_exact_str_identifier_remains_string():
    p = product("11633374", "Beans", "0201000000179")
    assert isinstance(p.barcode, str) and p.barcode.startswith("0")


def test_supplier_name_bridge_is_evidence_only():
    source_image = image("sesame oil").model_copy(update={"source": "asia_express_food"})
    result = match_image(source_image, [product("1", "Sesame Oil")], [SupplierProduct(name="Sesame Oil", supplier="Asian Express Food (NL)")], .90, .65)
    assert any(value.startswith("supplier name bridge") for value in result.candidate.evidence)


def test_knowledge_base_persistence(tmp_path: Path):
    from product_mapper.matching.knowledge_base import load_knowledge_base, save_knowledge_base

    kb_file = tmp_path / "kb.json"
    save_knowledge_base({"sample.jpg": {"barcode": "1234567890123"}}, kb_file)
    loaded = load_knowledge_base(kb_file)
    assert loaded["sample.jpg"]["barcode"] == "1234567890123"


def test_asropa_ean_barcode_math():
    img = ProductImage(
        path=Path("asropa_73302_bap_cha.jpg"),
        filename="asropa_73302_bap_cha.jpg",
        source="asropa",
        source_product_id="73302",
        raw_name="asropa_73302_bap_cha",
        normalized_name="bap cha",
        packaging=parse_packaging("25x200g")
    )
    target = product("1", "Bap Cha", barcode="4045198733022")
    other = product("2", "Cha Ploo", barcode="8850123456789")
    result = match_image(img, [target, other], [], .88, .60)
    assert result.status == "AUTO_MATCHED"
    assert result.match_method == "asropa_ean_barcode"
    assert result.candidate.product.barcode == "4045198733022"


def test_multilingual_synonym_matching():
    img = ProductImage(
        path=Path("asropa_74107_reismehl.jpg"),
        filename="asropa_74107_reismehl.jpg",
        source="asropa",
        source_product_id="74107",
        raw_name="reismehl",
        normalized_name="reismehl",
        packaging=parse_packaging("50x400g")
    )
    target = product("1", "Rice Flour", barcode="084909000774")
    other = product("2", "Wheat Flour", barcode="8850123456789")
    result = match_image(img, [target, other], [], .80, .60)
    assert result.status == "AUTO_MATCHED"
    assert result.candidate.product.barcode == "084909000774"


def test_category_guard_noodle_vs_non_noodle():
    img = ProductImage(
        path=Path("noodles_spicy.jpg"),
        filename="noodles_spicy.jpg",
        source="asia_express_food",
        source_product_id="1",
        raw_name="noodles spicy",
        normalized_name="noodles spicy",
        packaging=parse_packaging("")
    )
    non_noodle = product("1", "Hot Chili", barcode="8719497392155")
    result = match_image(img, [non_noodle], [], .88, .60)
    assert result.status != "AUTO_MATCHED"


