"""High-speed memory-efficient parallel barcode scanner using OpenCV and zxingcpp."""
from __future__ import annotations

import concurrent.futures
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps
import pillow_heif
import zxingcpp

from product_mapper.zohanubis.sanitizer import RawPhotoRecord

# Register HEIC opener for Apple images
pillow_heif.register_heif_opener()


@dataclass
class BarcodeScanResult:
    path: Path
    filename: str
    partition: str
    barcodes: List[str]
    detected_angle: int  # 0, 90, 180, 270
    enhancement_used: bool
    barcode_centers: Dict[str, Tuple[float, float]] = field(default_factory=dict)


def _load_scaled_bgr(photo_path: Path, max_dim: int = 1600) -> Optional[np.ndarray]:
    """Loads image, applies EXIF transpose, and scales down to max_dim to avoid MemoryError."""
    try:
        pil_img = Image.open(photo_path)
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        w, h = pil_img.size
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        rgb = np.array(pil_img, dtype=np.uint8)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _apply_clahe(cv_bgr: np.ndarray) -> np.ndarray:
    """Enhance local contrast using CLAHE to read barcodes with specular glare."""
    gray = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _calculate_barcode_centers(
    results: list, angle: int, img_w: int, img_h: int
) -> Dict[str, Tuple[float, float]]:
    centers: Dict[str, Tuple[float, float]] = {}
    for r in results:
        bc = r.text.strip()
        if not bc or len(bc) < 6:
            continue
        p = r.position
        rx = (p.top_left.x + p.bottom_right.x) / 2.0
        ry = (p.top_left.y + p.bottom_right.y) / 2.0
        
        # Invert rotation to get coordinates in unrotated image
        if angle == 0:
            cx, cy = rx, ry
        elif angle == 90:
            cx, cy = ry, img_h - 1 - rx
        elif angle == 180:
            cx, cy = img_w - 1 - rx, img_h - 1 - ry
        elif angle == 270:
            cx, cy = img_w - 1 - ry, rx
        else:
            cx, cy = rx, ry
            
        norm_x = max(0.0, min(1.0, float(cx) / max(1, img_w)))
        norm_y = max(0.0, min(1.0, float(cy) / max(1, img_h)))
        centers[bc] = (round(norm_x, 4), round(norm_y, 4))
    return centers


def scan_single_image(photo_path: Path, partition: str = "") -> BarcodeScanResult:
    """Scans a single photo for barcodes across 4 rotation angles with contrast fallback."""
    bgr = _load_scaled_bgr(photo_path, max_dim=1600)
    if bgr is None:
        return BarcodeScanResult(
            path=photo_path,
            filename=photo_path.name,
            partition=partition,
            barcodes=[],
            detected_angle=0,
            enhancement_used=False,
            barcode_centers={},
        )

    img_h, img_w = bgr.shape[:2]
    # Convert to grayscale for fastest scanning
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 1. Sweep 4 rotation angles (0, 90, 180, 270)
    current = gray
    for angle in [0, 90, 180, 270]:
        if angle == 90:
            current = cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            current = cv2.rotate(gray, cv2.ROTATE_180)
        elif angle == 270:
            current = cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)

        try:
            results = zxingcpp.read_barcodes(current)
            if results:
                clean_bcs = [r.text.strip() for r in results if r.text and len(r.text.strip()) >= 6]
                if clean_bcs:
                    centers = _calculate_barcode_centers(results, angle, img_w, img_h)
                    return BarcodeScanResult(
                        path=photo_path,
                        filename=photo_path.name,
                        partition=partition,
                        barcodes=clean_bcs,
                        detected_angle=angle,
                        enhancement_used=False,
                        barcode_centers=centers,
                    )
        except Exception:
            pass

    # 2. If standard sweep fails, try CLAHE contrast enhancement
    try:
        enhanced = _apply_clahe(bgr)
        # Try CLAHE at 0 deg
        res0 = zxingcpp.read_barcodes(enhanced)
        if res0:
            clean_bcs = [r.text.strip() for r in res0 if r.text and len(r.text.strip()) >= 6]
            if clean_bcs:
                centers = _calculate_barcode_centers(res0, 0, img_w, img_h)
                return BarcodeScanResult(
                    path=photo_path,
                    filename=photo_path.name,
                    partition=partition,
                    barcodes=clean_bcs,
                    detected_angle=0,
                    enhancement_used=True,
                    barcode_centers=centers,
                )
        # Try CLAHE at 90 deg
        enhanced_90 = cv2.rotate(enhanced, cv2.ROTATE_90_CLOCKWISE)
        res90 = zxingcpp.read_barcodes(enhanced_90)
        if res90:
            clean_bcs = [r.text.strip() for r in res90 if r.text and len(r.text.strip()) >= 6]
            if clean_bcs:
                centers = _calculate_barcode_centers(res90, 90, img_w, img_h)
                return BarcodeScanResult(
                    path=photo_path,
                    filename=photo_path.name,
                    partition=partition,
                    barcodes=clean_bcs,
                    detected_angle=90,
                    enhancement_used=True,
                    barcode_centers=centers,
                )
        # Try CLAHE at 180 and 270
        for angle in [180, 270]:
            rot_c = cv2.rotate(enhanced, cv2.ROTATE_180 if angle == 180 else cv2.ROTATE_90_COUNTERCLOCKWISE)
            res_c = zxingcpp.read_barcodes(rot_c)
            if res_c:
                clean_bcs = [r.text.strip() for r in res_c if r.text and len(r.text.strip()) >= 6]
                if clean_bcs:
                    centers = _calculate_barcode_centers(res_c, angle, img_w, img_h)
                    return BarcodeScanResult(
                        path=photo_path,
                        filename=photo_path.name,
                        partition=partition,
                        barcodes=clean_bcs,
                        detected_angle=angle,
                        enhancement_used=True,
                        barcode_centers=centers,
                    )
    except Exception:
        pass

    return BarcodeScanResult(
        path=photo_path,
        filename=photo_path.name,
        partition=partition,
        barcodes=[],
        detected_angle=0,
        enhancement_used=False,
        barcode_centers={},
    )


def _scan_worker(args: Tuple[Path, str]) -> BarcodeScanResult:
    path, partition = args
    try:
        return scan_single_image(path, partition)
    except Exception:
        return BarcodeScanResult(
            path=path,
            filename=path.name,
            partition=partition,
            barcodes=[],
            detected_angle=0,
            enhancement_used=False,
            barcode_centers={},
        )


class ParallelBarcodeScanner:
    """Orchestrates parallel barcode scanning across raw photo sets."""

    def __init__(self, max_workers: Optional[int] = None):
        if max_workers is None:
            self.max_workers = 4
        else:
            self.max_workers = max_workers

    def scan_records(
        self, records: List[RawPhotoRecord], show_progress: bool = True
    ) -> List[BarcodeScanResult]:
        """Scan a list of RawPhotoRecord objects in parallel using ThreadPoolExecutor."""
        tasks = [(r.path, r.partition) for r in records]
        results: List[BarcodeScanResult] = []
        total = len(tasks)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            completed = 0
            for res in executor.map(_scan_worker, tasks):
                results.append(res)
                completed += 1
                if show_progress and (completed % 25 == 0 or completed == total):
                    bcs = sum(1 for r in results if r.barcodes)
                    print(f"  [Scan Progress] {completed}/{total} scanned ({bcs} barcodes found)...", flush=True)

        return results
