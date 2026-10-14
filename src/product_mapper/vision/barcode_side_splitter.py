"""Barcode-first front/back split.

The barcode is on the back panel. Reading it first tells us which panel is the
back, which way is upright, and which panel is the front. Package aspect ratio
is kept: a landscape bag stays landscape once its text is upright.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageEnhance, ImageOps
from rembg import new_session, remove

from ..ingestion.image_loader import open_image_safely
from .barcode_validator import validate_ean_upc_checksum

SplitMode = Literal["back_left", "back_right", "back_top", "back_bottom", "back_only"]
RETAIL_FORMATS = zxingcpp.BarcodeFormat.EANUPC

_QUAD_NAMES = ("top_left", "top_right", "bottom_right", "bottom_left")


@dataclass(frozen=True)
class BarcodeHit:
    text: str
    area: float
    angle: float
    upright_ccw: int
    center_x: float
    center_y: float
    quad: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]
    mirrored: bool


@dataclass(frozen=True)
class SideBoxes:
    mode: SplitMode
    back: tuple[int, int, int, int]
    front: tuple[int, int, int, int] | None
    upright_ccw: int


def upright_ccw_from_angle(angle_deg: float) -> int:
    """CCW degrees that make the barcode's top edge point to the right."""
    snapped = int(round(angle_deg / 90.0)) * 90
    return snapped % 360


def transform_point(x: float, y: float, width: int, height: int, ccw: int) -> tuple[float, float]:
    if ccw == 0:
        return x, y
    if ccw == 90:
        return y, width - 1 - x
    if ccw == 180:
        return width - 1 - x, height - 1 - y
    if ccw == 270:
        return height - 1 - y, x
    raise ValueError(f"unsupported rotation {ccw}")


def rotated_size(width: int, height: int, ccw: int) -> tuple[int, int]:
    if ccw in (90, 270):
        return height, width
    if ccw in (0, 180):
        return width, height
    raise ValueError(f"unsupported rotation {ccw}")


def rotate_upright(image: Image.Image, ccw: int) -> Image.Image:
    if ccw == 0:
        return image
    if ccw in (90, 180, 270):
        return image.rotate(ccw, expand=True, resample=Image.Resampling.BICUBIC)
    raise ValueError(f"unsupported rotation {ccw}")


def _decode(image: Image.Image) -> list:
    return zxingcpp.read_barcodes(
        image,
        formats=RETAIL_FORMATS,
        try_rotate=True,
        try_downscale=True,
        try_invert=True,
        return_errors=False,
    )


def _quad_and_angle(result) -> tuple[list[tuple[float, float]], float, float]:
    points = []
    for name in _QUAD_NAMES:
        point = getattr(result.position, name)
        points.append((float(point.x), float(point.y)))
    top_left, top_right = points[0], points[1]
    angle = math.degrees(math.atan2(top_right[1] - top_left[1], top_right[0] - top_left[0]))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    area = max(1.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))
    return points, angle, area


def _hit_from_result(result, offset_x: float, offset_y: float, scale: float, mirrored: bool) -> BarcodeHit | None:
    text = "".join(ch for ch in str(result.text or "") if ch.isdigit())
    if not validate_ean_upc_checksum(text):
        return None
    points, angle, area = _quad_and_angle(result)
    if area < 80:
        return None
    mapped = [((x / scale) + offset_x, (y / scale) + offset_y) for x, y in points]
    xs = [p[0] for p in mapped]
    ys = [p[1] for p in mapped]
    quad = (mapped[0], mapped[1], mapped[2], mapped[3])
    return BarcodeHit(
        text=text,
        area=(max(xs) - min(xs)) * (max(ys) - min(ys)),
        angle=angle,
        upright_ccw=upright_ccw_from_angle(angle),
        center_x=sum(xs) / 4.0,
        center_y=sum(ys) / 4.0,
        quad=quad,
        mirrored=mirrored,
    )


def _prepare(image: Image.Image, max_long: int) -> tuple[Image.Image, float]:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_long:
        return image, 1.0
    resized = image.resize(
        (max(1, int(width * max_long / longest)), max(1, int(height * max_long / longest))),
        Image.Resampling.BILINEAR,
    )
    return resized, resized.size[0] / width


def _scan_region(image: Image.Image, box: tuple[int, int, int, int], max_long: int, mirrored: bool) -> list[BarcodeHit]:
    crop = image.crop(box)
    if min(crop.size) < 40:
        return []
    small, scale = _prepare(crop, max_long)
    hits: list[BarcodeHit] = []
    for result in _decode(small):
        hit = _hit_from_result(result, box[0], box[1], scale, mirrored)
        if hit is not None:
            hits.append(hit)
    return hits


