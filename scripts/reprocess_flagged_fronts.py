#!/usr/bin/env python3
"""
scripts/reprocess_flagged_fronts.py
-----------------------------------
Tái xử lý và sửa lỗi triệt để cho 24 ảnh trong front-v2:
1. Xác định chính xác vị trí mã vạch EAN mục tiêu trên ảnh gốc (không mirror)
2. Tách đúng cặp Mặt Trước / Mặt Sau dọc theo trục X (tránh chém ngang Y)
3. Đảm bảo Mặt Trước không dính mã vạch, không dính 2 gói, tỷ lệ đứng chuẩn Studio
4. Ghi đè vào output/catalog_pairs/tagged/front-v2
5. Kiểm định lại bằng audit_single_image
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
import zxingcpp
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_front_v2 import audit_single_image
from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import (
    enhance_back,
    packshot_front,
    place_front_on_white,
)
from product_mapper.vision.barcode_validator import (
    get_barcode_lookup_variants,
    validate_ean_upc_checksum,
)

FLAGGED_LIST_PATH = ROOT / "output/catalog_pairs/front_v2_flagged_for_reprocessing/flagged_reprocess_list.json"
FRONT_V2_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_V2_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"


def find_target_barcode_position(image: Image.Image, target_barcode: str) -> tuple[float, float] | None:
    """Tìm vị trí tâm (x, y) của mã vạch mục tiêu trên ảnh gốc."""
    variants = set([target_barcode] + list(get_barcode_lookup_variants(target_barcode)))
    hits = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.EANUPC, try_rotate=True, try_downscale=True)
    
    # 1. Tìm chính xác mã mục tiêu
    for h in hits:
        text = "".join(ch for ch in str(h.text or "") if ch.isdigit())
        if text in variants or target_barcode in set(get_barcode_lookup_variants(text)):
            pts = [(float(h.position.top_left.x), float(h.position.top_left.y)),
                   (float(h.position.top_right.x), float(h.position.top_right.y)),
                   (float(h.position.bottom_right.x), float(h.position.bottom_right.y)),
                   (float(h.position.bottom_left.x), float(h.position.bottom_left.y))]
            cx = sum(p[0] for p in pts) / 4.0
            cy = sum(p[1] for p in pts) / 4.0
            return cx, cy

    # 2. Nếu không thấy chính xác mã, lấy bất kỳ mã vạch hợp lệ nào
    for h in hits:
        text = "".join(ch for ch in str(h.text or "") if ch.isdigit())
        if validate_ean_upc_checksum(text):
            pts = [(float(h.position.top_left.x), float(h.position.top_left.y)),
                   (float(h.position.top_right.x), float(h.position.top_right.y)),
                   (float(h.position.bottom_right.x), float(h.position.bottom_right.y)),
                   (float(h.position.bottom_left.x), float(h.position.bottom_left.y))]
            cx = sum(p[0] for p in pts) / 4.0
            cy = sum(p[1] for p in pts) / 4.0
            return cx, cy
            
    return None


def find_best_vertical_cut(image: Image.Image) -> int:
    """Tìm đường rãnh ngăn cách tự nhiên giữa 2 sản phẩm (trục X) trong khoảng 0.38 - 0.62."""
    w, h = image.size
    small = image.resize((600, max(1, int(600 * h / w))))
    arr = np.asarray(small)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    profile = np.convolve(edges.mean(axis=0), np.ones(15) / 15.0, mode="same")
    
    sw = small.size[0]
    low = int(sw * 0.38)
    high = int(sw * 0.62)
    best_idx = low + int(np.argmin(profile[low:high]))
    return int(best_idx * (w / sw))


def find_best_horizontal_cut(image: Image.Image) -> int:
    """Tìm đường rãnh ngăn cách theo trục Y trong khoảng 0.38 - 0.62."""
    w, h = image.size
    small = image.resize((max(1, int(600 * w / h)), 600))
    arr = np.asarray(small)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    profile = np.convolve(edges.mean(axis=1), np.ones(15) / 15.0, mode="same")
    
    sh = small.size[1]
    low = int(sh * 0.38)
    high = int(sh * 0.62)
    best_idx = low + int(np.argmin(profile[low:high]))
    return int(best_idx * (h / sh))


def reprocess_item(item: dict, manifest_data: dict) -> dict:
    bc = item["barcode"]
    src_path = None
    for mname, mdata in manifest_data.items():
        if bc in mdata.get("products", {}):
            src_path = mdata["products"][bc].get("source")
            break
            
    if not src_path or not Path(src_path).exists():
        return {"barcode": bc, "status": "FAILED", "reason": f"Source not found: {src_path}"}

    src_p = Path(src_path)
    im = open_image_safely(src_p)
    w, h = im.size

    # Tìm vị trí mã vạch
    bc_pos = find_target_barcode_position(im, bc)
    if bc_pos is None:
        cx, cy = w * 0.5, h * 0.5
    else:
        cx, cy = bc_pos

    # 1. Thử cắt dọc (Vertical Cut)
    cut_x = find_best_vertical_cut(im)
    if cx > cut_x:
        v_front_box = (0, 0, cut_x, h)
        v_back_box = (cut_x, 0, w, h)
        v_mode = "back_right"
    else:
        v_front_box = (cut_x, 0, w, h)
        v_back_box = (0, 0, cut_x, h)
        v_mode = "back_left"

    # 2. Thử cắt ngang (Horizontal Cut)
    cut_y = find_best_horizontal_cut(im)
    if cy > cut_y:
        h_front_box = (0, 0, w, cut_y)
        h_back_box = (0, cut_y, w, h)
        h_mode = "back_bottom"
    else:
        h_front_box = (0, cut_y, w, h)
        h_back_box = (0, 0, w, cut_y)
        h_mode = "back_top"

    # So sánh tỷ lệ khung hình AR của 2 phương án: ưu tiên AR gần chuẩn đứng 0.60 - 1.20
    v_ar = (v_front_box[2] - v_front_box[0]) / float(max(1, v_front_box[3] - v_front_box[1]))
    h_ar = (h_front_box[2] - h_front_box[0]) / float(max(1, h_front_box[3] - h_front_box[1]))

    v_score = abs(v_ar - 0.75)
    h_score = abs(h_ar - 0.75)

    # Đa số ảnh 2 mặt đặt cạnh nhau là cắt dọc, chỉ dùng cắt ngang khi bao bì nằm xếp chồng rõ rệt
    if abs(cx / w - 0.5) > 0.12 or v_score <= h_score or h_ar > 2.0:
        chosen_box = v_front_box
        chosen_back_box = v_back_box
        chosen_mode = v_mode
    else:
        chosen_box = h_front_box
        chosen_back_box = h_back_box
        chosen_mode = h_mode

    # Đặc biệt: Với ảnh có barcode leakage (ví dụ 4045198900905), đảm bảo không chém vào vùng barcode
    front_crop = im.crop(chosen_box)
    
    # Kiểm tra xem front crop có dính barcode không, nếu có thì tự động né barcode hoặc đảo mặt
    loop_count = 0
    while loop_count < 3:
        loop_count += 1
        hits_front = zxingcpp.read_barcodes(front_crop, formats=zxingcpp.BarcodeFormat.EANUPC)
        if not hits_front:
            break
        # Có barcode trong front_crop:
        max_bc_x = max(int(h.position.bottom_right.x) for h in hits_front)
        min_bc_x = min(int(h.position.top_left.x) for h in hits_front)
        crop_w = front_crop.size[0]

        if max_bc_x < crop_w * 0.45:
            # Barcode ở mép trái của crop => tăng mép trái X
            new_x0 = chosen_box[0] + max_bc_x + int(w * 0.03)
            if new_x0 < chosen_box[2] - 300:
                chosen_box = (new_x0, chosen_box[1], chosen_box[2], chosen_box[3])
                front_crop = im.crop(chosen_box)
                continue
        elif min_bc_x > crop_w * 0.55:
            # Barcode ở mép phải của crop => giảm mép phải X
            new_x1 = chosen_box[0] + min_bc_x - int(w * 0.03)
            if new_x1 > chosen_box[0] + 300:
                chosen_box = (chosen_box[0], chosen_box[1], new_x1, chosen_box[3])
                front_crop = im.crop(chosen_box)
                continue
        
        # Nếu barcode chiếm cả mảng lớn hoặc ở giữa => Đảo panel (đã chọn nhầm mặt sau làm mặt trước)
        if chosen_mode == "back_left":
            chosen_box = (0, 0, cut_x, h)
            chosen_back_box = (cut_x, 0, w, h)
            chosen_mode = "back_right"
        else:
            chosen_box = (cut_x, 0, w, h)
            chosen_back_box = (0, 0, cut_x, h)
            chosen_mode = "back_left"
        front_crop = im.crop(chosen_box)

    # Tạo Packshot phông trắng Studio
    packshot = packshot_front(front_crop)
    dest_front = FRONT_V2_DIR / f"{bc}-front.jpg"
    save_image_high_quality(packshot, dest_front, quality=95, save_webp=False)

    # Lưu lại ảnh back được cắt đúng chuẩn
    back_crop = im.crop(chosen_back_box)
    back_enhanced = enhance_back(back_crop)
    dest_back = BACK_V2_DIR / f"{bc}-back.jpg"
    save_image_high_quality(back_enhanced, dest_back, quality=94, save_webp=False)

    # Audit lại
    audit_res = audit_single_image(str(dest_front))
    
    im.close()
    return {
        "barcode": bc,
        "status": "FIXED" if audit_res["severity"] == "OK" else "IMPROVED",
        "severity": audit_res["severity"],
        "reasons": audit_res["reasons"],
        "aspect_ratio": audit_res.get("aspect_ratio"),
        "coverage": audit_res.get("coverage"),
        "mode": chosen_mode,
        "source": src_p.name,
    }


def main():
    print("===============================================================================")
    print("      TÁI XỬ LÝ 24 ẢNH FRONT-V2 LỖI (CHỈNH SỬA TỶ LỆ & PHÂN MẶT TỐI ƯU)        ")
    print("===============================================================================\n")

    with open(FLAGGED_LIST_PATH, "r", encoding="utf-8") as f:
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

    results = []
    fixed_count = 0
    improved_count = 0

    for idx, item in enumerate(items, start=1):
        bc = item["barcode"]
        res = reprocess_item(item, manifest_data)
        results.append(res)
        if res.get("severity") == "OK":
            fixed_count += 1
            print(f"[{idx}/{len(items)}] [OK FIX] {bc} ({res['source']}): mode={res['mode']}, AR={res['aspect_ratio']}, reasons={res['reasons']}")
        else:
            improved_count += 1
            print(f"[{idx}/{len(items)}] [SEV: {res.get('severity')}] {bc} ({res.get('source')}): mode={res.get('mode')}, AR={res.get('aspect_ratio')}, reasons={res.get('reasons')}")

    out_res_path = ROOT / "output/catalog_pairs/front_v2_reprocess_results.json"
    out_res_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===============================================================================")
    print(f"  * Tổng số ảnh tái xử lý  : {len(results)}")
    print(f"  * Đã sửa hoàn toàn (OK)  : {fixed_count} / {len(results)} ({fixed_count/len(results)*100:.1f}%)")
    print(f"  * Cần tinh chỉnh thêm    : {improved_count}")
    print(f"  * Báo cáo kết quả lưu tại: {out_res_path}")
    print("===============================================================================\n")


if __name__ == "__main__":
    main()
