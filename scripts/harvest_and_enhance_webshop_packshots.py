"""
CLI Orchestrator for Automated Web Packshot Harvesting & Gemini Enhancement.
Reads SKUs from Rabuta_Customer_Reshoot_Request.xlsx, searches OpenFoodFacts / Google Images,
validates with visual anchoring & Gemini, standardizes to 2048x2048 HD, and triggers deliverable re-exports.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import openpyxl

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from product_mapper.harvest.candidate_resolver import CandidateResolver
from product_mapper.harvest.canvas_standardizer import CanvasStandardizerAndEnhancer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HarvestOrchestrator")


def load_reshoot_skus_from_excel(reshoot_excel_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, bytes]]:
    """
    Parses Rabuta_Customer_Reshoot_Request.xlsx to extract SKU metadata and embedded demo images.
    Returns: (list_of_sku_dicts, dict_mapping_barcode_to_demo_bytes)
    """
    logger.info(f"Loading Reshoot Catalog: {reshoot_excel_path.name}...")
    wb = openpyxl.load_workbook(reshoot_excel_path, data_only=True)
    ws = wb.active

    # Extract demo thumbnails from Column AA (col 27)
    demo_images_by_barcode: Dict[str, bytes] = {}
    row_to_images: Dict[int, bytes] = {}
    for img in getattr(ws, "_images", []):
        try:
            r_idx = img.anchor._from.row + 1
            row_to_images[r_idx] = img._data()
        except Exception:
            continue

    items: List[Dict[str, Any]] = []
    # In Rabuta_Customer_Reshoot_Request.xlsx, Row 3 has headers. Data starts at Row 4.
    # Barcode is at Col 5 (E), Title DA is at Col 7 (G), Brand is at Col 8 (H)
    for r in range(4, ws.max_row + 1):
        bc = str(ws.cell(r, 5).value or "").strip()
        if not bc:
            continue
        clean_bc = bc.replace(".0", "")

        demo_bytes = row_to_images.get(r)
        if demo_bytes:
            demo_images_by_barcode[clean_bc] = demo_bytes

        item = {
            "row_idx": r,
            "barcode": clean_bc,
            "full_name_en": str(ws.cell(r, 6).value or "").strip(),
            "fuldt_navn_da": str(ws.cell(r, 7).value or "").strip(),
            "brand": str(ws.cell(r, 8).value or "").strip(),
            "variant": str(ws.cell(r, 11).value or "").strip(),
            "net_quantity": str(ws.cell(r, 14).value or "").strip(),
            "net_unit": str(ws.cell(r, 15).value or "g").strip(),
            "priority": str(ws.cell(r, 1).value or "").strip(),
            "reason": str(ws.cell(r, 2).value or "").strip(),
        }
        items.append(item)

    wb.close()
    logger.info(f"Loaded {len(items)} reshoot items, {len(demo_images_by_barcode)} visual demo anchors.")
    return items, demo_images_by_barcode


def harvest_and_enhance_pipeline(
    reshoot_excel: Path,
    output_front_dir: Path,
    limit: Optional[int] = None,
    auto_reexport: bool = True,
) -> int:
    """Executes the end-to-end harvesting and enhancement loop across the reshoot dataset."""
    t0 = time.time()
    items, demo_map = load_reshoot_skus_from_excel(reshoot_excel)

    if limit and limit > 0:
        items = items[:limit]
        logger.info(f"Targeting batch limit of {len(items)} SKUs for processing.")

    resolver = CandidateResolver()
    standardizer = CanvasStandardizerAndEnhancer(target_dim=2048, fill_ratio=0.84, min_laplacian=50.0)

    success_count = 0
    skipped_existing = 0
    fail_count = 0

    print("\n=================================================================")
    print(f"STARTING PACKSHOT HARVESTING & ENHANCEMENT ({len(items)} SKUs)")
    print("=================================================================")

    for i, item in enumerate(items, 1):
        bc = item["barcode"]
        brand = item["brand"]
        name = item["fuldt_navn_da"] or item["full_name_en"]
        dest_file = output_front_dir / f"{bc}-front.jpg"

        print(f"\n[{i}/{len(items)}] Processing Barcode: {bc} | {brand} - {name[:35]}")

        # Check if already exists
        if dest_file.exists() and dest_file.stat().st_size > 20000:
            print(f"  -> File already exists: {dest_file.name} (Skipping query)")
            skipped_existing += 1
            success_count += 1
            continue

        demo_bytes = demo_map.get(bc)
        # 1. Resolve candidate through multi-tier network harvester
        cand_img, raw_bytes, source = resolver.resolve_best_candidate(item, demo_bytes)
        if not cand_img:
            print(f"  -> {source}")
            fail_count += 1
            continue

        # 2. Standardize onto 2048x2048 studio canvas and sharpen
        success, final_path, laplacian_score, msg = standardizer.standardize_and_enhance(
            img=cand_img,
            barcode=bc,
            output_dir=output_front_dir,
        )

        if success and final_path:
            print(f"  -> SUCCESS! Source: [{source}] -> Saved 2048x2048: {final_path.name} ({msg})")
            success_count += 1
        else:
            print(f"  -> REJECTED during QA: {msg}")
            fail_count += 1

    elapsed = time.time() - t0
    print("\n=================================================================")
    print("HARVESTING & ENHANCEMENT SUMMARY")
    print("=================================================================")
    print(f"Total Processed          : {len(items)}")
    print(f"Successfully Harvested   : {success_count} (Recovered into Front/)")
    print(f"  - Newly Generated      : {success_count - skipped_existing}")
    print(f"  - Pre-Existing Clean   : {skipped_existing}")
    print(f"Failed / Kept in Reshoot : {fail_count}")
    print(f"Time Elapsed             : {elapsed:.2f}s")
    print("=================================================================")

    if auto_reexport and (success_count - skipped_existing) > 0:
        print("\n[RE-AUDIT] Triggering automatic re-audit and catalog update...")
        try:
            cmd1 = [sys.executable, "scripts/audit_and_export_reshoot_list.py"]
            subprocess.run(cmd1, check=True)
            print("Audit and customer reshoot deliverable updated successfully!")

            cmd2 = [sys.executable, "scripts/export_shopify_catalog.py"]
            subprocess.run(cmd2, check=True)
            print("Shopify CSV deliverables updated successfully!")
        except Exception as e:
            logger.error(f"Failed during auto-reexport: {e}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest and Enhance Webshop Packshots by Barcode")
    parser.add_argument(
        "--reshoot-excel",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image/Rabuta_Customer_Reshoot_Request.xlsx",
        help="Customer reshoot excel deliverable to process",
    )
    parser.add_argument(
        "--output-front-dir",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image/webshop_front_hd/Front",
        help="Destination directory for verified 2048x2048 front packshots",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only first N items (for testing/batching)",
    )
    parser.add_argument(
        "--no-reexport",
        action="store_true",
        help="Skip triggering automatic re-audit and Shopify CSV exports",
    )
    args = parser.parse_args()

    return harvest_and_enhance_pipeline(
        reshoot_excel=args.reshoot_excel,
        output_front_dir=args.output_front_dir,
        limit=args.limit,
        auto_reexport=not args.no_reexport,
    )


if __name__ == "__main__":
    sys.exit(main())
