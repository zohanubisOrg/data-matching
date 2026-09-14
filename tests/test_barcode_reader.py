from pathlib import Path

from PIL import Image

from product_mapper.vision.barcode_reader import BarcodeReader


def test_barcode_reader_uses_multiple_image_passes_and_returns_consensus(tmp_path: Path):
    image_path = tmp_path / "product.jpg"
    Image.new("RGB", (100, 60), "white").save(image_path)

    calls = []

    def decoder(image):
        calls.append(image.size)
        if len(calls) in {1, 3, 5}:
            return ["4006381333931"]
        if len(calls) == 2:
            return ["036000291452"]
        return []

    result = BarcodeReader(decoder=decoder).analyze(image_path)

    assert len(calls) > 1
    assert result.barcode == "4006381333931"
    assert result.barcode_checksum_valid is True
    assert result.barcode_candidates.count("4006381333931") == 3


def test_barcode_reader_does_not_select_tied_values(tmp_path: Path):
    image_path = tmp_path / "product.jpg"
    Image.new("RGB", (100, 60), "white").save(image_path)

    calls = 0

    def decoder(image):
        nonlocal calls
        calls += 1
        return ["4006381333931"] if calls % 2 else ["036000291452"]

    result = BarcodeReader(decoder=decoder, max_passes=2).analyze(image_path)

    assert result.barcode is None
    assert result.barcode_checksum_valid is None
    assert sorted(result.barcode_candidates) == ["036000291452", "4006381333931"]
