from ..models import MatchResult


def flat_result(result: MatchResult) -> dict:
    product = result.candidate.product if result.candidate else None
    return {
        "image_path": str(result.image.path), "image_filename": result.image.filename,
        "source": result.image.source, "source_product_id": result.image.source_product_id,
        "parsed_name": result.image.normalized_name, "status": result.status,
        "product_id": product.product_id if product else None, "sku": product.sku if product else None,
        "barcode": product.barcode if product else None, "product_name": product.product_name if product else None,
        "official_name": product.official_name if product else None, "confidence": result.confidence,
        "match_method": result.match_method, "reason": result.reason,
        "evidence": result.evidence, "conflicts": result.candidate.conflicts if result.candidate else [],
    }
