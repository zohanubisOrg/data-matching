import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth

products = {p["barcode"]: p for p in load_ground_truth(EXCEL_SOURCE)}
with open(ROOT / "output/catalog_pairs/front_v2_audit_report.json", "r", encoding="utf-8") as f:
    rep = json.load(f)

print("=== 8 CRITICAL ITEMS ===")
for item in rep["critical_items"]:
    bc = item["barcode"]
    prod = products.get(bc, {})
    name = prod.get("name_en", "Unknown")
    brand = prod.get("brand", "Unknown")
    print(f"[{item['file']}] {item['reasons']} | {brand} - {name}")

print("\n=== EXTREME LANDSCAPE STRIP (WARNING) ===")
for item in rep["warning_items"]:
    if "extreme-landscape-strip" in item["reasons"]:
        bc = item["barcode"]
        prod = products.get(bc, {})
        name = prod.get("name_en", "Unknown")
        print(f"[{item['file']}] ar={item['aspect_ratio']} | {name}")

print("\n=== NGUỒN ẢNH CỦA 8 LANDSCAPE STRIP ITEMS ===")
landscape_barcodes = [
    "078895131178", "4045198908116", "4901313938669", "8850030007706",
    "8850403202509", "8886390203137", "8886390204011", "8938506580127"
]

manifests = [
    ROOT / "output/catalog_pairs/manifest_G1_original_v2.json",
    ROOT / "output/catalog_pairs/manifest_G2_original_v2.json",
    ROOT / "output/catalog_pairs/manifest_G3_Original_v2.json"
]

manifest_data = {}
for mpath in manifests:
    if mpath.exists():
        with open(mpath, "r", encoding="utf-8") as f:
            manifest_data[mpath.name] = json.load(f)

for bc in landscape_barcodes:
    for mname, data in manifest_data.items():
        if bc in data.get("products", {}):
            p = data["products"][bc]
            s_name = Path(p.get("source", "")).name
            print(f"[{bc}] in {mname}: source={s_name}, mode={p.get('mode')}, name={p.get('name_en')[:40]}")
            break


