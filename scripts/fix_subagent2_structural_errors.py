#!/usr/bin/env python3
"""
scripts/fix_subagent2_structural_errors.py
------------------------------------------
Fix all 62 structural error files in output/catalog_pairs/tagged/front-v3/.
Input list: scratch/subagent2_error_list.json.

Requirements:
1. For each file:
   - Non-2400x2400 dimensions (e.g. 447x447, 554x554, 600x600, etc.)
   - Non-white outer borders
   - Touching frame edges
2. Check best authentic source:
   - High-res native sources / HD Studio sources
   - Fallback to clean front-v3 image
   - Clean up packaging with rembg and hole-filling
   - Center on pure white 2400x2400 canvas with ~84-88% occupancy
   - Guarantee 100% pure white outer borders
3. Save fixed images to staging folder: output/catalog_pairs/fixed_sub2/
4. Verify all 62 images strictly against diagnostic criteria.
5. Overwrite corresponding files in output/catalog_pairs/tagged/front-v3/.
"""

import os
import sys
import json
import shutil
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image
from rembg import remove, new_session

ROOT = Path(__file__).resolve().parent.parent
INPUT_LIST = ROOT / "scratch/subagent2_error_list.json"
FRONT_V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
STAGING_DIR = ROOT / "output/catalog_pairs/fixed_sub2"
BC_FRONT_DIR = ROOT / "output/barcode_first/front"
HD_STUDIO_DIR = ROOT / "output/shopify_import_final/HD_Studio_Front_Images"
BACKUP_DIR = ROOT / "output/catalog_pairs/front-v3-backups/before-enhancement-2026-10-15/files"


def process_packshot(
    input_img: Image.Image,
    session,
    target_dim: int = 2400
) -> Image.Image:
    # 1. Background removal using rembg
    rembg_res = remove(input_img, session=session)
    arr_res = np.array(rembg_res)
    alpha = arr_res[:, :, 3]

    # 2. Fill internal holes so labels/graphics inside packaging are not hollowed out
    bin_mask = (alpha > 64).astype(np.uint8) * 255
    filled = np.zeros_like(bin_mask)
    contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        max_area = max(cv2.contourArea(c) for c in contours)
        valid = [c for c in contours if cv2.contourArea(c) >= max(100.0, max_area * 0.05)]
        cv2.drawContours(filled, valid, -1, 255, thickness=cv2.FILLED)

    dist = cv2.distanceTransform(filled, cv2.DIST_L2, 5)
    final_alpha = alpha.copy().astype(np.float32)
    final_alpha[dist > 3] = 255.0  # Solid inside
    final_alpha[dist == 0] = 0.0  # Transparent outside
    final_alpha = np.clip(final_alpha, 0, 255).astype(np.uint8)

    ys, xs = np.where(final_alpha > 0)
    if len(xs) == 0:
        # Fallback if rembg somehow failed: use non-white thresholding
        arr_orig = np.array(input_img.convert("RGB"))
        non_white = (255 - arr_orig).max(axis=-1) > 10
        ys, xs = np.where(non_white)
        if len(xs) == 0:
            raise ValueError("Input image is completely blank")
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
        rgb_crop = arr_orig[y0:y1, x0:x1]
        cropped_im = Image.fromarray(rgb_crop)
        pw, ph = x1 - x0, y1 - y0
    else:
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
        pw, ph = x1 - x0, y1 - y0
        rgb_crop = np.array(input_img.convert("RGB"))[y0:y1, x0:x1]
        a_crop = final_alpha[y0:y1, x0:x1, None] / 255.0
        crop_comp = (rgb_crop * a_crop + 255.0 * (1.0 - a_crop)).round().astype(np.uint8)
        cropped_im = Image.fromarray(crop_comp)

    # 3. Calculate scaling and occupancy (~84-88%)
    ratio = pw / float(ph)
    occ = 0.88 if (ratio < 0.65 or ratio > 1.35) else 0.85
    scale = (target_dim * occ) / float(max(pw, ph))
    new_w = max(1, round(pw * scale))
    new_h = max(1, round(ph * scale))
    resized = cropped_im.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 4. Center on pure white 2400x2400 canvas
    canvas = Image.new("RGB", (target_dim, target_dim), (255, 255, 255))
    offset_x = (target_dim - new_w) // 2
    offset_y = (target_dim - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))

    # 5. Guaranteed pure white outer border (outer 20px strictly (255, 255, 255))
    arr = np.array(canvas)
    arr[:20, :] = 255
    arr[-20:, :] = 255
    arr[:, :20] = 255
    arr[:, -20:] = 255
    canvas = Image.fromarray(arr)

    return canvas


