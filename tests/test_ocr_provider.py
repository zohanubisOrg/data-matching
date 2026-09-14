from pathlib import Path

from product_mapper.vision.paddle_ocr import PaddleOCRProvider


class FakeResult:
    def __init__(self, payload):
        self.json = payload


class FakeEngine:
    def __init__(self, results):
        self.results = results
        self.inputs = []

    def predict(self, value):
        self.inputs.append(value)
        return self.results


def test_paddle_provider_extracts_text_scores_and_polygons_without_model_download(tmp_path: Path):
    image_path = tmp_path / "product.jpg"
    image_path.write_bytes(b"not-used-by-fake-engine")
    engine = FakeEngine([
        FakeResult({
            "res": {
                "rec_texts": ["AROY-D", "COCONUT MILK", "400 ML"],
                "rec_scores": [0.99, 0.98, 0.96],
                "rec_polys": [
                    [[0, 0], [10, 0], [10, 5], [0, 5]],
                    [[0, 10], [30, 10], [30, 15], [0, 15]],
                    [[0, 20], [15, 20], [15, 25], [0, 25]],
                ],
            }
        })
    ])

    result = PaddleOCRProvider(engine=engine).analyze(image_path)

    assert engine.inputs == [str(image_path)]
    assert [line.text for line in result.ocr_lines] == ["AROY-D", "COCONUT MILK", "400 ML"]
    assert result.ocr_lines[1].confidence == 0.98
    assert result.ocr_lines[2].polygon[2] == [15.0, 25.0]


def test_paddle_provider_skips_blank_text_and_handles_direct_payload(tmp_path: Path):
    image_path = tmp_path / "product.jpg"
    image_path.write_bytes(b"x")
    engine = FakeEngine([
        {
            "rec_texts": ["", "GREEN TEA APPLE"],
            "rec_scores": [0.4, 0.93],
            "rec_polys": [[], [[1, 2], [3, 4]]],
        }
    ])

    result = PaddleOCRProvider(engine=engine).analyze(image_path)

    assert [line.text for line in result.ocr_lines] == ["GREEN TEA APPLE"]
    assert result.warnings == []
