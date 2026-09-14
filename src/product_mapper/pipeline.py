from __future__ import annotations

from pathlib import Path
import logging
import time

from .config import DEFAULT_IMAGES, DEFAULT_IMPORTS, DEFAULT_OUTPUT, DEFAULT_POS
from .ingestion.image_loader import load_images
from .ingestion.pos_loader import load_pos
from .ingestion.supplier_loader import load_imports
from .matching.image_deterministic import (
    find_ocr_review_candidates,
    match_filename_deterministic,
    ocr_conflict_reason,
)
from .matching.knowledge_base import load_knowledge_base
from .models import DataQualityIssue, MatchCandidate, MatchResult, POSProduct, ProductImage
from .reporting.excel_report import write_reports
from .reporting.html_report import write_html
from .reporting.image_exporter import export_standard_deliverables
from .reporting.profile_report import profile_workbooks, write_profile
from .vision.barcode_reader import BarcodeReader
from .vision.barcode_utils import is_gtin_like, normalize_barcode, validate_gtin
from .vision.provider import ImageAttributes, NoOpVisionProvider, VisionProvider


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


def _barcode_hits(value: str, products: list[POSProduct]) -> list[POSProduct]:
    normalized = normalize_barcode(value)
    if not normalized:
        return []
    return [
        product
        for product in products
        if product.barcode and normalize_barcode(product.barcode) == normalized
    ]


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


def resolve_image_evidence(
    image: ProductImage,
    products: list[POSProduct],
    barcode_reader: BarcodeReader | VisionProvider,
    ocr_provider: VisionProvider | None = None,
    top_k: int = 3,
) -> MatchResult:
    """Resolve one image using deterministic evidence only.

    Production priority is barcode -> deterministic filename -> deterministic OCR
    review. Fuzzy similarity is intentionally absent from this function.
    """
    ocr_provider = ocr_provider or NoOpVisionProvider()
    barcode_evidence = barcode_reader.analyze(image.path)

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
                image,
                "barcode_conflict",
                "INVALID_GTIN_CHECK_DIGIT",
                evidence=[f"decoded barcode rejected: {decoded}"],
            )

        hits = _barcode_hits(decoded, products)
        if not hits:
            return _review(
                image,
                "barcode_conflict",
                "BARCODE_NOT_FOUND_IN_POS",
                evidence=[f"decoded barcode not present in POS: {decoded}"],
            )
        if len(hits) > 1:
            return _review(
                image,
                "barcode_conflict",
                "DUPLICATE_POS_BARCODE",
                hits,
                [f"decoded barcode resolves to multiple POS rows: {decoded}"],
            )
        if not gtin_like:
            return _review(
                image,
                "barcode_conflict",
                "UNVALIDATED_NON_GTIN_BARCODE",
                hits,
                [f"exact non-GTIN barcode requires review: {decoded}"],
            )

        selected = hits[0]
        ocr_evidence = _analyze_ocr(ocr_provider, image)
        if ocr_evidence.ocr_lines:
            conflict = ocr_conflict_reason(ocr_evidence.ocr_lines, selected, products)
            if conflict:
                ocr_candidates = find_ocr_review_candidates(ocr_evidence.ocr_lines, products, top_k=top_k)
                candidates = [selected] + [
                    item.product for item in ocr_candidates if item.product.product_id != selected.product_id
                ]
                return _review(
                    image,
                    "barcode_ocr_conflict",
                    conflict,
                    candidates[: max(1, top_k)],
                    [
                        f"valid exact POS barcode: {decoded}",
                        "OCR exact identity conflicts with barcode-selected product",
                    ],
                )

        candidate = _candidate(selected, f"exact validated decoded POS barcode: {decoded}")
        return MatchResult(
            image=image,
            status="AUTO_MATCHED",
            candidate=candidate,
            top_candidates=[candidate],
            confidence=1.0,
            top2_score=0.0,
            margin=1.0,
            match_method="exact_barcode",
            reason="unique checksum-valid decoded barcode found in POS",
            evidence=candidate.evidence,
        )

    if barcode_evidence.barcode_candidates:
        distinct = sorted({normalize_barcode(value) for value in barcode_evidence.barcode_candidates if value})
        return _review(
            image,
            "barcode_conflict",
            "AMBIGUOUS_BARCODE_DECODE",
            evidence=["decoded values: " + " | ".join(distinct)],
        )

    filename_result = match_filename_deterministic(image, products)
    if filename_result is not None and filename_result.status == "AUTO_MATCHED":
        return filename_result

    ocr_evidence = _analyze_ocr(ocr_provider, image)
    ocr_candidates = find_ocr_review_candidates(ocr_evidence.ocr_lines, products, top_k=top_k)
    if ocr_candidates:
        return MatchResult(
            image=image,
            status="NEED_REVIEW",
            candidate=None,
            top_candidates=ocr_candidates,
            confidence=0.0,
            match_method="deterministic_ocr_review",
            reason="exact OCR evidence produced deterministic review candidates",
            evidence=[
                "OCR candidates use canonical exact tokens/family/size rules only",
                *ocr_evidence.warnings,
            ],
        )

    if filename_result is not None:
        return filename_result

    return MatchResult(
        image=image,
        status="UNMATCHED",
        confidence=0.0,
        match_method="none",
        reason="no deterministic barcode, filename or OCR candidate",
        evidence=[*barcode_evidence.warnings, *ocr_evidence.warnings],
    )


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

    auto_threshold/review_threshold are retained for CLI/API compatibility but are
    not used by the strict deterministic production path.
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
    logger.info("barcode reader available=%s", barcode_reader.available)

    kb = load_knowledge_base(output / "knowledge_base.json")
    if not kb and Path("knowledge_base.json").exists():
        kb = load_knowledge_base(Path("knowledge_base.json"))

    for index, image in enumerate(parsed_images, 1):
        try:
            if image.filename in kb and kb[image.filename].get("barcode"):
                approved_barcode = normalize_barcode(kb[image.filename]["barcode"])
                hits = _barcode_hits(approved_barcode, products)
                if len(hits) == 1:
                    candidate = _candidate(hits[0], "human-approved decision from knowledge base")
                    result = MatchResult(
                        image=image,
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
                        image,
                        "human_approved_conflict",
                        "approved barcode is missing or non-unique in current POS",
                        hits,
                    )
            elif image.filename in kb and kb[image.filename].get("selection") == "No Match":
                result = MatchResult(
                    image=image,
                    status="UNMATCHED",
                    confidence=0.0,
                    match_method="exact_human_approved",
                    reason="human confirmed no match",
                )
            else:
                result = resolve_image_evidence(
                    image=image,
                    products=products,
                    barcode_reader=barcode_reader,
                    ocr_provider=ocr,
                    top_k=top_k,
                )
            results.append(result)
        except Exception as exc:
            results.append(MatchResult(image=image, status="ERROR", reason="matching failed", error=str(exc)))
            logger.exception("matching failed for %s", image.filename)
        if index % 50 == 0:
            logger.info("matching progress %s/%s", index, len(parsed_images))

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
        **{key.lower(): value for key, value in counts.items()},
        **deliverables,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "strict_no_fuzzy": True,
        "ocr_provider": ocr_provider,
    }
    logger.info("final summary %s", summary)
    return summary
