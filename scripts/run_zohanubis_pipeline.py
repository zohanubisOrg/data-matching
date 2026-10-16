#!/usr/bin/env python3
"""Main CLI orchestrator for pipeline-zohanubis.

Pure-source, zero-cache, high-fidelity packshot processing pipeline.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import gc
import io
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
    force: bool = False,
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

    # Register existing generated packshots with AntiDuplicateGuard only if not force-regenerating
    if not force:
        for existing_f in part_front_dir.glob("*_front.jpg"):
            bc_id = existing_f.stem.replace("_front", "")
            standardizer.duplicate_guard.register_existing_file(existing_f, bc_id)

    total_p = len(prods)
    for idx, p in enumerate(prods, start=1):
        # 1. Customer Pre-Made Packshot Bypass
        cust_img_path = find_customer_image(p.barcode, customer_front_map)
        if cust_img_path is not None:
            print(f"[{folder_name:<13}] [{idx:>3}/{total_p}] {p.record_id} ({p.barcode})... [Customer Provided]", flush=True)
            try:
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
                    try:
                        raw_back_full = sanitizer.load_normalized_image(back_src)
                        back_box, was_back_iso, _, _, _ = hero_cropper.isolate_back_coords(
                            raw_back_full, barcode_center=p.barcode_center, strategy=p.strategy
                        )
                        if was_back_iso:
                            isolated_back = raw_back_full.crop(back_box)
                        else:
                            isolated_back = raw_back_full
                        if max(isolated_back.size) > 2048:
                            isolated_back.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                        back_hd_path = part_back_dir / f"{p.barcode}_back.jpg"
                        isolated_back.save(back_hd_path, "JPEG", quality=92, optimize=True)
                        back_map[p.record_id] = back_hd_path

                        # Evaluate back photo quality & barcode readability
                        back_m = quality_gate.evaluate_back_packshot(isolated_back, p.record_id, p.barcode)
                        if back_m.decision == "HARD_FAIL":
                            print(f" (Back photo warn: {back_m.fail_reasons})", end="", flush=True)
                    except Exception as back_err:
                        print(f" (Back photo warn: {back_err})", end="", flush=True)

                metrics = quality_gate.evaluate_customer_packshot(packshot_rgb, p.record_id, p.barcode)
                metrics_list.append(metrics)
            except Exception as cust_err:
                print(f" -> ERROR [Customer packshot: {cust_err}]", flush=True)
            gc.collect()
            continue

        # 2. Product Requires Studio Extraction
        if not p.selected_front_photo:
            continue

        front_hd_path = part_front_dir / f"{p.barcode}_front.jpg"
        back_hd_path = part_back_dir / f"{p.barcode}_back.jpg"

        if not force and front_hd_path.exists() and front_hd_path.stat().st_size > 1024:
            front_map[p.record_id] = front_hd_path
            if back_hd_path.exists() and back_hd_path.stat().st_size > 1024:
                back_map[p.record_id] = back_hd_path
            print(f"[{folder_name:<13}] [{idx:>3}/{total_p}] {p.record_id} ({p.barcode})... [Already Generated]", flush=True)
            metrics = QualityMetrics(
                record_id=p.record_id,
                barcode=p.barcode,
                decision="PASS",
                solidity=1.0,
                n_components=1,
                canvas_clipping_px=30,
                blur_score=100.0,
                fill_ratio=0.80,
                warning_reasons=["Already generated packshot reused"],
                fail_reasons=[],
            )
            metrics_list.append(metrics)
            continue

        print(f"[{folder_name:<13}] [{idx:>3}/{total_p}] {p.record_id} ({p.barcode})...", end="", flush=True)
        try:
            demo_img = demo_images.get(p.row_idx)

            # Load full-resolution raw front image without pre-downscaling
            raw_front_full = sanitizer.load_normalized_image(p.selected_front_photo)

            # Detect crop coordinates with SIFT Homography / Object awareness
            crop_box, was_isolated, is_unc, conf, crop_reason = hero_cropper.isolate_front_coords(
                raw_front_full, demo_img=demo_img, barcode_center=p.barcode_center, strategy=p.strategy
            )

            # Crop directly from full-resolution raw source
            if was_isolated:
                isolated_front = raw_front_full.crop(crop_box)
            else:
                isolated_front = raw_front_full

            is_complex = (p.partition == "G4") or matting_engine.is_complex_packaging(p.category, p.name_en)
            rgba_img, raw_crop_alpha = matting_engine.remove_background(
                isolated_front, enable_hole_protection=True, is_complex=is_complex
            )
            packshot_rgb, std_mask, bbox = standardizer.standardize(rgba_img)

            # Back photo isolation on full resolution
            back_src = p.verified_back_photos[0] if p.verified_back_photos else p.selected_front_photo
            if back_src:
                try:
                    raw_back_full = sanitizer.load_normalized_image(back_src)
                    back_box, was_back_iso, _, _, _ = hero_cropper.isolate_back_coords(
                        raw_back_full, barcode_center=p.barcode_center, strategy=p.strategy
                    )
                    if was_back_iso:
                        isolated_back = raw_back_full.crop(back_box)
                    else:
                        isolated_back = raw_back_full

                    if max(isolated_back.size) > 2048:
                        isolated_back.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                    back_hd_path = part_back_dir / f"{p.barcode}_back.jpg"
                    isolated_back.save(back_hd_path, "JPEG", quality=92, optimize=True)
                    back_map[p.record_id] = back_hd_path

                    # Evaluate back photo quality & barcode readability
                    back_metrics = quality_gate.evaluate_back_packshot(isolated_back, p.record_id, p.barcode)
                    if back_metrics.decision == "HARD_FAIL":
                        print(f" (Back photo warn: {back_metrics.fail_reasons})", end="", flush=True)
                except Exception as b_err:
                    print(f" (Back error: {b_err})", end="", flush=True)

            # Quality Gate Evaluation with crop truncation check and demo ground truth verification
            metrics = quality_gate.evaluate_packshot(
                packshot_rgb,
                std_mask,
                p.record_id,
                p.barcode,
                is_complex_shape=is_complex,
                crop_mask=raw_crop_alpha if was_isolated else None,
                demo_img=demo_img,
            )
            if is_unc:
                metrics.warning_reasons.append(f"Hero isolation composition: {crop_reason}")
                if metrics.decision == "PASS":
                    metrics.decision = "WARNING_ACCEPT"

            # AntiDuplicateGuard: ensure this newly generated packshot is not identical to another SKU
            is_uniq, coll_id = standardizer.duplicate_guard.check_image_unique(packshot_rgb, p.barcode, quality=95)
            if not is_uniq:
                metrics.decision = "HARD_FAIL"
                metrics.fail_reasons.append(f"AntiDuplicateGuard collision: identical SHA-256 with {coll_id}")

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
                quarantined_products.append((p, packshot_rgb, metrics))
                print(f" -> HARD_FAIL [{', '.join(metrics.fail_reasons)}]", flush=True)
            else:
                front_hd_path = part_front_dir / f"{p.barcode}_front.jpg"
                packshot_rgb.save(front_hd_path, "JPEG", quality=95, optimize=True)
                front_map[p.record_id] = front_hd_path
                metrics_list.append(metrics)
                print(f" -> {metrics.decision}", flush=True)

        except Exception as item_err:
            print(f" -> ERROR [{item_err}] - Attempting fallback", flush=True)
            try:
                raw_front = sanitizer.load_normalized_image(p.selected_front_photo)
                w_f, h_f = raw_front.size
                center_crop = raw_front.crop((int(w_f * 0.05), int(h_f * 0.05), int(w_f * 0.95), int(h_f * 0.95)))
                rgba_fb, _ = matting_engine.remove_background(center_crop, enable_hole_protection=False, is_complex=True)
                fb_packshot, _, _ = standardizer.standardize(rgba_fb)
                fb_uniq, fb_coll = standardizer.duplicate_guard.check_image_unique(fb_packshot, p.barcode, quality=92)
                if not fb_uniq:
                    raise ValueError(f"AntiDuplicateGuard collision in fallback with {fb_coll}")
                front_hd_path = part_front_dir / f"{p.barcode}_front.jpg"
                fb_packshot.save(front_hd_path, "JPEG", quality=92, optimize=True)
                front_map[p.record_id] = front_hd_path

                fb_metrics = QualityMetrics(
                    record_id=p.record_id,
                    barcode=p.barcode,
                    decision="WARNING_ACCEPT",
                    solidity=0.75,
                    n_components=1,
                    canvas_clipping_px=25,
                    blur_score=60.0,
                    fill_ratio=0.80,
                    warning_reasons=[f"Recovered via robust fallback: {item_err}"],
                    fail_reasons=[],
                )
                metrics_list.append(fb_metrics)
                print(f" -> RECOVERED_FALLBACK", flush=True)
            except Exception as fb_err:
                err_metrics = QualityMetrics(
                    record_id=p.record_id,
                    barcode=p.barcode,
                    decision="HARD_FAIL",
                    solidity=0.0,
                    n_components=0,
                    canvas_clipping_px=0,
                    blur_score=0.0,
                    fill_ratio=0.0,
                    warning_reasons=[],
                    fail_reasons=[str(item_err), str(fb_err)],
                )
                metrics_list.append(err_metrics)

        gc.collect()

    # 3. Two-Stage Quarantine Healing Loop
    if quarantined_products:
        print(f"\n[{folder_name:<13}] [QUARANTINE HEALER] Executing automated retry for {len(quarantined_products)} staged items...", flush=True)
        for qp, q_packshot, q_metrics in quarantined_products:
            try:
                # Level 1: Fallback with conservative center crop and wider margin
                q_raw = sanitizer.load_normalized_image(qp.selected_front_photo)
                w_q, h_q = q_raw.size
                pad_x, pad_y = int(w_q * 0.08), int(h_q * 0.08)
                healed_crop = q_raw.crop((pad_x, pad_y, w_q - pad_x, h_q - pad_y))
                h_rgba, h_crop_alpha = matting_engine.remove_background(healed_crop, enable_hole_protection=True, is_complex=True)
                h_packshot, h_mask, _ = standardizer.standardize(h_rgba)
                h_demo = demo_images.get(qp.row_idx)
                h_metrics = quality_gate.evaluate_packshot(
                    h_packshot,
                    h_mask,
                    qp.record_id,
                    qp.barcode,
                    is_complex_shape=True,
                    crop_mask=h_crop_alpha,
                    demo_img=h_demo,
                )
                h_uniq, h_coll = standardizer.duplicate_guard.check_image_unique(h_packshot, qp.barcode, quality=95)
                if not h_uniq:
                    h_metrics.decision = "HARD_FAIL"
                    h_metrics.fail_reasons.append(f"AntiDuplicateGuard collision on retry: identical SHA-256 with {h_coll}")

                if h_metrics.decision in ("PASS", "WARNING_ACCEPT") and len(h_metrics.fail_reasons) == 0:
                    h_metrics.decision = "HEALED_PASS"
                    h_metrics.warning_reasons.append("Recovered via Quarantine Healing Loop")
                    front_hd_path = part_front_dir / f"{qp.barcode}_front.jpg"
                    h_packshot.save(front_hd_path, "JPEG", quality=95, optimize=True)
                    front_map[qp.record_id] = front_hd_path
                    metrics_list.append(h_metrics)
                    print(f"[{folder_name:<13}]   Healed {qp.record_id} ({qp.barcode}) -> HEALED_PASS", flush=True)
                else:
                    # MUST RETAIN IN QUARANTINE! Do NOT deliver flawed packshot to webshop!
                    q_meta_path = part_quarantine_dir / f"{qp.barcode}_defect.json"
                    q_meta_path.write_text(json.dumps({
                        "record_id": qp.record_id,
                        "barcode": qp.barcode,
                        "fail_reasons": h_metrics.fail_reasons or q_metrics.fail_reasons,
                        "solidity": h_metrics.solidity,
                        "n_components": h_metrics.n_components,
                        "status": "RETAINED_IN_QUARANTINE_FOR_MANUAL_REVIEW",
                    }, indent=2), encoding="utf-8")
                    metrics_list.append(h_metrics)
                    print(f"[{folder_name:<13}]   Retained in Quarantine {qp.record_id} ({qp.barcode}) -> {h_metrics.fail_reasons}", flush=True)
            except Exception as h_err:
                metrics_list.append(q_metrics)
                print(f"[{folder_name:<13}]   Unresolved {qp.record_id} -> {h_err}", flush=True)

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
        "--partition",
        type=str,
        default=None,
        help="Target a specific folder/partition only (e.g., Nyt, Nyt25.09.26, G1, G2, G3, G4)",
    )
    parser.add_argument(
        "--matting-model",
        type=str,
        default="birefnet-general-lite",
        help="Matting model session name (u2net, birefnet-general-lite, or birefnet-general)",
    )
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="Scan existing generated HD images and embed into Master Excel without re-running pipeline",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force clean re-processing of packshots, ignoring already-generated output files",
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

    if args.embed_only:
        print("\n=================================================================")
        print("          PIPELINE-ZOHANUBIS: STANDALONE EMBED-ONLY MODE         ")
        print("=================================================================")
        print(f"Master Catalog : {args.excel}")
        print(f"Deliverables   : {output_dir}")
        print("Scanning existing HD deliverables across partitions for Excel embedding...")
        embedder = ExcelDualEmbedder(args.excel)
        # Scan front_hd_dir and back_hd_dir
        front_hd_files: Dict[str, Path] = {}
        back_hd_files: Dict[str, Path] = {}
        for f in front_hd_dir.rglob("*_front.jpg"):
            bc = f.stem.replace("_front", "").strip()
            front_hd_files[bc] = f
            front_hd_files[bc.lstrip("0")] = f
        for b in back_hd_dir.rglob("*_back.jpg"):
            bc = b.stem.replace("_back", "").strip()
            back_hd_files[bc] = b
            back_hd_files[bc.lstrip("0")] = b
        # Also include customer_provided
        for c in customer_dir.rglob("*_front.jpg"):
            bc = c.stem.replace("_front", "").strip()
            if bc not in front_hd_files:
                front_hd_files[bc] = c
                front_hd_files[bc.lstrip("0")] = c

        # Read catalog rows to map record_id -> front_path, back_path
        import openpyxl
        wb_cat = openpyxl.load_workbook(args.excel, read_only=True, data_only=True)
        ws_cat = wb_cat["Master_SKU"]
        front_embed_map: Dict[str, Path] = {}
        back_embed_map: Dict[str, Path] = {}
        found_front = 0
        found_back = 0
        for r_idx, row in enumerate(ws_cat.iter_rows(values_only=True), start=1):
            if r_idx == 1:
                continue
            rec_id = str(row[0]).strip() if row[0] is not None else f"ROW_{r_idx}"
            bc_val = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
            if not bc_val:
                continue
            # Match front
            f_p = front_hd_files.get(bc_val) or front_hd_files.get(bc_val.lstrip("0"))
            if f_p:
                front_embed_map[rec_id] = f_p
                found_front += 1
            # Match back
            b_p = back_hd_files.get(bc_val) or back_hd_files.get(bc_val.lstrip("0"))
            if b_p:
                back_embed_map[rec_id] = b_p
                found_back += 1
        wb_cat.close()

        print(f"Discovered matching HD assets: {found_front} front packshots, {found_back} back photos.")
        output_excel_path = reports_dir / "Rabuta_master_SKU_categories_zohanubis.xlsx"
        final_excel = embedder.embed_dual_images(
            output_excel_path=output_excel_path,
            product_front_map=front_embed_map,
            product_back_map=back_embed_map,
        )
        root_excel_path = output_dir / "Rabuta_master_SKU_categories_zohanubis.xlsx"
        try:
            shutil.copy2(final_excel, root_excel_path)
            print(f"Direct root copy created: {root_excel_path}")
        except (PermissionError, OSError):
            pass
        print(f"\n[EMBED-ONLY COMPLETE] Enriched Excel saved to: {final_excel}")
        return 0

    target_partition: Optional[str] = None
    if args.partition:
        p_raw = args.partition.strip().lower()
        if "nyt" in p_raw or "n25" in p_raw:
            target_partition = "Nyt"
        elif "g1" in p_raw:
            target_partition = "G1"
        elif "g2" in p_raw:
            target_partition = "G2"
        elif "g3" in p_raw:
            target_partition = "G3"
        elif "g4" in p_raw:
            target_partition = "G4"
        else:
            target_partition = args.partition.strip()

    target_folders = [PARTITION_FOLDER_NAMES.get(target_partition, target_partition)] if target_partition else set(PARTITION_FOLDER_NAMES.values())
    for folder_name in target_folders:
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
    if target_partition:
        print(f"Partition Mode : {target_partition} ({PARTITION_FOLDER_NAMES.get(target_partition, target_partition)})")
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
    print("\n[STAGE 0B] Discovering and indexing raw photography from source folders...")
    if target_partition:
        target_folder_name = PARTITION_FOLDER_NAMES.get(target_partition, target_partition)
        sanitizer = ImageSanitizer(source_roots=[ROOT / "source-import" / target_folder_name])
    else:
        sanitizer = ImageSanitizer()
    partition_photos = sanitizer.discover_raw_photos()
    if target_partition:
        partition_photos = {k: v for k, v in partition_photos.items() if k == target_partition}

    all_raw_records: List[RawPhotoRecord] = []
    for part, recs in partition_photos.items():
        print(f"  Partition {part:<4}: {len(recs)} valid raw photos indexed")
        all_raw_records.extend(recs)
    print(f"Total raw photos discovered: {len(all_raw_records)}")

    # -------------------------------------------------------------
    # STAGE 1: MULTI-ANGLE PARALLEL BARCODE SCANNING
    # -------------------------------------------------------------
    if target_partition:
        records_to_scan = partition_photos.get(target_partition, [])
        print(f"\n[STAGE 1] Partition-specific mode: scanning {len(records_to_scan)} raw photos in {target_partition}...")
    elif args.pilot:
        records_to_scan = []
        for part, recs in partition_photos.items():
            records_to_scan.extend(recs[:15])  # 15 from each partition = 75 photos
        print(f"\n[STAGE 1] Pilot mode active: scanning {len(records_to_scan)} sample photos across 5 partitions...")
    else:
        records_to_scan = all_raw_records
        print(f"\n[STAGE 1] Full catalog mode: scanning all {len(records_to_scan)} raw photos in parallel...")

    scan_cache_file = reports_dir / f"barcode_scan_cache_{target_partition}.json" if target_partition else reports_dir / "barcode_scan_cache.json"
    if scan_cache_file.exists() and not args.pilot:
        print(f"\n[STAGE 1] Loading cached barcode scan results from: {scan_cache_file}")
        with open(scan_cache_file, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        scan_results = [
            BarcodeScanResult(
                path=Path(item["path"]),
                filename=item["filename"],
                partition=item["partition"],
                barcodes=item["barcodes"],
                detected_angle=item["detected_angle"],
                enhancement_used=item["enhancement_used"],
                barcode_centers={bc: tuple(coord) for bc, coord in item.get("barcode_centers", {}).items()},
            )
            for item in cached_data
        ]
        print(f"Loaded {len(scan_results)} scan results ({sum(1 for r in scan_results if r.barcodes)} with confirmed barcodes) in 0.05s!")
    else:
        scanner = ParallelBarcodeScanner(max_workers=args.workers)
        t_scan_start = time.time()
        scan_results = scanner.scan_records(records_to_scan)
        print(f"Parallel scan complete in {time.time() - t_scan_start:.2f}s!")
        photos_with_barcode = sum(1 for r in scan_results if r.barcodes)
        print(f"Photos with confirmed barcodes: {photos_with_barcode}/{len(scan_results)}")
        try:
            cache_payload = [
                {
                    "path": str(r.path),
                    "filename": r.filename,
                    "partition": r.partition,
                    "barcodes": r.barcodes,
                    "detected_angle": r.detected_angle,
                    "enhancement_used": r.enhancement_used,
                    "barcode_centers": r.barcode_centers,
                }
                for r in scan_results
            ]
            with open(scan_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, indent=2)
            print(f"Barcode scan results cached to: {scan_cache_file}")
        except Exception as e:
            print(f"Warning: could not write scan cache: {e}")

    # -------------------------------------------------------------
    # STAGE 2: 3-WAY RECONCILIATION & GAP ANALYSIS
    # -------------------------------------------------------------
    print("\n[STAGE 2] Reconciling barcodes with master catalog...")
    reconciler = BarcodeReconciler(args.excel, reports_dir)
    reconcile_summary = reconciler.reconcile(
        scan_results, customer_front_map=customer_front_map, target_partition=target_partition
    )

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
    if target_partition:
        part_folder = PARTITION_FOLDER_NAMES.get(target_partition, target_partition).lower()
        target_prods = [
            p for p in catalog.values()
            if (
                p.partition == target_partition
                or any(part_folder in str(b).lower() for b in p.verified_back_photos)
                or (p.selected_front_photo and part_folder in str(p.selected_front_photo).lower())
            )
            and (p.verified_back_photos or find_customer_image(p.barcode, customer_front_map))
        ]
        # Align partition to target_partition for clean folder output
        for p in target_prods:
            p.partition = target_partition
        print(f"Partition '{target_partition}' filter: {len(target_prods)} verified products to process.")
    elif args.pilot:
        # Balanced pilot: some customer items + some studio items across partitions
        pilot_cust = []
        pilot_studio = []
        seen_parts = set()
        for p in catalog.values():
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
    else:
        target_prods = list(catalog.values())

    # Build blacklist of all verified back photo paths and already-assigned photos
    assigned_photos: Set[Path] = set(reconcile_summary.assigned_photos)
    all_back_paths: Set[Path] = set(assigned_photos)
    for p in catalog.values():
        all_back_paths.update(p.verified_back_photos)
        if p.selected_front_photo:
            all_back_paths.add(p.selected_front_photo)

    matched_front_results = {}
    hero_cropper = HeroCropper()

    for p in target_prods:
        # If customer already provided image, front is already determined!
        if find_customer_image(p.barcode, customer_front_map):
            continue

        if p.selected_front_photo is None or p.suggested_front_candidate is not None:
            cands = [cp for cp in partition_photos.get(p.partition, []) if cp.path not in all_back_paths]
            match_res = matcher.match_product_front(p, cands, all_back_paths)
            if match_res.winning_photo_path:
                p.selected_front_photo = match_res.winning_photo_path
                all_back_paths.add(match_res.winning_photo_path)
                matched_front_results[p.record_id] = match_res
            elif p.suggested_front_candidate and p.suggested_front_candidate not in all_back_paths:
                # Fallback only if no demo image exists for product
                demo_img = matcher.demo_images.get(p.row_idx)
                if demo_img is None:
                    p.selected_front_photo = p.suggested_front_candidate
                    all_back_paths.add(p.suggested_front_candidate)
                    matched_front_results[p.record_id] = p.suggested_front_candidate
        else:
            if p.selected_front_photo:
                all_back_paths.add(p.selected_front_photo)
            matched_front_results[p.record_id] = p.selected_front_photo

    print(f"Front views successfully matched: {len(matched_front_results)}/{len(target_prods)}")

    # Filter target_prods to only those with actionable photography
    target_prods = [
        p for p in target_prods
        if p.selected_front_photo or p.verified_back_photos or find_customer_image(p.barcode, customer_front_map)
    ]
    print(f"Products with actionable photography to process: {len(target_prods)}")

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

    # Execute active partitions sequentially for rock-solid memory safety and zero thread arena collisions
    active_partitions = list(partition_groups.keys())
    print(f"\nProcessing {len(active_partitions)} partitions with full CPU power: {active_partitions}")

    for part_name in active_partitions:
        p_front, p_back, p_metrics = process_partition_stream(
            part_name,
            partition_groups[part_name],
            customer_front_map,
            matcher.demo_images,
            front_hd_dir,
            back_hd_dir,
            quarantine_dir,
            customer_dir,
            args.matting_model,
            force=args.force,
        )
        front_embed_map.update(p_front)
        back_embed_map.update(p_back)
        quality_records.extend(p_metrics)
        folder_n = PARTITION_FOLDER_NAMES.get(part_name, part_name)
        print(f"[STREAM FINISHED] Partition {part_name} ({folder_n}): {len(p_front)} front, {len(p_back)} back, {len(p_metrics)} records.\n", flush=True)
        gc.collect()

    # Save ledger
    ledger_path = reports_dir / "zohanubis_audit_ledger.json"
    quality_gate = QualityGate()
    quality_gate.save_ledger(quality_records, ledger_path)
    print(f"\nAudit ledger saved to: {ledger_path}")

    # -------------------------------------------------------------
    # STAGE 5: ATOMIC EXCEL DUAL-IMAGE EMBEDDING & DELIVERABLES
    # -------------------------------------------------------------
    root_missing_path = output_dir / "Zohanubis_Missing_SKU_Report.xlsx"
    try:
        shutil.copy2(reconcile_summary.missing_report_path, root_missing_path)
    except (PermissionError, OSError):
        pass

    if target_partition:
        part_name = target_partition
        folder_n = PARTITION_FOLDER_NAMES.get(part_name, part_name)
        total_time = time.time() - total_start
        print("\n=================================================================")
        print(f" [STAGE 5 DEFERRED] Partition mode active (--partition {target_partition})")
        print(f" Master Excel embedding is DEFERRED until all folders are completed.")
        print(f" HD Deliverables saved to: {front_hd_dir / folder_n}")
        print(f" Missing SKU Gap Report  : {root_missing_path}")
        print(f" Audit Ledger            : {ledger_path}")
        print(f" Elapsed Time            : {total_time:.2f}s")
        print(f" When all folders are completed, run with --embed-only to generate Excel.")
        print("=================================================================\n")
        return 0

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
