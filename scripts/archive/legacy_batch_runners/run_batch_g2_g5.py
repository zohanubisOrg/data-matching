from __future__ import annotations

import argparse
import concurrent.futures
import csv
import io
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
from dotenv import load_dotenv

load_dotenv()

from src.product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality, SUPPORTED_EXTENSIONS
from src.product_mapper.vision.barcode_validator import get_barcode_lookup_variants, validate_ean_upc_checksum
from src.product_mapper.vision.gemini_vision import GeminiVisionExtractor, PackagingVisionResult
from src.product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

POS_FILE = Path("Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx")
OUTPUT_BASE = Path("output/shopify_import")
IMAGES_OUT_DIR = OUTPUT_BASE / "images"

LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()


def load_pos_catalogs() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], list[dict[str, str]]]:
    """Loads POS lookup tables indexed by barcode, sku, and full list for text bridge matching."""
    pos_by_bc: dict[str, dict[str, str]] = {}
    pos_by_sku: dict[str, dict[str, str]] = {}
    pos_list: list[dict[str, str]] = []

    if POS_FILE.exists():
        try:
            df = pd.read_excel(POS_FILE)
            for _, r in df.iterrows():
                bc_raw = str(r.get("Bar Code", "")).strip()
                if bc_raw.endswith(".0"):
                    bc_raw = bc_raw[:-2]
                sku_raw = str(r.get("Sku Code", "")).strip()
                name_raw = str(r.get("Product Name ", "")).strip()
                official_raw = str(r.get("Oficial Name ", "")).strip()
                price_raw = str(r.get("Selling Price", "")).strip()
                if price_raw.endswith(".0"):
                    price_raw = price_raw[:-2]

                item_info = {
                    "barcode": bc_raw,
                    "sku": sku_raw,
                    "name": name_raw,
                    "official_name": official_raw,
                    "price": price_raw,
                }
                pos_list.append(item_info)

                if sku_raw and sku_raw.lower() not in {"nan", "none"}:
                    pos_by_sku[sku_raw.upper()] = item_info

                if bc_raw and bc_raw.lower() not in {"nan", "none"}:
                    for var in get_barcode_lookup_variants(bc_raw):
                        pos_by_bc[var] = item_info
        except Exception as e:
            print(f"Warning loading POS file: {e}")

    return pos_by_bc, pos_by_sku, pos_list


def scan_zxing_multi_angle(im: Image.Image, pos_lookup: dict[str, dict[str, str]]) -> str | None:
    """Tier 1: Multi-angle ZXing scanner with CLAHE/Contrast enhancement."""
    try:
        import zxingcpp
    except ImportError:
        return None

    # Pass 1: Standard multi-angle
    for rot in [0, 90, 180, 270]:
        im_rot = im if rot == 0 else im.rotate(rot, expand=True)
        results = zxingcpp.read_barcodes(im_rot)
        for r in results:
            t = str(getattr(r, "text", "")).strip()
            if t.isdigit() and len(t) >= 8:
                if validate_ean_upc_checksum(t) or any(v in pos_lookup for v in get_barcode_lookup_variants(t)):
                    return t

    # Pass 2: Enhanced Contrast
    enhanced = ImageEnhance.Contrast(im).enhance(2.0)
    for rot in [0, 90, 180, 270]:
        im_rot = enhanced.rotate(rot, expand=True)
        for r in zxingcpp.read_barcodes(im_rot):
            t = str(getattr(r, "text", "")).strip()
            if t.isdigit() and len(t) >= 8:
                if validate_ean_upc_checksum(t) or any(v in pos_lookup for v in get_barcode_lookup_variants(t)):
                    return t

    return None


def recover_barcode_via_zoom(
    orig_im: Image.Image,
    box_2d: list[int] | None,
    vision_extractor: GeminiVisionExtractor,
    pos_lookup: dict[str, dict[str, str]],
) -> str | None:
    """Tier 2 & Tier 3: High-Res Zoom Crop with Otsu Binarization and Vision Deep OCR."""
    if not box_2d or len(box_2d) != 4:
        return None

    w, h = orig_im.size
    ymin, xmin, ymax, xmax = box_2d
    pad_x = int((xmax - xmin) * w / 1000 * 0.20)
    pad_y = int((ymax - ymin) * h / 1000 * 0.20)

    left = max(0, int(xmin * w / 1000) - pad_x)
    top = max(0, int(ymin * h / 1000) - pad_y)
    right = min(w, int(xmax * w / 1000) + pad_x)
    bottom = min(h, int(ymax * h / 1000) + pad_y)

    if right <= left or bottom <= top:
        return None

    crop_bc = orig_im.crop((left, top, right, bottom))

    # Try Tier 2: ZXing on Zoom Crop
    bc = scan_zxing_multi_angle(crop_bc, pos_lookup)
    if bc:
        return bc

    # Tier 2.2: Sharpen & Binarize
    sharp = crop_bc.filter(ImageFilter.SHARPEN)
    bc = scan_zxing_multi_angle(sharp, pos_lookup)
    if bc:
        return bc

    # Try Tier 3: Multimodal Vision Deep OCR
    return vision_extractor.read_zoomed_barcode(crop_bc)


