import pytest
import hashlib
from io import BytesIO
from types import SimpleNamespace
from PIL import Image

from product_mapper.vision.front_v5_gemini import (
    FrontVisualReview,
    derive_semantic_status,
    GeminiFrontReviewer,
    GeminiRequestState,
)


def _review(**overrides):
    values = {
        "correct_product": "yes",
        "face": "front",
        "single_sale_unit": "yes",
        "package_complete": "yes",
        "details_preserved": "yes",
        "external_background": "none",
        "reference_consistency": "consistent",
        "evidence": ["The pouch outline and top seal are visible in the source and candidate."],
        "reason_codes": [],
        "repair_action": "none",
        "uncertain_regions": [],
    }
    values.update(overrides)
    return FrontVisualReview.model_validate(values)


def test_complete_semantic_evidence_passes():
    review = _review()

    assert derive_semantic_status(review) == "PASS"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("correct_product", "no", "FAIL"),
        ("face", "back", "FAIL"),
        ("single_sale_unit", "no", "FAIL"),
        ("package_complete", "no", "FAIL"),
        ("details_preserved", "no", "FAIL"),
        ("external_background", "unwanted", "FAIL"),
        ("package_complete", "uncertain", "REVIEW"),
        ("reference_consistency", "conflict", "REVIEW"),
        ("external_background", "uncertain", "REVIEW"),
    ],
)
def test_semantic_fail_or_uncertainty_never_passes(field, value, expected):
    assert derive_semantic_status(_review(**{field: value})) == expected


def test_repair_action_is_allowlisted():
    with pytest.raises(ValueError):
        _review(repair_action="generate_a_new_package_image")


def test_uncertain_region_bbox_must_be_normalized_and_ordered():
    with pytest.raises(ValueError):
        _review(uncertain_regions=[{"image_role": "candidate", "bbox": [0.8, 0.2, 0.4, 0.7]}])


def test_detail_round_is_counted_and_success_is_cached(tmp_path):
    buffer = BytesIO()
    Image.new("RGB", (80, 60), "white").save(buffer, "JPEG")
    image = buffer.getvalue()
    first = _review(
        package_complete="uncertain",
        uncertain_regions=[{"image_role": "source", "bbox": [0.2, 0.2, 0.8, 0.8]}],
    )
    second = _review()

    class Client:
        def __init__(self):
            self.calls = 0
            self.models = self

        def generate_content(self, **kwargs):
            response = (first, second)[self.calls]
            self.calls += 1
            return SimpleNamespace(parsed=response, model_version="gemini-3.1-pro-preview-2026-10", usage_metadata=None)

    client = Client()
    reviewer = GeminiFrontReviewer(
        state=GeminiRequestState(tmp_path / "state", max_requests=3),
        cache_dir=tmp_path / "cache",
        client=client,
    )
    args = {
        "barcode": "8850157516457",
        "record_id": "G1-0001",
        "product_name": "Test item",
        "images": {"source": image, "candidate": image},
        "input_hashes": {
            "source": hashlib.sha256(image).hexdigest(),
            "source_image": hashlib.sha256(image).hexdigest(),
            "output": hashlib.sha256(image).hexdigest(),
            "front_reference": None,
            "back_reference": None,
            "run_fingerprint": "c" * 64,
        },
    }

    result = reviewer.review(**args)
    cached = reviewer.review(**args)

    assert result["verdict"] == "PASS"
    assert result["api_requests"] == 2
    assert client.calls == 2
    assert cached["cache_hit"] is True
    assert GeminiRequestState(tmp_path / "state", max_requests=3).used() == 2


def test_hash_mismatch_fails_before_api_request(tmp_path):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, "JPEG")
    image = buffer.getvalue()

    class NeverCall:
        def generate_content(self, **_kwargs):
            raise AssertionError("mismatched bytes must not reach Gemini")

        models = property(lambda self: self)

    reviewer = GeminiFrontReviewer(
        state=GeminiRequestState(tmp_path / "state", max_requests=3),
        cache_dir=tmp_path / "cache",
        client=NeverCall(),
    )
    result = reviewer.review(
        barcode="8850157516457", record_id="G1-0001", product_name="Test",
        images={"source": image, "candidate": image},
        input_hashes={
            "source": "0" * 64, "source_image": "0" * 64, "output": "0" * 64,
            "front_reference": None, "back_reference": None,
        },
    )

    assert result["reason_codes"] == ["input_hash_mismatch"]
    assert GeminiRequestState(tmp_path / "state", max_requests=3).used() == 0
