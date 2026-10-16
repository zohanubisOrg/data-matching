#!/usr/bin/env python3
"""Read-only grouped audit of front-v5 ledger results against the label matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_key(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(Path(value).resolve()).casefold()
    except OSError:
        return str(value).casefold()


def audit(run_dir: Path, labels_path: Path) -> dict:
    ledger = _jsonl(run_dir / "ledger.jsonl")
    labels = _jsonl(labels_path)
    by_barcode = {str(row.get("barcode")): row for row in ledger if row.get("barcode")}
    by_source = {_path_key(row.get("source_path")): row for row in ledger if row.get("source_path")}
    fingerprint_path = run_dir / "run_fingerprint.txt"
    fingerprint = fingerprint_path.read_text(encoding="utf-8").strip() if fingerprint_path.is_file() else None
    gate_names = [f"Q{i}" for i in range(1, 7)]
    groups: dict[str, dict] = defaultdict(lambda: {
        "labels": 0, "matched_results": 0, "accepted": 0, "valid_accepted": 0,
        "stale_accepted": 0, "critical_defect_accepts": None,
        "gates": {name: {"pass": 0, "fail": 0, "missing": 0} for name in gate_names},
    })
    missing = 0
    for label in labels:
        result = by_barcode.get(str(label.get("barcode"))) if label.get("barcode") else None
        result = result or by_source.get(_path_key(label.get("path")))
        group = str(label.get("package", "unlabeled"))
        counts = groups[group]
        counts["labels"] += 1
        if result is None:
            missing += 1
            for gate in gate_names:
                counts["gates"][gate]["missing"] += 1
            continue
        counts["matched_results"] += 1
        gates = result.get("gates") if isinstance(result.get("gates"), dict) else {}
        for gate in gate_names:
            evidence = gates.get(gate)
            if not isinstance(evidence, dict):
                counts["gates"][gate]["missing"] += 1
            elif evidence.get("passed") is True:
                counts["gates"][gate]["pass"] += 1
            else:
                counts["gates"][gate]["fail"] += 1
        if result.get("state") == "ACCEPTED":
            counts["accepted"] += 1
            path = Path(result["output_path"]) if result.get("output_path") else None
            valid = bool(path and path.is_file() and _sha256(path) == result.get("output_sha256"))
            valid = valid and fingerprint is not None and result.get("run_fingerprint") == fingerprint
            valid = valid and set(gates) == set(gate_names) and all(
                isinstance(gates.get(gate), dict) and gates[gate].get("passed") is True for gate in gate_names
            )
            if valid:
                counts["valid_accepted"] += 1
            else:
                counts["stale_accepted"] += 1
    state_counts: dict[str, int] = defaultdict(int)
    for row in ledger:
        state_counts[str(row.get("state", "MISSING"))] += 1
    return {
        "run_dir": str(run_dir.resolve()),
        "run_fingerprint": fingerprint,
        "labels": len(labels),
        "matched_labels": len(labels) - missing,
        "unmatched_labels": missing,
        "ledger_rows": len(ledger),
        "ledger_states": dict(state_counts),
        "groups": dict(sorted(groups.items())),
        "semantic_defects": {
            "wrong_face_accepts": None,
            "clipped_package_accepts": None,
            "multi_product_accepts": None,
            "note": "requires independent review labels bound to the exact output hashes; missing is not counted as zero",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="optional JSON output path; audit itself is read-only")
    args = parser.parse_args()
    report = audit(args.run_dir, args.labels)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
