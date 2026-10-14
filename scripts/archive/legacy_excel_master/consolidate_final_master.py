from __future__ import annotations

import json
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.product_mapper.reporting.shopify_exporter import export_shopify_csv, export_master_excel

OUTPUT_BASE = Path("output/shopify_import")


def consolidate_all():
    batches = ["G2", "G3", "G4", "G5"]
    all_records = []
    
    for b in batches:
        xlsx_file = OUTPUT_BASE / f"{b}_master_products.xlsx"
        if xlsx_file.exists():
            df = pd.read_excel(xlsx_file)
            recs = df.to_dict(orient="records")
            all_records.extend(recs)
            print(f"Loaded {len(recs)} records from {xlsx_file.name}")
            
    print(f"\nTotal combined records: {len(all_records)}")
    
    master_csv = OUTPUT_BASE / "Master_G2_G5_Shopify_Import.csv"
    master_xlsx = OUTPUT_BASE / "Master_G2_G5_Consolidated.xlsx"
    
    export_shopify_csv(all_records, master_csv, batch_tag="g2_g5_master_import")
    export_master_excel(all_records, master_xlsx)
    
    confirmed = sum(1 for r in all_records if str(r.get("barcode", "")).strip() and str(r.get("barcode", "")).strip().lower() not in {"nan", "none"})
    print("\n==========================================")
    print("🏆 FINAL RECONCILIATION SUMMARY:")
    print("==========================================")
    print(f"Total Input Images Processed: {len(all_records)}")
    print(f"Total Verified Barcodes:     {confirmed} ({confirmed/len(all_records)*100:.1f}%)")
    print(f"Shopify 28-Column CSV:       {master_csv}")
    print(f"Consolidated Master Excel:   {master_xlsx}")
    print("==========================================")


if __name__ == "__main__":
    consolidate_all()
