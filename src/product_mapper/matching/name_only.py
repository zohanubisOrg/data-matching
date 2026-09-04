from __future__ import annotations

from collections import Counter, defaultdict
import re

from rapidfuzz.fuzz import WRatio, token_set_ratio

from ..models import POSProduct, SupplierProduct
from ..parsing.text_normalizer import normalize_text, translate_multilingual
from .candidate_generator import CandidateGenerator


DOMAIN_ALIASES: dict[str, str] = {
    "choisam": "choi sam",
    "kaichoi": "kai choi",
    "casava": "cassava",
    "grøn bønne": "green bean",
    "gron bonne": "green bean",
    "dild": "dill",
    "græskar": "pumpkin",
    "graeskar": "pumpkin",
    "kokosmælk": "coconut milk",
    "kokosmaelk": "coconut milk",
    "kokosvand": "coconut water",
    "kondenseret mælk": "condensed milk",
    "kondenseret maelk": "condensed milk",
    "kyllingefødder": "chicken feet",
    "kyllingefodder": "chicken feet",
    "karrypulver": "curry powder",
    "majs mel": "corn flour",
    "rød miso": "red miso",
    "rod miso": "red miso",
    "brun shimeji": "brown shimeji",
    "grøn te": "green tea",
    "gron te": "green tea",
}

UNIT_RE = r"(?:kg|g|ml|l|pcs|pc|stk)"
PACK_RE = re.compile(rf"\b(?:\d+(?:[.,]\d+)?\s*x\s*)+(\d+(?:[.,]\d+)?)\s*({UNIT_RE})\b", re.I)
SIZE_RE = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", re.I)


