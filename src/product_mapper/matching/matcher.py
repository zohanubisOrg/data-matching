from ..models import MatchCandidate, MatchResult, ProductImage, POSProduct, SupplierProduct
from .candidate_generator import CandidateGenerator
from .scorer import score_candidate


def _find_asropa_ean_product(image: ProductImage, products: list[POSProduct]) -> POSProduct | None:
    if image.source == "asropa" and image.source_product_id:
        target_art = image.source_product_id.strip()
        for p in products:
            if p.barcode and p.barcode.startswith("4045198") and len(p.barcode) >= 12:
                if p.barcode[7:12] == target_art:
                    return p
    return None


def match_image(image: ProductImage, products: list[POSProduct], suppliers: list[SupplierProduct], auto_threshold: float, review_threshold: float, top_k: int = 3, generator: CandidateGenerator | None = None) -> MatchResult:
    # Priority 1: Deterministic Asropa EAN Barcode Math
    asropa_prod = _find_asropa_ean_product(image, products)
    if asropa_prod:
        candidate = MatchCandidate(
            product=asropa_prod,
            score=1.0,
            name_score=1.0,
            evidence=[f"deterministic Asropa EAN barcode match: 4045198 + {image.source_product_id}"]
        )
        return MatchResult(
            image=image,
            status="AUTO_MATCHED",
            candidate=candidate,
            top_candidates=[candidate],
            confidence=1.0,
            top2_score=0.0,
            margin=1.0,
            match_method="asropa_ean_barcode",
            reason="deterministic Asropa EAN barcode match",
            evidence=candidate.evidence
        )

    generator = generator or CandidateGenerator(products)
    candidates = [score_candidate(image, p, suppliers) for p in generator.generate(image.normalized_name)]
    candidates.sort(key=lambda c: c.score, reverse=True)
    top = candidates[:top_k]
    if not top:
        return MatchResult(image=image, status="UNMATCHED", reason="no candidate generated")

    best = top[0]
    second = top[1].score if len(top) > 1 else 0.0
    margin = best.score - second
    conflicts = best.conflicts

    is_same_pos_name = (
        len(top) > 1 and
        top[0].product.product_name.lower().strip() == top[1].product.product_name.lower().strip() and
        top[0].product.official_name.lower().strip() == top[1].product.official_name.lower().strip()
    )
    second_is_generic = (
        len(top) > 1 and
        len(top[1].product.product_name.split()) == 1 and
        len(best.product.product_name.split()) >= 2
    )

    if conflicts:
        status = "NEED_REVIEW"
        reason = "hard conflict: " + "; ".join(conflicts)
    elif is_same_pos_name and margin < 0.02:
        status = "NEED_REVIEW"
        reason = f"ambiguous match: identical POS names (SKU {best.product.sku} vs {top[1].product.sku})"
    elif best.score >= auto_threshold and (len(top) == 1 or margin >= 0.02 or second_is_generic) and best.product.barcode:
        status, reason = "AUTO_MATCHED", "high confidence match with verified barcode"
    elif best.score >= 0.80 and (len(top) == 1 or margin >= 0.035 or second_is_generic) and best.product.barcode:
        status, reason = "AUTO_MATCHED", "confident match with verified barcode"
    elif best.score >= review_threshold:
        status, reason = "NEED_REVIEW", f"review threshold met (score={best.score:.2f}, margin={margin:.2f})"
    else:
        status, reason = "UNMATCHED", "best candidate below review threshold"

    return MatchResult(image=image, status=status, candidate=best, top_candidates=top, confidence=best.score, top2_score=second, margin=margin, match_method="fuzzy_name", reason=reason, evidence=best.evidence)

