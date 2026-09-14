from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re

from ..models import POSProduct, SupplierProduct
from ..parsing.text_normalizer import GERMAN_VIET_SYNONYMS, normalize_text, strip_accents


_SPECIAL_CHARS = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss"})
_EXTRA_ALIASES = {
    "no added sugar": "noaddedsugar",
    "no sugar added": "noaddedsugar",
    "without added sugar": "noaddedsugar",
    "with added sugar": "addedsugar",
    "added sugar": "addedsugar",
    "sugar free": "sugarfree",
    "purple yam": "purple yam",
    "ube": "purple yam",
    "atchara": "papaya pickle",
    "sirup": "syrup",
    "suger": "sugar",
    "glass vermicelli": "glass noodle", "glass noodles": "glass noodle",
    "glasnudler": "glass noodle", "springrolls": "spring roll",
    "spring rolls": "spring roll", "forarsruller": "spring roll",
    "basmatiris": "basmati rice", "kokosmaelk": "coconut milk",
    "kokosvand": "coconut water", "kondenseret maelk": "condensed milk",
    "karrypulver": "curry powder", "kyllingefodder": "chicken feet",
    "gron bonne": "green bean", "graeskar": "pumpkin", "rod miso": "red miso",
    "brun shimeji": "brown shimeji", "choisam": "choi sam",
    "kaichoi": "kai choi", "casava": "cassava", "sort bonne": "black bean",
    "cassave": "cassava", "cassava grinded": "grated cassava",
    "citrongraes": "lemongrass", "lemon grass": "lemongrass",
    "lemongrass stems": "lemongrass", "litchi": "lychee",
    "surimi crabsticks": "surimi crab stick", "surimi crab partysticks": "surimi crab stick",
    "coffee mix": "coffee mix", "coffeemix": "coffee mix",
    "monosodium glutemate": "monosodium glutamate", "tumeric": "turmeric",
    "turamic": "turmeric", "vegatable": "vegetable", "veggies": "vegetable",
    "tof u": "tofu", "y akult": "yakult", "zig zag eel": "zigzag eel",
    "musselmeat": "mussel meat", "beancurd": "bean curd",
    "hotpot": "hot pot", "reiskraecker": "rice cracker", "kokos": "coconut",
    "gele": "jelly", "kaffe": "coffee",
    "liter": "l", "litre": "l",
}
_TOKEN_ALIASES = {
    "beans": "bean", "biscuits": "biscuit", "crackers": "cracker",
    "cakes": "cake", "chocolates": "chocolate", "drinks": "drink",
    "flowers": "flower", "leaves": "leaf", "limes": "lime",
    "mushrooms": "mushroom", "noodels": "noodle", "noodless": "noodle",
    "noodles": "noodle", "prawn": "shrimp", "ramyun": "ramen",
    "ramyon": "ramen", "rolls": "roll", "sauces": "sauce", "seeds": "seed",
    "shoots": "shoot", "shrimps": "shrimp", "sprouts": "sprout",
    "sticks": "stick", "yams": "yam",
}
_STOP_WORDS = {
    "a", "an", "and", "case", "de", "es", "for", "fur", "in", "it",
    "med", "mit", "of", "origin", "pack", "se", "style", "the",
    "type", "typ", "with",
}
_LOGISTICS = {"x", "pc", "pcs", "stk"}
_UNIT_RE = r"(?:kg|g|ml|cl|l|mg|oz)"
_SIZE_RE = re.compile(rf"(?<!\w)(\d+(?:[.,]\d+)?)\s*({_UNIT_RE})\b", re.I)
_PACK_SIZE_RE = re.compile(
    rf"\b(?:\d+(?:[.,]\d+)?\s*x\s*)+(\d+(?:[.,]\d+)?)\s*({_UNIT_RE})\b", re.I
)
_PACK_PCS_RE = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?\s*x\s*)*\d+(?:[.,]\d+)?\s*(?:pcs?|stk)\b", re.I
)
_FAMILY_BY_TOKEN = {
    "bean": "bean", "beef": "beef", "biscuit": "biscuit", "bread": "bread",
    "bun": "bun", "cake": "cake", "candy": "candy", "chips": "chips",
    "coffee": "beverage", "cream": "cream", "cracker": "cracker", "curry": "curry",
    "dace": "fish", "drink": "beverage", "duck": "duck", "fish": "fish",
    "flour": "flour", "juice": "beverage", "jam": "jam", "jelly": "jelly",
    "milk": "milk", "miso": "miso", "noodle": "noodle", "oil": "oil",
    "paste": "paste", "pork": "pork", "powder": "powder", "pudding": "pudding",
    "ramen": "noodle", "rice": "rice", "roll": "roll", "sauce": "sauce",
    "shrimp": "shrimp", "snack": "snack", "soup": "soup", "starch": "starch",
    "tea": "beverage", "tofu": "tofu", "vermicelli": "noodle", "water": "beverage",
}
_QUALIFIER_GROUPS = (
    {"black", "blue", "brown", "golden", "green", "red", "white", "yellow"},
    {"beef", "chicken", "duck", "fish", "pork", "shrimp", "vegetable"},
    {"hot", "mild", "spicy"},
    {"fresh", "frozen", "dried", "fried", "pickled", "raw", "roasted", "steamed"},
    {"salted", "unsalted"},
    {"sweetened", "unsweetened", "noaddedsugar", "addedsugar", "sugarfree"},
    {"glutinous", "nonglutinous"}, {"firm", "silken", "soft"},
    {"glutenfree", "vegan", "vegetarian"},
)
_FIELD_ORDER = {"product_name": 0, "official_name": 1, "printer_name": 2}


