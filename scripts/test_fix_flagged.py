import json
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from product_mapper.vision.barcode_side_splitter import (
    scan_file, split_sides, panel_halves, _boxes_for_mode, _prepare, packshot_front
)
from audit_front_v2 import audit_single_image

with open(ROOT / "output/catalog_pairs/front_v2_flagged_for_reprocessing/flagged_reprocess_list.json", "r", encoding="utf-8") as f:
    items = json.load(f)

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

print(f"Bắt đầu thử nghiệm giải pháp tối ưu cho {len(items)} ảnh lỗi...\n")

for item in items:
    bc = item["barcode"]
    src_path = None
    for mname, mdata in manifest_data.items():
        if bc in mdata.get("products", {}):
            src_path = mdata["products"][bc].get("source")
            break
    
    if not src_path or not Path(src_path).exists():
        print(f"[{bc}] Không tìm thấy file gốc: {src_path}")
        continue
    
    src_p = Path(src_path)
    im = Image.open(src_p)
    w, h = im.size
    scan_res = scan_file(src_p)
    cx, cy = scan_res.get("center", [w * 0.5, h * 0.5])
    
    # Phân tích vị trí Barcode
    bc_x_frac = cx / float(w)
    bc_y_frac = cy / float(h)
    
    print(f"[{bc}] ({src_p.name}): {w}x{h}, Barcode tại ({round(bc_x_frac, 2)}, {round(bc_y_frac, 2)}) | Lỗi cũ: {item['category']}")
