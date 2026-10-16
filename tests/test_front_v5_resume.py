import hashlib
import json

from product_mapper.vision.front_v5_ledger import build_run_fingerprint, can_reuse_result


def test_run_fingerprint_is_deterministic_and_input_sensitive():
    base = build_run_fingerprint("a" * 64, {"worker": "b" * 64}, {"q": 6})
    assert base == build_run_fingerprint("a" * 64, {"worker": "b" * 64}, {"q": 6})
    assert base != build_run_fingerprint("a" * 64, {"worker": "b" * 64}, {"q": 7})


def test_accepted_result_reuse_requires_same_inputs_and_current_output_hash(tmp_path):
    output = tmp_path / "candidate.jpg"
    output.write_bytes(b"verified bytes")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    fingerprint = "f" * 64
    inputs = {"source": "a" * 64, "front": None, "back": None}
    gates = {f"Q{i}": {"passed": True} for i in range(1, 7)}
    result = {
        "state": "ACCEPTED", "run_fingerprint": fingerprint,
        "input_hashes": inputs, "candidate_set_sha256": "c" * 64,
        "output_path": str(output), "output_sha256": digest, "gates": gates,
    }
    expected = {"run_fingerprint": fingerprint, "input_hashes": inputs, "candidate_set_sha256": "c" * 64}
    assert can_reuse_result(result, expected)
    assert not can_reuse_result(result, expected | {"run_fingerprint": "0" * 64})
    assert not can_reuse_result(result, expected | {"input_hashes": {"source": "d" * 64}})
    output.write_bytes(b"changed bytes")
    assert not can_reuse_result(result, expected)


def test_legacy_progress_without_provenance_is_never_reused():
    assert not can_reuse_result({"state": "ACCEPTED", "output_path": "old.jpg"}, {})


def test_unchanged_terminal_failure_can_be_reused_without_output():
    result = {
        "state": "QA_RETURN", "reason": "missing independent review", "output_path": None,
        "run_fingerprint": "f" * 64, "input_hashes": {"source": "a" * 64},
        "candidate_set_sha256": "c" * 64,
    }
    expected = {key: result[key] for key in ("run_fingerprint", "input_hashes", "candidate_set_sha256")}
    assert can_reuse_result(result, expected)
    assert not can_reuse_result(result, expected | {"candidate_set_sha256": "d" * 64})


def test_budget_exhausted_candidate_is_queued_for_a_new_budget_epoch(tmp_path):
    candidate = tmp_path / "candidate.jpg"
    candidate.write_bytes(b"candidate bytes")
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    qa_path = tmp_path / "qa.json"
    qa_path.write_text(json.dumps({
        "candidate_sha256": digest,
        "verdict": "REVIEW",
        "semantic_review": {"reason_codes": ["budget_exhausted"]},
    }), encoding="utf-8")
    result = {
        "state": "REVIEW", "reason": "budget exhausted", "output_path": None,
        "candidate_path": str(candidate), "output_sha256": digest, "qa_path": str(qa_path),
        "run_fingerprint": "f" * 64, "input_hashes": {"source": "a" * 64},
        "candidate_set_sha256": "c" * 64, "expected_destination_sha256": None,
    }

    assert not can_reuse_result(result, {
        "run_fingerprint": result["run_fingerprint"],
        "input_hashes": result["input_hashes"],
        "candidate_set_sha256": result["candidate_set_sha256"],
        "expected_destination_sha256": None,
    })
