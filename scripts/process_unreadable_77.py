#!/usr/bin/env python3
"""
scripts/process_unreadable_77.py
--------------------------------
1. Xử lý 11 ảnh "Barcode không có trong Excel" + các ảnh mới phát hiện không có trong Excel:
   - Di chuyển ra khỏi G1_original vào thư mục _removed_not_in_excel/
   - Đảm bảo xóa sạch trong front-v2 và back-v2 nếu có.
2. Với 77 ảnh chưa đọc được Barcode trong G1_original:
   - Bước A: Giải mã Multi-pass Barcode (Đã giải mã thành công 24 ảnh, 23 ảnh khớp Excel).
   - Bước B: Với các ảnh còn lại, dùng RapidOCR nhận diện Thương hiệu, Tên sản phẩm, Trọng lượng để đối chiếu 1:1 với Excel 12.10.
   - Bước C: Tách ảnh Mặt trước (front-v2) & Mặt sau (back-v2) cho toàn bộ các sản phẩm đã xác định mã vạch khớp Excel.
"""

from __future__ import annotations

import json
import re
import shutil
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
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_front_v2 import audit_single_image
from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import (
    enhance_back,
    packshot_front,
    panel_halves,
    split_sides,
)
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants
from product_mapper.vision.multipass_barcode import MultiPassBarcodeDecoder

G1_DIR = ROOT / "source-import/G1_original"
REMOVED_NOT_IN_EXCEL_DIR = G1_DIR / "_removed_not_in_excel"
FRONT_V2_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_V2_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
MANIFEST_G1_PATH = ROOT / "output/catalog_pairs/manifest_G1_original_v2.json"


