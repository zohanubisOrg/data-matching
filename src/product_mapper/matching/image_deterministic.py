from __future__ import annotations

from ..models import MatchCandidate, MatchResult, POSProduct, ProductImage, SupplierProduct
from ..parsing.ocr_parser import parse_ocr_identity
from ..vision.provider import OCRLine
from .no_fuzzy import (
    _identity,
    _qualifier_conflict,
    _size_relation,
    match_import_names_no_fuzzy,
)
from .product_index import IndexedProductIdentity, ProductEvidenceIndex


def _candidate(product: POSProduct, evidence: str) -> MatchCandidate:
    return MatchCandidate(
        product=product,
        score=1.0,
        name_score=1.0,
        evidence=[evidence],
    )


def _candidate_products_from_row(row: dict, index: ProductEvidenceIndex) -> list[POSProduct]:
    """Restore exact POS rows from an auditable no-fuzzy result row."""
    raw_rows = str(row.get("candidate_row_indexes", ""))
    row_indexes = []
    for value in raw_rows.split("|"):
        value = value.strip()
        if value.isdigit():
            row_indexes.append(int(value))
    if row_indexes:
        return [index.products[row_index] for row_index in row_indexes if 0 <= row_index < len(index.products)]

    # Backward compatibility for older report rows without row indexes.
    raw_ids = str(row.get("candidate_product_ids", ""))
    ids = [value.strip() for value in raw_ids.split("|") if value.strip()]
    result: list[POSProduct] = []
    seen_rows: set[int] = set()
    for product_id in ids:
        for product in index.by_id.get(product_id, []):
            row_key = id(product)
            if row_key not in seen_rows:
                result.append(product)
                seen_rows.add(row_key)
    return result


def _identity_compatible(query: dict, identity: dict) -> tuple[bool, bool]:
    if query["family"] and identity["family"] and query["family"] != identity["family"]:
        return False, False
    if _qualifier_conflict(query["tokens"], identity["tokens"]):
        return False, False
    size_exact, size_conflict = _size_relation(query["item_size"], identity["item_size"])
    if size_conflict:
        return False, False
    return True, size_exact


def _size_evidence_complete(query: dict, identity: dict) -> bool:
    return bool(query["item_size"]) == bool(identity["item_size"])


def _strict_core_identity(query: dict, identity: dict) -> bool:
    compatible, size_exact = _identity_compatible(query, identity)
    if not compatible or not _size_evidence_complete(query, identity):
        return False
    if query["item_size"] and identity["item_size"] and not size_exact:
        return False
    return query["core"] == identity["core"]


def _fast_exact_filename(
    image: ProductImage,
    index: ProductEvidenceIndex,
) -> MatchResult | None:
    source_name = (image.raw_name or image.normalized_name or "").strip()
    if not source_name:
        return None
    query = _identity(source_name)
    full_records = index.by_full.get(query["full"], [])
    method = "canonical_exact"
    records = full_records
    if not records:
        method = "core_exact"
        records = index.by_core.get(query["core"], [])
    if not records:
        return None

    matched_rows: dict[int, POSProduct] = {}
    incomplete_rows: dict[int, POSProduct] = {}
    for record in records:
        compatible, _ = _identity_compatible(query, record.identity)
        if not compatible:
            continue
        if method == "canonical_exact" or _strict_core_identity(query, record.identity):
            matched_rows[record.row_index] = record.product
        else:
            incomplete_rows[record.row_index] = record.product

    if matched_rows:
        ordered = [matched_rows[key] for key in sorted(matched_rows)]
        top = [_candidate(product, "deterministic indexed filename candidate") for product in ordered]
        if len(ordered) == 1:
            chosen = top[0]
            return MatchResult(
                image=image,
                status="AUTO_MATCHED",
                candidate=chosen,
                top_candidates=[chosen],
                confidence=1.0,
                top2_score=0.0,
                margin=1.0,
                match_method="deterministic_filename",
                reason=f"indexed {method} no-fuzzy match",
                evidence=chosen.evidence,
            )
        return MatchResult(
            image=image,
            status="NEED_REVIEW",
            candidate=None,
            top_candidates=top,
            confidence=0.0,
            match_method="deterministic_filename_review",
            reason="MULTIPLE_POS_ROWS_FOR_DETERMINISTIC_IDENTITY",
            evidence=["deterministic filename candidates only; duplicate POS rows remain ambiguous"],
        )

    if incomplete_rows:
        ordered = [incomplete_rows[key] for key in sorted(incomplete_rows)]
        return MatchResult(
            image=image,
            status="NEED_REVIEW",
            candidate=None,
            top_candidates=[
                _candidate(product, "core name agrees but required size evidence is incomplete")
                for product in ordered
            ],
            confidence=0.0,
            match_method="deterministic_filename_review",
            reason="INCOMPLETE_CORE_IDENTITY",
            evidence=["core name agreement cannot auto-match when size evidence is missing"],
        )
    return None


