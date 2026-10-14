import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.vision.barcode_side_splitter import scan_file
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
products = load_ground_truth(EXCEL_SOURCE)
lookup = truth_lookup(products)

g4_dir = ROOT / "source-import/G4-original"
files = sorted(list(g4_dir.glob("*.*")))

front_v2 = {p.stem.replace("-front", "").replace("_front", "") for p in (ROOT / "output/catalog_pairs/tagged/front-v2").glob("*.jpg")}
back_v2 = {p.stem.replace("-back", "").replace("_back", "") for p in (ROOT / "output/catalog_pairs/tagged/back-v2").glob("*.jpg")}

results = []
for f in files:
    rec = scan_file(f, set(lookup.keys()))
    bc = rec.get("barcode")
    excel_bc = lookup.get(bc) if bc else None
    if bc and not excel_bc:
        for v in get_barcode_lookup_variants(bc):
            if v in lookup:
                excel_bc = lookup[v]
                break
    results.append({
        "file": f.name,
        "path": str(f),
        "barcode": bc,
        "excel_barcode": excel_bc,
        "in_front_v2": excel_bc in front_v2 if excel_bc else False,
        "in_back_v2": excel_bc in back_v2 if excel_bc else False,
        "width": rec.get("width"),
        "height": rec.get("height"),
        "center": rec.get("center"),
    })

found_bc = [r for r in results if r["barcode"]]
in_excel = [r for r in results if r["excel_barcode"]]
not_in_excel = [r for r in results if r["barcode"] and not r["excel_barcode"]]
no_bc = [r for r in results if not r["barcode"]]
in_prev = [r for r in in_excel if r["in_back_v2"]]

print(f"Total files: {len(files)}")
print(f"With barcode: {len(found_bc)}")
print(f"  In Excel: {len(in_excel)}")
print(f"  Not in Excel: {len(not_in_excel)}")
print(f"  Duplicate in previous back-v2: {len(in_prev)}")
print(f"Without barcode: {len(no_bc)}")

if not_in_excel:
    print("\n--- NOT IN EXCEL ---")
    for r in not_in_excel:
        print(f"{r['file']}: barcode={r['barcode']}")

if in_prev:
    print("\n--- DUPLICATE IN PREVIOUS V2 ---")
    for r in in_prev:
        print(f"{r['file']}: barcode={r['barcode']}, excel_bc={r['excel_barcode']}")

(ROOT / "output/catalog_pairs/g4_initial_scan.json").write_text(
    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
)