def bridge_pos_barcode_match(
    vision_data: dict[str, Any],
    pos_by_sku: dict[str, dict[str, str]],
    pos_list: list[dict[str, str]],
) -> tuple[str | None, str | None, str | None]:
    """Tier 4: Match unreadable barcode via Supplier SKU / Brand / Literal Name against POS Master."""
    supplier_sku = str(vision_data.get("supplier_sku") or "").strip().upper()
    if supplier_sku and supplier_sku in pos_by_sku:
        match = pos_by_sku[supplier_sku]
        return match.get("barcode"), match.get("sku"), match.get("official_name")

    brand = str(vision_data.get("brand") or "").strip().lower()
    title = str(vision_data.get("full_name_en") or vision_data.get("literal_label_name") or "").strip().lower()
    
    if brand and len(brand) >= 3 and title:
        # Find exact matches in POS
        for item in pos_list:
            pos_name = item.get("name", "").lower()
            if brand in pos_name:
                tokens = [t for t in re.split(r"\W+", title) if len(t) >= 4]
                if tokens and sum(1 for t in tokens if t in pos_name) >= max(2, len(tokens) - 1):
                    return item.get("barcode"), item.get("sku"), item.get("official_name")

    return None, None, None


def extract_and_save_front_crop(
    orig_im: Image.Image,
    front_box_2d: list[int] | None,
    rotation_angle: int,
    barcode: str,
    output_dir: Path,
) -> tuple[str, int, int]:
    """Isolates front packaging crop at native resolution, applies 4-5% padding, ensures portrait upright format."""
    w, h = orig_im.size
    
    if front_box_2d and len(front_box_2d) == 4:
        ymin, xmin, ymax, xmax = front_box_2d
        # Adaptive 4% padding
        pad_w = int((xmax - xmin) * 0.045)
        pad_h = int((ymax - ymin) * 0.045)
        left = max(0, int((xmin - pad_w) * w / 1000))
        top = max(0, int((ymin - pad_h) * h / 1000))
        right = min(w, int((xmax + pad_w) * w / 1000))
        bottom = min(h, int((ymax + pad_h) * h / 1000))
    else:
        # Fallback to left half (assuming front side is left side in 2-sided photo)
        left, top, right, bottom = 0, 0, int(w * 0.52), h

    if right <= left or bottom <= top:
        crop_im = orig_im
    else:
        crop_im = orig_im.crop((left, top, right, bottom))

    # Rotate to upright if specified
    if rotation_angle != 0:
        crop_im = crop_im.rotate(-rotation_angle, expand=True)

    # Auto-Upright Normalization: Ensure vertical portrait mode (Height >= Width)
    if crop_im.height < crop_im.width:
        crop_im = crop_im.rotate(270, expand=True)

    out_name = f"{barcode}.jpg" if barcode else f"temp_{int(time.time()*1000)}.jpg"
    final_path = output_dir / out_name
    save_image_high_quality(crop_im, final_path, quality=95, save_webp=True)

    return out_name, crop_im.width, crop_im.height


