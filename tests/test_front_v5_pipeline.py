from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import numpy as np
from PIL import Image

from product_mapper.vision import front_v5_pipeline as pipeline
from product_mapper.vision.front_v5_workers import _save_quality_evidence


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pass_result(candidate, fingerprint="f" * 64):
    digest = _sha(candidate)
    source = candidate.parent / "source.jpg"
    source.write_bytes(b"source bytes")
    qa_path = candidate.parent / "qa" / "8850157516457" / "attempt-01-review-01.json"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    gates = {f"Q{i}": {"status": "PASS", "passed": True} for i in range(1, 7)}
    qa_path.write_text(json.dumps({
        "verdict": "PASS", "run_fingerprint": fingerprint,
        "candidate_path": str(candidate), "candidate_sha256": digest,
        "source_path": str(source), "source_sha256": _sha(source),
        "semantic_review": {"verdict": "PASS"}, "gates": gates,
    }), encoding="utf-8")
    return {
        "state": "PASS",
        "candidate_path": str(candidate),
        "output_sha256": digest,
        "gates": gates,
        "qa_path": str(qa_path),
        "run_fingerprint": fingerprint,
    }


def _approval(tmp_path, fingerprint, labels_hash):
    report = tmp_path / "pilot-report.json"
    report.write_text(json.dumps({
        "run_fingerprint": fingerprint,
        "labels_sha256": labels_hash,
        "rows": 48,
        "pilot_criteria_passed": True,
    }), encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({
        "approved": True,
        "pilot_id": "pilot-1",
        "run_fingerprint": fingerprint,
        "pilot_report_path": str(report),
        "pilot_report_sha256": _sha(report),
        "labels_sha256": labels_hash,
        "approved_by": "reviewer",
        "approved_at": "2026-10-16T00:00:00Z",
    }), encoding="utf-8")
    return approval


