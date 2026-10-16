"""Quality Gate module with balanced 3-tier classification and mathematical verification."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image


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
        return float(cv2.Laplacian(cv_gray, cv2.CV_64F).var())

    def evaluate_packshot(
        self,
        packshot_img: Image.Image,
        alpha_mask: np.ndarray,
        record_id: str,
        barcode: str,
        is_complex_shape: bool = False,
    ) -> QualityMetrics:
        """Evaluates image quality metrics and assigns a balanced decision."""
        h, w = alpha_mask.shape
        img_area = float(h * w)

        warnings: List[str] = []
        fails: List[str] = []

        # 1. Bounding box & clipping check
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

        # Check distance to canvas borders in 2048 canvas
        # If product is on a 2048 canvas, check if any edge is closer than margin_padding_min_px
        clipping_px = min(min_x, min_y, w - 1 - max_x, h - 1 - max_y)
        if clipping_px <= 2:
            fails.append(f"Product touches or is clipped against canvas border (margin={clipping_px}px)")
        elif clipping_px < self.margin_padding_min_px:
            warnings.append(f"Product is tight against border (margin={clipping_px}px)")

        # 2. Connected components & Saliency check
        _, bin_mask = cv2.threshold(alpha_mask, 20, 255, cv2.THRESH_BINARY)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bin_mask)
        # Exclude background label 0
        significant_components = 0
        for i in range(1, num_labels):
            comp_area = stats[i, cv2.CC_STAT_AREA]
            if comp_area >= img_area * 0.04:  # At least 4% of image area
                significant_components += 1

        if significant_components > 1:
            fails.append(f"Multiple disconnected objects detected ({significant_components} components)")

        # 3. Solidity check (Convexity)
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
        if solidity < 0.50:
            fails.append(f"Severe hollowing or broken body detected (solidity={solidity:.3f})")
        elif solidity < min_solidity:
            warnings.append(f"Irregular or hollow silhouette (solidity={solidity:.3f} < {min_solidity})")

        # 4. Sharpness / Blur score
        cv_rgb = cv2.cvtColor(np.array(packshot_img), cv2.COLOR_RGB2BGR)
        cv_gray = cv2.cvtColor(cv_rgb, cv2.COLOR_BGR2GRAY)
        # Measure blur on product region only
        product_crop = cv_gray[min_y : max_y + 1, min_x : max_x + 1]
        blur_score = self._calculate_blur(product_crop) if product_crop.size > 0 else 0.0

        if blur_score < 10.0:
            warnings.append(f"Low surface texture or soft focus (score={blur_score:.1f})")
        elif blur_score < self.min_blur_score:
            warnings.append(f"Mildly soft focus detected (score={blur_score:.1f} < {self.min_blur_score})")

        # 5. Fill ratio
        prod_w = max_x - min_x + 1
        prod_h = max_y - min_y + 1
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
