"""Process-pool workers for the front-v5 batch. Importable on Windows."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pillow_heif
from PIL import Image

from product_mapper.ingestion.image_loader import open_image_safely
from product_mapper.vision.barcode_side_splitter import transform_point
from product_mapper.vision.conservative_front import (
    FrontRejected,
    best_hit,
    border_median,
    foreground_mask,
    output_is_clean,
    preview,
    read_barcodes,
    render_panel,
    rotate_lossless,
    select_front_package,
)
from product_mapper.vision.front_v5_ledger import index_fields
from product_mapper.vision.front_v5_quality import evaluate_front

pillow_heif.register_heif_opener()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_one(path_str: str) -> dict:
    path = Path(path_str)
    try:
        image = open_image_safely(path)
        hit = best_hit(read_barcodes(image))
        return index_fields(
            path,
            _sha256(path),
            image.size,
            None if hit is None else hit.text,
            0 if hit is None else hit.upright_ccw,
        ) | {
            "barcode_cx": None if hit is None else hit.cx,
            "barcode_cy": None if hit is None else hit.cy,
        }
    except Exception:
        return index_fields(path, _sha256(path), (0, 0), None, 0) | {
            "barcode_cx": None,
            "barcode_cy": None,
        }


def _rgb_bytes(payload: bytes | None) -> np.ndarray | None:
    if not payload:
        return None
    with Image.open(io.BytesIO(payload)) as image:
        return np.asarray(image.convert("RGB"))


def _load_quality_evidence(manifest_path: str) -> dict:
    """Load numeric QA evidence and source-aligned masks from a run's qa folder."""
    manifest = Path(manifest_path).resolve()
    if not manifest.is_file():
        return {}
    try:
        evidence = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid QA evidence manifest: {manifest}") from error
    if not isinstance(evidence, dict):
        raise ValueError("QA evidence manifest must contain an object")
    mask_files = evidence.pop("mask_files", {})
    if not isinstance(mask_files, dict):
        raise ValueError("mask_files must contain an object")
    allowed_masks = {
        "product_mask", "envelope_mask", "source_core_mask",
        "selected_source_product_mask",
    }
    root = manifest.parent.resolve()
    for key, relative_path in mask_files.items():
        if key not in allowed_masks or not isinstance(relative_path, str):
            raise ValueError(f"unsupported QA mask entry: {key}")
        path = (root / relative_path).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"QA mask must be a file under {root}: {relative_path}")
        with Image.open(path) as image:
            evidence[key] = np.asarray(image.convert("L")) > 127
    return evidence


