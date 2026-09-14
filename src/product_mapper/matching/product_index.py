from __future__ import annotations

from collections import Counter
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

    Product names are canonicalized once per pipeline run. Row identity is preserved
    separately from Product ID so malformed POS data with duplicate IDs can never
    collapse into a false unique match. Token postings allow OCR review retrieval to
    inspect only rows with deterministic token overlap instead of scanning all POS rows.
    """

    def __init__(self, products: list[POSProduct]):
        self.products = products
        self.by_id: dict[str, list[POSProduct]] = {}
        self.identities: list[IndexedProductIdentity] = []
        self.by_row: dict[int, list[IndexedProductIdentity]] = {}
        self.by_full: dict[str, list[IndexedProductIdentity]] = {}
        self.by_core: dict[str, list[IndexedProductIdentity]] = {}
        self.rows_by_token: dict[str, set[int]] = {}

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
                for token in identity["tokens"]:
                    self.rows_by_token.setdefault(token, set()).add(row_index)

    def candidate_row_indexes(self, query_tokens: set[str] | frozenset[str], min_overlap: int = 2) -> set[int]:
        """Return POS rows sharing enough exact canonical tokens with a query.

        This is candidate pruning only. The caller still applies full family, qualifier,
        size and token-subset verification before returning any candidate.
        """
        if min_overlap < 1:
            min_overlap = 1
        counts: Counter[int] = Counter()
        for token in query_tokens:
            counts.update(self.rows_by_token.get(token, ()))
        return {row_index for row_index, count in counts.items() if count >= min_overlap}
