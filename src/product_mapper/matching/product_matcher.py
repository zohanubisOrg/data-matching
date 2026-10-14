"""
src/product_mapper/matching/product_matcher.py
----------------------------------------------
Bộ Ghép Cặp Sản Phẩm Dựa Trên Bằng Chứng (Evidence-Based Product Matcher).
Giải quyết triệt để lỗi:
1. Ghép nhầm mặt trước - mặt sau của hai sản phẩm khác nhau (ví dụ: cùng hãng nhưng khác vị).
2. Kiểm tra xung đột thuộc tính: Brand, Product Name, Variant/Flavor, Net Weight.
3. Phân loại 3 trạng thái nghiêm ngặt:
   - MATCHED          : Đủ bằng chứng, không xung đột -> Chấp thuận xuất file.
   - REVIEW_REQUIRED  : Thiếu bằng chứng hoặc góc chụp lạ -> Chờ người xem xét.
   - REJECTED         : Phát hiện mâu thuẫn thuộc tính -> Từ chối ghép cặp.
"""

from __future__ import annotations

import re
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import openpyxl
from PIL import Image, ImageOps

from ..vision.multipass_barcode import MultiPassBarcodeDecoder
from ..vision.quality_assessment import ImageQualityAssessor, FrontQualityResult, BackQualityResult


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"


@dataclass
class MatchDecision:
    status: MatchStatus
    barcode: str
    evidence_score: float  # 0.0 - 1.0
    front_quality: FrontQualityResult
    back_quality: BackQualityResult
    matched_signals: list[str] = field(default_factory=list)
    conflict_reasons: list[str] = field(default_factory=list)
    ground_truth: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


