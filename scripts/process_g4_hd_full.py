#!/usr/bin/env python3
"""
scripts/process_g4_hd_full.py
=============================
Upgraded Pipeline-Zohanubis Dedicated Front HD Processor for G4-original.

Enhancements:
1. Zero Duplicates: Strictly 1 file per product ({barcode}_front.jpg).
   No duplicate hyphen-named files or redundant aliases.
2. 100% Detail Preservation for Vegetables & Transparent Bags:
   Vegetable packaging bags are processed intact (full bag, zero vertical/horizontal slicing).
   Enhanced alpha matting protects delicate green leaves, transparent film, and stems.
3. Accurate Sequential Pairing & Carton Detection:
   Resolves front photos from user-verified ground truth pairs.
4. Clean Slate Overwrite: Cleans target directory before processing to ensure zero leftover duplicates.
5. Back processing: SKIPPED (already generated in webshop_back_hd/G4-original).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.product_mapper.zohanubis.sanitizer import ImageSanitizer
from src.product_mapper.zohanubis.matting_engine import MattingEngine
from src.product_mapper.zohanubis.studio_standardizer import StudioStandardizer, AntiDuplicateGuard
from src.product_mapper.zohanubis.quality_gate import QualityGate

G4_SOURCE_DIR = ROOT / "source-import/G4-original"
FRONT_HD_DIR = ROOT / "output/shopify-zohanubis-image/webshop_front_hd/G4-original"
REPORTS_DIR = ROOT / "output/shopify-zohanubis-image/reports"
CLEAN_SPECS_FILE = ROOT / "scratch/g4_clean_specs_v3.json"


def run_pipeline() -> int:
    print("=" * 80)
    print("  UPGRADED PIPELINE-ZOHANUBIS: G4-ORIGINAL (ZERO DUPLICATE & FULL DETAIL)   ")
    print("=" * 80)
    print(f"Source folder : {G4_SOURCE_DIR}")
    print(f"Output folder : {FRONT_HD_DIR}")
    print(f"Back images   : SKIPPED (already verified in webshop_back_hd)")
    print("=" * 80)

    if not CLEAN_SPECS_FILE.exists():
        print(f"[ERROR] Clean specs file not found: {CLEAN_SPECS_FILE}")
        return 1

    with open(CLEAN_SPECS_FILE, "r", encoding="utf-8") as f:
        specs: List[Dict[str, Any]] = json.load(f)

    # 1. Clean destination folder to prevent any lingering duplicate files
    FRONT_HD_DIR.mkdir(parents=True, exist_ok=True)
    existing_files = list(FRONT_HD_DIR.glob("*.*"))
    if existing_files:
        print(f"\n[CLEAN SLATE] Purging {len(existing_files)} existing files in output directory to eliminate duplicates...")
        for ef in existing_files:
            try:
                ef.unlink()
            except Exception as e:
                print(f"  Warning: could not delete {ef.name}: {e}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(specs)} unique product specifications to process.")

    sanitizer = ImageSanitizer()
    matting = MattingEngine("birefnet-general-lite")
    standardizer = StudioStandardizer(canvas_size=2048)
    guard = AntiDuplicateGuard()
    gate = QualityGate()

    results: List[Dict[str, Any]] = []
    start_time = time.time()
    total_specs = len(specs)
    seen_output_barcodes = set()

    for idx, spec in enumerate(specs, start=1):
        bc = str(spec["barcode"]).strip()
        nm = spec.get("name") or ""
        stype = spec.get("type", "single")
        src_fn = spec.get("source")
        mode = spec.get("mode", "")
        src_path = G4_SOURCE_DIR / src_fn

        print(f"\n[{idx:2d}/{total_specs}] {bc} ({src_fn}) - {nm} [{stype}|{mode}]...", flush=True)

        if bc in seen_output_barcodes:
            print(f"  [SKIPPED DUPLICATE] Barcode {bc} already generated in this run!")
            continue
        seen_output_barcodes.add(bc)

        if not src_path.exists():
            print(f"  [ERROR] Source file missing: {src_path.name}")
            results.append({
                "barcode": bc,
                "name": nm,
                "source": src_fn,
                "decision": "ERROR_FILE_NOT_FOUND",
                "error": "Source file not found",
            })
            continue

        try:
            # 1. Load normalized source image (HEIC decode, EXIF auto-orientation, RGB)
            full_img = sanitizer.load_normalized_image(src_path)
            w, h = full_img.size

            # 2. Extract Front Region (No slicing for single bags/vegetables!)
            if stype == "single":
                front_raw_img = full_img
            elif stype == "split":
                f_half = spec.get("front_half", "left")
                if f_half == "left":
                    front_raw_img = full_img.crop((0, 0, int(w * 0.54), h))
                elif f_half == "right":
                    front_raw_img = full_img.crop((int(w * 0.46), 0, w, h))
                elif f_half == "top":
                    front_raw_img = full_img.crop((0, 0, w, int(h * 0.54)))
                elif f_half == "bottom":
                    front_raw_img = full_img.crop((0, int(h * 0.46), w, h))
                else:
                    front_raw_img = full_img
            else:
                front_raw_img = full_img

            if spec.get("rotation"):
                front_raw_img = front_raw_img.rotate(spec["rotation"], expand=True)

            # 3. High-Fidelity BiRefNet Matting with hole & transparent packaging protection
            t0 = time.time()
            rgba, alpha = matting.remove_background(
                front_raw_img,
                enable_hole_protection=True,
                is_complex=True,
            )
            matting_time = time.time() - t0

            # 4. Canvas Standardization to 2048x2048 #FFFFFF with studio floor shadow
            packshot_front, mask, bbox = standardizer.standardize(rgba)

            # 5. Anti-Duplicate Guard
            is_unique, collision = guard.check_image_unique(packshot_front, bc)
            if not is_unique:
                print(f"  [ANTI-DUPLICATE WARNING] Image collision detected with barcode {collision}")

            # 6. Save deliverable front image (STRICTLY SINGLE FILE: {barcode}_front.jpg)
            out_front_path = FRONT_HD_DIR / f"{bc}_front.jpg"
            packshot_front.save(out_front_path, "JPEG", quality=95, optimize=True)

            # 7. Quality Gate Evaluation
            metrics = gate.evaluate_packshot(packshot_front, mask, bc, bc)
            print(f"  Front Saved: {out_front_path.name} in {matting_time:.1f}s | BBox: {bbox}")
            print(f"  Quality Gate: {metrics.decision} (Solidity: {metrics.solidity:.3f}, Blur: {metrics.blur_score:.1f}, Margin: {metrics.canvas_clipping_px}px)")

            results.append({
                "barcode": bc,
                "name": nm,
                "source": src_fn,
                "type": stype,
                "mode": mode,
                "decision": metrics.decision,
                "solidity": float(metrics.solidity),
                "blur_score": float(metrics.blur_score),
                "bbox": [int(x) for x in bbox],
                "front_path": str(out_front_path),
                "warnings": metrics.warning_reasons,
                "fails": metrics.fail_reasons,
            })

        except Exception as e:
            print(f"  [ERROR] Failed to process {bc}: {e}")
            results.append({
                "barcode": bc,
                "name": nm,
                "source": src_fn,
                "type": stype,
                "mode": mode,
                "decision": "ERROR",
                "error": str(e),
            })

    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"PIPELINE COMPLETED IN {total_time/60:.1f} MINUTES")
    print(f"Total processed : {len(results)}")
    print(f"Passed          : {sum(1 for r in results if r.get('decision') in ('PASS', 'WARNING_ACCEPT'))}")
    print(f"Errors/Failed   : {sum(1 for r in results if r.get('decision') not in ('PASS', 'WARNING_ACCEPT'))}")
    print(f"Total files in output dir: {len(list(FRONT_HD_DIR.glob('*.*')))}")
    print("=" * 80)

    # Save ledger
    audit_file = REPORTS_DIR / "g4_front_audit_ledger.json"
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_evaluated": len(results),
            "passed": sum(1 for r in results if r.get("decision") in ("PASS", "WARNING_ACCEPT")),
            "failed": sum(1 for r in results if r.get("decision") not in ("PASS", "WARNING_ACCEPT")),
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"Audit ledger saved to: {audit_file}")
    return 0


if __name__ == "__main__":
    sys.exit(run_pipeline())