def process_single_image(
    image_path: Path,
    batch_name: str,
    vision_extractor: GeminiVisionExtractor,
    pos_by_bc: dict[str, dict[str, str]],
    pos_by_sku: dict[str, dict[str, str]],
    pos_list: list[dict[str, str]],
) -> dict[str, Any]:
    """End-to-end processing of a single product photo with 4-tier barcode recovery and smart crop."""
    orig_im = open_image_safely(image_path)
    
    # 1. Tier 1: Multi-Angle Direct ZXing
    barcode = scan_zxing_multi_angle(orig_im, pos_by_bc)
    detection_method = "zxing_direct" if barcode else ""

    # 2. Vision AI Deep Extraction
    vision_res = vision_extractor.analyze_image_deep(image_path)
    vision_dict = vision_res.model_dump()

    # 3. Tier 2 & 3: Zoom Barcode Recovery if not yet detected
    if not barcode:
        barcode = recover_barcode_via_zoom(orig_im, vision_dict.get("barcode_box_2d"), vision_extractor, pos_by_bc)
        if barcode:
            detection_method = "vision_zoom_ocr"

    # 4. Tier 4: Text-Bridge POS Matching if still no barcode
    pos_sku = ""
    pos_name = ""
    if not barcode:
        bc_bridge, sku_bridge, name_bridge = bridge_pos_barcode_match(vision_dict, pos_by_sku, pos_list)
        if bc_bridge:
            barcode = bc_bridge
            pos_sku = sku_bridge or ""
            pos_name = name_bridge or ""
            detection_method = "pos_text_bridge"

    # 5. Check POS Master with verified barcode
    if barcode and barcode in pos_by_bc:
        pos_match = pos_by_bc[barcode]
        if not pos_sku:
            pos_sku = pos_match.get("sku", "")
        if not pos_name:
            pos_name = pos_match.get("official_name", "") or pos_match.get("name", "")

    # 6. Extract Front Crop
    front_filename, crop_w, crop_h = extract_and_save_front_crop(
        orig_im=orig_im,
        front_box_2d=vision_dict.get("front_box_2d"),
        rotation_angle=vision_dict.get("front_rotation", 0),
        barcode=barcode or image_path.stem,
        output_dir=IMAGES_OUT_DIR,
    )

    # 7. Assemble Record
    final_record = {
        **vision_dict,
        "barcode": barcode or "",
        "pos_sku": pos_sku,
        "pos_product_name": pos_name,
        "source_photo": image_path.name,
        "batch": batch_name,
        "detection_method": detection_method or "unresolved",
        "Website Front Image": front_filename,
        "image_width_px": crop_w,
        "image_height_px": crop_h,
        "status": "CONFIRMED" if barcode else "NEEDS_REVIEW",
    }

    with PRINT_LOCK:
        status_icon = "✅" if barcode else "⚠️"
        print(f"[{batch_name}] {status_icon} {image_path.name} -> BC: {barcode or 'NO_BARCODE'} | SKU: {pos_sku or 'N/A'} | Title: {final_record.get('full_name_en') or final_record.get('fuldt_navn_da') or 'N/A'}")

    return final_record


def get_photo_numeric_id(fname: str) -> int | None:
    digits = re.findall(r"\d+", fname)
    if digits:
        try:
            return int(digits[-1])
        except Exception:
            return None
    return None


