#!/usr/bin/env python3
"""
scripts/audit_front_v3_hardened.py
----------------------------------
Fast Deep Vision Audit across all 1,169 packshots in output/catalog_pairs/tagged/front-v3/
Checks:
1. Canvas size: 2400x2400.
2. Guillotine Cuts: Flat cut lines across top (>50%), sides (>45%), or bottom (>65%).
3. Narrow Slivers: Aspect ratio < 0.20 or > 5.0.
4. Cardboard Leak: Kraft paper / table brown pixels remaining on canvas.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
import numpy as np
from PIL import Image

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v3"


def audit_packshot(path: Path) -> dict[str, Any]:
    with Image.open(path) as im:
        w, h = im.size
        
        res = {
            "barcode": path.stem.replace("-front", "").replace("_front", ""),
            "size": f"{w}x{h}",
            "guillotine": False,
            "sliver": False,
            "cardboard": False,
            "defects": [],
        }
        
        if w != 2400 or h != 2400:
            res["defects"].append(f"Invalid dimensions: {w}x{h}")
            
        # Fast downscale to 600x600 for instant geometric inspection
        thumb = im.copy()
        thumb.thumbnail((600, 600), Image.Resampling.BILINEAR)

    arr = np.asarray(thumb.convert("RGB"))
    diff = np.abs(arr.astype(int) - 255).sum(axis=2)
    fg = diff > 20
    ys, xs = np.where(fg)
    
    if len(xs) == 0:
        res["defects"].append("Completely blank canvas")
        return res
        
    bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    pw, ph = bx1 - bx0, by1 - by0
    
    # 1. Aspect ratio sliver check
    aspect = pw / max(1, ph)
    if aspect < 0.20 or aspect > 5.0:
        res["sliver"] = True
        res["defects"].append(f"Sliver aspect ratio: {aspect:.2f} ({pw}x{ph})")
        
    # 2. Border flat edge check
    crop_fg = fg[by0:by1, bx0:bx1]
    top_fill = crop_fg[:3, :].mean(axis=1).max()
    bottom_fill = crop_fg[-3:, :].mean(axis=1).max()
    left_fill = crop_fg[:, :3].mean(axis=0).max()
    right_fill = crop_fg[:, -3:].mean(axis=0).max()
    
    if top_fill > 0.50:
        res["guillotine"] = True
        res["defects"].append(f"Top guillotine cut: {top_fill:.2f}")
    if bottom_fill > 0.65:
        res["guillotine"] = True
        res["defects"].append(f"Bottom guillotine cut: {bottom_fill:.2f}")
    if left_fill > 0.45:
        res["guillotine"] = True
        res["defects"].append(f"Left guillotine cut: {left_fill:.2f}")
    if right_fill > 0.45:
        res["guillotine"] = True
        res["defects"].append(f"Right guillotine cut: {right_fill:.2f}")
        
    # 3. Cardboard background leak check
    r = arr[by0:by1, bx0:bx1, 0]
    g = arr[by0:by1, bx0:bx1, 1]
    b = arr[by0:by1, bx0:bx1, 2]
    is_c = (r > 130) & (g >= 90) & (g <= 195) & (b >= 50) & (b <= 160) & (r >= g) & (g >= b) & ((r.astype(int) - b.astype(int)) >= 15)
    
    outer_mask = np.zeros_like(is_c, dtype=bool)
    pad_y = max(3, int(ph * 0.10))
    pad_x = max(3, int(pw * 0.10))
    outer_mask[:pad_y, :] = True
    outer_mask[-pad_y:, :] = True
    outer_mask[:, :pad_x] = True
    outer_mask[:, -pad_x:] = True
    
    cardboard_leak_count = np.sum(is_c & crop_fg & outer_mask)
    if cardboard_leak_count > (pw * ph * 0.08):
        res["cardboard"] = True
        res["defects"].append(f"Cardboard paper leak: {cardboard_leak_count} pixels")
        
    return res


if __name__ == "__main__":
    files = sorted(list(FRONT_DIR.glob("*-front.jpg")))
    print(f"Auditing all {len(files)} packshots in {FRONT_DIR}...", flush=True)
    
    guillotine_count = 0
    sliver_count = 0
    cardboard_count = 0
    defect_list = []
    
    for i, f in enumerate(files):
        info = audit_packshot(f)
        if info["guillotine"]:
            guillotine_count += 1
        if info["sliver"]:
            sliver_count += 1
        if info["cardboard"]:
            cardboard_count += 1
        if info["defects"]:
            defect_list.append((f.name, info["defects"]))
        if (i + 1) % 200 == 0:
            print(f"  Scanned: {i + 1}/{len(files)}...", flush=True)
            
    print("\n===============================================================================", flush=True)
    print("                      KẾT QUẢ DEEP VISION AUDIT FRONT-V3                       ", flush=True)
    print("===============================================================================", flush=True)
    print(f"  * Tổng số ảnh quét           : {len(files)}", flush=True)
    print(f"  * Số ảnh lỗi guillotine cắt ngang/dọc : {guillotine_count}", flush=True)
    print(f"  * Số ảnh lỗi cắt thành lát mỏng (sliver) : {sliver_count}", flush=True)
    print(f"  * Số ảnh lỗi dính nền bìa carton      : {cardboard_count}", flush=True)
    print(f"  * Tổng số ảnh phát hiện lỗi           : {len(defect_list)}", flush=True)
    print("===============================================================================\n", flush=True)
    
    if defect_list:
        print("Chi tiết các lỗi phát hiện:")
        for name, errs in defect_list[:20]:
            print(f"  - {name}: {', '.join(errs)}", flush=True)
