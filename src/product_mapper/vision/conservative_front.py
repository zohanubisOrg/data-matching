"""One-pass webshop front from an original photo.

Detection runs on a short preview. The delivered pixels are a single
downsample of the original. The mask only expands into the background.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np
import zxingcpp
from PIL import Image

from product_mapper.vision.barcode_side_splitter import transform_point, upright_ccw_from_angle
from product_mapper.vision.barcode_validator import validate_ean_upc_checksum

CANVAS = 2400
OCCUPANCY = 0.86
MIN_MARGIN = 48
SQUARE_PAD_RATIO = 0.18
SQUARE_FILL = 0.90
PREVIEW_LONG = 1600
PAD_RATIO = 0.03
SECOND_PASS_BUDGET_S = 2.0
MIN_COMPONENT_AREA = 0.012


class FrontRejected(Exception):
    def __init__(self, state: str, reason: str) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason


@dataclass(frozen=True)
class BarcodeHit:
    text: str
    cx: float
    cy: float
    upright_ccw: int
    area: float


def preview(image: Image.Image, max_long: int = PREVIEW_LONG) -> tuple[Image.Image, float]:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_long:
        return image, 1.0
    scale = max_long / longest
    resized = image.resize(
        (max(1, int(width * scale)), max(1, int(height * scale))),
        Image.Resampling.BILINEAR,
    )
    return resized, scale


def _hits_from_results(results, offset_x: float, offset_y: float, scale: float) -> list[BarcodeHit]:
    hits: list[BarcodeHit] = []
    for result in results:
        digits = "".join(ch for ch in str(result.text or "") if ch.isdigit())
        if not validate_ean_upc_checksum(digits):
            continue
        points = []
        for name in ("top_left", "top_right", "bottom_right", "bottom_left"):
            point = getattr(result.position, name)
            points.append(((point.x / scale) + offset_x, (point.y / scale) + offset_y))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        top_left, top_right = points[0], points[1]
        angle = float(np.degrees(np.arctan2(top_right[1] - top_left[1], top_right[0] - top_left[0])))
        hits.append(
            BarcodeHit(
                text=digits,
                cx=sum(xs) / 4.0,
                cy=sum(ys) / 4.0,
                upright_ccw=upright_ccw_from_angle(angle),
                area=max(1.0, (max(xs) - min(xs)) * (max(ys) - min(ys))),
            )
        )
    return hits


def _scan(image: Image.Image, offset_x: float, offset_y: float, *, invert: bool = False) -> list[BarcodeHit]:
    small, scale = preview(image)
    results = zxingcpp.read_barcodes(
        small,
        formats=zxingcpp.BarcodeFormat.EANUPC,
        try_rotate=True,
        try_downscale=True,
        try_invert=invert,
    )
    return _hits_from_results(results, offset_x, offset_y, scale)


def read_barcodes(image: Image.Image, budget_s: float = SECOND_PASS_BUDGET_S) -> list[BarcodeHit]:
    """One full-frame read, then at most a few seconds of half-frame reads."""
    hits = _scan(image, 0, 0)
    if hits:
        return hits
    width, height = image.size
    regions = (
        (0, 0, int(width * 0.62), height),
        (int(width * 0.38), 0, width, height),
        (0, 0, width, int(height * 0.62)),
        (0, int(height * 0.38), width, height),
    )
    started = time.perf_counter()
    for x0, y0, x1, y1 in regions:
        if time.perf_counter() - started > budget_s:
            break
        crop = image.crop((x0, y0, x1, y1))
        hits.extend(_scan(crop, x0, y0, invert=True))
        if hits:
            break
    return hits


def best_hit(hits: list[BarcodeHit]) -> BarcodeHit | None:
    if not hits:
        return None
    return max(hits, key=lambda hit: hit.area)


def border_median(rgb: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    band = max(4, min(height, width) // 80)
    samples = np.concatenate(
        [
            rgb[:band].reshape(-1, 3),
            rgb[-band:].reshape(-1, 3),
            rgb[:, :band].reshape(-1, 3),
            rgb[:, -band:].reshape(-1, 3),
        ]
    )
    return np.median(samples, axis=0)


def _valley_index(profile: np.ndarray) -> int | None:
    count = len(profile)
    start, end = int(count * 0.28), int(count * 0.72)
    if end - start < 8:
        return None
    local = profile[start:end]
    depth_index = int(np.argmin(local))
    depth = float(local[depth_index])
    trough = np.flatnonzero(local <= depth + 0.05)
    index = start + int(np.median(trough))
    left, right = profile[start:index], profile[index + 1 : end]
    if left.size == 0 or right.size == 0:
        return None
    shoulders = float(min(left.max(), right.max()))
    if depth < 0.4 and shoulders >= 0.35 and shoulders - depth >= 0.2:
        return index
    return None


def foreground_mask(rgb: np.ndarray, median: np.ndarray | None = None) -> np.ndarray:
    if median is None:
        median = border_median(rgb)
    distance = np.abs(rgb.astype(np.int16) - median.astype(np.int16)).sum(axis=2)
    chosen = None
    best_score = -1.0
    for threshold in (100, 140, 180, 220):
        mask = np.where(distance > threshold, 255, 0).astype(np.uint8)
        binary = mask > 0
        score = 0.0
        for profile in (binary.mean(axis=0), binary.mean(axis=1)):
            index = _valley_index(profile)
            if index is None:
                continue
            start, end = int(len(profile) * 0.28), int(len(profile) * 0.72)
            left, right = profile[start:index], profile[index + 1 : end]
            score = max(score, float(min(left.max(), right.max()) - profile[index]))
        if score > best_score:
            best_score = score
            chosen = mask
    if chosen is None:
        chosen = np.where(distance > 140, 255, 0).astype(np.uint8)
    return chosen


def _components(mask: np.ndarray) -> list[dict]:
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    height, width = mask.shape
    minimum = MIN_COMPONENT_AREA * height * width
    found = []
    for index in range(1, count):
        x, y, box_w, box_h, area = (int(value) for value in stats[index])
        if area < minimum:
            continue
        box = (x, y, x + box_w, y + box_h)
        found.append(
            {
                "box": box,
                "area": area,
                "touches": x <= 1 or y <= 1 or x + box_w >= width - 1 or y + box_h >= height - 1,
            }
        )
    return found


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _gap_is_background(mask: np.ndarray, front: tuple[int, int, int, int], back: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = front
    bx0, by0, bx1, by1 = back
    if bx1 <= x0:
        strip = mask[max(y0, by0) : min(y1, by1), bx1:x0]
    elif x1 <= bx0:
        strip = mask[max(y0, by0) : min(y1, by1), x1:bx0]
    elif by1 <= y0:
        strip = mask[by1:y0, max(x0, bx0) : min(x1, bx1)]
    elif y1 <= by0:
        strip = mask[y1:by0, max(x0, bx0) : min(x1, bx1)]
    else:
        return False
    if strip.size == 0:
        return False
    return float(np.count_nonzero(strip)) / strip.size < 0.08


def pad_box(
    box: tuple[int, int, int, int],
    frame: tuple[int, int],
    other: tuple[int, int, int, int] | None,
    ratio: float = PAD_RATIO,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    grow_x = int(width * ratio)
    grow_y = int(height * ratio)
    nx0, ny0, nx1, ny1 = x0 - grow_x, y0 - grow_y, x1 + grow_x, y1 + grow_y
    frame_w, frame_h = frame
    nx0, ny0 = max(0, nx0), max(0, ny0)
    nx1, ny1 = min(frame_w, nx1), min(frame_h, ny1)
    if other is not None:
        ox0, oy0, ox1, oy1 = other
        if ox1 <= x0:
            nx0 = max(nx0, ox1)
        if x1 <= ox0:
            nx1 = min(nx1, ox0)
        if oy1 <= y0:
            ny0 = max(ny0, oy1)
        if y1 <= oy0:
            ny1 = min(ny1, oy0)
    return nx0, ny0, nx1, ny1


def shrink_from_seam(
    front: tuple[int, int, int, int],
    back: tuple[int, int, int, int],
    ratio: float,
) -> tuple[int, int, int, int]:
    """Move the shared edge into the front panel. An 8% move cuts the package."""
    x0, y0, x1, y1 = front
    bx0, by0, bx1, by1 = back
    width, height = x1 - x0, y1 - y0
    if bx1 <= x0:
        return (x0 + int(width * ratio), y0, x1, y1)
    if x1 <= bx0:
        return (x0, y0, x1 - int(width * ratio), y1)
    if by1 <= y0:
        return (x0, y0 + int(height * ratio), x1, y1)
    if y1 <= by0:
        return (x0, y0, x1, y1 - int(height * ratio))
    return front


def seam_cut_is_background(
    mask: np.ndarray,
    front: tuple[int, int, int, int],
    back: tuple[int, int, int, int],
    shift_ratio: float,
) -> bool:
    if shift_ratio == 0:
        return _gap_is_background(mask, front, back)
    shifted = shrink_from_seam(front, back, shift_ratio)
    x0, y0, x1, y1 = front
    sx0, sy0, sx1, sy1 = shifted
    if sx0 > x0:
        strip = mask[y0:y1, x0:sx0]
    elif sx1 < x1:
        strip = mask[y0:y1, sx1:x1]
    elif sy0 > y0:
        strip = mask[y0:sy0, x0:x1]
    elif sy1 < y1:
        strip = mask[sy1:y1, x0:x1]
    else:
        return False
    if strip.size == 0:
        return False
    return float(np.count_nonzero(strip)) / strip.size < 0.05


def _largest_box(mask: np.ndarray, origin: tuple[int, int]) -> tuple[int, int, int, int] | None:
    comps = _components(mask)
    if not comps:
        return None
    chosen = max(comps, key=lambda item: item["area"])
    x0, y0, x1, y1 = chosen["box"]
    return (x0 + origin[0], y0 + origin[1], x1 + origin[0], y1 + origin[1])


def _clipped_away_from_cut(box: tuple[int, int, int, int], frame: tuple[int, int], open_edge: str) -> bool:
    x0, y0, x1, y1 = box
    width, height = frame
    if y0 <= 2 or y1 >= height - 2:
        return True
    if open_edge != "left" and x0 <= 2:
        return True
    if open_edge != "right" and x1 >= width - 2:
        return True
    if open_edge != "top" and y0 <= 2:
        return True
    if open_edge != "bottom" and y1 >= height - 2:
        return True
    return False


def _front_from_cut(
    mask: np.ndarray,
    barcode_xy: tuple[float, float],
    cut: int,
    axis: str,
) -> tuple[int, int, int, int]:
    height, width = mask.shape
    binary = (mask > 0).astype(np.uint8)
    if axis == "x":
        left = _largest_box(binary[:, :cut], (0, 0))
        right = _largest_box(binary[:, cut:], (cut, 0))
        if left is None or right is None:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "gap did not separate two packages")
        if barcode_xy[0] < cut:
            front, open_edge, other = right, "left", left
        else:
            front, open_edge, other = left, "right", right
    else:
        top = _largest_box(binary[:cut, :], (0, 0))
        bottom = _largest_box(binary[cut:, :], (0, cut))
        if top is None or bottom is None:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "gap did not separate two packages")
        if barcode_xy[1] < cut:
            front, open_edge, other = bottom, "top", top
        else:
            front, open_edge, other = top, "bottom", bottom
    if _clipped_away_from_cut(front, (width, height), open_edge):
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front package touches the photo edge")
    padded = pad_box(front, (width, height), other)
    if _overlap(padded, other):
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front padding crosses into the other package")
    return padded


def _boundary_energy(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gradient only where package pixels sit on both sides. Outer silhouette is ignored."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lightness = lab[:, :, 0].astype(np.float32)
    gx = cv2.Sobel(lightness, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lightness, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)
    peak = float(magnitude.max())
    if peak > 0:
        magnitude /= peak
    binary = mask > 0
    span = max(6, min(binary.shape) // 40)
    vertical = np.zeros(binary.shape, bool)
    horizontal = np.zeros(binary.shape, bool)
    vertical[:, span:-span] = binary[:, :-span * 2] & binary[:, span * 2 :]
    horizontal[span:-span, :] = binary[:-span * 2, :] & binary[span * 2 :, :]
    return magnitude * vertical, magnitude * horizontal


def _max_seam(energy: np.ndarray) -> tuple[np.ndarray, float]:
    """One x index per row, following the strongest boundary."""
    height, width = energy.shape
    if height < 4 or width < 4 or float(energy.max()) <= 0:
        return np.zeros(height, np.int32), 0.0
    score = energy.astype(np.float32).copy()
    step = np.zeros((height, width), np.int8)
    for y in range(1, height):
        padded = np.pad(score[y - 1], 1, constant_values=-1e9)
        window = np.stack((padded[:-2], padded[1:-1], padded[2:]), axis=0)
        pick = np.argmax(window, axis=0).astype(np.int8)
        step[y] = pick - 1
        score[y] = energy[y] + window[pick, np.arange(width)]
    x = int(np.argmax(score[-1]))
    path = np.empty(height, np.int32)
    path[-1] = x
    for y in range(height - 1, 0, -1):
        x = int(np.clip(x + int(step[y, x]), 0, width - 1))
        path[y - 1] = x
    return path, float(energy[np.arange(height), path].mean())


def _seam_mask(mask: np.ndarray, path: np.ndarray, barcode_xy: tuple[float, float], axis: str) -> np.ndarray:
    height, width = mask.shape
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]
    if axis == "x":
        barcode_on_left = barcode_xy[0] < float(np.median(path))
        front = cols > path[:, None] if barcode_on_left else cols < path[:, None]
    else:
        barcode_on_top = barcode_xy[1] < float(np.median(path))
        front = rows > path[None, :] if barcode_on_top else rows < path[None, :]
    kept = ((mask > 0) & front).astype(np.uint8) * 255
    if np.count_nonzero(kept) < 0.12 * max(1, np.count_nonzero(mask)):
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front side of the seam is too small")
    if np.count_nonzero((mask > 0) & ~front) < 0.12 * max(1, np.count_nonzero(mask)):
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "back side of the seam is too small")
    return kept


def _second_seam(energy: np.ndarray, occupied: np.ndarray) -> float:
    blocked = energy.copy()
    blocked[occupied > 0] = 0
    _path, score = _max_seam(blocked)
    return score


def _seam_after(energy: np.ndarray, paths: list[np.ndarray]) -> tuple[np.ndarray, float]:
    blocked = energy.copy()
    rows = np.arange(energy.shape[0])
    for path in paths:
        for delta in range(-12, 13):
            cols = np.clip(path + delta, 0, energy.shape[1] - 1)
            blocked[rows, cols] = 0
    return _max_seam(blocked)


def _front_band(mask: np.ndarray, seams: list[np.ndarray], barcode_xy: tuple[float, float], axis: str) -> np.ndarray:
    """Barcode band is the back. With three bands the far end is the front and the middle is the side."""
    height, width = mask.shape
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]
    band = np.zeros((height, width), np.uint8)
    if axis == "x":
        for path in seams:
            band += (cols > path[:, None]).astype(np.uint8)
        barcode_band = int(sum(barcode_xy[0] > float(np.median(path)) for path in seams))
    else:
        for path in seams:
            band += (rows > path[None, :]).astype(np.uint8)
        barcode_band = int(sum(barcode_xy[1] > float(np.median(path)) for path in seams))
    count = len(seams) + 1
    if count > 3:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "more than three packages in one photo")
    if count == 3 and barcode_band == 1:
        front_band = barcode_band
    else:
        front_band = (count - 1) - barcode_band
    kept = ((mask > 0) & (band == front_band)).astype(np.uint8) * 255
    if np.count_nonzero(kept) < 0.12 * max(1, np.count_nonzero(mask)):
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front subject is too small")
    return kept


def _cross_contrast(rgb: np.ndarray, path: np.ndarray, axis: str) -> float:
    """Color change across a seam. Text inside one pack scores low; a second pack scores high."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    height, width = lab.shape[:2]
    if axis == "x":
        span = max(8, width // 40)
        rows = np.arange(height)
        left = lab[rows, np.clip(path - span, 0, width - 1)]
        right = lab[rows, np.clip(path + span, 0, width - 1)]
        return float(np.abs(left - right).mean())
    span = max(8, height // 40)
    cols = np.arange(width)
    above = lab[np.clip(path - span, 0, height - 1), cols]
    below = lab[np.clip(path + span, 0, height - 1), cols]
    return float(np.abs(above - below).mean())


def _package_seams(energy: np.ndarray, rgb: np.ndarray, axis: str) -> list[np.ndarray]:
    found: list[np.ndarray] = []
    blocked: list[np.ndarray] = []
    for _ in range(4):
        path, score = _max_seam(energy) if not blocked else _seam_after(energy, blocked)
        if score < 0.12:
            break
        blocked.append(path)
        if _cross_contrast(rgb, path, axis) < 18:
            continue
        found.append(path)
        if len(found) > 2:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "more than three packages in one photo")
    return found


def _chroma(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    return np.sqrt((lab[:, :, 1] - 128.0) ** 2 + (lab[:, :, 2] - 128.0) ** 2)


def _smooth_profile(profile: np.ndarray) -> np.ndarray:
    values = profile.astype(np.float32)
    kernel = 15 if values.size >= 48 else 5
    if values.size < kernel:
        return values
    return cv2.GaussianBlur(values.reshape(1, -1), (1, kernel), 0).ravel()


def _narrow_valleys(profile: np.ndarray) -> list[tuple[float, int]]:
    """Narrow drops in color coverage. A wide label panel is not a package gap."""
    smoothed = _smooth_profile(profile)
    count = len(smoothed)
    recover = max(8, int(count * 0.035))
    if count < recover * 4:
        return []
    found: list[tuple[float, int]] = []
    for index in range(recover + 2, count - recover - 2):
        if index < int(count * 0.16) or index > int(count * 0.84):
            continue
        here = float(smoothed[index])
        left = float(smoothed[index - recover : index].max())
        right = float(smoothed[index + 1 : index + 1 + recover].max())
        if min(left, right) < 0.22:
            continue
        depth = min(left, right) - here
        if depth < 0.07:
            continue
        if here > float(smoothed[index - 3 : index + 4].min()) + 0.02:
            continue
        if float(smoothed[:index].max()) < 0.28 or float(smoothed[index:].max()) < 0.28:
            continue
        found.append((depth, index))
    found.sort(reverse=True)
    peaks: list[tuple[float, int]] = []
    for depth, index in found:
        if all(abs(index - other) > int(count * 0.1) for _depth, other in peaks):
            peaks.append((depth, index))
        if len(peaks) == 3:
            break
    return peaks


def _drift_path(covered: np.ndarray, anchor: int) -> np.ndarray:
    """Follow a slanted gap without jumping onto a label crease."""
    height, width = covered.shape
    recover = max(8, int(width * 0.03))
    band = max(40, height // 16)
    samples: list[tuple[int, float]] = []
    for start in range(band, max(band, height - band), max(20, band // 3)):
        local = _smooth_profile(covered[start : start + band].mean(axis=0))
        low = max(recover, anchor - int(width * 0.1))
        high = min(width - recover - 1, anchor + int(width * 0.1))
        best_depth = 0.0
        best_x = anchor
        for index in range(low, high):
            left_start = max(0, index - recover)
            if index <= left_start:
                continue
            right_end = min(width, index + 1 + recover)
            if right_end <= index + 1:
                continue
            left = float(local[left_start:index].max())
            right = float(local[index + 1 : right_end].max())
            if min(left, right) < 0.22:
                continue
            depth = min(left, right) - float(local[index])
            if depth > best_depth:
                best_depth = depth
                best_x = index
        if best_depth > 0.05:
            samples.append((start + band // 2, float(best_x)))
    if len(samples) < 2:
        return np.full(height, anchor, np.float32)
    cursor = float(anchor)
    kept_y: list[int] = []
    kept_x: list[float] = []
    step = max(8.0, width * 0.012)
    for y_pos, x_pos in samples:
        cursor = 0.55 * cursor + 0.45 * float(np.clip(x_pos, cursor - step, cursor + step))
        kept_y.append(y_pos)
        kept_x.append(cursor)
    return np.interp(np.arange(height), kept_y, kept_x).astype(np.float32)


def _mask_on_front_side(rgb: np.ndarray, chroma: np.ndarray, front: np.ndarray) -> np.ndarray:
    height, width = front.shape
    colored = ((chroma > 12) & front).astype(np.uint8)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(colored, 8)
    if count <= 1:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front subject is too small")
    index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    core = np.where(labels == index, 255, 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    closed = cv2.morphologyEx(core, cv2.MORPH_CLOSE, kernel)
    closed = np.where(front, closed, 0).astype(np.uint8)
    background = (closed == 0).astype(np.uint8)
    bg_count, bg_labels, bg_stats, _bg_centroids = cv2.connectedComponentsWithStats(background, 8)
    limit = int(0.04 * height * width)
    for label in range(1, bg_count):
        x, y, box_w, box_h, area = (int(value) for value in bg_stats[label])
        if area > limit or x <= 1 or y <= 1 or x + box_w >= width - 1 or y + box_h >= height - 1:
            continue
        closed[bg_labels == label] = 255
    closed = np.where(front, closed, 0).astype(np.uint8)
    corners = np.concatenate(
        [
            rgb[:12, :12].reshape(-1, 3),
            rgb[:12, -12:].reshape(-1, 3),
            rgb[-12:, :12].reshape(-1, 3),
            rgb[-12:, -12:].reshape(-1, 3),
        ]
    )
    median = np.median(corners, axis=0)
    distance = np.abs(rgb.astype(np.int16) - median.astype(np.int16)).sum(axis=2)
    frame = np.zeros((height, width), bool)
    frame[:4, :] = True
    frame[-4:, :] = True
    frame[:, :4] = True
    frame[:, -4:] = True
    closed[frame & (distance < 80)] = 0
    if np.count_nonzero(closed) < 0.04 * height * width:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front subject is too small")
    return closed


def _front_of_gaps(
    rgb: np.ndarray,
    chroma: np.ndarray,
    cuts: list[tuple[float, int]],
    barcode_xy: tuple[float, float],
    *,
    vertical: bool,
) -> np.ndarray:
    if len(cuts) >= 3:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "more than three packages in one photo")
    height, width = rgb.shape[:2]
    positions = sorted(index for _depth, index in cuts)
    barcode_pos = barcode_xy[0] if vertical else barcode_xy[1]
    if len(positions) == 1:
        covered = (chroma > 18).astype(np.float32)
        path = _drift_path(covered if vertical else covered.T, positions[0])
        # A crease inside the back panel must not pull the cut onto that panel.
        slack = 8
        if vertical:
            if barcode_xy[0] >= positions[0]:
                path = np.minimum(path, float(positions[0] + slack))
            else:
                path = np.maximum(path, float(positions[0] - slack))
        elif barcode_xy[1] >= positions[0]:
            path = np.minimum(path, float(positions[0] + slack))
        else:
            path = np.maximum(path, float(positions[0] - slack))
        inset = 2
        if vertical:
            barcode_on_left = barcode_xy[0] < float(np.median(path))
            cols = np.arange(width)[None, :]
            front = cols > path[:, None] + inset if barcode_on_left else cols < path[:, None] - inset
        else:
            barcode_on_top = barcode_xy[1] < float(np.median(path))
            rows = np.arange(height)[:, None]
            front = rows > path[None, :] + inset if barcode_on_top else rows < path[None, :] - inset
    else:
        barcode_band = int(sum(barcode_pos > position for position in positions))
        if barcode_band == 1:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "barcode is on the middle subject")
        front_band = len(positions) - barcode_band
        if vertical:
            cols = np.arange(width)[None, :]
            band = np.zeros((height, width), np.uint8)
            for position in positions:
                band += (cols > position).astype(np.uint8)
            front = band == front_band
        else:
            rows = np.arange(height)[:, None]
            band = np.zeros((height, width), np.uint8)
            for position in positions:
                band += (rows > position).astype(np.uint8)
            front = band == front_band
    return _mask_on_front_side(rgb, chroma, front)


def _seam_sides_differ(rgb: np.ndarray, path: np.ndarray, axis: str) -> bool:
    """A sticker has the same package color on both far sides. Two products do not."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    height, width = lab.shape[:2]
    span = max(24, (width if axis == "x" else height) // 8)
    if axis == "x":
        rows = np.arange(height)
        left = lab[rows, np.clip(path - span, 0, width - 1)]
        right = lab[rows, np.clip(path + span, 0, width - 1)]
        return float(np.abs(left - right).mean()) >= 10
    cols = np.arange(width)
    above = lab[np.clip(path - span, 0, height - 1), cols]
    below = lab[np.clip(path + span, 0, height - 1), cols]
    return float(np.abs(above - below).mean()) >= 10


def _separate_on_color_seams(rgb: np.ndarray, mask: np.ndarray, barcode_xy: tuple[float, float]) -> np.ndarray:
    vertical, horizontal = _boundary_energy(rgb, mask)
    vertical_seams = [path for path in _package_seams(vertical, rgb, "x") if _seam_sides_differ(rgb, path, "x")]
    horizontal_paths = _package_seams(horizontal.T, rgb, "y")
    horizontal_seams = [path for path in horizontal_paths if _seam_sides_differ(rgb, path, "y")]
    if len(vertical_seams) >= len(horizontal_seams) and vertical_seams:
        return _front_band(mask, vertical_seams, barcode_xy, "x")
    if horizontal_seams:
        return _front_band(mask, horizontal_seams, barcode_xy, "y")
    raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "touching packages have no reliable boundary")


def _is_full_gap(chroma: np.ndarray, index: int, vertical: bool) -> bool:
    """A printed fold keeps color on the line. An opening between two packages does not."""
    product = chroma > 18
    if vertical:
        if index < 2 or index >= chroma.shape[1] - 2:
            return False
        left = product[:, :index].any(axis=1)
        right = product[:, index + 1 :].any(axis=1)
        span = left & right
        opening = chroma[:, index] < 18
    else:
        if index < 2 or index >= chroma.shape[0] - 2:
            return False
        above = product[:index, :].any(axis=0)
        below = product[index + 1 :, :].any(axis=0)
        span = above & below
        opening = chroma[index, :] < 18
    if int(span.sum()) < 10:
        return False
    return float(opening[span].mean()) >= 0.72


def _colored_parts(chroma: np.ndarray) -> list[tuple[float, float]]:
    """Centroids of large colored masses. One mass is one package, not a second face."""
    mask = (chroma > 28).astype(np.uint8)
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    height, width = chroma.shape
    minimum = 0.025 * height * width
    parts: list[tuple[float, float]] = []
    for index in range(1, count):
        if int(stats[index, cv2.CC_STAT_AREA]) < minimum:
            continue
        parts.append((float(centroids[index][0]), float(centroids[index][1])))
    return parts


def _cuts_between_parts(parts: list[tuple[float, float]], axis: int) -> list[tuple[float, int]]:
    """A background gap between two masses is a subject boundary even without a chroma dip."""
    coords = sorted(part[axis] for part in parts)
    found: list[tuple[float, int]] = []
    for left, right in zip(coords, coords[1:]):
        if right - left < 40:
            continue
        found.append((float(right - left), int(round((left + right) / 2))))
    return found[:2]


def _between_masses(cuts: list[tuple[float, int]], parts: list[tuple[float, float]], axis: int) -> list[tuple[float, int]]:
    """Keep the valley that actually sits between two packages."""
    if len(cuts) <= 2 or len(parts) < 2:
        return cuts
    # The two masses farthest apart on this axis are the outer packages.
    left = min(parts, key=lambda item: item[axis])
    right = max(parts, key=lambda item: item[axis])
    low, high = left[axis], right[axis]
    between = [item for item in cuts if low + 8 < item[1] < high - 8]
    if not between:
        return cuts[:2]
    middle = (low + high) / 2.0
    return [min(between, key=lambda item: abs(item[1] - middle))]


def _crack_toward_front(
    rgb: np.ndarray,
    valley: int,
    barcode_pos: float,
    *,
    vertical: bool,
) -> int | None:
    """Dark crack on the front side of a label edge. Search only that short window."""
    lightness = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    chroma = _chroma(rgb)
    if vertical:
        start_band, end_band = int(rgb.shape[0] * 0.18), int(rgb.shape[0] * 0.62)
        rows = chroma[start_band:end_band].mean(axis=1) > 18
        if int(rows.sum()) < 20:
            return None
        profile = lightness[start_band:end_band][rows].mean(axis=0)
    else:
        start_band, end_band = int(rgb.shape[1] * 0.18), int(rgb.shape[1] * 0.62)
        cols = chroma[:, start_band:end_band].mean(axis=0) > 18
        if int(cols.sum()) < 20:
            return None
        profile = lightness[:, start_band:end_band][:, cols].mean(axis=1)
    smoothed = _smooth_profile(profile)
    count = len(smoothed)
    span = 25
    limit = max(24, int(count * 0.08))
    if barcode_pos > valley:
        low, high = max(span, valley - limit), valley - 4
    else:
        low, high = valley + 4, min(count - span, valley + limit)
    if high - low < 8:
        return None
    best_depth = 18.0
    best: int | None = None
    for index in range(low, high):
        here = float(smoothed[index])
        left = float(smoothed[index - span : index].max())
        right = float(smoothed[index + 1 : index + 1 + span].max())
        depth = min(left, right) - here
        if depth < best_depth or here > float(smoothed[index - 2 : index + 3].min()) + 1.5:
            continue
        best_depth = depth
        best = index
    return best


def _snap_cut_off_label(
    rgb: np.ndarray,
    cuts: list[tuple[float, int]],
    barcode_pos: float,
    *,
    vertical: bool,
) -> list[tuple[float, int]]:
    """A label edge sits closer to the barcode than the dark crack between two packages."""
    if not cuts:
        return cuts
    _depth, index = max(cuts, key=lambda item: item[0])
    crack = _crack_toward_front(rgb, index, barcode_pos, vertical=vertical)
    if crack is None:
        return cuts
    return [(depth, int(crack) if cut == index else cut) for depth, cut in cuts]


def _keep_largest(mask: np.ndarray) -> np.ndarray:
    """Specks of table are not a second part of the package."""
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    if count <= 1:
        return mask
    index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == index, mask, 0).astype(np.uint8)


def _fill_enclosed(mask: np.ndarray) -> np.ndarray:
    """A label sitting inside one package is part of that package."""
    height, width = mask.shape
    outside = np.where(mask > 0, 0, 255).astype(np.uint8)
    border_y, border_x = np.where(outside > 0)
    on_border = (border_x == 0) | (border_y == 0) | (border_x == width - 1) | (border_y == height - 1)
    if not np.any(on_border):
        return mask
    for x_pos, y_pos in zip(border_x[on_border], border_y[on_border]):
        if outside[y_pos, x_pos] != 255:
            continue
        cv2.floodFill(outside, np.zeros((height + 2, width + 2), np.uint8), (int(x_pos), int(y_pos)), 128)
    filled = mask.copy()
    filled[outside == 255] = 255
    return filled


def _attach_pale_edges(rgb: np.ndarray, front: np.ndarray, kept: np.ndarray) -> np.ndarray:
    """Keep a pale cap or seal that sits on the front and touches the colored core."""
    corners = np.concatenate(
        [
            rgb[:8, :8].reshape(-1, 3),
            rgb[:8, -8:].reshape(-1, 3),
            rgb[-8:, :8].reshape(-1, 3),
            rgb[-8:, -8:].reshape(-1, 3),
        ]
    )
    median = np.median(corners, axis=0)
    distance = np.abs(rgb.astype(np.int16) - median.astype(np.int16)).sum(axis=2)
    pale = (_chroma(rgb) < 18) & (distance > 45) & front
    allowed = (pale | (kept > 0)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grown = kept.copy()
    for _ in range(24):
        nxt = cv2.dilate(grown, kernel) & allowed
        if np.array_equal(nxt, grown):
            break
        grown = nxt
    return _fill_enclosed(grown)


def _front_color_count(
    chroma: np.ndarray,
    cuts: list[tuple[float, int]],
    barcode_xy: tuple[float, float],
    *,
    vertical: bool,
) -> int:
    """How much package color the non-barcode side of the strongest cut keeps."""
    if not cuts:
        return 0
    _depth, index = max(cuts, key=lambda item: item[0])
    if vertical:
        front = np.arange(chroma.shape[1]) < index if barcode_xy[0] >= index else np.arange(chroma.shape[1]) > index
        side = (chroma > 28)[:, front]
    else:
        front = np.arange(chroma.shape[0]) < index if barcode_xy[1] >= index else np.arange(chroma.shape[0]) > index
        side = (chroma > 28)[front, :]
    return int(side.sum())


def _confirmed_cuts(
    cuts: list[tuple[float, int]],
    chroma: np.ndarray,
    parts: list[tuple[float, float]],
    *,
    vertical: bool,
) -> list[tuple[float, int]]:
    axis = 0 if vertical else 1
    confirmed: list[tuple[float, int]] = []
    for depth, index in cuts:
        if _is_full_gap(chroma, index, vertical):
            confirmed.append((depth, index))
            continue
        if len(parts) < 2:
            continue
        before = any(part[axis] < index - 10 for part in parts)
        after = any(part[axis] > index + 10 for part in parts)
        if before and after:
            confirmed.append((depth, index))
    return confirmed


MATCH_MIN = 0.12
MATCH_MARGIN = 0.06
FEATURE_MIN = 0.08
FEATURE_MARGIN = 0.05


def _cut_axis(
    rgb: np.ndarray,
    barcode_xy: tuple[float, float],
) -> tuple[bool, list[tuple[float, int]]] | None:
    """The axis that separates subjects. None means one package."""
    chroma = _chroma(rgb)
    covered = (chroma > 18).astype(np.float32)
    parts = _colored_parts(chroma)
    vertical_cuts = _confirmed_cuts(_narrow_valleys(covered.mean(axis=0)), chroma, parts, vertical=True)
    horizontal_cuts = _confirmed_cuts(_narrow_valleys(covered.mean(axis=1)), chroma, parts, vertical=False)
    if len(horizontal_cuts) >= 3 and 1 <= len(vertical_cuts) <= 2:
        horizontal_cuts = []
    if len(vertical_cuts) >= 3 and 1 <= len(horizontal_cuts) <= 2:
        vertical_cuts = []
    vertical_cuts = _between_masses(vertical_cuts, parts, 0)
    horizontal_cuts = _between_masses(horizontal_cuts, parts, 1)
    vertical_cuts = _snap_cut_off_label(rgb, vertical_cuts, barcode_xy[0], vertical=True)
    horizontal_cuts = _snap_cut_off_label(rgb, horizontal_cuts, barcode_xy[1], vertical=False)
    if len(vertical_cuts) >= 3 or len(horizontal_cuts) >= 3:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "more than three packages in one photo")
    if not vertical_cuts and not horizontal_cuts and len(parts) >= 2:
        vertical_cuts = _cuts_between_parts(parts, 0)
        horizontal_cuts = _cuts_between_parts(parts, 1)
        if len(vertical_cuts) >= 3 and 1 <= len(horizontal_cuts) <= 2:
            vertical_cuts = []
        if len(horizontal_cuts) >= 3 and 1 <= len(vertical_cuts) <= 2:
            horizontal_cuts = []
    if not vertical_cuts and not horizontal_cuts:
        return None
    if vertical_cuts and not horizontal_cuts:
        return True, vertical_cuts
    if horizontal_cuts and not vertical_cuts:
        return False, horizontal_cuts
    vertical = _front_color_count(chroma, vertical_cuts, barcode_xy, vertical=True) >= _front_color_count(
        chroma, horizontal_cuts, barcode_xy, vertical=False
    )
    return vertical, vertical_cuts if vertical else horizontal_cuts


def _subject_crop(rgb: np.ndarray, mask: np.ndarray, *, keep_interior: bool = False) -> np.ndarray | None:
    ys, xs = np.where(mask > 0)
    if len(xs) < 16:
        return None
    crop = rgb[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1].copy()
    if not keep_interior:
        local = mask[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1] > 0
        crop[~local] = 255
    return crop


def _feature_score(crop: np.ndarray, reference: np.ndarray, sift) -> float | None:
    """Share of package keypoints that match the customer photo."""
    gray_crop = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    gray_reference = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
    _crop_points, crop_desc = sift.detectAndCompute(gray_crop, None)
    _reference_points, reference_desc = sift.detectAndCompute(gray_reference, None)
    if crop_desc is None or reference_desc is None or len(crop_desc) < 12 or len(reference_desc) < 12:
        return None
    try:
        pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(crop_desc, reference_desc, k=2)
    except cv2.error:
        return None
    good = 0
    for pair in pairs:
        if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
            good += 1
    return good / float(len(crop_desc))


def _appearance(rgb: np.ndarray, mask: np.ndarray, reference: np.ndarray) -> float:
    """Spatial match between a subject crop and a customer photo. Higher is closer."""
    crop = _subject_crop(rgb, mask)
    if crop is None or reference.size == 0:
        return -1.0

    def signature(image: np.ndarray) -> np.ndarray:
        resized = np.asarray(Image.fromarray(image).resize((48, 48), Image.Resampling.BILINEAR))
        lab = cv2.cvtColor(resized, cv2.COLOR_RGB2LAB).astype(np.float32).reshape(-1)
        centered = lab - lab.mean()
        scale = float(centered.std())
        if scale < 1e-3:
            return np.zeros_like(centered)
        return centered / scale

    return float((signature(crop) * signature(reference)).mean())


def _seam_subject_masks(rgb: np.ndarray, mask: np.ndarray) -> list[np.ndarray]:
    """Subjects that touch, split on color boundaries rather than a background gap."""
    vertical_energy, horizontal_energy = _boundary_energy(rgb, mask)
    vertical_seams = [path for path in _package_seams(vertical_energy, rgb, "x") if _seam_sides_differ(rgb, path, "x")]
    horizontal_paths = _package_seams(horizontal_energy.T, rgb, "y")
    horizontal_seams = [path for path in horizontal_paths if _seam_sides_differ(rgb, path, "y")]
    if len(vertical_seams) >= len(horizontal_seams) and vertical_seams:
        seams, axis = vertical_seams, "x"
    elif horizontal_seams:
        seams, axis = horizontal_seams, "y"
    else:
        return []
    height, width = mask.shape
    index = np.zeros((height, width), np.uint8)
    if axis == "x":
        cols = np.arange(width)[None, :]
        for path in seams:
            index += (cols > path[:, None]).astype(np.uint8)
    else:
        rows = np.arange(height)[:, None]
        for path in seams:
            index += (rows > path[None, :]).astype(np.uint8)
    found: list[np.ndarray] = []
    covered = max(1, int(np.count_nonzero(mask)))
    for value in range(int(index.max()) + 1):
        kept = np.where((mask > 0) & (index == value), 255, 0).astype(np.uint8)
        if np.count_nonzero(kept) < 0.08 * covered:
            continue
        found.append(_keep_largest(kept))
    return found


def _subject_masks(rgb: np.ndarray, barcode_xy: tuple[float, float]) -> list[np.ndarray]:
    axis = _cut_axis(rgb, barcode_xy)
    if axis is None:
        return _seam_subject_masks(rgb, foreground_mask(rgb))
    vertical, cuts = axis
    chroma = _chroma(rgb)
    height, width = rgb.shape[:2]
    positions = sorted(index for _depth, index in cuts)
    limit = width if vertical else height
    edges = [0, *[position for position in positions if 8 < position < limit - 8], limit]
    found: list[np.ndarray] = []
    for start, end in zip(edges, edges[1:]):
        if end - start < 8:
            continue
        region = np.zeros((height, width), bool)
        if vertical:
            region[:, start:end] = True
        else:
            region[start:end, :] = True
        try:
            found.append(_mask_on_front_side(rgb, chroma, region))
        except FrontRejected:
            continue
    return found


def _same_package_split(rgb: np.ndarray, masks: list[np.ndarray]) -> bool:
    """Seam fragments of one package share a color. Two wide subjects are separate packs."""
    spans = []
    for mask in masks:
        columns = np.flatnonzero(mask.any(axis=0))
        rows = np.flatnonzero(mask.any(axis=1))
        if len(columns) == 0 or len(rows) == 0:
            continue
        spans.append(
            max(
                (int(columns[-1] - columns[0]) + 1) / mask.shape[1],
                (int(rows[-1] - rows[0]) + 1) / mask.shape[0],
            )
        )
    if len(spans) >= 2 and min(spans) >= 0.18:
        return False
    if len(_colored_parts(_chroma(rgb))) > 1:
        return False
    means = []
    for mask in masks:
        pixels = rgb[mask > 0]
        if len(pixels) < 20:
            continue
        means.append(pixels.astype(np.float32).mean(axis=0))
    if len(means) < 2:
        return True
    for index, left in enumerate(means):
        for right in means[index + 1 :]:
            if float(np.abs(left - right).sum()) > 80:
                return False
    return True


def _mask_matching_reference(
    rgb: np.ndarray,
    barcode_xy: tuple[float, float],
    reference: np.ndarray,
    back: np.ndarray | None,
    *,
    review: bool = False,
) -> np.ndarray | None:
    """Pick the subject that matches the customer front. Position is not used."""
    masks = _subject_masks(rgb, barcode_xy)
    if len(masks) < 2 or _same_package_split(rgb, masks):
        return None
    return _best_reference_subject(rgb, masks, reference, back, review=review)


def separate_touching(rgb: np.ndarray, mask: np.ndarray, barcode_xy: tuple[float, float]) -> np.ndarray:
    """Two or three touching subjects.

    A separate barcode face is the back when another face is in the frame.
    A barcode printed on the chosen package stays with that package.
    One colored mass is one package, even when a label band or the long axis looks like a seam.
    """
    axis = _cut_axis(rgb, barcode_xy)
    if axis is None:
        try:
            return _separate_on_color_seams(rgb, mask, barcode_xy)
        except FrontRejected as error:
            if len(_colored_parts(_chroma(rgb))) <= 1 and (
                "more than three" in error.reason or "no reliable" in error.reason or "too small" in error.reason
            ):
                raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "single package") from error
            raise
    vertical, cuts = axis
    kept = _front_of_gaps(rgb, _chroma(rgb), cuts, barcode_xy, vertical=vertical)
    return _fill_enclosed(kept)


def _projection_bands(rgb: np.ndarray) -> list[np.ndarray]:
    """Two or three packages with a real gap between them.

    A label stripe inside one package is narrower than a second package, so it
    does not count. Packages that touch with no gap are left to the seam splitter.
    """
    chroma = _chroma(rgb)
    light = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    # High chroma is a printed face. Dark glass is a bottle. Cardboard sits in between.
    product = (chroma > 28) | (light < 70)
    height, width = product.shape

    def spans(occupancy: np.ndarray) -> list[tuple[int, int]]:
        smooth = np.convolve(occupancy.astype(np.float32), np.ones(9) / 9.0, mode="same")
        active = smooth > 0.12
        found: list[tuple[int, int]] = []
        start = None
        limit = len(active)
        for index, on in enumerate(active):
            if on and start is None:
                start = index
            elif not on and start is not None:
                if index - start >= int(0.18 * limit):
                    found.append((start, index))
                start = None
        if start is not None and limit - start >= int(0.18 * limit):
            found.append((start, limit))
        return found

    vertical = spans(product.mean(axis=0))
    horizontal = spans(product.mean(axis=1))
    if 2 <= len(vertical) <= 3 and len(vertical) >= len(horizontal):
        chosen, upright = vertical, True
    elif 2 <= len(horizontal) <= 3:
        chosen, upright = horizontal, False
    elif len(vertical) == 1:
        chosen, upright = vertical, True
    elif len(horizontal) == 1:
        chosen, upright = horizontal, False
    else:
        return []
    masks = []
    for start, end in chosen:
        mask = np.zeros((height, width), np.uint8)
        if upright:
            mask[:, start:end] = np.where(product[:, start:end], 255, 0)
        else:
            mask[start:end, :] = np.where(product[start:end, :], 255, 0)
        if np.count_nonzero(mask) < 0.08 * max(1, int(product.sum())):
            continue
        masks.append(mask)
    if len(masks) == 1:
        pale = _pale_sibling(rgb, masks[0])
        if pale is not None:
            masks.append(pale)
    if not 2 <= len(masks) <= 3:
        return []
    return masks


def _pale_sibling(rgb: np.ndarray, strong: np.ndarray) -> np.ndarray | None:
    """A white nutrition panel sitting beside a colored front."""
    outside = (foreground_mask(rgb) > 0) & (strong == 0)
    if int(outside.sum()) < 0.25 * max(1, int((strong > 0).sum())):
        return None
    sibling = _keep_largest(np.where(outside, 255, 0).astype(np.uint8))
    if int((sibling > 0).sum()) < 0.25 * max(1, int((strong > 0).sum())):
        return None
    sy, sx = np.where(sibling > 0)
    ty, tx = np.where(strong > 0)
    center_x = (int(sx.min()) + int(sx.max())) / 2
    center_y = (int(sy.min()) + int(sy.max())) / 2
    # Pale print on the chosen package sits inside it. A second panel sits beside it.
    if int(tx.min()) <= center_x <= int(tx.max()) and int(ty.min()) <= center_y <= int(ty.max()):
        return None
    surrounds = (
        int(sx.min()) < int(tx.min())
        and int(sx.max()) > int(tx.max())
        and int(sy.min()) < int(ty.min())
        and int(sy.max()) > int(ty.max())
    )
    if surrounds:
        return None
    return sibling


def _touching_pair(rgb: np.ndarray) -> list[np.ndarray]:
    """Two packs that touch, split on the strongest seam in the middle of the frame."""
    light = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    gradient = np.abs(cv2.Sobel(light, cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0)
    width = len(gradient)
    start, end = int(width * 0.35), int(width * 0.65)
    window = gradient[start:end]
    if window.size == 0 or float(window.max()) < max(8.0, float(np.median(gradient)) * 1.35):
        return []
    cut = start + int(np.argmax(window))
    chroma = _chroma(rgb)
    product = (chroma > 20) | (light < 80)
    total = max(1, int(product.sum()))
    left = np.zeros(product.shape, np.uint8)
    right = np.zeros(product.shape, np.uint8)
    left[:, :cut] = np.where(product[:, :cut], 255, 0)
    right[:, cut:] = np.where(product[:, cut:], 255, 0)
    if int((left > 0).sum()) < 0.2 * total or int((right > 0).sum()) < 0.2 * total:
        return []
    if _half_is_two_colors(rgb, left) or _half_is_two_colors(rgb, right):
        return []
    return [left, right]


def _half_is_two_colors(rgb: np.ndarray, mask: np.ndarray) -> bool:
    """True when one side of a seam still holds two different packages."""
    columns = np.flatnonzero(mask.any(axis=0))
    if len(columns) < 24:
        return False
    third = max(4, (int(columns[-1]) - int(columns[0])) // 3)
    left_columns = columns[:third]
    right_columns = columns[-third:]
    left_pixels = rgb[:, left_columns][mask[:, left_columns] > 0]
    right_pixels = rgb[:, right_columns][mask[:, right_columns] > 0]
    if len(left_pixels) < 10 or len(right_pixels) < 10:
        return False
    return float(np.abs(left_pixels.mean(axis=0) - right_pixels.mean(axis=0)).sum()) > 80


def _best_reference_subject(
    rgb: np.ndarray,
    masks: list[np.ndarray],
    reference: np.ndarray,
    back: np.ndarray | None,
    *,
    review: bool = False,
) -> np.ndarray:
    """The one subject that matches the customer front. The others stay out of the crop."""
    crops = [_subject_crop(rgb, mask, keep_interior=True) for mask in masks]
    sift = cv2.SIFT_create(nfeatures=2000)
    feature_scores: list[float] = []
    for crop in crops:
        if crop is None:
            feature_scores = []
            break
        value = _feature_score(crop, reference, sift)
        if value is None:
            feature_scores = []
            break
        feature_scores.append(value)
    appearance_scores = [_appearance(rgb, mask, reference) for mask in masks]

    def choice(scores: list[float], minimum: float, margin: float) -> tuple[int, float] | None:
        if len(scores) < 2:
            return None
        best_index = max(range(len(scores)), key=lambda index: scores[index])
        ordered = sorted(scores, reverse=True)
        if ordered[0] < minimum or ordered[0] - ordered[1] < margin:
            return None
        return best_index, ordered[0]

    # Keypoints decide when they are strong. A glossy bottle often has a weak
    # keypoint score and a clear color match, so appearance is the fallback.
    chosen = choice(feature_scores, FEATURE_MIN, FEATURE_MARGIN) if feature_scores else None
    method = "feature"
    if chosen is None:
        chosen = choice(appearance_scores, MATCH_MIN, MATCH_MARGIN)
        method = "appearance"
    if chosen is None:
        if not review:
            raise FrontRejected("QA_RETURN", "customer front does not match one subject")
        pool = appearance_scores or feature_scores
        if not pool:
            raise FrontRejected("QA_RETURN", "customer front does not match one subject")
        return masks[max(range(len(pool)), key=lambda index: pool[index])]
    best, winning = chosen
    if review:
        return masks[best]
    if back is not None and crops[best] is not None:
        if method == "feature":
            back_score = _feature_score(crops[best], back, sift)
        else:
            back_score = _appearance(rgb, masks[best], back)
        if back_score is None or back_score >= winning:
            raise FrontRejected("QA_RETURN", "chosen face matches the back photo")
    return masks[best]


def _reject_if_this_face_is_the_back(
    rgb: np.ndarray,
    mask: np.ndarray,
    reference: np.ndarray | None,
    back: np.ndarray | None,
) -> None:
    """A photo that is only the nutrition panel must not ship as the front."""
    if reference is None or back is None:
        return
    crop = _subject_crop(rgb, mask, keep_interior=True)
    if crop is None:
        return
    sift = cv2.SIFT_create(nfeatures=1500)
    front_score = _feature_score(crop, reference, sift)
    back_score = _feature_score(crop, back, sift)
    if front_score is None or back_score is None:
        front_score = _appearance(rgb, mask, reference)
        back_score = _appearance(rgb, mask, back)
    if back_score >= 0.05 and back_score >= front_score + 0.01:
        raise FrontRejected("QA_RETURN", "chosen face matches the back photo")


def _product_pixels(rgb: np.ndarray) -> np.ndarray:
    """Printed face or dark glass. Plain cardboard stays out."""
    light = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0].astype(np.float32)
    return (_chroma(rgb) > 28) | (light < 70)


def _mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _occupancy_spans(occupancy: np.ndarray, minimum_ratio: float) -> list[tuple[int, int]]:
    smooth = np.convolve(occupancy.astype(np.float32), np.ones(9) / 9.0, mode="same")
    active = smooth > 0.12
    found: list[tuple[int, int]] = []
    start = None
    limit = len(active)
    minimum = max(8, int(minimum_ratio * limit))
    for index, on in enumerate(active):
        if on and start is None:
            start = index
        elif not on and start is not None:
            if index - start >= minimum:
                found.append((start, index))
            start = None
    if start is not None and limit - start >= minimum:
        found.append((start, limit))
    return found


def _coalesce_cap_and_body(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """A short lid and the taller body on the same footprint are one package."""
    if len(spans) < 2:
        return list(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        previous_start, previous_end = merged[-1]
        gap = start - previous_end
        shorter = min(previous_end - previous_start, end - start)
        longer = max(previous_end - previous_start, end - start)
        if shorter > 0 and gap < shorter and shorter < 0.55 * longer:
            merged[-1] = (previous_start, end)
            continue
        merged.append((start, end))
    return merged


def _is_cut_from_component(
    box: tuple[int, int, int, int],
    component: tuple[int, int, int, int],
    chosen_area: int,
    component_area: int,
) -> bool:
    """True when the crop is a lid, a label stripe, or a patch inside one package.

    A full subject sitting beside another subject is not a cut, even when the
    two touch and share one connected component.
    """
    x0, y0, x1, y1 = box
    cx0, cy0, cx1, cy1 = component
    comp_w = max(1, cx1 - cx0)
    comp_h = max(1, cy1 - cy0)
    box_w = max(1, x1 - x0)
    box_h = max(1, y1 - y0)
    inset_left = x0 - cx0
    inset_right = cx1 - x1
    inset_top = y0 - cy0
    inset_bottom = cy1 - y1
    interior = (
        min(inset_left, inset_right, inset_top, inset_bottom) >= 8
        and chosen_area < 0.5 * component_area
    )
    if interior:
        return True
    if min(box_w, box_h) / max(box_w, box_h) >= 0.45 or component_area < 1.35 * chosen_area:
        return False
    if box_h <= box_w:
        spans = box_w >= 0.7 * comp_w
        continues = inset_top > 0.08 * comp_h or inset_bottom > 0.08 * comp_h
        siblings = inset_left > 0.08 * comp_w and inset_right > 0.08 * comp_w
    else:
        spans = box_h >= 0.7 * comp_h
        continues = inset_left > 0.08 * comp_w or inset_right > 0.08 * comp_w
        siblings = inset_top > 0.08 * comp_h and inset_bottom > 0.08 * comp_h
    return spans and continues and not siblings


def _grow_into_component(product: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """A label stripe or an edge slice is replaced by the package component that contains it."""
    chosen = mask > 0
    chosen_area = int(chosen.sum())
    box = _mask_bbox(mask)
    if box is None or chosen_area < 16 or not product.any():
        return mask
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(product.astype(np.uint8), 8)
    best_label = 0
    best_overlap = 0
    for label in range(1, count):
        overlap = int(((labels == label) & chosen).sum())
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    if best_label == 0 or best_overlap < 0.35 * chosen_area:
        return mask
    component_area = int(stats[best_label, cv2.CC_STAT_AREA])
    comp_x = int(stats[best_label, cv2.CC_STAT_LEFT])
    comp_y = int(stats[best_label, cv2.CC_STAT_TOP])
    comp_w = int(stats[best_label, cv2.CC_STAT_WIDTH])
    comp_h = int(stats[best_label, cv2.CC_STAT_HEIGHT])
    frame_h, frame_w = mask.shape
    if comp_w > 0.92 * frame_w and comp_h > 0.92 * frame_h:
        return mask
    component_box = (comp_x, comp_y, comp_x + comp_w, comp_y + comp_h)
    if not _is_cut_from_component(box, component_box, chosen_area, component_area):
        return mask
    return np.where(labels == best_label, 255, 0).astype(np.uint8)


def _attach_partner_span(product: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Pull a disconnected lid or body back onto the package that was actually chosen."""
    box = _mask_bbox(mask)
    if box is None:
        return mask
    grown = mask.copy()
    for upright in (False, True):
        grown = _attach_one_axis(product, grown, upright=upright)
    return grown


def _attach_one_axis(product: np.ndarray, mask: np.ndarray, *, upright: bool) -> np.ndarray:
    occupancy = product.mean(axis=0 if upright else 1)
    spans = _occupancy_spans(occupancy, 0.10)
    if len(spans) < 2:
        return mask
    box = _mask_bbox(mask)
    if box is None:
        return mask
    x0, y0, x1, y1 = box
    axis_start, axis_end = (x0, x1) if upright else (y0, y1)
    center = (axis_start + axis_end) // 2
    home = next(((start, end) for start, end in spans if start <= center < end), None)
    if home is None:
        return mask
    home_length = home[1] - home[0]
    partners: list[tuple[int, int]] = []
    for start, end in spans:
        if (start, end) == home:
            continue
        gap = start - home[1] if start >= home[1] else home[0] - end
        if gap < 0:
            continue
        length = end - start
        shorter = min(home_length, length)
        longer = max(home_length, length)
        if gap < shorter and shorter < 0.55 * longer:
            partners.append((start, end))
    if not partners:
        return mask
    cross = product.shape[0] if upright else product.shape[1]
    home_band = np.zeros(cross, bool)
    if upright:
        home_band |= product[:, home[0] : home[1]].any(axis=1)
    else:
        home_band |= product[home[0] : home[1], :].any(axis=0)
    shared = home_band.copy()
    for start, end in partners:
        if upright:
            shared &= product[:, start:end].any(axis=1)
        else:
            shared &= product[start:end, :].any(axis=0)
    if upright:
        shared[:y0] = False
        shared[y1:] = False
    else:
        shared[:x0] = False
        shared[x1:] = False
    if int(shared.sum()) < 8:
        return mask
    lo = min([home[0], *[start for start, _end in partners]])
    hi = max([home[1], *[end for _start, end in partners]])
    grown = mask.copy()
    if upright:
        grown[shared, lo:hi] = 255
    else:
        grown[lo:hi, shared] = 255
    return grown


def _pieces_from_spans(
    mask: np.ndarray,
    spans: list[tuple[int, int]],
    *,
    upright: bool,
) -> list[np.ndarray]:
    pieces: list[np.ndarray] = []
    covered = max(1, int(np.count_nonzero(mask)))
    for start, end in spans:
        piece = np.zeros(mask.shape, np.uint8)
        if upright:
            piece[:, start:end] = mask[:, start:end]
        else:
            piece[start:end, :] = mask[start:end, :]
        if np.count_nonzero(piece) < 0.15 * covered:
            continue
        pieces.append(_keep_largest(piece))
    return pieces if 2 <= len(pieces) <= 3 else []


def _separate_packages(rgb: np.ndarray, mask: np.ndarray) -> list[np.ndarray]:
    """Two packages inside one crop. A lid and its body stay together."""
    binary = mask > 0
    if int(binary.sum()) < 16:
        return []
    vertical = _coalesce_cap_and_body(_occupancy_spans(binary.mean(axis=0), 0.18))
    horizontal = _coalesce_cap_and_body(_occupancy_spans(binary.mean(axis=1), 0.18))
    if 2 <= len(vertical) <= 3 and len(vertical) >= len(horizontal):
        return _pieces_from_spans(mask, vertical, upright=True)
    if 2 <= len(horizontal) <= 3:
        return _pieces_from_spans(mask, horizontal, upright=False)
    box = _mask_bbox(mask)
    if box is None:
        return []
    x0, y0, x1, y1 = box
    if x1 - x0 < 24 or y1 - y0 < 24:
        return []
    pair = _touching_pair(rgb[y0:y1, x0:x1])
    if len(pair) != 2:
        return []
    pieces = []
    for piece in pair:
        full = np.zeros(mask.shape, np.uint8)
        full[y0:y1, x0:x1] = piece
        if np.count_nonzero(full) < 0.15 * max(1, int(np.count_nonzero(mask))):
            continue
        pieces.append(_keep_largest(full))
    return pieces if len(pieces) == 2 else []


def _touches_frame(mask: np.ndarray) -> bool:
    box = _mask_bbox(mask)
    if box is None:
        return True
    height, width = mask.shape
    x0, y0, x1, y1 = box
    return x0 <= 1 or y0 <= 1 or x1 >= width - 1 or y1 >= height - 1


def _prefer_complete_piece(masks: list[np.ndarray]) -> np.ndarray:
    """A border sliver loses to a package that sits inside the frame."""
    interior = [mask for mask in masks if not _touches_frame(mask)]
    pool = interior or masks
    return max(pool, key=lambda item: int(np.count_nonzero(item)))


def _restore_full_package(
    rgb: np.ndarray,
    mask: np.ndarray,
    reference: np.ndarray | None,
    back: np.ndarray | None,
    *,
    review: bool,
) -> np.ndarray:
    """Grow a lid band or an edge slice back to one complete package."""
    product = _product_pixels(rgb)
    grown = _attach_partner_span(product, _grow_into_component(product, mask))
    pieces = _separate_packages(rgb, grown)
    if len(pieces) < 2:
        return _keep_largest(grown)
    if reference is None:
        return _keep_largest(_prefer_complete_piece(pieces))
    try:
        chosen = _best_reference_subject(rgb, pieces, reference, back, review=review)
    except FrontRejected:
        if not review:
            raise
        chosen = _prefer_complete_piece(pieces)
    if _touches_frame(chosen) and any(not _touches_frame(piece) for piece in pieces):
        box = _mask_bbox(chosen)
        if box is not None:
            width = box[2] - box[0]
            height = box[3] - box[1]
            if min(width, height) / max(width, height) < 0.45:
                chosen = _prefer_complete_piece(pieces)
    return _keep_largest(chosen)


def select_front_package(
    rgb: np.ndarray,
    barcode_xy: tuple[float, float] | None,
    reference: np.ndarray | None = None,
    back: np.ndarray | None = None,
    *,
    review: bool = False,
) -> tuple[tuple[int, int, int, int], np.ndarray]:
    """Return the front package box and mask.

    When a customer front photo is available, the subject that matches it is kept,
    including a barcode printed on that subject. Otherwise touching packs are split
    on their boundary and the barcode face is the back.
    """
    mask = foreground_mask(rgb)
    if reference is None and barcode_xy is not None and not review:
        possible = _subject_masks(rgb, barcode_xy)
        if len(possible) >= 2:
            raise FrontRejected("QA_RETURN", "multiple subjects need a front reference or hash-bound human review")
    kept = None
    subjects = _projection_bands(rgb)
    if len(subjects) < 2 and reference is not None:
        pair = _touching_pair(rgb)
        if len(pair) == 2:
            try:
                kept = _best_reference_subject(rgb, pair, reference, back, review=review)
                subjects = pair
            except FrontRejected:
                kept = None
    if kept is None and len(subjects) >= 2 and reference is not None:
        kept = _best_reference_subject(rgb, subjects, reference, back, review=review)
    if kept is None and reference is not None and barcode_xy is not None:
        try:
            kept = _mask_matching_reference(rgb, barcode_xy, reference, back, review=review)
        except FrontRejected as error:
            if error.state == "QA_RETURN" and not review:
                raise
            kept = None
    if kept is None and barcode_xy is not None:
        try:
            kept = separate_touching(rgb, mask, barcode_xy)
        except FrontRejected as error:
            if "middle" in error.reason and not review:
                raise
            if "more than three" in error.reason:
                largest = _keep_largest(mask)
                share = np.count_nonzero(largest) / max(1, np.count_nonzero(mask))
                if share < 0.35 and not review:
                    raise
                kept = largest
            elif "single package" in error.reason:
                kept = _attach_pale_edges(rgb, np.ones(mask.shape[:2], bool), mask)
            else:
                box = select_front_box(mask, barcode_xy)
                kept = np.zeros_like(mask)
                kept[box[1] : box[3], box[0] : box[2]] = mask[box[1] : box[3], box[0] : box[2]]
    elif kept is None:
        if len(_colored_parts(_chroma(rgb))) <= 1:
            kept = mask
        else:
            box = select_front_box(mask, None)
            kept = np.zeros_like(mask)
            kept[box[1] : box[3], box[0] : box[2]] = mask[box[1] : box[3], box[0] : box[2]]
    kept = _keep_largest(kept)
    kept = _restore_full_package(rgb, kept, reference, back, review=review)
    if reference is not None and back is not None:
        _reject_if_this_face_is_the_back(rgb, kept, reference, back)
    ys, xs = np.where(kept > 0)
    if len(xs) == 0:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front mask is empty")
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    height, width = kept.shape
    core_distance = np.abs(rgb.astype(np.int16) - border_median(rgb).astype(np.int16)).sum(axis=2)
    core = (kept > 0) & (core_distance > 160)
    edge_load = max(
        float(core[0].mean()),
        float(core[-1].mean()),
        float(core[:, 0].mean()),
        float(core[:, -1].mean()),
    )
    if not review and (edge_load > 0.12 or core[0].any() or core[-1].any() or core[:, 0].any() or core[:, -1].any()):
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front package touches the photo edge")
    return box, kept


def select_front_box(
    mask: np.ndarray,
    barcode_xy: tuple[float, float] | None,
) -> tuple[int, int, int, int]:
    height, width = mask.shape
    binary = (mask > 0).astype(np.uint8)
    cut_x = _valley_index(binary.mean(axis=0))
    cut_y = _valley_index(binary.mean(axis=1))
    if barcode_xy is not None and (cut_x is not None or cut_y is not None):
        use_x = cut_x is not None and (cut_y is None or abs(barcode_xy[0] - cut_x) >= abs(barcode_xy[1] - (cut_y or 0)))
        if use_x and cut_x is not None:
            return _front_from_cut(mask, barcode_xy, cut_x, "x")
        if cut_y is not None:
            return _front_from_cut(mask, barcode_xy, cut_y, "y")
    comps = _components(mask)
    if barcode_xy is not None:
        bx, by = barcode_xy
        back = next((item for item in comps if item["box"][0] <= bx < item["box"][2] and item["box"][1] <= by < item["box"][3]), None)
        if back is None:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "barcode panel was not found")
        choices = []
        for other in comps:
            if other is back or other["touches"]:
                continue
            if not _gap_is_background(mask, other["box"], back["box"]):
                continue
            padded = pad_box(other["box"], (width, height), back["box"])
            if _overlap(padded, back["box"]):
                continue
            if not seam_cut_is_background(mask, other["box"], back["box"], 0):
                continue
            choices.append(other)
        if not choices:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "no background gap between back and front")
        if len(choices) > 2:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "more than three packages in one photo")
        bx, by = barcode_xy

        def distance(item: dict) -> float:
            x0, y0, x1, y1 = item["box"]
            return (x0 + x1) / 2 - bx, (y0 + y1) / 2 - by

        ends = [item for item in choices if distance(item)[0] * distance(item)[0] + distance(item)[1] * distance(item)[1] > 1]
        if len(choices) == 2:
            left = any(distance(item)[0] < -10 for item in choices)
            right = any(distance(item)[0] > 10 for item in choices)
            above = any(distance(item)[1] < -10 for item in choices)
            below = any(distance(item)[1] > 10 for item in choices)
            if (left and right) or (above and below):
                return pad_box(back["box"], (width, height), None)
        front = max(ends or choices, key=lambda item: distance(item)[0] ** 2 + distance(item)[1] ** 2)
        return pad_box(front["box"], (width, height), back["box"])
    if len(comps) != 1 or comps[0]["touches"]:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "front-only photo is clipped or ambiguous")
    return pad_box(comps[0]["box"], (width, height), None)


def core_is_preserved(alpha: np.ndarray, core: np.ndarray) -> bool:
    if alpha.shape != core.shape or not core.any():
        return False
    covered = np.count_nonzero((alpha >= 0.99) & core)
    return bool(covered / np.count_nonzero(core) >= 0.995)


def _square_background_box(
    rgb: np.ndarray,
    box: tuple[int, int, int, int],
    package_mask: np.ndarray | None,
) -> tuple[int, int, int, int]:
    """Grow the package box into a rectangle that keeps clear film and a square of background.

    The pad stops before another colored package.
    """
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = box
    long_side = max(x1 - x0, y1 - y0)
    pad = int(round(SQUARE_PAD_RATIO * long_side))
    nx0, ny0 = max(0, x0 - pad), max(0, y0 - pad)
    nx1, ny1 = min(width, x1 + pad), min(height, y1 + pad)
    if package_mask is None:
        return nx0, ny0, nx1, ny1
    other = (package_mask == 0) & (_chroma(rgb) > 36)
    outside = (package_mask == 0) & (foreground_mask(rgb) > 0)
    package_area = max(1, int((package_mask > 0).sum()))
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(outside.astype(np.uint8), 8)
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= 0.02 * package_area:
            other[labels == label] = True
    if not other.any():
        return nx0, ny0, nx1, ny1
    columns = np.where(other.any(axis=0))[0]
    rows = np.where(other.any(axis=1))[0]
    left = columns[columns < x0]
    right = columns[columns >= x1]
    above = rows[rows < y0]
    below = rows[rows >= y1]
    if left.size:
        nx0 = max(nx0, int(left[-1]) + 1)
    if right.size:
        nx1 = min(nx1, int(right[0]))
    if above.size:
        ny0 = max(ny0, int(above[-1]) + 1)
    if below.size:
        ny1 = min(ny1, int(below[0]))
    return nx0, ny0, nx1, ny1


def render_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
    median: np.ndarray,
    *,
    canvas: int = CANVAS,
    occupancy: float = OCCUPANCY,
    min_margin: int = MIN_MARGIN,
    package_mask: np.ndarray | None = None,
    strict_geometry: bool = False,
    allow_upscale: bool = False,
) -> tuple[Image.Image, dict]:
    del median
    rgb = np.asarray(image)
    x0, y0, x1, y1 = _square_background_box(rgb, box, package_mask)
    if package_mask is not None and _projection_bands(rgb[y0:y1, x0:x1]):
        x0, y0, x1, y1 = box
    width, height = image.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    panel_w, panel_h = x1 - x0, y1 - y0
    if panel_w < 1 or panel_h < 1:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "empty front panel")
    if package_mask is not None and not (package_mask[y0:y1, x0:x1] > 0).any():
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "package could not be separated from the table")
    if strict_geometry:
        if package_mask is None:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "strict geometry needs a complete product mask")
        ys, xs = np.where(package_mask > 0)
        if not len(xs):
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "complete product mask is empty")
        product_bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        px0, py0, px1, py1 = product_bbox
        product_long_side = max(px1 - px0, py1 - py0)
        scale = min(1.0, 2064 / product_long_side)
        max_span = int((canvas - 2 * min_margin) / scale)
        # Retained background is optional context. Clamp it around the complete product;
        # never shrink the product to make an oversized envelope fit.
        center_x, center_y = (px0 + px1) // 2, (py0 + py1) // 2
        if x1 - x0 > max_span:
            x0, x1 = center_x - max_span // 2, center_x + (max_span - max_span // 2)
        if y1 - y0 > max_span:
            y0, y1 = center_y - max_span // 2, center_y + (max_span - max_span // 2)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x0 > px0 or y0 > py0 or x1 < px1 or y1 < py1:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "retained envelope cannot fit without clipping product")
        panel_w, panel_h = x1 - x0, y1 - y0
        placed_size = (max(1, round(panel_w * scale)), max(1, round(panel_h * scale)))
        if placed_size[0] > canvas or placed_size[1] > canvas:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "retained envelope does not fit around target-sized product")
        panel = image.crop((x0, y0, x1, y1))
        placed = panel.resize(placed_size, Image.Resampling.LANCZOS)
        output = Image.new("RGB", (canvas, canvas), (255, 255, 255))
        product_w, product_h = px1 - px0, py1 - py0
        product_cx = round((px0 - x0 + product_w / 2) * scale)
        product_cy = round((py0 - y0 + product_h / 2) * scale)
        offset = (canvas // 2 - product_cx, canvas // 2 - product_cy)
        canvas_bbox = (
            offset[0] + round((px0 - x0) * scale),
            offset[1] + round((py0 - y0) * scale),
            offset[0] + round((px1 - x0) * scale),
            offset[1] + round((py1 - y0) * scale),
        )
        margins = (canvas_bbox[0], canvas_bbox[1], canvas - canvas_bbox[2], canvas - canvas_bbox[3])
        if min(margins) < min_margin:
            raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "product would sit closer than 48px to canvas edge")
        output.paste(placed, offset)
        return output, {
            "native_long_side": product_long_side,
            "scale": scale,
            "offset": offset,
            "placed_size": placed_size,
            "source_product_bbox": product_bbox,
            "source_envelope_bbox": (x0, y0, x1, y1),
            "canvas_product_bbox": canvas_bbox,
            "square_pad_ratio": SQUARE_PAD_RATIO,
        }
    long_side = max(panel_w, panel_h)
    scale = canvas * occupancy / long_side
    if scale > 1.08 and not allow_upscale:
        raise FrontRejected("CUSTOMER_RESHOOT", f"native long side {long_side}px would need upscaling")
    panel = image.crop((x0, y0, x1, y1))
    placed_size = (max(1, round(panel_w * scale)), max(1, round(panel_h * scale)))
    placed = panel.resize(placed_size, Image.Resampling.LANCZOS)
    output = Image.new("RGB", (canvas, canvas), (255, 255, 255))
    offset = ((canvas - placed_size[0]) // 2, (canvas - placed_size[1]) // 2)
    if min(offset[0], offset[1], canvas - offset[0] - placed_size[0], canvas - offset[1] - placed_size[1]) < min_margin:
        raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", "product would sit closer than 48px to the canvas edge")
    output.paste(placed, offset)
    return output, {
        "native_long_side": long_side,
        "scale": scale,
        "offset": offset,
        "placed_size": placed_size,
        "square_pad_ratio": SQUARE_PAD_RATIO,
    }


def rotate_lossless(image: Image.Image, ccw: int) -> Image.Image:
    if ccw == 0:
        return image
    if ccw == 90:
        return image.transpose(Image.Transpose.ROTATE_90)
    if ccw == 180:
        return image.transpose(Image.Transpose.ROTATE_180)
    if ccw == 270:
        return image.transpose(Image.Transpose.ROTATE_270)
    raise FrontRejected("BLOCKED_INCOMPLETE_EDGE", f"unsupported rotation {ccw}")


def content_is_square(rgb: np.ndarray) -> bool:
    """True when the kept area fills its own rectangle, including a square of background."""
    distance = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    content = distance > 18
    ys, xs = np.where(content)
    if len(xs) < 16:
        return False
    plate = content[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    return float(plate.mean()) >= SQUARE_FILL


def _table_halo_fraction(rgb: np.ndarray) -> float:
    """Share of the frame that is dull color touching the white canvas.

    A pale cap on the package stays under the gate. Cardboard left around the
    product does not.
    """
    distance = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    content = distance > 30
    if not content.any():
        return 1.0
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.int16)
    chroma = np.sqrt((lab[:, :, 1] - 128) ** 2 + (lab[:, :, 2] - 128) ** 2)
    # A white label sits on the package. Cardboard sits away from the package color.
    distance_to_color = cv2.distanceTransform((chroma < 22).astype(np.uint8), cv2.DIST_L2, 3)
    dull = content & (chroma < 22) & (distance_to_color > 8)
    white = (~content).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    touching = dull & (cv2.dilate(white, kernel) > 0)
    count, labels, _stats, _centroids = cv2.connectedComponentsWithStats(dull.astype(np.uint8), 8)
    halo = np.zeros(content.shape, bool)
    for label in range(1, count):
        if touching[labels == label].any():
            halo[labels == label] = True
    return float(halo.sum()) / float(content.sum())


def leftover_barcode_panel(rgb: np.ndarray, hits: list[BarcodeHit]) -> bool:
    """True when a barcode sits outside the main product.

    A barcode inside that product is printed on the chosen package and is allowed.
    """
    if not hits:
        return False
    components = _components(foreground_mask(rgb))
    if not components:
        return False
    x0, y0, x1, y1 = max(components, key=lambda item: item["area"])["box"]
    pad = 8
    for hit in hits:
        if x0 - pad <= hit.cx < x1 + pad and y0 - pad <= hit.cy < y1 + pad:
            continue
        return True
    return False


def output_is_clean(image: Image.Image) -> str | None:
    """QA gate. None means the canvas may be accepted. Any reason sends it back."""
    if image.size != (CANVAS, CANVAS):
        return "canvas is not 2400 square"
    rgb = np.asarray(image)
    if rgb.ndim != 3:
        return "canvas is not RGB"
    corners = np.stack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
    if np.abs(corners.astype(np.int16) - 255).sum() > 40:
        return "corners are not white"
    small, _scale = preview(image, 900)
    preview_rgb = np.asarray(small)
    if not content_is_square(preview_rgb) and _table_halo_fraction(preview_rgb) > 0.05:
        return "table or cardboard remains around the product"
    if leftover_barcode_panel(preview_rgb, _scan(small, 0, 0)):
        return "separate barcode panel remains"
    if _projection_bands(preview_rgb):
        return "second product remains"
    if _cut_to_a_strip(preview_rgb) or _only_an_edge_sliver(preview_rgb):
        return "product is cut down to a strip"
    mask = foreground_mask(preview_rgb)
    comps = _components(mask)
    if len(comps) >= 2:
        largest = max(item["area"] for item in comps)
        if any(item["area"] > 0.08 * largest for item in comps if item["area"] != largest):
            return "second product remains"
    return None


def _cut_to_a_strip(rgb: np.ndarray) -> bool:
    """A bottle chopped down to its cap, or a bag reduced to one edge."""
    distance = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    content = distance > 18
    ys, xs = np.where(content)
    if len(xs) < 16:
        return True
    height = int(ys.max() - ys.min()) + 1
    width = int(xs.max() - xs.min()) + 1
    return min(height, width) / max(height, width) < 0.22


def _only_an_edge_sliver(rgb: np.ndarray) -> bool:
    """Cardboard or an open carton with only a scrap of the package in frame."""
    chroma = _chroma(rgb)
    light = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[:, :, 0]
    distance = np.abs(rgb.astype(np.int16) - 255).sum(axis=2)
    content = distance > 18
    if int(content.sum()) < 16:
        return False
    product = content & ((chroma > 32) | (light < 75))
    if int(product.sum()) < 10:
        return True
    if float(product.sum()) / float(content.sum()) >= 0.2:
        return False
    ys, xs = np.where(product)
    cys, cxs = np.where(content)
    product_short = min(int(ys.max() - ys.min()) + 1, int(xs.max() - xs.min()) + 1)
    content_long = max(int(cys.max() - cys.min()) + 1, int(cxs.max() - cxs.min()) + 1)
    return product_short < 0.28 * content_long
