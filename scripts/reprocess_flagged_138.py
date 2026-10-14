#!/usr/bin/env python3
"""
scripts/reprocess_flagged_138.py
--------------------------------
Reprocesses the 138 flagged items from the initial 1,169 scan using the latest
studio_front_v3_extractor with seam threshold 0.08 and edge purge.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from studio_front_v3_extractor import process_single_product
from run_and_audit_all_batches import audit_single_image

STATUS_FILE = ROOT / "output/catalog_pairs/full_audit_1169_status.json"

def main():
    if not STATUS_FILE.exists():
        print(f"Status file not found: {STATUS_FILE}")
        return

    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    flagged = data.get("flagged", [])
    print(f"Total flagged items to reprocess: {len(flagged)}")

    improved_to_dat = 0
    still_flagged = []

    for i, item in enumerate(flagged):
        bc = item["barcode"]
        prev_errors = item.get("errors", [])
        
        # Reprocess
        success = process_single_product(bc)
        
        # Re-audit
        res = audit_single_image(bc)
        if res["status"] == "ĐẠT":
            improved_to_dat += 1
            print(f"[{i+1}/{len(flagged)}] {bc}: ĐÃ ĐẠT! (Trước đó: {', '.join(prev_errors)})")
        else:
            still_flagged.append(res)
            print(f"[{i+1}/{len(flagged)}] {bc}: CHƯA ĐẠT ({', '.join(res['errors'])})")

    print("\n==========================================")
    print(f"TỔNG KẾT REPROCESS:")
    print(f"  Chuyển thành ĐẠT: {improved_to_dat}/{len(flagged)}")
    print(f"  Còn lại CHƯA ĐẠT: {len(still_flagged)}/{len(flagged)}")
    print("==========================================")

    out_path = ROOT / "output/catalog_pairs/reprocess_138_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "initial_flagged": len(flagged),
            "improved_to_dat": improved_to_dat,
            "remaining_flagged": still_flagged
        }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
