from __future__ import annotations

import hashlib

import numpy as np
import pytest
from PIL import Image

from product_mapper.vision.front_v5_quality import evaluate_front


def _valid_case():
    image = Image.new("RGB", (2400, 2400), "white")
    pixels = np.asarray(image).copy()
    pixels[168:2232, 1100:1300] = (190, 30, 50)
    image = Image.fromarray(pixels)
    product = np.zeros((2400, 2400), dtype=bool)
    product[168:2232, 1100:1300] = True
    expected = product.copy()
    source_sha = hashlib.sha256(b"source").hexdigest()
    output_sha = hashlib.sha256(b"output").hexdigest()
    front_sha = hashlib.sha256(b"front reference").hexdigest()
    back_sha = hashlib.sha256(b"back reference").hexdigest()
    evidence = {
        "product_mask": product,
        "envelope_mask": product.copy(),
        "source_core_mask": expected,
        "selected_source_product_mask": expected.copy(),
        "source_complete": True,
        "holes_ratio": 0.0,
        "has_separation": False,
        "separation_background_ratio": 1.0,
        "unit_count": 1,
        "retained_background_fill": 1.0,
        "residual_background_ratio": 0.0,
        "detached_fragment_ratios": [],
        "front_reference_available": True,
        "front_reference_sha256": front_sha,
        "face_score": 0.40,
        "runner_up_score": 0.10,
        "score_method": "appearance",
        "back_reference_available": True,
        "back_reference_sha256": back_sha,
        "back_score": 0.12,
        "human_review": None,
        "source_boundary_clear": True,
        "source_product_long_side": 2580,
        "canvas_product_bbox": (1100, 168, 1300, 2232),
        "scale": 0.8,
        "rectangular_envelope": True,
        "aspect_ratio_error": 0.0,
        "rotation": 0,
        "saved_format": "JPEG",
        "jpeg_quality": 95,
        "jpeg_subsampling": "4:4:4",
        "saved_file_verified": True,
        "catalog_barcode": "8850157516457",
        "filename_barcode": "8850157516457",
        "catalog_record_id": "G1-0001",
        "result_record_id": "G1-0001",
        "identity_conflict": False,
        "source_sha256": source_sha,
        "output_sha256": output_sha,
        "run_fingerprint": "f" * 64,
        "expected_run_fingerprint": "f" * 64,
        "semantic_review": {
            "verdict": "PASS",
            "model_version": "gemini-3.1-pro-preview-test",
            "prompt_version": "front-v5-visual-review-v1",
            "schema_version": "front-v5-visual-review-v1",
            "input_hashes": {
                "source": source_sha, "output": output_sha,
                "front_reference": front_sha, "back_reference": back_sha,
            },
            "observations": {
                "correct_product": "yes", "face": "front", "single_sale_unit": "yes",
                "package_complete": "yes", "details_preserved": "yes",
                "external_background": "none", "reference_consistency": "consistent",
            },
        },
    }
    return image, evidence


def test_all_six_gates_pass_with_complete_evidence():
    image, evidence = _valid_case()

    report = evaluate_front(image, evidence)

    assert report["passed"] is True
    assert set(report["gates"]) == {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"}
    assert all(item["passed"] for item in report["gates"].values())


@pytest.mark.parametrize(
    ("gate", "mutate"),
    [
        ("Q1", lambda image, evidence: [image.putpixel((x, y), (0, 0, 0)) for x in range(64) for y in range(64)]),
        ("Q2", lambda image, evidence: evidence.update(source_complete=False)),
        ("Q3", lambda image, evidence: evidence.update(unit_count=2)),
        ("Q4", lambda image, evidence: evidence.update(runner_up_score=0.40)),
        ("Q5", lambda image, evidence: evidence.update(scale=1.01)),
        ("Q6", lambda image, evidence: evidence.update(filename_barcode="8850157516458")),
    ],
)
def test_each_quality_gate_rejects_its_own_failure(gate, mutate):
    image, evidence = _valid_case()
    mutate(image, evidence)

    report = evaluate_front(image, evidence)

    assert report["passed"] is False
    assert report["gates"][gate]["passed"] is False
    assert report["gates"][gate]["reason"]


def test_q1_requires_rgb_canvas_and_corner_tile_thresholds():
    image, evidence = _valid_case()
    pixels = np.asarray(image).copy()
    pixels[:64, :64] = (245, 255, 255)
    image = Image.fromarray(pixels)

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q1"]["passed"] is False


def test_missing_source_core_and_separation_evidence_fail_q2():
    image, evidence = _valid_case()
    evidence.pop("source_core_mask")
    evidence["has_separation"] = True
    evidence.pop("separation_background_ratio")

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q2"]["passed"] is False


def test_q2_checks_selected_mask_covers_independent_package_core():
    image, evidence = _valid_case()
    core = evidence["source_core_mask"].copy()
    core[168:500, 1000:1100] = True
    evidence["source_core_mask"] = core

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q2"]["passed"] is False


def test_q3_rejects_unbounded_background_or_detached_piece():
    image, evidence = _valid_case()
    evidence["residual_background_ratio"] = 0.10
    evidence["detached_fragment_ratios"] = [0.011]

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q3"]["passed"] is False


def test_q4_rejects_low_match_even_when_it_beats_the_runner_up():
    image, evidence = _valid_case()
    evidence["face_score"] = 0.03
    evidence["runner_up_score"] = 0.0

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q4"]["passed"] is False


def test_q4_requires_hash_bound_human_evidence_when_reference_is_missing():
    image, evidence = _valid_case()
    evidence["front_reference_available"] = False
    evidence["human_review"] = {"approved": True, "barcode": evidence["catalog_barcode"]}

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q4"]["status"] == "REVIEW"


def test_semantic_evidence_must_bind_exact_saved_source_output_and_references():
    image, evidence = _valid_case()
    evidence["semantic_review"]["input_hashes"]["output"] = "0" * 64

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q2"]["status"] == "REVIEW"
    assert report["gates"]["Q4"]["status"] == "REVIEW"


def test_missing_gemini_result_never_passes_final_evaluation():
    image, evidence = _valid_case()
    evidence.pop("semantic_review")

    report = evaluate_front(image, evidence)

    assert report["passed"] is False
    assert all(gate["status"] == "REVIEW" for gate in report["gates"].values() if gate["reason"] == "semantic Gemini evidence is missing")


@pytest.mark.parametrize(
    "change",
    [
        {"canvas_product_bbox": (47, 168, 247, 2232)},
        {"canvas_product_bbox": (1100, 168, 1300, 2200)},
        {"source_product_long_side": 2063},
        {"aspect_ratio_error": 0.006},
        {"rotation": 45},
        {"saved_format": "PNG"},
        {"jpeg_quality": 90},
        {"saved_file_verified": False},
    ],
)
def test_q5_validates_saved_geometry_and_encoding(change):
    image, evidence = _valid_case()
    evidence.update(change)

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q5"]["passed"] is False


def test_q6_rejects_identity_conflict_and_missing_hashes():
    image, evidence = _valid_case()
    evidence["identity_conflict"] = True
    evidence.pop("output_sha256")

    report = evaluate_front(image, evidence)

    assert report["gates"]["Q6"]["passed"] is False

