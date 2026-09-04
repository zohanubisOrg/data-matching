from rapidfuzz import process, fuzz

from ..models import POSProduct
from ..parsing.text_normalizer import normalize_text, translate_multilingual


class CandidateGenerator:
    def __init__(self, products: list[POSProduct], pool_size: int = 60):
        self.products = products
        self.pool_size = pool_size
        self.choices: list[tuple[str, int]] = []
        for index, product in enumerate(products):
            for value in (product.product_name, product.official_name, product.printer_name):
                if value:
                    self.choices.append((normalize_text(translate_multilingual(value)), index))
        self.texts = [x[0] for x in self.choices]

    def generate(self, query: str) -> list[POSProduct]:
        # Fast retrieval on multilingual normalized query
        clean_q = normalize_text(translate_multilingual(query))
        hits = process.extract(clean_q, self.texts, scorer=fuzz.token_set_ratio, limit=self.pool_size)
        scores: dict[int, float] = {}
        for _, score, corpus_index in hits:
            product_index = self.choices[corpus_index][1]
            scores[product_index] = max(scores.get(product_index, 0), float(score))
        return [self.products[index] for index, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]

