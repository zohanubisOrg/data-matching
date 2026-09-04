from ..config import SUPPLIER_ALIASES
from ..models import MatchCandidate, POSProduct, ProductImage, SupplierProduct
from ..parsing.attributes import packaging_conflict, parse_packaging
from ..parsing.text_normalizer import normalize_text, tokens, translate_multilingual
from .rules import variant_tokens
from rapidfuzz import process
from rapidfuzz.fuzz import WRatio, token_set_ratio

BRAND_PREFIXES: dict[str, str] = {
    "8934734": "vinh thuan",
    "8850987": "mama",
    "8994963": "indomie",
    "8801043": "nongshim",
    "8801073": "samyang",
    "084909": "cock",
    "0084909": "cock",
    "84909": "cock",
    "016229": "aroy-d",
    "078895": "lkk",
    "5011308": "patak",
    "7178600": "ahmed",
    "8935311": "vifon",
    "8934563": "acecook",
    "8852018": "yum yum",
}

KNOWN_BRANDS: set[str] = {
    "maling", "chinchin", "pride", "aroyd", "chaokoh", "vifon", "mama", "nongshim", "shin",
    "samyang", "yumyum", "indomie", "taisun", "wuchung", "ngoc lien", "fishwell", "surasang",
    "okf", "bibigo", "jongga", "ottogi", "fathai", "vinh thuan", "flying goose", "lkk",
    "lee kum kee", "cock", "wai wai", "nissin", "kikkoman", "foco", "yeos", "vinamilk",
    "chinsu", "nam duong", "cholimex", "hung phat", "haohao", "acecook", "mikko", "sevenco"
}

INGREDIENTS: set[str] = {
    "chicken", "beef", "pork", "duck", "shrimp", "fish", "squid", "crab",
    "lime", "lemon", "mango", "banana", "strawberry", "peach", "lychee", "guava",
    "coconut", "taro", "bamboo", "garlic", "ginger", "chilli", "chili", "pepper", "eggplant", "brinjal",
    "sesame", "peanut", "mushroom", "curry", "kimchi", "miso", "teriyaki", "wasabi", "basil"
}

CATEGORIES: set[str] = {
    "noodle", "noodles", "ramen", "vermicelli", "rice", "flour", "sauce", "oil", "tea",
    "drink", "soup", "chutney", "pickle", "paste", "chips", "snack", "cake", "jam",
    "cream", "juice", "milk", "puree", "bean", "beans"
}


def _get_product_brand(product: POSProduct) -> str | None:
    p_text = f"{product.product_name} {product.official_name}".lower()
    if product.barcode:
        for pfx, bname in BRAND_PREFIXES.items():
            if product.barcode.startswith(pfx):
                return bname
    for b in KNOWN_BRANDS:
        if b in p_text:
            return b
    return None


def _get_image_brands(image: ProductImage) -> set[str]:
    fn = image.filename.lower().replace("-", " ").replace("_", " ")
    b_set = {b for b in KNOWN_BRANDS if b in fn}
    if "vinh_thuan" in image.filename.lower(): b_set.add("vinh thuan")
    if "aroyd" in fn: b_set.add("aroy-d")
    if "lee kum kee" in fn: b_set.add("lkk")
    if "haohao" in fn: b_set.add("acecook")
    if "yumyum" in fn: b_set.add("yum yum")
    if "shin" in fn: b_set.add("nongshim")
    if "buldak" in fn: b_set.add("samyang")
    return b_set


def _name_score(image: ProductImage, product: POSProduct) -> tuple[float, float]:
    query_trans = translate_multilingual(image.normalized_name)
    q_norm = normalize_text(query_trans)
    q_toks = set(q_norm.split())

    best_score = 0.0
    best_cov = 0.0
    for value in (product.product_name, product.official_name, product.printer_name):
        if not value:
            continue
        v_trans = translate_multilingual(value)
        v_norm = normalize_text(v_trans)
        p_toks = set(v_norm.split())
        overlap = len(q_toks & p_toks)
        cov = overlap / max(1, len(q_toks))

        wr = WRatio(q_norm, v_norm) / 100.0
        ts = token_set_ratio(q_norm, v_norm) / 100.0
        if len(p_toks) <= 2 and len(q_toks) >= 4:
            ts = ts * (0.6 + 0.4 * cov)

        s = max(wr, ts)
        if s > best_score:
            best_score = s
            best_cov = cov
    return best_score, best_cov


