import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.extend([str(ROOT / "scripts"), str(ROOT / "src")])

from retry_g2_missing_barcodes import hard_read, _excel_barcode
from barcode_first_pipeline import load_ground_truth, truth_lookup

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
lookup = truth_lookup(load_ground_truth(EXCEL_SOURCE))

data = json.loads((ROOT / "output/catalog_pairs/g4_initial_scan.json").read_text(encoding="utf-8"))
all_files = [d["file"] for d in data]
no_bc = [d for d in data if not d["barcode"]]

print(f"Testing hard_read on {len(no_bc)} photos without barcode in initial scan...")
recovered = []
still_no_bc = []

for item in no_bc:
    p = ROOT / "source-import/G4-original" / item["file"]
    hit = hard_read(p)
    if hit:
        bc = hit["text"]
        xl = _excel_barcode(bc, lookup)
        recovered.append({"file": item["file"], "barcode": bc, "excel_barcode": xl, "engine": hit["engine"]})
        print(f"  [RECOVERED] {item['file']}: {bc} (in_excel: {xl is not None})")
    else:
        still_no_bc.append(item["file"])
        print(f"  [NO BC] {item['file']}")

print(f"\nTotal recovered by hard_read: {len(recovered)}")
print(f"Still no barcode: {len(still_no_bc)}")

(ROOT / "output/catalog_pairs/g4_hard_read_results.json").write_text(
    json.dumps({"recovered": recovered, "still_no_bc": still_no_bc}, indent=2, ensure_ascii=False),
    encoding="utf-8"
)
