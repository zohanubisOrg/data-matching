import hashlib
import json

from scripts.audit_front_v5_acceptance import audit


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_grouped_audit_reports_missing_gates_and_does_not_invent_semantic_zero(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run_fingerprint.txt").write_text("f" * 64, encoding="utf-8")
    image = run / "front.jpg"
    image.write_bytes(b"output")
    gates = {f"Q{i}": {"passed": i != 3} for i in range(1, 7)}
    _write_jsonl(run / "ledger.jsonl", [{
        "barcode": "8850157516457", "source_path": r"D:\\source\\a.jpg",
        "state": "ACCEPTED", "output_path": str(image),
        "output_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "run_fingerprint": "f" * 64, "gates": gates,
    }])
    labels = tmp_path / "labels.jsonl"
    _write_jsonl(labels, [
        {"id": 1, "path": r"D:\\source\\a.jpg", "package": "bag"},
        {"id": 2, "path": r"D:\\source\\missing.jpg", "package": "bottle_jar"},
    ])

    report = audit(run, labels)

    assert report["matched_labels"] == 1
    assert report["unmatched_labels"] == 1
    assert report["groups"]["bag"]["gates"]["Q3"]["fail"] == 1
    assert report["groups"]["bag"]["valid_accepted"] == 0
    assert report["semantic_defects"]["wrong_face_accepts"] is None


def test_legacy_run_without_fingerprint_is_audited_as_stale_not_crashing(tmp_path):
    run = tmp_path / "legacy"
    run.mkdir()
    output = run / "old.jpg"
    output.write_bytes(b"old")
    _write_jsonl(run / "ledger.jsonl", [{
        "barcode": "8850157516457", "source_path": "legacy.jpg", "state": "ACCEPTED",
        "output_path": str(output), "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }])
    labels = tmp_path / "labels.jsonl"
    _write_jsonl(labels, [{"id": 1, "path": "legacy.jpg", "package": "bag"}])

    report = audit(run, labels)

    assert report["run_fingerprint"] is None
    assert report["groups"]["bag"]["stale_accepted"] == 1
