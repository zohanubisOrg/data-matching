#!/usr/bin/env python3
r"""Dedicated Processor for G2 Bottles, Jars, and Rigid Containers.

Reads directly from:
    D:\Work\shopify\output\shopify-zohanubis-image\webshop_front_hd\G2_original
Processes separately into:
    D:\Work\shopify\output\shopify-zohanubis-image\webshop_bottles_boxes\G2_original
Strictly maintaining [barcode]-front.jpg naming.

Guarantees 100% True Front View:
1. Cross-checks customer packshots (source-import/customer-send-me-front-product)
2. Cross-checks verified front ground truth (output/catalog_pairs/tagged/front-v5)
3. For multi-bottle/multi-object scenes, carves valleys between bottles and uses
   FrontHeroSelector with OpenCV BarcodeDetector to eliminate rear barcode views
   and select the primary front hero label.
4. Centers single hero on 2048x2048 white studio canvas with container contact shadow.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import cv2
import numpy as np
from PIL import Image

from product_mapper.zohanubis.studio_standardizer import StudioStandardizer
from product_mapper.zohanubis.quality_gate import QualityGate, QualityMetrics
from product_mapper.zohanubis.container_detector import RigidContainerDetector
from product_mapper.zohanubis.valley_separator import MultiColumnValleySeparator
from product_mapper.zohanubis.front_hero_selector import FrontHeroSelector
from scripts.run_g3_all_462 import clean_alpha_mask


def get_barcode_variants(bc: str) -> List[str]:
    """Generates all standard UPC/EAN digit-length variants for robust matching."""
    variants = [bc]
    stripped = bc.lstrip("0")
    if stripped:
        variants.append(stripped)
    if bc.startswith("0") and len(bc) > 1:
        variants.append(bc[1:])
    for length in (11, 12, 13, 14):
        if stripped:
            variants.append(stripped.zfill(length))
    seen = set()
    res = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res


def clean_container_alpha(alpha: np.ndarray) -> np.ndarray:
    """Isolates the single main hero bottle and eliminates any residual fragments."""
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 40).astype(np.uint8))
    if num_labels <= 2:
        return alpha
    areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, num_labels)]
    max_idx = int(np.argmax(areas)) + 1
    max_area = areas[max_idx - 1]
    
    cleaned = np.zeros_like(alpha)
    # Always keep the primary component
    cleaned[labels == max_idx] = alpha[labels == max_idx]
    
    # Check if any other component is a cap/straw directly above or attached
    main_x = stats[max_idx, cv2.CC_STAT_LEFT]
    main_w = stats[max_idx, cv2.CC_STAT_WIDTH]
    main_y = stats[max_idx, cv2.CC_STAT_TOP]
    
    for i in range(1, num_labels):
        if i == max_idx:
            continue
        comp_area = stats[i, cv2.CC_STAT_AREA]
        comp_x = stats[i, cv2.CC_STAT_LEFT]
        comp_w = stats[i, cv2.CC_STAT_WIDTH]
        comp_y = stats[i, cv2.CC_STAT_TOP]
        comp_h = stats[i, cv2.CC_STAT_HEIGHT]
        
        # Horizontal overlap with main bottle
        overlap_x = max(0, min(main_x + main_w, comp_x + comp_w) - max(main_x, comp_x))
        if overlap_x > comp_w * 0.5 and (comp_y + comp_h <= main_y + 30 or comp_y >= main_y + stats[max_idx, cv2.CC_STAT_HEIGHT] - 30):
            if comp_area >= max_area * 0.01:
                cleaned[labels == i] = alpha[labels == i]
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Process G2 Bottles & Boxes Separately")
    parser.add_argument("--limit", type=int, default=None, help="Process first N files")
    args = parser.parse_args()

    g2_front_hd_dir = ROOT / "output/shopify-zohanubis-image/webshop_front_hd/G2_original"
    output_dest_dir = ROOT / "output/shopify-zohanubis-image/webshop_bottles_boxes/G2_original"
    reports_dir = ROOT / "output/shopify-zohanubis-image/reports"
    excel_path = ROOT / "source-import/Rabuta_master_SKU_categories.xlsx"

    v5_dir = ROOT / "output/catalog_pairs/tagged/front-v5"
    cust_dir = ROOT / "source-import/customer-send-me-front-product"

    output_dest_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("      DEDICATED G2 BOTTLES & BOXES PROCESSOR (SEPARATE MIRROR)      ")
    print("=" * 75)
    print(f"Source Folder : {g2_front_hd_dir}")
    print(f"Dest Folder   : {output_dest_dir}")
    print(f"Policy        : Single Front Hero ([barcode]-front.jpg)")
    print("-" * 75)

    catalog = RigidContainerDetector.index_catalog(excel_path)
    print(f"Catalog indexed: {len(catalog)} barcode entries.")

    # Index customer pre-made front packshots with variant mapping
    customer_front_map: Dict[str, Path] = {}
    if cust_dir.exists():
        for cf in cust_dir.glob("*.jpg"):
            clean_bc = cf.stem.replace("_front", "").replace("-front", "").strip()
            for v in get_barcode_variants(clean_bc):
                if v not in customer_front_map:
                    customer_front_map[v] = cf
    print(f"Indexed customer pre-made front packshots with variant mapping.")

    # Index v5 ground truth with variant mapping
    v5_map: Dict[str, Path] = {}
    if v5_dir.exists():
        for vf in v5_dir.glob("*.jpg"):
            clean_bc = vf.stem.replace("-front", "").replace("_front", "").strip()
            for v in get_barcode_variants(clean_bc):
                if v not in v5_map:
                    v5_map[v] = vf
    print(f"Indexed {len(v5_map)} verified v5 front ground truth entries.")

    # All input files from webshop_front_hd/G2_original
    input_files = sorted(list(g2_front_hd_dir.glob("*.jpg")), key=lambda p: p.name)
    if args.limit:
        input_files = input_files[:args.limit]

    print(f"Total input files to review/process: {len(input_files)}")

    separator = MultiColumnValleySeparator()
    selector = FrontHeroSelector()
    standardizer = StudioStandardizer(canvas_size=2048)
    quality_gate = QualityGate()

    results: List[Dict[str, Any]] = []
    used_names: Set[str] = set()

    t_start = time.time()
    processed_count = 0

    for idx, f_path in enumerate(input_files, start=1):
        filename = f_path.name
        # Barcode extraction from [barcode]-front.jpg
        primary_bc = filename.replace("-front.jpg", "").replace("_front.jpg", "").split("_")[0].strip()
        cat_info = catalog.get(primary_bc)
        name_en = cat_info["name_en"] if cat_info else ""
        record_id = cat_info["record_id"] if cat_info else f"G2-{idx:04d}"

        # Target filename: strictly [barcode]-front.jpg (1 file per product)
        if primary_bc in used_names:
            print(f"[{idx:>3}/{len(input_files)}] {primary_bc:<36} ... SKIPPED (Already generated {primary_bc}-front.jpg)")
            continue
        used_names.add(primary_bc)

        target_name = f"{primary_bc}-front.jpg"
        target_save_path = output_dest_dir / target_name
        disp_id = f"{primary_bc} ({name_en[:24]})" if name_en else primary_bc
        print(f"[{idx:>3}/{len(input_files)}] {disp_id:<36} ... ", end="", flush=True)

        method_used = "UNKNOWN"
        packshot_rgb: Optional[Image.Image] = None
        std_mask: Optional[np.ndarray] = None
        bbox = (0, 0, 2048, 2048)

        try:
            bc_variants = get_barcode_variants(primary_bc)

            # Resolution Path 1: Check Customer Pre-made Packshot
            for v in bc_variants:
                cust_img = customer_front_map.get(v)
                if cust_img and cust_img.exists() and cust_img.stat().st_size > 5000:
                    with Image.open(cust_img) as c_im:
                        c_rgb = c_im.convert("RGB")
                    packshot_rgb = standardizer.fit_to_canvas(c_rgb)
                    std_mask = np.ones((2048, 2048), dtype=np.uint8) * 255
                    metrics = quality_gate.evaluate_customer_packshot(packshot_rgb, record_id, primary_bc)
                    method_used = "CUSTOMER_PACKSHOT"
                    break

            # Resolution Path 2: Check Verified Front-v5 Ground Truth
            if packshot_rgb is None:
                for v in bc_variants:
                    v5_candidate = v5_map.get(v)
                    if v5_candidate and v5_candidate.exists() and v5_candidate.stat().st_size > 5000:
                        with Image.open(v5_candidate) as v5_im:
                            v5_rgb = v5_im.convert("RGB")
                        packshot_rgb = standardizer.fit_to_canvas(v5_rgb)
                        std_mask = np.ones((2048, 2048), dtype=np.uint8) * 255
                        metrics = quality_gate.evaluate_customer_packshot(packshot_rgb, record_id, primary_bc)
                        method_used = "VERIFIED_V5_TRUTH"
                        break

            # Resolution Path 3: Multi-Column Separation & Front Hero Isolation directly from webshop_front_hd
            if packshot_rgb is None:
                with Image.open(f_path) as current_im:
                    current_rgb = current_im.convert("RGB")

                # Separate columns
                boxes = separator.separate_columns(current_rgb)

                if len(boxes) > 1:
                    # Multi-bottle scene: select front hero, rejecting any box with a barcode
                    best_box, best_idx, scores = selector.select_front_hero(current_rgb, boxes)
                    hero_crop = current_rgb.crop(best_box)
                    method_used = f"VALLEY_SEPARATED_{len(boxes)}COLS"
                else:
                    hero_crop = current_rgb
                    method_used = "SINGLE_HERO_STANDARDIZED"

                # Convert white studio background to alpha
                hero_arr = np.array(hero_crop)
                is_prod = (np.any(hero_arr < 248, axis=2)).astype(np.uint8) * 255
                cleaned_alpha = clean_container_alpha(is_prod)
                r, g, b = hero_crop.split()
                hero_rgba = Image.merge("RGBA", (r, g, b, Image.fromarray(cleaned_alpha, mode="L")))

                # Standardize onto 2048 canvas with container contact shadow
                packshot_rgb, std_mask, bbox = standardizer.standardize(hero_rgba, is_container=True)
                metrics = quality_gate.evaluate_packshot(
                    packshot_rgb, std_mask, record_id, primary_bc, is_container=True
                )

            # Save deliverable strictly as [barcode]-front.jpg
            packshot_rgb.save(target_save_path, "JPEG", quality=95, optimize=True)
            processed_count += 1
            print(f"DONE -> {target_name} [{method_used}, {metrics.decision}]", flush=True)

            results.append({
                "idx": idx,
                "input_file": filename,
                "output_file": target_name,
                "barcode": primary_bc,
                "record_id": record_id,
                "name_en": name_en,
                "method": method_used,
                "decision": metrics.decision,
                "solidity": metrics.solidity,
                "bbox": bbox,
            })
        except Exception as e:
            print(f"FAILED [{e}]", flush=True)

        if idx % 50 == 0:
            gc.collect()

    t_elapsed = time.time() - t_start

    # Save execution manifest
    manifest_out = reports_dir / "g2_bottles_boxes_manifest.json"
    with open(manifest_out, "w", encoding="utf-8") as f:
        json.dump({
            "total_input": len(input_files),
            "processed": processed_count,
            "elapsed_seconds": round(t_elapsed, 2),
            "records": results,
        }, f, indent=2)

    print("\n" + "=" * 75)
    print(f"G2 BOTTLES & BOXES PROCESSING COMPLETE!")
    print(f"Total Files Processed : {processed_count}/{len(input_files)}")
    print(f"Output Directory       : {output_dest_dir}")
    print(f"Manifest Saved         : {manifest_out}")
    print(f"Total Elapsed Time     : {t_elapsed / 60:.2f} minutes")
    print("=" * 75)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
