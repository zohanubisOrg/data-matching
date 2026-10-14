#!/usr/bin/env python3
"""Retired automatic healing; render helper now requires a reviewed package mask.
Use reprocess_rabuta_verified.py for traceable candidates, not automatic QA PASS.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import zxingcpp
from rembg import new_session, remove

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
ORIGINALS_DIR = ROOT / "output/catalog_pairs/originals"
BACK_V2_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
FRONT_V3_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"
FRONT_V2_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
CUSTOMER_EXCEL = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx"
FRONT_V3_DIR.mkdir(parents=True, exist_ok=True)

_REMBG_SESSION = None

def get_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        _REMBG_SESSION = new_session("u2net")
    return _REMBG_SESSION

def separate_front_box(im: Image.Image, target_bc: str) -> tuple[Image.Image, tuple[int, int, int, int]]:
    w, h = im.size
    
    # 1. Multi-scale barcode detection
    hits = zxingcpp.read_barcodes(im, try_rotate=True, try_downscale=True)
    curr_w, curr_h = w, h
    if not hits:
        for max_dim in (2400, 1800, 1200):
            if max(w, h) > max_dim:
                scaled = im.copy()
                scaled.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                s_hits = zxingcpp.read_barcodes(scaled, try_rotate=True, try_downscale=True)
                if s_hits:
                    hits = s_hits
                    curr_w, curr_h = scaled.size
                    break

    if not hits:
        # Single product or unreadable barcode: full frame
        return im, (0, 0, w, h)
        
    # Pick matching barcode
    chosen_hit = hits[0]
    for h_hit in hits:
        clean = "".join(c for c in str(h_hit.text or "") if c.isdigit())
        if target_bc in clean or clean in target_bc:
            chosen_hit = h_hit
            break

    pts = [(getattr(chosen_hit.position, name).x, getattr(chosen_hit.position, name).y) for name in ('top_left', 'top_right', 'bottom_right', 'bottom_left')]
    bc_x = sum(p[0] for p in pts) / 4.0 / float(curr_w)
    bc_y = sum(p[1] for p in pts) / 4.0 / float(curr_h)

    # Multi-item detection via edge projection
    thumb = im.copy()
    thumb.thumbnail((800, 800))
    tw, th = thumb.size
    arr = np.asarray(thumb)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)

    # 1. LANDSCAPE ORIENTATION (width >= height):
    # Rule: Supermarket bench photos have products placed side-by-side. Pure vertical X-axis split ONLY.
    if w >= h:
        col_proj = edges.mean(axis=0)
        col_s = np.convolve(col_proj, np.ones(15) / 15.0, mode='same')
        c_min = int(tw * 0.35) + np.argmin(col_s[int(tw * 0.35):int(tw * 0.65)])
        c_seam = c_min / float(tw)
        
        if bc_x < 0.50:
            crop_box = (max(0, int(min(c_seam - 0.02, 0.48) * w)), 0, w, h)
        else:
            crop_box = (0, 0, min(w, int(max(c_seam + 0.02, 0.52) * w)), h)

    # 2. PORTRAIT ORIENTATION (width < height):
    else:
        # Check if stacked vertically (barcode distinctly high or low)
        if abs(bc_y - 0.50) > 0.15 and abs(bc_x - 0.50) <= 0.15:
            # Stacked vertically (e.g. Longkou vermicelli 8717703638608)
            row_proj = edges.mean(axis=1)
            row_s = np.convolve(row_proj, np.ones(15) / 15.0, mode='same')
            r_min = int(th * 0.35) + np.argmin(row_s[int(th * 0.35):int(th * 0.65)])
            r_seam = r_min / float(th)
            if bc_y > 0.50:
                crop_box = (0, 0, w, min(h, int(max(r_seam + 0.02, 0.52) * h)))
            else:
                crop_box = (0, max(0, int(min(r_seam - 0.02, 0.48) * h)), w, h)
        elif abs(bc_x - 0.50) > 0.10:
            # Side-by-side in portrait
            col_proj = edges.mean(axis=0)
            col_s = np.convolve(col_proj, np.ones(15) / 15.0, mode='same')
            c_min = int(tw * 0.35) + np.argmin(col_s[int(tw * 0.35):int(tw * 0.65)])
            c_seam = c_min / float(tw)
            if bc_x < 0.50:
                crop_box = (max(0, int(min(c_seam - 0.02, 0.48) * w)), 0, w, h)
            else:
                crop_box = (0, 0, min(w, int(max(c_seam + 0.02, 0.52) * w)), h)
        else:
            # Single product in frame: full frame
            crop_box = (0, 0, w, h)

    cropped = im.crop(crop_box)

    # 3. Post-check: If barcode still leaks inside cropped area, safely adjust edge without slivering
    leak_hits = zxingcpp.read_barcodes(cropped, try_rotate=True, try_downscale=True)
    matching_leak = [lh for lh in leak_hits if "".join(c for c in str(lh.text or "") if c.isdigit()) == target_bc]
    if matching_leak:
        cw, ch = cropped.size
        l_pts = [(getattr(matching_leak[0].position, name).x, getattr(matching_leak[0].position, name).y) for name in ('top_left', 'top_right', 'bottom_right', 'bottom_left')]
        l_x = sum(p[0] for p in l_pts) / 4.0 / float(cw)
        l_y = sum(p[1] for p in l_pts) / 4.0 / float(ch)
        
        # Only crop if barcode is within 15% of the border, and resulting width >= 30% of original
        if l_x < 0.15 and (cw - int(cw * 0.16)) >= (w * 0.30):
            cropped = cropped.crop((int(cw * 0.16), 0, cw, ch))
        elif l_x > 0.85 and int(cw * 0.84) >= (w * 0.30):
            cropped = cropped.crop((0, 0, int(cw * 0.84), ch))
        elif l_y < 0.15 and (ch - int(ch * 0.16)) >= (h * 0.30):
            cropped = cropped.crop((0, int(ch * 0.16), cw, ch))
        elif l_y > 0.85 and int(ch * 0.84) >= (h * 0.30):
            cropped = cropped.crop((0, 0, cw, int(ch * 0.84)))

    return cropped, crop_box


def render_studio_packshot(front_im: Image.Image, target_size: int = 2400, *, package_mask=None, shape="auto") -> Image.Image:
    """Legacy bridge: independently verified whole-package mask is mandatory."""
    sys.path.insert(0, str(ROOT / "src"))
    from product_mapper.vision.package_packshot import render_verified_packshot
    return render_verified_packshot(front_im, package_mask, target_size, shape)[0]


def is_guillotine_cut(packshot: Image.Image) -> bool:
    """Validate that product is not sliced by a flat guillotine line or reduced to a sliver."""
    arr = np.asarray(packshot.convert("RGB"))
    diff = np.abs(arr.astype(int) - 255).sum(axis=2)
    fg = diff > 20
    ys, xs = np.where(fg)
    if len(xs) == 0:
        return True

    bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    pw, ph = bx1 - bx0, by1 - by0

    # 1. Aspect ratio sliver check
    if pw / max(1, ph) < 0.20 or ph / max(1, pw) < 0.20:
        return True

    # 2. Border flat edge check
    crop_fg = fg[by0:by1, bx0:bx1]
    ch, cw = crop_fg.shape
    if ch < 20 or cw < 20:
        return True

    # Check top edge (rows 0..3) - must not be sliced across top (> 50%)
    if crop_fg[:3, :].mean(axis=1).max() > 0.50:
        return True
    # Check bottom edge (rows -3..) - accommodate natural flat jar/can bases up to 65%
    if crop_fg[-3:, :].mean(axis=1).max() > 0.65:
        return True
    # Check left edge (cols 0..3) - must not be sliced vertically (> 45%)
    if crop_fg[:, :3].mean(axis=0).max() > 0.45:
        return True
    # Check right edge (cols -3..) - must not be sliced vertically (> 45%)
    if crop_fg[:, -3:].mean(axis=0).max() > 0.45:
        return True

    return False


def fetch_openfoodfacts_packshot(barcode: str) -> Image.Image | None:
    """Fetch official high-resolution front packshot from Open Food Facts."""
    try:
        url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "RabutaCatalogPackshot/1.0 (contact@example.com)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == 1:
                p = data.get("product", {})
                img_url = p.get("image_front_url") or p.get("image_url")
                if img_url:
                    with urllib.request.urlopen(img_url, timeout=5) as img_resp:
                        return Image.open(BytesIO(img_resp.read()))
    except Exception:
        pass
    return None


def format_to_canvas(im: Image.Image, target_size: int = 2400, *, package_mask=None, shape='auto') -> Image.Image:
    """Legacy bridge; padding a photograph is not verified background removal."""
    return render_studio_packshot(im, target_size, package_mask=package_mask, shape=shape)


def load_excel_front_map() -> dict[str, Any]:
    """Load embedded customer front photos from final Excel workbook."""
    if not CUSTOMER_EXCEL.exists():
        return {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(CUSTOMER_EXCEL)
        ws = wb.active
        barcode_by_row = {}
        for r in range(4, ws.max_row + 1):
            bc = ws.cell(r, 1).value
            if bc:
                barcode_by_row[r] = str(bc).strip()

        excel_fronts = {}
        for img in ws._images:
            row_idx = getattr(getattr(img, "anchor", None), "_from", None)
            if row_idx is not None:
                excel_row = row_idx.row + 1
                bc = barcode_by_row.get(excel_row)
                if bc and hasattr(img, "_data"):
                    excel_fronts[bc] = img
        return excel_fronts
    except Exception:
        return {}


def process_single_product(barcode: str, excel_image_map: dict[str, Any] | None = None) -> bool:
    orig_dir = ORIGINALS_DIR / barcode
    dest_path = FRONT_V3_DIR / f"{barcode}-front.jpg"

    candidate_files = []
    if orig_dir.exists():
        candidate_files = [f for f in orig_dir.glob("*") if f.is_file() and not f.name.startswith(".")]

    # Tier 1: Original Camera Photo
    if candidate_files:
        best_file = candidate_files[0]
        if len(candidate_files) > 1:
            for f in candidate_files:
                try:
                    im_temp = ImageOps.exif_transpose(Image.open(f))
                    hits = zxingcpp.read_barcodes(im_temp, try_rotate=True, try_downscale=True)
                    if len(hits) == 0:
                        best_file = f
                        break
                except Exception:
                    continue

        try:
            im = ImageOps.exif_transpose(Image.open(best_file))
            # Attempt 1: Geometry-aware separation
            front_im, box = separate_front_box(im, barcode)
            packshot = render_studio_packshot(front_im, target_size=2400)
            if not is_guillotine_cut(packshot):
                packshot.save(dest_path, "JPEG", quality=95)
                return True
                
            # Attempt 2: If split was flagged as guillotine cut, try full-frame (single centered product)
            if box != (0, 0, im.width, im.height):
                full_packshot = render_studio_packshot(im, target_size=2400)
                if not is_guillotine_cut(full_packshot):
                    full_packshot.save(dest_path, "JPEG", quality=95)
                    return True
        except Exception:
            pass

    # Tier 2: Open Food Facts API (official studio front packshot)
    off_im = fetch_openfoodfacts_packshot(barcode)
    if off_im:
        try:
            packshot = render_studio_packshot(off_im, target_size=2400)
            packshot.save(dest_path, "JPEG", quality=95)
            return True
        except Exception:
            pass

    # Tier 3: Customer Excel Embedded Front Photo
    if excel_image_map and barcode in excel_image_map:
        try:
            img_obj = excel_image_map[barcode]
            pil_im = Image.open(BytesIO(img_obj._data())).convert("RGB")
            packshot = render_studio_packshot(pil_im, target_size=2400)
            packshot.save(dest_path, "JPEG", quality=95)
            return True
        except Exception:
            pass

    # Tier 4: Existing front-v2 fallback
    f2_path = FRONT_V2_DIR / f"{barcode}-front.jpg"
    if f2_path.exists():
        try:
            im = ImageOps.exif_transpose(Image.open(f2_path))
            packshot = render_studio_packshot(im, target_size=2400)
            packshot.save(dest_path, "JPEG", quality=95)
            return True
        except Exception:
            pass

    return False


if __name__ == "__main__":
    raise SystemExit("Unsafe legacy auto-healing is retired. Use scripts/reprocess_rabuta_verified.py with reviewed source polygons; front-v3 is not overwritten.")
