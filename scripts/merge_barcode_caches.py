#!/usr/bin/env python3
"""
scripts/merge_barcode_caches.py
===============================
Merges all individual partition barcode scan caches (G1, G2, G3, G4, Nyt)
and integrates recovered barcodes into a unified `barcode_scan_cache.json`
for pipeline-zohanubis.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "output" / "shopify-zohanubis-image" / "reports"
PARTITIONS = ["G1", "G2", "G3", "G4", "Nyt"]


def merge_caches() -> Path:
    recovered_file = REPORTS_DIR / "recovered_g2_barcodes.json"
    recovered_g2: Dict[str, str] = {}
    if recovered_file.exists():
        with open(recovered_file, "r", encoding="utf-8") as f:
            recovered_g2 = json.load(f)
        print(f"Loaded {len(recovered_g2)} recovered G2 barcodes.")

    unified_records: List[dict] = []
    seen_paths: Set[str] = set()

    for part in PARTITIONS:
        cache_path = REPORTS_DIR / f"barcode_scan_cache_{part}.json"
        if not cache_path.exists():
            print(f"Warning: {cache_path.name} not found, skipping.")
            continue

        with open(cache_path, "r", encoding="utf-8") as f:
            items = json.load(f)

        part_count = 0
        part_bc_count = 0
        for it in items:
            # Inject recovered barcode if empty in G2
            if part == "G2" and not it.get("barcodes") and it.get("filename") in recovered_g2:
                it["barcodes"] = [recovered_g2[it["filename"]]]
                it["enhancement_used"] = True

            path_key = it.get("path")
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                unified_records.append(it)
                part_count += 1
                if it.get("barcodes"):
                    part_bc_count += 1

        print(f"[{part:<3}] Added {part_count:>4} items ({part_bc_count:>4} with barcode) from {cache_path.name}")

    target_file = REPORTS_DIR / "barcode_scan_cache.json"

    # Backup existing file if smaller (e.g. pilot run)
    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if len(old_data) < len(unified_records):
                backup_file = REPORTS_DIR / f"barcode_scan_cache_pilot_{len(old_data)}.json"
                shutil.copy2(target_file, backup_file)
                print(f"Backed up previous smaller cache ({len(old_data)} items) -> {backup_file.name}")
        except Exception:
            pass

    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(unified_records, f, indent=2)

    total_with_bc = sum(1 for x in unified_records if x.get("barcodes"))
    print("\n" + "=" * 60)
    print("UNIFIED BARCODE SCAN CACHE GENERATED")
    print(f"File Path        : {target_file}")
    print(f"Total Photos     : {len(unified_records)}")
    print(f"With Barcode     : {total_with_bc} ({total_with_bc / len(unified_records) * 100:.1f}%)")
    print("=" * 60)

    return target_file


if __name__ == "__main__":
    merge_caches()