def _apply_aliases(text: str) -> str:
    result = text
    for src, dst in sorted(DOMAIN_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(src, dst)
    return result


def _normalized(value: str) -> str:
    text = normalize_text(translate_multilingual(value or ""))
    text = re.sub(r"(?<=\d)(?=[a-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)
    return " ".join(_apply_aliases(text).split())


def _clean_name(value: str) -> str:
    text = _normalized(value)
    # Keep the sellable unit size, discard only case-count logistics: 20 x 500 ml -> 500 ml.
    text = PACK_RE.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    text = re.sub(r"\borigin\s*:?[ ]*[a-z]{2,3}\b", " ", text, flags=re.I)
    text = re.sub(r"\borigin\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:eu|esp)\b$", " ", text, flags=re.I)
    return " ".join(text.split())


def _core_name(value: str) -> str:
    text = _clean_name(value)
    text = re.sub(rf"\b\d+(?:[.,]\d+)?\s*{UNIT_RE}\b", " ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", text)
    text = re.sub(r"\b(?:x|pcs|pc|stk|pack|case)\b", " ", text)
    return " ".join(text.split())


def _extract_item_size(value: str) -> tuple[str, float] | None:
    raw = (value or "").lower().replace(",", ".")
    pack_matches = list(re.finditer(r"\b(?:\d+(?:\.\d+)?\s*x\s*)+(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b", raw))
    if pack_matches:
        number, unit = pack_matches[-1].group(1), pack_matches[-1].group(2)
    else:
        matches = list(re.finditer(r"(?<!\w)(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b", raw))
        if not matches:
            return None
        number, unit = matches[-1].group(1), matches[-1].group(2)
    amount = float(number)
    if unit == "kg":
        return "mass", amount * 1000.0
    if unit == "g":
        return "mass", amount
    if unit == "l":
        return "volume", amount * 1000.0
    return "volume", amount


def _size_relation(query: str, candidate: str) -> tuple[bool, bool]:
    q_size = _extract_item_size(query)
    c_size = _extract_item_size(candidate)
    if not q_size or not c_size or q_size[0] != c_size[0]:
        return False, False
    tolerance = max(1.0, 0.02 * max(q_size[1], c_size[1]))
    exact = abs(q_size[1] - c_size[1]) <= tolerance
    return exact, not exact


def _score_text(query: str, candidate: str) -> float:
    q = _clean_name(query)
    c = _clean_name(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    overlap = len(q_tokens & c_tokens)
    query_coverage = overlap / max(1, len(q_tokens))
    candidate_coverage = overlap / max(1, len(c_tokens))
    wr = WRatio(q, c) / 100.0
    ts = token_set_ratio(q, c) / 100.0
    score = max(wr, ts) * 0.72 + candidate_coverage * 0.18 + query_coverage * 0.10
    return min(1.0, score)


def _score_core(query: str, candidate: str) -> float:
    q = _core_name(query)
    c = _core_name(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    overlap = len(q_tokens & c_tokens)
    query_coverage = overlap / max(1, len(q_tokens))
    candidate_coverage = overlap / max(1, len(c_tokens))
    wr = WRatio(q, c) / 100.0
    ts = token_set_ratio(q, c) / 100.0
    score = max(wr, ts) * 0.65 + candidate_coverage * 0.20 + query_coverage * 0.15
    # A one-word POS label must not swallow a long, specific import description.
    if len(c_tokens) == 1 and len(q_tokens) >= 3:
        score = min(score, 0.72)
    elif len(c_tokens) <= 2 and len(q_tokens) >= 5 and candidate_coverage < 1.0:
        score = min(score, 0.78)
    return min(1.0, score)


def _product_evidence(import_name: str, product: POSProduct) -> dict:
    best: dict | None = None
    for field, value in (
        ("product_name", product.product_name),
        ("official_name", product.official_name),
        ("printer_name", product.printer_name),
    ):
        if not value:
            continue
        full_score = _score_text(import_name, value)
        core_score = _score_core(import_name, value)
        size_exact, size_conflict = _size_relation(import_name, value)
        score = max(full_score, core_score * 0.97)
        if size_exact:
            score = min(1.0, score + 0.03)
        if size_conflict:
            score = min(score, 0.74)

        q_core_tokens = set(_core_name(import_name).split())
        c_core_tokens = set(_core_name(value).split())
        generic = len(c_core_tokens) == 1 and len(q_core_tokens) >= 3
        if generic:
            score = min(score, 0.74)

        evidence = {
            "score": score,
            "full_score": full_score,
            "core_score": core_score,
            "size_exact": size_exact,
            "size_conflict": size_conflict,
            "generic_candidate": generic,
            "matched_field": field,
            "matched_name": value,
            "name_key": _clean_name(value),
            "core_key": _core_name(value),
        }
        if best is None or evidence["score"] > best["score"]:
            best = evidence
    return best or {
        "score": 0.0, "full_score": 0.0, "core_score": 0.0,
        "size_exact": False, "size_conflict": False, "generic_candidate": False,
        "matched_field": "", "matched_name": "", "name_key": "", "core_key": "",
    }


def match_import_names(
    products: list[POSProduct],
    imports: list[SupplierProduct],
    auto_threshold: float = 0.80,
    review_threshold: float = 0.68,
    ambiguity_margin: float = 0.02,
) -> list[dict]:
    """Match import names directly to POS names. Images and IDs never influence scoring.

    Matching is intentionally evaluated at POS-name level. Multiple POS rows that expose
    the same matched name are one name candidate; their SKU identity remains explicitly
    ambiguous rather than suppressing an otherwise valid name match.
    """
    if not 0 <= review_threshold <= auto_threshold <= 1:
        raise ValueError("require 0 <= review_threshold <= auto_threshold <= 1")

    rows: list[dict] = []
    generator = CandidateGenerator(products, pool_size=100)
    for source in imports:
        candidates_by_id: dict[str, POSProduct] = {}
        for query in (source.name, _clean_name(source.name), _core_name(source.name)):
            if not query:
                continue
            for product in generator.generate(query):
                candidates_by_id[product.product_id] = product
        candidates = list(candidates_by_id.values())

        grouped: dict[str, list[tuple[dict, POSProduct]]] = defaultdict(list)
        for product in candidates:
            evidence = _product_evidence(source.name, product)
            key = evidence["name_key"] or f"product:{product.product_id}"
            grouped[key].append((evidence, product))

        scored_groups: list[tuple[float, dict, list[POSProduct]]] = []
        for items in grouped.values():
            evidence, _ = max(items, key=lambda item: item[0]["score"])
            group_products = [product for _, product in items]
            scored_groups.append((evidence["score"], evidence, group_products))
        scored_groups.sort(key=lambda item: item[0], reverse=True)

        if not scored_groups:
            rows.append({
                "sheet": source.sheet, "supplier": source.supplier, "import_name": source.name,
                "supplier_sku": source.supplier_sku or "", "status": "UNMATCHED", "score": 0.0,
                "core_score": 0.0, "top2_score": 0.0, "margin": 0.0, "match_method": "name_only",
                "matched_field": "", "matched_pos_rows": 0, "pos_identity_ambiguous": False,
                "size_conflict": False, "pos_product_id": "", "pos_sku": "", "pos_barcode": "",
                "pos_product_name": "", "pos_official_name": "", "pos_printer_name": "",
            })
            continue

        best_score, evidence, best_products = scored_groups[0]
        second_score = scored_groups[1][0] if len(scored_groups) > 1 else 0.0
        margin = best_score - second_score
        identity_ambiguous = len(best_products) > 1

        candidate_core_tokens = set(evidence["core_key"].split())
        strong_core = evidence["core_score"] >= 0.92 and len(candidate_core_tokens) >= 2
        exact_name = _clean_name(source.name) == evidence["name_key"]
        safe_auto = (
            not evidence["size_conflict"]
            and not evidence["generic_candidate"]
            and best_score >= auto_threshold
            and (margin >= ambiguity_margin or exact_name or strong_core)
        )
        if safe_auto:
            status = "AUTO_MATCHED"
        elif best_score >= review_threshold:
            status = "REVIEW"
        else:
            status = "UNMATCHED"

        representative = best_products[0]
        expose_identity = status != "UNMATCHED" and not identity_ambiguous
        rows.append({
            "sheet": source.sheet,
            "supplier": source.supplier,
            "import_name": source.name,
            "supplier_sku": source.supplier_sku or "",
            "status": status,
            "score": round(best_score, 6),
            "core_score": round(evidence["core_score"], 6),
            "top2_score": round(second_score, 6),
            "margin": round(margin, 6),
            "match_method": "name_only",
            "matched_field": evidence["matched_field"],
            "matched_pos_rows": len(best_products),
            "pos_identity_ambiguous": identity_ambiguous,
            "size_conflict": evidence["size_conflict"],
            "pos_product_id": representative.product_id if expose_identity else "",
            "pos_sku": representative.sku if expose_identity else "",
            "pos_barcode": (representative.barcode or "") if expose_identity else "",
            "pos_product_name": representative.product_name if status != "UNMATCHED" else "",
            "pos_official_name": representative.official_name if status != "UNMATCHED" else "",
            "pos_printer_name": representative.printer_name if status != "UNMATCHED" else "",
        })
    return rows


def summarize_name_matches(rows: list[dict]) -> dict:
    counts = Counter(str(row.get("status", "UNMATCHED")) for row in rows)
    total = len(rows)
    auto = counts["AUTO_MATCHED"]
    review = counts["REVIEW"]
    unmatched = counts["UNMATCHED"]
    return {
        "total_import_rows": total,
        "auto_matched": auto,
        "review": review,
        "unmatched": unmatched,
        "auto_match_rate_pct": round(auto / total * 100, 2) if total else 0.0,
        "candidate_coverage_pct": round((auto + review) / total * 100, 2) if total else 0.0,
    }


def write_name_match_outputs(rows: list[dict], summary: dict, output_dir):
    from pathlib import Path
    import json
    import pandas as pd

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx_path = output / "name_only_match.xlsx"
    csv_path = output / "name_only_match.csv"
    summary_path = output / "name_only_summary.json"

    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="matches", index=False)
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary", index=False)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"xlsx": xlsx_path, "csv": csv_path, "summary_json": summary_path}