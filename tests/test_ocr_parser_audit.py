from product_mapper.parsing.ocr_parser import parse_ocr_identity
from product_mapper.vision.provider import OCRLine


def test_multiple_different_ocr_measurements_are_marked_ambiguous():
    identity = parse_ocr_identity([
        OCRLine("COCONUT MILK", 0.99),
        OCRLine("400 ML", 0.98),
        OCRLine("Nutrition per 100 ML", 0.97),
    ])

    assert identity["item_size"] is None
    assert identity["size_ambiguous"] is True
    assert set(identity["observed_sizes"]) == {("volume", 400.0), ("volume", 100.0)}


def test_one_unique_ocr_measurement_remains_usable():
    identity = parse_ocr_identity([
        OCRLine("GREEN TEA APPLE", 0.99),
        OCRLine("500 ML", 0.98),
    ])

    assert identity["item_size"] == ("volume", 500.0)
    assert identity["size_ambiguous"] is False
