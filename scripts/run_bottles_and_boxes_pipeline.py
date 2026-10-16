#!/usr/bin/env python3
"""Dedicated Pipeline for Rigid Containers (Bottles, Jars, Cans, Upright Boxes).

Identifies, isolates, and standardizes single front hero packshots for container items
across partitions (G1_original, G2_original, G3_Original, G4-original).
Saves deliverables into a dedicated folder mirroring source partitions:
    output/shopify-zohanubis-image/webshop_bottles_boxes/<partition_name>/[barcode]-front.jpg
Preserves webshop_front_hd completely untouched.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
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

from product_mapper.zohanubis.sanitizer import ImageSanitizer
from product_mapper.zohanubis.matting_engine import MattingEngine
from product_mapper.zohanubis.studio_standardizer import StudioStandardizer
from product_mapper.zohanubis.quality_gate import QualityGate, QualityMetrics
from product_mapper.zohanubis.container_detector import RigidContainerDetector
from product_mapper.zohanubis.valley_separator import MultiColumnValleySeparator
from product_mapper.zohanubis.front_hero_selector import FrontHeroSelector
from scripts.run_g3_all_462 import load_g3_barcode_maps, clean_alpha_mask


def load_partition_barcode_maps(
    partition: str, reports_dir: Path
) -> Tuple[Dict[str, List[str]], Dict[str, Dict[str, Tuple[float, float]]], Dict[str, str]]:
    """Loads barcode maps for a specific partition."""
    # Check scan cache
    clean_p = partition.replace("-original", "").replace("_original", "").replace("_Original", "")
    cache_candidates = [
        reports_dir / f"barcode_scan_cache_{clean_p}.json",
        reports_dir / f"barcode_scan_cache_{partition}.json",
    ]
    scan_cache_path = None
    for c in cache_candidates:
        if c.exists():
            scan_cache_path = c
            break

    manifest_candidates = [
        ROOT / f"output/catalog_pairs/manifest_{partition}_v2.json",
        ROOT / f"output/catalog_pairs/manifest_{partition}.json",
    ]
    manifest_path = None
    for m in manifest_candidates:
        if m.exists():
            manifest_path = m
            break

    return load_g3_barcode_maps(
        scan_cache_path or Path("non_existent"),
        manifest_path or Path("non_existent"),
    )


def process_container_item(
    raw_path: Path,
    target_path: Path,
    record_id: str,
    barcode: str,
    name_en: str,
    sanitizer: ImageSanitizer,
    matting_engine: MattingEngine,
    separator: MultiColumnValleySeparator,
    selector: FrontHeroSelector,
    standardizer: StudioStandardizer,
    quality_gate: QualityGate,
    barcode_centers: Optional[List[Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """Processes a single raw container photo into a single front hero packshot."""
    raw_img = sanitizer.load_normalized_image(raw_path)
    w, h = raw_img.size

    # 1. Multi-column separation using thumbnail matting mask
    boxes = separator.separate_columns(raw_img, matting_engine=matting_engine)

    # 2. Select the front hero column
    best_box, best_idx, scores = selector.select_front_hero(
        raw_img, boxes, barcode_centers=barcode_centers
    )

    # 3. Crop candidate
    hero_crop = raw_img.crop(best_box)
    if max(hero_crop.size) > 2048:
        hero_crop.thumbnail((2048, 2048), Image.Resampling.BILINEAR)

    # 4. Neural background matting
    rgba_img, alpha_mask = matting_engine.remove_background(
        hero_crop, enable_hole_protection=True, allow_escalation=False
    )

    # 5. Connected component filtering
    cleaned_alpha = clean_alpha_mask(alpha_mask)
    r, g, b, _ = rgba_img.split()
    cleaned_rgba = Image.merge("RGBA", (r, g, b, Image.fromarray(cleaned_alpha, mode="L")))

    # 6. Container-specific studio standardization
    packshot_rgb, std_mask, bbox = standardizer.standardize(cleaned_rgba, is_container=True)

    # 7. QualityGate evaluation
    metrics = quality_gate.evaluate_packshot(
        packshot_rgb, std_mask, record_id, barcode, is_container=True
    )

    # 8. Save deliverable into dedicated mirrored folder
    target_path.parent.mkdir(parents=True, exist_ok=True)
    packshot_rgb.save(target_path, "JPEG", quality=95, optimize=True)

    return {
        "raw_file": raw_path.name,
        "record_id": record_id,
        "barcode": barcode,
        "name_en": name_en,
        "n_columns_detected": len(boxes),
        "selected_column_idx": best_idx,
        "selected_box": best_box,
        "scores": scores,
        "decision": metrics.decision,
        "solidity": metrics.solidity,
        "bbox": bbox,
        "output_path": str(target_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Bottles & Boxes Dedicated Pipeline")
    parser.add_argument("--partition", type=str, default="G3_Original", help="Partition name (e.g. G3_Original, G2_original, G1_original)")
    parser.add_argument("--targets", type=str, default=None, help="Comma-separated stems or barcodes to process (e.g. IMG_1261,IMG_1268)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items")
    args = parser.parse_args()

    output_root = ROOT / "output/shopify-zohanubis-image"
    bottles_boxes_root = output_root / "webshop_bottles_boxes"
    reports_dir = output_root / "reports"
    excel_path = ROOT / "source-import/Rabuta_master_SKU_categories.xlsx"

    target_partition_dir = ROOT / f"source-import/{args.partition}"
    if not target_partition_dir.exists():
        print(f"Error: {target_partition_dir} does not exist!")
        return 1

    partition_dest_dir = bottles_boxes_root / args.partition
    partition_dest_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("      DEDICATED RIGID CONTAINERS PIPELINE (BOTTLES & BOXES)      ")
    print("=" * 70)
    print(f"Target Partition : {args.partition}")
    print(f"Deliverable Dest : {partition_dest_dir}")
    print(f"Catalog Index    : {excel_path}")

    # Index catalog with container flags
    catalog = RigidContainerDetector.index_catalog(excel_path)
    file_to_barcodes, file_to_centers, file_to_mode = load_partition_barcode_maps(args.partition, reports_dir)

    all_raw_files = sorted(list(target_partition_dir.glob("*")), key=lambda p: p.name)
    supported_exts = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
    all_raw_files = [f for f in all_raw_files if f.suffix.lower() in supported_exts]

    target_stems = set(args.targets.split(",")) if args.targets else None

    # Filter items to containers or specified targets
    queue: List[Tuple[Path, str, str, str, Optional[List[Tuple[float, float]]]]] = []
    for rf in all_raw_files:
        stem = rf.stem
        if target_stems and stem not in target_stems:
            continue

        barcodes = file_to_barcodes.get(rf.name, []) or file_to_barcodes.get(stem, [])
        primary_bc = barcodes[0] if barcodes else ""
        cat_info = catalog.get(primary_bc) if primary_bc else None

        # Check if container or explicit target
        is_container = cat_info["is_container"] if cat_info else False
        if not is_container and target_stems and stem in target_stems:
            is_container = True  # force process requested targets

        if is_container or (target_stems and stem in target_stems):
            record_id = cat_info["record_id"] if cat_info else f"{args.partition}-{stem}"
            name_en = cat_info["name_en"] if cat_info else ""
            centers_map = file_to_centers.get(rf.name, file_to_centers.get(stem, {}))
            bc_centers = list(centers_map.values()) if centers_map else None
            queue.append((rf, primary_bc, record_id, name_en, bc_centers))

    if args.limit:
        queue = queue[:args.limit]

    print(f"Found {len(queue)} container candidate items to process in {args.partition}.\n")
    if not queue:
        print("No items in queue.")
        return 0

    sanitizer = ImageSanitizer()
    matting_engine = MattingEngine("u2net")
    separator = MultiColumnValleySeparator()
    selector = FrontHeroSelector()
    standardizer = StudioStandardizer(canvas_size=2048)
    quality_gate = QualityGate()

    results: List[Dict[str, Any]] = []
    used_names: Set[str] = set()

    for idx, (raw_path, barcode, record_id, name_en, bc_centers) in enumerate(queue, start=1):
        stem = raw_path.stem
        if barcode:
            cand = f"{barcode}-front.jpg"
            if cand in used_names:
                target_filename = f"{barcode}_{stem}-front.jpg"
            else:
                target_filename = cand
        else:
            target_filename = f"{stem}-front.jpg"
        used_names.add(target_filename)

        target_save_path = partition_dest_dir / target_filename
        disp_id = f"{barcode} ({stem})" if barcode else stem
        print(f"[{idx:>3}/{len(queue)}] Processing {disp_id:<28} ... ", end="", flush=True)

        try:
            res = process_container_item(
                raw_path=raw_path,
                target_path=target_save_path,
                record_id=record_id,
                barcode=barcode or stem,
                name_en=name_en,
                sanitizer=sanitizer,
                matting_engine=matting_engine,
                separator=separator,
                selector=selector,
                standardizer=standardizer,
                quality_gate=quality_gate,
                barcode_centers=bc_centers,
            )
            results.append(res)
            print(f"DONE -> {target_filename} [cols={res['n_columns_detected']}, picked={res['selected_column_idx']}, {res['decision']}]", flush=True)
        except Exception as e:
            print(f"FAILED [{e}]", flush=True)

        gc.collect()

    # Save execution manifest
    manifest_out = reports_dir / f"bottles_boxes_manifest_{args.partition}.json"
    with open(manifest_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nExecution summary saved to: {manifest_out}")
    print(f"All container packshots stored in: {partition_dest_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
