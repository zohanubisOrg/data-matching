#!/usr/bin/env python3
"""
scripts/resolve_all_remaining_and_audit.py
------------------------------------------
1. Reprocesses all flagged items using the updated studio extractor (multi-scale, strict 3-panel, seam 0.06).
2. For products with only back photos or persistent barcode leak, queries Open Food Facts API for the front packshot.
3. If no web photo is found, records the item into Rabuta_Missing_Front_Photos_For_Customer.xlsx for the customer to reshoot.
4. Audits all 1,169 products in 12 batches of 100 items and saves batch_01_audit.json .. batch_12_audit.json.
5. Embeds Front-v3 and Back-v2 into Rabuta_12_10_Delivery_Embedded_v3.xlsx.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import openpyxl
from PIL import Image
import zxingcpp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from studio_front_v3_extractor import (
    process_single_product,
    render_studio_packshot,
    FRONT_V3_DIR,
    BACK_V2_DIR,
)
from run_and_audit_all_batches import audit_single_image, run_all_batches
from embed_v3_images_to_excel import embed_catalog_images

OFF_CACHE = ROOT / "output/catalog_pairs/off_cache"
OFF_CACHE.mkdir(parents=True, exist_ok=True)


def fetch_openfoodfacts_front(barcode: str) -> Image.Image | None:
    cache_file = OFF_CACHE / f"{barcode}.jpg"
    if cache_file.exists():
        try:
            return Image.open(cache_file)
        except Exception:
            pass

    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "ShopifyCatalogStudio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if data.get("status") == 1:
                p = data.get("product", {})
                img_url = p.get("image_front_url") or p.get("image_url")
                if img_url:
                    img_req = urllib.request.Request(img_url, headers={"User-Agent": "ShopifyCatalogStudio/1.0"})
                    with urllib.request.urlopen(img_req, timeout=12) as img_resp:
                        im = Image.open(BytesIO(img_resp.read()))
                        im.convert("RGB").save(cache_file, "JPEG", quality=95)
                        return im
    except Exception:
        pass
    return None


def main():
    print("===============================================================================")
    print("     BẮT ĐẦU GIẢI QUYẾT TRIỆT ĐỂ CÁC MÃ CÒN LỖI & AUDIT TOÀN BỘ 1.169 ẢNH      ")
    print("===============================================================================\n")

    bcs = sorted([f.stem.replace("-back", "") for f in BACK_V2_DIR.glob("*-back.jpg")])
    total = len(bcs)
    print(f"Tổng số mã sản phẩm trong catalog: {total}")

    # Load Excel product names
    excel_path = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
    bc_to_name = {}
    if excel_path.exists():
        wb = openpyxl.load_workbook(excel_path, read_only=True)
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            if len(row) > 1 and row[0]:
                c_bc = "".join(c for c in str(row[0]) if c.isdigit())
                if c_bc:
                    bc_to_name[c_bc] = str(row[1]) if len(row) > 1 else ""

    # 1. Quét tìm tất cả các mã hiện chưa đạt
    print("\n>>> Bước 1: Quét kiểm tra trạng thái hiện tại của 1.169 ảnh...")
    flagged = []
    for bc in bcs:
        res = audit_single_image(bc)
        if res["status"] != "ĐẠT":
            flagged.append(res)

    print(f"    Số ảnh cần xử lý lại: {len(flagged)} / {total}")

    # 2. Tái xử lý bằng Studio Extractor cải tiến
    print("\n>>> Bước 2: Tái xử lý các mã bằng thuật toán mới...")
    still_need_web = []
    for i, item in enumerate(flagged):
        bc = item["barcode"]
        process_single_product(bc)
        res = audit_single_image(bc)
        if res["status"] == "ĐẠT":
            print(f"    [{i+1}/{len(flagged)}] {bc}: ĐÃ ĐẠT!")
        else:
            still_need_web.append(item)

    print(f"    Số mã đã được giải quyết qua ảnh gốc: {len(flagged) - len(still_need_web)}")
    print(f"    Số mã còn lại cần tìm kiếm bổ sung: {len(still_need_web)}")

    # 3. Tìm kiếm Open Food Facts cho các mã còn lại
    print("\n>>> Bước 3: Tìm kiếm ảnh mặt trước trực tuyến cho các mã còn dính lỗi...")
    unresolved_for_customer = []
    for i, item in enumerate(still_need_web):
        bc = item["barcode"]
        name = bc_to_name.get(bc, "Sản phẩm")
        web_im = fetch_openfoodfacts_front(bc)
        if web_im:
            try:
                packshot = render_studio_packshot(web_im, target_size=2400)
                dest = FRONT_V3_DIR / f"{bc}-front.jpg"
                packshot.save(dest, "JPEG", quality=95)
                res = audit_single_image(bc)
                if res["status"] == "ĐẠT":
                    print(f"    [WEB FOUND] {bc} ({name[:30]}): ĐÃ ĐẠT!")
                    continue
            except Exception:
                pass

        # Nếu không có trên web hoặc vẫn chưa đạt
        res = audit_single_image(bc)
        unresolved_for_customer.append({
            "barcode": bc,
            "name": name,
            "errors": res.get("errors", [])
        })
        print(f"    [CẦN KHÁCH CHỤP LẠI] {bc} ({name[:30]}): {', '.join(res.get('errors', []))}")

    # 4. Xuất file Excel các mã cần khách chụp bổ sung nếu có
    if unresolved_for_customer:
        wb_miss = openpyxl.Workbook()
        ws_miss = wb_miss.active
        ws_miss.title = "Cần Khách Chụp Thêm"
        ws_miss.append(["STT", "Mã Barcode", "Tên Sản Phẩm", "Lý Do Cần Chụp Lại Mặt Trước"])
        for idx, itm in enumerate(unresolved_for_customer, start=1):
            ws_miss.append([idx, itm["barcode"], itm["name"], "; ".join(itm["errors"])])
        
        miss_file = ROOT / "output/catalog_pairs/Rabuta_Missing_Front_Photos_For_Customer.xlsx"
        wb_miss.save(miss_file)
        print(f"\n>>> Đã xuất danh sách {len(unresolved_for_customer)} sản phẩm cần khách chụp thêm tại: {miss_file.name}")

    # 5. Chạy Audit toàn diện 12 đợt (100 ảnh / đợt)
    print("\n>>> Bước 4: Chạy Audit chính thức 12 đợt cho toàn bộ 1.169 ảnh...")
    run_all_batches(start_batch=0, batch_size=100, audit_only=True)

    # 6. Nhúng ảnh vào file Excel xuất giao khách hàng
    print("\n>>> Bước 5: Nhúng ảnh Front-v3 và Back-v2 vào file Excel hoàn thiện...")
    embed_catalog_images()

    print("\n===============================================================================")
    print("                     HOÀN TẤT TOÀN BỘ QUY TRÌNH THÀNH CÔNG!                     ")
    print("===============================================================================")


if __name__ == "__main__":
    main()
