#!/usr/bin/env python3
r"""Batch reprocess all catalog items directly from the 5 original photo folders.

Original folders:
- source-import/G1_original
- source-import/G2_original
- source-import/G3_Original
- source-import/G4-original
- source-import/Nyt25.09.26
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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
import zxingcpp

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent

EXCEL_PATH = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
V5_DIR = ROOT / "output/catalog_pairs/tagged/front-v5"
DELIVERY_DIR = ROOT / "output/catalog_pairs/front-delivery-1169"

TARGET_CANVAS = 2400
MIN_MARGIN = 48


def build_full_source_index() -> dict[str, Path]:
    index = {}
    manifests = [
        "manifest_G1_original_v2.json",
        "manifest_G2_original_v2.json",
        "manifest_G3_Original_v2.json",
        "manifest_G4-original_v2.json",
        "manifest_Nyt25.09.26_v2.json",
    ]
    for m in manifests:
        p = ROOT / "output/catalog_pairs" / m
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for bc, info in data.get("products", {}).items():
                        src = info.get("source")
                        if src and Path(src).exists() and bc not in index:
                            index[bc] = Path(src)
            except Exception:
                pass
                
    smap_p = ROOT / "output/catalog_pairs/front_v3_source_map.json"
    if smap_p.exists():
        try:
            with open(smap_p, "r", encoding="utf-8") as f:
                smap = json.load(f)
                for bc, info in smap.items():
                    if bc not in index:
                        for sp in info.get("paths", []):
                            if Path(sp).exists():
                                index[bc] = Path(sp)
                                break
        except Exception:
            pass
            
    # Also check special filenames like Tofu.jpg
    nyt = ROOT / "source-import/Nyt25.09.26"
    if (nyt / "Tofu.jpg").exists():
        index["87282504"] = nyt / "Tofu.jpg"
        
    return index


def reprocess_worker(barcode: str, src_path_str: str) -> tuple[str, bool, str]:
    try:
        from rembg import remove, new_session
        import pillow_heif
        pillow_heif.register_heif_opener()
        
        session = new_session("u2net")
        src_path = Path(src_path_str)
        
        with Image.open(src_path) as im:
            rgb_im = im.convert("RGB")
            w, h = rgb_im.size
            
            # Barcode scanning
            hits = zxingcpp.read_barcodes(rgb_im, try_rotate=True, try_downscale=True)
            if not hits:
                scaled = rgb_im.copy()
                scaled.thumbnail((1600, 1600))
                hits = zxingcpp.read_barcodes(scaled, try_rotate=True, try_downscale=True)
                sw, sh = scaled.size
            else:
                sw, sh = w, h
                
            target_hit = None
            for hit in hits:
                clean = "".join(c for c in str(hit.text or "") if c.isdigit())
                if barcode in clean or clean in barcode:
                    target_hit = hit
                    break
            if not target_hit and hits:
                target_hit = hits[0]
                
            if target_hit:
                pts = [(getattr(target_hit.position, name).x, getattr(target_hit.position, name).y) for name in ('top_left', 'top_right', 'bottom_right', 'bottom_left')]
                bc_x = sum(p[0] for p in pts) / 4.0 / float(sw)
                bc_y = sum(p[1] for p in pts) / 4.0 / float(sh)
            else:
                bc_x, bc_y = 0.5, 0.5
                
            # Determine front crop box
            if w >= h: # Landscape
                if bc_x > 0.5:
                    crop_box = (0, 0, int(0.62 * w), h)
                else:
                    crop_box = (int(0.38 * w), 0, w, h)
            else: # Portrait
                if abs(bc_y - 0.5) > 0.15: # Vertically stacked
                    if bc_y > 0.5:
                        crop_box = (0, 0, w, int(0.62 * h))
                    else:
                        crop_box = (0, int(0.38 * h), w, h)
                elif bc_x > 0.5:
                    crop_box = (0, 0, int(0.62 * w), h)
                else:
                    crop_box = (int(0.38 * w), 0, w, h)
                    
            front_sub = rgb_im.crop(crop_box)
            nobg = remove(front_sub, session=session)
            alpha = np.asarray(nobg)[:, :, 3]
            ys, xs = np.where(alpha > 30)
            if len(xs) < 100:
                return barcode, False, "alpha empty"
                
            product = nobg.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
            pw, ph = product.size
            
            avail = TARGET_CANVAS - 2 * MIN_MARGIN
            scale = min(avail / pw, avail / ph)
            nw, nh = max(1, int(round(pw * scale))), max(1, int(round(ph * scale)))
            resized = product.resize((nw, nh), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (TARGET_CANVAS, TARGET_CANVAS), (255, 255, 255))
            canvas.paste(resized, ((TARGET_CANVAS - nw) // 2, (TARGET_CANVAS - nh) // 2), resized)
            
            dest_v5 = V5_DIR / f"{barcode}-front.jpg"
            dest_deliv = DELIVERY_DIR / f"{barcode}-front.jpg"
            canvas.save(dest_v5, "JPEG", quality=95, subsampling=0)
            canvas.save(dest_deliv, "JPEG", quality=95, subsampling=0)
            
            return barcode, True, f"w={pw}, h={ph} from {src_path.name}"
    except Exception as e:
        return barcode, False, f"error: {e}"


def run_full_reprocessing(max_workers: int = 4):
    print("=== STARTING FULL REPROCESSING DIRECTLY FROM THE 5 ORIGINAL PHOTO FOLDERS ===")
    t_start = time.perf_counter()
    
    index = build_full_source_index()
    print(f"Total barcodes mapped to original photos: {len(index)}")
    
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    sheet = wb.active
    back_bcs = set(f.stem.replace("-back", "") for f in BACK_DIR.glob("*.jpg"))
    
    catalog_bcs = []
    seen = set()
    for row in sheet.iter_rows(min_row=2, values_only=True):
        bc = str(row[0]).strip() if row[0] is not None else ""
        if bc and bc in back_bcs and bc not in seen:
            seen.add(bc)
            catalog_bcs.append(bc)
            
    print(f"Total catalog barcodes: {len(catalog_bcs)}")
    
    # Strictly protect barcodes in apptance (confirmed by user)
    APPT_DIR = ROOT / "output/catalog_pairs/tagged/apptance"
    apptance_bcs = set(f.stem.replace("-front", "") for f in APPT_DIR.glob("*.*"))
    
    protected_apptance = [bc for bc in catalog_bcs if bc in apptance_bcs]
    targets_to_reprocess = [bc for bc in catalog_bcs if bc not in apptance_bcs]
    
    with_orig = [bc for bc in targets_to_reprocess if bc in index]
    without_orig = [bc for bc in targets_to_reprocess if bc not in index]
    
    print(f"  - [PROTECTED] In apptance (Skipped, user-confirmed): {len(protected_apptance)}")
    print(f"  - [TARGETS] To reprocess from 5 original folders: {len(targets_to_reprocess)}")
    print(f"    * Confirmed original photo in 5 folders: {len(with_orig)}")
    print(f"    * Missing original photo in 5 folders: {len(without_orig)}")
    
    success_count = 0
    fail_count = 0
    
    print(f"\nProcessing {len(with_orig)} items directly from raw original photos with {max_workers} parallel workers...")
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(reprocess_worker, bc, str(index[bc])): bc for bc in with_orig}
        completed = 0
        for future in as_completed(futures):
            bc, ok, msg = future.result()
            completed += 1
            if ok:
                success_count += 1
            else:
                fail_count += 1
                print(f"  [REPROCESS FAILED] {bc}: {msg}")
                
            if completed % 50 == 0 or completed == len(with_orig):
                print(f"Progress: {completed}/{len(with_orig)} items ({success_count} success, {fail_count} failed)...")
                
    elapsed = time.perf_counter() - t_start
    print("\n" + "=" * 60)
    print("=== REPROCESSING COMPLETE ===")
    print("=" * 60)
    print(f"Total processed from raw originals: {len(with_orig)}")
    print(f"Successfully rendered to front-v5: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Total execution time: {elapsed:.1f} s (Average: {(elapsed / max(1, len(with_orig))):.2f} s / item)")
    
    # Update Excel deliverable
    try:
        from scripts.build_complete_front_1169 import main as update_delivery
        print("\nUpdating Excel workbook and review gallery with newly reprocessed packshots...")
        update_delivery()
    except Exception as e:
        print(f"Delivery update note: {e}")


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    run_full_reprocessing(workers)
