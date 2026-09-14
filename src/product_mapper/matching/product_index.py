from __future__ import annotations

from dataclasses import dataclass

from ..models import POSProduct
from .no_fuzzy import _identity


@dataclass(frozen=True)
class IndexedProductIdentity:
    row_index: int
    product: POSProduct
    field: str
    raw_name: str
    identity: dict


class ProductEvidenceIndex:
    """Run-scoped deterministic index shared by barcode/OCR matching.

    Product names are canonicalized and grouped once per pipeline run instead of once
    per image. Row identity is preserved separately from Product ID so malformed POS
    data with duplicate Product IDs can never collapse into a false unique match.
    """

    def __init__(self, products: list[POSProduct]):
        self.products = products
        self.by_id: dict[str, list[POSProduct]] = {}
        self.identities: list[IndexedProductIdentity] = []
        self.by_row: dict[int, list[IndexedProductIdentity]] = {}
        self.by_full: dict[str, list[IndexedProductIdentity]] = {}
        self.by_core: dict[str, list[IndexedProductIdentity]] = {}

        for row_index, product in enumerate(products):
            self.by_id.setdefault(product.product_id, []).append(product)
            for field, value in (
                ("product_name", product.product_name),
                ("official_name", product.official_name),
                ("printer_name", product.printer_name),
            ):
                if not value:
                    continue
                identity = _identity(value)
                item = IndexedProductIdentity(row_index, product, field, value, identity)
                self.identities.append(item)
                self.by_row.setdefault(row_index, []).append(item)
                self.by_full.setdefault(identity["full"], []).append(item)
                self.by_core.setdefault(identity["core"], []).append(item)
