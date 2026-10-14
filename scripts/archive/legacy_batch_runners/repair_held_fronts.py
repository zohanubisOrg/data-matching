"""Repair the 145 fronts left in tagged/front.

A cut is allowed only where the table shows through between packages.
A label line, a lid line, or a fold is not a seam. Three packages yield
one face. A result is written only when it is one complete package.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fix_tagged_backs import (  # noqa: E402
    _match_panel,
    _panels_at,
    label_ink,
    package_count,
    product_text_score,
    stand_up,
)
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality  # noqa: E402
from product_mapper.vision.barcode_side_splitter import packshot_front, place_front_on_white  # noqa: E402
from product_mapper.vision.yolo_detector import YOLOPackagingDetector  # noqa: E402

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front"
FRONT_V1 = ROOT / "output/catalog_pairs/tagged/front-v1"
YOLO_WEIGHTS = ROOT / "output/yolo_training/packaging_detector/weights/best.pt"
_YOLO = None
ORIG_DIR = ROOT / "output/catalog_pairs/originals"
PREVIEW = ROOT / "output/catalog_pairs/_held_preview"
BACKUP = ROOT / "output/catalog_pairs/_front_before_held_fix"
MANIFEST = ROOT / "output/catalog_pairs/manifest.json"
PLAN = ROOT / "output/catalog_pairs/_held_plan.json"


def _border_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels that are not the table color around the frame."""
    arr = rgb.astype(np.int16)
    height, width = arr.shape[:2]
    edge = max(4, min(height, width) // 36)
    border = np.concatenate(
        [
            arr[:edge].reshape(-1, 3),
            arr[-edge:].reshape(-1, 3),
            arr[:, :edge].reshape(-1, 3),
            arr[:, -edge:].reshape(-1, 3),
        ]
    )
    color = np.median(border, axis=0)
    distance = np.abs(arr - color).sum(axis=2)
    mask = (distance > 50).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask


def _probe(image: Image.Image, limit: int = 720) -> tuple[np.ndarray, np.ndarray]:
    preview = image.copy()
    preview.thumbnail((limit, limit))
    rgb = np.asarray(preview.convert("RGB"))
    return rgb, _border_mask(rgb)


def _package_runs(mask: np.ndarray, axis: str) -> list[tuple[float, float]]:
    """Content blocks separated by table, as fractions of this axis."""
    profile = mask.mean(axis=0 if axis == "x" else 1).astype(np.float32)
    length = int(profile.shape[0])
    if length < 20:
        return []
    kernel = max(5, length // 48)
    smooth = np.convolve(profile, np.ones(kernel, dtype=np.float32) / kernel, mode="same")
    active = smooth > 0.16
    spans: list[list[int]] = []
    start: int | None = None
    for index, on in enumerate([*active.tolist(), False]):
        if on and start is None:
            start = index
        elif not on and start is not None:
            spans.append([start, index])
            start = None
    merged: list[list[int]] = []
    for span in spans:
        if not merged:
            merged.append(span)
            continue
        gap = smooth[merged[-1][1] : span[0]]
        gap_frac = (span[0] - merged[-1][1]) / length
        real_gap = gap.size > 0 and float(np.percentile(gap, 15)) < 0.07 and gap_frac >= 0.012
        if real_gap:
            merged.append(span)
        else:
            merged[-1][1] = span[1]
    runs: list[tuple[float, float]] = []
    for left, right in merged:
        size = (right - left) / length
        if size >= 0.18:
            runs.append((left / length, right / length))
    return runs


def _usable(runs: list[tuple[float, float]]) -> bool:
    sizes = [end - start for start, end in runs]
    if len(runs) == 2:
        return all(0.18 <= size <= 0.78 for size in sizes)
    if len(runs) == 3:
        return all(0.18 <= size <= 0.48 for size in sizes)
    return False


def layout_cuts(image: Image.Image) -> tuple[str, list[float]] | None:
    """Seams that are empty table. Side-by-side seams win over stacked ones."""
    _rgb, mask = _probe(image)
    columns = _package_runs(mask, "x")
    rows = _package_runs(mask, "y")
    chosen: tuple[str, list[tuple[float, float]]] | None = None
    if _usable(columns):
        chosen = ("x", columns)
    elif _usable(rows):
        chosen = ("y", rows)
    if chosen is None:
        return None
    axis, runs = chosen
    # A horizontal cut through one standing bottle is a lid line, not two packages.
    if axis == "y" and len(runs) == 2:
        heights = [end - start for start, end in runs]
        if min(heights) < 0.34:
            return None
    cuts = [(runs[index][1] + runs[index + 1][0]) / 2 for index in range(len(runs) - 1)]
    return axis, cuts


def _chroma(image: Image.Image) -> float:
    probe = image.copy()
    probe.thumbnail((240, 240))
    arr = np.asarray(probe.convert("RGB")).astype(np.int16)
    return float((arr.max(axis=2) - arr.min(axis=2)).mean())


def _nutrition(panel: Image.Image, rival: Image.Image) -> bool:
    """A dense low-color table beside a colored brand face."""
    return label_ink(panel) > label_ink(rival) * 1.28 and _chroma(panel) + 6 < _chroma(rival)


def _content_hw(image: Image.Image) -> float:
    _rgb, mask = _probe(image, 480)
    ys, xs = np.where(mask)
    if len(xs) < 20:
        return 1.0
    height = float(ys.max() - ys.min() + 1)
    width = float(xs.max() - xs.min() + 1)
    return height / max(width, 1.0)


def _touching_cut(image: Image.Image) -> float | None:
    """A straight vertical seam where two different packages touch."""
    rgb, mask = _probe(image, 640)
    ys, xs = np.where(mask)
    if len(xs) < 80:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    box_w = x1 - x0 + 1
    box_h = y1 - y0 + 1
    if box_w < 90 or box_h < 40 or box_w < box_h * 1.15:
        return None
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    region = edges[y0 : y1 + 1, x0 : x1 + 1]
    column = region.mean(axis=0)
    left = int(box_w * 0.36)
    right = int(box_w * 0.64)
    if right <= left + 4:
        return None
    peak = left + int(column[left:right].argmax())
    if column[peak] < float(np.median(column)) * 1.8:
        return None
    if float((region[:, peak] > 0).mean()) < 0.55:
        return None
    left_rgb = rgb[y0 : y1 + 1, x0 : x0 + peak]
    right_rgb = rgb[y0 : y1 + 1, x0 + peak : x1 + 1]
    if left_rgb.size == 0 or right_rgb.size == 0:
        return None

    def chroma(part: np.ndarray) -> float:
        values = part.astype(np.int16)
        return float((values.max(axis=2) - values.min(axis=2)).mean())

    def ink(part: np.ndarray) -> float:
        mono = cv2.cvtColor(part, cv2.COLOR_RGB2GRAY)
        return float(cv2.Canny(mono, 40, 120).mean())

    chroma_ratio = max(chroma(left_rgb), chroma(right_rgb)) / max(min(chroma(left_rgb), chroma(right_rgb)), 1.0)
    ink_ratio = max(ink(left_rgb), ink(right_rgb)) / max(min(ink(left_rgb), ink(right_rgb)), 1.0)
    if chroma_ratio < 1.35 and ink_ratio < 1.45:
        return None
    return (x0 + peak) / rgb.shape[1]


def trim_content(image: Image.Image) -> Image.Image:
    """Drop the table around one package. Keep the frame if only the print remains."""
    rgb, mask = _probe(image, 900)
    ys, xs = np.where(mask)
    if len(xs) < 40:
        return image
    height, width = mask.shape
    box_area = float((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
    if box_area < 0.20 * width * height:
        return image
    scale = image.size[0] / rgb.shape[1]
    pad_x = int((xs.max() - xs.min()) * scale * 0.03)
    pad_y = int((ys.max() - ys.min()) * scale * 0.03)
    left = max(0, int(xs.min() * scale) - pad_x)
    top = max(0, int(ys.min() * scale) - pad_y)
    right = min(image.size[0], int((xs.max() + 1) * scale) + pad_x)
    bottom = min(image.size[1], int((ys.max() + 1) * scale) + pad_y)
    if right - left < 80 or bottom - top < 80:
        return image
    return image.crop((left, top, right, bottom))


def _pick_panel(panels: list[Image.Image], code: str) -> Image.Image | None:
    if len(panels) not in (2, 3):
        return None
    matched = [index for index, panel in enumerate(panels) if _match_panel(panel, code)]
    if len(panels) == 3:
        if matched and 1 not in matched:
            face = panels[1]
            rival = max((panels[index] for index in (0, 2) if index not in matched), key=_chroma, default=panels[0])
            if _nutrition(face, rival):
                return rival
            return face
        if matched == [1]:
            return max((panels[0], panels[2]), key=_chroma)
        if not matched:
            face = panels[1]
            rival = max((panels[0], panels[2]), key=_chroma)
            if _nutrition(face, rival):
                return rival
            return face
        return None
    if len(matched) == 1:
        other = panels[1 - matched[0]]
        branded = panels[matched[0]]
        if _nutrition(other, branded):
            return branded
        return other
    if len(matched) == 2:
        return None
    first, second = panels
    chroma_ratio = max(_chroma(first), _chroma(second)) / max(min(_chroma(first), _chroma(second)), 1.0)
    ink_ratio = max(label_ink(first), label_ink(second)) / max(min(label_ink(first), label_ink(second)), 1.0)
    if chroma_ratio < 1.2 and ink_ratio < 1.25:
        return None
    if chroma_ratio >= ink_ratio:
        return first if _chroma(first) >= _chroma(second) else second
    return first if label_ink(first) <= label_ink(second) else second


def _rotate_if_lying(face: Image.Image) -> tuple[Image.Image, int]:
    score, fraction = product_text_score(face)
    landscape = face.size[0] > face.size[1] * 1.25
    if not landscape or score < 1.45 or fraction < 0.45:
        return face, 0
    turned, ccw = stand_up(face)
    if not ccw:
        return face, 0
    turned_score, _fraction = product_text_score(turned)
    if turned_score > score - 0.20:
        return face, 0
    return turned, ccw


def _crop_box(image: Image.Image, box: list[int]) -> Image.Image:
    width, height = image.size
    top = max(0, int(box[0] * height / 1000))
    left = max(0, int(box[1] * width / 1000))
    bottom = min(height, int(box[2] * height / 1000))
    right = min(width, int(box[3] * width / 1000))
    if right - left < 80 or bottom - top < 80:
        return image
    return image.crop((left, top, right, bottom))


def _yolo_face(image: Image.Image) -> tuple[Image.Image | None, str]:
    """The trained front class only. A COCO weight file does not know the sales face."""
    global _YOLO
    if not YOLO_WEIGHTS.is_file():
        return None, "no-yolo-weights"
    if _YOLO is None:
        _YOLO = YOLOPackagingDetector(YOLO_WEIGHTS)
    if not _YOLO.is_custom_trained:
        return None, "yolo-not-custom"
    found = _YOLO.detect(image)
    box = found.front_box_2d
    if box is None or found.confidence_front < 0.65:
        return None, "yolo-low-conf"
    top, left, bottom, right = box
    box_w = right - left
    box_h = bottom - top
    if box_w < 120 or box_h < 120:
        return None, "yolo-sliver"
    if box_w * box_h < 80_000:
        return None, "yolo-logo"
    if box_w > 920 and box_h > 920:
        return None, "yolo-full-frame"
    face = _crop_box(image, box)
    if package_count(face) > 1:
        return None, "yolo-multi"
    return trim_content(face), f"yolo {found.confidence_front:.2f}"


def sales_face(image: Image.Image, code: str) -> tuple[Image.Image | None, str]:
    """One sales face from a warehouse photo, or nothing when the seam is unsafe."""
    yolo_face, yolo_reason = _yolo_face(image)
    if yolo_face is not None:
        return yolo_face, yolo_reason
    found = layout_cuts(image)
    reason = "split"
    if found is None:
        fraction = _touching_cut(image)
        if fraction is None:
            if package_count(image) > 1:
                return None, "still-multi"
            return trim_content(image), "whole"
        found = ("x", [fraction])
        reason = "touch"
    axis, cuts = found
    panels = _panels_at(image, axis, cuts)
    if len(panels) != (2 if len(cuts) == 1 else 3):
        return None, "panel-count"
    face = _pick_panel(panels, code)
    if face is None:
        return None, "no-choice"
    if package_count(face) > 1:
        return None, "face-multi"
    return trim_content(face), reason


def deliver(face: Image.Image) -> Image.Image:
    """White packshot. If background removal keeps only the print, keep the whole package."""
    trimmed = trim_content(face)
    before_hw = _content_hw(trimmed)
    shot = packshot_front(trimmed)
    after_hw = _content_hw(shot)
    if min(before_hw, after_hw) <= 0:
        return place_front_on_white(trimmed)
    ratio = max(before_hw, after_hw) / min(before_hw, after_hw)
    if ratio > 1.6:
        return place_front_on_white(trimmed)
    return shot


def _measure(image: Image.Image) -> dict[str, float | int]:
    probe = image.copy()
    probe.thumbnail((480, 480))
    rgb = np.asarray(probe.convert("RGB"))
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    ink = ~((rgb.min(axis=2) > 236) & (spread < 18))
    height, width = ink.shape
    ys, xs = np.where(ink)
    if len(xs) == 0:
        return {"coverage": 0.0, "w": 0.0, "h": 0.0, "text": 1.0, "blobs": 0}
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    frame = width * height
    blobs = sum(int(stats[index, cv2.CC_STAT_AREA]) > frame * 0.08 for index in range(1, count))
    score, _fraction = product_text_score(image)
    return {
        "coverage": float(ink.mean()),
        "w": float(xs.max() - xs.min() + 1) / width,
        "h": float(ys.max() - ys.min() + 1) / height,
        "text": score,
        "blobs": blobs,
    }


def _partial_of_tall(current: Image.Image, original: Image.Image | None) -> bool:
    if original is None:
        return False
    return _content_hw(original) > 1.15 and _content_hw(current) < 0.90


def _back_label(image: Image.Image, code: str) -> bool:
    if not _match_panel(image, code):
        return False
    return _chroma(image) < 18


def current_is_complete(image: Image.Image, code: str, original: Image.Image | None) -> bool:
    """A held file that is already one upright sales face."""
    stats = _measure(image)
    tall_bottle = float(stats["h"]) >= 0.72 and float(stats["w"]) >= 0.15 and float(stats["text"]) < 1.55
    wide_enough = float(stats["w"]) >= 0.22 or tall_bottle
    flat_pack = float(stats["h"]) >= 0.42 and float(stats["w"]) >= 0.50 and float(stats["text"]) < 1.35
    tall_enough = float(stats["h"]) >= 0.55 or flat_pack or tall_bottle
    if int(stats["blobs"]) != 1 or not wide_enough or not tall_enough:
        return False
    if float(stats["coverage"]) < 0.12 or float(stats["text"]) >= 1.70:
        return False
    if _touching_cut(image) is not None or _partial_of_tall(image, original):
        return False
    if _back_label(image, code):
        return False
    return True


def _original(code: str) -> Path | None:
    folder = ORIG_DIR / code
    if not folder.exists():
        return None
    files = [path for path in folder.iterdir() if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_size)


def _accepted(image: Image.Image) -> bool:
    stats = _measure(image)
    if int(stats["blobs"]) != 1 or float(stats["coverage"]) < 0.10:
        return False
    if float(stats["h"]) < 0.38:
        return False
    if float(stats["w"]) < 0.16 and float(stats["h"]) < 0.70:
        return False
    if float(stats["text"]) >= 1.85:
        return False
    if float(stats["w"]) < 0.22 and float(stats["text"]) >= 1.55:
        return False
    return package_count(image) <= 1


def decide(path: Path) -> tuple[str, Image.Image | None, str]:
    code = path.stem.replace("_front", "")
    current = open_image_safely(path)
    source = _original(code)
    original = open_image_safely(source) if source is not None else None
    if current_is_complete(current, code, original):
        return "move", current, "already-one"
    if original is None:
        return "hold", None, "no-original"
    face, reason = sales_face(original, code)
    if face is None:
        return "hold", None, reason
    turned, ccw = _rotate_if_lying(face)
    if ccw:
        face = turned
        reason = f"{reason}+rot{ccw}"
    if package_count(face) > 1:
        return "hold", None, "face-multi"
    if _content_hw(original) > 1.3 and _content_hw(face) < 0.85:
        return "hold", None, "lost-body"
    return "repair", face, reason


def _note_manifest(updates: dict[str, tuple[str, int, int]]) -> None:
    if not updates or not MANIFEST.exists():
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for code, (action, width, height) in updates.items():
        entry = manifest.get(code)
        if not isinstance(entry, dict):
            continue
        entry["front_path"] = str(FRONT_V1 / f"{code}_front.jpg")
        entry["front_size"] = f"{width}x{height}"
        entry["front_ok"] = True
        if action == "repair":
            entry["note"] = "Kept one upright sales face from the held photo."
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _thumb(image: Image.Image, code: str, action: str) -> None:
    folder = PREVIEW / action
    folder.mkdir(parents=True, exist_ok=True)
    copy = image.copy()
    copy.thumbnail((420, 420))
    canvas = Image.new("RGB", (420, 450), (255, 255, 255))
    canvas.paste(copy, ((420 - copy.size[0]) // 2, (420 - copy.size[1]) // 2))
    draw_band = Image.new("RGB", (420, 30), (20, 20, 20))
    canvas.paste(draw_band, (0, 420))
    canvas.save(folder / f"{code}.jpg", quality=80)


def main() -> None:
    apply = "--apply" in sys.argv
    FRONT_V1.mkdir(parents=True, exist_ok=True)
    files = sorted(FRONT_DIR.glob("*_front.jpg"))
    plan: dict[str, str] = {}
    updates: dict[str, tuple[str, int, int]] = {}
    counts = {"move": 0, "repair": 0, "hold": 0}
    for index, path in enumerate(files, start=1):
        code = path.stem.replace("_front", "")
        if (FRONT_V1 / path.name).exists():
            print(code, "hold", "already-in-v1", flush=True)
            plan[code] = "hold already-in-v1"
            counts["hold"] += 1
            continue
        action, image, reason = decide(path)
        counts[action] += 1
        plan[code] = f"{action} {reason}"
        print(f"{index}/{len(files)}", code, action, reason, flush=True)
        if image is not None and not apply:
            _thumb(image, code, action)
        if not apply or action == "hold" or image is None:
            continue
        final = image if action == "move" else deliver(image)
        if action == "repair" and not _accepted(final):
            print(code, "hold", "rejected-after-packshot", flush=True)
            plan[code] = "hold rejected-after-packshot"
            counts["repair"] -= 1
            counts["hold"] += 1
            continue
        dest = FRONT_V1 / path.name
        BACKUP.mkdir(parents=True, exist_ok=True)
        if not (BACKUP / path.name).exists():
            shutil.copy2(path, BACKUP / path.name)
        if action == "move":
            shutil.copy2(path, dest)
        else:
            save_image_high_quality(final, dest, quality=95, save_webp=False)
        path.unlink()
        updates[code] = (action, *dest_size(dest))
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    _note_manifest(updates)
    print("counts", counts, "written", len(updates), flush=True)


def dest_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


if __name__ == "__main__":
    main()
