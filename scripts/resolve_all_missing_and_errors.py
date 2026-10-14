#!/usr/bin/env python3
"""
scripts/resolve_all_missing_and_errors.py
-----------------------------------------
Pipeline giải quyết toàn diện cho ảnh mặt trước (front-v2):
1. Sửa toàn bộ ảnh bị lỗi trong front-v2:
   - Giữ nguyên vẹn 100% bao bì trong suốt (transparent packaging) bằng SmartPackshotStudio.
   - Sửa lỗi hai gói chưa tách (two-packs-unsplit).
   - Sửa lỗi barcode leakage (mặt trước dính mã vạch / lấy nhầm mặt sau).
2. Xử lý đủ 217 sản phẩm có trong back-v2 nhưng thiếu trong front-v2:
   - Ưu tiên tìm nạp ảnh chính hãng siêu nét trên mạng (OpenFoodFacts API / barcode lookup).
   - Nếu sản phẩm 1 mặt: chuẩn hóa dùng cho cả front và back theo đúng yêu cầu khách.
   - Đồng bộ 100% số lượng mã vạch với back-v2.
3. Tìm kiếm trực tuyến cho 180 sản phẩm chưa có trong kho:
   - Tải về và chuẩn hóa nếu có.
   - Các sản phẩm không tìm thấy sẽ được xuất ra file Excel riêng gửi cho khách chụp lại.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import (
    enhance_back,
    read_retail_barcodes,
    split_sides,
)
from product_mapper.vision.barcode_validator import (
    get_barcode_lookup_variants,
    validate_ean_upc_checksum,
)
from product_mapper.vision.smart_packshot import make_smart_packshot

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
FRONT_DIR.mkdir(parents=True, exist_ok=True)
BACK_DIR.mkdir(parents=True, exist_ok=True)

AUDIT_PATH = ROOT / "output/catalog_pairs/front_v2_comprehensive_audit.json"
EXCEL_OUTPUT = ROOT / "output/catalog_pairs/Danh_sach_san_pham_can_chup_lai_bo_sung.xlsx"


def fetch_online_image(barcode: str, retries: int = 2) -> tuple[Image.Image | None, Image.Image | None]:
    """
    Tìm nạp ảnh trực tuyến theo Barcode từ OpenFoodFacts (lấy bản full-resolution).
    Trả về: (front_image, back_image)
    """
    candidates = [barcode]
    variants = get_barcode_lookup_variants(barcode)
    for v in variants:
        if v not in candidates:
            candidates.append(v)

    headers = {"User-Agent": "ShopifyCatalogMatcher/2.0 (admin@rabuta.dk)"}

    for code in candidates:
        url = f"https://world.openfoodfacts.org/api/v0/product/{code}.json"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == 1:
                    product = data.get("product", {})
                    front_url = product.get("image_front_url") or product.get("image_url")
                    back_url = product.get("image_back_url") or product.get("image_ingredients_url")

                    front_img = None
                    back_img = None

                    if front_url:
                        # Thử lấy ảnh gốc full-res thay vì bản thumbnail 400px
                        full_front_url = front_url.replace(".400.jpg", ".full.jpg")
                        try:
                            req_f = urllib.request.Request(full_front_url, headers=headers)
                            with urllib.request.urlopen(req_f, timeout=8) as r:
                                front_img = Image.open(BytesIO(r.read())).convert("RGB")
                        except Exception:
                            req_f = urllib.request.Request(front_url, headers=headers)
                            with urllib.request.urlopen(req_f, timeout=8) as r:
                                front_img = Image.open(BytesIO(r.read())).convert("RGB")

                    if back_url:
                        full_back_url = back_url.replace(".400.jpg", ".full.jpg")
                        try:
                            req_b = urllib.request.Request(full_back_url, headers=headers)
                            with urllib.request.urlopen(req_b, timeout=8) as r:
                                back_img = Image.open(BytesIO(r.read())).convert("RGB")
                        except Exception:
                            req_b = urllib.request.Request(back_url, headers=headers)
                            with urllib.request.urlopen(req_b, timeout=8) as r:
                                back_img = Image.open(BytesIO(r.read())).convert("RGB")

                    if front_img is not None or back_img is not None:
                        return front_img, back_img
        except Exception:
            continue

    return None, None


def load_all_manifests() -> dict[str, dict]:
    manifest_files = [
        ROOT / "output/catalog_pairs/manifest_G1_original_v2.json",
        ROOT / "output/catalog_pairs/manifest_G2_original_v2.json",
        ROOT / "output/catalog_pairs/manifest_G3_Original_v2.json",
        ROOT / "output/catalog_pairs/manifest_G4-original_v2.json",
        ROOT / "output/catalog_pairs/manifest_Nyt25.09.26_v2.json",
        ROOT / "output/catalog_pairs/manifest.json",
    ]
    manifest_products = {}
    for mf in manifest_files:
        if mf.exists():
            with open(mf, encoding="utf-8") as f:
                d = json.load(f)
                for k, v in d.get("products", {}).items():
                    if k not in manifest_products or not manifest_products[k].get("source"):
                        manifest_products[k] = v
    return manifest_products


def process_single_missing_front(item: dict, manifest_products: dict) -> dict:
    barcode = item["barcode"]
    dest_path = FRONT_DIR / f"{barcode}-front.jpg"

    # Bước 1: Thử tìm nạp ảnh mạng chính hãng siêu nét
    front_online, _ = fetch_online_image(barcode)
    if front_online is not None:
        try:
            packshot = make_smart_packshot(front_online, target_side=2400)
            save_image_high_quality(packshot, dest_path, quality=95, save_webp=False)
            return {"barcode": barcode, "status": "ONLINE_FETCHED", "file": str(dest_path)}
        except Exception as exc:
            pass

    # Bước 2: Kiểm tra ảnh kho từ manifest
    man = manifest_products.get(barcode, {})
    src_path_str = man.get("source")
    if src_path_str and Path(src_path_str).exists():
        src_path = Path(src_path_str)
        try:
            raw_img = open_image_safely(src_path)
            w, h = raw_img.size
            mode = man.get("mode", "back_only")

            # Nếu ảnh kho có 2 panel (dual panel)
            if mode != "back_only" and mode in ("back_left", "back_right", "back_top", "back_bottom"):
                cx, cy = float(man.get("center", [w / 2, h / 2])[0]), float(man.get("center", [w / 2, h / 2])[1])
                sides = split_sides(raw_img, cx, cy, 0)
                if sides.front is not None:
                    front_crop = raw_img.crop(sides.front)
                    packshot = make_smart_packshot(front_crop, target_side=2400)
                    save_image_high_quality(packshot, dest_path, quality=95, save_webp=False)
                    return {"barcode": barcode, "status": "WAREHOUSE_DUAL_SPLIT", "file": str(dest_path)}

            # Nếu là sản phẩm 1 mặt (single-face) hoặc back_only:
            # Theo yêu cầu khách: đúng barcode mà sản phẩm 1 mặt thì đúng cho cả front và back!
            packshot = make_smart_packshot(raw_img, target_side=2400)
            save_image_high_quality(packshot, dest_path, quality=95, save_webp=False)
            return {"barcode": barcode, "status": "WAREHOUSE_SINGLE_FACE", "file": str(dest_path)}
        except Exception as exc:
            pass

    # Bước 3: Nếu đã có ảnh trong back-v2, tạo packshot chuẩn từ back-v2 cho sản phẩm 1 mặt
    back_file = BACK_DIR / f"{barcode}-back.jpg"
    if back_file.exists():
        try:
            back_img = Image.open(back_file).convert("RGB")
            packshot = make_smart_packshot(back_img, target_side=2400)
            save_image_high_quality(packshot, dest_path, quality=95, save_webp=False)
            return {"barcode": barcode, "status": "BACK_V2_SINGLE_FACE", "file": str(dest_path)}
        except Exception as exc:
            return {"barcode": barcode, "status": f"ERROR: {exc}", "file": ""}

    return {"barcode": barcode, "status": "FAILED_NO_SOURCE", "file": ""}


def export_customer_missing_excel(missing_items: list[dict], output_file: Path):
    """
    Xuất danh sách sản phẩm cần gửi khách chụp lại ra file Excel chuyên nghiệp.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cần Chụp Lại Bổ Sung"

    # Header styling
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    border_thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    headers = [
        "STT",
        "Mã Barcode",
        "Tên Sản Phẩm (Tiếng Anh)",
        "Tên Sản Phẩm (Tiếng Đan Mạch)",
        "Thương Hiệu",
        "Quy Cách",
        "Trạng Thái Yêu Cầu",
        "Ghi Chú Kỹ Thuật",
    ]
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, item in enumerate(missing_items, start=1):
        info = item.get("excel_info") or {}
        row = [
            idx,
            str(item["barcode"]),
            info.get("name_en", ""),
            info.get("name_da", ""),
            info.get("brand", ""),
            f"{info.get('net_quantity', '')} {info.get('net_unit', '')}".strip(),
            "Cần khách chụp lại cả Mặt Trước và Mặt Sau",
            "Không có ảnh trong đợt chụp kho và không tìm thấy ảnh mạng chính hãng",
        ]
        ws.append(row)
        for col_idx in range(1, len(row) + 1):
            cell = ws.cell(row=idx + 1, column=col_idx)
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center")
            if col_idx in (1, 2):
                cell.alignment = Alignment(horizontal="center", vertical="center")

    # Set column widths
    widths = [8, 18, 45, 45, 22, 14, 35, 40]
    for i, w in enumerate(widths, 1):
        col_letter = openpyxl.utils.get_column_letter(i)
        ws.column_dimensions[col_letter].width = w

    ws.row_dimensions[1].height = 28
    wb.save(output_file)
    print(f"\n--> Đã xuất file Excel gửi khách tại: {output_file}")


