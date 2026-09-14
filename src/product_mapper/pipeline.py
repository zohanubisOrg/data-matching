from __future__ import annotations

from collections import Counter
from pathlib import Path
import logging
import time

from .config import DEFAULT_IMAGES, DEFAULT_IMPORTS, DEFAULT_OUTPUT, DEFAULT_POS
from .ingestion.capture_group import group_product_images, preferred_ocr_images
from .ingestion.image_loader import load_images
from .ingestion.pos_loader import load_pos
from .ingestion.supplier_loader import load_imports
from .matching.image_deterministic import (
    find_ocr_review_candidates,
    match_filename_deterministic,
    ocr_conflict_reason,
)
from .matching.knowledge_base import load_knowledge_base
from .matching.product_index import ProductEvidenceIndex
from .models import DataQualityIssue, MatchCandidate, MatchResult, POSProduct, ProductImage
from .reporting.excel_report import write_reports
from .reporting.html_report import write_html
from .reporting.image_exporter import export_standard_deliverables
from .reporting.profile_report import profile_workbooks, write_profile
from .vision.barcode_reader import BarcodeReader
from .vision.barcode_utils import (
    barcode_lookup_keys,
    canonical_gtin14,
    choose_barcode_consensus,
    is_gtin_like,
    normalize_barcode,
    validate_gtin,
)
from .vision.provider import ImageAttributes, NoOpVisionProvider, VisionProvider


BarcodeIndex = dict[str, list[POSProduct]]