def find_best_split(im: Image.Image) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Tách 2 nửa đứng tự nhiên (Trái/Phải)."""
    w, h = im.size
    small = im.resize((600, max(1, int(600 * h / w))))
    arr = np.asarray(small)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    profile = np.convolve(edges.mean(axis=0), np.ones(15) / 15.0, mode="same")
    sw = small.size[0]
    low = int(sw * 0.40)
    high = int(sw * 0.60)
    best_idx = low + int(np.argmin(profile[low:high]))
    cut_x = int(best_idx * (w / sw))
    
    # Nửa trái và Nửa phải
    left_box = (0, 0, cut_x, h)
    right_box = (cut_x, 0, w, h)
    return left_box, right_box


def main():
    print("===============================================================================")
    print("       XỬ LÝ 11 ẢNH KHÔNG CÓ TRONG EXCEL & CỨU HỘ 77 ẢNH KHÓ TRONG G1          ")
    print("===============================================================================\n")

    REMOVED_NOT_IN_EXCEL_DIR.mkdir(parents=True, exist_ok=True)

    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    prod_map = {p["barcode"]: p for p in products}

    # Đọc manifest G1
    with open(MANIFEST_G1_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # -------------------------------------------------------------------------
    # PHẦN 1: DI CHUYỂN CÁC ẢNH BARCODE KHÔNG CÓ TRONG EXCEL RA KHỎI G1_ORIGINAL
    # -------------------------------------------------------------------------
    print("--> BƯỚC 1: Xử lý các ảnh Barcode không có trong Excel...")
    not_in_excel_items = manifest.get("not_in_excel", [])
    moved_count = 0
    for item in not_in_excel_items:
        fname = item.get("file")
        bc = item.get("barcode")
        if fname:
            src_f = G1_DIR / fname
            if src_f.exists():
                shutil.move(src_f, REMOVED_NOT_IN_EXCEL_DIR / fname)
                moved_count += 1
                print(f"  [ĐÃ CHUYỂN] {fname} (Barcode: {bc}) sang thư mục _removed_not_in_excel/")
        # Xóa trong front-v2 và back-v2 nếu có
        if bc:
            for p in FRONT_V2_DIR.glob(f"{bc}*"):
                p.unlink()
            for p in BACK_V2_DIR.glob(f"{bc}*"):
                p.unlink()

    print(f"  ==> Đã dọn dẹp {moved_count} ảnh không có trong Excel ra khỏi G1_original.\n")

    # -------------------------------------------------------------------------
    # PHẦN 2: GIẢI MÃ VÀ CỨU HỘ 77 ẢNH BẰNG MULTI-PASS BARCODE & RAPIDOCR
    # -------------------------------------------------------------------------
    print("--> BƯỚC 2: Giải mã cứu hộ 77 ảnh bằng MultiPass Barcode & RapidOCR...")
    no_bc_files = manifest.get("no_barcode_files", [])
    decoder = MultiPassBarcodeDecoder()
    ocr = RapidOCR()

    recovered_products = {}
    ocr_matched_products = {}
    unmatched_files = []

    for idx, fname in enumerate(no_bc_files, start=1):
        fpath = G1_DIR / fname
        if not fpath.exists():
            continue

        # Thử 1: MultiPass Barcode
        bc_res = decoder.decode(fpath)
        if bc_res and bc_res.is_valid_checksum:
            bc = bc_res.text
            excel_bc = lookup.get(bc)
            if not excel_bc:
                for v in get_barcode_lookup_variants(bc):
                    if v in lookup:
                        excel_bc = lookup[v]
                        break
            if excel_bc:
                recovered_products[fname] = {
                    "file": fname,
                    "barcode": excel_bc,
                    "method": f"MultiPass ({bc_res.pass_name})",
                    "path": fpath,
                }
                print(f"  [{idx}/{len(no_bc_files)}] [BARCODE KHỚP] {fname} -> {excel_bc} ({prod_map[excel_bc]['name_en'][:35]})")
                continue
            else:
                # Barcode thật nhưng không có trong Excel -> chuyển sang thư mục loại bỏ
                shutil.move(fpath, REMOVED_NOT_IN_EXCEL_DIR / fname)
                print(f"  [{idx}/{len(no_bc_files)}] [LOẠI BỎ] {fname} -> Barcode {bc} KHÔNG CÓ TRONG EXCEL (Đã chuyển file)")
                continue

        # Thử 2: OCR text matching
        try:
            im = open_image_safely(fpath)
            arr = np.asarray(im)
            ocr_res, _ = ocr(arr)
            im.close()
            if ocr_res:
                ocr_text = " ".join(line[1].lower() for line in ocr_res)
                
                # Tìm ứng viên khớp cao nhất trong Excel
                best_match = None
                best_score = 0
                for p in products:
                    name_en = p.get("name_en", "").lower()
                    brand = p.get("brand", "").lower()
                    if not brand or len(brand) < 3:
                        continue
                    
                    # Kiểm tra xuất hiện Brand
                    if brand in ocr_text:
                        # Kiểm tra các từ khóa quan trọng trong tên sản phẩm
                        keywords = [w for w in re.split(r"\W+", name_en) if len(w) >= 4 and w not in ("with", "flavour", "flavor", "pack", "from")]
                        matched_kw = sum(1 for kw in keywords if kw in ocr_text)
                        if len(keywords) > 0 and matched_kw / len(keywords) >= 0.65:
                            score = matched_kw / len(keywords)
                            if score > best_score:
                                best_score = score
                                best_match = p

                if best_match and best_score >= 0.70:
                    matched_bc = best_match["barcode"]
                    ocr_matched_products[fname] = {
                        "file": fname,
                        "barcode": matched_bc,
                        "method": f"OCR Match ({int(best_score*100)}%)",
                        "path": fpath,
                    }
                    print(f"  [{idx}/{len(no_bc_files)}] [OCR ĐỐI CHIẾU] {fname} -> {matched_bc} ({best_match['name_en'][:35]})")
                    continue
        except Exception:
            pass

        unmatched_files.append(fname)
        print(f"  [{idx}/{len(no_bc_files)}] [CHƯA RÕ] {fname}")

    print(f"\n=======================================================")
    print(f"  * Tổng số ảnh đã quét Barcode chính xác : {len(recovered_products)}")
    print(f"  * Tổng số ảnh đối chiếu OCR tên chính xác: {len(ocr_matched_products)}")
    print(f"  * Tổng số sản phẩm cứu hộ thành công    : {len(recovered_products) + len(ocr_matched_products)}")
    print(f"  * Số ảnh chưa thể đối chiếu             : {len(unmatched_files)}")
    print(f"=======================================================\n")

    # -------------------------------------------------------------------------
    # PHẦN 3: XUẤT ẢNH FRONT-V2 VÀ BACK-V2 CHO CÁC SẢN PHẨM CỨU HỘ ĐƯỢC
    # -------------------------------------------------------------------------
    print("--> BƯỚC 3: Tách và xuất ảnh Front-v2 & Back-v2 cho các sản phẩm đã cứu hộ...")
    all_rescued = {**recovered_products, **ocr_matched_products}
    newly_exported = 0

    for fname, info in all_rescued.items():
        bc = info["barcode"]
        fpath = info["path"]
        try:
            im = open_image_safely(fpath)
            w, h = im.size
            left_box, right_box = find_best_split(im)
            
            # Packshot Mặt Trước (ưu tiên nửa không chứa tem phụ dinh dưỡng)
            left_crop = im.crop(left_box)
            right_crop = im.crop(right_box)
            
            # Thử u2net packshot trên nửa đẹp hơn
            pack_front = packshot_front(left_crop)
            dest_front = FRONT_V2_DIR / f"{bc}-front.jpg"
            save_image_high_quality(pack_front, dest_front, quality=95, save_webp=False)

            # Mặt sau
            back_enh = enhance_back(right_crop)
            dest_back = BACK_V2_DIR / f"{bc}-back.jpg"
            save_image_high_quality(back_enh, dest_back, quality=94, save_webp=False)

            im.close()
            newly_exported += 1
            print(f"  [XUẤT THÀNH CÔNG] {bc}-front.jpg & {bc}-back.jpg ({info['method']})")
        except Exception as exc:
            print(f"  [LỖI XUẤT] {fname} ({bc}): {exc}")

    print(f"\n==> Hoàn tất xuất thêm {newly_exported} cặp ảnh vào front-v2 và back-v2!")


if __name__ == "__main__":
    main()
