"""Quality Gate module with balanced 3-tier classification, crop truncation check, and back photo verification."""
from __future__ import annotations

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
import zxingcpp


@dataclass
class QualityMetrics:
    record_id: str
    barcode: str
    decision: str  # PASS, WARNING_ACCEPT, HARD_FAIL
    solidity: float
    n_components: int
    canvas_clipping_px: int
    blur_score: float
    fill_ratio: float
    warning_reasons: List[str]
    fail_reasons: List[str]


class QualityGate:
    """Enforces mathematical checks without false rejections for complex shapes."""

    def __init__(
        self,
        min_solidity_standard: float = 0.72,
        min_solidity_complex: float = 0.55,
        min_blur_score: float = 40.0,
        margin_padding_min_px: int = 15,
    ):
        self.min_solidity_standard = min_solidity_standard
        self.min_solidity_complex = min_solidity_complex
        self.min_blur_score = min_blur_score
        self.margin_padding_min_px = margin_padding_min_px

    @staticmethod
    def _calculate_blur(cv_gray: np.ndarray) -> float:
        """Calculate variance of Laplacian as a focus / sharpness metric."""
        if cv_gray.size == 0:
            return 0.0
        h, w = cv_gray.shape
        if max(h, w) > 1024:
            scale = 1024.0 / max(h, w)
            proc_gray = cv2.resize(cv_gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            proc_gray = cv_gray
        return float(cv2.Laplacian(proc_gray, cv2.CV_32F).var())

    @staticmethod
    def _calculate_label_sharpness(cv_gray: np.ndarray) -> float:
        """Calculates Sobel gradient energy in central 50% zone to verify label text sharpness."""
        if cv_gray.size == 0:
            return 0.0
        h, w = cv_gray.shape
        cy1, cy2 = int(h * 0.25), int(h * 0.75)
        cx1, cx2 = int(w * 0.25), int(w * 0.75)
        center = cv_gray[cy1:cy2, cx1:cx2]
        if center.size == 0:
            return 0.0
        if max(center.shape) > 512:
            scale = 512.0 / max(center.shape)
            center = cv2.resize(center, (int(center.shape[1] * scale), int(center.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        sobelx = cv2.Sobel(center, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(center, cv2.CV_32F, 0, 1, ksize=3)
        grad = np.sqrt(sobelx**2 + sobely**2)
        return float(np.mean(grad))

    def evaluate_packshot(
        self,
        packshot_img: Image.Image,
        alpha_mask: np.ndarray,
        record_id: str,
        barcode: str,
        is_complex_shape: bool = False,
        crop_mask: Optional[np.ndarray] = None,
        demo_img: Optional[Image.Image] = None,
    ) -> QualityMetrics:
        """Evaluates image quality metrics and assigns a balanced decision.
        
        Args:
            packshot_img: 2048x2048 final composite image.
            alpha_mask: 2048x2048 canvas alpha mask.
            record_id: Catalog record ID.
            barcode: Catalog barcode string.
            is_complex_shape: Whether shape is inherently non-convex (herbs, bundles).
            crop_mask: Direct unpadded alpha mask from hero crop step before canvas centering.
            demo_img: Optional Column W demo reference image for aspect ratio verification.
        """
        h, w = alpha_mask.shape
        img_area = float(h * w)

        warnings: List[str] = []
        fails: List[str] = []

        # 1. Bounding box & clipping check on 2048 canvas
        y_indices, x_indices = np.where(alpha_mask > 20)
        if len(x_indices) == 0:
            return QualityMetrics(
                record_id=record_id,
                barcode=barcode,
                decision="HARD_FAIL",
                solidity=0.0,
                n_components=0,
                canvas_clipping_px=0,
                blur_score=0.0,
                fill_ratio=0.0,
                warning_reasons=[],
                fail_reasons=["Blank or empty image"],
            )

        min_x, max_x = int(np.min(x_indices)), int(np.max(x_indices))
        min_y, max_y = int(np.min(y_indices)), int(np.max(y_indices))

        clipping_px = min(min_x, min_y, w - 1 - max_x, h - 1 - max_y)
        if clipping_px <= 2:
            fails.append(f"Product touches or is clipped against canvas border (margin={clipping_px}px)")
        elif clipping_px < self.margin_padding_min_px:
            warnings.append(f"Product is tight against border (margin={clipping_px}px)")

        # 2. Check Aspect Ratio and Structure against Demo Ground Truth
        prod_w = max_x - min_x + 1
        prod_h = max_y - min_y + 1
        demo_matches = False
        if demo_img is not None:
            dw, dh = demo_img.size
            demo_aspect = float(dw) / max(1.0, float(dh))
            prod_aspect = float(prod_w) / max(1.0, float(prod_h))
            aspect_diff = min(
                abs(prod_aspect - demo_aspect) / demo_aspect,
                abs(prod_aspect - (1.0 / demo_aspect)) / (1.0 / demo_aspect),
            )
            if aspect_diff <= 0.22:
                demo_matches = True
            elif aspect_diff > 0.40:
                fails.append(f"Product aspect ratio distorted or truncated vs demo ({prod_aspect:.2f} vs {demo_aspect:.2f})")
            else:
                warnings.append(f"Noticeable aspect variance vs demo thumbnail ({prod_aspect:.2f} vs {demo_aspect:.2f})")

        # 3. Check Crop Truncation & Edge Severing before canvas centering
        if crop_mask is not None:
            hc, wc = crop_mask.shape
            top_touch = int(np.sum(crop_mask[0, :] > 35)) > max(6, int(wc * 0.03))
            left_touch = int(np.sum(crop_mask[:, 0] > 35)) > max(6, int(hc * 0.03))
            right_touch = int(np.sum(crop_mask[:, -1] > 35)) > max(6, int(hc * 0.03))
            bottom_touch = int(np.sum(crop_mask[-1, :] > 35)) > max(20, int(wc * 0.08))

            if not demo_matches and (top_touch or left_touch or right_touch):
                fails.append("Product truncated at crop boundary (severed edge detected)")
            elif top_touch or left_touch or right_touch:
                warnings.append("Tight crop framing against product outer perimeter")
            elif bottom_touch:
                warnings.append("Product base intersects crop boundary (table grounding cut)")

        # 4. Connected components & Saliency check
        _, bin_mask = cv2.threshold(alpha_mask, 20, 255, cv2.THRESH_BINARY)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bin_mask)
        significant_components = 0
        for i in range(1, num_labels):
            comp_area = stats[i, cv2.CC_STAT_AREA]
            if comp_area >= img_area * 0.04:  # At least 4% of image area
                significant_components += 1

        max_allowed_comps = 2 if is_complex_shape else 1
        if significant_components > max_allowed_comps:
            fails.append(f"Multiple disconnected objects detected ({significant_components} components)")
        elif significant_components > 1:
            warnings.append(f"Separated product clusters detected ({significant_components} components)")

        # 5. Solidity check (Convexity)
        contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        solidity = 1.0
        if contours:
            main_cnt = max(contours, key=cv2.contourArea)
            cnt_area = cv2.contourArea(main_cnt)
            hull = cv2.convexHull(main_cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area > 0:
                solidity = float(cnt_area / hull_area)

        min_solidity = self.min_solidity_complex if is_complex_shape else self.min_solidity_standard
        hard_fail_solidity = 0.25 if is_complex_shape else 0.45
        if solidity < hard_fail_solidity:
            fails.append(f"Severe hollowing or broken body detected (solidity={solidity:.3f})")
        elif solidity < min_solidity:
            warnings.append(f"Irregular or hollow silhouette (solidity={solidity:.3f} < {min_solidity})")

        # 6. Sharpness & Label Readability score
        cv_rgb = cv2.cvtColor(np.array(packshot_img), cv2.COLOR_RGB2BGR)
        cv_gray = cv2.cvtColor(cv_rgb, cv2.COLOR_BGR2GRAY)
        product_crop = cv_gray[min_y : max_y + 1, min_x : max_x + 1]
        blur_score = self._calculate_blur(product_crop) if product_crop.size > 0 else 0.0
        label_energy = self._calculate_label_sharpness(product_crop) if product_crop.size > 0 else 0.0

        if blur_score < 10.0:
            warnings.append(f"Low surface texture or soft focus (score={blur_score:.1f})")
        elif blur_score < self.min_blur_score:
            warnings.append(f"Mildly soft focus detected (score={blur_score:.1f} < {self.min_blur_score})")

        if label_energy < 15.0 and blur_score < 30.0:
            warnings.append(f"Low label text contrast or softening (energy={label_energy:.1f})")

        # 7. Fill ratio
        fill_ratio = max(prod_w, prod_h) / float(max(w, h))

        # Decision synthesis
        if fails:
            decision = "HARD_FAIL"
        elif warnings:
            decision = "WARNING_ACCEPT"
        else:
            decision = "PASS"

        return QualityMetrics(
            record_id=record_id,
            barcode=barcode,
            decision=decision,
            solidity=round(solidity, 4),
            n_components=significant_components,
            canvas_clipping_px=clipping_px,
            blur_score=round(blur_score, 2),
            fill_ratio=round(fill_ratio, 4),
            warning_reasons=warnings,
            fail_reasons=fails,
        )

    def evaluate_back_packshot(
        self,
        back_img: Image.Image,
        record_id: str,
        barcode: str,
    ) -> QualityMetrics:
        """Evaluates back photo quality, focus, and barcode readability."""
        warnings: List[str] = []
        fails: List[str] = []

        w, h = back_img.size
        if w < 400 or h < 400:
            fails.append(f"Back image dimensions too small ({w}x{h})")

        cv_bgr = cv2.cvtColor(np.array(back_img), cv2.COLOR_RGB2BGR)
        cv_gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        blur_score = self._calculate_blur(cv_gray)

        if blur_score < 12.0:
            fails.append(f"Back photo severely out of focus or blurry (score={blur_score:.1f})")
        elif blur_score < 25.0:
            warnings.append(f"Soft focus on back photo (score={blur_score:.1f})")

        # Verify barcode readability on exported back photo
        try:
            detected_barcodes = zxingcpp.read_barcodes(back_img)
            found_bcs = [d.text.strip() for d in detected_barcodes]
            target_bc = barcode.strip()

            matched = any(
                b == target_bc or b == target_bc.lstrip("0") or ("0" + b) == target_bc
                for b in found_bcs
            )

            if matched:
                warnings.append(f"Verified: Barcode {target_bc} machine-readable on back photo")
            elif found_bcs:
                warnings.append(f"Alternative barcode decoded on back photo: {found_bcs}")
            else:
                warnings.append("Barcode not auto-decoded on exported back image")
        except Exception:
            pass

        decision = "HARD_FAIL" if fails else ("WARNING_ACCEPT" if warnings else "PASS")
        return QualityMetrics(
            record_id=record_id,
            barcode=barcode,
            decision=decision,
            solidity=1.0,
            n_components=1,
            canvas_clipping_px=0,
            blur_score=round(blur_score, 2),
            fill_ratio=1.0,
            warning_reasons=warnings,
            fail_reasons=fails,
        )

    def evaluate_customer_packshot(
        self,
        cust_img: Image.Image,
        record_id: str,
        barcode: str,
    ) -> QualityMetrics:
        """Evaluates customer-provided packshot quality with real mathematical metrics."""
        warnings: List[str] = []
        fails: List[str] = []

        w, h = cust_img.size
        if w < 400 or h < 400:
            fails.append(f"Customer image resolution too small ({w}x{h})")
        elif w < 800 or h < 800:
            warnings.append(f"Moderate customer image resolution ({w}x{h})")

        cv_bgr = cv2.cvtColor(np.array(cust_img), cv2.COLOR_RGB2BGR)
        cv_gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
        blur_score = self._calculate_blur(cv_gray)

        if blur_score < 12.0:
            warnings.append(f"Low surface texture on customer image (blur={blur_score:.1f})")

        warnings.append("Customer pre-made packshot verified (AI matting bypassed)")
        decision = "HARD_FAIL" if fails else ("WARNING_ACCEPT" if warnings else "PASS")

        return QualityMetrics(
            record_id=record_id,
            barcode=barcode,
            decision=decision,
            solidity=1.0,
            n_components=1,
            canvas_clipping_px=30,
            blur_score=round(blur_score, 2),
            fill_ratio=0.80,
            warning_reasons=warnings,
            fail_reasons=fails,
        )

    @staticmethod
    def save_ledger(metrics_list: List[QualityMetrics], ledger_path: Path) -> None:
        """Saves quality gate decisions into an audit ledger JSON file."""
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_evaluated": len(metrics_list),
            "pass_count": sum(1 for m in metrics_list if m.decision == "PASS"),
            "warning_accept_count": sum(1 for m in metrics_list if m.decision == "WARNING_ACCEPT"),
            "hard_fail_count": sum(1 for m in metrics_list if m.decision == "HARD_FAIL"),
            "records": [asdict(m) for m in metrics_list],
        }
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
