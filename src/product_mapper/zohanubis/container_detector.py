"""Rigid container detector for bottles, jars, cans, and upright boxes.

Classifies products using a deterministic 3-tier approach:
1. Volume regex (e.g. 700 ml, 1.5 L, 330 ml)
2. Packaging & category keyword semantics
3. Visual foreground aspect ratio and contour geometry (H/W >= 1.6)
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image


class RigidContainerDetector:
    """Detects whether a catalog SKU represents a bottle, jar, can, or upright box."""

    VOLUME_REGEX = re.compile(
        r"\b\d+(?:[.,]\d+)?\s*(?:ml|l|liter|litres?|cl|fl\s*oz)\b", re.IGNORECASE
    )

    CONTAINER_KEYWORDS = {
        "bottle", "jar", "can", "tin", "tub", "carton", "box",
        "sauce", "paste", "syrup", "vinegar", "juice", "drink", "beverage",
        "oil", "soju", "soda", "wine", "beer", "water", "tea", "coffee",
        "dressing", "mayo", "mayonnaise", "ketchup", "honey", "extract"
    }

    CONTAINER_CATEGORIES = {
        "sauces and condiments", "cooking sauces", "fish sauce",
        "beverages", "drinks", "curry pastes", "seasoning mixes",
        "preserved vegetables", "pickled vegetables", "oils"
    }

    @classmethod
    def is_container_by_metadata(
        cls, name: str, category: str = ""
    ) -> Tuple[bool, str]:
        """Checks if product metadata indicates a liquid or rigid container.
        
        Returns:
            (is_container, detection_reason)
        """
        name_lower = name.lower()
        cat_lower = category.lower()

        # 1. Volume indicator is high confidence liquid/container
        if cls.VOLUME_REGEX.search(name_lower):
            return True, "volume_unit"

        # 2. Packaging / container keywords in title
        for kw in cls.CONTAINER_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", name_lower):
                return True, f"keyword_{kw}"

        # 3. Category match
        for cat in cls.CONTAINER_CATEGORIES:
            if cat in cat_lower:
                return True, f"category_{cat}"

        return False, "non_container"

    @classmethod
    def is_container_by_shape(
        cls, image: Image.Image, min_aspect: float = 1.55
    ) -> Tuple[bool, float]:
        """Analyzes image foreground contour to check for tall cylindrical/box shape.
        
        Returns:
            (is_tall_container, aspect_ratio)
        """
        arr = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # Background is white studio canvas
        fg_mask = (gray < 250).astype(np.uint8) * 255

        y_indices, x_indices = np.where(fg_mask > 0)
        if len(x_indices) == 0 or len(y_indices) == 0:
            return False, 0.0

        w = int(np.max(x_indices) - np.min(x_indices) + 1)
        h = int(np.max(y_indices) - np.min(y_indices) + 1)
        aspect = float(h) / max(1.0, float(w))

        return aspect >= min_aspect, aspect

    @classmethod
    def classify(
        cls, name: str, category: str = "", image: Optional[Image.Image] = None
    ) -> Tuple[bool, str]:
        """Full 3-tier classification."""
        is_meta, reason = cls.is_container_by_metadata(name, category)
        if is_meta:
            return True, reason

        if image is not None:
            is_shape, aspect = cls.is_container_by_shape(image)
            if is_shape:
                return True, f"shape_aspect_{aspect:.2f}"

        return False, "non_container"

    @classmethod
    def index_catalog(cls, excel_path: Path) -> Dict[str, Dict[str, Any]]:
        """Indexes the master Excel catalog with container classification flags."""
        import openpyxl

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        ws = wb.active
        catalog: Dict[str, Dict[str, Any]] = {}

        for r in range(4, ws.max_row + 1):
            raw_bc = ws.cell(r, 1).value
            if not raw_bc:
                continue
            bc = str(raw_bc).strip()
            if bc.endswith(".0"):
                bc = bc[:-2]

            name = str(ws.cell(r, 2).value or "").strip()
            category = str(ws.cell(r, 8).value or "").strip()
            record_id = str(ws.cell(r, 5).value or f"ROW-{r}").strip()

            is_container, reason = cls.classify(name, category)

            entry = {
                "barcode": bc,
                "name_en": name,
                "category": category,
                "record_id": record_id,
                "row_idx": r,
                "is_container": is_container,
                "container_reason": reason,
            }

            catalog[bc] = entry
            clean_bc = bc.lstrip("0")
            if clean_bc and clean_bc not in catalog:
                catalog[clean_bc] = entry
            if not bc.startswith("0"):
                catalog["0" + bc] = entry

        return catalog

