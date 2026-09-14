from __future__ import annotations

from dataclasses import dataclass

from ..models import POSProduct
from .no_fuzzy import _identity


@dataclass(frozen=True)
class IndexedProductIdentity:
    product: POSProduct
    field: str
    raw_name: str
    identity: dict


class ProductEvidenceIndex:
    """Run-scoped deterministic index shared by barcode/OCR matching.

    Product names are canonicalized once per pipeline run instead of once per image.
    The index contains no similarity scores or fuzzy retrieval structures.
    """

    def __init__(self, products: list[POSProduct]):
        self.products = products
        self.by_id: dict[str, POSProduct] = {product.product_id: product for product in products}
        self.identities: list[IndexedProductIdentity] = []
        self.by_full: dict[str, list[IndexedProductIdentity]] = {}
        self.by_core: dict[str, list[IndexedProductIdentity]] = {}

        for product in products:
            for field, value in (
                ("product_name", product.product_name),
                ("official_name", product.official_name),
                ("printer_name", product.printer_name),
            ):
                if not value:
                    continue
                identity = _identity(value)
                item = IndexedProductIdentity(product, field, value, identity)
                self.identities.append(item)
                self.by_full.setdefault(identity["full"], []).append(item)
                self.by_core.setdefault(identity["core"], []).append(item)
