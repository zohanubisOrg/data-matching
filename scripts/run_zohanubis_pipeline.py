#!/usr/bin/env python3
"""Main CLI orchestrator for pipeline-zohanubis.

Pure-source, zero-cache, high-fidelity packshot processing pipeline.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import gc
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from product_mapper.zohanubis.sanitizer import ImageSanitizer, RawPhotoRecord
from product_mapper.zohanubis.barcode_scanner import ParallelBarcodeScanner, BarcodeScanResult
from product_mapper.zohanubis.reconciler import BarcodeReconciler, CatalogProduct
from product_mapper.zohanubis.hero_cropper import HeroCropper
from product_mapper.zohanubis.front_matcher import FrontViewMatcher
from product_mapper.zohanubis.matting_engine import MattingEngine
from product_mapper.zohanubis.studio_standardizer import StudioStandardizer
from product_mapper.zohanubis.quality_gate import QualityGate, QualityMetrics
from product_mapper.zohanubis.excel_embedder import ExcelDualEmbedder


PARTITION_FOLDER_NAMES: Dict[str, str] = {
    "G1": "G1_original",
    "G2": "G2_original",
    "G3": "G3_Original",
    "G4": "G4-original",
    "N25": "Nyt25.09.26",
    "Nyt": "Nyt25.09.26",
}


def find_customer_image(barcode: str, cust_map: Dict[str, Path]) -> Optional[Path]:
    """Finds matching customer packshot by barcode, supporting leading zero variants."""
    bc = barcode.strip()
    if bc in cust_map:
        return cust_map[bc]
    stripped = bc.lstrip("0")
    if stripped in cust_map:
        return cust_map[stripped]
    with_zero = "0" + bc
    if with_zero in cust_map:
        return cust_map[with_zero]
    return None


def process_partition_stream(
    partition_name: str,
    prods: List[CatalogProduct],
    customer_front_map: Dict[str, Path],
    demo_images: Dict[int, Image.Image],
    front_hd_dir: Path,
    back_hd_dir: Path,
    quarantine_dir: Path,
    customer_dir: Path,
    matting_model: str,
) -> Tuple[Dict[str, Path], Dict[str, Path], List[QualityMetrics]]:
    """Processes all products belonging to a single partition stream."""
    folder_name = PARTITION_FOLDER_NAMES.get(partition_name, partition_name)
    part_front_dir = front_hd_dir / folder_name
    part_back_dir = back_hd_dir / folder_name
    part_quarantine_dir = quarantine_dir / folder_name
    part_front_dir.mkdir(parents=True, exist_ok=True)
    part_back_dir.mkdir(parents=True, exist_ok=True)
    part_quarantine_dir.mkdir(parents=True, exist_ok=True)

    sanitizer = ImageSanitizer()
    hero_cropper = HeroCropper()
    matting_engine = MattingEngine(matting_model)
    standardizer = StudioStandardizer(canvas_size=2048)
    quality_gate = QualityGate()

    front_map: Dict[str, Path] = {}
    back_map: Dict[str, Path] = {}
    metrics_list: List[QualityMetrics] = []
    quarantined_products: List[Tuple[CatalogProduct, Image.Image, QualityMetrics]] = []

    total_p = len(prods)
    for idx, p in enumerate(prods, start=1):
        # 1. Customer Pre-Made Packshot Bypass
        cust_img_path = find_customer_image(p.barcode, customer_front_map)
        if cust_img_path is not None:
            print(f"[{folder_name:<13}] [{idx:>3}/{total_p}] {p.record_id} ({p.barcode})... [Customer Provided]", flush=True)
            with Image.open(cust_img_path) as c_img:
                c_rgb = c_img.convert("RGB")
            packshot_rgb = standardizer.fit_to_canvas(c_rgb)

            front_hd_path = part_front_dir / f"{p.barcode}_front.jpg"
            packshot_rgb.save(front_hd_path, "JPEG", quality=95, optimize=True)
            front_map[p.record_id] = front_hd_path

            cust_save_path = customer_dir / f"{p.barcode}_front.jpg"
            if not cust_save_path.exists():
                packshot_rgb.save(cust_save_path, "JPEG", quality=95, optimize=True)

            back_src = p.verified_back_photos[0] if p.verified_back_photos else p.selected_front_photo
            if back_src:
                raw_back = sanitizer.load_normalized_image(back_src)
                isolated_back, _ = hero_cropper.isolate_back(
                    raw_back, barcode_center=p.barcode_center, strategy=p.strategy
                )
                back_hd_path = part_back_dir / f"{p.barcode}_back.jpg"
                if max(isolated_back.size) > 2048:
                    isolated_back.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                isolated_back.save(back_hd_path, "JPEG", quality=92, optimize=True)
                back_map[p.record_id] = back_hd_path

            metrics = QualityMetrics(
                record_id=p.record_id,
                barcode=p.barcode,
                decision="PASS",
                solidity=1.0,
                n_components=1,
                canvas_clipping_px=30,
                blur_score=100.0,
                fill_ratio=0.80,
                warning_reasons=["Customer pre-made packshot used (AI matting skipped)"],
                fail_reasons=[],
            )
            metrics_list.append(metrics)
            continue

        # 2. Product Requires Studio Extraction
        if not p.selected_front_photo:
            continue

        print(f"[{folder_name:<13}] [{idx:>3}/{total_p}] {p.record_id} ({p.barcode})...", end="", flush=True)
        demo_img = demo_images.get(p.row_idx)

        raw_front = sanitizer.load_normalized_image(p.selected_front_photo)
        if max(raw_front.size) > 2400:
            raw_front.thumbnail((2400, 2400), Image.Resampling.BILINEAR)

        isolated_front, was_isolated = hero_cropper.isolate_front(
            raw_front, demo_img=demo_img, barcode_center=p.barcode_center, strategy=p.strategy
        )

        rgba_img, alpha_mask = matting_engine.remove_background(isolated_front, enable_hole_protection=True)
        packshot_rgb, std_mask, bbox = standardizer.standardize(rgba_img)

        # Back photo isolation
        back_src = p.verified_back_photos[0] if p.verified_back_photos else p.selected_front_photo
        if back_src:
            raw_back = sanitizer.load_normalized_image(back_src)
            if max(raw_back.size) > 2400:
                raw_back.thumbnail((2400, 2400), Image.Resampling.BILINEAR)
            isolated_back, _ = hero_cropper.isolate_back(
                raw_back, barcode_center=p.barcode_center, strategy=p.strategy
            )
            back_hd_path = part_back_dir / f"{p.barcode}_back.jpg"
            if max(isolated_back.size) > 2048:
                isolated_back.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            isolated_back.save(back_hd_path, "JPEG", quality=92, optimize=True)
            back_map[p.record_id] = back_hd_path

        # Quality Gate Evaluation
        metrics = quality_gate.evaluate_packshot(packshot_rgb, std_mask, p.record_id, p.barcode)

        if metrics.decision == "HARD_FAIL":
            # Stage into quarantine
            q_img_path = part_quarantine_dir / f"{p.barcode}_quarantine.jpg"
            packshot_rgb.save(q_img_path, "JPEG", quality=92)
            q_meta_path = part_quarantine_dir / f"{p.barcode}_defect.json"
            q_meta_path.write_text(json.dumps({
                "record_id": p.record_id,
                "barcode": p.barcode,
                "fail_reasons": metrics.fail_reasons,
                "solidity": metrics.solidity,
                "n_components": metrics.n_components,
            }, indent=2), encoding="utf-8")
            quarantined_products.append((p, raw_front, metrics))
            print(f" -> HARD_FAIL [Staged to Quarantine]", flush=True)
        else:
            front_hd_path = part_front_dir / f"{p.barcode}_front.jpg"
            packshot_rgb.save(front_hd_path, "JPEG", quality=95, optimize=True)
            front_map[p.record_id] = front_hd_path
            metrics_list.append(metrics)
            print(f" -> {metrics.decision}", flush=True)

        if idx % 8 == 0:
            gc.collect()

    # 3. Two-Stage Quarantine Healing Loop
    if quarantined_products:
        print(f"\n[{folder_name:<13}] [QUARANTINE HEALER] Executing automated retry for {len(quarantined_products)} staged items...", flush=True)
        for qp, q_raw, q_metrics in quarantined_products:
            try:
                # Level 1: Fallback with conservative center crop and wider margin
                w_q, h_q = q_raw.size
                pad_x, pad_y = int(w_q * 0.08), int(h_q * 0.08)
                healed_crop = q_raw.crop((pad_x, pad_y, w_q - pad_x, h_q - pad_y))
                h_rgba, _ = matting_engine.remove_background(healed_crop, enable_hole_protection=True)
                h_packshot, h_mask, _ = standardizer.standardize(h_rgba)
                h_metrics = quality_gate.evaluate_packshot(h_packshot, h_mask, qp.record_id, qp.barcode)

                if h_metrics.decision in ("PASS", "WARNING/SOFT-PASS") or h_metrics.solidity >= 0.70:
                    front_hd_path = part_front_dir / f"{qp.barcode}_front.jpg"
                    h_packshot.save(front_hd_path, "JPEG", quality=95, optimize=True)
                    front_map[qp.record_id] = front_hd_path
                    h_metrics.decision = "HEALED_PASS"
                    h_metrics.warning_reasons.append("Recovered via Quarantine Healing Loop")
                    metrics_list.append(h_metrics)
                    print(f"[{folder_name:<13}]   Healed {qp.record_id} ({qp.barcode}) -> HEALED_PASS", flush=True)
                else:
                    metrics_list.append(q_metrics)
                    print(f"[{folder_name:<13}]   Unresolved {qp.record_id} -> RETAINED IN QUARANTINE", flush=True)
            except Exception:
                metrics_list.append(q_metrics)

    return front_map, back_map, metrics_list


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="pipeline-zohanubis: Pure-source e-commerce image pipeline"
    )
    parser.add_argument(
        "--excel",
        type=Path,
        default=ROOT / "source-import/Rabuta_master_SKU_categories.xlsx",
        help="Path to master catalog spreadsheet",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image",
        help="Root output directory for all deliverables",
    )
    parser.add_argument(
        "--customer-dir",
        type=Path,
        default=ROOT / "source-import/customer-send-me-front-product",
        help="Directory of customer-provided front product images",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Max CPU worker processes for parallel scanning",
    )
    parser.add_argument(
        "--pilot",
        type=int,
        default=None,
        help="Limit execution to N pilot items across partitions",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run across all catalog items",
    )
    parser.add_argument(
        "--pass1-only",
        action="store_true",
        help="Run Pass 1 screening & reconciliation only without matting",
    )
    parser.add_argument(
        "--matting-model",
        type=str,
        default="birefnet-general",
        help="Matting model session name (birefnet-general or u2net)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    front_hd_dir = output_dir / "webshop_front_hd"
    back_hd_dir = output_dir / "webshop_back_hd"
    customer_dir = output_dir / "customer_provided"
    reports_dir = output_dir / "reports"
    quarantine_dir = output_dir / "quarantine_for_retry"

    front_hd_dir.mkdir(parents=True, exist_ok=True)
    back_hd_dir.mkdir(parents=True, exist_ok=True)
    customer_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    for folder_name in set(PARTITION_FOLDER_NAMES.values()):
        (front_hd_dir / folder_name).mkdir(parents=True, exist_ok=True)
        (back_hd_dir / folder_name).mkdir(parents=True, exist_ok=True)
        (quarantine_dir / folder_name).mkdir(parents=True, exist_ok=True)

    print("=================================================================")
    print("           PIPELINE-ZOHANUBIS: CLEAN-SHEET ORCHESTRATOR           ")
    print("=================================================================")
    print(f"Master Catalog : {args.excel}")
    print(f"Output Root    : {output_dir}")
    print(f"Customer Root  : {args.customer_dir}")
    print(f"Workers        : {args.workers or 'Auto (ThreadPool-4)'}")
    print(f"Pilot Mode     : {args.pilot if args.pilot else 'Full Run'}")
    print("-----------------------------------------------------------------")

    total_start = time.time()

    # -------------------------------------------------------------
    # STAGE 0A: CUSTOMER-PROVIDED IMAGES INGESTION
    # -------------------------------------------------------------
    customer_front_map: Dict[str, Path] = {}
    if args.customer_dir.exists():
        for entry in args.customer_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                match = re.match(r"^([0-9A-Za-z]+)-front", entry.name)
                if match:
                    bc = match.group(1).strip()
                    customer_front_map[bc] = entry
                    if bc.startswith("0"):
                        customer_front_map[bc.lstrip("0")] = entry
        print(f"[STAGE 0A] Customer pre-made front repository indexed: {len(customer_front_map)} barcodes detected")

    # -------------------------------------------------------------
    # STAGE 0B: INPUT SANITIZATION & RAW DISCOVERY
    # -------------------------------------------------------------
    print("\n[STAGE 0B] Discovering and indexing raw photography from 5 sources...")
    sanitizer = ImageSanitizer()
    partition_photos = sanitizer.discover_raw_photos()
    all_raw_records: List[RawPhotoRecord] = []
    for part, recs in partition_photos.items():
        print(f"  Partition {part:<4}: {len(recs)} valid raw photos indexed")
        all_raw_records.extend(recs)
    print(f"Total raw photos discovered: {len(all_raw_records)}")

    # -------------------------------------------------------------
    # STAGE 1: MULTI-ANGLE PARALLEL BARCODE SCANNING
    # -------------------------------------------------------------
    if args.pilot:
        records_to_scan = []
        for part, recs in partition_photos.items():
            records_to_scan.extend(recs[:15])  # 15 from each partition = 75 photos
        print(f"\n[STAGE 1] Pilot mode active: scanning {len(records_to_scan)} sample photos across 5 partitions...")
    else:
        records_to_scan = all_raw_records
        print(f"\n[STAGE 1] Full catalog mode: scanning all {len(records_to_scan)} raw photos in parallel...")

    scanner = ParallelBarcodeScanner(max_workers=args.workers)
    t_scan_start = time.time()
    scan_results = scanner.scan_records(records_to_scan)
    print(f"Parallel scan complete in {time.time() - t_scan_start:.2f}s!")
    photos_with_barcode = sum(1 for r in scan_results if r.barcodes)
    print(f"Photos with confirmed barcodes: {photos_with_barcode}/{len(scan_results)}")

    # -------------------------------------------------------------
    # STAGE 2: 3-WAY RECONCILIATION & GAP ANALYSIS
    # -------------------------------------------------------------
    print("\n[STAGE 2] Reconciling barcodes with master catalog...")
    reconciler = BarcodeReconciler(args.excel, reports_dir)
    reconcile_summary = reconciler.reconcile(scan_results, customer_front_map=customer_front_map)

    print(f"  Catalog Total Rows   : {reconcile_summary.total_catalog_rows}")
    print(f"  Matched Back Photos  : {reconcile_summary.matched_count}")
    print(f"  Missing SKUs         : {reconcile_summary.missing_count}")
    print(f"  Orphan Barcode Photos: {reconcile_summary.orphan_count}")
    print(f"  Gap Report Generated : {reconcile_summary.missing_report_path}")

    if args.pass1_only:
        print("\nPass 1 complete (--pass1-only requested). Exiting successfully.")
        return 0

    # -------------------------------------------------------------
    # STAGE 3: HERO ISOLATION & FRONT MATCHING (PASS 1 EMBEDDING)
    # -------------------------------------------------------------
    print("\n[STAGE 3] Matching front views against Column W ground truth demo...")
    matcher = FrontViewMatcher(args.excel)
    matcher.load_demo_images()
    print(f"Loaded {len(matcher.demo_images)} demo reference thumbnails from Excel.")

    # Select products to process
    catalog = reconcile_summary.catalog_products
    target_prods = list(catalog.values())

    if args.pilot:
        # Balanced pilot: some customer items + some studio items across partitions
        pilot_cust = []
        pilot_studio = []
        seen_parts = set()
        for p in target_prods:
            c_path = find_customer_image(p.barcode, customer_front_map)
            if c_path and len(pilot_cust) < args.pilot // 2:
                pilot_cust.append(p)
            elif not c_path and p.verified_back_photos and p.partition not in seen_parts:
                pilot_studio.append(p)
                seen_parts.add(p.partition)
                if len(pilot_studio) >= (args.pilot - len(pilot_cust)):
                    break

        target_prods = pilot_cust + pilot_studio
        if not target_prods:
            target_prods = list(catalog.values())[:args.pilot]
        print(f"Pilot execution selected: {len(target_prods)} products ({len(pilot_cust)} customer, {len(pilot_studio)} studio across {seen_parts})")

    # Build blacklist of all verified back photo paths
    all_back_paths: Set[Path] = set()
    for p in catalog.values():
        all_back_paths.update(p.verified_back_photos)

    matched_front_results = {}
    hero_cropper = HeroCropper()

    for p in target_prods:
        # If customer already provided image, front is already determined!
        if find_customer_image(p.barcode, customer_front_map):
            continue

        if p.selected_front_photo is None:
            cands = partition_photos.get(p.partition, [])
            match_res = matcher.match_product_front(p, cands, all_back_paths)
            if match_res.winning_photo_path:
                p.selected_front_photo = match_res.winning_photo_path
                matched_front_results[p.record_id] = match_res
        else:
            matched_front_results[p.record_id] = p.selected_front_photo

    print(f"Front views successfully matched: {len(matched_front_results)}/{len(target_prods)}")

    # -------------------------------------------------------------
    # STAGE 4: CONCURRENT PARTITION PROCESSING & QUALITY GATE (PASS 2)
    # -------------------------------------------------------------
    print("\n[STAGE 4] Executing 5-partition concurrent alpha matting, quarantine staging & quality gate...")

    # Group target products by partition
    partition_groups: Dict[str, List[CatalogProduct]] = collections.defaultdict(list)
    for p in target_prods:
        partition_groups[p.partition].append(p)

    front_embed_map: Dict[str, Path] = {}
    back_embed_map: Dict[str, Path] = {}
    quality_records: List[QualityMetrics] = []

    # Concurrently execute all active partitions
    active_partitions = list(partition_groups.keys())
    num_threads = min(5, len(active_partitions)) if active_partitions else 1
    print(f"Launching {num_threads} parallel partition workers for partitions: {active_partitions}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_part = {
            executor.submit(
                process_partition_stream,
                part_name,
                partition_groups[part_name],
                customer_front_map,
                matcher.demo_images,
                front_hd_dir,
                back_hd_dir,
                quarantine_dir,
                customer_dir,
                args.matting_model,
            ): part_name
            for part_name in active_partitions
        }

        for future in concurrent.futures.as_completed(future_to_part):
            part_name = future_to_part[future]
            try:
                p_front, p_back, p_metrics = future.result()
                front_embed_map.update(p_front)
                back_embed_map.update(p_back)
                quality_records.extend(p_metrics)
                folder_n = PARTITION_FOLDER_NAMES.get(part_name, part_name)
                print(f"[STREAM FINISHED] Partition {part_name} ({folder_n}): {len(p_front)} front, {len(p_back)} back, {len(p_metrics)} records.")
            except Exception as e:
                print(f"[ERROR] Partition {part_name} worker failed with exception: {e}")
                import traceback
                traceback.print_exc()

    # Save ledger
    ledger_path = reports_dir / "zohanubis_audit_ledger.json"
    quality_gate = QualityGate()
    quality_gate.save_ledger(quality_records, ledger_path)
    print(f"\nAudit ledger saved to: {ledger_path}")

    # -------------------------------------------------------------
    # STAGE 5: ATOMIC EXCEL DUAL-IMAGE EMBEDDING & DELIVERABLES
    # -------------------------------------------------------------
    print("\n[STAGE 5] Embedding dual images into Master Excel workbook...")
    embedder = ExcelDualEmbedder(args.excel)
    output_excel_path = reports_dir / "Rabuta_master_SKU_categories_zohanubis.xlsx"
    target_ids = {p.record_id for p in target_prods} if args.pilot else None
    final_excel = embedder.embed_dual_images(
        output_excel_path=output_excel_path,
        product_front_map=front_embed_map,
        product_back_map=back_embed_map,
        target_record_ids=target_ids,
    )
    print(f"Final enriched Excel workbook generated in reports: {final_excel}")

    # Copy workbook directly to output root for easy 1-click access
    root_excel_path = output_dir / "Rabuta_master_SKU_categories_zohanubis.xlsx"
    try:
        shutil.copy2(final_excel, root_excel_path)
        print(f"Direct root copy created: {root_excel_path}")
    except (PermissionError, OSError):
        print(f"[NOTE] Root copy skipped because {root_excel_path.name} is open in Excel. Enriched file is safe in {final_excel}.")

    # Copy missing report directly to output root
    root_missing_path = output_dir / "Zohanubis_Missing_SKU_Report.xlsx"
    try:
        shutil.copy2(reconcile_summary.missing_report_path, root_missing_path)
    except (PermissionError, OSError):
        pass

    # Write Manifest
    manifest_path = output_dir / "README_DELIVERABLES.txt"
    customer_used_count = sum(1 for m in quality_records if "Customer" in str(m.warning_reasons))
    ai_matted_count = len(quality_records) - customer_used_count
    quarantined_count = sum(1 for p in quarantine_dir.rglob("*_defect.json"))
    manifest_text = f"""===================================================================