def configure_logging(output: Path, verbose: bool = False) -> logging.Logger:
    output.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("product_mapper")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(output / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    if verbose:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        logger.addHandler(console)
    return logger


def build_ocr_provider(name: str) -> VisionProvider:
    normalized = str(name or "none").strip().casefold()
    if normalized in {"", "none", "off", "disabled"}:
        return NoOpVisionProvider()
    if normalized == "paddle":
        from .vision.paddle_ocr import PaddleOCRProvider

        return PaddleOCRProvider()
    raise ValueError(f"unsupported OCR provider: {name!r}; expected 'none' or 'paddle'")


def build_barcode_index(products: list[POSProduct]) -> BarcodeIndex:
    """Build exact and standards-equivalent deterministic POS barcode keys once."""
    index: BarcodeIndex = {}
    for product in products:
        for key in barcode_lookup_keys(product.barcode):
            bucket = index.setdefault(key, [])
            if all(existing.product_id != product.product_id for existing in bucket):
                bucket.append(product)
    return index


def _barcode_hits(
    value: str,
    products: list[POSProduct],
    barcode_index: BarcodeIndex | None = None,
) -> list[POSProduct]:
    keys = barcode_lookup_keys(value)
    if not keys:
        return []

    found: dict[str, POSProduct] = {}
    if barcode_index is not None:
        for key in keys:
            for product in barcode_index.get(key, []):
                found[product.product_id] = product
        return [found[key] for key in sorted(found)]

    query_keys = set(keys)
    for product in products:
        if query_keys.intersection(barcode_lookup_keys(product.barcode)):
            found[product.product_id] = product
    return [found[key] for key in sorted(found)]


def _candidate(product: POSProduct, evidence: str) -> MatchCandidate:
    return MatchCandidate(product=product, score=1.0, name_score=1.0, evidence=[evidence])


def _review(
    image: ProductImage,
    method: str,
    reason: str,
    products: list[POSProduct] | None = None,
    evidence: list[str] | None = None,
) -> MatchResult:
    top = [_candidate(product, reason) for product in (products or [])]
    return MatchResult(
        image=image,
        status="NEED_REVIEW",
        candidate=None,
        top_candidates=top,
        confidence=0.0,
        top2_score=0.0,
        margin=0.0,
        match_method=method,
        reason=reason,
        evidence=evidence or [],
    )


def _analyze_ocr(provider: VisionProvider, image: ProductImage) -> ImageAttributes:
    try:
        return provider.analyze(image.path)
    except Exception as exc:
        return ImageAttributes(warnings=[f"ocr_provider_failed:{type(exc).__name__}"])


def _analyze_capture_ocr(provider: VisionProvider, images: list[ProductImage]) -> ImageAttributes:
    """Read front-label OCR first, falling back to one alternate image only if empty.

    This keeps ingredient/nutrition text on the back from contaminating a successful
    front-label identity while still recovering OCR evidence when the front is unreadable.
    """
    lines = []
    warnings: list[str] = []
    primary = preferred_ocr_images(images)

    for image in primary:
        evidence = _analyze_ocr(provider, image)
        lines.extend(evidence.ocr_lines)
        warnings.extend(f"{image.filename}:{warning}" for warning in evidence.warnings)

    if lines:
        return ImageAttributes(ocr_lines=lines, warnings=warnings)

    primary_paths = {image.path for image in primary}
    fallback = next((image for image in images if image.path not in primary_paths), None)
    if fallback is not None:
        evidence = _analyze_ocr(provider, fallback)
        lines.extend(evidence.ocr_lines)
        warnings.extend(f"{fallback.filename}:{warning}" for warning in evidence.warnings)

    return ImageAttributes(ocr_lines=lines, warnings=warnings)


def _select_capture_barcode(values: list[str]) -> str | None:
    normalized = [normalize_barcode(value) for value in values]
    normalized = [value for value in normalized if value]
    valid_gtins = [value for value in normalized if is_gtin_like(value) and validate_gtin(value)]
    canonical_valid = {canonical_gtin14(value) for value in valid_gtins}
    canonical_valid.discard(None)
    if len(canonical_valid) > 1:
        return None
    if len(canonical_valid) == 1:
        target = next(iter(canonical_valid))
        equivalent = [value for value in valid_gtins if canonical_gtin14(value) == target]
        return choose_barcode_consensus(equivalent) or equivalent[0]
    return choose_barcode_consensus(normalized)


def _observed_values(evidence: ImageAttributes) -> list[str]:
    values = list(evidence.barcode_candidates)
    if evidence.barcode:
        values.append(evidence.barcode)
    result: list[str] = []
    for value in values:
        normalized = normalize_barcode(value)
        if normalized:
            result.append(normalized)
    return result


def _analyze_capture_barcodes(
    reader: BarcodeReader | VisionProvider,
    images: list[ProductImage],
) -> ImageAttributes:
    """Decode back images first and skip redundant front decoding after strong evidence."""
    values: list[str] = []
    warnings: list[str] = []
    backs = [image for image in images if image.image_side == "back"]
    remaining = [image for image in images if image not in backs]
    phases = [backs, remaining] if backs else [remaining]

    for phase_index, phase in enumerate(phases):
        for image in phase:
            try:
                evidence = reader.analyze(image.path)
            except Exception as exc:
                warnings.append(f"{image.filename}:barcode_reader_failed:{type(exc).__name__}")
                continue
            values.extend(_observed_values(evidence))
            warnings.extend(f"{image.filename}:{warning}" for warning in evidence.warnings)

        if phase_index == 0 and backs:
            valid_canonical = {
                canonical_gtin14(value)
                for value in values
                if is_gtin_like(value) and validate_gtin(value)
            }
            valid_canonical.discard(None)
            # One valid barcode from the intentional back-side capture is enough;
            # front OCR later provides an independent product-label cross-check.
            if len(valid_canonical) >= 1:
                break

    barcode = _select_capture_barcode(values)
    checksum_valid = validate_gtin(barcode) if barcode and is_gtin_like(barcode) else None
    return ImageAttributes(
        barcode=barcode,
        barcode_candidates=values,
        barcode_checksum_valid=checksum_valid,
        warnings=warnings,
    )


def _copy_result_for_images(result: MatchResult, images: list[ProductImage]) -> list[MatchResult]:
    return [result.model_copy(update={"image": image}) for image in images]


def _meaningful_filename_image(images: list[ProductImage]) -> ProductImage | None:
    return next((image for image in images if (image.raw_name or image.normalized_name).strip()), None)


def _barcode_evidence_label(decoded: str, selected: POSProduct) -> str:
    selected_barcode = normalize_barcode(selected.barcode)
    if decoded == selected_barcode:
        return f"exact validated decoded POS barcode: {decoded}"
    if canonical_gtin14(decoded) and canonical_gtin14(decoded) == canonical_gtin14(selected_barcode):
        return f"validated standards-equivalent GTIN: image={decoded} POS={selected_barcode}"
    return f"validated deterministic barcode resolution: image={decoded} POS={selected_barcode}"


def _resolve_capture_from_evidence(
    images: list[ProductImage],
    products: list[POSProduct],
    barcode_evidence: ImageAttributes,
    ocr_provider: VisionProvider,
    top_k: int,
    barcode_index: BarcodeIndex | None,
    evidence_index: ProductEvidenceIndex | None,
) -> MatchResult:
    representative = images[0]

    if barcode_evidence.barcode:
        decoded = normalize_barcode(barcode_evidence.barcode)
        gtin_like = is_gtin_like(decoded)
        checksum_valid = (
            barcode_evidence.barcode_checksum_valid
            if barcode_evidence.barcode_checksum_valid is not None
            else (validate_gtin(decoded) if gtin_like else None)
        )

        if gtin_like and checksum_valid is False:
            return _review(
                representative,
                "barcode_conflict",
                "INVALID_GTIN_CHECK_DIGIT",
                evidence=[f"decoded barcode rejected: {decoded}", *barcode_evidence.warnings],
            )

        hits = _barcode_hits(decoded, products, barcode_index)
        if not hits:
            return _review(
                representative,
                "barcode_conflict",
                "BARCODE_NOT_FOUND_IN_POS",
                evidence=[f"decoded barcode not present in POS: {decoded}", *barcode_evidence.warnings],
            )
        if len(hits) > 1:
            return _review(
                representative,
                "barcode_conflict",
                "DUPLICATE_OR_EQUIVALENT_POS_BARCODE",
                hits,
                [f"decoded barcode resolves to multiple POS rows: {decoded}", *barcode_evidence.warnings],
            )
        if not gtin_like:
            return _review(
                representative,
                "barcode_conflict",
                "UNVALIDATED_NON_GTIN_BARCODE",
                hits,
                [f"exact non-GTIN barcode requires review: {decoded}", *barcode_evidence.warnings],
            )

        selected = hits[0]
        ocr_evidence = _analyze_capture_ocr(ocr_provider, images)
        if ocr_evidence.ocr_lines:
            conflict = ocr_conflict_reason(
                ocr_evidence.ocr_lines,
                selected,
                products,
                evidence_index=evidence_index,
            )
            if conflict:
                ocr_candidates = find_ocr_review_candidates(
                    ocr_evidence.ocr_lines,
                    products,
                    top_k=top_k,
                    evidence_index=evidence_index,
                )
                candidates = [selected] + [
                    item.product for item in ocr_candidates if item.product.product_id != selected.product_id
                ]
                return _review(
                    representative,
                    "barcode_ocr_conflict",
                    conflict,
                    candidates[: max(1, top_k)],
                    [
                        _barcode_evidence_label(decoded, selected),
                        "front-label OCR exact identity conflicts with barcode-selected product",
                        *ocr_evidence.warnings,
                    ],
                )

        evidence_text = _barcode_evidence_label(decoded, selected)
        candidate = _candidate(selected, evidence_text)
        return MatchResult(
            image=representative,
            status="AUTO_MATCHED",
            candidate=candidate,
            top_candidates=[candidate],
            confidence=1.0,
            top2_score=0.0,
            margin=1.0,
            match_method="exact_barcode",
            reason="unique checksum-valid barcode/GTIN resolved to one POS identity",
            evidence=[*candidate.evidence, *barcode_evidence.warnings],
        )

    if barcode_evidence.barcode_candidates:
        distinct = sorted({normalize_barcode(value) for value in barcode_evidence.barcode_candidates if value})
        valid_canonical = {
            canonical_gtin14(value)
            for value in distinct
            if is_gtin_like(value) and validate_gtin(value)
        }
        valid_canonical.discard(None)
        reason = "MULTIPLE_VALID_GTIN_VALUES" if len(valid_canonical) > 1 else "AMBIGUOUS_BARCODE_DECODE"
        return _review(
            representative,
            "barcode_conflict",
            reason,
            evidence=["decoded values: " + " | ".join(distinct), *barcode_evidence.warnings],
        )

    filename_image = _meaningful_filename_image(images)
    filename_result = (
        match_filename_deterministic(filename_image, products, evidence_index=evidence_index)
        if filename_image is not None
        else None
    )
    if filename_result is not None and filename_result.status == "AUTO_MATCHED":
        return filename_result.model_copy(update={"image": representative})

    ocr_evidence = _analyze_capture_ocr(ocr_provider, images)
    ocr_candidates = find_ocr_review_candidates(
        ocr_evidence.ocr_lines,
        products,
        top_k=top_k,
        evidence_index=evidence_index,
    )
    if ocr_candidates:
        return MatchResult(
            image=representative,
            status="NEED_REVIEW",
            candidate=None,
            top_candidates=ocr_candidates,
            confidence=0.0,
            match_method="deterministic_ocr_review",
            reason="exact OCR evidence produced deterministic review candidates",
            evidence=[
                "OCR candidates use canonical exact tokens/family/size rules only",
                *barcode_evidence.warnings,
                *ocr_evidence.warnings,
            ],
        )

    if filename_result is not None:
        return filename_result.model_copy(update={"image": representative})

    return MatchResult(
        image=representative,
        status="UNMATCHED",
        confidence=0.0,
        match_method="none",
        reason="no deterministic barcode, filename or OCR candidate",
        evidence=[*barcode_evidence.warnings, *ocr_evidence.warnings],
    )


def resolve_capture_evidence(
    images: list[ProductImage],
    products: list[POSProduct],
    barcode_reader: BarcodeReader | VisionProvider,
    ocr_provider: VisionProvider | None = None,
    top_k: int = 3,
    barcode_index: BarcodeIndex | None = None,
    evidence_index: ProductEvidenceIndex | None = None,
) -> list[MatchResult]:
    """Resolve one physical product capture and assign the decision to all its images."""
    if not images:
        return []
    ocr_provider = ocr_provider or NoOpVisionProvider()
    barcode_evidence = _analyze_capture_barcodes(barcode_reader, images)
    result = _resolve_capture_from_evidence(
        images=images,
        products=products,
        barcode_evidence=barcode_evidence,
        ocr_provider=ocr_provider,
        top_k=top_k,
        barcode_index=barcode_index,
        evidence_index=evidence_index,
    )
    return _copy_result_for_images(result, images)


def resolve_image_evidence(
    image: ProductImage,
    products: list[POSProduct],
    barcode_reader: BarcodeReader | VisionProvider,
    ocr_provider: VisionProvider | None = None,
    top_k: int = 3,
    barcode_index: BarcodeIndex | None = None,
    evidence_index: ProductEvidenceIndex | None = None,
) -> MatchResult:
    """Backward-compatible single-image wrapper around capture resolution."""
    return resolve_capture_evidence(
        [image],
        products,
        barcode_reader,
        ocr_provider,
        top_k,
        barcode_index,
        evidence_index,
    )[0]


def _human_group_result(
    images: list[ProductImage],
    products: list[POSProduct],
    kb: dict[str, dict[str, str]],
    filename_counts: Counter[str],
    barcode_index: BarcodeIndex,
) -> list[MatchResult] | None:
    """Apply human decisions only when filename keys are globally unambiguous."""
    entries = [
        kb[image.filename]
        for image in images
        if filename_counts[image.filename.casefold()] == 1 and image.filename in kb
    ]
    if not entries:
        return None

    approved = {normalize_barcode(entry.get("barcode")) for entry in entries if entry.get("barcode")}
    no_match = any(entry.get("selection") == "No Match" for entry in entries)
    representative = images[0]

    if len(approved) == 1 and not no_match:
        approved_barcode = next(iter(approved))
        hits = _barcode_hits(approved_barcode, products, barcode_index)
        if len(hits) == 1:
            candidate = _candidate(hits[0], "human-approved decision from knowledge base")
            result = MatchResult(
                image=representative,
                status="AUTO_MATCHED",
                candidate=candidate,
                top_candidates=[candidate],
                confidence=1.0,
                top2_score=0.0,
                margin=1.0,
                match_method="exact_human_approved",
                reason="human verified mapping",
                evidence=candidate.evidence,
            )
        else:
            result = _review(
                representative,
                "human_approved_conflict",
                "approved barcode is missing or non-unique in current POS",
                hits,
            )
        return _copy_result_for_images(result, images)

    if no_match and not approved:
        result = MatchResult(
            image=representative,
            status="UNMATCHED",
            confidence=0.0,
            match_method="exact_human_approved",
            reason="human confirmed no match",
        )
        return _copy_result_for_images(result, images)

    result = _review(
        representative,
        "human_approved_conflict",
        "conflicting human decisions within one product capture",
        evidence=["approved barcodes: " + " | ".join(sorted(approved))] if approved else [],
    )
    return _copy_result_for_images(result, images)


def run(
    images: list[Path] | None = None,
    pos: Path = DEFAULT_POS,
    imports: Path = DEFAULT_IMPORTS,
    output: Path = DEFAULT_OUTPUT,
    auto_threshold: float = .80,
    review_threshold: float = .60,
    top_k: int = 3,
    verbose: bool = False,
    ocr_provider: str = "none",
) -> dict:
    """Run the strict production image reconciliation pipeline.

    auto_threshold/review_threshold remain only for Python API compatibility and are
    ignored by the strict deterministic production path.
    """
    started = time.perf_counter()
    images = images or DEFAULT_IMAGES
    logger = configure_logging(output, verbose)
    logger.info(
        "run start pos=%s imports=%s images=%s strict_no_fuzzy=true ocr_provider=%s",
        pos,
        imports,
        images,
        ocr_provider,
    )
    logger.debug(
        "legacy thresholds ignored by strict production pipeline auto=%s review=%s",
        auto_threshold,
        review_threshold,
    )

    products, pos_issues, pos_meta = load_pos(pos)
    suppliers, import_meta = load_imports(imports)
    parsed_images, image_issues, image_meta = load_images(images)
    issues: list[DataQualityIssue] = pos_issues + image_issues
    profile = profile_workbooks(pos, imports, images, pos_meta, import_meta, image_meta, issues)
    write_profile(profile, output)

    results: list[MatchResult] = []
    barcode_reader = BarcodeReader()
    ocr = build_ocr_provider(ocr_provider)
    barcode_index = build_barcode_index(products)
    evidence_index = ProductEvidenceIndex(products)
    capture_groups = group_product_images(parsed_images)
    filename_counts = Counter(image.filename.casefold() for image in parsed_images)
    logger.info(
        "barcode reader available=%s captures=%s images=%s",
        barcode_reader.available,
        len(capture_groups),
        len(parsed_images),
    )

    kb = load_knowledge_base(output / "knowledge_base.json")
    if not kb and Path("knowledge_base.json").exists():
        kb = load_knowledge_base(Path("knowledge_base.json"))

    processed = 0
    for capture in capture_groups:
        try:
            human_results = _human_group_result(capture, products, kb, filename_counts, barcode_index)
            if human_results is not None:
                capture_results = human_results
            else:
                capture_results = resolve_capture_evidence(
                    images=capture,
                    products=products,
                    barcode_reader=barcode_reader,
                    ocr_provider=ocr,
                    top_k=top_k,
                    barcode_index=barcode_index,
                    evidence_index=evidence_index,
                )
            results.extend(capture_results)
        except Exception as exc:
            for image in capture:
                results.append(
                    MatchResult(
                        image=image,
                        status="ERROR",
                        reason="matching failed",
                        error=str(exc),
                    )
                )
            logger.exception("matching failed for capture %s", [image.filename for image in capture])

        processed += len(capture)
        if processed % 50 == 0 or processed == len(parsed_images):
            logger.info("matching progress %s/%s", processed, len(parsed_images))

    write_reports(results, issues, profile, output)
    write_html(results, output)
    deliverables = export_standard_deliverables(results, output, total_pos_count=len(products))
    counts = {
        status: sum(result.status == status for result in results)
        for status in ["AUTO_MATCHED", "NEED_REVIEW", "UNMATCHED", "ERROR"]
    }
    summary = {
        "pos_products": len(products),
        "imported_products": len(suppliers),
        "images": len(parsed_images),
        "captures": len(capture_groups),
        **{key.lower(): value for key, value in counts.items()},
        **deliverables,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "strict_no_fuzzy": True,
        "ocr_provider": ocr_provider,
    }
    logger.info("final summary %s", summary)
    return summary
