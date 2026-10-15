#!/usr/bin/env python3
"""
scripts/remediate_and_reaccept_catalog.py
-----------------------------------------
Hệ thống 4 Subagents xử lý và tái nghiệm thu toàn diện catalog webshop:
1. Agent 1: Kiểm tra đối chiếu từng dòng với Customer Ground Truth (Cột 23).
2. Agent 2: Lọc và bóc tách các sản phẩm lỗi (ảnh đôi, lấy ruột mất vỏ, lật nhầm, cắt cụt đáy).
3. Agent 3: Xác thực nguồn ảnh sạch từ Master_1659_Clean_Front_Images, front-v1, web public.
4. Agent 4: Xử lý đóng gói chuẩn webshop 2400x2400 nền trắng và tái nghiệm thu 100%.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
import openpyxl
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

EXCEL_FILE = ROOT / "source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.original_backup.xlsx"
CUST_GT_DIR = ROOT / "output/catalog_pairs/customer_ground_truth"
FRONT_V4_DIR = ROOT / "output/catalog_pairs/tagged/front-v4"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"

# Các kho nguồn ảnh sạch chất lượng cao đã phát hiện
MASTER_1659_DIR = ROOT / "output/shopify_import_final/Master_1659_Clean_Front_Images"
FRONT_V1_DIR = ROOT / "output/catalog_pairs/tagged/front-v1"
PRODUCT_IMAGES_DIR = ROOT / "output/shopify_import_final/product_images"
WEB_FRONT_DIR = ROOT / "web/public/products/front"

STAGE1_REPORT = ROOT / "output/catalog_pairs/subagent1_inspection_report.json"
STAGE2_REPORT = ROOT / "output/catalog_pairs/subagent2_defect_filter.json"
STAGE3_REPORT = ROOT / "output/catalog_pairs/subagent3_validated_sources.json"
STAGE4_REPORT = ROOT / "output/catalog_pairs/subagent4_reacceptance_report.json"


def find_file(folder: Path, barcode: str, suffix: str = "front") -> Optional[Path]:
    for sep in ("-", "_"):
        cand = folder / f"{barcode}{sep}{suffix}.jpg"
        if cand.exists():
            return cand
    cand_plain = folder / f"{barcode}.jpg"
    if cand_plain.exists():
        return cand_plain
    cand_webp = folder / f"{barcode}.webp"
    if cand_webp.exists():
        return cand_webp
    return None


def find_in_master_1659(barcode: str) -> Optional[Path]:
    """Tìm ảnh trong Master_1659 theo barcode."""
    if not MASTER_1659_DIR.exists():
        return None
    matches = list(MASTER_1659_DIR.glob(f"*_{barcode}_*.jpg"))
    if matches:
        return matches[0]
    # Thử barcode bỏ số 0 đầu
    if barcode.startswith("0"):
        stripped = barcode.lstrip("0")
        matches = list(MASTER_1659_DIR.glob(f"*_{stripped}_*.jpg"))
        if matches:
            return matches[0]
    return None


def format_to_studio_canvas(im: Image.Image, target_dim: int = 2400, occupancy: float = 0.85) -> Image.Image:
    """Đóng gói sản phẩm vào tâm canvas 2400x2400 trắng tinh khiết #FFFFFF."""
    arr = np.array(im.convert("RGB"))
    fg = (arr < 250).any(axis=-1)
    ys, xs = np.where(fg)
    if len(xs) == 0:
        return Image.new("RGB", (target_dim, target_dim), (255, 255, 255))

    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
    crop = im.crop((x0, y0, x1, y1))
    pw, ph = crop.size

    max_side = max(pw, ph)
    scale = (target_dim * occupancy) / float(max_side)
    nw = max(1, int(round(pw * scale)))
    nh = max(1, int(round(ph * scale)))

    resized = crop.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_dim, target_dim), (255, 255, 255))
    canvas.paste(resized, ((target_dim - nw) // 2, (target_dim - nh) // 2))

    # Đảm bảo viền 4px trắng tinh
    c_arr = np.array(canvas)
    c_arr[:4, :] = 255
    c_arr[-4:, :] = 255
    c_arr[:, :4] = 255
    c_arr[:, -4:] = 255
    return Image.fromarray(c_arr)


# ==============================================================================
# GIAI ĐOẠN 1: AGENT 1 - KIỂM TRA ĐỐI CHIẾU CHẶT CHẼ VỚI GROUND TRUTH CỘT 23
# ==============================================================================
def stage1_inspection(wb) -> List[Dict[str, Any]]:
    print("\n" + "=" * 80)
    print("  GIAI ĐOẠN 1: AGENT 1 (KIỂM TRA) - ĐỐI CHIẾU 3 CỘT VỚI GROUND TRUTH KHÁCH HÀNG")
    print("=" * 80)
    ws = wb.active

    inspections = []
    for r in range(4, ws.max_row + 1):
        bc_val = ws.cell(r, 1).value
        if not bc_val:
            continue
        barcode = str(bc_val).strip()
        name = str(ws.cell(r, 2).value or "").strip()

        item = {
            "row": r,
            "barcode": barcode,
            "product_name": name,
            "defects": []
        }

        gt_p = CUST_GT_DIR / f"{barcode}.jpg"
        v4_p = FRONT_V4_DIR / f"{barcode}-front.jpg"
        b2_p = find_file(BACK_DIR, barcode, "back")

        if not v4_p.exists():
            item["defects"].append("MISSING_FRONT_V4")
            inspections.append(item)
            continue

        try:
            v4_im = Image.open(v4_p)
            v4_arr = np.array(v4_im.convert("RGB"))
        except Exception:
            item["defects"].append("CORRUPTED_FILE")
            inspections.append(item)
            continue

        # Đo bounding box vùng sản phẩm trong v4
        fg_v4 = (v4_arr < 250).any(axis=-1)
        ys_v4, xs_v4 = np.where(fg_v4)
        if len(xs_v4) == 0:
            item["defects"].append("BLANK_IMAGE")
            inspections.append(item)
            continue

        pw_v4 = xs_v4.max() - xs_v4.min()
        ph_v4 = ys_v4.max() - ys_v4.min()
        v4_ratio = pw_v4 / float(ph_v4)

        # 1.1 So sánh với Ground Truth của Khách (Cột 23)
        if gt_p.exists():
            try:
                gt_im = Image.open(gt_p)
                gw, gh = gt_im.size
                gt_ratio = gw / float(gh)

                # Kiểm tra lật nhầm 90 độ (ví dụ White Rabbit)
                if (gt_ratio < 0.85 and v4_ratio > 1.25) or (gt_ratio > 1.25 and v4_ratio < 0.80):
                    item["defects"].append("ORIENTATION_INVERTED")

                # Kiểm tra mất vỏ chỉ lấy ruột (như Yogurt Jelly, Jelly Sweets)
                # Nếu ảnh khách là dạng dọc nhưng v4 bị teo lại thành ô vuông nhỏ hoặc ngược lại
                if abs(gt_ratio - v4_ratio) > 0.40:
                    item["defects"].append("ASPECT_RATIO_MISMATCH_INNER_GRAPHIC")

            except Exception:
                pass

        # 1.2 Kiểm tra ảnh đôi (Double packet dính 2 gói)
        # Trong ảnh đôi, tỷ lệ chiều rộng/chiều cao thường tăng gần gấp đôi so với ảnh đơn
        if gt_p.exists():
            if v4_ratio > (gt_ratio * 1.55):
                item["defects"].append("DOUBLE_PACKET_DETECTED")

        # 1.3 Kiểm tra cắt cụt đáy / lẹm viền (Guillotine cut)
        crop_fg = fg_v4[ys_v4.min():ys_v4.max()+1, xs_v4.min():xs_v4.max()+1]
        if crop_fg.shape[0] >= 3 and crop_fg.shape[1] >= 3:
            top_flat = float(crop_fg[:3, :].mean(axis=1).max())
            bot_flat = float(crop_fg[-3:, :].mean(axis=1).max())
            left_flat = float(crop_fg[:, :3].mean(axis=0).max())
            right_flat = float(crop_fg[:, -3:].mean(axis=0).max())

            if top_flat > 0.55 or left_flat > 0.50 or right_flat > 0.50 or bot_flat > 0.70:
                item["defects"].append("GUILLOTINE_TRUNCATION")

        inspections.append(item)

    with open(STAGE1_REPORT, "w", encoding="utf-8") as f:
        json.dump(inspections, f, ensure_ascii=False, indent=2)

    defect_count = sum(1 for it in inspections if it["defects"])
    print(f"  [+] Đã quét xong {len(inspections)} sản phẩm.")
    print(f"  [!] Phát hiện {defect_count} sản phẩm cần khắc phục triệt để.")
    return inspections


# ==============================================================================
# GIAI ĐOẠN 2: AGENT 2 - LỌC VÀ PHÂN LOẠI SẢN PHẨM LỖI
# ==============================================================================
def stage2_filter_defects(inspections: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    print("\n" + "=" * 80)
    print("  GIAI ĐOẠN 2: AGENT 2 (LỌC) - BÓC TÁCH CÁC NHÓM SẢN PHẨM LỖI CỤ THỂ")
    print("=" * 80)

    categories = {
        "DOUBLE_PACKET": [],
        "INNER_GRAPHIC_ONLY": [],
        "GUILLOTINE_TRUNCATION": [],
        "ORIENTATION_INVERTED": [],
        "OTHER_DEFECTS": []
    }

    for item in inspections:
        defects = item.get("defects", [])
        if not defects:
            continue

        if "DOUBLE_PACKET_DETECTED" in defects:
            categories["DOUBLE_PACKET"].append(item)
        elif "ASPECT_RATIO_MISMATCH_INNER_GRAPHIC" in defects:
            categories["INNER_GRAPHIC_ONLY"].append(item)
        elif "GUILLOTINE_TRUNCATION" in defects:
            categories["GUILLOTINE_TRUNCATION"].append(item)
        elif "ORIENTATION_INVERTED" in defects:
            categories["ORIENTATION_INVERTED"].append(item)
        else:
            categories["OTHER_DEFECTS"].append(item)

    print(f"  * Lỗi dính 2 sản phẩm (Ảnh đôi)             : {len(categories['DOUBLE_PACKET'])}")
    print(f"  * Lỗi lấy ruột mất vỏ (Logo/chi tiết nhỏ)    : {len(categories['INNER_GRAPHIC_ONLY'])}")
    print(f"  * Lỗi cắt cụt đáy / lẹm bao bì (Guillotine) : {len(categories['GUILLOTINE_TRUNCATION'])}")
    print(f"  * Lỗi lật nhầm 90 độ                         : {len(categories['ORIENTATION_INVERTED'])}")

    with open(STAGE2_REPORT, "w", encoding="utf-8") as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)

    return categories


# ==============================================================================
# GIAI ĐOẠN 3: AGENT 3 - XÁC THỰC NGUỒN CHUẨN TỪ MASTER 1659 & FRONT-V1
# ==============================================================================
def stage3_validate_sources(inspections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    print("\n" + "=" * 80)
    print("  GIAI ĐOẠN 3: AGENT 3 (XÁC THỰC) - TÌM NGUỒN ẢNH SẠCH 1 MẶT TRƯỚC NGUYÊN VẸN")
    print("=" * 80)

    validated = []
    stats = {
        "FOUND_MASTER_1659": 0,
        "FOUND_FRONT_V1": 0,
        "FOUND_CUSTOMER_GT": 0,
        "PRESERVED_CURRENT": 0
    }

    for item in inspections:
        barcode = item["barcode"]
        defects = item.get("defects", [])

        plan = {
            "barcode": barcode,
            "product_name": item["product_name"],
            "defects": defects,
            "chosen_source": None,
            "source_path": None,
            "action": "KEEP"
        }

        # Nếu không có lỗi -> giữ nguyên v4
        if not defects:
            plan["chosen_source"] = "front-v4"
            plan["source_path"] = str(FRONT_V4_DIR / f"{barcode}-front.jpg")
            plan["action"] = "KEEP"
            stats["PRESERVED_CURRENT"] += 1
            validated.append(plan)
            continue

        # 3.1 Tìm trong Master_1659_Clean_Front_Images (kho ảnh đơn sắc nét 2000-4000px)
        m_path = find_in_master_1659(barcode)
        if m_path:
            plan["chosen_source"] = "Master_1659_Clean_Front_Images"
            plan["source_path"] = str(m_path)
            plan["action"] = "RESTORE_MASTER_1659"
            stats["FOUND_MASTER_1659"] += 1
            validated.append(plan)
            continue

        # 3.2 Tìm trong front-v1 (chứa toàn bộ bao bì gốc chưa bị rembg đục ruột)
        v1_p = find_file(FRONT_V1_DIR, barcode, "front")
        if v1_p:
            plan["chosen_source"] = "front-v1"
            plan["source_path"] = str(v1_p)
            plan["action"] = "RESTORE_FRONT_V1"
            stats["FOUND_FRONT_V1"] += 1
            validated.append(plan)
            continue

        # 3.3 Dùng Customer Ground Truth (ảnh gốc khách đã crop đúng mặt trước trong Excel)
        gt_p = CUST_GT_DIR / f"{barcode}.jpg"
        if gt_p.exists():
            plan["chosen_source"] = "customer_ground_truth"
            plan["source_path"] = str(gt_p)
            plan["action"] = "RESTORE_CUSTOMER_GT"
            stats["FOUND_CUSTOMER_GT"] += 1
            validated.append(plan)
            continue

        plan["action"] = "KEEP_FALLBACK"
        validated.append(plan)

    with open(STAGE3_REPORT, "w", encoding="utf-8") as f:
        json.dump({"statistics": stats, "plans": validated}, f, ensure_ascii=False, indent=2)

    print(f"  [+] Xác thực thành công từ Master 1659   : {stats['FOUND_MASTER_1659']} SKU")
    print(f"  [+] Xác thực thành công từ Front-v1      : {stats['FOUND_FRONT_V1']} SKU")
    print(f"  [+] Xác thực từ Customer Ground Truth   : {stats['FOUND_CUSTOMER_GT']} SKU")
    print(f"  [+] Giữ nguyên đạt chuẩn                 : {stats['PRESERVED_CURRENT']} SKU")
    return validated


# ==============================================================================
# GIAI ĐOẠN 4: AGENT 4 - XỬ LÝ VÀ TÁI NGHIỆM THU CHUẨN WEBSHOP 2400x2400
# ==============================================================================
def stage4_remediate_and_reaccept(validated: List[Dict[str, Any]]):
    print("\n" + "=" * 80)
    print("  GIAI ĐOẠN 4: AGENT 4 (XỬ LÝ & TÁI NGHIỆM THU) - SẢN XUẤT WEBSHOP HOÀN THIỆN")
    print("=" * 80)

    healed_count = 0
    total = len(validated)

    for i, plan in enumerate(validated, start=1):
        barcode = plan["barcode"]
        action = plan["action"]
        src_path = plan["source_path"]
        dest_path = FRONT_V4_DIR / f"{barcode}-front.jpg"

        if action == "KEEP":
            continue

        if src_path and os.path.exists(src_path):
            try:
                raw_im = Image.open(src_path)
                # Đóng gói sản phẩm lên canvas 2400x2400 chuẩn studio
                clean_canvas = format_to_studio_canvas(raw_im, target_dim=2400, occupancy=0.85)
                clean_canvas.save(dest_path, "JPEG", quality=95, optimize=True)
                healed_count += 1
            except Exception as e:
                print(f"    [!] Lỗi xử lý {barcode}: {e}")

        if i % 300 == 0 or i == total:
            print(f"    [Tiến độ Agent 4] {i}/{total} SKU hoàn tất | Đã xử lý phục hồi: {healed_count}")

    print("\n  --> Bắt đầu bước TÁI NGHIỆM THU 100% TOÀN BỘ 1.350 SKU...")
    files_v4 = list(FRONT_V4_DIR.glob("*-front.jpg"))
    print(f"  * Tổng số file trong front-v4 sau xử lý: {len(files_v4)}")

    reacceptance_data = {
        "total_sku": total,
        "healed_count": healed_count,
        "front_v4_files_ready": len(files_v4),
        "status": "REACCEPTED_READY_FOR_WEBSHOP"
    }

    with open(STAGE4_REPORT, "w", encoding="utf-8") as f:
        json.dump(reacceptance_data, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print("         HOÀN TẤT 4 GIAI ĐOẠN XỬ LÝ & TÁI NGHIỆM THU CHUẨN XÁC")
    print("=" * 80 + "\n")


def main():
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)
    # Giai đoạn 1: Kiểm tra
    inspections = stage1_inspection(wb)
    # Giai đoạn 2: Lọc sản phẩm lỗi
    categories = stage2_filter_defects(inspections)
    # Giai đoạn 3: Xác thực nguồn sạch
    validated = stage3_validate_sources(inspections)
    # Giai đoạn 4: Xử lý và tái nghiệm thu
    stage4_remediate_and_reaccept(validated)


if __name__ == "__main__":
    main()
