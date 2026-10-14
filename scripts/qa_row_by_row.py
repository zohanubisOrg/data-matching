#!/usr/bin/env python3
"""
scripts/qa_row_by_row.py
------------------------
Screens embedded previews; never certifies full-resolution product QA:
output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx

For each row between --start-row and --end-row:
- Checks Column 23 (W): Customer original front image
- Checks Column 24 (X): Webshop studio front image (front-v3)
- Checks Column 25 (Y): Back image (back-v2)
- Evaluates Col 24 Vision Quality:
    * Background purity (#FFFFFF)
    * Single product verification (no double cans/objects)
    * Solidity check (no hollowed-out holes/bodies)
    * Canvas padding (not cut at borders)
- Emits structured JSON and summary report.
"""

from __future__ import annotations

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any
import cv2
import numpy as np
import openpyxl
from PIL import Image
import zxingcpp

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
EXCEL_PATH = ROOT / "output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx"
CHUNKS_DIR = ROOT / "output/catalog_pairs/qa_thumbnail_screening_v2"


def inspect_col24_image(img_obj: Any) -> tuple[bool, list[str]]:
    """Preview anomaly screening only; returns no full-resolution PASS."""
    flags = []
    try:
        data = img_obj._data()
        with Image.open(BytesIO(data)) as im:
            arr = np.asarray(im.convert("RGB"))

        # Background purity
        diff = np.abs(arr.astype(int) - 255).sum(axis=2)
        fg = (diff > 28).astype(np.uint8)
        # Suppress single-pixel JPEG compression noise
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

        total_area = int(np.sum(fg))
        if total_area < 50:
            return False, ["Blank or nearly empty image"]

        # Connected components (Single product check)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
        comps = []
        for l in range(1, num_labels):
            area = stats[l, cv2.CC_STAT_AREA]
            if area > (total_area * 0.05):
                comps.append((l, area, stats[l]))

        comps.sort(key=lambda x: x[1], reverse=True)
        if len(comps) >= 2:
            c1_area = comps[0][1]
            c2_area = comps[1][1]
            if c2_area > (c1_area * 0.15):
                # Check if vertically aligned (single bottle with transparent neck: cap + body)
                dx = abs(centroids[comps[0][0]][0] - centroids[comps[1][0]][0])
                if dx > 6.0:  # Horizontally separated products
                    flags.append(f"Multiple objects in frame ({len(comps)} components, dx={dx:.1f}px)")

        # Solidity check (Hollowed-out check)
        ys, xs = np.where(fg > 0)
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        bbox_area = (bx1 - bx0) * (by1 - by0)
        solidity = total_area / max(1, bbox_area)
        aspect = (bx1 - bx0) / max(1, (by1 - by0))

        if 0.4 < aspect < 2.5 and solidity < 0.28:
            flags.append(f"Hollowed-out packaging (solidity {solidity:.2f})")

        # Border touch / clipped edge (margin check)
        h, w = arr.shape[:2]
        if bx0 == 0 or by0 == 0 or bx1 >= w or by1 >= h:
            flags.append("Border touch / clipped edge")

        # Barcode is an observation; authentic one-sided fronts can include it.
        hits = zxingcpp.read_barcodes(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
        if hits:
            flags.append(f"Barcode observed: {[h.text for h in hits]}; verify authentic front / one-sided exception")

        flags.append("NOT_VERIFIED: thumbnail cannot certify identity, full packaging, native detail or correct face")
        return False, flags
    except Exception as e:
        return False, [f"Inspection error: {e}"]


def run_row_qa(start_row: int, end_row: int) -> dict[str, Any]:
    print(f"Loading workbook: {EXCEL_PATH}...")
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    ws = wb.active

    # Index images by (row, col)
    img_map = {}
    for img in ws._images:
        anchor = getattr(img, "anchor", None)
        from_cell = getattr(anchor, "_from", None)
        if from_cell:
            r = from_cell.row + 1
            c = from_cell.col + 1
            img_map[(r, c)] = img

    results = []
    total_rows = max(0, min(end_row, ws.max_row) - start_row + 1)
    passed_rows = 0
    defect_rows = 0
    empty_rows = 0

    print(f"\n{'Row':<5} | {'Barcode':<14} | {'Name':<25} | {'Col23':<6} | {'Col24':<6} | {'Col25':<6} | {'Status':<6} | {'Notes'}")
    print("-" * 95)

    for r in range(start_row, min(end_row + 1, ws.max_row + 1)):
        bc_val = ws.cell(r, 1).value
        name_val = ws.cell(r, 2).value
        barcode = str(bc_val).strip() if bc_val else ""
        name = str(name_val).strip()[:24] if name_val else ""
        record_id = str(ws.cell(r, 5).value or '').strip()

        img23 = img_map.get((r, 23))
        img24 = img_map.get((r, 24))
        img25 = img_map.get((r, 25))

        has_23 = img23 is not None
        has_24 = img24 is not None
        has_25 = img25 is not None

        if not barcode and not name and not record_id and not has_23 and not has_24 and not has_25:
            empty_rows += 1
            status = "EMPTY"
            notes = "Blank row"
        elif not has_24 and not has_25:
            empty_rows += 1
            status = "BLOCKED_NEEDS_SOURCE"
            notes = "No webshop pair"
        else:
            _, flags_24 = inspect_col24_image(img24) if has_24 else (False, ["Missing Col 24"])
            if has_24 and has_25 and all(f.startswith('NOT_VERIFIED:') for f in flags_24):
                status = "NOT_VERIFIED"
                notes = "; ".join(flags_24)
            else:
                status = "NEEDS_MANUAL_REVIEW"
                notes = "; ".join(flags_24) if flags_24 else "Missing images"

        print(f"{r:<5} | {barcode:<14} | {name:<25} | {'YES' if has_23 else 'NO':<6} | {'YES' if has_24 else 'NO':<6} | {'YES' if has_25 else 'NO':<6} | {status:<6} | {notes[:40]}")

        results.append({
            "row": r,
            "barcode": barcode,
            "record_id": record_id,
            "name": name,
            "col23_present": has_23,
            "col24_present": has_24,
            "col25_present": has_25,
            "status": status,
            "notes": notes,
        })

    summary = {
        "start_row": start_row,
        "end_row": end_row,
        "total_rows": total_rows,
        "passed_rows": passed_rows,
        "defect_rows": defect_rows,
        "empty_rows": empty_rows,
        "not_verified_rows": sum(r['status'] == 'NOT_VERIFIED' for r in results),
        "qa_pass": False,
        "review_rows": sum(r['status'] == 'NEEDS_MANUAL_REVIEW' for r in results),
        "results": results,
    }

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = CHUNKS_DIR / f"chunk_{start_row}_{end_row}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("-" * 95)
    print(f"Summary for Chunk Rows {start_row}-{end_row}:")
    print(f"  * Passed rows: {passed_rows}")
    print(f"  * Defect rows: {defect_rows}")
    print(f"  * Empty/Uncataloged rows: {empty_rows}")
    print(f"  * Chunk report saved to: {out_file}\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-row", type=int, default=4)
    parser.add_argument("--end-row", type=int, default=103)
    args = parser.parse_args()
    run_row_qa(args.start_row, args.end_row)