def _basic_text(value: object) -> str:
    text = str("" if value is None else value).casefold().translate(_SPECIAL_CHARS)
    text = normalize_text(strip_accents(text))
    text = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", text)
    return " ".join(text.split())


def _measurement_text(value: object) -> str:
    text = str("" if value is None else value).casefold().translate(_SPECIAL_CHARS)
    text = strip_accents(text).replace(",", ".").replace("×", "x")
    return " ".join(re.sub(r"[^a-z0-9.%]+", " ", text).split())


def _alias_pairs() -> tuple[tuple[str, str], ...]:
    aliases = {
        **{key: value for key, value in GERMAN_VIET_SYNONYMS.items() if key != "and"},
        **_EXTRA_ALIASES,
    }
    normalized = {_basic_text(key): _basic_text(value) for key, value in aliases.items()}
    return tuple(sorted(normalized.items(), key=lambda item: len(item[0]), reverse=True))


_ALIASES = _alias_pairs()


def _canonical_text(value: object) -> str:
    text = _basic_text(value)
    for source, target in _ALIASES:
        text = re.sub(rf"(?<![a-z0-9]){re.escape(source)}(?![a-z0-9])", target, text)
    return " ".join(_TOKEN_ALIASES.get(token, token) for token in text.split())


def _normalized_measurement(amount: float, unit: str) -> tuple[str, float]:
    if unit == "kg": return "mass", amount * 1000
    if unit == "mg": return "mass", amount / 1000
    if unit == "g": return "mass", amount
    if unit == "l": return "volume", amount * 1000
    if unit == "cl": return "volume", amount * 10
    if unit == "ml": return "volume", amount
    return "mass", amount * 28.349523125


def _extract_item_size(value: object) -> tuple[str, float] | None:
    text = _measurement_text(value)
    pack = _PACK_SIZE_RE.search(text)
    if pack:
        amount = float(pack.group(1).replace(",", "."))
        return _normalized_measurement(amount, pack.group(2).casefold())
    matches = list(_SIZE_RE.finditer(text))
    if not matches:
        return None
    amount = float(matches[-1].group(1).replace(",", "."))
    return _normalized_measurement(amount, matches[-1].group(2).casefold())


def _extract_case_pack(value: object) -> str:
    text = _measurement_text(value)
    match = _PACK_SIZE_RE.search(text) or _PACK_PCS_RE.search(text)
    return match.group(0) if match else ""


def _description_text(value: object) -> str:
    """Remove logistics expressions without discarding identity text around them."""
    text = _measurement_text(value)
    text = _PACK_SIZE_RE.sub(" ", text)
    text = _PACK_PCS_RE.sub(" ", text)
    return " ".join(text.split())


