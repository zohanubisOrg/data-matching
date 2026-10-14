import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data = json.loads((ROOT / "output/catalog_pairs/review/analysis_21_errors.json").read_text(encoding="utf-8"))

for idx, d in enumerate(data, 1):
    bc = d["barcode"]
    src = d["source_file"]
    w, h = d["img_size"]
    eb_w, eb_h = d["err_back_size"]
    has_bc = d["err_back_has_bc"]
    det = d["barcode_detected"]
    det_str = f"{det['text']} at ({det['cx_pct']}, {det['cy_pct']})" if det else "NO BARCODE"
    print(f"#{idx:02d} {bc} [{src}]: err_back=({eb_w}x{eb_h}) has_bc={has_bc} | barcode: {det_str}")
