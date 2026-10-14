#!/usr/bin/env python3
"""
scripts/process_nyt_front_back_v2.py
------------------------------------
Batch processor for D:\\Work\\shopify\\source-import\\Nyt25.09.26.
Pairs and enhances front (packshot) and back (full label info) images,
matches and validates barcodes against Rabuta.12.10.2026_original.xlsx,
and writes canonical outputs to output/catalog_pairs/tagged/front-v2 and back-v2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import (
    enhance_back,
    packshot_front,
    panel_halves,
    predict_split,
    read_retail_barcodes,
    scan_file,
    split_sides,
)
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
SOURCE_DIR = ROOT / "source-import/Nyt25.09.26"
FRONT_V2_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_V2_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
FRONT_V2_DIR.mkdir(parents=True, exist_ok=True)
BACK_V2_DIR.mkdir(parents=True, exist_ok=True)

# Specification of all product packages in Nyt25.09.26
PRODUCT_SPECS = [
    # --- Split-panel files ---
    {"type": "split", "barcode": "8856001000011", "source": "5.jpg"},
    {"type": "split", "barcode": "8850813101102", "source": "6.jpg"},
    {"type": "split", "barcode": "7178600000881", "source": "8.jpg"},
    {"type": "back_only", "barcode": "4804888804998", "source": "11.jpg"},
    {"type": "split", "barcode": "8851028000631", "source": "12.jpg"},
    {"type": "split", "barcode": "8717703624632", "source": "13.jpg"},
    {"type": "pair", "barcode": "8717703638660", "front": "14.jpg", "back": "15.jpg"},
    {"type": "split", "barcode": "3700417300126", "source": "mychinh.jpg"},
    {"type": "split", "barcode": "4806011812986", "source": "super.jpg"},
    {"type": "split", "barcode": "87282504", "source": "Tofu.jpg"},
    {"type": "split", "barcode": "87282009", "source": "tofu2.jpg"},
    {"type": "split", "barcode": "8719497391554", "source": "IMG_5446.HEIC"},
    {"type": "split", "barcode": "8859448600585", "source": "IMG_5478.HEIC"},
    {"type": "split", "barcode": "8938500075018", "source": "IMG_5508.HEIC"},

    # --- Consecutive HEIC photo pairs (Front shot, Back shot) ---
    {"type": "pair", "barcode": "6925487994878", "front": "IMG_5447.HEIC", "back": "IMG_5448.HEIC"},
    {"type": "pair", "barcode": "8850369010323", "front": "IMG_5449.HEIC", "back": "IMG_5450.HEIC"},
    {"type": "pair", "barcode": "8888296019010", "front": "IMG_5451.HEIC", "back": "IMG_5452.HEIC"},
    {"type": "pair", "barcode": "8850369126017", "front": "IMG_5453.HEIC", "back": "IMG_5454.HEIC"},
    {"type": "pair", "barcode": "6901118900012", "front": "IMG_5455.HEIC", "back": "IMG_5456.HEIC"},
    {"type": "pair", "barcode": "5017689000646", "front": "IMG_5457.HEIC", "back": "IMG_5458.HEIC"},
    {"type": "pair", "barcode": "807176703779",  "front": "IMG_5459.HEIC", "back": "IMG_5460.HEIC"},
    {"type": "pair", "barcode": "4045198723191", "front": "IMG_5461.HEIC", "back": "IMG_5462.HEIC"},
    {"type": "pair", "barcode": "4710623830699", "front": "IMG_5463.HEIC", "back": "IMG_5464.HEIC"},
    {"type": "pair", "barcode": "8801073110502", "front": "IMG_5465.HEIC", "back": "IMG_5466.HEIC"},
    {"type": "pair", "barcode": "6902253886889", "front": "IMG_5467.HEIC", "back": "IMG_5470.HEIC"},
    {"type": "pair", "barcode": "5060786251343", "front": "IMG_5471.HEIC", "back": "IMG_5472.HEIC"},
    {"type": "pair", "barcode": "8801073116467", "front": "IMG_5475.HEIC", "back": "IMG_5476.HEIC"},
    {"type": "pair", "barcode": "8850100101143", "front": "IMG_5479.HEIC", "back": "IMG_5480.HEIC"},
    {"type": "pair", "barcode": "8934563138165", "front": "IMG_5481.HEIC", "back": "IMG_5482.HEIC"},
    {"type": "pair", "barcode": "8851229000799", "front": "IMG_5483.HEIC", "back": "IMG_5484.HEIC"},
    {"type": "pair", "barcode": "8850030116064", "front": "IMG_5485.HEIC", "back": "IMG_5486.HEIC"},
    {"type": "pair", "barcode": "8850030116217", "front": "IMG_5487.HEIC", "back": "IMG_5488.HEIC"},
    {"type": "pair", "barcode": "8850030030339", "front": "IMG_5489.HEIC", "back": "IMG_5490.HEIC"},
    {"type": "pair", "barcode": "8850030110765", "front": "IMG_5491.HEIC", "back": "IMG_5492.HEIC"},
    {"type": "pair", "barcode": "6922130121452", "front": "IMG_5493.HEIC", "back": "IMG_5494.HEIC"},
    {"type": "pair", "barcode": "6921379720037", "front": "IMG_5495.HEIC", "back": "IMG_5496.HEIC"},
    {"type": "pair", "barcode": "4804888804011", "front": "IMG_5497.HEIC", "back": "IMG_5498.HEIC"},
    {"type": "pair", "barcode": "8801073116474", "front": "IMG_5499.HEIC", "back": "IMG_5500.HEIC"},
    {"type": "pair", "barcode": "087703007796",  "front": "IMG_5501.HEIC", "back": "IMG_5502.HEIC"},
    {"type": "pair", "barcode": "4045198753136", "front": "IMG_5504.HEIC", "back": "IMG_5503.HEIC"},
    {"type": "pair", "barcode": "8858652600084", "front": "IMG_5505.HEIC", "back": "IMG_5506.HEIC"},
    {"type": "pair", "barcode": "8851683001608", "front": "IMG_5509.HEIC", "back": "IMG_5510.HEIC"},
    {"type": "pair", "barcode": "6920202900660", "front": "IMG_5511.HEIC", "back": "IMG_5512.HEIC"},
    {"type": "pair", "barcode": "8717624008269", "front": "IMG_5513.HEIC", "back": "IMG_5514.HEIC"},
    {"type": "pair", "barcode": "6972007904381", "front": "IMG_5515.HEIC", "back": "IMG_5516.HEIC"},
    {"type": "pair", "barcode": "8436566460033", "front": "IMG_5517.HEIC", "back": "IMG_5518.HEIC"},
    {"type": "pair", "barcode": "6954132815688", "front": "IMG_5520.HEIC", "back": "IMG_5519.HEIC"},
    {"type": "pair", "barcode": "4316734081878", "front": "IMG_5521.HEIC", "back": "IMG_5522.HEIC"},
    {"type": "pair", "barcode": "6974510151993", "front": "IMG_5523.HEIC", "back": "IMG_5524.HEIC"},
    {"type": "pair", "barcode": "6925487992379", "front": "IMG_5525.HEIC", "back": "IMG_5526.HEIC"},
    {"type": "pair", "barcode": "6927992589037", "front": "IMG_5527.HEIC", "back": "IMG_5528.HEIC"},
    {"type": "pair", "barcode": "8850157405843", "front": "IMG_5529.HEIC", "back": "IMG_5530.HEIC"},
    {"type": "pair", "barcode": "8850157405836", "front": "IMG_5531.HEIC", "back": "IMG_5532.HEIC"},
    {"type": "pair", "barcode": "8850157405829", "front": "IMG_5533.HEIC", "back": "IMG_5534.HEIC"},
    {"type": "pair", "barcode": "6972007904237", "front": "IMG_5535.HEIC", "back": "IMG_5536.HEIC"},
    {"type": "pair", "barcode": "6972007903605", "front": "IMG_5541.HEIC", "back": "IMG_5542.HEIC"},
    {"type": "pair", "barcode": "8936082240046", "front": "IMG_5543.HEIC", "back": "IMG_5544.HEIC"},
    {"type": "pair", "barcode": "8852646086809", "front": "IMG_5545.HEIC", "back": "IMG_5546.HEIC"},
    {"type": "pair", "barcode": "5011308306263", "front": "IMG_5547.HEIC", "back": "IMG_5548.HEIC"},
    {"type": "pair", "barcode": "5011308306362", "front": "IMG_5549.HEIC", "back": "IMG_5550.HEIC"},
    {"type": "pair", "barcode": "8850025001023", "front": "IMG_5551.HEIC", "back": "IMG_5552.HEIC"},
    {"type": "pair", "barcode": "8809705070521", "front": "IMG_5553.HEIC", "back": "IMG_5554.HEIC"},
    {"type": "pair", "barcode": "4260243040546", "front": "IMG_5555.HEIC", "back": "IMG_5556.HEIC"},
    {"type": "pair", "barcode": "5700002202017", "front": "IMG_5557.HEIC", "back": "IMG_5558.HEIC"},
]


def process_split_item(spec: dict, barcode: str, front_dir: Path, back_dir: Path) -> dict:
    source_path = SOURCE_DIR / spec["source"]
    record = scan_file(source_path, {barcode})
    center_x = float(record.get("center", [0, 0])[0])
    center_y = float(record.get("center", [0, 0])[1])
    
    image = open_image_safely(source_path)
    sides = split_sides(image, center_x, center_y, 0)
    
    back_crop = image.crop(sides.back)
    back = enhance_back(back_crop)
    back_dest = back_dir / f"{barcode}-back.jpg"
    save_image_high_quality(back, back_dest, quality=94, save_webp=False)
    
    front_dest = ""
    front_ok = False
    if sides.front is not None:
        front_crop = image.crop(sides.front)
        front = packshot_front(front_crop)
        dest = front_dir / f"{barcode}-front.jpg"
        save_image_high_quality(front, dest, quality=95, save_webp=False)
        front_dest = str(dest)
        front_ok = True
    image.close()
    
    return {
        "barcode": barcode,
        "type": "split",
        "source": spec["source"],
        "front_ok": front_ok,
        "back_ok": True,
        "front_file": front_dest,
        "back_file": str(back_dest),
    }


def process_pair_item(spec: dict, barcode: str, front_dir: Path, back_dir: Path) -> dict:
    front_path = SOURCE_DIR / spec["front"]
    back_path = SOURCE_DIR / spec["back"]
    
    # Process front with packshot
    img_f = open_image_safely(front_path)
    front = packshot_front(img_f)
    front_dest = front_dir / f"{barcode}-front.jpg"
    save_image_high_quality(front, front_dest, quality=95, save_webp=False)
    img_f.close()
    
    # Process back with enhance_back
    img_b = open_image_safely(back_path)
    back = enhance_back(img_b)
    back_dest = back_dir / f"{barcode}-back.jpg"
    save_image_high_quality(back, back_dest, quality=94, save_webp=False)
    img_b.close()
    
    return {
        "barcode": barcode,
        "type": "pair",
        "front_source": spec["front"],
        "back_source": spec["back"],
        "front_ok": True,
        "back_ok": True,
        "front_file": str(front_dest),
        "back_file": str(back_dest),
    }


def process_back_only_item(spec: dict, barcode: str, back_dir: Path) -> dict:
    source_path = SOURCE_DIR / spec["source"]
    img = open_image_safely(source_path)
    back = enhance_back(img)
    back_dest = back_dir / f"{barcode}-back.jpg"
    save_image_high_quality(back, back_dest, quality=94, save_webp=False)
    img.close()
    
    return {
        "barcode": barcode,
        "type": "back_only",
        "source": spec["source"],
        "front_ok": False,
        "back_ok": True,
        "front_file": "",
        "back_file": str(back_dest),
    }


def main():
    print("===============================================================================")
    print("      PROCESSING Nyt25.09.26 DATASET (FRONT-V2 & BACK-V2 ENHANCEMENT)         ")
    print("===============================================================================\n")

    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    product_map = {p["barcode"]: p for p in products}
    print(f"Loaded {len(products)} products from customer Excel.")

    manifest = {}
    both_count = 0
    back_only_count = 0

    total_specs = len(PRODUCT_SPECS)
    for i, spec in enumerate(PRODUCT_SPECS, start=1):
        raw_bc = spec["barcode"]
        excel_bc = lookup.get(raw_bc)
        if not excel_bc:
            for v in get_barcode_lookup_variants(raw_bc):
                if v in lookup:
                    excel_bc = lookup[v]
                    break
        if not excel_bc:
            excel_bc = raw_bc

        prod = product_map.get(excel_bc, {})
        name_en = prod.get("name_en", "")

        print(f"[{i:2d}/{total_specs}] Processing barcode: {excel_bc} ({name_en[:30]})...", flush=True)

        item_type = spec["type"]
        if item_type == "pair":
            res = process_pair_item(spec, excel_bc, FRONT_V2_DIR, BACK_V2_DIR)
        elif item_type == "split":
            res = process_split_item(spec, excel_bc, FRONT_V2_DIR, BACK_V2_DIR)
        elif item_type == "back_only":
            res = process_back_only_item(spec, excel_bc, BACK_V2_DIR)
        else:
            raise ValueError(f"Unknown item type: {item_type}")

        res["name_en"] = name_en
        res["brand"] = prod.get("brand", "")
        manifest[excel_bc] = res

        if res["front_ok"] and res["back_ok"]:
            both_count += 1
            print(f"       -> BOTH OK: front & back generated.", flush=True)
        elif res["back_ok"]:
            back_only_count += 1
            print(f"       -> BACK ONLY generated.", flush=True)

    manifest_path = ROOT / "output/catalog_pairs/manifest_Nyt25.09.26_v2.json"
    report = {
        "source": str(SOURCE_DIR),
        "total_products_processed": len(manifest),
        "both_sides": both_count,
        "back_only": back_only_count,
        "front_dir": str(FRONT_V2_DIR),
        "back_dir": str(BACK_V2_DIR),
        "products": manifest,
    }
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n-------------------------------------------------------------------------------")
    print(f"DONE PROCESSING Nyt25.09.26!")
    print(f"Total products: {len(manifest)}")
    print(f"Both front & back: {both_count}")
    print(f"Back only: {back_only_count}")
    print(f"Manifest written to: {manifest_path}")
    print("-------------------------------------------------------------------------------")


if __name__ == "__main__":
    main()
