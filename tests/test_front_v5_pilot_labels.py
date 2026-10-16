import json

import pytest

from scripts.run_front_v5_batch import _load_confirmed_pilot


GROUPS = ("box", "bottle_jar", "sealed_bag", "transparent_bag", "produce_tray", "reflective_frozen")


def _labels():
    rows = []
    number = 1
    for index in range(12):
        rows.append({
            "barcode": str(number).zfill(13), "confirmed": True,
            "group": GROUPS[index % len(GROUPS)],
            "case_type": "positive", "expected_verdict": "PASS",
        })
        number += 1
        rows.append({
            "barcode": str(number).zfill(13), "confirmed": True,
            "group": GROUPS[index % len(GROUPS)],
            "case_type": "regression", "expected_verdict": "FAIL",
        })
        number += 1
    for index in range(24):
        rows.append({
            "barcode": str(number).zfill(13), "confirmed": True,
            "case_type": "difficult", "group": GROUPS[index // 4],
            "expected_verdict": "REVIEW",
        })
        number += 1
    return rows


def test_pilot_requires_48_confirmed_stratified_human_labels(tmp_path):
    labels = tmp_path / "confirmed.jsonl"
    labels.write_text("\n".join(json.dumps(item) for item in _labels()) + "\n", encoding="utf-8")

    loaded = _load_confirmed_pilot(labels)

    assert len(loaded) == 48
    assert sum(item["case_type"] == "positive" for item in loaded.values()) == 12


def test_pilot_rejects_provisional_or_duplicate_labels(tmp_path):
    labels = _labels()
    labels[0]["confirmed"] = False
    labels[1]["barcode"] = labels[0]["barcode"]
    path = tmp_path / "provisional.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in labels) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="48 unique, human-confirmed"):
        _load_confirmed_pilot(path)