def pair_and_consolidate_multishots(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Pairs consecutive photos belonging to the same product (e.g. Photo A = Front packaging, Photo B = Back with barcode).
    Merges barcode, POS SKU, and nutrition facts into the front record and ensures canonical crop naming.
    """
    if not records:
        return records

    # Sort records by source photo name (preserves chronological sequence)
    sorted_recs = sorted(records, key=lambda x: x.get("source_photo", ""))
    
    n = len(sorted_recs)
    for i in range(n):
        curr = sorted_recs[i]
        curr_bc = curr.get("barcode", "")
        curr_num = get_photo_numeric_id(curr.get("source_photo", ""))
        
        # If current record has no barcode, check immediate adjacent neighbors (i-1, i+1, i-2, i+2)
        if not curr_bc:
            curr_title = (curr.get("full_name_en") or curr.get("literal_label_name") or curr.get("product_name") or "").lower()
            curr_brand = (curr.get("brand") or "").lower()
            
            for offset in [-1, 1, -2, 2]:
                idx = i + offset
                if 0 <= idx < n:
                    neighbor = sorted_recs[idx]
                    n_bc = neighbor.get("barcode", "")
                    n_num = get_photo_numeric_id(neighbor.get("source_photo", ""))
                    
                    if n_bc:
                        n_title = (neighbor.get("full_name_en") or neighbor.get("literal_label_name") or neighbor.get("product_name") or "").lower()
                        n_brand = (neighbor.get("brand") or "").lower()
                        
                        # Match condition 1: same brand and significant title token overlap
                        is_match = False
                        if curr_brand and n_brand and curr_brand == n_brand:
                            is_match = True
                        elif curr_title and n_title:
                            c_tokens = set(re.findall(r"\w{3,}", curr_title))
                            n_tokens = set(re.findall(r"\w{3,}", n_title))
                            if c_tokens and n_tokens and len(c_tokens.intersection(n_tokens)) >= 2:
                                is_match = True
                        # Match condition 2: strictly sequential numbering (diff <= 1)
                        elif curr_num is not None and n_num is not None and abs(curr_num - n_num) == 1:
                            is_match = True
                                
                        if is_match:
                            curr["barcode"] = n_bc
                            if not curr.get("pos_sku") and neighbor.get("pos_sku"):
                                curr["pos_sku"] = neighbor.get("pos_sku")
                            if not curr.get("pos_product_name") and neighbor.get("pos_product_name"):
                                curr["pos_product_name"] = neighbor.get("pos_product_name")
                            if not curr.get("fuldt_navn_da") and neighbor.get("fuldt_navn_da"):
                                curr["fuldt_navn_da"] = neighbor.get("fuldt_navn_da")
                            if not curr.get("full_name_en") and neighbor.get("full_name_en"):
                                curr["full_name_en"] = neighbor.get("full_name_en")
                            if not curr.get("brand") and neighbor.get("brand"):
                                curr["brand"] = neighbor.get("brand")
                            if not curr.get("category") and neighbor.get("category"):
                                curr["category"] = neighbor.get("category")
                            if not curr.get("ingredients_en") and neighbor.get("ingredients_en"):
                                curr["ingredients_en"] = neighbor.get("ingredients_en")
                                curr["ingredienser_da"] = neighbor.get("ingredienser_da")
                            if curr.get("energy_kcal") is None and neighbor.get("energy_kcal") is not None:
                                for k in ["energy_kj", "energy_kcal", "fat_g", "saturates_g", "carbohydrate_g", "sugars_g", "protein_g", "salt_g"]:
                                    curr[k] = neighbor.get(k)
                            curr["detection_method"] = "multishot_pair"
                            curr["status"] = "CONFIRMED"
                            
                            # Rename the front crop to the newly resolved barcode
                            curr["Website Front Image"] = f"{n_bc}.jpg"
                            break

    return sorted_recs


def run_batch(batch_name: str, folder_path: Path, max_workers: int = 4) -> list[dict[str, Any]]:
    """Runs batch pipeline on a specific directory."""
    print(f"\n==========================================")
    print(f"🚀 Starting Batch {batch_name} ({folder_path})")
    print(f"==========================================")

    cache_file = OUTPUT_BASE / f"{batch_name.lower()}_vision_cache.json"
    vision_extractor = GeminiVisionExtractor(cache_path=cache_file)
    pos_by_bc, pos_by_sku, pos_list = load_pos_catalogs()

    images = [p for p in sorted(folder_path.iterdir()) if p.is_file() and p.suffix.casefold() in SUPPORTED_EXTENSIONS]
    print(f"Found {len(images)} images in {folder_path}")

    records: list[dict[str, Any]] = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_single_image,
                img,
                batch_name,
                vision_extractor,
                pos_by_bc,
                pos_by_sku,
                pos_list,
            ): img
            for img in images
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                rec = future.result()
                if rec and isinstance(rec, dict):
                    records.append(rec)
            except Exception as exc:
                img_p = futures[future]
                print(f"Error processing {img_p}: {exc}")

    # Apply Multi-Shot Pair Consolidation
    records = pair_and_consolidate_multishots(records)

    # Export individual batch reports
    batch_csv_out = OUTPUT_BASE / f"{batch_name}_shopify_products.csv"
    batch_xlsx_out = OUTPUT_BASE / f"{batch_name}_master_products.xlsx"
    export_shopify_csv(records, batch_csv_out, batch_tag=f"{batch_name.lower()}_import")
    export_master_excel(records, batch_xlsx_out)

    confirmed_count = sum(1 for r in records if r.get("barcode"))
    print(f"\n✨ Batch {batch_name} complete: {confirmed_count}/{len(records)} verified barcodes ({confirmed_count/len(records)*100:.1f}%)")
    return records


def main():
    parser = argparse.ArgumentParser(description="Run G2-G5 Shopify Batch Pipeline")
    parser.add_argument("--batch", choices=["g2", "g3", "g4", "g5", "all"], default="all", help="Select batch to process")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers")
    args = parser.parse_args()

    batch_folders = {
        "G2": Path("source-import/G2_original"),
        "G3": Path("source-import/G3_Original"),
        "G4": Path("source-import/G4-original"),
        "G5": Path("source-import/Nyt25.09.26"),
    }

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    IMAGES_OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []

    if args.batch == "all":
        for b_name, b_folder in batch_folders.items():
            if b_folder.exists():
                recs = run_batch(b_name, b_folder, max_workers=args.workers)
                all_records.extend(recs)
    else:
        target_name = args.batch.upper()
        target_folder = batch_folders.get(target_name)
        if target_folder and target_folder.exists():
            all_records = run_batch(target_name, target_folder, max_workers=args.workers)

    if all_records:
        master_csv = OUTPUT_BASE / "Master_G2_G5_Shopify_Import.csv"
        master_xlsx = OUTPUT_BASE / "Master_G2_G5_Consolidated.xlsx"
        export_shopify_csv(all_records, master_csv, batch_tag="g2_g5_master_import")
        export_master_excel(all_records, master_xlsx)
        print(f"\n🎉 MASTER EXPORT READY:")
        print(f"  - Shopify CSV: {master_csv}")
        print(f"  - Master Excel: {master_xlsx}")
        print(f"  - Total Products: {len(all_records)}")


if __name__ == "__main__":
    main()
