#!/usr/bin/env python3
r"""Audit front-v5 strictly in-place across all 1169 items (12 batches of 100).

Rules:
1. Audits ONLY output/catalog_pairs/tagged/front-v5 (no back-v2 or cross-folder fallback).
2. When a defective image is found, reprocesses it directly from the 5 original photo folders:
   - source-import/G1_original
   - source-import/G2_original
   - source-import/G3_Original
   - source-import/G4-original
   - source-import/Nyt25.09.26
3. Verifies newly reprocessed image in front-v5.
4. Reports metrics for each batch (First-pass rate, Reprocessed rate, Flagged rate, Time).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import openpyxl
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reprocess_from_originals import (
    build_barcode_index,
    reprocess_barcode_from_originals,
)

EXCEL_PATH = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
V5_DIR = ROOT / "output/catalog_pairs/tagged/front-v5"
DELIVERY_DIR = ROOT / "output/catalog_pairs/front-delivery-1169"

TARGET_CANVAS = 2400


def load_catalog_items() -> list[dict]:
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    sheet = wb.active
    back_bcs = set(f.stem.replace("-back", "") for f in BACK_DIR.glob("*.jpg"))
    seen = set()
    items = []
    
    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        bc = str(row[0]).strip() if row[0] is not None else ""
        name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if bc and bc in back_bcs and bc not in seen:
            seen.add(bc)
            items.append({
                "excel_row": row_idx,
                "barcode": bc,
                "name": name,
            })
    return items


def audit_single_v5_image(image_path: Path) -> tuple[bool, list[str], dict]:
    if not image_path.exists():
        return False, ["missing_front_v5_file"], {}
        
    with Image.open(image_path) as im:
        rgb = np.asarray(im.convert("RGB"))
        
    defects = []
    h, w, _ = rgb.shape
    if (w, h) != (TARGET_CANVAS, TARGET_CANVAS):
        defects.append(f"wrong_size_{w}x{h}")
        
    corners = [rgb[:32, :32], rgb[:32, -32:], rgb[-32:, :32], rgb[-32:, -32:]]
    min_corner = min(c.mean() for c in corners)
    if min_corner < 250.0:
        defects.append(f"gray_corners_{int(min_corner)}")
        
    dist = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    fg = dist > 20
    ys, xs = np.where(fg)
    if len(xs) < 100:
        defects.append("empty_or_tiny_product")
        return False, defects, {"plong": 0, "aspect": 0.0}
        
    pw = int(xs.max() - xs.min() + 1)
    ph = int(ys.max() - ys.min() + 1)
    plong = max(pw, ph)
    aspect = min(pw, ph) / max(1, plong)
    
    if plong < 1200:
        defects.append(f"small_product_{plong}px")
    if aspect < 0.18:
        defects.append(f"cut_to_strip_{aspect:.2f}")
        
    return len(defects) == 0, defects, {"plong": plong, "aspect": round(aspect, 2)}


def run_batch_audit(batch_num: int, batch_items: list[dict], orig_index: dict) -> dict:
    t0 = time.perf_counter()
    total = len(batch_items)
    first_pass_ok = []
    reprocessed_ok = []
    flagged = []
    
    for item in batch_items:
        bc = item["barcode"]
        front_p = V5_DIR / f"{bc}-front.jpg"
        
        is_clean, defects, metrics = audit_single_v5_image(front_p)
        if is_clean:
            first_pass_ok.append(item)
            # Ensure delivery has latest copy
            shutil.copy2(front_p, DELIVERY_DIR / f"{bc}-front.jpg")
        else:
            print(f"  [DEFECT DETECTED] Row {item['excel_row']} | {bc} | {item['name'][:25]}: {defects}")
            print(f"  -> Reprocessing from 5 original folders...")
            success, msg = reprocess_barcode_from_originals(bc, orig_index)
            if success:
                # Re-verify
                re_clean, re_defects, _ = audit_single_v5_image(front_p)
                if re_clean:
                    reprocessed_ok.append((item, msg))
                    print(f"  -> [REPROCESSED SUCCESS] {msg}")
                else:
                    flagged.append((item, re_defects, "reprocessed_still_defective"))
                    print(f"  -> [REPROCESSED FAILED AUDIT] {re_defects}")
            else:
                flagged.append((item, defects, msg))
                print(f"  -> [FLAGGED] {msg}")
                
    elapsed = time.perf_counter() - t0
    avg_ms = (elapsed / total) * 1000 if total > 0 else 0
    
    fp_rate = (len(first_pass_ok) / total) * 100
    rp_rate = (len(reprocessed_ok) / total) * 100
    fl_rate = (len(flagged) / total) * 100
    yield_rate = ((len(first_pass_ok) + len(reprocessed_ok)) / total) * 100
    
    print(f"\n=== BATCH {batch_num} AUDIT & REPROCESS SUMMARY ===")
    print(f"Total: {total} items | Time: {elapsed:.2f}s ({avg_ms:.1f} ms/photo)")
    print(f"1. First-Pass Clean: {len(first_pass_ok)} ({fp_rate:.1f}%)")
    print(f"2. Reprocessed from Originals: {len(reprocessed_ok)} ({rp_rate:.1f}%)")
    print(f"3. Flagged (no original or bad): {len(flagged)} ({fl_rate:.1f}%)")
    print(f"-> Batch Yield: {yield_rate:.1f}%\n")
    
    return {
        "batch_num": batch_num,
        "total": total,
        "first_pass": len(first_pass_ok),
        "reprocessed": len(reprocessed_ok),
        "flagged": len(flagged),
        "yield_rate": yield_rate,
        "elapsed": elapsed,
        "flagged_details": flagged,
    }


def main():
    print("=== STARTING PURE V5 AUDIT & ORIGINAL REPROCESSOR (1169 ITEMS) ===")
    all_items = load_catalog_items()
    print(f"Loaded {len(all_items)} catalog items in order.")
    
    print("Indexing 5 original photo folders...")
    orig_index = build_barcode_index()
    print(f"Indexed {len(orig_index)} unique barcodes from original photo folders.\n")
    
    batch_size = 100
    total_batches = (len(all_items) + batch_size - 1) // batch_size
    all_results = []
    
    for b_idx in range(total_batches):
        b_num = b_idx + 1
        start = b_idx * batch_size
        end = min(len(all_items), start + batch_size)
        batch = all_items[start:end]
        
        print(f">>> Running Batch {b_num}/{total_batches} (Items {start + 1} to {end})...")
        res = run_batch_audit(b_num, batch, orig_index)
        all_results.append(res)
        
    total_photos = sum(r["total"] for r in all_results)
    total_clean = sum(r["first_pass"] for r in all_results)
    total_reprocessed = sum(r["reprocessed"] for r in all_results)
    total_flagged = sum(r["flagged"] for r in all_results)
    total_time = sum(r["elapsed"] for r in all_results)
    
    print("=" * 60)
    print("=== FINAL 12 BATCHES SUMMARY ===")
    print("=" * 60)
    print(f"Total Audited in front-v5: {total_photos} photos")
    print(f"Total Time: {total_time:.1f} s")
    print(f"1. First-Pass Clean: {total_clean} ({(total_clean/total_photos)*100:.1f}%)")
    print(f"2. Reprocessed from Originals: {total_reprocessed} ({(total_reprocessed/total_photos)*100:.1f}%)")
    print(f"3. Flagged: {total_flagged} ({(total_flagged/total_photos)*100:.1f}%)")
    print(f"Overall Catalog Yield: {((total_clean + total_reprocessed)/total_photos)*100:.1f}%")
    
    # Save audit summary
    out_json = ROOT / "output/catalog_pairs/pure_v5_audit_summary.json"
    out_json.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Audit log saved to: {out_json}")


if __name__ == "__main__":
    main()
