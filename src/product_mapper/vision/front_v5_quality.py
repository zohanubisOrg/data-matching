"""Fail-closed acceptance gates for front-v5 packshot candidates."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

import numpy as np
from PIL import Image

from product_mapper.vision.barcode_validator import validate_ean_upc_checksum

CANVAS_SIZE = 2400
PRODUCT_LONG_SIDE = 2064
PRODUCT_TOLERANCE = 2
MIN_MARGIN = 48


def _num(evidence: Mapping, key: str) -> float | None:
    value = evidence.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _mask(evidence: Mapping, key: str) -> np.ndarray | None:
    value = evidence.get(key)
    if not isinstance(value, np.ndarray) or value.dtype != np.bool_ or value.ndim != 2:
        return None
    return value


def _gate(ok: bool, reason: str, *, status: str | None = None, **measurements) -> dict:
    status = status or ("PASS" if ok else "FAIL")
    return {"passed": status == "PASS", "status": status, "reason": "pass" if ok else reason, "measurements": measurements}


def _bound_semantic(e: Mapping) -> tuple[dict | None, str | None]:
    semantic = e.get("semantic_review")
    if not isinstance(semantic, Mapping):
        return None, "semantic Gemini evidence is missing"
    if not all(semantic.get(key) for key in ("model_version", "prompt_version", "schema_version")):
        return None, "semantic Gemini version evidence is missing"
    observations = semantic.get("observations")
    if not isinstance(observations, Mapping):
        return None, "semantic Gemini observations are missing"
    inputs = semantic.get("input_hashes")
    expected = {
        "source": e.get("source_sha256"),
        "output": e.get("output_sha256"),
        "front_reference": e.get("front_reference_sha256"),
        "back_reference": e.get("back_reference_sha256"),
    }
    if not isinstance(inputs, Mapping) or any(inputs.get(key) != value for key, value in expected.items()):
        return None, "semantic Gemini evidence does not bind current source/output/references"
    return dict(observations), None


def _semantic_status(observations: dict | None, invalid_reason: str | None, fields: tuple[str, ...], fail_values: set[str]) -> tuple[str, str]:
    if invalid_reason or observations is None:
        return "REVIEW", invalid_reason or "semantic evidence missing"
    values = [observations.get(field) for field in fields]
    if any(value in fail_values for value in values):
        return "FAIL", "; ".join(f"{field}={observations.get(field)}" for field in fields if observations.get(field) in fail_values)
    if any(value is None or value in {"uncertain", "unavailable", "conflict"} for value in values):
        return "REVIEW", "; ".join(f"{field}={observations.get(field, 'missing')}" for field in fields if observations.get(field) in {None, "uncertain", "unavailable", "conflict"})
    return "PASS", "pass"


def _quality_gates(image: Image.Image, e: Mapping) -> dict[str, dict]:
    semantic, semantic_error = _bound_semantic(e)
    # Q1 — final canvas and clean white outside the retained envelope.
    product = _mask(e, "product_mask")
    envelope = _mask(e, "envelope_mask")
    q1_reasons = []
    if image.mode != "RGB" or image.size != (CANVAS_SIZE, CANVAS_SIZE):
        q1_reasons.append("canvas must be 2400x2400 RGB")
    if product is None or envelope is None or product.shape != (CANVAS_SIZE, CANVAS_SIZE) or envelope.shape != product.shape:
        q1_reasons.append("product/envelope masks missing or wrong-sized")
        outside_ratio, corner_min = 0.0, 0.0
    else:
        if not product.any() or np.any(product & ~envelope):
            q1_reasons.append("product must be nonempty and contained by envelope")
        pixels = np.asarray(image)
        outside = ~envelope
        white = np.all(pixels >= 250, axis=2)
        outside_ratio = float(white[outside].mean()) if outside.any() else 0.0
        tiles = [pixels[:64, :64], pixels[:64, -64:], pixels[-64:, :64], pixels[-64:, -64:]]
        corner_min = min(float(tile.mean()) for tile in tiles)
        if outside_ratio < 0.995 or corner_min < 253.0:
            q1_reasons.append("background/corners are below whiteness threshold")
    
    if semantic is not None and semantic.get("external_background") == "unwanted":
        q1_reasons.append("Gemini found unwanted external background")
    q1_status = "FAIL" if q1_reasons else (
        "REVIEW" if semantic_error or semantic is None or semantic.get("external_background") == "uncertain" else "PASS"
    )

    # Q2 — independent masks when available; otherwise hash-bound semantic review.
    core = _mask(e, "source_core_mask")
    selected = _mask(e, "selected_source_product_mask")
    q2_reasons = []
    coverage = 0.0
    masks_available = core is not None and selected is not None and core.shape == selected.shape and core.any()
    if masks_available:
        coverage = float(np.count_nonzero(core & selected) / np.count_nonzero(core))
        if coverage < 0.995:
            q2_reasons.append("selected mask does not cover the independent package core")
    holes = _num(e, "holes_ratio")
    if holes is not None and holes > 0.005:
        q2_reasons.append("excessive package-mask holes")
    if e.get("has_separation") is True:
        separation = _num(e, "separation_background_ratio")
        if separation is None or separation < 0.90:
            q2_reasons.append("separation lacks confirmed background-gap evidence")
    q2_semantic, q2_semantic_reason = _semantic_status(
        semantic, semantic_error, ("package_complete", "details_preserved"), {"no"}
    )
    if e.get("source_complete") is False or e.get("source_boundary_clear") is False:
        q2_semantic, q2_semantic_reason = "REVIEW", "source-boundary evidence conflicts with semantic review"
    q2_status = "FAIL" if q2_reasons or q2_semantic == "FAIL" else (
        "PASS" if q2_semantic == "PASS" and (masks_available or not q2_reasons) else "REVIEW"
    )

    # Q3 — one product, bounded envelope and residual fragments.
    q3_reasons = []
    units = e.get("unit_count")
    if units is not None and units != 1:
        q3_reasons.append("exactly one product unit required")
    retained = _num(e, "retained_background_fill")
    residual = _num(e, "residual_background_ratio")
    fragments = e.get("detached_fragment_ratios")
    retained_pixels = 0
    if product is not None and envelope is not None and product.shape == envelope.shape:
        retained_pixels = int(np.count_nonzero(envelope & ~product))
        if retained_pixels:
            py, px = np.where(product)
            ey, ex = np.where(envelope)
            product_long = max(int(px.max() - px.min() + 1), int(py.max() - py.min() + 1)) if len(px) else 0
            envelope_pad = max(
                int(px.min() - ex.min()), int(py.min() - ey.min()),
                int(ex.max() - px.max()), int(ey.max() - py.max()),
            ) if len(px) and len(ex) else CANVAS_SIZE
            if retained is None or retained < 0.90 or e.get("rectangular_envelope") is not True:
                q3_reasons.append("retained background must be rectangular and at least 90% filled")
            if product_long <= 0 or envelope_pad > round(product_long * 0.18):
                q3_reasons.append("retained envelope exceeds 18% maximum allowance")
    elif retained is not None and e.get("rectangular_envelope") is not False:
        q3_reasons.append("retained background/envelope evidence missing")
    if residual is not None and residual > 0.09:
        q3_reasons.append("residual background measurement exceeds threshold")
    if isinstance(fragments, list) and any(_num({"x": item}, "x") is None or float(item) > 0.01 for item in fragments):
        q3_reasons.append("detached fragments exceed threshold")
    q3_semantic, q3_semantic_reason = _semantic_status(
        semantic, semantic_error, ("single_sale_unit", "external_background"), {"no", "unwanted"}
    )
    if semantic is not None and semantic.get("external_background") == "allowed_behind_package" and retained is None:
        q3_semantic, q3_semantic_reason = "REVIEW", "retained clear-package background lacks a Python fill measurement"
    q3_status = "FAIL" if q3_reasons or q3_semantic == "FAIL" else (
        "PASS" if q3_semantic == "PASS" and (units in (None, 1)) else "REVIEW"
    )

    # Q4 — unique front match; no positional fallback; human evidence binds both files.
    q4_reasons = []
    q4_status = "REVIEW"
    q4_reason = semantic_error or "semantic evidence missing"
    if semantic is not None and semantic_error is None:
        q4_status, q4_reason = _semantic_status(
            semantic, None,
            ("correct_product", "face", "reference_consistency"),
            {"no", "back", "conflict"},
        )
        if e.get("front_reference_available") is not True:
            review = e.get("human_review")
            required = ("barcode", "record_id", "source_sha256", "output_sha256", "reviewer")
            bound = isinstance(review, Mapping) and review.get("approved") is True and not any(
                not review.get(key) for key in required
            ) and review.get("barcode") == e.get("catalog_barcode") and review.get("record_id") == e.get("catalog_record_id") and review.get("source_sha256") == e.get("source_sha256") and review.get("output_sha256") == e.get("output_sha256")
            if not bound:
                q4_status, q4_reason = "REVIEW", "missing front reference requires hash-bound human approval"
        # Apply numeric identity scores only when a complete, measured score set exists.
        face, runner = _num(e, "face_score"), _num(e, "runner_up_score")
        if face is not None and runner is not None:
            method = e.get("score_method")
            floor, margin = (0.08, 0.05) if method == "feature" else (0.12, 0.06)
            if q4_status == "PASS" and (face < floor or face - runner < margin):
                q4_status, q4_reason = "REVIEW", "measured front score is weak or non-unique"
            back = _num(e, "back_score") if e.get("back_reference_available") is True else None
            if q4_status == "PASS" and back is not None and face <= back:
                q4_status, q4_reason = "REVIEW", "measured candidate score does not beat back reference"

    # Q5 — scale from complete product geometry and verified saved JPEG.
    q5_reasons = []
    bbox = e.get("canvas_product_bbox")
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in bbox):
        q5_reasons.append("product bbox missing")
        width = height = 0.0
        margins = (0.0, 0.0, 0.0, 0.0)
    else:
        x0, y0, x1, y1 = map(float, bbox)
        width, height = x1 - x0, y1 - y0
        margins = (x0, y0, CANVAS_SIZE - x1, CANVAS_SIZE - y1)
        if width <= 0 or height <= 0 or min(margins) < MIN_MARGIN:
            q5_reasons.append("product geometry invalid or canvas margin under 48px")
    product_long = max(width, height)
    native_long, scale = _num(e, "source_product_long_side"), _num(e, "scale")
    expected_target = PRODUCT_LONG_SIDE if native_long is not None and native_long >= PRODUCT_LONG_SIDE else native_long
    if (native_long is None or scale is None or scale <= 0 or scale > 1
            or expected_target is None
            or not expected_target - PRODUCT_TOLERANCE <= product_long <= expected_target + PRODUCT_TOLERANCE
            or abs(product_long - native_long * scale) > PRODUCT_TOLERANCE):
        q5_reasons.append("native/output product scale violates target or would upscale")
    aspect, rotation = _num(e, "aspect_ratio_error"), e.get("rotation")
    if aspect is None or aspect > 0.005 or rotation not in (0, 90, 180, 270):
        q5_reasons.append("aspect ratio or lossless rotation evidence invalid")
    if (e.get("saved_file_verified") is not True or e.get("saved_format") != "JPEG"
            or e.get("jpeg_quality") != 95 or e.get("jpeg_subsampling") not in ("4:4:4", 0)
            or image.mode != "RGB"):
        q5_reasons.append("saved RGB JPEG settings/file verification invalid")

    # Q6 — exact catalog identity, run provenance and content hashes.
    q6_reasons = []
    barcode = str(e.get("catalog_barcode", ""))
    if (not barcode or barcode != str(e.get("filename_barcode", ""))
            or not validate_ean_upc_checksum(barcode)
            or not e.get("catalog_record_id") or e.get("catalog_record_id") != e.get("result_record_id")
            or e.get("identity_conflict") is not False):
        q6_reasons.append("catalog identity is missing, conflicting or invalid")
    sha = re.compile(r"^[0-9a-f]{64}$")
    if any(not isinstance(e.get(key), str) or not sha.fullmatch(e[key]) for key in ("source_sha256", "output_sha256")):
        q6_reasons.append("source/output SHA-256 missing or invalid")
    if (not isinstance(e.get("run_fingerprint"), str) or not sha.fullmatch(e["run_fingerprint"])
            or e.get("run_fingerprint") != e.get("expected_run_fingerprint")):
        q6_reasons.append("result fingerprint does not match current inputs and configuration")

    return {
        "Q1": _gate(not q1_reasons and q1_status == "PASS", "; ".join(q1_reasons) or semantic_error or "semantic background state unresolved", status=q1_status, outside_white_ratio=outside_ratio, minimum_corner_mean=corner_min),
        "Q2": _gate(q2_status == "PASS", "; ".join(q2_reasons) or q2_semantic_reason, status=q2_status, core_coverage=coverage),
        "Q3": _gate(q3_status == "PASS", "; ".join(q3_reasons) or q3_semantic_reason, status=q3_status, unit_count=units, retained_background_pixels=retained_pixels, retained_background_fill=retained, residual_background_ratio=residual),
        "Q4": _gate(q4_status == "PASS", q4_reason, status=q4_status),
        "Q5": _gate(not q5_reasons, "; ".join(q5_reasons), product_bbox=bbox, product_long_side=product_long, margins=margins, scale=scale),
        "Q6": _gate(not q6_reasons, "; ".join(q6_reasons)),
    }


def evaluate_front(image: Image.Image, evidence: Mapping) -> dict:
    """Return auditable Q1-Q6 results. Missing evidence always fails its gate."""
    if not isinstance(evidence, Mapping):
        evidence = {}
    gates = _quality_gates(image, evidence)
    return {"passed": all(gate["passed"] for gate in gates.values()), "gates": gates}