def read_retail_barcodes(image: Image.Image) -> list[BarcodeHit]:
    """Read EAN/UPC codes. A second pass zooms into each half when the full frame misses."""
    width, height = image.size
    hits = _scan_region(image, (0, 0, width, height), 1800, mirrored=False)
    if hits:
        return _dedupe(hits)

    regions = [
        (0, 0, int(width * 0.62), height),
        (int(width * 0.38), 0, width, height),
        (0, 0, width, int(height * 0.62)),
        (0, int(height * 0.38), width, height),
    ]
    for region in regions:
        hits.extend(_scan_region(image, region, 2200, mirrored=False))
    if hits:
        return _dedupe(hits)

    mirrored = ImageOps.mirror(image)
    hits.extend(_scan_region(mirrored, (0, 0, width, height), 1800, mirrored=True))
    if hits:
        return _dedupe(hits)
    return _dedupe(_rescue_small_barcodes(image))


def _dedupe(hits: list[BarcodeHit]) -> list[BarcodeHit]:
    best: dict[str, BarcodeHit] = {}
    for hit in hits:
        current = best.get(hit.text)
        if current is None or hit.area > current.area:
            best[hit.text] = hit
    ordered = sorted(best.values(), key=lambda item: item.area, reverse=True)
    if not ordered:
        return []
    # A partial misread of the same bars is much smaller than the real symbol.
    largest = ordered[0].area
    return [hit for hit in ordered if hit.area >= largest * 0.25]


def _rescue_small_barcodes(image: Image.Image) -> list[BarcodeHit]:
    """Zoom into overlapping tiles when a full-frame scan misses a small bottle or jar code."""
    width, height = image.size
    hits: list[BarcodeHit] = []
    tight_windows = (
        (0.02, 0.55, 0.52, 0.98),
        (0.48, 0.55, 0.98, 0.98),
        (0.02, 0.28, 0.52, 0.72),
        (0.48, 0.28, 0.98, 0.72),
    )
    for x0f, y0f, x1f, y1f in tight_windows:
        hit_box = (int(width * x0f), int(height * y0f), int(width * x1f), int(height * y1f))
        hits.extend(_scan_enlarged(image, hit_box, min_long=0))
        if hits:
            return hits
    for y_frac in (0.45, 0.22, 0.0):
        for x_frac in (0.0, 0.45):
            x0 = int(width * x_frac)
            y0 = int(height * y_frac)
            x1 = min(width, x0 + int(width * 0.58))
            y1 = min(height, y0 + int(height * 0.58))
            if x1 - x0 < 40 or y1 - y0 < 40:
                continue
            hits.extend(_scan_enlarged(image, (x0, y0, x1, y1), min_long=3600))
            if hits:
                return hits
    return hits


def _scan_enlarged(image: Image.Image, box: tuple[int, int, int, int], min_long: int) -> list[BarcodeHit]:
    """Decode one crop. ``min_long`` 0 means enlarge to 3x, which reads small bottle codes."""
    x0, y0, x1, y1 = box
    crop = image.crop(box)
    if min(crop.size) < 40:
        return []
    if min_long == 0:
        scale = 3.0
    else:
        long_side = max(crop.size)
        scale = max(1.0, min_long / long_side)
    if scale > 1.01:
        crop = crop.resize(
            (max(1, int(crop.size[0] * scale)), max(1, int(crop.size[1] * scale))),
            Image.Resampling.LANCZOS,
        )
        crop = ImageEnhance.Sharpness(crop).enhance(2.0)
        crop = ImageEnhance.Contrast(crop).enhance(1.5)
    hits: list[BarcodeHit] = []
    for result in _decode(crop):
        hit = _hit_from_result(result, x0, y0, scale, mirrored=False)
        if hit is not None:
            hits.append(hit)
    return hits


def choose_barcode(hits: list[BarcodeHit], truth_codes: set[str] | None = None) -> BarcodeHit | None:
    if not hits:
        return None
    truth = truth_codes or set()

    def rank(hit: BarcodeHit) -> tuple[int, float]:
        return (1 if hit.text in truth else 0, hit.area)

    return max(hits, key=rank)


def scan_file(path: Path, truth_codes: set[str] | None = None) -> dict:
    image = open_image_safely(path)
    width, height = image.size
    hits = read_retail_barcodes(image)
    chosen = choose_barcode(hits, truth_codes)
    image.close()
    payload: dict = {
        "path": str(path),
        "width": width,
        "height": height,
        "codes": [hit.text for hit in hits],
        "barcode": None,
    }
    if chosen is None:
        return payload
    payload.update(
        {
            "barcode": chosen.text,
            "area": round(chosen.area, 1),
            "angle": round(chosen.angle, 2),
            "upright_ccw": chosen.upright_ccw,
            "mirrored": chosen.mirrored,
            "center": [round(chosen.center_x, 1), round(chosen.center_y, 1)],
            "quad": [[round(x, 1), round(y, 1)] for x, y in chosen.quad],
        }
    )
    return payload


