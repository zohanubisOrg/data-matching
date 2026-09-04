from pathlib import Path

from product_mapper.parsing.attributes import packaging_conflict, parse_packaging
from product_mapper.parsing.filename_parser import parse_filename
from product_mapper.parsing.text_normalizer import normalize_text


def test_filename_parser_supports_multitoken_source_and_suffix_id():
    image = parse_filename(Path("asia_express_food_7680mp_instant_noodles_shin_ramyun.jpg"))
    assert image.source == "asia_express_food"
    assert image.source_product_id == "7680mp"
    assert image.normalized_name == "instant noodles shin ramyun"


def test_normalizer_preserves_unicode_and_numbers():
    assert normalize_text(" SESAME_OIL--1L ÄÖ Đà Nẵng ") == "sesame oil 1l äö đà nẵng"


def test_packaging_and_size_conflict():
    assert parse_packaging("24x500ml").levels == [(24.0, "ml"), (500.0, "x")]
    assert parse_packaging("1l").levels == [(1000.0, "ml")]
    assert "size conflict" in (packaging_conflict(parse_packaging("650ml"), parse_packaging("150ml")) or "")

