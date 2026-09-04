from __future__ import annotations

from collections import Counter
import re

from rapidfuzz.fuzz import WRatio, token_set_ratio

from ..models import POSProduct, SupplierProduct
from ..parsing.text_normalizer import normalize_text, translate_multilingual
from .candidate_generator import CandidateGenerator


def _normalized(value: str) -> str:
    text = normalize_text(translate_multilingual(value or ""))
    # Treat compact units (120g/500ml) and spaced units (120 g/500 ml) equally.
    text = re.sub(r"(?<=\d)(?=[a-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)
    return " ".join(text.split())


def _score_name(query: str, candidate: str) -> float:
    q = _normalized(query)
    c = _normalized(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0

    q_tokens = set(q.split())
    c_tokens = set(c.split())
    coverage = len(q_tokens & c_tokens) / max(1, len(q_tokens))
    wr = WRatio(q, c) / 100.0
    ts = token_set_ratio(q, c) / 100.0

    # Token-set similarity can overrate short/generic POS names. Penalize it
    # when the POS candidate covers only a small part of the import name.
    if len(c_tokens) <= 2 and len(q_tokens) >= 4:
        ts *= 0.60 + 0.40 * coverage

    return min(1.0, max(wr, ts) * 0.90 + coverage * 0.10)


def _product_score(import_name: str, product: POSProduct) -> float:
    return max(
        _score_name(import_name, product.product_name),
        _score_name(import_name, product.official_name),
        _score_name(import_name, product.printer_name),
    )


def match_import_names(
    products: list[POSProduct],
    imports: list[SupplierProduct],
    auto_threshold: float = 0.88,
    review_threshold: float = 0.72,
    ambiguity_margin: float = 0.04,
) -> list[dict]:
    """Match import workbook product names directly to POS product names.

    No image, image filename, barcode, SKU, source ID, or supplier metadata is
    used as matching evidence. Barcode/SKU are returned only as POS metadata.
    """
    if not 0 <= review_threshold <= auto_threshold <= 1:
        raise ValueError("require 0 <= review_threshold <= auto_threshold <= 1")

    rows: list[dict] = []
    generator = CandidateGenerator(products, pool_size=80)
    for source in imports:
        candidates = generator.generate(source.name)
        scored = sorted(
            ((_product_score(source.name, product), product) for product in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        if not scored:
            rows.append({
                "sheet": source.sheet,
                "supplier": source.supplier,
                "import_name": source.name,
                "supplier_sku": source.supplier_sku or "",
                "status": "UNMATCHED",
                "score": 0.0,
                "top2_score": 0.0,
                "margin": 0.0,
                "match_method": "name_only",
                "pos_product_id": "",
                "pos_sku": "",
                "pos_barcode": "",
                "pos_product_name": "",
                "pos_official_name": "",
                "pos_printer_name": "",
            })
            continue

        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - second_score

        if best_score >= auto_threshold and (len(scored) == 1 or margin >= ambiguity_margin):
            status = "AUTO_MATCHED"
        elif best_score >= review_threshold:
            status = "REVIEW"
        else:
            status = "UNMATCHED"

        rows.append({
            "sheet": source.sheet,
            "supplier": source.supplier,
            "import_name": source.name,
            "supplier_sku": source.supplier_sku or "",
            "status": status,
            "score": round(best_score, 6),
            "top2_score": round(second_score, 6),
            "margin": round(margin, 6),
            "match_method": "name_only",
            "pos_product_id": best.product_id if status != "UNMATCHED" else "",
            "pos_sku": best.sku if status != "UNMATCHED" else "",
            "pos_barcode": (best.barcode or "") if status != "UNMATCHED" else "",
            "pos_product_name": best.product_name if status != "UNMATCHED" else "",
            "pos_official_name": best.official_name if status != "UNMATCHED" else "",
            "pos_printer_name": best.printer_name if status != "UNMATCHED" else "",
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