def _largest_box(arr: np.ndarray, roi: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    height, width = arr.shape[:2]
    x0, y0, x1, y1 = roi
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    patch = arr[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 25, 90)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    closed = cv2.morphologyEx(cv2.dilate(edges, kernel, iterations=2), cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    roi_area = max(1, patch.shape[0] * patch.shape[1])
    best = None
    best_area = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < roi_area * 0.08 or area <= best_area:
            continue
        bx, by, bw, bh = cv2.boundingRect(contour)
        best = (x0 + bx, y0 + by, x0 + bx + bw, y0 + by + bh)
        best_area = area
    return best


def _clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    x0 = max(0, min(width - 1, x0))
    y0 = max(0, min(height - 1, y0))
    x1 = max(x0 + 1, min(width, x1))
    y1 = max(y0 + 1, min(height, y1))
    return x0, y0, x1, y1


def _pad_away_from_sibling(
    box: tuple[int, int, int, int],
    sibling: tuple[int, int, int, int] | None,
    width: int,
    height: int,
    ratio: float = 0.045,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    pad_x = int((x1 - x0) * ratio)
    pad_y = int((y1 - y0) * ratio)
    nx0, ny0, nx1, ny1 = x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y
    if sibling is not None:
        sx0, sy0, sx1, sy1 = sibling
        if sx0 >= x1:
            nx1 = min(nx1, (x1 + sx0) // 2)
        if x0 >= sx1:
            nx0 = max(nx0, (sx1 + x0) // 2)
        if sy0 >= y1:
            ny1 = min(ny1, (y1 + sy0) // 2)
        if y0 >= sy1:
            ny0 = max(ny0, (sy1 + y0) // 2)
    return _clamp_box((nx0, ny0, nx1, ny1), width, height)


def _profile_cut(profile: np.ndarray) -> tuple[float, float, float]:
    """Return cut fraction, depth, and how balanced the two shoulders are.

    A real gap has content on both sides. A shoulder line on a standing bottle
    has one quiet side and one busy side, so its balance stays low.
    """
    length = len(profile)
    low = int(length * 0.28)
    high = int(length * 0.72)
    index = low + int(np.argmin(profile[low:high]))
    left = float(profile[int(length * 0.08) : int(length * 0.28)].mean())
    right = float(profile[int(length * 0.72) : int(length * 0.92)].mean())
    shoulders = (left + right) / 2.0
    center = float(profile[index])
    depth = 0.0 if shoulders <= 1 else 1.0 - (center / shoulders)
    balance = 0.0 if max(left, right) <= 1 else min(left, right) / max(left, right)
    return index / length, depth, balance


def _cut_ok(fraction: float, depth: float, balance: float, min_depth: float, min_balance: float) -> bool:
    return depth >= min_depth and balance >= min_balance and 0.32 <= fraction <= 0.68


def _mode_at(axis: str, fraction: float, center_x: float, center_y: float, width: int, height: int) -> tuple[SplitMode, int]:
    if axis == "x":
        cut = max(1, min(width - 1, int(round(fraction * width))))
        mode: SplitMode = "back_left" if center_x < cut else "back_right"
        return mode, cut
    cut = max(1, min(height - 1, int(round(fraction * height))))
    mode = "back_top" if center_y < cut else "back_bottom"
    return mode, cut


def _narrow_side_holds_barcode(cut: float, barcode_at: float) -> bool:
    """The barcode sits on the smaller side of a cut, clear of the seam."""
    if barcode_at < cut - 0.03:
        return 0.22 <= cut <= 0.48
    if barcode_at > cut + 0.03:
        return 0.22 <= (1.0 - cut) <= 0.48
    return False


def _valley_in_band(
    profile: np.ndarray,
    low: float,
    high: float,
    min_depth: float,
    min_balance: float,
) -> tuple[float, float, float] | None:
    """Deepest valley inside one fraction band. Global valleys can hide this seam."""
    length = len(profile)
    span = max(8, int(length * 0.08))
    best: tuple[float, float, float] | None = None
    start = max(1, int(length * low))
    stop = min(length - 1, int(length * high))
    for index in range(start, stop):
        if profile[index] > profile[index - 1] or profile[index] > profile[index + 1]:
            continue
        left = float(profile[max(0, index - span) : index].mean())
        right = float(profile[index + 1 : min(length, index + span)].mean())
        shoulders = (left + right) / 2.0
        if shoulders <= 1 or max(left, right) <= 1:
            continue
        depth = 1.0 - float(profile[index]) / shoulders
        balance = min(left, right) / max(left, right)
        if depth < min_depth or balance < min_balance:
            continue
        if best is None or depth > best[1]:
            best = (index / length, depth, balance)
    return best


def _stacked_packages_row(
    row_profile: np.ndarray,
    column_at: float,
    center_x: float,
    center_y: float,
    width: int,
    height: int,
) -> tuple[SplitMode, int] | None:
    """Two packages one above the other, when a vertical cut only slices both."""
    if height <= width:
        return None
    barcode_x = center_x / max(1, width)
    barcode_y = center_y / max(1, height)
    if 0.40 <= barcode_y <= 0.60 or not _narrow_side_holds_barcode(column_at, barcode_x):
        return None
    empty = _valley_in_band(row_profile, 0.38, 0.62, 0.90, 0.55)
    # Packages that touch have a shallow seam. A deep line is usually print on one box.
    touching = None if empty is not None else _valley_in_band(row_profile, 0.38, 0.62, 0.30, 0.65)
    if touching is not None and touching[1] > 0.55:
        touching = None
    chosen = empty or touching
    if chosen is None:
        return None
    return _mode_at("y", chosen[0], center_x, center_y, width, height)


def _spine_panel(
    column_profile: np.ndarray,
    center_x: float,
    center_y: float,
    width: int,
    height: int,
) -> tuple[SplitMode, int] | None:
    """The ingredients panel beside the front of a box, already photographed upright."""
    if width <= height:
        return None
    barcode_x = center_x / max(1, width)
    gaps = [
        item
        for item in _local_gaps(column_profile, min_depth=0.45, min_sep=0.10)
        if item[2] >= 0.55 and _narrow_side_holds_barcode(item[0], barcode_x)
    ]
    if not gaps:
        return None
    fraction = max(gaps, key=lambda item: item[1])[0]
    return _mode_at("x", fraction, center_x, center_y, width, height)


def _gap_options(arr: np.ndarray, center_x: float, center_y: float) -> list[tuple[SplitMode, int]]:
    """Side-by-side gaps win over a horizontal line that only slices a standing product."""
    height, width = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    # A narrow kernel keeps the slim gap between two standing bottles.
    kernel = np.ones(15) / 15.0
    column_at, column_depth, column_balance = _profile_cut(np.convolve(edges.mean(axis=0), kernel, mode="same"))
    row_at, row_depth, row_balance = _profile_cut(np.convolve(edges.mean(axis=1), kernel, mode="same"))

    options: list[tuple[SplitMode, int]] = []
    column_profile = np.convolve(edges.mean(axis=0), kernel, mode="same")
    row_profile = np.convolve(edges.mean(axis=1), kernel, mode="same")
    stacked = _stacked_packages_row(row_profile, column_at, center_x, center_y, width, height)
    if stacked is not None:
        options.append(stacked)
    spine = _spine_panel(column_profile, center_x, center_y, width, height)
    if spine is not None and not _cut_ok(column_at, column_depth, column_balance, 0.35, 0.55):
        options.append(spine)
    # Two bags touching: the seam is a shallow valley with content balanced on both sides.
    for fraction, depth, balance in _local_gaps(column_profile, min_depth=0.30, min_sep=0.18):
        if 0.40 <= fraction <= 0.60 and balance >= 0.90:
            options.append(_mode_at("x", fraction, center_x, center_y, width, height))
            break
    if _cut_ok(column_at, column_depth, column_balance, 0.35, 0.55):
        strong = _mode_at("x", column_at, center_x, center_y, width, height)
        if strong not in options:
            options.append(strong)
    # Two upright bottles standing next to each other. Do not use this on a landscape photo of bottles lying down.
    if height > width:
        for fraction, depth, balance in _local_gaps(column_profile, min_depth=0.35, min_sep=0.18):
            if 0.34 <= fraction <= 0.66 and balance >= 0.60:
                side_by_side = _mode_at("x", fraction, center_x, center_y, width, height)
                if side_by_side not in options:
                    options.append(side_by_side)
                break
    # Two packages lying one above the other. A label line near the edge is not the gap.
    if width > height:
        central_rows = [
            item
            for item in _local_gaps(row_profile, min_depth=0.45, min_sep=0.10)
            if 0.42 <= item[0] <= 0.62 and item[2] >= 0.75
        ]
        if central_rows:
            fraction = max(central_rows, key=lambda item: item[1])[0]
            options.append(_mode_at("y", fraction, center_x, center_y, width, height))
    if _cut_ok(row_at, row_depth, row_balance, 0.45, 0.62):
        row_option = _mode_at("y", row_at, center_x, center_y, width, height)
        if row_option not in options:
            options.append(row_option)
    if _cut_ok(column_at, column_depth, column_balance, 0.18, 0.55):
        weak = _mode_at("x", column_at, center_x, center_y, width, height)
        if weak not in options:
            options.append(weak)
    local_gaps = _local_column_gaps(np.convolve(edges.mean(axis=0), np.ones(21) / 21.0, mode="same"), min_depth=0.22)
    if len(local_gaps) == 1 and 0.32 <= local_gaps[0] <= 0.68:
        local = _mode_at("x", local_gaps[0], center_x, center_y, width, height)
        if local not in options:
            options.append(local)
    options.append(("back_only", 0))
    return options


def _local_gaps(profile: np.ndarray, min_depth: float, min_sep: float = 0.18) -> list[tuple[float, float]]:
    """Deep valleys along one axis, as (fraction, depth), at most two."""
    length = len(profile)
    span = max(8, int(length * 0.08))
    found: list[tuple[float, float]] = []
    for index in range(int(length * 0.15), int(length * 0.85)):
        if profile[index] > profile[index - 1] or profile[index] > profile[index + 1]:
            continue
        left = float(profile[max(0, index - span) : index].mean())
        right = float(profile[index + 1 : min(length, index + span)].mean())
        shoulders = (left + right) / 2.0
        if shoulders <= 1:
            continue
        depth = 1.0 - float(profile[index]) / shoulders
        balance = 0.0 if max(left, right) <= 1 else min(left, right) / max(left, right)
        if depth >= min_depth:
            found.append((index / length, depth, balance))
    found.sort(key=lambda item: item[1], reverse=True)
    kept: list[tuple[float, float, float]] = []
    for fraction, depth, balance in found:
        if all(abs(fraction - previous) >= min_sep for previous, _depth, _balance in kept):
            kept.append((fraction, depth, balance))
        if len(kept) == 2:
            break
    kept.sort()
    return kept


def _local_column_gaps(profile: np.ndarray, min_depth: float) -> list[float]:
    return [fraction for fraction, _depth, _balance in _local_gaps(profile, min_depth, min_sep=0.14)]


def _column_profile(arr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    return np.convolve(edges.mean(axis=0), np.ones(21) / 21.0, mode="same")


def _edge_profile(arr: np.ndarray, axis: str) -> np.ndarray:
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    mean = edges.mean(axis=0 if axis == "x" else 1)
    return np.convolve(mean, np.ones(15) / 15.0, mode="same")


def _segment_edges(arr: np.ndarray, axis: str, segment: tuple[int, int]) -> float:
    patch = arr[:, segment[0] : segment[1]] if axis == "x" else arr[segment[0] : segment[1], :]
    if patch.size == 0:
        return 0.0
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    return float(cv2.Canny(gray, 40, 120).mean())


def _three_panel(
    arr: np.ndarray,
    center_x: float,
    center_y: float,
    scale: float,
    width: int,
    height: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Three packages in a row. The barcode package is the back.

    When the barcode is on an end package, the middle one is the sales face.
    When the barcode is in the middle, the sales face is the side with less fine print.
    """
    preview_h, preview_w = arr.shape[:2]

    def usable(gaps: list[tuple[float, float, float]]) -> bool:
        if len(gaps) != 2:
            return False
        start, end = gaps[0][0], gaps[1][0]
        sizes = (start, end - start, 1.0 - end)
        # A barcode sticker is narrower than a package face.
        return all(0.28 <= size <= 0.46 for size in sizes)

    column_gaps = _local_gaps(_edge_profile(arr, "x"), min_depth=0.45, min_sep=0.18)
    row_gaps = _local_gaps(_edge_profile(arr, "y"), min_depth=0.45, min_sep=0.18)
    if usable(column_gaps):
        axis, gaps, span = "x", column_gaps, preview_w
        barcode_at = center_x
    elif usable(row_gaps):
        axis, gaps, span = "y", row_gaps, preview_h
        barcode_at = center_y
    else:
        return None

    cuts = [max(1, min(span - 1, int(round(fraction * span)))) for fraction, _depth, _balance in gaps]
    segments = [(0, cuts[0]), (cuts[0], cuts[1]), (cuts[1], span)]
    barcode_px = int(min(span - 1, max(0, round(barcode_at))))
    back_index = 0
    for index, (left, right) in enumerate(segments):
        if left <= barcode_px <= right:
            back_index = index
            break
    if back_index in (0, 2):
        front_index = 1
    else:
        front_index = min((0, 2), key=lambda index: _segment_edges(arr, axis, segments[index]))

    def full_box(segment: tuple[int, int]) -> tuple[int, int, int, int]:
        start = int(round(segment[0] / scale))
        end = int(round(segment[1] / scale))
        if axis == "x":
            return _clamp_box((start, 0, end, height), width, height)
        return _clamp_box((0, start, width, end), width, height)

    return full_box(segments[back_index]), full_box(segments[front_index])


def _mode_from_boxes(
    back: tuple[int, int, int, int],
    front: tuple[int, int, int, int],
) -> SplitMode:
    if back[1] >= front[3] - 2:
        return "back_bottom"
    if front[1] >= back[3] - 2:
        return "back_top"
    if back[0] <= front[0]:
        return "back_left"
    return "back_right"


def _horizontal_slice(box: tuple[int, int, int, int], width: int, height: int) -> bool:
    """A cap or label band cut across a standing bottle. A full-height package is kept."""
    box_w = box[2] - box[0]
    box_h = box[3] - box[1]
    if box_w <= 0 or box_h <= 0:
        return True
    if box_h >= box_w:
        return False
    # Stacked flat pouches sit near half the frame. A neck band is shorter than that.
    return (box_w / box_h) >= 1.85 and box_h < height * 0.42


def _panel_too_thin(box: tuple[int, int, int, int], width: int, height: int) -> bool:
    """Reject a horizontal band or a blank edge sliver. A tall bottle is kept."""
    box_w = box[2] - box[0]
    box_h = box[3] - box[1]
    if box_w <= 0 or box_h <= 0:
        return True
    # A lying bottle is a wide short panel. Only a portrait photo can be a neck slice.
    short_limit = 0.34 if height > width else 0.12
    wide_band = box_w > width * 0.72 and box_h < height * short_limit
    tall_sliver = box_h > height * 0.72 and box_w < width * 0.16
    tiny = (box_w * box_h) < (width * height * 0.08)
    return wide_band or tall_sliver or tiny


def _rois_from_gap(
    mode: SplitMode,
    cut: int,
    width: int,
    height: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int] | None]:
    if mode == "back_left":
        return (0, 0, cut, height), (cut, 0, width, height)
    if mode == "back_right":
        return (cut, 0, width, height), (0, 0, cut, height)
    if mode == "back_top":
        return (0, 0, width, cut), (0, cut, width, height)
    if mode == "back_bottom":
        return (0, cut, width, height), (0, 0, width, cut)
    if mode == "back_only":
        return (0, 0, width, height), None
    raise ValueError(f"unsupported split {mode}")


def _separate_overlap(
    mode: SplitMode,
    back: tuple[int, int, int, int],
    front: tuple[int, int, int, int] | None,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int] | None]:
    if front is None:
        return back, None
    bx0, by0, bx1, by1 = back
    fx0, fy0, fx1, fy1 = front
    if mode in ("back_left", "back_right"):
        overlap_left = max(bx0, fx0)
        overlap_right = min(bx1, fx1)
        if overlap_right > overlap_left:
            boundary = (overlap_left + overlap_right) // 2
            if mode == "back_left":
                back = (bx0, by0, boundary, by1)
                front = (boundary, fy0, fx1, fy1)
            else:
                front = (fx0, fy0, boundary, fy1)
                back = (boundary, by0, bx1, by1)
    elif mode in ("back_top", "back_bottom"):
        overlap_top = max(by0, fy0)
        overlap_bottom = min(by1, fy1)
        if overlap_bottom > overlap_top:
            boundary = (overlap_top + overlap_bottom) // 2
            if mode == "back_top":
                back = (bx0, by0, bx1, boundary)
                front = (fx0, boundary, fx1, fy1)
            else:
                front = (fx0, fy0, fx1, boundary)
                back = (bx0, boundary, bx1, by1)
    else:
        raise ValueError(f"unsupported split {mode}")
    return back, front


def _boxes_for_mode(
    arr: np.ndarray,
    scale: float,
    mode: SplitMode,
    preview_cut: int,
    width: int,
    height: int,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int] | None]:
    full_cut = int(round(preview_cut / scale)) if mode != "back_only" else 0
    back_roi, front_roi = _rois_from_gap(mode, full_cut, width, height)

    def lift(box: tuple[int, int, int, int] | None, roi: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if box is None:
            found = roi
        else:
            found = tuple(int(round(value / scale)) for value in box)
        return _clamp_box(found, width, height)

    # The strongest contour in the back half is usually the barcode sticker.
    # The back image has to be the whole panel, not that sticker.
    back_box = lift(None, back_roi)
    front_box = None
    if front_roi is not None:
        scaled_front = tuple(int(value * scale) for value in front_roi)
        tight = lift(_largest_box(arr, scaled_front), front_roi)  # type: ignore[arg-type]
        roi_area = max(1, (front_roi[2] - front_roi[0]) * (front_roi[3] - front_roi[1]))
        tight_area = (tight[2] - tight[0]) * (tight[3] - tight[1])
        front_box = tight if tight_area >= roi_area * 0.45 else lift(None, front_roi)
        if _panel_too_thin(front_box, width, height) or _panel_too_thin(back_box, width, height):
            return back_box, None
        front_box = _pad_away_from_sibling(front_box, back_box, width, height)
        back_box, front_box = _separate_overlap(mode, back_box, front_box)
        if front_box is not None and (_panel_too_thin(front_box, width, height) or _panel_too_thin(back_box, width, height)):
            return back_box, None
    return back_box, front_box


def _cut_crosses_barcode(mode: SplitMode, cut: int, center_x: float, center_y: float, width: int, height: int) -> bool:
    """A seam that runs through the barcode is slicing the package, not separating two packages."""
    if mode in ("back_left", "back_right"):
        return abs(center_x - cut) < width * 0.08
    if mode in ("back_top", "back_bottom"):
        return abs(center_y - cut) < height * 0.08
    return False


def split_sides(image: Image.Image, center_x: float, center_y: float, upright_ccw: int) -> SideBoxes:
    """Split an already upright image. `center_*` is in that upright image."""
    width, height = image.size
    preview, scale = _prepare(image, 900)
    arr = np.asarray(preview)
    scaled_x, scaled_y = center_x * scale, center_y * scale
    preview_h, preview_w = arr.shape[:2]
    trio = _three_panel(arr, scaled_x, scaled_y, scale, width, height)
    if trio is not None:
        back_box, front_box = trio
        if (
            not _panel_too_thin(front_box, width, height)
            and not _panel_too_thin(back_box, width, height)
            and not _horizontal_slice(front_box, width, height)
            and not _horizontal_slice(back_box, width, height)
        ):
            mode = _mode_from_boxes(back_box, front_box)
            return SideBoxes(mode=mode, back=back_box, front=front_box, upright_ccw=upright_ccw)
    chosen_mode: SplitMode = "back_only"
    back_box = (0, 0, width, height)
    front_box: tuple[int, int, int, int] | None = None
    for mode, preview_cut in _gap_options(arr, scaled_x, scaled_y):
        if _cut_crosses_barcode(mode, preview_cut, scaled_x, scaled_y, preview_w, preview_h):
            continue
        back_box, front_box = _boxes_for_mode(arr, scale, mode, preview_cut, width, height)
        if _horizontal_slice(back_box, width, height) or (front_box is not None and _horizontal_slice(front_box, width, height)):
            continue
        chosen_mode = mode if front_box is not None or mode == "back_only" else "back_only"
        if mode == "back_only" or front_box is not None:
            break
    if _panel_too_thin(back_box, width, height) or _horizontal_slice(back_box, width, height):
        back_box = (0, 0, width, height)
        chosen_mode = "back_only"
        front_box = None
    return SideBoxes(mode=chosen_mode, back=back_box, front=front_box, upright_ccw=upright_ccw)


def separate_joined_packages(
    image: Image.Image,
    box: tuple[int, int, int, int],
    anchor_x: float,
    anchor_y: float,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Split a frame that holds two packages touching each other.

    Returns (side closer to the barcode, side farther from the barcode).
    A single package has no central gap and is left unchanged.
    """
    x0, y0, x1, y1 = box
    crop_w = x1 - x0
    crop_h = y1 - y0
    if crop_w < 80 or crop_h < 80:
        return None
    crop = image.crop(box)
    preview, _scale = _prepare(crop, 720)
    arr = np.asarray(preview)

    def centered(axis: str, min_depth: float, min_balance: float) -> tuple[float, float, float] | None:
        gaps = [
            item
            for item in _local_gaps(_edge_profile(arr, axis), min_depth=min_depth, min_sep=0.20)
            if 0.38 <= item[0] <= 0.62 and item[2] >= min_balance
        ]
        if len(gaps) != 1:
            return None
        return gaps[0]

    # Side-by-side packages touch, so the seam is shallow but even. A label fold is not.
    column = centered("x", min_depth=0.25, min_balance=0.75)
    row = None if column is not None else centered("y", min_depth=0.55, min_balance=0.85)
    if column is None and row is None:
        return None
    use_column = column is not None
    if use_column and column is not None:
        cut = x0 + int(round(column[0] * crop_w))
        first_distance = abs(((x0 + cut) / 2) - anchor_x)
        second_distance = abs(((cut + x1) / 2) - anchor_x)
        # Keep the printed edge that sits on the seam, instead of shaving the barcode.
        shift = int(crop_w * 0.08)
        if first_distance <= second_distance:
            cut = min(x0 + int(crop_w * 0.70), cut + shift)
        else:
            cut = max(x0 + int(crop_w * 0.30), cut - shift)
        first = (x0, y0, cut, y1)
        second = (cut, y0, x1, y1)
    elif row is not None:
        cut = y0 + int(round(row[0] * crop_h))
        first_distance = abs(((y0 + cut) / 2) - anchor_y)
        second_distance = abs(((cut + y1) / 2) - anchor_y)
        shift = int(crop_h * 0.08)
        if first_distance <= second_distance:
            cut = min(y0 + int(crop_h * 0.70), cut + shift)
        else:
            cut = max(y0 + int(crop_h * 0.30), cut - shift)
        first = (x0, y0, x1, cut)
        second = (x0, cut, x1, y1)
    else:
        return None
    width, height = image.size
    for candidate in (first, second):
        if _panel_too_thin(candidate, width, height) or _horizontal_slice(candidate, width, height):
            return None
    if first_distance <= second_distance:
        return first, second
    return second, first


def panel_halves(image: Image.Image, center_x: float, center_y: float, upright_ccw: int) -> SideBoxes:
    """The same gap cut as `split_sides`, without the tight package contour."""
    width, height = image.size
    preview, scale = _prepare(image, 900)
    arr = np.asarray(preview)
    trio = _three_panel(arr, center_x * scale, center_y * scale, scale, width, height)
    if trio is not None:
        back_box, front_box = trio
        if (
            not _panel_too_thin(front_box, width, height)
            and not _panel_too_thin(back_box, width, height)
            and not _horizontal_slice(front_box, width, height)
            and not _horizontal_slice(back_box, width, height)
        ):
            mode = _mode_from_boxes(back_box, front_box)
            return SideBoxes(mode=mode, back=back_box, front=front_box, upright_ccw=upright_ccw)
    preview_h, preview_w = arr.shape[:2]
    scaled_x, scaled_y = center_x * scale, center_y * scale
    for mode, preview_cut in _gap_options(arr, scaled_x, scaled_y):
        if _cut_crosses_barcode(mode, preview_cut, scaled_x, scaled_y, preview_w, preview_h):
            continue
        full_cut = int(round(preview_cut / scale)) if mode != "back_only" else 0
        back, front = _rois_from_gap(mode, full_cut, width, height)
        if _horizontal_slice(back, width, height) or (front is not None and _horizontal_slice(front, width, height)):
            continue
        if front is not None and (_panel_too_thin(back, width, height) or _panel_too_thin(front, width, height)):
            continue
        return SideBoxes(mode=mode, back=back, front=front, upright_ccw=upright_ccw)
    return SideBoxes(mode="back_only", back=(0, 0, width, height), front=None, upright_ccw=upright_ccw)


def predict_split(width: int, height: int, center_x: float, center_y: float, upright_ccw: int) -> SplitMode:
    """Fast geometric guess used only when the photo has not been opened yet."""
    rotated_x, rotated_y = transform_point(center_x, center_y, width, height, upright_ccw)
    rotated_w, rotated_h = rotated_size(width, height, upright_ccw)
    nx = rotated_x / max(1, rotated_w)
    ny = rotated_y / max(1, rotated_h)
    if abs(nx - 0.5) >= 0.12 and abs(nx - 0.5) >= abs(ny - 0.5):
        return "back_left" if nx < 0.5 else "back_right"
    if abs(ny - 0.5) >= 0.12:
        return "back_top" if ny < 0.5 else "back_bottom"
    return "back_only"


def place_front_on_white(image: Image.Image, pad_ratio: float = 0.06, max_side: int = 2400) -> Image.Image:
    """Center the upright front crop on white without rotating it or scaling it up."""
    width, height = image.size
    side = int(math.ceil(max(width, height) * (1 + 2 * pad_ratio)))
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2))
    if side > max_side:
        canvas.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return canvas


def packshot_front(image: Image.Image) -> Image.Image:
    """Studio-grade packshot of the whole package. Preserves transparent packaging & eliminates erosion."""
    from .smart_packshot import make_smart_packshot
    return make_smart_packshot(image, target_side=2400, pad_ratio=0.08, fill_holes=True, sharpness_factor=1.15)


def enhance_back(image: Image.Image, max_long: int = 2400) -> Image.Image:
    """Keep the full back label, cap only oversized camera files, then crisp the text."""
    width, height = image.size
    if max(width, height) > max_long:
        scale = max_long / max(width, height)
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
    image = ImageEnhance.Sharpness(image).enhance(1.25)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    return image