def _strict_fallback_auto_allowed(source_name: str, product: POSProduct, method: str) -> bool:
    if method == "canonical_exact":
        return True
    if method != "core_exact":
        return False
    query = _identity(source_name)
    for value in (product.product_name, product.official_name, product.printer_name):
        if not value:
            continue
        identity = _identity(value)
        if _strict_core_identity(query, identity):
            return True
    return False


def match_filename_deterministic(
    image: ProductImage,
    products: list[POSProduct],
    evidence_index: ProductEvidenceIndex | None = None,
) -> MatchResult | None:
    """Resolve an image filename through strict deterministic no-fuzzy rules.

    Token subset discovery is review assistance only. Duplicate POS rows always remain
    ambiguous even when malformed source data reuses the same Product ID.
    """
    source_name = (image.raw_name or image.normalized_name or "").strip()
    if not source_name:
        return None

    index = evidence_index or ProductEvidenceIndex(products)
    fast = _fast_exact_filename(image, index)
    if fast is not None:
        return fast

    supplier = SupplierProduct(
        name=source_name,
        supplier=image.source or "image",
        supplier_sku=image.source_product_id,
        sheet="image",
    )
    row = match_import_names_no_fuzzy(products, [supplier])[0]
    if row.get("status") == "UNMATCHED":
        return None

    candidate_products = _candidate_products_from_row(row, index)
    top = [_candidate(product, "deterministic canonical filename candidate") for product in candidate_products]

    product_id = str(row.get("pos_product_id", "")).strip()
    rows_for_id = index.by_id.get(product_id, []) if product_id else []
    method = str(row.get("match_method") or "")
    if (
        row.get("status") == "AUTO_MATCHED"
        and not row.get("pos_identity_ambiguous")
        and len(rows_for_id) == 1
        and _strict_fallback_auto_allowed(source_name, rows_for_id[0], method)
    ):
        chosen = _candidate(rows_for_id[0], "unique strict deterministic filename identity")
        return MatchResult(
            image=image,
            status="AUTO_MATCHED",
            candidate=chosen,
            top_candidates=[chosen],
            confidence=1.0,
            top2_score=0.0,
            margin=1.0,
            match_method="deterministic_filename",
            reason=f"strict no-fuzzy {method} match",
            evidence=chosen.evidence,
        )

    reason = str(row.get("reason") or "ambiguous deterministic filename identity")
    if product_id and len(rows_for_id) > 1:
        reason = "DUPLICATE_POS_PRODUCT_ID_REQUIRES_REVIEW"
        top = [_candidate(product, reason) for product in rows_for_id]
    elif method == "safe_subset":
        reason = "SAFE_SUBSET_REQUIRES_REVIEW"
    elif method == "core_exact" and row.get("status") != "AUTO_MATCHED":
        reason = str(row.get("reason") or "INCOMPLETE_CORE_IDENTITY")

    return MatchResult(
        image=image,
        status="NEED_REVIEW",
        candidate=None,
        top_candidates=top,
        confidence=0.0,
        match_method="deterministic_filename_review",
        reason=reason,
        evidence=["deterministic filename candidates only; no fuzzy score used"],
    )


