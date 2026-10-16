#!/usr/bin/env python3
r"""Reprocess defective front packshots directly from the 5 original photo folders.

Original folders:
1. d:\Work\shopify\source-import\G1_original
2. d:\Work\shopify\source-import\G2_original
3. d:\Work\shopify\source-import\G3_Original
4. d:\Work\shopify\source-import\G4-original
5. d:\Work\shopify\source-import\Nyt25.09.26
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
import zxingcpp

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent

ORIG_DIRS = [
    ROOT / "source-import/G1_original",
    ROOT / "source-import/G2_original",
    ROOT / "source-import/G3_Original",
    ROOT / "source-import/G4-original",
    ROOT / "source-import/Nyt25.09.26",
]

V5_DIR = ROOT / "output/catalog_pairs/tagged/front-v5"
DELIVERY_DIR = ROOT / "output/catalog_pairs/front-delivery-1169"

TARGET_CANVAS = 2400
MIN_MARGIN = 48


def build_barcode_index() -> dict[str, Path]:
    """Scan manifests and the 5 source folders to locate original photo for every barcode."""
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
                
    # Also check source map
    smap_path = ROOT / "output/catalog_pairs/front_v3_source_map.json"
    if smap_path.exists():
        try:
            with open(smap_path, "r", encoding="utf-8") as f:
                smap = json.load(f)
                for bc, info in smap.items():
                    if bc not in index:
                        for p in info.get("paths", []):
                            if Path(p).exists():
                                index[bc] = Path(p)
                                break
        except Exception:
            pass
            
    return index


def separate_front_from_original(im: Image.Image, target_bc: str) -> Image.Image:
    """Separate front face from original photo containing front & back placed side-by-side."""
    w, h = im.size
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
        return im

    chosen_hit = hits[0]
    for h_hit in hits:
        clean = "".join(c for c in str(h_hit.text or "") if c.isdigit())
        if target_bc in clean or clean in target_bc:
            chosen_hit = h_hit
            break

    pts = [(getattr(chosen_hit.position, name).x, getattr(chosen_hit.position, name).y) for name in ('top_left', 'top_right', 'bottom_right', 'bottom_left')]
    bc_x = sum(p[0] for p in pts) / 4.0 / float(curr_w)
    bc_y = sum(p[1] for p in pts) / 4.0 / float(curr_h)

    thumb = im.copy()
    thumb.thumbnail((800, 800))
    tw, th = thumb.size
    arr = np.asarray(thumb)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)

    if w >= h:
        col_proj = edges.mean(axis=0)
        col_s = np.convolve(col_proj, np.ones(15) / 15.0, mode='same')
        c_min = int(tw * 0.35) + np.argmin(col_s[int(tw * 0.35):int(tw * 0.65)])
        c_seam = c_min / float(tw)
        if bc_x < 0.50:
            crop_box = (max(0, int(min(c_seam - 0.02, 0.48) * w)), 0, w, h)
        else:
            crop_box = (0, 0, min(w, int(max(c_seam + 0.02, 0.52) * w)), h)
    else:
        if abs(bc_y - 0.50) > 0.15 and abs(bc_x - 0.50) <= 0.15:
            row_proj = edges.mean(axis=1)
            row_s = np.convolve(row_proj, np.ones(15) / 15.0, mode='same')
            r_min = int(th * 0.35) + np.argmin(row_s[int(th * 0.35):int(th * 0.65)])
            r_seam = r_min / float(th)
            if bc_y > 0.50:
                crop_box = (0, 0, w, min(h, int(max(r_seam + 0.02, 0.52) * h)))
            else:
                crop_box = (0, max(0, int(min(r_seam - 0.02, 0.48) * h)), w, h)
        else:
            col_proj = edges.mean(axis=0)
            col_s = np.convolve(col_proj, np.ones(15) / 15.0, mode='same')
            c_min = int(tw * 0.35) + np.argmin(col_s[int(tw * 0.35):int(tw * 0.65)])
            c_seam = c_min / float(tw)
            if bc_x < 0.50:
                crop_box = (max(0, int(min(c_seam - 0.02, 0.48) * w)), 0, w, h)
            else:
                crop_box = (0, 0, min(w, int(max(c_seam + 0.02, 0.52) * w)), h)

    return im.crop(crop_box)


def isolate_and_render_to_canvas(crop_im: Image.Image) -> Image.Image:
    """Extract foreground packshot with rembg and place on 2400x2400 white canvas."""
    try:
        from rembg import remove, new_session
        session = new_session("u2net")
        nobg = remove(crop_im, session=session)
        # Find alpha bounding box
        alpha = np.asarray(nobg)[:, :, 3]
        ys, xs = np.where(alpha > 20)
        if len(xs) > 100:
            crop_im = nobg.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    except Exception:
        pass
        
    rgb = crop_im.convert("RGBA")
    w, h = rgb.size
    avail = TARGET_CANVAS - 2 * MIN_MARGIN
    scale = min(avail / w, avail / h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    canvas = Image.new("RGBA", (TARGET_CANVAS, TARGET_CANVAS), (255, 255, 255, 255))
    canvas.paste(resized, ((TARGET_CANVAS - new_w) // 2, (TARGET_CANVAS - new_h) // 2), resized)
    return canvas.convert("RGB")


def reprocess_barcode_from_originals(barcode: str, index: dict[str, Path] | None = None) -> tuple[bool, str]:
    """Reprocess a single barcode from 5 original folders and save to front-v5."""
    if index is None:
        index = build_barcode_index()
        
    orig_path = index.get(barcode)
    if not orig_path or not orig_path.exists():
        return False, f"no original photo found in 5 folders for {barcode}"
        
    try:
        with Image.open(orig_path) as im:
            rgb_im = im.convert("RGB")
            front_crop = separate_front_from_original(rgb_im, barcode)
            canvas = isolate_and_render_to_canvas(front_crop)
            
            dest_v5 = V5_DIR / f"{barcode}-front.jpg"
            dest_deliv = DELIVERY_DIR / f"{barcode}-front.jpg"
            
            canvas.save(dest_v5, "JPEG", quality=95, subsampling=0)
            canvas.save(dest_deliv, "JPEG", quality=95, subsampling=0)
            return True, f"reprocessed from {orig_path.name}"
    except Exception as e:
        return False, f"reprocess error: {e}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        bc = sys.argv[1]
        success, msg = reprocess_barcode_from_originals(bc)
        print(f"Reprocess {bc}: {success} ({msg})")
