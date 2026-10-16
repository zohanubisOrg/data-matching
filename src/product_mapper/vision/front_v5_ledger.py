"""Workbook identity and source-file ledger for the front-v5 batch."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

_SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

SOURCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
FORBIDDEN_ROOT_NAMES = ("front-v3", "back-v2")


def barcode_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return ""
    return re.sub(r"\D", "", str(value).strip())


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall(f"{_SHEET_NS}si"):
        strings.append("".join(node.text or "" for node in item.iter(f"{_SHEET_NS}t")))
    return strings


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{_SHEET_NS}t"))
    value = cell.find(f"{_SHEET_NS}v")
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return shared[int(value.text)]
    return value.text


def _column_row(ref: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref or "")
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def load_catalog_rows(path: Path) -> list[dict]:
    """Read barcode, name, and Record ID without loading embedded pictures."""
    rows = []
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        with archive.open("xl/worksheets/sheet1.xml") as handle:
            for _event, element in ET.iterparse(handle, events=("end",)):
                if element.tag != f"{_SHEET_NS}row":
                    continue
                values = {"A": "", "B": "", "E": ""}
                excel_row = int(element.get("r") or 0)
                for cell in element.findall(f"{_SHEET_NS}c"):
                    parsed = _column_row(cell.get("r") or "")
                    if parsed is None:
                        continue
                    column, _row = parsed
                    if column in values:
                        values[column] = _cell_text(cell, shared)
                element.clear()
                if excel_row < 4:
                    continue
                barcode = barcode_text(values["A"])
                if not barcode:
                    continue
                rows.append(
                    {
                        "excel_row": excel_row,
                        "barcode": barcode,
                        "record_id": str(values["E"]).strip(),
                        "name": str(values["B"]).strip(),
                    }
                )
    return mark_identity_conflicts(rows)


def mark_identity_conflicts(rows: list[dict]) -> list[dict]:
    owners: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for variant in get_barcode_lookup_variants(row["barcode"]):
            owners[variant].add(row["record_id"])
    contested = {variant for variant, ids in owners.items() if len(ids) > 1}
    for row in rows:
        row["identity_conflict"] = any(
            variant in contested for variant in get_barcode_lookup_variants(row["barcode"])
        )
    return rows


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.name.lower() in FORBIDDEN_ROOT_NAMES:
            raise ValueError(f"refusing to index {root}")
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            lowered = str(path).lower()
            if "removed_not_in_excel" in lowered:
                continue
            if path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            files.append(path)
    return files


_XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _media_name(target: str) -> str:
    cleaned = target.split("?")[0].lstrip("/")
    if cleaned.startswith("../"):
        cleaned = "xl/" + cleaned.removeprefix("../")
    return cleaned


def load_column_media(path: Path, column: str) -> dict[str, bytes]:
    """Customer photos embedded in one drawing column, keyed by barcode."""
    barcode_by_row = {
        row["excel_row"]: row["barcode"]
        for row in load_catalog_rows(path)
        if not row["identity_conflict"]
    }
    found: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        drawing = ET.fromstring(archive.read("xl/drawings/drawing1.xml"))
        rels = ET.fromstring(archive.read("xl/drawings/_rels/drawing1.xml.rels"))
        targets = {
            node.get("Id"): node.get("Target")
            for node in rels
            if node.get("Id") and node.get("Target")
        }
        for anchor in drawing:
            column_node = anchor.find(f"{_XDR}from/{_XDR}col")
            row_node = anchor.find(f"{_XDR}from/{_XDR}row")
            if column_node is None or row_node is None or column_node.text != column or row_node.text is None:
                continue
            barcode = barcode_by_row.get(int(row_node.text) + 1)
            if not barcode:
                continue
            blip = anchor.find(f".//{_A_NS}blip")
            if blip is None:
                continue
            rid = blip.get(f"{_REL_NS}embed")
            target = targets.get(rid or "")
            if not target:
                continue
            found[barcode] = archive.read(_media_name(target))
    return found


def index_fields(path: Path, sha256: str, size: tuple[int, int], barcode: str | None, rotation: int) -> dict:
    return {
        "path": str(path),
        "sha256": sha256,
        "oriented_size": [size[0], size[1]],
        "barcode": barcode,
        "rotation": rotation,
    }


def build_run_fingerprint(workbook_sha256: str, implementation_hashes: dict, config: dict) -> str:
    """Stable digest of workbook, implementation and quality/render configuration."""
    payload = {
        "workbook_sha256": workbook_sha256,
        "implementation_hashes": implementation_hashes,
        "config": config,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def can_reuse_result(result: dict, expected: dict) -> bool:
    """Reuse only a current result with identical inputs and verified output bytes."""
    if not isinstance(result, dict) or not isinstance(expected, dict):
        return False
    if result.get("run_fingerprint") != expected.get("run_fingerprint"):
        return False
    if result.get("input_hashes") != expected.get("input_hashes"):
        return False
    if result.get("candidate_set_sha256") != expected.get("candidate_set_sha256"):
        return False
    if result.get("state") != "ACCEPTED":
        if ("expected_destination_sha256" in expected
                and result.get("expected_destination_sha256") != expected.get("expected_destination_sha256")):
            return False
        state = result.get("state")
        if state not in {"PASS", "QA_RETURN", "CUSTOMER_RESHOOT"} or not result.get("reason") or result.get("output_path"):
            return False
        candidate_path = result.get("candidate_path")
        if candidate_path:
            path = Path(candidate_path)
            qa_path = Path(result.get("qa_path", ""))
            if not path.is_file() or not qa_path.is_file():
                return False
            candidate_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if candidate_digest != result.get("output_sha256"):
                return False
            try:
                qa = json.loads(qa_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                return False
            semantic = qa.get("semantic_review", {})
            if "budget_exhausted" in semantic.get("reason_codes", []):
                return False
            return qa.get("candidate_sha256") == candidate_digest and qa.get("verdict") == result.get("state")
        return state in {"QA_RETURN", "CUSTOMER_RESHOOT"}
    output_path = result.get("output_path")
    output_digest = result.get("output_sha256")
    if not output_path or not isinstance(output_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", output_digest):
        return False
    path = Path(output_path)
    if not path.is_file():
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != output_digest:
        return False
    gates = result.get("gates")
    if not isinstance(gates, dict) or set(gates) != {f"Q{i}" for i in range(1, 7)}:
        return False
    if not all(isinstance(gate, dict) and gate.get("passed") is True for gate in gates.values()):
        return False
    return True


def accepted_set_digest(rows: list[dict]) -> str:
    records = sorted(
        (str(row.get("barcode", "")), str(row.get("record_id", "")), str(row.get("output_sha256", "")))
        for row in rows if row.get("state") == "ACCEPTED"
    )
    return hashlib.sha256(json.dumps(records, separators=(",", ":")).encode("utf-8")).hexdigest()


def first_batch_digest(rows: list[dict]) -> str:
    """Bind the ordered first 150 catalog outcomes and evidence to review."""
    bound = [
        {
            key: row.get(key)
            for key in ("excel_row", "barcode", "record_id", "state", "source_path", "output_path", "output_sha256", "run_fingerprint", "input_hashes", "candidate_set_sha256")
        }
        for row in rows[:150]
    ]
    canonical = json.dumps(bound, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_release(ledger: list[dict], release: dict, run_fingerprint: str) -> None:
    """Raise unless a complete visual review approves this exact accepted set."""
    if not isinstance(release, dict) or release.get("run_fingerprint") != run_fingerprint:
        raise ValueError("release missing or stale run fingerprint")
    accepted = [row for row in ledger if row.get("state") == "ACCEPTED"]
    if not accepted:
        raise ValueError("empty accepted set cannot be released")
    digest = accepted_set_digest(ledger)
    if release.get("accepted_set_sha256") != digest:
        raise ValueError("release accepted-set digest does not match ledger")
    expected_hashes = {row.get("barcode"): row.get("output_sha256") for row in accepted}
    if release.get("output_hashes") != expected_hashes:
        raise ValueError("release output hashes do not match accepted ledger rows")
    for row in accepted:
        output_path = row.get("output_path")
        if not output_path or not Path(output_path).is_file():
            raise ValueError("accepted output missing")
        if hashlib.sha256(Path(output_path).read_bytes()).hexdigest() != row.get("output_sha256"):
            raise ValueError("accepted output hash changed")
        gates = row.get("gates")
        if not isinstance(gates, dict) or set(gates) != {f"Q{i}" for i in range(1, 7)} or not all(g.get("passed") is True for g in gates.values()):
            raise ValueError("accepted row lacks six passing quality gates")
    sample = release.get("sample")
    if not isinstance(sample, list):
        raise ValueError("release sample missing")
    if len(accepted) >= 93 and len(sample) < 93:
        raise ValueError("release sample must include at least 93 accepted files, or all when fewer exist")
    if len(accepted) < 93 and len(sample) != len(accepted):
        raise ValueError("all accepted files must be reviewed when fewer than 93 exist")
    if len(accepted) >= 93 and len(sample) < 93:
        raise ValueError("release sample is smaller than 93")
    accepted_by_barcode = {row.get("barcode"): row for row in accepted}
    if len({entry.get("barcode") for entry in sample if isinstance(entry, dict)}) != len(sample):
        raise ValueError("release sample contains duplicate or malformed rows")
    for entry in sample:
        if not isinstance(entry, dict):
            raise ValueError("release sample row malformed")
        row = accepted_by_barcode.get(entry.get("barcode"))
        if row is None or entry.get("output_sha256") != row.get("output_sha256"):
            raise ValueError("review sample is not bound to current accepted output")
        if entry.get("decision") not in {"PASS", "MINOR", "CRITICAL"}:
            raise ValueError("review sample decision missing")
    if any(entry["decision"] == "CRITICAL" for entry in sample):
        raise ValueError("critical defect blocks release")
    if sum(entry["decision"] == "MINOR" for entry in sample) > 1:
        raise ValueError("more than one minor defect blocks release")
    groups = release.get("group_counts")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("release group counts missing")
    sampled_per_group: dict[str, int] = defaultdict(int)
    if isinstance(release.get("sample_seed"), bool) or not isinstance(release.get("sample_seed"), int):
        raise ValueError("release sample seed missing")
    for entry in sample:
        group = entry.get("group")
        if not group:
            raise ValueError("sample row missing product group")
        sampled_per_group[str(group)] += 1
    if any(int(total) >= 30 and sampled_per_group.get(group, 0) < 8 for group, total in groups.items()):
        raise ValueError("release sample under-represents a group with at least 30 accepted rows")
    first_batch = release.get("first_batch_review")
    if (not isinstance(first_batch, dict) or first_batch.get("approved") is not True
            or first_batch.get("critical_defects") != 0
            or first_batch.get("rows_sha256") != first_batch_digest(ledger)
            or first_batch.get("reviewed_row_count") != min(150, len(ledger))
            or not first_batch.get("reviewer")):
        raise ValueError("clean first-150 review is required")
    if not release.get("reviewer"):
        raise ValueError("release reviewer missing")


def normalize_barcode_variants(code: str) -> set[str]:
    variants = set(get_barcode_lookup_variants(code))
    variants.add(code)
    stripped = code.lstrip("0")
    if stripped:
        variants.add(stripped)
        variants.add(stripped.zfill(12))
        variants.add(stripped.zfill(13))
    return variants


def load_apptance_records(
    apptance_dir: Path,
    front_dir: Path | None = None,
) -> dict[str, dict]:
    """Load curated selections as inputs; selection alone never grants acceptance.

    ``front_dir`` remains for caller compatibility but is intentionally unused:
    selected files are immutable evidence and must pass the normal gates.
    """
    if not apptance_dir.exists():
        return {}
    del front_dir

    records: dict[str, dict] = {}
    for path in sorted(apptance_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        stem = path.stem
        code = stem.replace("-front", "")
        if not code.isdigit():
            continue

        digest = hashlib.sha256(path.read_bytes()).hexdigest()

        record = {
            "state": "QA_RETURN",
            "reason": "curated selection requires current Q1-Q6 evidence",
            "selection_state": "USER_SELECTED",
            "source_path": str(path),
            "output_path": None,
            "barcode": code,
            "source_sha256": digest,
        }
        for variant in normalize_barcode_variants(code):
            records[variant] = record

    return records