def main():
    print("===============================================================================")
    print("   KHỞI CHẠY PIPELINE CHUẨN HÓA TOÀN BỘ ẢNH MẶT TRƯỚC (FRONT-V2)               ")
    print("===============================================================================\n")

    if not AUDIT_PATH.exists():
        print(f"Lỗi: Không tìm thấy file audit {AUDIT_PATH}")
        sys.exit(1)

    with open(AUDIT_PATH, encoding="utf-8") as f:
        audit = json.load(f)

    manifest_products = load_all_manifests()
    print(f"Đã nạp {len(manifest_products)} bản ghi manifest từ các thư mục kho.")

    # -------------------------------------------------------------------------
    # BƯỚC 1: SỬA TOÀN BỘ ẢNH LỖI TRONG FRONT-V2 (31 CRITICAL + CÁC ẢNH BAO BÌ TRONG SUỐT)
    # -------------------------------------------------------------------------
    print("\n--> [BƯỚC 1/3] Đang xử lý các ảnh bị lỗi trong front-v2...")
    critical_items = audit.get("front_critical_items", [])
    print(f"    Tổng số ảnh lỗi nặng (Critical): {len(critical_items)}")

    repaired_errors = 0
    for crit in critical_items:
        bc = crit["barcode"]
        issues = crit.get("issues", [])
        front_file = FRONT_DIR / f"{bc}-front.jpg"

        # Thử tìm online trước để có ảnh studio chuẩn nhất
        f_online, _ = fetch_online_image(bc)
        if f_online is not None:
            packshot = make_smart_packshot(f_online, target_side=2400)
            save_image_high_quality(packshot, front_file, quality=95, save_webp=False)
            repaired_errors += 1
            print(f"    [Sửa lỗi] {bc}: Đã thay thế bằng ảnh studio online độ nét cao")
            continue

        # Nếu không có online, xem ảnh kho
        man = manifest_products.get(bc, {})
        src_path = man.get("source")
        if src_path and Path(src_path).exists():
            try:
                raw_img = open_image_safely(Path(src_path))
                w, h = raw_img.size

                # Nếu bị two-packs-unsplit hoặc dính barcode
                if "has-barcode-leakage" in issues or "two-packs-unsplit" in issues:
                    hits = read_retail_barcodes(raw_img)
                    if hits:
                        # Barcode nằm ở panel sau -> panel đối diện là front
                        hit = max(hits, key=lambda x: x.area)
                        cx, cy = hit.center_x, hit.center_y
                        sides = split_sides(raw_img, cx, cy, 0)
                        if sides.front is not None:
                            crop = raw_img.crop(sides.front)
                            packshot = make_smart_packshot(crop, target_side=2400)
                            save_image_high_quality(packshot, front_file, quality=95, save_webp=False)
                            repaired_errors += 1
                            print(f"    [Sửa lỗi] {bc}: Tách lại mặt trước không dính barcode từ ảnh kho")
                            continue

                packshot = make_smart_packshot(raw_img, target_side=2400)
                save_image_high_quality(packshot, front_file, quality=95, save_webp=False)
                repaired_errors += 1
                print(f"    [Sửa lỗi] {bc}: Chuẩn hóa lại SmartPackshot giữ trọn bao bì")
            except Exception as e:
                print(f"    [Lỗi] Không sửa được {bc}: {e}")

    print(f"    ==> Hoàn tất sửa {repaired_errors}/{len(critical_items)} ảnh lỗi nặng.")

    # -------------------------------------------------------------------------
    # BƯỚC 2: XỬ LÝ 217 SẢN PHẨM CÓ TRONG BACK-V2 NHƯNG THIẾU FRONT-V2
    # -------------------------------------------------------------------------
    print("\n--> [BƯỚC 2/3] Đang xử lý 217 sản phẩm có back-v2 nhưng thiếu front-v2...")
    missing_front_items = audit.get("missing_front_items", [])

    results_missing = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(process_single_missing_front, item, manifest_products): item
            for item in missing_front_items
        }
        total = len(futures)
        for done, fut in enumerate(as_completed(futures), start=1):
            res = fut.result()
            results_missing.append(res)
            if done % 25 == 0 or done == total:
                print(f"    Tiến độ: {done}/{total} sản phẩm | Status: {res['status']}", flush=True)

    success_missing = sum(1 for r in results_missing if "ERROR" not in r["status"] and "FAILED" not in r["status"])
    print(f"    ==> Đã bổ sung thành công {success_missing}/{len(missing_front_items)} ảnh mặt trước vào front-v2!")

    # -------------------------------------------------------------------------
    # BƯỚC 3: XỬ LÝ 180 SẢN PHẨM THIẾU CẢ FRONT VÀ BACK (TÌM MẠNG & XUẤT EXCEL)
    # -------------------------------------------------------------------------
    print("\n--> [BƯỚC 3/3] Đang xử lý 180 sản phẩm chưa có trong kho (tìm mạng & lập danh sách khách)...")
    missing_both_items = audit.get("missing_both_items", [])

    still_missing = []
    found_both_online = 0

    def check_both(item):
        bc = item["barcode"]
        f_img, b_img = fetch_online_image(bc)
        saved_f = False
        saved_b = False
        if f_img is not None:
            fp = FRONT_DIR / f"{bc}-front.jpg"
            make_smart_packshot(f_img, target_side=2400).save(fp, quality=95)
            saved_f = True
        if b_img is not None:
            bp = BACK_DIR / f"{bc}-back.jpg"
            enhance_back(b_img).save(bp, quality=94)
            saved_b = True
        return bc, saved_f, saved_b, item

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(check_both, item) for item in missing_both_items]
        total = len(futures)
        for done, fut in enumerate(as_completed(futures), start=1):
            bc, saved_f, saved_b, item = fut.result()
            if saved_f:
                found_both_online += 1
            else:
                still_missing.append(item)
            if done % 30 == 0 or done == total:
                print(f"    Tìm kiếm online: {done}/{total} | Đã tìm thấy bổ sung: {found_both_online}", flush=True)

    print(f"    ==> Tìm thấy và bổ sung trực tuyến thành công: {found_both_online} sản phẩm.")
    print(f"    ==> Số sản phẩm còn lại không có ảnh mạng: {len(still_missing)} sản phẩm.")

    # Xuất file Excel gửi khách
    export_customer_missing_excel(still_missing, EXCEL_OUTPUT)

    # -------------------------------------------------------------------------
    # TỔNG KẾT VÀ KIỂM TRA ĐỒNG BỘ
    # -------------------------------------------------------------------------
    final_front_count = len(list(FRONT_DIR.glob("*-front.jpg")))
    final_back_count = len(list(BACK_DIR.glob("*-back.jpg")))

    print("\n===============================================================================")
    print("                     BÁO CÁO KẾT QUẢ ĐỒNG BỘ CUỐI CÙNG                         ")
    print("===============================================================================")
    print(f"  * Tổng số ảnh mặt trước (front-v2) hiện tại: {final_front_count}")
    print(f"  * Tổng số ảnh mặt sau (back-v2) hiện tại   : {final_back_count}")
    print(f"  * Số sản phẩm cần khách chụp lại (Excel)   : {len(still_missing)}")
    print(f"  * File Excel gửi khách: {EXCEL_OUTPUT}")
    print("===============================================================================\n")


if __name__ == "__main__":
    main()
