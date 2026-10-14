"""Prepares and web-optimizes product assets from output/g1_delivery into web/public/
for instant Vercel deployment and high-speed client viewing.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from PIL import Image, ImageOps

def optimize_image(
    src_path: Path,
    dest_path: Path,
    max_dimension: int = 750,
    quality: int = 82,
    force_portrait: bool = False,
    orig_path: Path | None = None,
    overwrite: bool = True
) -> bool:
    if dest_path.exists() and not overwrite:
        return False
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src_path) as im:
            im = im.convert("RGB")
            
            # Smart portrait auto-orientation for front product shots
            if force_portrait and im.width > im.height:
                orient = 1
                if orig_path and orig_path.exists():
                    try:
                        with Image.open(orig_path) as o_im:
                            orient = o_im.getexif().get(274, 1)
                    except Exception:
                        pass
                
                if orient == 8:
                    im = im.transpose(Image.Transpose.ROTATE_90)
                else:
                    im = im.transpose(Image.Transpose.ROTATE_270)
            
            w, h = im.size
            if max(w, h) > max_dimension:
                scale = max_dimension / max(w, h)
                im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            im.save(dest_path, format="WEBP", quality=quality, method=4)
        return True
    except Exception as e:
        print(f"Error optimizing {src_path.name}: {e}")
        return False

def sync_web_assets(
    root_dir: Path = Path("."),
    delivery_dir: Path = Path("output/g1_delivery"),
    web_dir: Path = Path("web"),
) -> dict:
    json_path = delivery_dir / "G1_products.json"
    if not json_path.exists():
        print(f"File {json_path} does not exist yet.")
        return {}

    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    public_dir = web_dir / "public"
    front_dest_dir = public_dir / "products" / "front"
    raw_dest_dir = public_dir / "products" / "raw"
    data_dest_dir = public_dir / "data"

    front_dest_dir.mkdir(parents=True, exist_ok=True)
    raw_dest_dir.mkdir(parents=True, exist_ok=True)
    data_dest_dir.mkdir(parents=True, exist_ok=True)

    web_products = []
    converted_front = 0
    converted_raw = 0

    print(f"Syncing {len(products)} products to web/public...")

    for p in products:
        barcode = p.get("barcode", "")
        raw_fname = p.get("original_image", "")
        web_front_src = delivery_dir / p.get("website_front_image", "")
        raw_src = root_dir / "G1_original" / raw_fname

        front_slug = f"{barcode}.webp"
        raw_slug = f"{Path(raw_fname).stem}.webp"

        front_target = front_dest_dir / front_slug
        raw_target = raw_dest_dir / raw_slug

        # 1. Optimize front cropped image with smart portrait orientation
        if web_front_src.exists():
            if optimize_image(web_front_src, front_target, max_dimension=800, quality=88, force_portrait=True, orig_path=raw_src):
                converted_front += 1
            front_web_url = f"/products/front/{front_slug}"
        else:
            front_web_url = ""

        # 2. Optimize raw packaging photo (for side-by-side comparison modal)
        if raw_src.exists():
            if optimize_image(raw_src, raw_target, max_dimension=600, quality=78, force_portrait=False):
                converted_raw += 1
            raw_web_url = f"/products/raw/{raw_slug}"
        else:
            raw_web_url = ""

        p_web = dict(p)
        p_web["front_web_url"] = front_web_url
        p_web["raw_web_url"] = raw_web_url
        web_products.append(p_web)

    # Compute stats
    total = len(web_products)
    confirmed = sum(1 for p in web_products if p.get("status") == "CONFIRMED")
    pos_matched = sum(1 for p in web_products if p.get("pos_sku"))
    review_needed = total - confirmed
    brands = sorted(list(set(p.get("brand") for p in web_products if p.get("brand"))))

    payload = {
        "stats": {
            "total": total,
            "confirmed": confirmed,
            "pos_matched": pos_matched,
            "review_needed": review_needed,
            "brands_count": len(brands),
        },
        "brands": brands,
        "products": web_products,
    }

    out_file = data_dest_dir / "products.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Sync complete:")
    print(f"  Total items: {total}")
    print(f"  Converted front images: {converted_front}")
    print(f"  Converted raw images: {converted_raw}")
    print(f"  Output saved to: {out_file}")
    return payload

if __name__ == "__main__":
    sync_web_assets()
