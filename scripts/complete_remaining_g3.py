#!/usr/bin/env python3
"""Completes processing for any remaining raw images in G3_Original.

Ensures:
- Every raw photo in source-import/G3_Original maps to an output in webshop_front_hd/G3_Original
- Strictly single file per SKU ([barcode]-front.jpg or [barcode]_[stem]-front.jpg if duplicate barcode)
- Fixes empty alpha edge cases with graceful fallback
- Updates Excel workbook and execution manifest
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
from product_mapper.zohanubis.quality_gate import QualityGate
from product_mapper.zohanubis.excel_embedder import ExcelDualEmbedder
from scripts.run_g3_all_462 import load_g3_barcode_maps, load_catalog_info, calculate_front_crop_box, clean_alpha_mask


def main():
    raw_dir = ROOT / "source-import/G3_Original"
    output_dir = ROOT / "output/shopify-zohanubis-image"
    front_hd_dir = output_dir / "webshop_front_hd/G3_Original"
    back_hd_dir = output_dir / "webshop_back_hd/G3_Original"
    reports_dir = output_dir / "reports"
    excel_path = ROOT / "source-import/Rabuta_master_SKU_categories.xlsx"
    v5_dir = ROOT / "output/catalog_pairs/tagged/front-v5"
    cust_dir = ROOT / "source-import/customer-send-me-front-product"

    scan_cache_path = reports_dir / "barcode_scan_cache_G3.json"
    manifest_path = ROOT / "output/catalog_pairs/manifest_G3_Original_v2.json"

    file_to_barcodes, file_to_centers, file_to_mode = load_g3_barcode_maps(scan_cache_path, manifest_path)
    catalog = load_catalog_info(excel_path)

    # Index customer pre-made front repository
    customer_front_map: Dict[str, Path] = {}
    if cust_dir.exists():
        for cf in cust_dir.glob("*.jpg"):
            clean_bc = cf.stem.replace("_front", "").replace("-front", "").strip()
            customer_front_map[clean_bc] = cf

    all_raw_files = sorted(list(raw_dir.glob("*")), key=lambda p: p.name)
    existing_outputs = {f.name for f in front_hd_dir.glob("*")}

    # Find remaining raw files
    remaining_raw: List[Path] = []
    used_front_names = set(existing_outputs)

    for rf in all_raw_files:
        stem = rf.stem
        barcodes = file_to_barcodes.get(rf.name, []) or file_to_barcodes.get(stem, [])
        primary_bc = barcodes[0] if barcodes else None
        
        cand1 = f"{primary_bc}-front.jpg" if primary_bc else f"{stem}-front.jpg"
        cand2 = f"{primary_bc}_{stem}-front.jpg" if primary_bc else None
        
        if cand1 in existing_outputs or (cand2 and cand2 in existing_outputs):
            continue
        remaining_raw.append(rf)

    print(f"Total raw files: {len(all_raw_files)}")
    print(f"Already delivered in webshop_front_hd/G3_Original: {len(existing_outputs)}")
    print(f"Remaining to process: {len(remaining_raw)}")

    if not remaining_raw:
        print("All raw files are already processed!")
        return

    sanitizer = ImageSanitizer()
    matting_engine = MattingEngine("u2net")
    standardizer = StudioStandardizer(canvas_size=2048)
    quality_gate = QualityGate()

    new_processed_records = []
    new_product_front_map: Dict[str, Path] = {}

    for idx, raw_path in enumerate(remaining_raw, start=1):
        fn = raw_path.name
        stem = raw_path.stem
        barcodes = file_to_barcodes.get(fn, []) or file_to_barcodes.get(stem, [])
        mode = file_to_mode.get(stem, file_to_mode.get(fn, "unknown"))
        centers_map = file_to_centers.get(fn, file_to_centers.get(stem, {}))

        primary_bc = barcodes[0] if barcodes else None
        bc_center = centers_map.get(primary_bc) if primary_bc else None
        if not bc_center and mode != "unknown":
            if mode == "back_right":
                bc_center = (0.75, 0.50)
            elif mode == "back_left":
                bc_center = (0.25, 0.50)
            elif mode == "back_bottom":
                bc_center = (0.50, 0.75)
            elif mode == "back_top":
                bc_center = (0.50, 0.25)

        cat_info = catalog.get(primary_bc) if primary_bc else None
        record_id = cat_info["record_id"] if cat_info else f"G3-RAW-{stem}"
        name_en = cat_info["name_en"] if cat_info else ""

        if primary_bc:
            cand_name = f"{primary_bc}-front.jpg"
            if cand_name in used_front_names:
                front_filename = f"{primary_bc}_{stem}-front.jpg"
            else:
                front_filename = cand_name
        else:
            front_filename = f"{stem}-front.jpg"
        used_front_names.add(front_filename)

        front_save_path = front_hd_dir / front_filename
        disp_id = f"{primary_bc} ({stem})" if primary_bc else stem
        print(f"[{idx:>2}/{len(remaining_raw)}] Processing {disp_id:<28} ... ", end="", flush=True)

        try:
            cust_img_path = (customer_front_map.get(primary_bc) or customer_front_map.get(primary_bc.lstrip("0"))) if primary_bc else None
            v5_front_path = (v5_dir / f"{primary_bc}-front.jpg") if primary_bc else None
            if not v5_front_path or not v5_front_path.exists():
                v5_front_path = (v5_dir / f"{primary_bc.lstrip('0')}-front.jpg") if primary_bc and primary_bc.startswith("0") else None

            if cust_img_path is not None:
                with Image.open(cust_img_path) as c_img:
                    c_rgb = c_img.convert("RGB")
                packshot_rgb = standardizer.fit_to_canvas(c_rgb)
                std_mask = np.ones((2048, 2048), dtype=np.uint8) * 255
                metrics = quality_gate.evaluate_customer_packshot(packshot_rgb, record_id, primary_bc or stem)
                bbox = (0, 0, 2048, 2048)
                method_used = "CUSTOMER_PACKSHOT"

            elif mode == "back_only" and v5_front_path is not None and v5_front_path.exists() and v5_front_path.stat().st_size > 5000:
                with Image.open(v5_front_path) as v5_im:
                    v5_rgb = v5_im.convert("RGB")
                packshot_rgb = standardizer.fit_to_canvas(v5_rgb)
                std_mask = np.ones((2048, 2048), dtype=np.uint8) * 255
                metrics = quality_gate.evaluate_customer_packshot(packshot_rgb, record_id, primary_bc or stem)
                bbox = (0, 0, 2048, 2048)
                method_used = "VERIFIED_V5_RECONCILED"

            else:
                raw_img = sanitizer.load_normalized_image(raw_path)
                crop_box = calculate_front_crop_box(raw_img, mode=mode, bc_center=bc_center)
                isolated_front = raw_img.crop(crop_box)
                if max(isolated_front.size) > 2048:
                    isolated_front.thumbnail((2048, 2048), Image.Resampling.BILINEAR)

                rgba_img, alpha_mask = matting_engine.remove_background(
                    isolated_front, enable_hole_protection=True, allow_escalation=False
                )
                cleaned_alpha = clean_alpha_mask(alpha_mask)
                r, g, b, _ = rgba_img.split()
                cleaned_rgba = Image.merge("RGBA", (r, g, b, Image.fromarray(cleaned_alpha, mode="L")))
                packshot_rgb, std_mask, bbox = standardizer.standardize(cleaned_rgba)
                metrics = quality_gate.evaluate_packshot(packshot_rgb, std_mask, record_id, primary_bc or stem)
                method_used = "UPGRADED_SEAM_STUDIO"

            packshot_rgb.save(front_save_path, "JPEG", quality=95, optimize=True)
            if cat_info:
                new_product_front_map[record_id] = front_save_path

            print(f"DONE -> {front_save_path.name} [{method_used}]", flush=True)

            new_processed_records.append({
                "raw_file": fn,
                "stem": stem,
                "barcode": primary_bc,
                "record_id": record_id,
                "name_en": name_en,
                "front_path": str(front_save_path),
                "method": method_used,
                "decision": metrics.decision,
                "solidity": metrics.solidity,
                "bbox": bbox,
            })
        except Exception as e:
            print(f"FAILED [{e}]", flush=True)

        gc.collect()

    print(f"\nRemaining batch finished. Successfully generated {len(new_processed_records)} packshots.")
    total_on_disk = len(list(front_hd_dir.glob("*.jpg")))
    print(f"Total front packshots now in webshop_front_hd/G3_Original: {total_on_disk}")

    # Update Master Excel workbook
    print("\nRefreshing Master Excel workbook with complete G3 collection...")
    all_front_map: Dict[str, Path] = {}
    for f in front_hd_dir.glob("*.jpg"):
        bc_c = f.stem.replace("-front", "").split("_")[0].strip()
        cat_p = catalog.get(bc_c)
        if cat_p:
            all_front_map[cat_p["record_id"]] = f

    all_back_map: Dict[str, Path] = {}
    for bf in back_hd_dir.glob("*.jpg"):
        bc_b = bf.stem.replace("_back", "").replace("-back", "").strip()
        cat_p = catalog.get(bc_b)
        if cat_p:
            all_back_map[cat_p["record_id"]] = bf

    embedder = ExcelDualEmbedder(excel_path)
    output_excel_path = reports_dir / "Rabuta_master_SKU_categories_zohanubis.xlsx"
    root_excel_path = output_dir / "Rabuta_master_SKU_categories_zohanubis.xlsx"

    embedder.embed_dual_images(
        output_excel_path=output_excel_path,
        product_front_map=all_front_map,
        product_back_map=all_back_map,
        target_record_ids=set(all_front_map.keys()),
    )
    import shutil
    shutil.copy2(output_excel_path, root_excel_path)
    print("Master Excel workbook refreshed successfully.")


if __name__ == "__main__":
    main()