def _core_text(value: object) -> str:
    text = _canonical_text(_description_text(value))
    text = re.sub(r"\borigin\s+[a-z]{2,3}\b", " ", text)
    text = _PACK_SIZE_RE.sub(" ", text)
    text = _PACK_PCS_RE.sub(" ", text)
    text = _SIZE_RE.sub(" ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:alc|alcohol)\b", " ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*pack\b", " ", text)
    return " ".join(token for token in text.split() if token not in _STOP_WORDS | _LOGISTICS)


def _product_family(core: str) -> str:
    head = re.split(r"\b(?:for|in|with)\b", core, maxsplit=1)[0]
    families = [_FAMILY_BY_TOKEN[token] for token in head.split() if token in _FAMILY_BY_TOKEN]
    return families[-1] if families else ""


def _identity(value: object) -> dict:
    full = _canonical_text(value)
    core = _core_text(value)
    return {
        "full": full,
        "core": core,
        "tokens": frozenset(core.split()),
        "family": _product_family(_canonical_text(_description_text(value))),
        "item_size": _extract_item_size(value),
        "case_pack": _extract_case_pack(value),
    }


def _size_relation(left: tuple[str, float] | None, right: tuple[str, float] | None) -> tuple[bool, bool]:
    if not left or not right:
        return False, False
    if left[0] != right[0]:
        return False, True
    exact = abs(left[1] - right[1]) <= 1e-6
    return exact, not exact


def _format_item_size(item_size: tuple[str, float] | None) -> str:
    return f"{item_size[1]:g} {'g' if item_size[0] == 'mass' else 'ml'}" if item_size else ""


def _qualifier_conflict(query_tokens: frozenset[str], candidate_tokens: frozenset[str]) -> bool:
    for group in _QUALIFIER_GROUPS:
        query_values, candidate_values = query_tokens & group, candidate_tokens & group
        if query_values and candidate_values and query_values.isdisjoint(candidate_values):
            return True
    return False


def _missing_protected_qualifier(query_tokens: frozenset[str], candidate_tokens: frozenset[str]) -> bool:
    return any(query_tokens & group and not candidate_tokens & group for group in _QUALIFIER_GROUPS)


def _name_records(products: list[POSProduct]) -> list[dict]:
    records = []
    for row_index, product in enumerate(products):
        for field, raw_name in (
            ("product_name", product.product_name),
            ("official_name", product.official_name),
            ("printer_name", product.printer_name),
        ):
            if raw_name:
                records.append({
                    "row_index": row_index,
                    "product": product,
                    "field": field,
                    "raw_name": raw_name,
                    "identity": _identity(raw_name),
                })
    return records


def _dedupe_products(records: list[dict], query: dict) -> list[dict]:
    """Deduplicate name fields per POS row, never across distinct POS rows."""
    best: dict[int, dict] = {}
    for record in records:
        size_exact, _ = _size_relation(query["item_size"], record["identity"]["item_size"])
        rank = (int(size_exact), len(record["identity"]["tokens"]), -_FIELD_ORDER[record["field"]])
        row_index = int(record["row_index"])
        if row_index not in best or rank > best[row_index]["rank"]:
            best[row_index] = {**record, "rank": rank}
    return [best[key] for key in sorted(best)]


def _group_key(record: dict) -> tuple[str, tuple[str, float] | None]:
    identity = record["identity"]
    return identity["core"], identity["item_size"]


def _candidate_summary(records: list[dict]) -> dict[str, str]:
    ordered = sorted(records, key=lambda record: int(record["row_index"]))
    return {
        "candidate_names": " | ".join(record["raw_name"] for record in ordered),
        "candidate_product_ids": " | ".join(record["product"].product_id for record in ordered),
        "candidate_skus": " | ".join(record["product"].sku for record in ordered),
        "candidate_barcodes": " | ".join(record["product"].barcode or "" for record in ordered),
        "candidate_row_indexes": " | ".join(str(record["row_index"]) for record in ordered),
    }