def main():
    print("=" * 80)
    print("     SUBAGENT 2: STRUCTURAL ERROR FIXER (62 FILES)")
    print("=" * 80)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    session = new_session("u2net")

    with open(INPUT_LIST, "r", encoding="utf-8") as f:
        error_items = json.load(f)

    print(f"Loaded {len(error_items)} items from {INPUT_LIST.name}")

    staged_results = []

    for idx, item in enumerate(error_items):
        fn = item["filename"]
        bc = item["barcode"]
        reason = item.get("reason", "")
        dims = item.get("dims", [])

        print(f"\n[{idx+1:2d}/62] Processing {fn} (Barcode: {bc}, current dims: {dims})...")

        # Select best source image
        chosen_src_path = None
        chosen_src_type = None

        # Check Candidate 1: barcode_first/front (if size is 2400x2400 and matches front)
        bcf_p = BC_FRONT_DIR / f"{bc}_front.jpg"
        fv3_p = FRONT_V3_DIR / fn
        if not fv3_p.exists():
            fv3_p = BACKUP_DIR / fn

        if bcf_p.exists() and fv3_p.exists():
            try:
                bcf_im = Image.open(bcf_p)
                fv3_im = Image.open(fv3_p)
                # Compare similarity to ensure it's the FRONT, not BACK
                t1 = bcf_im.resize((100, 100)).convert("L")
                t2 = fv3_im.resize((100, 100)).convert("L")
                diff = np.abs(np.array(t1, dtype=float) - np.array(t2, dtype=float)).mean()

                # If bcf is clean 2400x2400 and reasonably matches front (< 65 diff)
                if bcf_im.size == (2400, 2400) and diff < 65.0:
                    arr_b = np.array(bcf_im.convert("RGB"))
                    b_clean = (arr_b[0] == 255).all() and (arr_b[-1] == 255).all() and (arr_b[:, 0] == 255).all() and (arr_b[:, -1] == 255).all()
                    non_w = (arr_b != 255).any(axis=-1)
                    if b_clean and non_w.any():
                        ys, xs = np.where(non_w)
                        if xs.min() > 0 and ys.min() > 0 and xs.max() + 1 < 2400 and ys.max() + 1 < 2400:
                            chosen_src_path = bcf_p
                            chosen_src_type = f"barcode_first (native 2400, diff={diff:.1f})"
                elif bcf_im.size[0] >= 1400 and diff < 65.0:
                    chosen_src_path = bcf_p
                    chosen_src_type = f"barcode_first (high-res {bcf_im.size}, diff={diff:.1f})"
            except Exception as e:
                print(f"  Warning checking bcf: {e}")

        # Check Candidate 2: HD Studio
        if chosen_src_path is None:
            for cand_bc in [bc, f"0{bc}", f"00{bc}"]:
                hd_p = HD_STUDIO_DIR / f"{cand_bc}.jpg"
                if hd_p.exists():
                    try:
                        hd_im = Image.open(hd_p)
                        if fv3_p.exists():
                            t1 = hd_im.resize((100, 100)).convert("L")
                            t2 = Image.open(fv3_p).resize((100, 100)).convert("L")
                            diff = np.abs(np.array(t1, dtype=float) - np.array(t2, dtype=float)).mean()
                            if diff < 65.0:
                                chosen_src_path = hd_p
                                chosen_src_type = f"hd_studio ({hd_im.size}, diff={diff:.1f})"
                                break
                    except Exception:
                        pass

        # Candidate 3: existing front-v3 or backup
        if chosen_src_path is None:
            if fv3_p.exists():
                chosen_src_path = fv3_p
                chosen_src_type = f"front-v3 existing ({Image.open(fv3_p).size})"
            else:
                raise FileNotFoundError(f"No source image found for {fn}")

        print(f"  Using source: {chosen_src_type} -> {chosen_src_path}")

        # Load input image
        with Image.open(chosen_src_path) as src_im:
            src_im = src_im.convert("RGB")
            # If chosen_src is already perfect 2400x2400 and border clean:
            if src_im.size == (2400, 2400) and "native 2400" in chosen_src_type:
                # Copy directly with border guarantee
                arr = np.array(src_im)
                arr[:20, :] = 255
                arr[-20:, :] = 255
                arr[:, :20] = 255
                arr[:, -20:] = 255
                fixed_im = Image.fromarray(arr)
            else:
                fixed_im = process_packshot(src_im, session, target_dim=2400)

        # Save to staging
        staged_path = STAGING_DIR / fn
        if fn.lower().endswith(".png"):
            fixed_im.save(staged_path, "PNG", optimize=True)
        else:
            fixed_im.save(staged_path, "JPEG", quality=95, subsampling=0)

        # Immediate QA verification
        with Image.open(staged_path) as check_im:
            cw, ch = check_im.size
            carr = np.array(check_im.convert("RGB"))

        assert (cw, ch) == (2400, 2400), f"Wrong dimensions: {(cw, ch)}"
        top_clean = (carr[0] == 255).all()
        bot_clean = (carr[-1] == 255).all()
        left_clean = (carr[:, 0] == 255).all()
        right_clean = (carr[:, -1] == 255).all()
        assert top_clean and bot_clean and left_clean and right_clean, "Outer border not pure white #FFFFFF"

        non_white = (carr != 255).any(axis=-1)
        assert non_white.any(), "Image is blank white"

        ys, xs = np.where(non_white)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
        pw, ph = x1 - x0, y1 - y0
        touches = (x0 == 0 or y0 == 0 or x1 == 2400 or y1 == 2400)
        assert not touches, f"Touches border: bbox=[{x0}, {y0}, {x1}, {y1}]"

        fg_crop = carr[y0:y1, x0:x1]
        gray_fg = cv2.cvtColor(fg_crop, cv2.COLOR_RGB2GRAY)
        lap_var = float(cv2.Laplacian(gray_fg, cv2.CV_64F).var())

        print(f"  VERIFIED: 2400x2400, pure white border, bbox=[{x0},{y0},{x1},{y1}] ({pw}x{ph}), lap_var={lap_var:.1f}")

        staged_results.append({
            "filename": fn,
            "barcode": bc,
            "source_used": chosen_src_type,
            "bbox": [x0, y0, x1, y1],
            "laplacian_var": round(lap_var, 1),
            "staged_path": str(staged_path),
            "target_path": str(FRONT_V3_DIR / fn)
        })

    print("\n" + "=" * 80)
    print(f"  ALL {len(staged_results)}/62 FILES SUCCESSFULLY FIXED AND VERIFIED IN STAGING!")
    print("=" * 80)

    # Overwrite into target directory output/catalog_pairs/tagged/front-v3/
    print("\nOverwriting verified files into output/catalog_pairs/tagged/front-v3/...")
    for res in staged_results:
        src = Path(res["staged_path"])
        dst = Path(res["target_path"])
        shutil.copy2(src, dst)

    # Re-verify live directory
    print("\nFinal QA verification on live output/catalog_pairs/tagged/front-v3/ directory:")
    failures = 0
    for res in staged_results:
        dst = Path(res["target_path"])
        with Image.open(dst) as live_im:
            lw, lh = live_im.size
            larr = np.array(live_im.convert("RGB"))
        t_ok = (larr[0] == 255).all() and (larr[-1] == 255).all() and (larr[:, 0] == 255).all() and (larr[:, -1] == 255).all()
        nw = (larr != 255).any(axis=-1)
        ys, xs = np.where(nw)
        touches = (xs.min() == 0 or ys.min() == 0 or xs.max() + 1 == lw or ys.max() + 1 == lh)

        if (lw, lh) != (2400, 2400) or not t_ok or touches:
            print(f"  FAIL: {res['filename']} (dims: {lw}x{lh}, border_ok: {t_ok}, touches: {touches})")
            failures += 1

    if failures == 0:
        print("\nALL 62 FILES IN output/catalog_pairs/tagged/front-v3/ ARE 100% CLEAN AND PASS STRUCTURAL QA!")
    else:
        print(f"\nWARNING: {failures} files failed final QA check!")

    # Write summary log
    summary_path = ROOT / "scratch/subagent2_completion_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_fixed": len(staged_results),
            "failures": failures,
            "results": staged_results
        }, f, indent=2, ensure_ascii=False)
    print(f"\nSummary report saved to {summary_path}")


if __name__ == "__main__":
    main()