def _save_quality_evidence(path: Path, evidence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    masks = {}
    serializable = {}
    mask_root = path.parent / f"{path.stem}-masks"
    for key, value in evidence.items():
        if isinstance(value, np.ndarray) and value.dtype == np.bool_ and value.ndim == 2:
            mask_root.mkdir(parents=True, exist_ok=True)
            mask_path = mask_root / f"{key}.png"
            Image.fromarray(value.astype(np.uint8) * 255).save(mask_path)
            masks[key] = str(mask_path.relative_to(path.parent))
        else:
            serializable[key] = value
    serializable["mask_files"] = masks
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(serializable, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _rotate_quality_masks(evidence: dict, image_size: tuple[int, int], rotation: int) -> dict:
    width, height = image_size
    for key in ("source_core_mask", "selected_source_product_mask"):
        mask = evidence.get(key)
        if isinstance(mask, np.ndarray) and mask.shape == (height, width):
            evidence[key] = np.rot90(mask, k=(rotation // 90) % 4).copy()
    return evidence


def render_one(payload: dict) -> dict:
    destination = Path(payload["destination"])
    metadata = {
        "run_fingerprint": payload.get("run_fingerprint"),
        "input_hashes": payload.get("input_hashes"),
        "candidate_set_sha256": payload.get("candidate_set_sha256"),
    }
    last = {"state": "CUSTOMER_RESHOOT", "reason": "no usable original", "source_path": None} | metadata
    attempts = max(1, min(3, int(payload.get("max_render_attempts", 3))))
    first_attempt = max(1, min(3, int(payload.get("attempt_number", 1))))
    for attempt, candidate in enumerate(payload["candidates"][:attempts], start=first_attempt):
        try:
            image = open_image_safely(candidate["path"])
            rotation = int(candidate["rotation"])
            evidence = _load_quality_evidence(payload.get("quality_evidence_path", ""))
            evidence = _rotate_quality_masks(evidence, image.size, rotation)
            center = None
            if candidate.get("barcode_cx") is not None:
                center = transform_point(
                    float(candidate["barcode_cx"]),
                    float(candidate["barcode_cy"]),
                    image.size[0],
                    image.size[1],
                    rotation,
                )
            image = rotate_lossless(image, rotation)
            small, scale = preview(image)
            rgb = np.asarray(small)
            median = border_median(rgb)
            mask = foreground_mask(rgb, median)
            barcode_xy = None if center is None else (center[0] * scale, center[1] * scale)
            reference = _rgb_bytes(payload.get("reference"))
            back = _rgb_bytes(payload.get("back"))
            box, front_mask = select_front_package(rgb, barcode_xy, reference, back, review=True)
            full_box = tuple(int(round(value / scale)) for value in box)
            full_mask = np.array(Image.fromarray(front_mask).resize(image.size, Image.Resampling.NEAREST))
            output, metrics = render_panel(
                image, full_box, median, package_mask=full_mask, strict_geometry=True
            )
            candidate_base = Path(payload.get("review_destination") or destination)
            destination = candidate_base.with_name(f"{candidate_base.stem}-attempt-{attempt:02d}.jpg")
            if payload.get("run_dir"):
                run_root = Path(payload["run_dir"]).resolve()
                if run_root not in destination.resolve().parents:
                    raise ValueError("candidate destination must stay inside its run directory")
            elif payload.get("front_dir") and destination.resolve().parent == Path(payload["front_dir"]).resolve():
                raise ValueError("worker may not write a candidate into the delivery directory")
            elif not payload.get("review_destination"):
                raise ValueError("worker requires a private candidate destination")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_destination = destination.with_name(destination.stem + f".{attempt}.tmp.jpg")
            output.save(temp_destination, "JPEG", quality=95, subsampling=0)
            temp_digest = _sha256(temp_destination)
            if destination.exists():
                if _sha256(destination) != temp_digest:
                    temp_destination.unlink()
                    raise RuntimeError(f"immutable attempt path already contains different bytes: {destination}")
                temp_destination.unlink()
            else:
                temp_destination.replace(destination)
            digest = _sha256(destination)
            canvas_product = np.zeros((2400, 2400), dtype=bool)
            canvas_envelope = np.zeros_like(canvas_product)
            offset_x, offset_y = metrics["offset"]
            placed_w, placed_h = metrics["placed_size"]
            x0, y0, x1, y1 = metrics["source_envelope_bbox"]
            panel_mask = Image.fromarray((full_mask[y0:y1, x0:x1] > 0).astype(np.uint8) * 255)
            panel_mask = panel_mask.resize((placed_w, placed_h), Image.Resampling.NEAREST)
            placed_mask = np.asarray(panel_mask) > 127
            left, top = max(0, offset_x), max(0, offset_y)
            right, bottom = min(2400, offset_x + placed_w), min(2400, offset_y + placed_h)
            if right <= left or bottom <= top:
                raise ValueError("rendered envelope lies outside the output canvas")
            source_left, source_top = left - offset_x, top - offset_y
            canvas_envelope[top:bottom, left:right] = True
            canvas_product[top:bottom, left:right] = placed_mask[
                source_top:source_top + bottom - top, source_left:source_left + right - left
            ]
            source_core = evidence.get("source_core_mask")
            selected_source = evidence.get("selected_source_product_mask")
            selected_source = full_mask.astype(bool) if selected_source is None else selected_source
            rendered_pixels = np.asarray(output)
            retained_pixels = canvas_envelope & ~canvas_product
            retained_fill = (
                float(np.any(rendered_pixels < 250, axis=2)[retained_pixels].mean())
                if retained_pixels.any() else None
            )
            evidence.update({
                "product_mask": canvas_product,
                "envelope_mask": canvas_envelope,
                "selected_source_product_mask": selected_source,
                "source_core_mask": source_core,
                "retained_background_fill": retained_fill,
                "rectangular_envelope": True,
                "catalog_barcode": payload.get("barcode"),
                "filename_barcode": payload.get("barcode"),
                "catalog_record_id": payload.get("record_id"),
                "result_record_id": payload.get("record_id"),
                "identity_conflict": payload.get("identity_conflict", False),
                "source_sha256": candidate.get("sha256"),
                "output_sha256": digest,
                "run_fingerprint": payload.get("run_fingerprint"),
                "expected_run_fingerprint": payload.get("run_fingerprint"),
                "source_product_long_side": metrics.get("native_long_side"),
                "scale": metrics.get("scale"),
                "canvas_product_bbox": metrics.get("canvas_product_bbox"),
                "front_reference_available": bool(payload.get("reference")),
                "back_reference_available": bool(payload.get("back")),
                "front_reference_sha256": payload.get("input_hashes", {}).get("front_reference"),
                "back_reference_sha256": payload.get("input_hashes", {}).get("back_reference"),
                "aspect_ratio_error": 0.0,
                "rotation": rotation % 360,
                "saved_format": "JPEG",
                "jpeg_quality": 95,
                "jpeg_subsampling": "4:4:4",
                "saved_file_verified": _verify_saved_jpeg(destination),
            })
            with Image.open(destination) as saved:
                saved.load()
                quality = evaluate_front(saved.convert("RGB"), evidence)
            evidence_path = destination.with_suffix(".python.json")
            if evidence_path.is_file():
                prior_evidence = _load_quality_evidence(str(evidence_path))
                if (prior_evidence.get("source_sha256") != evidence.get("source_sha256")
                        or prior_evidence.get("output_sha256") != digest
                        or prior_evidence.get("run_fingerprint") != payload.get("run_fingerprint")):
                    raise RuntimeError("immutable attempt evidence does not match this render")
            else:
                _save_quality_evidence(evidence_path, evidence)
            return {
                "state": "CANDIDATE",
                "reason": "awaiting Python/Gemini QA",
                "source_path": candidate["path"],
                "rotation": rotation % 360,
                "candidate_path": str(destination),
                "python_evidence_path": str(evidence_path),
                "attempt": attempt,
                "native_long_side": metrics["native_long_side"],
                "scale": metrics["scale"],
                "output_sha256": digest,
                "gates": quality["gates"],
                "run_fingerprint": payload.get("run_fingerprint"),
                "input_hashes": payload.get("input_hashes"),
                "candidate_set_sha256": payload.get("candidate_set_sha256"),
            }
        except FrontRejected as error:
            last = {"state": error.state, "reason": error.reason, "source_path": candidate["path"]} | metadata
        except Exception as error:
            last = {"state": "BLOCKED_INCOMPLETE_EDGE", "reason": str(error), "source_path": candidate["path"]} | metadata
    return last


def _verify_saved_jpeg(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.load()
            return image.format == "JPEG" and image.mode == "RGB" and image.size == (2400, 2400)
    except (OSError, ValueError):
        return False