def _result_row(
    source: SupplierProduct,
    query: dict,
    status: str,
    method: str,
    records: list[dict],
    reason: str = "",
    **flags,
) -> dict:
    records = _dedupe_products(records, query)
    groups = {_group_key(record) for record in records}
    representative_record = records[0] if records else None
    representative = representative_record["product"] if representative_record else None
    ambiguous = len(records) > 1
    expose_identity = status == "AUTO_MATCHED" and not ambiguous and representative is not None
    empty_candidates = {
        key: ""
        for key in (
            "candidate_names",
            "candidate_product_ids",
            "candidate_skus",
            "candidate_barcodes",
            "candidate_row_indexes",
        )
    }
    candidate_data = _candidate_summary(records) if records else empty_candidates
    return {
        "sheet": source.sheet,
        "supplier": source.supplier,
        "supplier_sku": source.supplier_sku or "",
        "import_name": source.name,
        "canonical_import_name": query["full"],
        "core_import_name": query["core"],
        "product_family": query["family"],
        "item_size": _format_item_size(query["item_size"]),
        "case_pack": query["case_pack"],
        "status": status,
        "match_method": method,
        "reason": reason,
        "candidate_group_count": len(groups),
        "matched_pos_rows": len(records),
        "pos_identity_ambiguous": ambiguous,
        "size_conflict": bool(flags.get("size_conflict")),
        "size_evidence_incomplete": bool(flags.get("size_evidence_incomplete")),
        "family_conflict": bool(flags.get("family_conflict")),
        "qualifier_conflict": bool(flags.get("qualifier_conflict")),
        "missing_protected_qualifier": bool(flags.get("missing_protected_qualifier")),
        "matched_field": representative_record["field"] if representative_record else "",
        "matched_name": representative_record["raw_name"] if representative_record else "",
        "pos_product_id": representative.product_id if expose_identity else "",
        "pos_sku": representative.sku if expose_identity else "",
        "pos_barcode": (representative.barcode or "") if expose_identity else "",
        "pos_product_name": representative.product_name if representative else "",
        "pos_official_name": representative.official_name if representative else "",
        "pos_printer_name": representative.printer_name if representative else "",
        **candidate_data,
    }


def match_import_names_no_fuzzy(products: list[POSProduct], imports: list[SupplierProduct]) -> list[dict]:
    """Match names deterministically with precision-first identity rules.

    Only unique canonical/core exact identities can auto-match. Token subset discovery
    is review assistance only and never identity proof.
    """
    records = _name_records(products)
    full_index, core_index, token_index = defaultdict(list), defaultdict(list), defaultdict(list)
    for record in records:
        identity = record["identity"]
        full_index[identity["full"]].append(record)
        core_index[identity["core"]].append(record)
        for token in identity["tokens"]:
            token_index[token].append(record)

    rows = []
    for source in imports:
        query, method = _identity(source.name), "canonical_exact"
        candidates = full_index.get(query["full"], [])
        if not candidates:
            method, candidates = "core_exact", core_index.get(query["core"], [])
        if not candidates:
            method, possible = "safe_subset", {}
            for token in query["tokens"]:
                for record in token_index.get(token, []):
                    possible[(record["row_index"], record["field"])] = record
            candidates = [
                record
                for record in possible.values()
                if len(record["identity"]["tokens"]) >= 2
                and record["identity"]["tokens"].issubset(query["tokens"])
            ]
        if not candidates:
            rows.append(_result_row(source, query, "UNMATCHED", "none", [], "no_deterministic_candidate"))
            continue

        clean, conflicts, conflict_flags = [], [], Counter()
        for record in _dedupe_products(candidates, query):
            identity = record["identity"]
            size_exact, size_conflict = _size_relation(query["item_size"], identity["item_size"])
            size_incomplete = method == "core_exact" and bool(query["item_size"]) != bool(identity["item_size"])
            family_conflict = bool(
                query["family"]
                and (
                    (identity["family"] and query["family"] != identity["family"])
                    or (not identity["family"] and identity["tokens"] != query["tokens"])
                )
            )
            qualifier_conflict = _qualifier_conflict(query["tokens"], identity["tokens"])
            missing_qualifier = _missing_protected_qualifier(query["tokens"], identity["tokens"])
            if size_conflict or family_conflict or qualifier_conflict or missing_qualifier:
                conflicts.append(record)
                conflict_flags.update({
                    "size_conflict": size_conflict,
                    "family_conflict": family_conflict,
                    "qualifier_conflict": qualifier_conflict,
                    "missing_protected_qualifier": missing_qualifier,
                })
            else:
                record["rank"] = (
                    int(size_exact),
                    int(not size_incomplete),
                    len(identity["tokens"]),
                    -_FIELD_ORDER[record["field"]],
                )
                record["size_evidence_incomplete"] = size_incomplete
                clean.append(record)

        if clean:
            best_rank = max(record["rank"][:3] for record in clean)
            selected = _dedupe_products(
                [record for record in clean if record["rank"][:3] == best_rank],
                query,
            )
            has_incomplete_size = any(record.get("size_evidence_incomplete") for record in selected)
            groups = {_group_key(record) for record in selected}
            if method == "safe_subset":
                rows.append(_result_row(
                    source,
                    query,
                    "REVIEW",
                    method,
                    selected,
                    "SAFE_SUBSET_REQUIRES_REVIEW",
                ))
            elif len(selected) != 1:
                rows.append(_result_row(
                    source,
                    query,
                    "REVIEW",
                    method,
                    selected,
                    "MULTIPLE_POS_ROWS_FOR_DETERMINISTIC_IDENTITY",
                ))
            elif len(groups) != 1:
                rows.append(_result_row(
                    source,
                    query,
                    "REVIEW",
                    method,
                    selected,
                    "multiple_deterministic_candidates",
                ))
            elif has_incomplete_size:
                rows.append(_result_row(
                    source,
                    query,
                    "REVIEW",
                    method,
                    selected,
                    "INCOMPLETE_SIZE_EVIDENCE",
                    size_evidence_incomplete=True,
                ))
            else:
                rows.append(_result_row(source, query, "AUTO_MATCHED", method, selected))
        else:
            active = [
                name
                for name in (
                    "size_conflict",
                    "family_conflict",
                    "qualifier_conflict",
                    "missing_protected_qualifier",
                )
                if conflict_flags[name]
            ]
            rows.append(_result_row(
                source,
                query,
                "REVIEW",
                method,
                conflicts,
                ",".join(active) or "deterministic_conflict",
                **conflict_flags,
            ))
    return rows


