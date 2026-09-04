from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re

from ..models import POSProduct, SupplierProduct
from ..parsing.text_normalizer import normalize_text


def _normalized_exact(value: str) -> str:
    """Deterministic normalization only; no synonyms, translation, or fuzzy scoring."""
    text = normalize_text(value or "")
    # Formatting equivalence only: 500ml == 500 ml, 12pcs == 12 pcs.
    text = re.sub(r"(?<=\d)(?=[a-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)
    return " ".join(text.split())


def match_import_names_no_fuzzy(
    products: list[POSProduct],
    imports: list[SupplierProduct],
) -> list[dict]:
    """Strict name-only matching after deterministic normalization.

    Matching evidence is equality only against POS product_name, official_name,
    or printer_name. No image, barcode, SKU, supplier metadata, synonyms,
    translations, RapidFuzz, similarity score, threshold, or containment logic
    is used as matching evidence.
    """
    index: dict[str, list[tuple[POSProduct, str, str]]] = defaultdict(list)
    for product in products:
        for field, raw_name in (
            ("product_name", product.product_name),
            ("official_name", product.official_name),
            ("printer_name", product.printer_name),
        ):
            key = _normalized_exact(raw_name)
            if key:
                index[key].append((product, field, raw_name))

    rows: list[dict] = []
    for source in imports:
        normalized_import = _normalized_exact(source.name)
        raw_hits = index.get(normalized_import, [])

        # Deduplicate aliases from the same POS row while preserving all distinct POS identities.
        by_product: dict[str, tuple[POSProduct, str, str]] = {}
        for product, field, raw_name in raw_hits:
            by_product.setdefault(product.product_id, (product, field, raw_name))
        hits = list(by_product.values())

        if not hits:
            rows.append({
                "sheet": source.sheet,
                "supplier": source.supplier,
                "import_name": source.name,
                "normalized_import_name": normalized_import,
                "supplier_sku": source.supplier_sku or "",
                "status": "UNMATCHED",
                "match_method": "normalized_exact_name",
                "matched_field": "",
                "matched_name": "",
                "matched_pos_rows": 0,
                "pos_identity_ambiguous": False,
                "pos_product_id": "",
                "pos_sku": "",
                "pos_barcode": "",
                "pos_product_name": "",
                "pos_official_name": "",
                "pos_printer_name": "",
            })
            continue

        representative, matched_field, matched_name = hits[0]
        ambiguous = len(hits) > 1
        rows.append({
            "sheet": source.sheet,
            "supplier": source.supplier,
            "import_name": source.name,
            "normalized_import_name": normalized_import,
            "supplier_sku": source.supplier_sku or "",
            "status": "MATCHED",
            "match_method": "normalized_exact_name",
            "matched_field": matched_field,
            "matched_name": matched_name,
            "matched_pos_rows": len(hits),
            "pos_identity_ambiguous": ambiguous,
            "pos_product_id": "" if ambiguous else representative.product_id,
            "pos_sku": "" if ambiguous else representative.sku,
            "pos_barcode": "" if ambiguous else (representative.barcode or ""),
            "pos_product_name": representative.product_name,
            "pos_official_name": representative.official_name,
            "pos_printer_name": representative.printer_name,
        })
    return rows


def summarize_no_fuzzy_matches(rows: list[dict]) -> dict:
    counts = Counter(str(row.get("status", "UNMATCHED")) for row in rows)
    total = len(rows)
    matched = counts["MATCHED"]
    unmatched = counts["UNMATCHED"]
    return {
        "total_import_rows": total,
        "matched": matched,
        "unmatched": unmatched,
        "match_rate_pct": round(matched / total * 100, 2) if total else 0.0,
    }


def write_no_fuzzy_outputs(rows: list[dict], summary: dict, output_dir: Path):
    import pandas as pd

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx_path = output / "no_fuzzy_match.xlsx"
    csv_path = output / "no_fuzzy_match.csv"
    summary_path = output / "no_fuzzy_summary.json"

    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="matches", index=False)
        pd.DataFrame([summary]).to_excel(writer, sheet_name="summary", index=False)

    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"xlsx": xlsx_path, "csv": csv_path, "summary_json": summary_path}