def score_candidate(image: ProductImage, product: POSProduct, supplier_rows: list[SupplierProduct]) -> MatchCandidate:
    name_score, query_cov = _name_score(image, product)
    conflicts: list[str] = []
    evidence: list[str] = []

    img_full = translate_multilingual(image.filename.lower())
    p_full = translate_multilingual(f"{product.product_name} {product.official_name} {product.printer_name}".lower())

    img_brands = _get_image_brands(image)
    p_brand = _get_product_brand(product)

    brand_bonus = 0.0
    if img_brands:
        if p_brand:
            if p_brand in img_brands or any(b in p_brand for b in img_brands):
                brand_bonus = 0.18
                evidence.append(f"brand verified: {p_brand}")
            else:
                conflicts.append(f"brand conflict: {sorted(img_brands)} vs {p_brand}")
        else:
            if any(b in p_full for b in img_brands):
                brand_bonus = 0.14
                evidence.append("brand matched in product text")

    img_categories = set(normalize_text(img_full).split()) & CATEGORIES
    p_categories = set(normalize_text(p_full).split()) & CATEGORIES

    # Category guards
    if any(w in img_categories for w in ("noodle", "noodles", "ramen")):
        if not any(w in p_full for w in ("noodle", "noodles", "ramen", "nudler", "vermicelli", "udon", "soba", "pho", "pad thai", "tom yum", "mi goreng")):
            conflicts.append("category mismatch: noodle image vs non-noodle POS")
    if "tea" in img_categories and "tea" not in p_categories and "te" not in p_full:
        if "drink" in p_categories:
            conflicts.append("tea vs non-tea drink")
    if "flour" in img_categories and any(c in p_categories for c in ("sauce", "oil", "chips", "snack", "pickle", "bamboo")):
        conflicts.append("flour vs non-flour conflict")
    if any(b in img_categories for b in ("bean", "beans")) and any(c in p_categories for c in ("sauce", "oil", "chips", "bamboo")):
        conflicts.append("bean vs sauce/bamboo conflict")
    if "vermicelli" in img_categories and not any(w in p_full for w in ("vermicelli", "noodle", "noodles", "nudler", "mien", "bun")):
        conflicts.append("vermicelli vs non-noodle conflict")
    if "porridge" in img_full and not any(w in p_full for w in ("porridge", "chao", "graad", "congee")):
        conflicts.append("porridge vs soup conflict")

    img_ingredients = set(normalize_text(img_full).split()) & INGREDIENTS
    p_ingredients = set(normalize_text(p_full).split()) & INGREDIENTS
    if img_ingredients and p_ingredients:
        if img_ingredients.isdisjoint(p_ingredients):
            conflicts.append(f"ingredient conflict: {sorted(img_ingredients)} vs {sorted(p_ingredients)}")

    penalty = 0.0
    extra_ings = p_ingredients - img_ingredients
    if extra_ings and not img_ingredients:
        penalty += 0.12
    elif extra_ings and img_ingredients:
        penalty += 0.08

    for cat in ("cream", "jam", "puree", "chutney", "paste", "milk"):
        if cat in img_categories and cat in p_categories:
            brand_bonus += 0.08
        elif cat in img_categories and cat not in p_categories:
            penalty += 0.12

    image_variants = variant_tokens(image.normalized_name)
    product_variants = variant_tokens(" ".join((product.product_name, product.official_name, product.printer_name)))
    variant_score = 0.0
    variant_weight = 0.0
    if image_variants and product_variants:
        variant_weight = 0.15
        variant_score = 1.0 if image_variants == product_variants else (0.0 if image_variants.isdisjoint(product_variants) else 0.7)
        if variant_score == 0: conflicts.append(f"variant/flavour conflict: {sorted(image_variants)} vs {sorted(product_variants)}")
        elif variant_score == 1: evidence.append("variant/flavour tokens agree")

    image_pack = image.packaging
    product_pack = parse_packaging(" ".join((product.product_name, product.official_name, product.printer_name)))
    size_score = 0.0
    size_weight = 0.0
    if image_pack.levels and product_pack.levels:
        size_weight = 0.15
        size_score = 1.0 if image_pack.levels == product_pack.levels else 0.0
        conflict = packaging_conflict(image_pack, product_pack)
        if conflict: conflicts.append(conflict)
        if size_score == 1: evidence.append(f"size exact: {image_pack.raw}")

    source_score = 0.0
    source_weight = 0.0
    bridge_score = 0.0
    compatible = [r for r in supplier_rows if SUPPLIER_ALIASES.get(image.source or "") == r.supplier]
    if compatible:
        source_weight = 0.10
        source_score = 1.0
        evidence.append(f"supplier compatible: {image.source} → {compatible[0].supplier}")
        if image.source_product_id and any(r.supplier_sku == image.source_product_id for r in compatible):
            bridge_score = 1.0
            evidence.append("source product ID equals supplier SKU")
        else:
            bridge_hits = process.extract(image.normalized_name, [normalize_text(r.name) for r in compatible], scorer=WRatio, limit=2)
            if bridge_hits and bridge_hits[0][1] >= 90 and (len(bridge_hits) == 1 or bridge_hits[0][1] - bridge_hits[1][1] >= 10):
                bridge_score = 1.0
                evidence.append(f"supplier name bridge: {bridge_hits[0][1]:.1f}")


    combined_name = min(1.0, max(0.0, name_score * 0.85 + query_cov * 0.15 + brand_bonus - penalty))
    weighted = [(combined_name, 0.50)]
    if variant_weight: weighted.append((variant_score, variant_weight))
    if size_weight: weighted.append((size_score, size_weight))
    if source_weight: weighted.append((source_score, source_weight))
    if bridge_score: weighted.append((bridge_score, 0.10))
    final = sum(value * weight for value, weight in weighted) / sum(weight for value, weight in weighted)

    if conflicts:
        final = max(0.0, final - 0.35)

    return MatchCandidate(
        product=product,
        score=round(final, 6),
        name_score=round(combined_name, 6),
        variant_score=variant_score,
        size_score=size_score,
        supplier_score=source_score,
        bridge_score=bridge_score,
        conflicts=conflicts,
        evidence=evidence
    )

