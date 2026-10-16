#!/usr/bin/env python3
"""Decoupled, non-blocking batch pipeline runner.

Architecture:
1. First-Pass Gate: Clean images immediately pass and proceed to delivery without waiting.
2. Refinement Worker: Defective but recoverable images are routed to an isolated refinement step.
3. Poor Source Flagging: Truly poor or unrecoverable images are tagged separately without blocking the batch.
4. Metric Tracking: Measures first-pass pass rate, post-refinement rate, flagged rate, and processing time.
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

import cv2
import numpy as np
import openpyxl
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXCEL_PATH = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
V5_DIR = ROOT / "output/catalog_pairs/tagged/front-v5"
V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
APPT_DIR = ROOT / "output/catalog_pairs/tagged/apptance"
DELIVERY_DIR = ROOT / "output/catalog_pairs/front-delivery-1169"
SOURCE_MAP_PATH = ROOT / "output/catalog_pairs/front_v3_source_map.json"

TARGET_CANVAS = 2400
MIN_MARGIN = 48


def load_ordered_catalog() -> list[dict]:
    """Load unique barcodes in exact Excel catalog order that have back photos."""
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


def audit_image(image_path: Path, back_path: Path | None = None) -> tuple[bool, list[str], dict]:
    """Audit single image for defects. Returns (is_clean, defect_list, metrics)."""
    if not image_path.exists():
        return False, ["missing_file"], {}
        
    with Image.open(image_path) as im:
        rgb = np.asarray(im.convert("RGB"))
        
    defects = []
    h, w, c = rgb.shape
    
    # 1. Size check
    if (w, h) != (TARGET_CANVAS, TARGET_CANVAS):
        defects.append(f"wrong_size_{w}x{h}")
        
    # 2. Corner whiteness
    corners = [rgb[:32, :32], rgb[:32, -32:], rgb[-32:, :32], rgb[-32:, -32:]]
    min_corner = min(c.mean() for c in corners)
    if min_corner < 250.0:
        defects.append(f"gray_corners_{int(min_corner)}")
        
    # 3. Product occupancy
    dist = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    fg = dist > 20
    ys, xs = np.where(fg)
    
    if len(xs) < 100:
        defects.append("empty_or_tiny_product")
        metrics = {"plong": 0, "aspect": 0.0, "min_corner": min_corner}
    else:
        pw = int(xs.max() - xs.min() + 1)
        ph = int(ys.max() - ys.min() + 1)
        plong = max(pw, ph)
        pshort = min(pw, ph)
        aspect = pshort / max(1, plong)
        
        if plong < 1200:
            defects.append(f"small_product_{plong}px")
        if aspect < 0.18:
            defects.append(f"cut_to_strip_aspect_{aspect:.2f}")
            
        metrics = {"plong": plong, "aspect": aspect, "min_corner": min_corner}
        
    # 4. Compare with back image (face inversion)
    if back_path and back_path.exists():
        try:
            with Image.open(back_path) as bim:
                brgb = cv2.resize(np.asarray(bim.convert("RGB")), (300, 300))
            frgb = cv2.resize(rgb, (300, 300))
            diff = float(np.mean(np.abs(frgb.astype(np.float32) - brgb.astype(np.float32))))
            if diff < 12.0:
                defects.append(f"same_as_back_diff_{diff:.1f}")
        except Exception:
            pass
            
    return len(defects) == 0, defects, metrics


def prepare_canvas_image(image: Image.Image) -> Image.Image:
    """Pad and center image onto 2400x2400 pure white canvas."""
    rgb = image.convert("RGB")
    if rgb.size == (TARGET_CANVAS, TARGET_CANVAS):
        return rgb
    w, h = rgb.size
    avail = TARGET_CANVAS - 2 * MIN_MARGIN
    scale = min(avail / w, avail / h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (TARGET_CANVAS, TARGET_CANVAS), (255, 255, 255))
    canvas.paste(resized, ((TARGET_CANVAS - new_w) // 2, (TARGET_CANVAS - new_h) // 2))
    return canvas


def refine_product(barcode: str, source_map: dict) -> tuple[bool, Image.Image | None, str]:
    """Attempt refinement on a defective product from available original / fallback sources."""
    # 1. Try front-v3 if it has a complete box
    v3_path = V3_DIR / f"{barcode}-front.jpg"
    if v3_path.exists():
        is_clean, defects, metrics = audit_image(v3_path)
        if is_clean or (metrics.get("aspect", 0) >= 0.25 and metrics.get("plong", 0) >= 1200):
            with Image.open(v3_path) as im:
                canvas = prepare_canvas_image(im)
                is_c, _, _ = audit_image_obj(canvas)
                if is_c:
                    return True, canvas, "recovered_from_v3_complete_packshot"
                    
    # 2. Try apptance
    appt_path = APPT_DIR / f"{barcode}-front.jpg"
    if appt_path.exists():
        with Image.open(appt_path) as im:
            canvas = prepare_canvas_image(im)
            is_c, _, _ = audit_image_obj(canvas)
            if is_c:
                return True, canvas, "recovered_from_apptance"
                
    # 3. Try original photo if available
    info = source_map.get(barcode, {})
    paths = [Path(p) for p in info.get("paths", []) if Path(p).exists()]
    if paths:
        # We can perform auto-crop from original if needed
        pass
        
    return False, None, "unrecoverable_needs_manual_check"


def audit_image_obj(image: Image.Image) -> tuple[bool, list[str], dict]:
    rgb = np.asarray(image.convert("RGB"))
    corners = [rgb[:32, :32], rgb[:32, -32:], rgb[-32:, :32], rgb[-32:, -32:]]
    min_corner = min(c.mean() for c in corners)
    dist = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    fg = dist > 20
    ys, xs = np.where(fg)
    if len(xs) < 100:
        return False, ["empty"], {}
    pw = int(xs.max() - xs.min() + 1)
    ph = int(ys.max() - ys.min() + 1)
    plong = max(pw, ph)
    aspect = min(pw, ph) / max(1, plong)
    ok = (min_corner >= 250.0 and plong >= 1200 and aspect >= 0.18)
    return ok, [], {"plong": plong, "aspect": aspect}


def process_batch(batch_num: int = 1, batch_size: int = 100) -> dict:
    start_time = time.perf_counter()
    catalog = load_ordered_catalog()
    
    start_idx = (batch_num - 1) * batch_size
    end_idx = min(len(catalog), start_idx + batch_size)
    batch_items = catalog[start_idx:end_idx]
    
    if not batch_items:
        print(f"Batch {batch_num} is empty!")
        return {}
        
    with open(SOURCE_MAP_PATH, "r", encoding="utf-8") as f:
        source_map = json.load(f)
        
    first_pass_ok = []
    recovered_ok = []
    flagged_poor = []
    
    for item in batch_items:
        bc = item["barcode"]
        front_p = V5_DIR / f"{bc}-front.jpg"
        back_p = BACK_DIR / f"{bc}-back.jpg"
        
        # Step 1: First-Pass Gate
        is_clean, defects, metrics = audit_image(front_p, back_p)
        
        if is_clean:
            first_pass_ok.append({
                "barcode": bc,
                "name": item["name"],
                "excel_row": item["excel_row"],
                "metrics": metrics,
            })
            # Immediate pass - ensure delivery copy is up to date
            shutil.copy2(front_p, DELIVERY_DIR / f"{bc}-front.jpg")
        else:
            # Step 2: Refinement Worker (Tách luồng xử lý lại)
            success, refined_img, reason = refine_product(bc, source_map)
            if success and refined_img is not None:
                # Save refined image to front-v5 and delivery
                refined_img.save(front_p, "JPEG", quality=95, subsampling=0)
                refined_img.save(DELIVERY_DIR / f"{bc}-front.jpg", "JPEG", quality=95, subsampling=0)
                recovered_ok.append({
                    "barcode": bc,
                    "name": item["name"],
                    "excel_row": item["excel_row"],
                    "initial_defects": defects,
                    "resolution": reason,
                })
            else:
                # Step 3: Flagged / Poor source (Đánh dấu riêng, không tắc luồng)
                flagged_poor.append({
                    "barcode": bc,
                    "name": item["name"],
                    "excel_row": item["excel_row"],
                    "defects": defects,
                    "reason": reason,
                })
                
    elapsed_s = time.perf_counter() - start_time
    total = len(batch_items)
    avg_ms = (elapsed_s / total) * 1000 if total > 0 else 0
    
    first_pass_rate = (len(first_pass_ok) / total) * 100
    recovered_rate = (len(recovered_ok) / total) * 100
    flagged_rate = (len(flagged_poor) / total) * 100
    total_yield = ((len(first_pass_ok) + len(recovered_ok)) / total) * 100
    
    report = {
        "batch_num": batch_num,
        "batch_range": f"{start_idx + 1}..{end_idx}",
        "total_items": total,
        "first_pass_count": len(first_pass_ok),
        "first_pass_rate": round(first_pass_rate, 1),
        "recovered_count": len(recovered_ok),
        "recovered_rate": round(recovered_rate, 1),
        "flagged_count": len(flagged_poor),
        "flagged_rate": round(flagged_rate, 1),
        "total_yield": round(total_yield, 1),
        "elapsed_seconds": round(elapsed_s, 2),
        "avg_ms_per_photo": round(avg_ms, 1),
        "recovered_items": recovered_ok,
        "flagged_items": flagged_poor,
    }
    
    # Save batch audit log
    log_dir = ROOT / "output/catalog_pairs/batch_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"batch_{batch_num:02d}_report.json"
    log_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"=== BATCH {batch_num} AUDIT & PROCESSING SUMMARY ({start_idx + 1}..{end_idx}) ===")
    print(f"Total items in batch: {total}")
    print(f"1. First-Pass Pass Rate: {report['first_pass_rate']}% ({len(first_pass_ok)}/{total} items passed immediately)")
    print(f"2. Post-Refinement Rate: {report['recovered_rate']}% ({len(recovered_ok)}/{total} items recovered in refinement)")
    print(f"3. Flagged / Poor Source: {report['flagged_rate']}% ({len(flagged_poor)}/{total} items flagged for manual review)")
    print(f"-> OVERALL YIELD: {report['total_yield']}%")
    print(f"Average time per photo: {report['avg_ms_per_photo']} ms (Total: {report['elapsed_seconds']} s)")
    
    if recovered_ok:
        print("\nRecovered Items:")
        for r in recovered_ok:
            print(f"  Row {r['excel_row']} | {r['barcode']} | {r['name'][:30]}: {r['initial_defects']} -> {r['resolution']}")
            
    if flagged_poor:
        print("\nFlagged Items (to be handled separately):")
        for f in flagged_poor:
            print(f"  Row {f['excel_row']} | {f['barcode']} | {f['name'][:30]}: {f['defects']}")
            
    return report


def run_all_batches():
    print("=== STARTING FULL RUN: BATCH 1 TO BATCH 12 (1169 ITEMS) ===")
    total_start = time.perf_counter()
    all_reports = []
    
    for batch_num in range(1, 13):
        print(f"\n>>> Running Batch {batch_num}/12...")
        rep = process_batch(batch_num)
        all_reports.append(rep)
        
    total_elapsed = time.perf_counter() - total_start
    total_photos = sum(r["total_items"] for r in all_reports)
    total_first_pass = sum(r["first_pass_count"] for r in all_reports)
    total_recovered = sum(r["recovered_count"] for r in all_reports)
    total_flagged = sum(r["flagged_count"] for r in all_reports)
    
    print("\n" + "=" * 60)
    print("=== FULL RUN COMPLETE: 1169 ITEMS ACROSS 12 BATCHES ===")
    print("=" * 60)
    print(f"Total Processed: {total_photos} photos")
    print(f"Total Time: {total_elapsed:.1f} s (Average: {(total_elapsed / total_photos)*1000:.1f} ms / photo)")
    print(f"1. First-Pass Pass: {total_first_pass} ({(total_first_pass / total_photos)*100:.1f}%)")
    print(f"2. Post-Refinement Recovered: {total_recovered} ({(total_recovered / total_photos)*100:.1f}%)")
    print(f"3. Flagged for Manual Review: {total_flagged} ({(total_flagged / total_photos)*100:.1f}%)")
    print(f"Overall Catalog Yield: {((total_first_pass + total_recovered) / total_photos)*100:.1f}%")
    
    # Update Excel and HTML gallery
    try:
        from scripts.build_complete_front_1169 import main as update_delivery
        print("\nUpdating final delivery Excel workbook and interactive HTML review gallery...")
        update_delivery()
    except Exception as e:
        print(f"Delivery update note: {e}")


if __name__ == "__main__":
    import sys
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if arg == "all":
        run_all_batches()
    else:
        process_batch(int(arg))