SHOPIFY-ZOHANUBIS-IMAGE: CLEAN-SHEET PRODUCTION DELIVERABLES
===================================================================
Master Catalog: {args.excel.name}
Total Products Processed in this run: {len(quality_records)}
- Customer Packshots Used (AI Matting Skipped): {customer_used_count}
- Studio Photos AI-Matted (Dual-Hero Isolated) : {ai_matted_count}
- Quarantined Defect Photos (Staged for Review) : {quarantined_count}

FOLDER STRUCTURE:
- webshop_front_hd/<partition>/ : 2048x2048 px pure white (#FFFFFF), centered, sRGB, subtle shadow.
- webshop_back_hd/<partition>/  : High-resolution studio back photos isolated from studio photography.
- quarantine_for_retry/<partition>/ : Staged defects with metadata for automated/manual review.
- customer_provided/            : Standardized 2048x2048 customer-provided packshots.
- reports/                      :
    * Rabuta_master_SKU_categories_zohanubis.xlsx (Dual embedded thumbnails in Col 24 & 25)
    * Zohanubis_Missing_SKU_Report.xlsx (Gap report for missing / unphotographed SKUs)
    * zohanubis_audit_ledger.json (Machine-readable audit metrics for all SKUs)
- Rabuta_master_SKU_categories_zohanubis.xlsx : Root copy for instant opening.
===================================================================
"""
    manifest_path.write_text(manifest_text, encoding="utf-8")

    total_time = time.time() - total_start
    print("\n=================================================================")
    print("                    PIPELINE EXECUTION COMPLETE                   ")
    print("=================================================================")
    print(f"Total Elapsed Time : {total_time:.2f}s")
    print(f"Products Processed : {len(quality_records)}")
    print(f"  * Customer Skipped : {customer_used_count}")
    print(f"  * Studio AI Matting: {ai_matted_count}")
    print(f"Deliverables Root  : {output_dir}")
    print(f"Enriched Excel     : {root_excel_path.name}")
    print(f"Missing Report     : {root_missing_path.name}")
    print(f"Audit Ledger       : {ledger_path.name}")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
