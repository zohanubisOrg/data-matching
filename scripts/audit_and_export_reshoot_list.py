#!/usr/bin/env python3
"""Standalone Reshoot Audit & Customer Sheet Export.

Evaluates raw photography across all 5 source folders (G1, G2, G3, G4, Nyt25.09.26)
against the 1,351 items in Rabuta_master_SKU_categories.xlsx.
Detects missing, blurry, unreadable barcode, truncated, or defective items,
and exports an exact customer-matching spreadsheet for reshooting.
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2
import numpy as np
import openpyxl
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image

from product_mapper.zohanubis.barcode_scanner import BarcodeScanResult, ParallelBarcodeScanner
from product_mapper.zohanubis.quality_gate import QualityGate
from product_mapper.zohanubis.reconciler import BarcodeReconciler, CatalogProduct
from product_mapper.zohanubis.sanitizer import ImageSanitizer, RawPhotoRecord

PARTITION_FOLDER_NAMES: Dict[str, str] = {
    "G1": "G1_original",
    "G2": "G2_original",
    "G3": "G3_Original",
    "G4": "G4-original",
    "N25": "Nyt25.09.26",
    "Nyt": "Nyt25.09.26",
}


@dataclass
class ReshootVerdict:
    product: CatalogProduct
    is_reshoot_required: bool
    priority: str  # "BẮT BUỘC", "KHUYẾN NGHỊ", "ĐẠT CHUẨN"
    issue_code: str  # MISSING_RAW, NO_BARCODE, POOR_BLUR, TRUNCATED, QUARANTINE_DEFECT, PASS
    reason_vi: str
    required_angle: str
    guide_vi: str
    blur_score: float = 0.0
    label_sharpness: float = 0.0
    photo_paths: List[Path] = field(default_factory=list)


class ReshootClassifier:
    """Classifies catalog products for reshoot necessity based on multi-criteria quality standards."""

    def __init__(
        self,
        min_blur_score: float = 35.0,
        min_label_sharpness: float = 15.0,
        quarantine_dir: Optional[Path] = None,
        webshop_hd_dir: Optional[Path] = None,
        curated_front_dir: Optional[Path] = None,
        demo_images: Optional[Dict[int, Image.Image]] = None,
    ):
        self.min_blur = min_blur_score
        self.min_sharpness = min_label_sharpness
        self.quarantine_dir = quarantine_dir
        self.demo_images = demo_images or {}
        self.quarantined_barcodes: Dict[str, dict] = {}

        if self.quarantine_dir and self.quarantine_dir.exists():
            for meta_f in self.quarantine_dir.rglob("*_defect.json"):
                try:
                    data = json.loads(meta_f.read_text(encoding="utf-8"))
                    bc = data.get("barcode")
                    if bc:
                        self.quarantined_barcodes[bc] = data
                except Exception:
                    pass

        self.webshop_packshots: Dict[str, Path] = {}
        if webshop_hd_dir and webshop_hd_dir.exists():
            for f in webshop_hd_dir.rglob("*_front.jpg"):
                bc = f.stem.replace("_front", "").strip()
                self.webshop_packshots[bc] = f
                self.webshop_packshots[bc.lstrip("0")] = f

        self.curated_pass_barcodes: Set[str] = set()
        if curated_front_dir and curated_front_dir.exists():
            for f in curated_front_dir.iterdir():
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    bc = re.sub(r"[-_]front$", "", f.stem, flags=re.IGNORECASE).strip()
                    self.curated_pass_barcodes.add(bc)
                    self.curated_pass_barcodes.add(bc.lstrip("0"))

    @staticmethod
    def _compute_image_metrics(img_path: Path) -> Tuple[float, float, int, float]:
        """Calculates blur score (Laplacian var), label sharpness (Sobel gradient), resolution, and glare ratio."""
        try:
            pil_img = ImageSanitizer.load_normalized_image(img_path)
            w_orig, h_orig = pil_img.size
            min_dim = min(w_orig, h_orig)

            cv_rgb = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            cv_gray = cv2.cvtColor(cv_rgb, cv2.COLOR_BGR2GRAY)

            h, w = cv_gray.shape
            # Fast downscale for analysis if image is massive
            if max(h, w) > 1200:
                scale = 1200.0 / max(h, w)
                cv_gray = cv2.resize(cv_gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                h, w = cv_gray.shape

            # 1. Laplacian blur
            blur_score = float(cv2.Laplacian(cv_gray, cv2.CV_32F).var())

            # 2. Central 50% Sobel label sharpness
            cy1, cy2 = int(h * 0.25), int(h * 0.75)
            cx1, cx2 = int(w * 0.25), int(w * 0.75)
            center = cv_gray[cy1:cy2, cx1:cx2]
            sobelx = cv2.Sobel(center, cv2.CV_32F, 1, 0, ksize=3)
            sobely = cv2.Sobel(center, cv2.CV_32F, 0, 1, ksize=3)
            label_sharpness = float(np.mean(np.sqrt(sobelx**2 + sobely**2)))

            # 3. Glare ratio in central packaging area
            glare_pixels = np.sum(center >= 252)
            glare_ratio = float(glare_pixels / max(1, center.size))

            return blur_score, label_sharpness, min_dim, glare_ratio
        except Exception:
            return 0.0, 0.0, 0, 0.0

    def _evaluate_packshot_integrity(
        self,
        packshot_path: Path,
        p: CatalogProduct,
    ) -> Optional[ReshootVerdict]:
        """Examines the actual generated webshop packshot for severed tops, hollowing, fragmented produce, or broken silhouettes."""
        try:
            img = cv2.imread(str(packshot_path))
            if img is None:
                return None
            h, w = img.shape[:2]

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

            y_idx, x_idx = np.where(mask > 0)
            if len(x_idx) == 0:
                return ReshootVerdict(
                    product=p,
                    is_reshoot_required=True,
                    priority="BẮT BUỘC",
                    issue_code="PIPELINE_CUTOFF_DEFECT",
                    reason_vi="Ảnh webshop qua pipeline bị xóa trắng hoàn toàn (không còn thân sản phẩm do ảnh gốc dính nền).",
                    required_angle="Chụp lại trên nền tương phản cao",
                    guide_vi="Đặt sản phẩm trên nền sáng khác màu với bao bì, tránh để đèn chiếu lóa làm mất biên dạng.",
                    photo_paths=[packshot_path],
                )

            min_x, max_x = int(np.min(x_idx)), int(np.max(x_idx))
            min_y, max_y = int(np.min(y_idx)), int(np.max(y_idx))
            prod_w = max_x - min_x + 1
            prod_h = max_y - min_y + 1
            prod_aspect = float(prod_w) / max(1.0, float(prod_h))

            # 1. Check aspect ratio vs demo reference in Column W
            demo = self.demo_images.get(p.row_idx)
            aspect_fail = False
            aspect_desc = ""
            if demo:
                dw, dh = demo.size
                demo_aspect = float(dw) / max(1.0, float(dh))
                diff = abs(prod_aspect - demo_aspect) / max(0.01, demo_aspect)
                if diff > 0.40:
                    aspect_fail = True
                    aspect_desc = f"Khuôn hình bị cắt lệch nghiêm trọng so với mẫu demo (tỉ lệ output={prod_aspect:.2f} vs demo={demo_aspect:.2f})"

            # 2. Connected components check
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
            sig_comps = sum(
                1
                for i in range(1, num_labels)
                if stats[i, cv2.CC_STAT_AREA] >= (h * w) * 0.02
            )

            # 3. Solidity check
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            solidity = 1.0
            if cnts:
                main_cnt = max(cnts, key=cv2.contourArea)
                ca = cv2.contourArea(main_cnt)
                ha = cv2.convexHull(main_cnt)
                if cv2.contourArea(ha) > 0:
                    solidity = ca / cv2.contourArea(ha)

            # 4. Internal white void check (transparent container hollowing)
            sub_mask = mask[min_y : max_y + 1, min_x : max_x + 1]
            white_inside = np.sum(sub_mask == 0) / float(prod_w * prod_h)

            name_lower = p.name_en.lower()
            cat_lower = p.category.lower()

            is_produce = any(
                k in name_lower or k in cat_lower
                for k in [
                    "vegetable", "herb", "chilli", "garlic", "onion", "lemongrass",
                    "cabbage", "rau", "ngò", "hành", "ớt", "sả", "coriander",
                    "spinach", "leaves", "bunch", "tươi", "radish", "jackfruit"
                ]
            )
            is_seafood = any(
                k in name_lower or k in cat_lower
                for k in [
                    "seafood", "fish", "shrimp", "prawn", "crab", "squid", "cá",
                    "tôm", "mực", "chả cá", "bạch tuộc", "frozen", "hải sản", "clam"
                ]
            )
            is_bottle_box = any(
                k in name_lower or k in cat_lower
                for k in [
                    "sauce", "oil", "bottle", "can", "jar", "vinegar", "syrup",
                    "drink", "beverage", "box", "chai", "lọ", "hộp", "lon", "paste",
                    "nước mắm", "xì dầu", "soy sauce"
                ]
            )

            reasons: List[str] = []
            is_transparent_issue = False
            is_touching_issue = False
            is_contrast_issue = False

            if aspect_fail:
                reasons.append(aspect_desc)
                is_touching_issue = True
            if sig_comps > 2:
                reasons.append(f"viền bao bì/cành lá bị vỡ tách làm {sig_comps} phần rời")
                is_contrast_issue = True
            if solidity < 0.60 and not ("herb" in name_lower or "bundle" in name_lower or "bunch" in name_lower):
                reasons.append(f"mất vỏ bao bì hoặc đứt thân (độ lồi={solidity:.2f} < 0.60)")
                is_contrast_issue = True
            if white_inside > 0.45 and (is_bottle_box or is_seafood):
                reasons.append(f"thân chai/bao bì trong suốt bị xóa mất thân ({white_inside*100:.0f}% khoảng trắng)")
                is_transparent_issue = True
            if min_y < 15 and is_bottle_box and np.sum(mask[min_y, min_x : max_x + 1] > 0) > prod_w * 0.40:
                reasons.append("bị cụt nắp hoặc chém phẳng đỉnh chai/hộp")
                is_contrast_issue = True

            if reasons:
                # Select user-friendly refined customer communication phrasing
                if is_transparent_issue:
                    main_reason = "Sản phẩm trong suốt bị mất chi tiết khi qua xử lí. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn"
                    req_angle = "Chụp sản phẩm trong suốt trên phông nền tương phản, tránh bóng lóa"
                    guide = "Sản phẩm trong suốt bị mất chi tiết khi qua xử lí. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng đặt sản phẩm trên phông nền có độ tương phản rõ rệt (tránh nền trùng màu hoặc đèn chiếu xuyên thấu làm mất viền chai/túi nilon)."
                elif is_touching_issue:
                    main_reason = "Sản phẩm dính quá gần nhau nên không lấy được mặt trước. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn"
                    req_angle = "Đặt 1 sản phẩm đứng riêng biệt, tách rời các hộp/mặt sau khác"
                    guide = "Sản phẩm dính quá gần nhau nên không lấy được mặt trước. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng đặt riêng từng sản phẩm đứng độc lập, cách xa các vật thể khác tối thiểu 10cm."
                else:
                    main_reason = "Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn"
                    if is_produce:
                        req_angle = "Chụp rau củ trải phẳng trên phông nền tương phản, vuông góc từ trên xuống"
                        guide = "Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng trải rau củ trên nền tương phản, vuốt phẳng nilon để tránh AI cắt cụt cành/lá."
                    elif is_bottle_box:
                        req_angle = "Chụp chai/hộp đứng thẳng trên nền tương phản, lấy đủ từ đỉnh nắp đến đáy"
                        guide = "Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng đặt chai/hộp trên nền tương phản, lùi máy ảnh xa hơn để lấy trọn vẹn từ nắp chai đến đáy."
                    else:
                        req_angle = "Chụp lại sản phẩm trên phông nền tương phản, lùi xa chừa khoảng trống viền"
                        guide = "Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng chụp trên phông nền có màu tương phản với sản phẩm, chừa khoảng trống biên tối thiểu 15%."

                return ReshootVerdict(
                    product=p,
                    is_reshoot_required=True,
                    priority="BẮT BUỘC",
                    issue_code="PIPELINE_CUTOFF_DEFECT",
                    reason_vi=f"{main_reason} ({'; '.join(reasons)}).",
                    required_angle=req_angle,
                    guide_vi=guide,
                    photo_paths=[packshot_path],
                )
            return None
        except Exception:
            return None

    def evaluate_product(
        self,
        p: CatalogProduct,
        customer_front_map: Optional[Dict[str, Path]] = None,
    ) -> ReshootVerdict:
        """Evaluates a single catalog product against all reshoot rules."""
        bc_clean = p.barcode.strip()
        has_cust_img = False
        if customer_front_map:
            if bc_clean in customer_front_map or bc_clean.lstrip("0") in customer_front_map:
                has_cust_img = True

        all_photos: List[Path] = []
        if p.selected_front_photo:
            all_photos.append(p.selected_front_photo)
        for b in p.verified_back_photos:
            if b not in all_photos:
                all_photos.append(b)

        # 0. Check Verified Curated Pass list (Front directory)
        # Barcodes in Front are already verified good and do NOT need reshoot.
        if bc_clean in self.curated_pass_barcodes or bc_clean.lstrip("0") in self.curated_pass_barcodes:
            return ReshootVerdict(
                product=p,
                is_reshoot_required=False,
                priority="ĐẠT CHUẨN",
                issue_code="PASS",
                reason_vi="Ảnh gốc và packshot đạt chuẩn webshop (đã được kiểm định đạt tại Front, không cần chụp lại).",
                required_angle="Không cần chụp lại",
                guide_vi="",
                photo_paths=all_photos,
            )

        # 1. Completely missing raw photography (Barcode not found in any raw photo)
        if not all_photos and not has_cust_img:
            return ReshootVerdict(
                product=p,
                is_reshoot_required=True,
                priority="BẮT BUỘC",
                issue_code="MISSING_RAW",
                reason_vi="Không tìm thấy ảnh khi tìm kiếm theo barcode (hơn 180 ảnh không có ảnh trong kho dữ liệu ảnh gốc).",
                required_angle="Chụp bổ sung cả 2 mặt: Mặt trước trực diện + Mặt sau có mã vạch",
                guide_vi="Quý khách vui lòng cung cấp ảnh chụp mới: Mặt trước chụp chính diện thẳng góc và mặt sau/đáy chụp rõ nét mã vạch.",
                photo_paths=[],
            )

        # 2. Check pipeline quarantine defect
        defect_data = self.quarantined_barcodes.get(p.barcode) or self.quarantined_barcodes.get(bc_clean.lstrip("0"))
        if defect_data:
            reasons = defect_data.get("fail_reasons", [])
            is_truncated = any("clipped" in r.lower() or "truncated" in r.lower() for r in reasons)
            is_touching = any("multiple" in r.lower() or "touch" in r.lower() or "close" in r.lower() for r in reasons)
            if is_truncated:
                issue_cd = "TRUNCATED"
                reason_vi = "Ảnh mất góc / bị cắt xén biên bao bì ngay từ ảnh gốc."
                angle_req = "Chụp lùi xa máy ảnh, chừa khoảng trống viền tối thiểu 15%"
                guide = "Quý khách vui lòng lùi máy ảnh ra xa hơn, căn chỉnh sản phẩm ở giữa khung hình, chừa mép viền tối thiểu 15-20% để không bị mất góc hay cụt nắp/đáy."
            elif is_touching:
                issue_cd = "TOUCHING"
                reason_vi = "Sản phẩm dính quá gần nhau nên không lấy được mặt trước. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn."
                angle_req = "Đặt 1 sản phẩm đứng riêng biệt, tách rời các hộp khác"
                guide = "Sản phẩm dính quá gần nhau nên không lấy được mặt trước. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng đặt riêng từng sản phẩm đứng độc lập, cách xa các vật thể khác tối thiểu 10cm."
            else:
                issue_cd = "LOW_CONTRAST"
                reason_vi = "Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn."
                angle_req = "Chụp lại mặt trước trên phông nền tương phản rõ rệt"
                guide = "Quý khách vui lòng đặt sản phẩm trên nền có màu tương phản, tránh nền trùng màu với bao bì để hệ thống AI nhận diện chính xác."
            return ReshootVerdict(
                product=p,
                is_reshoot_required=True,
                priority="BẮT BUỘC",
                issue_code=issue_cd,
                reason_vi=reason_vi,
                required_angle=angle_req,
                guide_vi=guide,
                photo_paths=all_photos,
            )

        # 3. Missing verified back barcode photo
        if not p.verified_back_photos and not has_cust_img:
            return ReshootVerdict(
                product=p,
                is_reshoot_required=True,
                priority="BẮT BUỘC",
                issue_code="NO_BARCODE",
                reason_vi="Có ảnh mặt trước nhưng không tìm thấy ảnh chụp mã vạch ở mặt sau để đối soát chuẩn SKU.",
                required_angle="Chụp bổ sung mặt sau / đáy hộp có in mã vạch",
                guide_vi="Chụp cận cảnh mặt sau hoặc cạnh đáy nơi in mã vạch rõ ràng, phẳng phiu, không bị bóng lóa đèn.",
                photo_paths=all_photos,
            )

        # 4. Evaluate physical sharpness, resolution & glare of available photos
        primary_photo = p.selected_front_photo or (p.verified_back_photos[0] if p.verified_back_photos else None)
        blur_sc, sharpness_sc, min_dim, glare_ratio = (0.0, 0.0, 0, 0.0)
        if primary_photo and primary_photo.exists():
            blur_sc, sharpness_sc, min_dim, glare_ratio = self._compute_image_metrics(primary_photo)

            # Low resolution check
            if min_dim > 0 and min_dim < 800:
                return ReshootVerdict(
                    product=p,
                    is_reshoot_required=True,
                    priority="BẮT BUỘC",
                    issue_code="LOW_RESOLUTION",
                    reason_vi=f"Ảnh tìm thấy nhưng lưu về quá mờ để sử dụng làm webshop (độ phân giải thấp {min_dim}px < 800px).",
                    required_angle="Chụp lại bằng camera độ phân giải cao",
                    guide_vi="Cài đặt camera điện thoại ở chế độ chụp gốc 12MP trở lên, không nén gửi qua app làm giảm dung lượng.",
                    blur_score=round(blur_sc, 1),
                    label_sharpness=round(sharpness_sc, 1),
                    photo_paths=all_photos,
                )

            # Critical or soft blur
            if blur_sc < self.min_blur or sharpness_sc < self.min_sharpness:
                return ReshootVerdict(
                    product=p,
                    is_reshoot_required=True,
                    priority="BẮT BUỘC",
                    issue_code="POOR_BLUR",
                    reason_vi=f"Ảnh tìm thấy nhưng lưu về quá mờ để sử dụng làm webshop (out nét / mờ nhòe, độ nét={blur_sc:.1f}).",
                    required_angle="Chụp lại mặt trước rõ nét, đủ ánh sáng",
                    guide_vi="Lau sạch camera, giữ máy cố định và lấy nét trực diện vào chữ nhãn hiệu sản phẩm.",
                    blur_score=round(blur_sc, 1),
                    label_sharpness=round(sharpness_sc, 1),
                    photo_paths=all_photos,
                )

            # Severe glare / flash blowout
            if glare_ratio > 0.18:
                return ReshootVerdict(
                    product=p,
                    is_reshoot_required=True,
                    priority="BẮT BUỘC",
                    issue_code="SEVERE_GLARE",
                    reason_vi=f"Sản phẩm bị bóng lóa đèn flash làm mất chi tiết chữ và mất tương phản viền bao bì ({glare_ratio*100:.1f}% vùng trung tâm bị cháy sáng).",
                    required_angle="Chụp lại với ánh sáng tán xạ, tắt đèn flash trực tiếp",
                    guide_vi="Tắt flash điện thoại, chụp dưới ánh sáng phòng dịu hoặc nghiêng nhẹ góc máy để bóng đèn không phản chiếu thẳng vào ống kính.",
                    blur_score=round(blur_sc, 1),
                    label_sharpness=round(sharpness_sc, 1),
                    photo_paths=all_photos,
                )

        # 5. Evaluate Generated Webshop Packshot for Cutting / Loss of Detail (Produce, Seafood, Bottles & Boxes)
        packshot_path = self.webshop_packshots.get(p.barcode) or self.webshop_packshots.get(bc_clean.lstrip("0"))
        if packshot_path and packshot_path.exists():
            pack_defect = self._evaluate_packshot_integrity(packshot_path, p)
            if pack_defect is not None:
                return pack_defect

        # 6. Fallback for products outside Front (requires reshoot due to quality limitations)
        name_lower = p.name_en.lower()
        cat_lower = p.category.lower()

        is_produce = any(
            k in name_lower or k in cat_lower
            for k in [
                "vegetable", "herb", "chilli", "garlic", "onion", "lemongrass",
                "cabbage", "rau", "ngò", "hành", "ớt", "sả", "coriander",
                "spinach", "leaves", "bunch", "tươi", "radish", "jackfruit", "fruit", "củ", "quả"
            ]
        )
        is_seafood = any(
            k in name_lower or k in cat_lower
            for k in [
                "seafood", "fish", "shrimp", "prawn", "crab", "squid", "cá",
                "tôm", "mực", "chả cá", "bạch tuộc", "frozen", "hải sản", "clam"
            ]
        )
        is_bottle_box = any(
            k in name_lower or k in cat_lower
            for k in [
                "sauce", "oil", "bottle", "can", "jar", "vinegar", "syrup",
                "drink", "beverage", "chai", "lọ", "lon", "paste",
                "nước mắm", "xì dầu", "soy sauce", "glass", "clear"
            ]
        )

        if is_bottle_box:
            return ReshootVerdict(
                product=p,
                is_reshoot_required=True,
                priority="BẮT BUỘC",
                issue_code="TRANSPARENT_LOSS",
                reason_vi="Sản phẩm trong suốt bị mất chi tiết khi qua xử lí. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn.",
                required_angle="Chụp sản phẩm trong suốt trên phông nền tương phản, tránh bóng lóa",
                guide_vi="Sản phẩm trong suốt bị mất chi tiết khi qua xử lí. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng đặt sản phẩm trên phông nền có độ tương phản rõ rệt, ánh sáng dịu để giữ trọn vẹn viền chai/túi.",
                blur_score=round(blur_sc, 1),
                label_sharpness=round(sharpness_sc, 1),
                photo_paths=all_photos,
            )
        elif is_produce or is_seafood:
            return ReshootVerdict(
                product=p,
                is_reshoot_required=True,
                priority="BẮT BUỘC",
                issue_code="LOW_CONTRAST",
                reason_vi="Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn.",
                required_angle="Chụp trải phẳng trên phông nền tương phản rõ rệt, vuông góc từ trên xuống",
                guide_vi="Sản phẩm không có tương phản nền nên xử lí sẽ làm mất chi tiết ảnh. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn. Quý khách vui lòng trải rau củ / hải sản trên nền tương phản, vuốt phẳng bao bì nilon để tránh AI cắt cụt chi tiết.",
                blur_score=round(blur_sc, 1),
                label_sharpness=round(sharpness_sc, 1),
                photo_paths=all_photos,
            )
        else:
            return ReshootVerdict(
                product=p,
                is_reshoot_required=True,
                priority="BẮT BUỘC",
                issue_code="LOW_CONTRAST",
                reason_vi="Sản phẩm không có tương phản nền hoặc ảnh mất góc. Giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn.",
                required_angle="Chụp lại sản phẩm độc lập trên phông nền tương phản cao, chừa mép viền",
                guide_vi="Quý khách vui lòng đặt sản phẩm trên nền tương phản, lùi máy ảnh lấy trọn vẹn bao bì, đủ ánh sáng và không để dính sản phẩm khác.",
                blur_score=round(blur_sc, 1),
                label_sharpness=round(sharpness_sc, 1),
                photo_paths=all_photos,
            )


class ReshootExcelExporter:
    """Clones master catalog structure and outputs structured Reshoot Request Excel with Front & Back packshots."""

    def __init__(
        self,
        master_excel_path: Path,
        webshop_front_dir: Optional[Path] = None,
        webshop_back_dir: Optional[Path] = None,
    ):
        self.master_excel_path = master_excel_path
        self.webshop_front_dir = webshop_front_dir
        self.webshop_back_dir = webshop_back_dir
        self._thumb_cache: Dict[str, bytes] = {}

    def _create_thumbnail_from_bytes(self, img_data: bytes, max_dim: int = 130) -> Optional[OpenpyxlImage]:
        try:
            pil_img = Image.open(io.BytesIO(img_data))
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85, optimize=True)
            buf.seek(0)
            xl_img = OpenpyxlImage(buf)
            xl_img.width = pil_img.width
            xl_img.height = pil_img.height
            return xl_img
        except Exception:
            return None

    def _create_thumbnail_from_file(self, file_path: Path, max_dim: int = 130) -> Optional[OpenpyxlImage]:
        try:
            p_str = str(file_path)
            if p_str in self._thumb_cache:
                buf = io.BytesIO(self._thumb_cache[p_str])
                xl_img = OpenpyxlImage(buf)
                xl_img.width = xl_img.image.width
                xl_img.height = xl_img.image.height
                return xl_img

            with Image.open(file_path) as pil_img:
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG", quality=85, optimize=True)
                b_val = buf.getvalue()
                self._thumb_cache[p_str] = b_val
                buf.seek(0)
                xl_img = OpenpyxlImage(buf)
                xl_img.width = pil_img.width
                xl_img.height = pil_img.height
                return xl_img
        except Exception:
            return None

    @staticmethod
    def _index_image_dir(directory: Optional[Path]) -> Dict[str, Path]:
        m: Dict[str, Path] = {}
        if directory and directory.exists():
            for f in directory.iterdir():
                if f.is_file() and f.suffix.lower() in (".jpg", ".png", ".jpeg", ".webp"):
                    match = re.match(r"^(\d+)", f.name)
                    if match:
                        raw_bc = match.group(1).strip()
                        norm_bc = raw_bc.lstrip("0")
                        m[raw_bc] = f
                        m[norm_bc] = f
        return m

    def _populate_sheet(
        self,
        ws_out,
        sheet_verdicts: List[ReshootVerdict],
        ws_src,
        orig_headers: List[str],
        max_col: int,
        demo_images_by_row: Dict[int, bytes],
        front_map: Dict[str, Path],
        back_map: Dict[str, Path],
        title_text: str,
        banner_text: str,
        embed_thumbnails: bool = True,
    ):
        """Populates an Excel worksheet with audit columns, master columns, and embedded Demo/Front/Back images."""
        # Set up Styles
        font_title = Font(name="Calibri", size=14, bold=True, color="1F497D")
        font_header_audit = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_header_orig = Font(name="Calibri", size=11, bold=True, color="1F497D")
        font_header_img = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Calibri", size=10)
        font_bold = Font(name="Calibri", size=10, bold=True)
        font_dim = Font(name="Calibri", size=9, italic=True, color="7F7F7F")

        fill_header_audit = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
        fill_header_orig = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
        fill_header_img = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

        fill_critical = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # Soft red
        fill_warning = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")   # Soft yellow
        fill_pass = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")      # Soft green

        border_thin = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # Row 1: Document Banner Title
        ws_out.cell(1, 1, value=title_text).font = font_title
        ws_out.row_dimensions[1].height = 28

        # Row 2: Customer Banner & Defect Notification
        cell_note = ws_out.cell(2, 1, value=banner_text)
        cell_note.font = Font(name="Calibri", size=10, bold=True, color="9C0006")
        cell_note.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        cell_note.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws_out.merge_cells("A2:H2")
        ws_out.row_dimensions[2].height = 42

        # Row 3: Headers
        # Columns 1-4: Audit Action Guidance
        audit_headers = [
            "[ƯU TIÊN] Mức độ chụp lại",
            "[LÝ DO] Chi tiết nguyên nhân",
            "[GÓC CHỤP] Yêu cầu",
            "[HƯỚNG DẪN] Thao tác chụp chuẩn",
        ]

        for c_idx, h_name in enumerate(audit_headers, start=1):
            cell = ws_out.cell(3, c_idx, value=h_name)
            cell.font = font_header_audit
            cell.fill = fill_header_audit
            cell.alignment = align_center
            cell.border = border_thin

        # Master columns up to Col 23 (Cols 5 to 27)
        for col_i in range(1, 24):
            h_name = orig_headers[col_i - 1]
            cell = ws_out.cell(3, len(audit_headers) + col_i, value=h_name)
            cell.font = font_header_orig
            cell.fill = fill_header_orig
            cell.alignment = align_center
            cell.border = border_thin

        # Two New Image Columns adjacent to Col 23 (Col AA): Col 28 (AB) and Col 29 (AC)
        cell_front = ws_out.cell(3, 28, value="[WEBSHOP] Ảnh mặt trước hoàn thiện")
        cell_front.font = font_header_img
        cell_front.fill = fill_header_img
        cell_front.alignment = align_center
        cell_front.border = border_thin

        cell_back = ws_out.cell(3, 29, value="[MẶT SAU] Ảnh mặt sau (Back)")
        cell_back.font = font_header_img
        cell_back.fill = fill_header_img
        cell_back.alignment = align_center
        cell_back.border = border_thin

        # Remaining Master Columns (Col 24 onwards -> Col 30 onwards)
        for col_i in range(24, max_col + 1):
            h_name = orig_headers[col_i - 1]
            cell = ws_out.cell(3, len(audit_headers) + col_i + 2, value=h_name)
            cell.font = font_header_orig
            cell.fill = fill_header_orig
            cell.alignment = align_center
            cell.border = border_thin

        ws_out.row_dimensions[3].height = 28

        # Set Column Widths
        ws_out.column_dimensions["A"].width = 18  # Priority
        ws_out.column_dimensions["B"].width = 38  # Reason
        ws_out.column_dimensions["C"].width = 30  # Required angle
        ws_out.column_dimensions["D"].width = 42  # Guide
        ws_out.column_dimensions["AA"].width = 22  # Master Demo image
        ws_out.column_dimensions["AB"].width = 22  # Webshop front image
        ws_out.column_dimensions["AC"].width = 22  # Back photo

        # Populate Data Rows
        out_row_idx = 4
        print(f"[EXCEL EXPORTER] Writing {len(sheet_verdicts)} items into sheet '{ws_out.title}'...")

        for v in sheet_verdicts:
            p = v.product
            r_orig = p.row_idx

            # 1. Fill Audit Columns (Col 1-4)
            cell_prio = ws_out.cell(out_row_idx, 1, value=v.priority)
            cell_prio.alignment = align_center
            cell_prio.border = border_thin
            cell_prio.font = font_bold
            if v.priority == "BẮT BUỘC":
                cell_prio.fill = fill_critical
            elif v.priority == "ĐẠT CHUẨN":
                cell_prio.fill = fill_pass
            else:
                cell_prio.fill = fill_warning

            cell_reason = ws_out.cell(out_row_idx, 2, value=v.reason_vi)
            cell_reason.alignment = align_left
            cell_reason.border = border_thin
            cell_reason.font = font_data

            cell_angle = ws_out.cell(out_row_idx, 3, value=v.required_angle)
            cell_angle.alignment = align_left
            cell_angle.border = border_thin
            cell_angle.font = font_bold

            cell_guide = ws_out.cell(out_row_idx, 4, value=v.guide_vi)
            cell_guide.alignment = align_left
            cell_guide.border = border_thin
            cell_guide.font = font_data

            # 2. Copy Original 31 Master Columns with 2-column offset after Col 23
            for col_i in range(1, max_col + 1):
                orig_val = ws_src.cell(r_orig, col_i).value
                if col_i <= 23:
                    target_col_idx = len(audit_headers) + col_i
                else:
                    target_col_idx = len(audit_headers) + col_i + 2

                cell_dest = ws_out.cell(out_row_idx, target_col_idx, value=orig_val)
                cell_dest.font = font_data
                cell_dest.border = border_thin
                cell_dest.alignment = align_left

                if col_i == 1:
                    cell_dest.number_format = "@"
                    cell_dest.alignment = align_center

            # Set Row Height for comfortable reading and image presentation
            ws_out.row_dimensions[out_row_idx].height = 115

            # 3. Embed Thumbnail 1: Master Demo Image (Col 27 / AA)
            if embed_thumbnails and r_orig in demo_images_by_row:
                img_data = demo_images_by_row[r_orig]
                xl_thumb = self._create_thumbnail_from_bytes(img_data, max_dim=130)
                if xl_thumb is not None:
                    ws_out.add_image(xl_thumb, f"AA{out_row_idx}")

            # 4. Embed Thumbnail 2: Webshop Front HD (Col 28 / AB)
            bc = p.barcode.strip()
            norm_bc = bc.lstrip("0")
            front_file = front_map.get(bc) or front_map.get(norm_bc)
            if embed_thumbnails and front_file and front_file.exists():
                xl_front = self._create_thumbnail_from_file(front_file, max_dim=130)
                if xl_front is not None:
                    ws_out.add_image(xl_front, f"AB{out_row_idx}")
            else:
                cell_f = ws_out.cell(out_row_idx, 28, value="[Chưa có / Cần chụp lại]" if v.is_reshoot_required else "")
                cell_f.font = font_dim
                cell_f.alignment = align_center
                cell_f.border = border_thin

            # 5. Embed Thumbnail 3: Back Photo with Barcode (Col 29 / AC)
            back_file = back_map.get(bc) or back_map.get(norm_bc)
            if embed_thumbnails and back_file and back_file.exists():
                xl_back = self._create_thumbnail_from_file(back_file, max_dim=130)
                if xl_back is not None:
                    ws_out.add_image(xl_back, f"AC{out_row_idx}")
            else:
                cell_b = ws_out.cell(out_row_idx, 29, value="[Không có ảnh mặt sau]")
                cell_b.font = font_dim
                cell_b.alignment = align_center
                cell_b.border = border_thin

            out_row_idx += 1

        # Adjust remaining columns width based on header length
        for col_i in range(1, max_col + 1):
            if col_i <= 23:
                target_col_idx = len(audit_headers) + col_i
            else:
                target_col_idx = len(audit_headers) + col_i + 2
            target_col_letter = openpyxl.utils.get_column_letter(target_col_idx)
            if target_col_letter in ("AA", "AB", "AC"):
                continue
            h_len = len(str(orig_headers[col_i - 1] or ""))
            ws_out.column_dimensions[target_col_letter].width = max(14, min(36, h_len + 4))

        # Freeze Panes at Row 4 & Column E so customer can scroll comfortably
        ws_out.freeze_panes = "E4"

    def export_master_catalog_with_images(
        self,
        output_excel_path: Path,
        wb_src,
        orig_headers: List[str],
        max_col: int,
        demo_images_by_row: Dict[int, bytes],
        front_map: Dict[str, Path],
        back_map: Dict[str, Path],
        embed_thumbnails: bool = True,
    ) -> Path:
        """Exports the full master catalog (1,350 SKUs) with 2 image columns inserted next to 'Ảnh mặt trước'."""
        output_excel_path.parent.mkdir(parents=True, exist_ok=True)
        ws_src = wb_src.active

        wb_out = openpyxl.Workbook()
        ws_out = wb_out.active
        ws_out.title = "Master SKU Categories"

        font_header_orig = Font(name="Calibri", size=11, bold=True, color="1F497D")
        font_header_img = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Calibri", size=10)

        fill_header_orig = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
        fill_header_img = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

        border_thin = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )
        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # Copy rows 1 and 2 from master if present
        for r in (1, 2):
            for c in range(1, max_col + 1):
                v = ws_src.cell(r, c).value
                if v is not None:
                    dest_c = c if c <= 23 else c + 2
                    ws_out.cell(r, dest_c, value=v)

        # Row 3: Headers
        # Cols 1 to 23
        for col_i in range(1, 24):
            cell = ws_out.cell(3, col_i, value=orig_headers[col_i - 1])
            cell.font = font_header_orig
            cell.fill = fill_header_orig
            cell.alignment = align_center
            cell.border = border_thin

        # Col 24: New Webshop Front Header
        cell_f = ws_out.cell(3, 24, value="Ảnh webshop (Front)")
        cell_f.font = font_header_img
        cell_f.fill = fill_header_img
        cell_f.alignment = align_center
        cell_f.border = border_thin

        # Col 25: New Back Header
        cell_b = ws_out.cell(3, 25, value="Ảnh mặt sau (Back)")
        cell_b.font = font_header_img
        cell_b.fill = fill_header_img
        cell_b.alignment = align_center
        cell_b.border = border_thin

        # Col 26 onwards: Remaining original headers
        for col_i in range(24, max_col + 1):
            cell = ws_out.cell(3, col_i + 2, value=orig_headers[col_i - 1])
            cell.font = font_header_orig
            cell.fill = fill_header_orig
            cell.alignment = align_center
            cell.border = border_thin

        ws_out.row_dimensions[3].height = 28

        # Set Column Widths
        ws_out.column_dimensions["W"].width = 22  # Demo image
        ws_out.column_dimensions["X"].width = 22  # Webshop front
        ws_out.column_dimensions["Y"].width = 22  # Back photo

        print(f"[EXCEL EXPORTER] Writing master catalog with embedded images ({ws_src.max_row - 3} rows)...")
        for r_orig in range(4, ws_src.max_row + 1):
            bc_val = str(ws_src.cell(r_orig, 1).value or "").strip()
            norm_bc = bc_val.lstrip("0")

            # Copy original data
            for col_i in range(1, max_col + 1):
                val = ws_src.cell(r_orig, col_i).value
                dest_col = col_i if col_i <= 23 else col_i + 2
                cell = ws_out.cell(r_orig, dest_col, value=val)
                cell.font = font_data
                cell.border = border_thin
                cell.alignment = align_left
                if col_i == 1:
                    cell.number_format = "@"
                    cell.alignment = align_center

            ws_out.row_dimensions[r_orig].height = 115

            # 1. Embed Demo Image at Col 23 (W)
            if embed_thumbnails and r_orig in demo_images_by_row:
                img_data = demo_images_by_row[r_orig]
                xl_thumb = self._create_thumbnail_from_bytes(img_data, max_dim=130)
                if xl_thumb is not None:
                    ws_out.add_image(xl_thumb, f"W{r_orig}")

            # 2. Embed Webshop Front at Col 24 (X)
            front_file = front_map.get(bc_val) or front_map.get(norm_bc)
            if embed_thumbnails and front_file and front_file.exists():
                xl_front = self._create_thumbnail_from_file(front_file, max_dim=130)
                if xl_front is not None:
                    ws_out.add_image(xl_front, f"X{r_orig}")
            else:
                cell_nf = ws_out.cell(r_orig, 24, value="")
                cell_nf.border = border_thin

            # 3. Embed Back Photo at Col 25 (Y)
            back_file = back_map.get(bc_val) or back_map.get(norm_bc)
            if embed_thumbnails and back_file and back_file.exists():
                xl_back = self._create_thumbnail_from_file(back_file, max_dim=130)
                if xl_back is not None:
                    ws_out.add_image(xl_back, f"Y{r_orig}")
            else:
                cell_nb = ws_out.cell(r_orig, 25, value="")
                cell_nb.border = border_thin

        # Adjust column widths
        for col_i in range(1, max_col + 1):
            dest_col = col_i if col_i <= 23 else col_i + 2
            letter = openpyxl.utils.get_column_letter(dest_col)
            if letter in ("W", "X", "Y"):
                continue
            h_len = len(str(orig_headers[col_i - 1] or ""))
            ws_out.column_dimensions[letter].width = max(14, min(36, h_len + 4))

        ws_out.freeze_panes = "D4"
        wb_out.save(output_excel_path)
        print(f"[EXCEL EXPORTER] Saved Master Catalog with images: {output_excel_path} ({output_excel_path.stat().st_size / (1024*1024):.2f} MB)")
        return output_excel_path

    def export(
        self,
        verdicts: List[ReshootVerdict],
        output_excel_path: Path,
        master_output_excel_path: Optional[Path] = None,
        embed_demo_thumbnails: bool = True,
        include_warnings: bool = True,
    ) -> Tuple[Path, Optional[Path]]:
        """Exports 2 separate files: 1 master catalog with added image columns, and 1 customer reshoot sheet."""
        output_excel_path.parent.mkdir(parents=True, exist_ok=True)

        target_verdicts = [
            v for v in verdicts
            if v.is_reshoot_required and (include_warnings or v.priority == "BẮT BUỘC")
        ]

        print(f"\n[EXCEL EXPORTER] Reading Master Excel: {self.master_excel_path.name}...")
        wb_src = openpyxl.load_workbook(self.master_excel_path, data_only=True)
        ws_src = wb_src.active

        # Extract embedded demo images from Column W
        demo_images_by_row: Dict[int, bytes] = {}
        if embed_demo_thumbnails:
            print("[EXCEL EXPORTER] Extracting demo thumbnails from Column W for visual reference...")
            for img in getattr(ws_src, "_images", []):
                try:
                    r_idx = img.anchor._from.row + 1
                    demo_images_by_row[r_idx] = img._data()
                except Exception:
                    continue
            print(f"[EXCEL EXPORTER] Extracted {len(demo_images_by_row)} demo thumbnails from master spreadsheet.")

        # Index Front and Back image directories
        front_map = self._index_image_dir(self.webshop_front_dir)
        back_map = self._index_image_dir(self.webshop_back_dir)
        print(f"[EXCEL EXPORTER] Indexed Front packshots: {len(front_map)} barcodes, Back photos: {len(back_map)} barcodes.")

        # Read master headers at row 3
        max_col = ws_src.max_column
        orig_headers = [ws_src.cell(3, c).value for c in range(1, max_col + 1)]

        # --- FILE 1: Master Catalog with Images (All 1,350 SKUs) ---
        saved_master_path: Optional[Path] = None
        if master_output_excel_path:
            print(f"\n[EXCEL EXPORTER] Exporting File 1: Master Catalog with Added Columns...")
            saved_master_path = self.export_master_catalog_with_images(
                output_excel_path=master_output_excel_path,
                wb_src=wb_src,
                orig_headers=orig_headers,
                max_col=max_col,
                demo_images_by_row=demo_images_by_row,
                front_map=front_map,
                back_map=back_map,
                embed_thumbnails=embed_demo_thumbnails,
            )

        # --- FILE 2: Customer Reshoot Sheet (Only Reshoot SKUs) ---
        print(f"\n[EXCEL EXPORTER] Exporting File 2: Customer Reshoot Request Sheet ({len(target_verdicts)} SKUs)...")
        wb_reshoot = openpyxl.Workbook()
        ws_reshoot = wb_reshoot.active
        ws_reshoot.title = "Danh sách chụp lại (Reshoot)"
        reshoot_banner = (
            "LƯU Ý QUAN TRỌNG: Đã audit hơn 180 ảnh không có ảnh khi tìm kiếm theo barcode, một số ảnh tìm thấy nhưng lưu về quá mờ để sử dụng. "
            "Các lỗi phần lớn gồm: sản phẩm không có tương phản nền (xử lý làm mất chi tiết ảnh), ảnh mất góc / cụt biên bao bì, "
            "và sản phẩm dính quá gần nhau (giới hạn kỹ thuật không thể xử lí nếu ảnh đầu vào không ổn). "
            "Quý khách vui lòng đối chiếu theo các cột [HƯỚNG DẪN CHỤP] & [GÓC CHỤP] ở đầu bảng. Đã nhúng kèm ảnh Demo, ảnh Webshop, và ảnh Mặt sau để đối soát mã vạch."
        )
        self._populate_sheet(
            ws_out=ws_reshoot,
            sheet_verdicts=target_verdicts,
            ws_src=ws_src,
            orig_headers=orig_headers,
            max_col=max_col,
            demo_images_by_row=demo_images_by_row,
            front_map=front_map,
            back_map=back_map,
            title_text=f"DANH SÁCH SẢN PHẨM CẦN CHỤP LẠI (RESHOOT REQUEST) — {len(target_verdicts)} MẶT HÀNG",
            banner_text=reshoot_banner,
            embed_thumbnails=embed_demo_thumbnails,
        )
        wb_reshoot.save(output_excel_path)
        wb_src.close()
        print(f"[EXCEL EXPORTER] Saved customer reshoot sheet: {output_excel_path} ({output_excel_path.stat().st_size / (1024*1024):.2f} MB)")
        return output_excel_path, saved_master_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone Reshoot Quality Audit & Customer Sheet Export"
    )
    parser.add_argument(
        "--excel",
        type=Path,
        default=ROOT / "source-import/Rabuta_master_SKU_categories.xlsx",
        help="Master catalog excel file",
    )
    parser.add_argument(
        "--output-excel",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image/reports/Rabuta_Customer_Reshoot_Request.xlsx",
        help="Path for customer reshoot spreadsheet deliverable",
    )
    parser.add_argument(
        "--partition",
        type=str,
        default=None,
        help="Filter audit to specific partition (e.g. G1, G2, G3, G4, Nyt)",
    )
    parser.add_argument(
        "--min-blur",
        type=float,
        default=35.0,
        help="Threshold for Laplacian blur focus score",
    )
    parser.add_argument(
        "--min-label-sharpness",
        type=float,
        default=15.0,
        help="Threshold for Sobel gradient label sharpness score",
    )
    parser.add_argument(
        "--force-rescan",
        action="store_true",
        help="Ignore cached barcode scan results and re-scan raw photos",
    )
    parser.add_argument(
        "--include-warnings",
        action="store_true",
        default=True,
        help="Include warnings (e.g. soft focus) alongside critical missing items",
    )
    parser.add_argument(
        "--no-thumbnails",
        action="store_true",
        help="Skip embedding demo thumbnails in excel to generate at maximum speed",
    )
    parser.add_argument(
        "--curated-front-dir",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image/webshop_front_hd/Front",
        help="Directory of verified passed front packshots (barcodes in this folder will not need reshooting)",
    )
    parser.add_argument(
        "--webshop-back-dir",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image/webshop_front_hd/Back",
        help="Directory of verified back packshots (to embed into Back column)",
    )
    parser.add_argument(
        "--master-output-excel",
        type=Path,
        default=ROOT / "output/shopify-zohanubis-image/webshop_front_hd/Rabuta_master_SKU_categories-image.xlsx",
        help="Path for full master catalog spreadsheet with added webshop front and back columns",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("=================================================================")
    print("      STANDALONE RESHOOT AUDIT & CUSTOMER SHEET EXPORTER        ")
    print("=================================================================")
    print(f"Master Catalog: {args.excel}")
    print(f"Output Sheet  : {args.output_excel}")
    if args.partition:
        print(f"Target Filter : {args.partition.upper()}")
    print(f"Blur Cutoff   : {args.min_blur} (Label Sharpness: {args.min_label_sharpness})")
    print("-----------------------------------------------------------------")

    t0 = time.time()
    reports_dir = ROOT / "output/shopify-zohanubis-image/reports"
    quarantine_dir = ROOT / "output/shopify-zohanubis-image/quarantine_for_retry"
    customer_dir = ROOT / "source-import/customer-send-me-front-product"

    # Index customer pre-made front repository
    customer_front_map: Dict[str, Path] = {}
    if customer_dir.exists():
        for entry in customer_dir.iterdir():
            if entry.is_file() and entry.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                match = re.match(r"^([0-9A-Za-z]+)-front", entry.name)
                if match:
                    bc = match.group(1).strip()
                    customer_front_map[bc] = entry
                    if bc.startswith("0"):
                        customer_front_map[bc.lstrip("0")] = entry
        print(f"[STAGE 0] Customer pre-made packshots indexed: {len(customer_front_map)} items.")

    # 1. Discover raw photos from 5 source folders
    sanitizer = ImageSanitizer()
    partition_photos = sanitizer.discover_raw_photos()
    all_raw_photos: List[RawPhotoRecord] = []
    for part, recs in partition_photos.items():
        all_raw_photos.extend(recs)
    print(f"[STAGE 1] Discovered {len(all_raw_photos)} raw photos across all 5 source folders.")

    # 2. Multi-angle barcode scanning & caching
    scan_cache_file = reports_dir / "barcode_scan_cache.json"
    scan_results: List[BarcodeScanResult] = []

    if scan_cache_file.exists() and not args.force_rescan:
        print(f"[STAGE 2] Loading cached barcode scan data from: {scan_cache_file.name}")
        with open(scan_cache_file, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        scan_results = [
            BarcodeScanResult(
                path=Path(item["path"]),
                filename=item["filename"],
                partition=item["partition"],
                barcodes=item["barcodes"],
                detected_angle=item["detected_angle"],
                enhancement_used=item["enhancement_used"],
                barcode_centers={bc: tuple(coord) for bc, coord in item.get("barcode_centers", {}).items()},
            )
            for item in cached_data
        ]
        print(f"Loaded {len(scan_results)} photo scan results in 0.05s!")
    else:
        print("[STAGE 2] Running multi-core barcode scanner across raw photos...")
        scanner = ParallelBarcodeScanner()
        scan_results = scanner.scan_records(all_raw_photos)
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
            cache_payload = [
                {
                    "path": str(r.path),
                    "filename": r.filename,
                    "partition": r.partition,
                    "barcodes": r.barcodes,
                    "detected_angle": r.detected_angle,
                    "enhancement_used": r.enhancement_used,
                    "barcode_centers": r.barcode_centers,
                }
                for r in scan_results
            ]
            with open(scan_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, indent=2)
            print(f"Saved barcode scan cache: {scan_cache_file.name}")
        except Exception as e:
            print(f"Warning: could not write scan cache: {e}")

    # 3. 3-Way Catalog Reconciliation
    print("\n[STAGE 3] Reconciling barcodes with Master Catalog...")
    reconciler = BarcodeReconciler(args.excel, reports_dir)
    reconcile_summary = reconciler.reconcile(
        scan_results, customer_front_map=customer_front_map, target_partition=args.partition
    )
    catalog = reconcile_summary.catalog_products

    # Target partition filter
    if args.partition:
        target_part = args.partition.strip().upper()
        if "NYT" in target_part or "N25" in target_part:
            target_part = "Nyt"
        target_prods = [p for p in catalog.values() if p.partition == target_part]
        print(f"Filtering evaluation to Partition '{target_part}': {len(target_prods)} SKUs.")
    else:
        target_prods = list(catalog.values())
        print(f"Evaluating entire catalog: {len(target_prods)} SKUs.")

    # 4. Multi-Criteria Quality Evaluation & Webshop Packshot Inspection
    print("\n[STAGE 4] Executing multi-criteria image quality audit & webshop packshot cut-off inspection...")
    webshop_hd_dir = ROOT / "output/shopify-zohanubis-image/webshop_front_hd"

    # Load demo reference images from Column W of Master Excel
    print("  Loading Column W reference thumbnails for aspect verification...")
    wb_cat_demo = openpyxl.load_workbook(args.excel, data_only=True)
    ws_cat_demo = wb_cat_demo.active
    demo_images_map: Dict[int, Image.Image] = {}
    for img in getattr(ws_cat_demo, "_images", []):
        try:
            r = img.anchor._from.row + 1
            demo_images_map[r] = Image.open(io.BytesIO(img._data()))
        except Exception:
            pass
    wb_cat_demo.close()
    print(f"  Loaded {len(demo_images_map)} demo images from master spreadsheet.")

    classifier = ReshootClassifier(
        min_blur_score=args.min_blur,
        min_label_sharpness=args.min_label_sharpness,
        quarantine_dir=quarantine_dir,
        webshop_hd_dir=webshop_hd_dir,
        curated_front_dir=args.curated_front_dir,
        demo_images=demo_images_map,
    )

    verdicts: List[ReshootVerdict] = []
    stats = collections.Counter()

    for p in target_prods:
        v = classifier.evaluate_product(p, customer_front_map=customer_front_map)
        verdicts.append(v)
        stats[v.issue_code] += 1
        if v.is_reshoot_required:
            stats[f"PRIO_{v.priority}"] += 1

    print("\nAUDIT SUMMARY BREAKDOWN:")
    print(f"  - Total Products Audited        : {len(verdicts)}")
    print(f"  - PASS (Webshop Ready)          : {stats['PASS']}")
    print(f"  - MISSING RAW (No Photo Found)  : {stats['MISSING_RAW']}")
    print(f"  - NO BARCODE (Missing Back/Code): {stats['NO_BARCODE']}")
    print(f"  - POOR BLUR (Severe Out of Focus: {stats['POOR_BLUR']}")
    print(f"  - TRUNCATED (Clipped Border)    : {stats['TRUNCATED']}")
    print(f"  - PIPELINE CUTOFF / DETAIL LOSS : {stats['PIPELINE_CUTOFF_DEFECT']}")
    print(f"  - QUARANTINE DEFECT (Studio Fail: {stats['QUARANTINE_DEFECT']}")
    print(f"  - SOFT FOCUS (Warning/Advisory) : {stats['SOFT_FOCUS']}")
    print("-----------------------------------------------------------------")
    print(f"  * Total Critical Reshoots [BẮT BUỘC]  : {stats['PRIO_BẮT BUỘC']}")
    print(f"  * Total Advisory Reshoots [KHUYẾN NGHỊ]: {stats['PRIO_KHUYẾN NGHỊ']}")
    total_reshoot = stats['PRIO_BẮT BUỘC'] + (stats['PRIO_KHUYẾN NGHỊ'] if args.include_warnings else 0)
    print(f"  * TOTAL SKUs IN RESHOOT DELIVERABLE   : {total_reshoot}")

    # 5. Export Customer-Structured Excel
    print("\n[STAGE 5] Generating Customer Reshoot & Master Spreadsheets...")
    exporter = ReshootExcelExporter(
        master_excel_path=args.excel,
        webshop_front_dir=args.curated_front_dir,
        webshop_back_dir=args.webshop_back_dir,
    )
    out_path, master_path = exporter.export(
        verdicts=verdicts,
        output_excel_path=args.output_excel,
        master_output_excel_path=args.master_output_excel,
        embed_demo_thumbnails=not args.no_thumbnails,
        include_warnings=args.include_warnings,
    )

    # Also copy customer sheet to root of output for convenient access
    root_copy = ROOT / "output/shopify-zohanubis-image/Rabuta_Customer_Reshoot_Request.xlsx"
    try:
        shutil.copy2(out_path, root_copy)
        print(f"Root copy synchronized: {root_copy}")
    except Exception as e:
        print(f"Warning: could not synchronize root copy: {e}")

    elapsed = time.time() - t0
    print("\n=================================================================")
    print(f"AUDIT & EXPORT COMPLETE in {elapsed:.2f}s!")
    print(f"Deliverable 1 (Master + Images)  : {master_path}")
    print(f"Deliverable 2 (Customer Reshoot) : {out_path}")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