def summarize_no_fuzzy_matches(rows: list[dict]) -> dict:
    counts, total = Counter(str(row.get("status", "UNMATCHED")) for row in rows), len(rows)
    auto, review, unmatched = counts["AUTO_MATCHED"], counts["REVIEW"], counts["UNMATCHED"]
    resolved = sum(
        row.get("status") == "AUTO_MATCHED"
        and not row.get("pos_identity_ambiguous")
        and bool(row.get("pos_product_id"))
        and bool(row.get("pos_sku"))
        for row in rows
    )
    pct = lambda value: round(value / total * 100, 2) if total else 0.0
    return {
        "total_import_rows": total,
        "unique_import_names": len({str(row.get("import_name", "")).strip() for row in rows}),
        "auto_matched": auto,
        "unique_pos_identity_resolved": resolved,
        "review": review,
        "unmatched": unmatched,
        "auto_match_rate_pct": pct(auto),
        "unique_pos_identity_rate_pct": pct(resolved),
        "review_rate_pct": pct(review),
        "unmatched_rate_pct": pct(unmatched),
        "candidate_coverage_pct": pct(auto + review),
        "target_auto_ge_80": pct(auto) >= 80,
        "target_review_lt_20": pct(review) < 20,
        "match_method_counts": dict(Counter(str(row.get("match_method", "none")) for row in rows)),
    }


def write_no_fuzzy_outputs(rows: list[dict], summary: dict, output_dir: Path):
    import pandas as pd
    from openpyxl.styles import Font, PatternFill

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx_path, csv_path = output / "no_fuzzy_match.xlsx", output / "no_fuzzy_match.csv"
    summary_path = output / "no_fuzzy_summary.json"
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary_frame = pd.DataFrame([
        {
            "metric": key,
            "value": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value,
        }
        for key, value in summary.items()
    ])
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary_frame.to_excel(writer, sheet_name="summary", index=False)
        frame.to_excel(writer, sheet_name="matches", index=False)
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes, worksheet.auto_filter.ref = "A2", worksheet.dimensions
            worksheet.sheet_view.showGridLines = False
            for cell in worksheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(fill_type="solid", fgColor="1F4E78")
            for column in worksheet.columns:
                worksheet.column_dimensions[column[0].column_letter].width = min(
                    48,
                    max(12, max(len(str(cell.value or "")) for cell in column) + 2),
                )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"xlsx": xlsx_path, "csv": csv_path, "summary_json": summary_path}
