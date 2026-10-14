import json
import shutil
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

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
DEST_DIR = ROOT / "output/catalog_pairs/front_v2_flagged_for_reprocessing"
DEST_DIR.mkdir(parents=True, exist_ok=True)

with open(ROOT / "output/catalog_pairs/front_v2_audit_report.json", "r", encoding="utf-8") as f:
    rep = json.load(f)

# Phân loại cụ thể
flagged_map = {}

# 1. Barcode leakage
for item in rep["critical_items"]:
    if "has-barcode-leakage" in item["reasons"]:
        flagged_map[item["barcode"]] = {
            "file": item["file"],
            "category": "BARCODE_LEAKAGE",
            "reason": "Ảnh mặt trước còn dính nguyên mã vạch (lấy nhầm mặt sau)",
            "ar": item["aspect_ratio"],
        }

# 2. Two packs
for item in rep["critical_items"]:
    if "two-packs-unsplit" in item["reasons"]:
        flagged_map[item["barcode"]] = {
            "file": item["file"],
            "category": "TWO_PACKS_UNSPLIT",
            "reason": "Ảnh dính cả 2 bao bì/chai song song chưa tách rời",
            "ar": item["aspect_ratio"],
        }

# 3. Extreme landscape strip
landscape_bcs = [
    "078895131178", "4045198908116", "4901313938669", "8850030007706",
    "8850403202509", "8886390203137", "8886390204011", "8938506580127"
]
for item in rep["warning_items"]:
    if item["barcode"] in landscape_bcs:
        flagged_map[item["barcode"]] = {
            "file": item["file"],
            "category": "LANDSCAPE_STRIP_SPLICE",
            "reason": "Cắt ngang nhầm trục Y tạo thành dải băng dẹt (ar > 2.6)",
            "ar": item["aspect_ratio"],
        }

# 4. Suspicious slivers (bao bì vuông/túi to nhưng bị cắt thành que dọc hẹp)
sliver_bcs = [
    "4045198925151", "5060284550153", "8005734101568", "8714573005240",
    "8716789011244", "8804009000083", "8850025335913", "9555907800525"
]
for item in rep["warning_items"]:
    if item["barcode"] in sliver_bcs:
        flagged_map[item["barcode"]] = {
            "file": item["file"],
            "category": "OVER_CROPPED_SLIVER",
            "reason": "Bao bì túi/hộp to nhưng bị cắt cụt thành thanh dọc quá hẹp (ar < 0.3)",
            "ar": item["aspect_ratio"],
        }

# Copy files và tạo danh sách
export_rows = []
for bc, info in sorted(flagged_map.items()):
    src_file = FRONT_DIR / info["file"]
    sub_dir = DEST_DIR / info["category"].lower()
    sub_dir.mkdir(parents=True, exist_ok=True)
    if src_file.exists():
        shutil.copy2(src_file, sub_dir / info["file"])
    
    prod = products.get(bc, {})
    export_rows.append({
        "barcode": bc,
        "file": info["file"],
        "category": info["category"],
        "error_description": info["reason"],
        "aspect_ratio": info["ar"],
        "product_name": prod.get("name_en", ""),
        "brand": prod.get("brand", ""),
        "saved_preview": str(sub_dir / info["file"]),
    })

out_json = DEST_DIR / "flagged_reprocess_list.json"
out_json.write_text(json.dumps(export_rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Đã trích xuất {len(export_rows)} ảnh lỗi sang: {DEST_DIR}")
print(f"File danh sách: {out_json}")
