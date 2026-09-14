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


def _candidate(product: POSProduct, evidence: str) -> MatchCandidate:
    return MatchCandidate(
        product=product,
        score=1.0,
        name_score=1.0,
        evidence=[evidence],
    )


def _candidate_products_from_row(row: dict, products: list[POSProduct]) -> list[POSProduct]:
    raw_ids = str(row.get("candidate_product_ids", ""))
    ids = [value.strip() for value in raw_ids.split("|") if value.strip()]
    index = {product.product_id: product for product in products}
    result: list[POSProduct] = []
    seen: set[str] = set()
    for product_id in ids:
        if product_id in index and product_id not in seen:
            result.append(index[product_id])
            seen.add(product_id)
    return result


def match_filename_deterministic(image: ProductImage, products: list[POSProduct]) -> MatchResult | None:
    """Resolve an image filename through the existing deterministic no-fuzzy matcher.

    Ambiguous POS identity is always downgraded to review even when the canonical
    product text is identical.
    """
    source_name = (image.raw_name or image.normalized_name or "").strip()
    if not source_name:
        return None

    supplier = SupplierProduct(
        name=source_name,
        supplier=image.source or "image",
        supplier_sku=image.source_product_id,
        sheet="image",
    )
    row = match_import_names_no_fuzzy(products, [supplier])[0]
    if row.get("status") == "UNMATCHED":
        return None

    candidate_products = _candidate_products_from_row(row, products)
    top = [_candidate(product, "deterministic canonical filename candidate") for product in candidate_products]

    product_id = str(row.get("pos_product_id", "")).strip()
    by_id = {product.product_id: product for product in products}
    if (
        row.get("status") == "AUTO_MATCHED"
        and not row.get("pos_identity_ambiguous")
        and product_id
        and product_id in by_id
    ):
        chosen = _candidate(by_id[product_id], "unique deterministic filename identity")
        return MatchResult(
            image=image,
            status="AUTO_MATCHED",
            candidate=chosen,
            top_candidates=[chosen],
            confidence=1.0,
            top2_score=0.0,
            margin=1.0,
            match_method="deterministic_filename",
            reason=f"no-fuzzy {row.get('match_method', 'canonical')} match",
            evidence=chosen.evidence,
        )

    return MatchResult(
        image=image,
        status="NEED_REVIEW",
        candidate=None,
        top_candidates=top,
        confidence=0.0,
        match_method="deterministic_filename_review",
        reason=str(row.get("reason") or "ambiguous deterministic filename identity"),
        evidence=["deterministic filename candidates only; no fuzzy score used"],
    )


def _best_identity(product: POSProduct, query: dict) -> tuple[dict, bool] | None:
    identities = [
        _identity(value)
        for value in (product.product_name, product.official_name, product.printer_name)
        if value
    ]
    valid: list[tuple[dict, bool]] = []
    for identity in identities:
        tokens = identity["tokens"]
        if len(tokens) < 2 or not tokens.issubset(query["tokens"]):
            continue
        if query["family"] and identity["family"] and query["family"] != identity["family"]:
            continue
        if _qualifier_conflict(query["tokens"], tokens):
            continue
        size_exact, size_conflict = _size_relation(query["item_size"], identity["item_size"])
        if size_conflict:
            continue
        valid.append((identity, size_exact))
    if not valid:
        return None
    return max(valid, key=lambda item: (len(item[0]["tokens"]), int(item[1])))


def find_ocr_review_candidates(
    lines: list[OCRLine],
    products: list[POSProduct],
    top_k: int = 3,
) -> list[MatchCandidate]:
    """Return exact deterministic OCR candidates for human review.

    Candidate discovery uses canonical token containment, family/qualifier rules and
    size conflict rejection. There is no edit distance, embedding or fuzzy score.
    """
    query = parse_ocr_identity(lines)
    if len(query["tokens"]) < 2:
        return []

    ranked: list[tuple[int, int, str, POSProduct]] = []
    for product in products:
        best = _best_identity(product, query)
        if best is None:
            continue
        identity, size_exact = best
        ranked.append((len(identity["tokens"]), int(size_exact), product.product_id, product))

    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [
        _candidate(product, "exact OCR tokens satisfy deterministic product rules")
        for _, _, _, product in ranked[:top_k]
    ]


def ocr_conflict_reason(
    lines: list[OCRLine],
    selected_product: POSProduct,
    products: list[POSProduct],
) -> str | None:
    """Return a hard OCR conflict only when OCR resolves one different exact identity.

    Missing/noisy OCR is deliberately not a conflict because a valid unique barcode
    remains stronger evidence than incomplete text recognition.
    """
    candidates = find_ocr_review_candidates(lines, products, top_k=3)
    if len(candidates) != 1:
        return None
    if candidates[0].product.product_id != selected_product.product_id:
        return "OCR_IDENTITY_CONFLICT"
    return None


__all__ = [
    "find_ocr_review_candidates",
    "match_filename_deterministic",
    "ocr_conflict_reason",
    "parse_ocr_identity",
]
