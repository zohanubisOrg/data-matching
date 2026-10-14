#!/usr/bin/env python3
"""
scripts/run_p0_catalog_matcher.py
----------------------------------
Pipeline P0 Nâng Cấp:
1. Multi-pass Barcode Decoding (ZXing-C++ + YOLO ROI + Deskew + CLAHE + GS1 Checksum)
2. Multi-Subject & Multi-Panel Detection:
   - Đếm số lượng chủ thể trong ảnh (1, 2, 3 chủ thể / panels)
   - Nhận diện ranh giới box từng chủ thể không cắt lẹm bao bì
   - Gán nhãn chính xác: FRONT (mặt trước), BACK (mặt sau), SIDE (mặt cạnh/mặt hông)
3. Image Quality Assessment (IQA: Sharpness, Glare, Framing, Readability)
4. Multi-signal Product Matching (Đối soát Excel 12.10: Brand, Variant, Name, Net Weight)
5. Xuất ảnh chuẩn:
   - Mặt trước (front-v1): siêu sắc nét cho webshop, không lọc bệt màu, định dạng dọc Portrait Studio
   - Mặt sau (back-v1): rõ nét bảng thành phần, dinh dưỡng, barcode, không mất bao bì
6. Xuất audit trail `manifest_p0.json` ghi nhận đầy đủ số lượng chủ thể, panel, điểm IQA.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageEnhance, ImageOps

from product_mapper.vision.multipass_barcode import MultiPassBarcodeDecoder
from product_mapper.vision.quality_assessment import ImageQualityAssessor
from product_mapper.vision.view_classifier import ViewClassifier, PackagingView
from product_mapper.matching.product_matcher import ProductEvidenceMatcher, MatchStatus
from product_mapper.vision.yolo_detector import YOLOPackagingDetector
from product_mapper.vision.subject_panel_detector import SubjectPanelDetector, SubjectRole


def enhance_front_web(image: Image.Image) -> Image.Image:
    """Hoàn thiện ảnh Mặt Trước sắc nét chuẩn webshop: giữ nguyên vẹn chất liệu, không lọc làm bệt màu."""
    image = ImageEnhance.Sharpness(image).enhance(1.18)
    image = ImageEnhance.Color(image).enhance(1.05)
    image = ImageEnhance.Contrast(image).enhance(1.04)
    return image


def enhance_back_clear(image: Image.Image, max_long: int = 2400) -> Image.Image:
    """Hoàn thiện ảnh Mặt Sau: tăng tương phản chữ, rõ bảng dinh dưỡng và barcode."""
    w, h = image.size
    if max(w, h) > max_long:
        scale = max_long / float(max(w, h))
        image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    image = ImageEnhance.Sharpness(image).enhance(1.25)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    return image


def run_pipeline(limit: int = 0, min_front_score: float = 55.0, min_back_score: float = 50.0):
    print("===============================================================================")
    print("   KHỞI CHẠY PIPELINE P0: ĐA CHỦ THỂ (1/2/3 PANELS) + IQA + PRODUCT MATCHING  ")
    print("===============================================================================\n")

    # 1. Khởi tạo các thư mục xuất dữ liệu
    out_base = ROOT / "output" / "catalog_pairs" / "tagged"
    front_v1_dir = out_base / "front-v1"
    back_v1_dir = out_base / "back-v1"
    review_dir = ROOT / "output" / "catalog_pairs" / "review"

    for d in [front_v1_dir, back_v1_dir, review_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Khởi tạo các engine P0
    print("--> Đang khởi tạo các module P0...")
    yolo_det = YOLOPackagingDetector()
    barcode_decoder = MultiPassBarcodeDecoder(yolo_detector=yolo_det)
    iqa = ImageQualityAssessor(yolo_detector=yolo_det)
    matcher = ProductEvidenceMatcher(barcode_decoder=barcode_decoder, quality_assessor=iqa)
    subject_detector = SubjectPanelDetector(yolo_detector=yolo_det, barcode_decoder=barcode_decoder)

    print(f"    Đã nạp {len(matcher.catalog)} mã barcode chuẩn từ Excel 12.10.")

    # 3. Quét ảnh trong kho (hỗ trợ case-insensitive)
    source_dirs = [
        ROOT / "source-import" / "G1_original",
        ROOT / "source-import" / "G2_original",
        ROOT / "source-import" / "G3_Original",
        ROOT / "source-import" / "Nyt25.09.26",
        ROOT / "source-import" / "new_source_from_customer"
    ]
    raw_images: list[Path] = []
    for sdir in source_dirs:
        if sdir.exists():
            for p in sdir.rglob("*"):
                if p.is_file() and p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    raw_images.append(p)

    print(f"--> Tìm thấy {len(raw_images)} ảnh gốc trong kho.")
    if limit > 0:
        raw_images = raw_images[:limit]
        print(f"    (Giới hạn xử lý: {limit} ảnh)")

    # 4. Gom nhóm ảnh theo Barcode
    print("\n--> Bước 1: Quét Barcode Multi-pass & Gom nhóm sản phẩm...")
    barcode_to_images: dict[str, list[tuple[Path, Any]]] = {}
    unresolved_images: list[Path] = []

    for idx, img_path in enumerate(raw_images, start=1):
        try:
            bc_res = barcode_decoder.decode(img_path)
            if bc_res and bc_res.is_valid_checksum and bc_res.text in matcher.catalog:
                barcode_to_images.setdefault(bc_res.text, []).append((img_path, bc_res))
            else:
                unresolved_images.append(img_path)
        except Exception:
            unresolved_images.append(img_path)

        if idx % 100 == 0 or idx == len(raw_images):
            print(f"    Đã quét {idx}/{len(raw_images)} ảnh... Nhận diện {len(barcode_to_images)} mã barcode hợp lệ.")

    # 5. Phân tích đa chủ thể, đánh giá IQA và Ghép cặp chuẩn xác
    print("\n--> Bước 2: Nhận diện Đa Chủ Thể (Box/Role), Đánh giá IQA & Ghép Cặp...")
    manifest: dict[str, Any] = {}
    stats = {
        "matched": 0,
        "review": 0,
        "rejected": 0,
        "front_exported": 0,
        "back_exported": 0,
        "single_subject": 0,
        "dual_panel": 0,
        "three_panel": 0
    }

    for barcode, image_entries in barcode_to_images.items():
        gt_info = matcher.catalog.get(barcode, {})

        evaluated_pairs: list[dict[str, Any]] = []

        for p, bc_res in image_entries:
            try:
                orig_pil = ImageOps.exif_transpose(Image.open(p))
                
                # Nhận diện đa chủ thể & gán nhãn FRONT, BACK, SIDE
                det_res = subject_detector.detect_and_classify_subjects(orig_pil, known_barcode=barcode)
                
                # Trích xuất 2 nửa sạch
                f_crop, b_crop = subject_detector.extract_clean_crops(orig_pil, det_res, padding_ratio=0.04)

                if f_crop is None:
                    # Fallback dùng YOLO portrait
                    f_crop = yolo_det.crop_front_portrait(orig_pil)

                if b_crop is None:
                    b_crop = orig_pil

                f_qual = iqa.assess_front(f_crop)
                b_qual = iqa.assess_back(b_crop, has_barcode=True)

                evaluated_pairs.append({
                    "path": p,
                    "det_res": det_res,
                    "front_crop": f_crop,
                    "back_crop": b_crop,
                    "front_qual": f_qual,
                    "back_qual": b_qual,
                    "front_score": f_qual.total_score,
                    "back_score": b_qual.total_score,
                    "combined_score": (f_qual.total_score * 0.55) + (b_qual.total_score * 0.45)
                })
            except Exception as e:
                continue

        if not evaluated_pairs:
            stats["review"] += 1
            manifest[barcode] = {
                "status": MatchStatus.REVIEW_REQUIRED.value,
                "reason": "failed_panel_extraction",
                "ground_truth": gt_info
            }
            continue

        # Chọn cặp ảnh có tổng điểm IQA cao nhất
        best_pair = max(evaluated_pairs, key=lambda x: x["combined_score"])
        best_p = best_pair["path"]
        best_det = best_pair["det_res"]
        best_f_crop = best_pair["front_crop"]
        best_b_crop = best_pair["back_crop"]
        best_f_score = best_pair["front_score"]
        best_b_score = best_pair["back_score"]

        # Thống kê chế độ chủ thể
        if best_det.mode == "three_panel":
            stats["three_panel"] += 1
        elif best_det.mode == "dual_panel":
            stats["dual_panel"] += 1
        else:
            stats["single_subject"] += 1

        # Đối soát bằng chứng (Product Matching)
        decision = matcher.verify_and_match(
            front_img_input=best_f_crop,
            back_img_input=best_b_crop,
            known_barcode=barcode,
            is_same_photo=True
        )

        # Xuất file nếu đạt chuẩn
        if decision.status == MatchStatus.MATCHED and best_f_score >= min_front_score and best_b_score >= min_back_score:
            stats["matched"] += 1

            # Hoàn thiện ảnh Mặt Trước siêu nét chuẩn Webshop
            final_front = enhance_front_web(best_f_crop)
            front_out_file = front_v1_dir / f"{barcode}-front.jpg"
            final_front.save(front_out_file, "JPEG", quality=95, optimize=True)
            stats["front_exported"] += 1

            # Hoàn thiện ảnh Mặt Sau rõ nét
            final_back = enhance_back_clear(best_b_crop)
            back_out_file = back_v1_dir / f"{barcode}-back.jpg"
            final_back.save(back_out_file, "JPEG", quality=94, optimize=True)
            stats["back_exported"] += 1

            # Ghi nhận chi tiết từng chủ thể
            panel_details = [
                {
                    "role": s.role.value,
                    "box_1000": s.box_1000,
                    "rel_width": s.relative_width,
                    "aspect_ratio": s.aspect_ratio,
                    "has_barcode": s.has_barcode,
                    "reasons": s.reasons
                }
                for s in best_det.subjects
            ]

            manifest[barcode] = {
                "status": MatchStatus.MATCHED.value,
                "barcode": barcode,
                "front_file": str(front_out_file.relative_to(ROOT)),
                "back_file": str(back_out_file.relative_to(ROOT)),
                "source_image": best_p.name,
                "subject_count": best_det.subject_count,
                "panel_mode": best_det.mode,
                "side_panels_count": len(best_det.side_subjects),
                "panels": panel_details,
                "front_score": round(best_f_score, 2),
                "back_score": round(best_b_score, 2),
                "evidence_score": decision.evidence_score,
                "matched_signals": decision.matched_signals,
                "product_name_en": gt_info.get("name_en", ""),
                "brand": gt_info.get("brand", "")
            }
            side_note = f" (+{len(best_det.side_subjects)} Side)" if best_det.side_subjects else ""
            print(f"  [OK] Barcode {barcode} [{best_det.mode}, {best_det.subject_count} subj{side_note}] -> Front: {best_f_score:.1f}, Back: {best_b_score:.1f}")
        else:
            stats["review"] += 1
            manifest[barcode] = {
                "status": MatchStatus.REVIEW_REQUIRED.value,
                "barcode": barcode,
                "source_image": best_p.name,
                "subject_count": best_det.subject_count,
                "panel_mode": best_det.mode,
                "front_score": round(best_f_score, 2),
                "back_score": round(best_b_score, 2),
                "conflict_reasons": decision.conflict_reasons or ["score_below_strict_threshold"],
                "ground_truth": gt_info
            }

    # 6. Ghi manifest_p0.json
    manifest_path = ROOT / "output" / "catalog_pairs" / "manifest_p0.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===============================================================================")
    print("                 BÁO CÁO KẾT QUẢ XUẤT ẢNH PIPELINE P0 ĐA CHỦ THỂ                ")
    print("===============================================================================")
    print(f"  * Tổng mã Barcode xử lý          : {len(barcode_to_images)}")
    print(f"  * Cặp ảnh MATCHED đạt chuẩn 100% : {stats['matched']}")
    print(f"  * Số ảnh Mặt Trước (front-v1)    : {stats['front_exported']} ({front_v1_dir})")
    print(f"  * Số ảnh Mặt Sau (back-v1)       : {stats['back_exported']} ({back_v1_dir})")
    print(f"  * Phân bố chế độ nhận diện       : 3-Panels: {stats['three_panel']} | 2-Panels: {stats['dual_panel']} | Đơn lập: {stats['single_subject']}")
    print(f"  * Số sản phẩm cần REVIEW         : {stats['review']}")
    print(f"  * Audit Trail Manifest đã lưu    : {manifest_path}")
    print("===============================================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy Pipeline P0 Xuất Ảnh Catalog Đa Chủ Thể")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số ảnh quét")
    parser.add_argument("--min-front", type=float, default=55.0, help="Điểm tối thiểu mặt trước")
    parser.add_argument("--min-back", type=float, default=50.0, help="Điểm tối thiểu mặt sau")
    args = parser.parse_args()

    run_pipeline(limit=args.limit, min_front_score=args.min_front, min_back_score=args.min_back)
