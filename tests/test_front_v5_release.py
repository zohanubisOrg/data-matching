import hashlib

import pytest

from product_mapper.vision.front_v5_ledger import accepted_set_digest, first_batch_digest, validate_release


def _accepted_row(tmp_path):
    path = tmp_path / "front.jpg"
    path.write_bytes(b"current output")
    return {
        "state": "ACCEPTED", "barcode": "8850157516457", "record_id": "R-1",
        "output_path": str(path), "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "gates": {f"Q{i}": {"passed": True} for i in range(1, 7)},
    }


def _release(ledger):
    row = ledger[0]
    return {
        "run_fingerprint": "f" * 64,
        "accepted_set_sha256": accepted_set_digest(ledger),
        "output_hashes": {row["barcode"]: row["output_sha256"]},
        "sample": [{"barcode": row["barcode"], "output_sha256": row["output_sha256"], "decision": "PASS", "group": "bag"}],
        "sample_seed": 20261016,
        "group_counts": {"bag": 1},
        "first_batch_review": {"approved": True, "critical_defects": 0, "rows_sha256": first_batch_digest(ledger), "reviewed_row_count": 1, "reviewer": "reviewer"},
        "reviewer": "independent reviewer",
    }


def test_release_accepts_exact_small_set_only_when_every_file_is_reviewed(tmp_path):
    ledger = [_accepted_row(tmp_path)]
    validate_release(ledger, _release(ledger), "f" * 64)


@pytest.mark.parametrize("mutation", ["missing", "changed_hash", "critical", "fingerprint", "first_batch"])
def test_release_rejects_stale_or_unsafe_reviews(tmp_path, mutation):
    ledger = [_accepted_row(tmp_path)]
    release = _release(ledger)
    if mutation == "missing":
        release["sample"] = []
    elif mutation == "changed_hash":
        ledger[0]["output_path"] and open(ledger[0]["output_path"], "wb").write(b"modified")
    elif mutation == "critical":
        release["sample"][0]["decision"] = "CRITICAL"
    elif mutation == "fingerprint":
        release["run_fingerprint"] = "0" * 64
    else:
        release["first_batch_review"]["approved"] = False
    with pytest.raises(ValueError):
        validate_release(ledger, release, "f" * 64)
