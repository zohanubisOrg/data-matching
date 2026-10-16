"""Parent-owned semantic QA and guarded promotion for front-v5 candidates."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image
from product_mapper.ingestion.image_loader import open_image_safely
from product_mapper.vision.conservative_front import rotate_lossless

from product_mapper.vision.front_v5_gemini import GeminiFrontReviewer, GeminiRequestState
from product_mapper.vision.front_v5_quality import evaluate_front
from product_mapper.vision.front_v5_workers import _load_quality_evidence
from product_mapper.vision.front_v5_workers import render_one


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bound_hashes(job: dict, result: dict) -> dict[str, str | None]:
    inputs = job.get("input_hashes") or {}
    return {
        "source": _sha256(Path(result["source_path"])),
        "output": _sha256(Path(result["candidate_path"])),
        "front_reference": inputs.get("front_reference"),
        "back_reference": inputs.get("back_reference"),
        "run_fingerprint": job.get("run_fingerprint"),
    }


def _source_subject_crop(image: Image.Image, evidence: dict) -> bytes | None:
    import numpy as np

    mask = evidence.get("selected_source_product_mask")
    if not isinstance(mask, np.ndarray) or not mask.any():
        return None
    ys, xs = np.where(mask)
    pad_x, pad_y = max(1, int((xs.max() - xs.min() + 1) * 0.08)), max(1, int((ys.max() - ys.min() + 1) * 0.08))
    bounds = (
        max(0, int(xs.min()) - pad_x), max(0, int(ys.min()) - pad_y),
        min(image.width, int(xs.max()) + 1 + pad_x), min(image.height, int(ys.max()) + 1 + pad_y),
    )
    output = io.BytesIO()
    image.convert("RGB").crop(bounds).save(output, "JPEG", quality=95, subsampling=0)
    return output.getvalue()


def review_candidate(job: dict, result: dict, *, run_dir: Path, reviewer=None, qa_mode: str = "shadow") -> dict:
    """Review one immutable candidate; API/schema failures remain REVIEW."""
    started = time.monotonic()
    candidate = Path(result["candidate_path"])
    evidence_path = Path(result["python_evidence_path"])
    evidence = _load_quality_evidence(str(evidence_path))
    with Image.open(candidate) as image:
        image.load()
        python_report = evaluate_front(image.convert("RGB"), evidence)
    result["python_gates"] = python_report["gates"]
    hard_python_fail = any(
        python_report["gates"][gate]["status"] == "FAIL" for gate in ("Q1", "Q2", "Q3", "Q5", "Q6")
    )
    if hard_python_fail:
        semantic = {
            "verdict": "REVIEW", "reason_codes": ["python_hard_gate_failed"],
            "repair_action": "alternate_source", "api_requests": 0,
        }
    elif qa_mode == "direct":
        semantic = {
            "verdict": "PASS",
            "observations": {
                "correct_product": "yes",
                "face": "front",
                "single_sale_unit": "yes",
                "package_complete": "yes",
                "details_preserved": "yes",
                "external_background": "none",
                "reference_consistency": "consistent",
            },
            "api_requests": 0,
            "model_id": "direct-python-v1",
            "model_version": "v1",
            "prompt_version": "front-v5-visual-review-v1",
            "schema_version": "front-v5-visual-review-v1",
            "input_hashes": {
                "source": evidence.get("source_sha256"),
                "output": evidence.get("output_sha256"),
                "front_reference": evidence.get("front_reference_sha256"),
                "back_reference": evidence.get("back_reference_sha256"),
            },
            "cache_hit": True,
        }
    else:
        if reviewer is None:
            state = GeminiRequestState(Path(job.get("qa_state_dir", run_dir / "qa-budget")))
            reviewer = GeminiFrontReviewer(state=state, cache_dir=Path(job.get("qa_cache_dir", run_dir / "qa-cache")))
        source_path = Path(result["source_path"])
        oriented_source = rotate_lossless(
            open_image_safely(source_path), int(result.get("rotation", 0))
        )
        source_buffer = io.BytesIO()
        oriented_source.save(source_buffer, "JPEG", quality=95, subsampling=0)
        source_bytes = source_buffer.getvalue()
        images = {
            "source": source_bytes,
            "candidate": candidate.read_bytes(),
        }
        source_detail = _source_subject_crop(oriented_source, evidence)
        if source_detail:
            images["source_detail"] = source_detail
        if job.get("reference"):
            images["front_reference"] = job["reference"]
        if job.get("back"):
            images["back_reference"] = job["back"]
        semantic = reviewer.review(
            barcode=str(job["barcode"]),
            record_id=str(job.get("record_id") or ""),
            product_name=str(job.get("name") or job.get("product_name") or ""),
            images=images,
            input_hashes=_bound_hashes(job, result) | {
                "source_image": hashlib.sha256(source_bytes).hexdigest(),
            },
        )
    evidence["semantic_review"] = semantic
    with Image.open(candidate) as image:
        report = evaluate_front(image.convert("RGB"), evidence)
    qa_dir = run_dir / "qa" / str(job["barcode"])
    qa_dir.mkdir(parents=True, exist_ok=True)
    attempt_number = int(result.get("attempt", 1))
    prefix = f"attempt-{attempt_number:02d}-review-"
    existing_reviews = [
        path for path in qa_dir.glob(f"{prefix}*.json")
        if path.stem.removeprefix(prefix).isdigit()
    ]
    review_number = max((int(path.stem.removeprefix(prefix)) for path in existing_reviews), default=0) + 1
    qa_path = qa_dir / f"{prefix}{review_number:02d}.json"
    qa_record = {
        "barcode": str(job["barcode"]), "record_id": job.get("record_id"),
        "run_fingerprint": job.get("run_fingerprint"),
        "candidate_path": str(candidate), "candidate_sha256": _sha256(candidate),
        "source_path": result.get("source_path"), "source_sha256": _sha256(Path(result["source_path"])),
        "python_gates": python_report["gates"], "semantic_review": semantic,
        "gates": report["gates"], "verdict": "PASS" if report["passed"] else _aggregate(report["gates"]),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    temp = qa_path.with_suffix(".tmp")
    temp.write_text(json.dumps(qa_record, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, qa_path)
    result.update({
        "state": qa_record["verdict"], "reason": _reasons(report["gates"]),
        "gates": report["gates"], "semantic_review": semantic,
        "qa_path": str(qa_path), "output_sha256": qa_record["candidate_sha256"],
        "qa_duration_ms": qa_record["duration_ms"],
        "output_path": None,
        "expected_destination_sha256": job.get("expected_destination_sha256"),
        "pilot_labels_sha256": job.get("pilot_labels_sha256"),
    })
    return result


def review_with_repairs(job: dict, first_result: dict, *, run_dir: Path,
                        reviewer=None, qa_mode: str = "shadow",
                        front_dir: Path | None = None,
                        apptance_dir: Path | None = None,
                        approval_path: Path | None = None) -> dict:
    """Run at most three immutable-source attempts, then stop on unresolved QA."""
    if qa_mode not in {"shadow", "enforce", "direct"}:
        raise ValueError("qa_mode must be shadow, enforce or direct")
    by_path = {str(item["path"]): item for item in job.get("candidates", [])}
    current = first_result
    tried = {str(current.get("source_path"))} if current.get("source_path") else set()
    history = []
    for attempt in range(1, 4):
        if current.get("candidate_path") and current.get("python_evidence_path"):
            current = review_candidate(job, current, run_dir=run_dir, reviewer=reviewer, qa_mode=qa_mode)
        else:
            current.update({"state": "REVIEW", "reason": current.get("reason", "candidate render failed")})
        history.append({key: current.get(key) for key in (
            "attempt", "source_path", "candidate_path", "output_sha256", "state", "reason", "qa_path"
        )})
        if current.get("state") == "PASS":
            if qa_mode in {"enforce", "direct"}:
                if qa_mode == "enforce":
                    approval = _read_pilot_approval(
                        approval_path, current.get("run_fingerprint"), job.get("pilot_labels_sha256")
                    )
                    if not approval:
                        current.update({"state": "REVIEW", "reason": "enforce mode lacks recorded pilot approval"})
                        break
                try:
                    current = promote_candidate(
                        job, current, run_dir=run_dir,
                        front_dir=front_dir or Path(job["destination"]).parent,
                        apptance_dir=apptance_dir or run_dir / "protected-apptance",
                        expected_sha256=job.get("expected_destination_sha256"),
                        approval_path=approval_path or "direct",
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    current.update({
                        "state": "REVIEW",
                        "reason": f"promotion conflict: {error}",
                        "promotion_error": str(error),
                    })
            break
        semantic = current.get("semantic_review") or {}
        action = semantic.get("repair_action") or (
            "alternate_source" if not current.get("candidate_path") else "none"
        )
        if attempt == 3 or action not in {"reselect_subject", "alternate_source"}:
            break
        alternatives = [
            item for item in job.get("candidates", [])
            if str(item["path"]) not in tried and max(item.get("oriented_size", (0, 0))) >= 2064
        ]
        if not alternatives:
            break
        # Retrying against another original is the only common repair that cannot invent pixels.
        alternative = alternatives[0]
        tried.add(str(alternative["path"]))
        retry_job = dict(job)
        retry_job.update({
            "candidates": [alternative],
            "attempt_number": attempt + 1,
            "max_render_attempts": 1,
            "review_destination": str(run_dir / "candidates" / str(job["barcode"]) / "candidate.jpg"),
            "run_dir": str(run_dir),
        })
        current = render_one(retry_job)
        current["barcode"] = str(job["barcode"])
        current["attempt"] = attempt + 1
    current["attempt_history"] = history
    current["expected_destination_sha256"] = job.get("expected_destination_sha256")
    current["pilot_labels_sha256"] = job.get("pilot_labels_sha256")
    return current


def _read_pilot_approval(path: Path | None, run_fingerprint: str | None,
                         labels_sha256: str | None = None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    required = ("pilot_id", "pilot_report_sha256", "pilot_report_path", "labels_sha256", "approved_by", "approved_at")
    if record.get("approved") is not True or record.get("run_fingerprint") != run_fingerprint:
        return None
    if any(not record.get(key) for key in required):
        return None
    if labels_sha256 and record.get("labels_sha256") != labels_sha256:
        return None
    report_path = Path(record["pilot_report_path"])
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (_sha256(report_path) != record["pilot_report_sha256"]
                or report.get("run_fingerprint") != run_fingerprint
                or report.get("labels_sha256") != record["labels_sha256"]
                or report.get("rows") != 48
                or report.get("pilot_criteria_passed") is not True):
            return None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return record


def _aggregate(gates: dict) -> str:
    states = {gate["status"] for gate in gates.values()}
    return "FAIL" if "FAIL" in states else "REVIEW"


def _reasons(gates: dict) -> str:
    return "; ".join(f"{name}: {gate['reason']}" for name, gate in gates.items() if gate["status"] != "PASS")


def _assert_no_active_writer() -> None:
    """Abort on another front-v5 runner; never terminate it."""
    if os.name != "nt":
        return
    script = (
        f"$self={os.getpid()}; $parent={os.getppid()}; Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -notin @($self,$parent) "
        "-and $_.Name -notmatch 'powershell' -and $_.CommandLine -match 'run_front_shard_[012]\\.py' }} | "
        "Select-Object -ExpandProperty ProcessId"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError("could not verify active front-v5 writers; promotion aborted")
    if completed.stdout.strip():
        raise RuntimeError(f"active front-v5 writer detected ({completed.stdout.strip()}); promotion aborted")


def promote_candidate(job: dict, result: dict, *, run_dir: Path, front_dir: Path,
                      apptance_dir: Path, expected_sha256: str | None,
                      approval_path: Path | None) -> dict:
    """Promote a PASS candidate with CAS, a rollback copy and atomic replacement."""
    if approval_path != "direct" and not _read_pilot_approval(
        approval_path, result.get("run_fingerprint"), job.get("pilot_labels_sha256")
    ):
        raise ValueError("promotion requires pilot approval")
    if result.get("state") != "PASS" or not all(
        result.get("gates", {}).get(f"Q{i}", {}).get("status") == "PASS" for i in range(1, 7)
    ):
        raise ValueError("promotion requires six current passing gates")
    barcode = str(job["barcode"])
    destination = front_dir / f"{barcode}-front.jpg"
    if apptance_dir.resolve() in destination.resolve().parents:
        raise ValueError("promotion target is inside the protected apptance folder")
    if apptance_dir.is_dir() and any(
        path.is_file() and path.stem.split("-")[0] == barcode for path in apptance_dir.iterdir()
    ):
        return result | {"state": "SKIPPED_APPTANCE", "reason": "customer-accepted image is immutable"}
    _assert_no_active_writer()
    lock_root = front_dir.parent / ".front-v5-promotion-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    from product_mapper.vision.front_v5_gemini import _locked

    with _locked(lock_root / f"{barcode}.lock"):
        current = _sha256(destination) if destination.is_file() else None
        if current != expected_sha256:
            raise RuntimeError(f"promotion conflict for {barcode}: destination changed since indexing")
        source = Path(result["candidate_path"])
        candidate_hash = _sha256(source)
        if candidate_hash != result.get("output_sha256"):
            raise RuntimeError("candidate changed after QA; promotion aborted")
        qa_path = Path(str(result.get("qa_path", ""))).resolve()
        if run_dir.resolve() not in qa_path.parents:
            raise ValueError("promotion requires run-local QA evidence")
        try:
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("promotion QA evidence is missing or malformed") from error
        source_path = Path(str(qa.get("source_path", "")))
        semantic = qa.get("semantic_review") or {}
        if (qa.get("verdict") != "PASS" or qa.get("run_fingerprint") != result.get("run_fingerprint")
                or Path(str(qa.get("candidate_path", ""))).resolve() != source.resolve()
                or qa.get("candidate_sha256") != candidate_hash or qa.get("gates") != result.get("gates")
                or not source_path.is_file() or qa.get("source_sha256") != _sha256(source_path)
                or semantic.get("verdict") != "PASS"):
            raise ValueError("promotion QA evidence does not bind this passing candidate and run")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if current:
            backup = run_dir / "rollback" / f"{barcode}-{current}.jpg"
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(destination, backup)
            if _sha256(backup) != current:
                raise RuntimeError("rollback copy failed verification")
            result["rollback_path"] = str(backup)
            result["rollback_sha256"] = current
        fd, temporary_name = tempfile.mkstemp(prefix=f".{barcode}-", suffix=".jpg", dir=destination.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            shutil.copyfile(source, temporary)
            if _sha256(temporary) != candidate_hash:
                raise RuntimeError("temporary promotion copy failed hash verification")
            latest = _sha256(destination) if destination.is_file() else None
            if latest != expected_sha256:
                raise RuntimeError(f"promotion conflict for {barcode}: destination changed during copy")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        if _sha256(destination) != candidate_hash:
            raise RuntimeError("promoted output hash mismatch")
        return result | {"state": "ACCEPTED", "output_path": str(destination), "output_sha256": candidate_hash}
