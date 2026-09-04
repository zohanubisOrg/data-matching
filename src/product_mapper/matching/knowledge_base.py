from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

logger = logging.getLogger("product_mapper")


def load_knowledge_base(path: Path) -> dict[str, dict[str, str]]:
    """Loads human-approved mappings to enable Level-1 deterministic matching on rerun."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded %d approved mappings from knowledge base: %s", len(data), path)
        return data
    except Exception as e:
        logger.error("Failed to load knowledge base from %s: %s", path, e)
        return {}


def save_knowledge_base(mappings: dict[str, dict[str, str]], path: Path) -> None:
    """Saves approved mappings to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mappings, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d mappings to knowledge base: %s", len(mappings), path)


def import_review_decisions(review_file: Path, kb_file: Path) -> int:
    """
    Parses customer_review.xlsx, extracts approved selections (1, 2, 3),
    and persists them into knowledge_base.json for permanent Level 1 exact matching.
    """
    if not review_file.exists():
        raise FileNotFoundError(f"Review workbook not found: {review_file}")

    wb = load_workbook(review_file, data_only=True)
    if "Review" not in wb.sheetnames:
        raise ValueError("Workbook missing 'Review' sheet")

    ws = wb["Review"]
    headers = [str(cell.value or "").strip() for cell in ws[1]]
    
    col_map = {h: i for i, h in enumerate(headers)}
    required = ["Image", "Customer Selection"]
    for req in required:
        if req not in col_map:
            raise ValueError(f"Missing required column in Review sheet: {req}")

    kb = load_knowledge_base(kb_file)
    added_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        image_name = str(row[col_map["Image"]] or "").strip()
        selection = str(row[col_map["Customer Selection"]] or "").strip()

        if not image_name or not selection:
            continue

        if selection in {"1", "2", "3"}:
            cand_idx = int(selection)
            bc_col_name = f"Candidate {cand_idx} Barcode"
            barcode = str(row[col_map.get(bc_col_name, -1)] or "").strip() if bc_col_name in col_map else ""

            if barcode:
                kb[image_name] = {
                    "barcode": barcode,
                    "selection": selection,
                    "source": "customer_review",
                }
                added_count += 1
        elif selection.lower() in {"no match", "nomatch"}:
            kb[image_name] = {
                "barcode": "",
                "selection": "No Match",
                "source": "customer_review",
            }
            added_count += 1

    save_knowledge_base(kb, kb_file)
    return added_count