def _best_indexed_identity(
    records: list[IndexedProductIdentity],
    query: dict,
) -> tuple[dict, bool] | None:
    valid: list[tuple[dict, bool]] = []
    for record in records:
        identity = record.identity
        tokens = identity["tokens"]
        if len(tokens) < 2 or not tokens.issubset(query["tokens"]):
            continue
        compatible, size_exact = _identity_compatible(query, identity)
        if compatible:
            valid.append((identity, size_exact))
    if not valid:
        return None
    return max(valid, key=lambda item: (len(item[0]["tokens"]), int(item[1])))


def _ocr_windows(lines: list[OCRLine], min_confidence: float = 0.65, max_window: int = 3) -> list[str]:
    # Hard conflicts need scored OCR evidence. Unknown/zero confidence remains usable
    # for human review through parse_ocr_identity(), but cannot overrule a valid GTIN.
    accepted = [
        str(line.text).strip()
        for line in lines
        if str(line.text).strip() and line.confidence >= min_confidence
    ]
    windows: list[str] = []
    for start in range(len(accepted)):
        for width in range(1, max_window + 1):
            chunk = accepted[start : start + width]
            if len(chunk) != width:
                break
            windows.append(" ".join(chunk))
    return windows


def find_ocr_exact_identity_candidates(
    lines: list[OCRLine],
    products: list[POSProduct],
    evidence_index: ProductEvidenceIndex | None = None,
) -> list[POSProduct]:
    """Find strong OCR identities from short contiguous high-confidence label windows."""
    index = evidence_index or ProductEvidenceIndex(products)
    found: dict[int, POSProduct] = {}
    for text in _ocr_windows(lines):
        query = _identity(text)
        full_records = index.by_full.get(query["full"], [])
        if full_records:
            records = full_records
            strict_core = False
        else:
            records = index.by_core.get(query["core"], [])
            strict_core = True
        for record in records:
            compatible, _ = _identity_compatible(query, record.identity)
            if not compatible:
                continue
            if strict_core and not _strict_core_identity(query, record.identity):
                continue
            found[record.row_index] = record.product
    return [found[key] for key in sorted(found)]


def find_ocr_review_candidates(
    lines: list[OCRLine],
    products: list[POSProduct],
    top_k: int = 3,
    evidence_index: ProductEvidenceIndex | None = None,
) -> list[MatchCandidate]:
    """Return deterministic OCR candidates for human review only.

    Exact label identities are checked first. Broader review retrieval uses an inverted
    exact-token index to avoid rescanning every POS row for every image, then applies
    the full deterministic family/qualifier/size verification before ranking.
    """
    index = evidence_index or ProductEvidenceIndex(products)

    exact_products = find_ocr_exact_identity_candidates(lines, products, index)
    if exact_products:
        return [
            _candidate(product, "exact contiguous OCR label identity")
            for product in exact_products[:top_k]
        ]

    query = parse_ocr_identity(lines)
    if len(query["tokens"]) < 2:
        return []

    candidate_rows = index.candidate_row_indexes(query["tokens"], min_overlap=2)
    ranked: list[tuple[int, int, int, POSProduct]] = []
    for row_index in sorted(candidate_rows):
        records = index.by_row.get(row_index, [])
        best = _best_indexed_identity(records, query)
        if best is None:
            continue
        identity, size_exact = best
        ranked.append((len(identity["tokens"]), int(size_exact), row_index, records[0].product))

    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [
        _candidate(product, "OCR tokens satisfy deterministic review rules")
        for _, _, _, product in ranked[:top_k]
    ]


def ocr_conflict_reason(
    lines: list[OCRLine],
    selected_product: POSProduct,
    products: list[POSProduct],
    evidence_index: ProductEvidenceIndex | None = None,
) -> str | None:
    """Return a hard conflict only for one complete, confident exact OCR POS row."""
    candidates = find_ocr_exact_identity_candidates(lines, products, evidence_index)
    if len(candidates) != 1:
        return None
    # Product IDs are not reliable row identities when source POS data is malformed.
    # The index stores the original POS objects, so object identity preserves row truth.
    if candidates[0] is not selected_product:
        return "OCR_IDENTITY_CONFLICT"
    return None


__all__ = [
    "find_ocr_exact_identity_candidates",
    "find_ocr_review_candidates",
    "match_filename_deterministic",
    "ocr_conflict_reason",
    "parse_ocr_identity",
]