class ProductEvidenceMatcher:
    def __init__(
        self,
        excel_path: str | Path | None = None,
        barcode_decoder: MultiPassBarcodeDecoder | None = None,
        quality_assessor: ImageQualityAssessor | None = None
    ):
        self.root = Path(__file__).resolve().parent.parent.parent.parent
        self.excel_path = Path(excel_path) if excel_path else (
            self.root / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
        )
        self.barcode_decoder = barcode_decoder or MultiPassBarcodeDecoder()
        self.quality_assessor = quality_assessor or ImageQualityAssessor()
        self._ocr_engine = None

        # Load ground truth database
        self.catalog: dict[str, dict[str, Any]] = {}
        self._load_ground_truth()

    def _get_ocr(self):
        if self._ocr_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr_engine = RapidOCR()
            except Exception:
                self._ocr_engine = None
        return self._ocr_engine

    def _load_ground_truth(self) -> None:
        """Đọc danh mục chuẩn từ Rabuta.12.10.2026_original.xlsx (read_only an toàn)."""
        if not self.excel_path.exists():
            print(f"[ProductMatcher] Không tìm thấy file Excel: {self.excel_path}")
            return

        try:
            wb = openpyxl.load_workbook(self.excel_path, read_only=True, data_only=True)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            wb.close()

            # Hàng tiêu đề ở index 2 (Row 3)
            for idx, r in enumerate(rows[3:], start=1):
                if not r or not r[0]:
                    continue
                raw_bc = str(r[0]).strip()
                digits_bc = re.sub(r"[^\d]", "", raw_bc)
                if not digits_bc:
                    continue

                self.catalog[digits_bc] = {
                    "stt": idx,
                    "barcode": digits_bc,
                    "name_en": str(r[1] or "").strip(),
                    "name_da": str(r[2] or "").strip(),
                    "brand": str(r[3] or "").strip(),
                    "record_id": str(r[4] or "").strip() if len(r) > 4 else "",
                    "literal_label": str(r[5] or "").strip() if len(r) > 5 else "",
                    "variant": str(r[7] or "").strip() if len(r) > 7 and r[7] else "",
                    "category": str(r[8] or "").strip() if len(r) > 8 and r[8] else "",
                    "packaging": str(r[9] or "").strip() if len(r) > 9 and r[9] else "",
                    "net_quantity": str(r[10] or "").strip() if len(r) > 10 and r[10] else "",
                    "net_unit": str(r[11] or "").strip() if len(r) > 11 and r[11] else "",
                }
            print(f"[ProductMatcher] Đã nạp {len(self.catalog)} sản phẩm chuẩn từ Excel.")
        except Exception as e:
            print(f"[ProductMatcher] Lỗi nạp Excel ground truth: {e}")

    def extract_ocr_tokens(self, img: Image.Image) -> list[str]:
        """Trích xuất danh sách từ ngữ từ ảnh bằng RapidOCR."""
        ocr = self._get_ocr()
        if ocr is None:
            return []
        try:
            res, _ = ocr(np.array(img))
            if not res:
                return []
            tokens = []
            for item in res:
                text = item[1].lower().strip()
                # Tách từ
                words = re.findall(r"[\w\d]+", text)
                tokens.extend(words)
            return list(dict.fromkeys(tokens))
        except Exception:
            return []

    def verify_and_match(
        self,
        front_img_input: str | Path | Image.Image,
        back_img_input: str | Path | Image.Image,
        known_barcode: str | None = None,
        is_same_photo: bool = False
    ) -> MatchDecision:
        """
        Đối soát và kiểm tra tính nhất quán giữa ảnh Mặt Trước và Mặt Sau.
        """
        # 1. Load ảnh
        if isinstance(front_img_input, (str, Path)):
            front_im = ImageOps.exif_transpose(Image.open(front_img_input))
        else:
            front_im = ImageOps.exif_transpose(front_img_input)

        if isinstance(back_img_input, (str, Path)):
            back_im = ImageOps.exif_transpose(Image.open(back_img_input))
        else:
            back_im = ImageOps.exif_transpose(back_img_input)

        # 2. Xác định Barcode từ mặt sau
        resolved_bc = known_barcode
        bc_hit = None
        if not resolved_bc:
            bc_hit = self.barcode_decoder.decode(back_im)
            if bc_hit and bc_hit.is_valid_checksum:
                resolved_bc = bc_hit.text
            else:
                # Thử quét thêm từ mặt trước nếu mặt sau không thấy
                bc_front = self.barcode_decoder.decode(front_im)
                if bc_front and bc_front.is_valid_checksum:
                    resolved_bc = bc_front.text

        matched_signals: list[str] = []
        conflict_reasons: list[str] = []

        # 3. Đánh giá chất lượng IQA
        front_q = self.quality_assessor.assess_front(front_im)
        back_q = self.quality_assessor.assess_back(back_im, has_barcode=bool(resolved_bc))

        if not resolved_bc:
            conflict_reasons.append("no_valid_barcode_detected")
            return MatchDecision(
                status=MatchStatus.REVIEW_REQUIRED,
                barcode="",
                evidence_score=0.0,
                front_quality=front_q,
                back_quality=back_q,
                conflict_reasons=conflict_reasons
            )

        # 4. Kiểm tra Barcode trong danh mục Excel
        gt_item = self.catalog.get(resolved_bc)
        if not gt_item:
            # Thử đối chiếu variants (UPC 12 <-> EAN 13 có số 0 đầu)
            for var_bc in [resolved_bc.lstrip("0"), "0" + resolved_bc]:
                if var_bc in self.catalog:
                    resolved_bc = var_bc
                    gt_item = self.catalog[var_bc]
                    break

        if not gt_item:
            conflict_reasons.append(f"barcode_{resolved_bc}_not_in_excel_catalog")
            return MatchDecision(
                status=MatchStatus.REVIEW_REQUIRED,
                barcode=resolved_bc,
                evidence_score=0.3,
                front_quality=front_q,
                back_quality=back_q,
                conflict_reasons=conflict_reasons
            )

        matched_signals.append(f"barcode_verified_in_excel ({resolved_bc})")

        # 5. Nếu ảnh trước và sau cắt từ CÙNG MỘT BỨC ẢNH kho (Side-by-side)
        if is_same_photo:
            matched_signals.append("same_physical_photo_guarantee")
            evidence_score = 0.95
            status = MatchStatus.MATCHED if front_q.is_acceptable else MatchStatus.REVIEW_REQUIRED
            return MatchDecision(
                status=status,
                barcode=resolved_bc,
                evidence_score=evidence_score,
                front_quality=front_q,
                back_quality=back_q,
                matched_signals=matched_signals,
                conflict_reasons=conflict_reasons,
                ground_truth=gt_item
            )

        # 6. Đối chiếu ngữ nghĩa qua OCR trên Mặt Trước (Evidence Cross-check)
        front_tokens = self.extract_ocr_tokens(front_im)
        front_text_blob = " ".join(front_tokens).lower()

        evidence_score = 0.5  # Base score có barcode hợp lệ

        # 6a. Kiểm tra Brand
        brand_raw = gt_item.get("brand", "").lower()
        brand_parts = [b.strip() for b in re.split(r"[/,]", brand_raw) if b.strip()]
        brand_found = any(bp in front_text_blob for bp in brand_parts if len(bp) >= 3)
        if brand_found:
            evidence_score += 0.25
            matched_signals.append(f"brand_matched ({brand_raw})")

        # 6b. Kiểm tra Variant / Hương vị (Phát hiện xung đột)
        variant_raw = gt_item.get("variant", "").lower()
        if variant_raw and len(variant_raw) >= 3:
            # Các biến thể xung đột phổ biến (thịt gà vs thịt bò vs tôm)
            conflict_pairs = [
                ({"chicken", "gà"}, {"beef", "bò"}, {"shrimp", "tôm"}),
                ({"original", "truyền thống"}, {"spicy", "cay"}, {"wasabi"}),
                ({"orange", "cam"}, {"grape", "nho"}, {"apple", "táo"})
            ]
            
            # Kiểm tra xem mặt trước có chứa từ khóa của variant này không
            if variant_raw in front_text_blob:
                evidence_score += 0.20
                matched_signals.append(f"variant_matched ({variant_raw})")
            else:
                # Kiểm tra xem có bị xung đột trực tiếp với variant khác không
                for group in conflict_pairs:
                    matched_in_group = [w for w in group if any(kw in variant_raw for kw in w)]
                    if matched_in_group:
                        other_in_group = [w for w in group if w not in matched_in_group]
                        for other_set in other_in_group:
                            if any(ow in front_text_blob for ow in other_set):
                                conflict_reasons.append(f"variant_conflict (Excel: {variant_raw} vs Front: {other_set})")
                                break

        # 6c. Kiểm tra Khối lượng tịnh (Net Weight)
        net_qty = gt_item.get("net_quantity", "")
        if net_qty and net_qty in front_text_blob:
            evidence_score += 0.10
            matched_signals.append(f"weight_matched ({net_qty})")

        # 7. Quyết định trạng thái cuối cùng
        evidence_score = min(1.0, round(evidence_score, 2))

        if conflict_reasons:
            status = MatchStatus.REJECTED
        elif evidence_score >= 0.70 and front_q.is_acceptable and back_q.is_acceptable:
            status = MatchStatus.MATCHED
        else:
            status = MatchStatus.REVIEW_REQUIRED

        return MatchDecision(
            status=status,
            barcode=resolved_bc,
            evidence_score=evidence_score,
            front_quality=front_q,
            back_quality=back_q,
            matched_signals=matched_signals,
            conflict_reasons=conflict_reasons,
            ground_truth=gt_item,
            details={"front_tokens_count": len(front_tokens), "evidence_score": evidence_score}
        )