def test_shadow_pass_does_not_promote(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate.jpg"
    candidate.write_bytes(b"verified image bytes")
    job = {"barcode": "8850157516457", "candidates": []}
    result = _pass_result(candidate)
    result["python_evidence_path"] = str(tmp_path / "candidate.python.json")

    monkeypatch.setattr(pipeline, "review_candidate", lambda *a, **k: result)
    outcome = pipeline.review_with_repairs(job, result, run_dir=tmp_path, qa_mode="shadow")

    assert outcome["state"] == "PASS"
    assert outcome.get("output_path") is None
    assert outcome["attempt_history"][0]["state"] == "PASS"


def test_repair_loop_uses_no_more_than_three_immutable_sources(tmp_path, monkeypatch):
    first = {
        "state": "CANDIDATE", "source_path": "source-0.jpg",
        "candidate_path": str(tmp_path / "candidate-1.jpg"),
        "python_evidence_path": str(tmp_path / "evidence-1.json"), "attempt": 1,
    }
    job = {
        "barcode": "8850157516457",
        "candidates": [
            {"path": f"source-{index}.jpg", "oriented_size": [3000, 3000]}
            for index in range(5)
        ],
    }
    reviewed_attempts = []
    rendered_attempts = []

    def review(_job, result, **_kwargs):
        number = result["attempt"]
        reviewed_attempts.append(number)
        status = "PASS" if number == 3 else "FAIL"
        return result | {
            "state": status,
            "reason": "" if status == "PASS" else "semantic defect",
            "semantic_review": {"repair_action": "alternate_source"},
            "gates": {f"Q{i}": {"status": status} for i in range(1, 7)},
        }

    def render(retry_job):
        number = retry_job["attempt_number"]
        rendered_attempts.append(number)
        return {
            "state": "CANDIDATE", "source_path": retry_job["candidates"][0]["path"],
            "candidate_path": str(tmp_path / f"candidate-{number}.jpg"),
            "python_evidence_path": str(tmp_path / f"evidence-{number}.json"),
            "attempt": number,
        }

    monkeypatch.setattr(pipeline, "review_candidate", review)
    monkeypatch.setattr(pipeline, "render_one", render)

    result = pipeline.review_with_repairs(job, first, run_dir=tmp_path)

    assert reviewed_attempts == [1, 2, 3]
    assert rendered_attempts == [2, 3]
    assert result["state"] == "PASS"
    assert len(result["attempt_history"]) == 3


def test_promotion_creates_rollback_and_replaces_only_expected_hash(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    front_dir = tmp_path / "front-v5"
    apptance = tmp_path / "apptance"
    run_dir.mkdir()
    front_dir.mkdir()
    apptance.mkdir()
    candidate = run_dir / "candidate.jpg"
    candidate.write_bytes(b"new output")
    destination = front_dir / "8850157516457-front.jpg"
    destination.write_bytes(b"old output")
    monkeypatch.setattr(pipeline, "_assert_no_active_writer", lambda: None)
    fingerprint = "f" * 64
    labels_hash = "a" * 64
    approval = _approval(tmp_path, fingerprint, labels_hash)
    job = {
        "barcode": "8850157516457",
        "expected_destination_sha256": _sha(destination),
        "pilot_labels_sha256": labels_hash,
    }
    result = _pass_result(candidate, fingerprint)

    promoted = pipeline.promote_candidate(
        job, result, run_dir=run_dir, front_dir=front_dir,
        apptance_dir=apptance, expected_sha256=_sha(destination), approval_path=approval,
    )

    old_hash = hashlib.sha256(b"old output").hexdigest()
    assert promoted["state"] == "ACCEPTED"
    assert destination.read_bytes() == b"new output"
    assert _sha(run_dir / "rollback" / f"8850157516457-{old_hash}.jpg") == old_hash


def test_promotion_rejects_stale_qa_evidence(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    candidate = run_dir / "candidate.jpg"
    candidate.parent.mkdir()
    candidate.write_bytes(b"candidate")
    result = _pass_result(candidate)
    qa_path = Path(result["qa_path"])
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    qa["candidate_sha256"] = "0" * 64
    qa_path.write_text(json.dumps(qa), encoding="utf-8")
    monkeypatch.setattr(pipeline, "_assert_no_active_writer", lambda: None)
    fingerprint, labels_hash = "f" * 64, "a" * 64
    approval = _approval(tmp_path, fingerprint, labels_hash)
    result["run_fingerprint"] = fingerprint
    with pytest.raises(ValueError, match="QA evidence"):
        pipeline.promote_candidate(
            {"barcode": "8850157516457", "pilot_labels_sha256": labels_hash}, result,
            run_dir=run_dir, front_dir=tmp_path / "front", apptance_dir=tmp_path / "apptance",
            expected_sha256=None, approval_path=approval,
        )


def test_promotion_aborts_when_delivery_file_changed(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    front_dir = tmp_path / "front"
    apptance = tmp_path / "apptance"
    run_dir.mkdir()
    front_dir.mkdir()
    apptance.mkdir()
    candidate = run_dir / "candidate.jpg"
    candidate.write_bytes(b"candidate")
    destination = front_dir / "8850157516457-front.jpg"
    destination.write_bytes(b"concurrent writer output")
    monkeypatch.setattr(pipeline, "_assert_no_active_writer", lambda: None)
    fingerprint = "e" * 64
    labels_hash = "b" * 64
    approval = _approval(tmp_path, fingerprint, labels_hash)
    result = _pass_result(candidate, fingerprint)

    with pytest.raises(RuntimeError, match="destination changed"):
        pipeline.promote_candidate(
            {"barcode": "8850157516457", "pilot_labels_sha256": labels_hash}, result,
            run_dir=run_dir, front_dir=front_dir, apptance_dir=apptance,
            expected_sha256=hashlib.sha256(b"previous version").hexdigest(), approval_path=approval,
        )
    assert destination.read_bytes() == b"concurrent writer output"


def test_promotion_never_accepts_partial_gates(tmp_path):
    candidate = tmp_path / "candidate.jpg"
    candidate.write_bytes(b"candidate")
    result = _pass_result(candidate)
    result["gates"]["Q3"]["status"] = "REVIEW"

    with pytest.raises(ValueError, match="six current passing gates"):
        pipeline.promote_candidate(
            {"barcode": "8850157516457"}, result,
            run_dir=tmp_path, front_dir=tmp_path / "front",
            apptance_dir=tmp_path / "apptance", expected_sha256=None,
            approval_path=None,
        )


def test_pilot_approval_requires_hashed_passing_benchmark(tmp_path):
    fingerprint = "d" * 64
    labels_hash = "a" * 64
    report = tmp_path / "pilot-report.json"
    report.write_text(json.dumps({
        "run_fingerprint": fingerprint, "labels_sha256": labels_hash,
        "rows": 48, "pilot_criteria_passed": False,
    }), encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({
        "approved": True, "pilot_id": "pilot",
        "run_fingerprint": fingerprint, "pilot_report_path": str(report),
        "pilot_report_sha256": _sha(report), "labels_sha256": labels_hash,
        "approved_by": "reviewer", "approved_at": "2026-10-16T00:00:00Z",
    }), encoding="utf-8")

    assert pipeline._read_pilot_approval(approval, fingerprint, labels_hash) is None


def test_review_candidate_combines_hash_bound_semantics_with_python_gates(tmp_path):
    candidate = tmp_path / "candidate.jpg"
    source = tmp_path / "source.jpg"
    image = Image.new("RGB", (2400, 2400), "white")
    pixels = np.asarray(image).copy()
    pixels[168:2232, 1100:1300] = (180, 40, 60)
    image = Image.fromarray(pixels)
    image.save(candidate, "JPEG", quality=95, subsampling=0)
    image.save(source, "JPEG", quality=95, subsampling=0)
    product = np.zeros((2400, 2400), dtype=bool)
    product[168:2232, 1100:1300] = True
    source_hash, output_hash = _sha(source), _sha(candidate)
    front_hash = hashlib.sha256(b"front reference").hexdigest()
    fingerprint = "c" * 64
    evidence_path = tmp_path / "candidate.python.json"
    _save_quality_evidence(evidence_path, {
        "product_mask": product,
        "envelope_mask": product.copy(),
        "source_core_mask": product.copy(),
        "selected_source_product_mask": product.copy(),
        "source_complete": True,
        "source_boundary_clear": True,
        "holes_ratio": 0.0,
        "has_separation": False,
        "unit_count": 1,
        "canvas_product_bbox": [1100, 168, 1300, 2232],
        "source_product_long_side": 2580,
        "scale": 0.8,
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
        "source_sha256": source_hash,
        "output_sha256": output_hash,
        "run_fingerprint": fingerprint,
        "expected_run_fingerprint": fingerprint,
        "front_reference_available": True,
        "back_reference_available": False,
        "front_reference_sha256": front_hash,
        "back_reference_sha256": None,
    })

    class Reviewer:
        def review(self, **kwargs):
            return {
                "verdict": "PASS",
                "observations": {
                    "correct_product": "yes", "face": "front", "single_sale_unit": "yes",
                    "package_complete": "yes", "details_preserved": "yes",
                    "external_background": "none", "reference_consistency": "consistent",
                },
                "reason_codes": [],
                "model_id": "gemini-3.1-pro-preview",
                "model_version": "gemini-3.1-pro-preview-2026-10",
                "prompt_version": "front-v5-visual-review-v1",
                "schema_version": "front-v5-visual-review-v1",
                "input_hashes": kwargs["input_hashes"],
                "api_requests": 1,
            }

    result = {
        "state": "CANDIDATE",
        "candidate_path": str(candidate),
        "python_evidence_path": str(evidence_path),
        "source_path": str(source),
        "attempt": 1,
        "output_sha256": output_hash,
        "run_fingerprint": fingerprint,
    }
    job = {
        "barcode": "8850157516457", "record_id": "G1-0001", "name": "Product",
        "input_hashes": {"front_reference": front_hash, "back_reference": None},
        "reference": b"front reference", "back": None,
    }

    reviewer = Reviewer()
    reviewed = pipeline.review_candidate(job, result, run_dir=tmp_path, reviewer=reviewer)
    first_qa = Path(reviewed["qa_path"])
    first_contents = first_qa.read_bytes()
    repeated = pipeline.review_candidate(job, reviewed, run_dir=tmp_path, reviewer=reviewer)

    assert reviewed["state"] == "PASS"
    assert all(gate["status"] == "PASS" for gate in reviewed["gates"].values())
    assert reviewed["semantic_review"]["input_hashes"]["output"] == output_hash
    assert Path(repeated["qa_path"]) != first_qa
    assert first_qa.read_bytes() == first_contents
