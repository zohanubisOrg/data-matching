import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

OUTPUT_DIR = Path("output/shopify_import")
WEB_FRONT_DIR = OUTPUT_DIR / "web_front_images"
IMAGES_DIR = OUTPUT_DIR / "images"

def main():
    print("Finalizing all clean record IDs and Shopify outputs...")
    master_xlsx = OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx"
    df = pd.read_excel(master_xlsx)
    records = df.to_dict(orient="records")

    batch_counters: dict[str, int] = {}
    updated_records = []
    batch_records_map: dict[str, list[dict[str, Any]]] = {}

    for idx, rec in enumerate(records):
        batch = str(rec.get("batch") or "G2").strip()
        batch_counters[batch] = batch_counters.get(batch, 0) + 1
        seq_num = batch_counters[batch]
        rec_id = f"{batch}-{seq_num:04d}"
        rec["record_id"] = rec_id

        barcode = str(rec.get("barcode") or "").strip()
        if barcode.endswith(".0"):
            barcode = barcode[:-2]
        if barcode.lower() in {"none", "nan", ""}:
            barcode = ""

        old_img = str(rec.get("Website Front Image") or "").strip()
        
        if barcode:
            new_img = f"{barcode}.jpg"
        else:
            new_img = f"NO_BARCODE_{batch}_{seq_num:04d}.jpg"
            # Copy file if needed
            old_p = WEB_FRONT_DIR / old_img
            new_p = WEB_FRONT_DIR / new_img
            if old_p.exists() and not new_p.exists():
                try:
                    with Image.open(old_p) as im:
                        im.save(new_p, format="JPEG", quality=95)
                        im.save(WEB_FRONT_DIR / new_img.replace(".jpg", ".webp"), format="WEBP", quality=88)
                        im.save(IMAGES_DIR / new_img, format="JPEG", quality=95)
                        im.save(IMAGES_DIR / new_img.replace(".jpg", ".webp"), format="WEBP", quality=88)
                except Exception as e:
                    print(f"Error copying {old_p}: {e}")

        rec["Website Front Image"] = new_img
        updated_records.append(rec)
        if batch not in batch_records_map:
            batch_records_map[batch] = []
        batch_records_map[batch].append(rec)

    # Clean up any leftover nan files
    for p in list(WEB_FRONT_DIR.glob("*nan*")) + list(IMAGES_DIR.glob("*nan*")):
        try:
            p.unlink()
        except Exception:
            pass

    # Re-export
    export_master_excel(updated_records, OUTPUT_DIR / "Master_G2_G5_Consolidated.xlsx")
    export_shopify_csv(updated_records, OUTPUT_DIR / "Master_G2_G5_Shopify_Import.csv", batch_tag="g2_g5_shopify_import")

    for bname, brecs in batch_records_map.items():
        if brecs:
            export_master_excel(brecs, OUTPUT_DIR / f"{bname}_master_products.xlsx")
            export_shopify_csv(brecs, OUTPUT_DIR / f"{bname}_shopify_products.csv", batch_tag=f"{bname.lower()}_import")

    print(f"Successfully finalized {len(updated_records)} records across all batches!")

if __name__ == "__main__":
    main()
