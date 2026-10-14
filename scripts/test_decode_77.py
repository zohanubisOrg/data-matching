import json
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants
from product_mapper.vision.multipass_barcode import MultiPassBarcodeDecoder

with open(ROOT / "output/catalog_pairs/manifest_G1_original_v2.json", "r", encoding="utf-8") as f:
    manifest = json.load(f)

no_bc_files = manifest.get("no_barcode_files", [])
print(f"Tổng số file không đọc được barcode: {len(no_bc_files)}")

products = load_ground_truth(EXCEL_SOURCE)
lookup = truth_lookup(products)

decoder = MultiPassBarcodeDecoder()

recovered = []
still_failed = []

for idx, fname in enumerate(no_bc_files, start=1):
    fpath = ROOT / "source-import/G1_original" / fname
    if not fpath.exists():
        continue
    
    res = decoder.decode(fpath)
    if res and res.is_valid_checksum:
        bc = res.text
        # Kiểm tra xem có trong Excel không
        excel_bc = lookup.get(bc)
        if not excel_bc:
            for v in get_barcode_lookup_variants(bc):
                if v in lookup:
                    excel_bc = lookup[v]
                    break
        in_excel = excel_bc is not None
        recovered.append({
            "file": fname,
            "barcode": bc,
            "excel_barcode": excel_bc or "",
            "in_excel": in_excel,
            "pass_name": res.pass_name
        })
        print(f"[{idx}/{len(no_bc_files)}] RECOVERED {fname} -> {bc} (in_excel={in_excel}) via {res.pass_name}")
    else:
        still_failed.append(fname)

print(f"\n=======================================================")
print(f"Đã giải mã cứu hộ thành công: {len(recovered)} / {len(no_bc_files)}")
print(f"Số barcode khớp trong Excel : {sum(1 for r in recovered if r['in_excel'])}")
print(f"Số barcode không có trong Excel: {sum(1 for r in recovered if not r['in_excel'])}")
print(f"Còn lại chưa đọc được        : {len(still_failed)}")
