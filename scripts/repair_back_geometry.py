"""Tighten failed backs: stand a sideways package up and crop off the table."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import INDEX_PATH  # noqa: E402
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality  # noqa: E402
from product_mapper.vision.barcode_side_splitter import (  # noqa: E402
    _edge_profile,
    _local_gaps,
    _prepare,
    enhance_back,
    read_retail_barcodes,
    rotate_upright,
)

OUT = ROOT / "output/catalog_pairs/_back_fix_preview"
CODES = [
    "8850025001023",
    "3447573606029",
    "084909006745",
    "044738102353",
    "0690225301244",
    "4045198940130",
    "4901740115237",
    "5011308306317",
    "078895147087",
    "7629493190482",
    "8716789014436",
    "8801043157766",
    "4901313938669",
    "8851028001690",
]


def text_is_sideways(image: Image.Image) -> float:
    width, height = image.size
    crop = image.crop((int(width * 0.12), int(height * 0.12), int(width * 0.88), int(height * 0.88)))
    crop.thumbnail((640, 640))
    gray = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2GRAY)
    vertical = float(np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)).mean())
    horizontal = float(np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)).mean())
    return vertical / max(horizontal, 1.0)


def foreground_box(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    work = image.copy()
    work.thumbnail((720, 720))
    arr = np.asarray(work)
    border = np.concatenate(
        [arr[:8].reshape(-1, 3), arr[-8:].reshape(-1, 3), arr[:, :8].reshape(-1, 3), arr[:, -8:].reshape(-1, 3)]
    )
    background = np.median(border, axis=0)
    distance = np.abs(arr.astype(np.int16) - background).sum(axis=2)
    rows = np.where((distance > 40).any(axis=1))[0]
    cols = np.where((distance > 40).any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return 0, 0, width, height
    return (
        int(cols[0] * width / arr.shape[1]),
        int(rows[0] * height / arr.shape[0]),
        int((cols[-1] + 1) * width / arr.shape[1]),
        int((rows[-1] + 1) * height / arr.shape[0]),
    )


def keep_barcode_side(image: Image.Image) -> Image.Image:
    preview, _scale = _prepare(image, 900)
    arr = np.asarray(preview)

    def central(axis: str) -> list[tuple[float, float, float]]:
        return [item for item in _local_gaps(_edge_profile(arr, axis), 0.45, 0.18) if 0.28 <= item[0] <= 0.72]

    column_gaps = central("x")
    row_gaps = central("y")
    if len(column_gaps) >= 2 or len(row_gaps) >= 2 or (not column_gaps and not row_gaps):
        return image
    fraction = (column_gaps or row_gaps)[0][0]
    width, height = image.size
    if column_gaps:
        cut = int(width * fraction)
        sides = [image.crop((0, 0, cut, height)), image.crop((cut, 0, width, height))]
    else:
        cut = int(height * fraction)
        sides = [image.crop((0, 0, width, cut)), image.crop((0, cut, width, height))]
    areas = [side.size[0] * side.size[1] for side in sides]
    if min(areas) < max(areas) * 0.35:
        return image
    for side in sides:
        probe = side.copy()
        probe.thumbnail((1200, 1200))
        if read_retail_barcodes(probe):
            return side
    return image


def stand_up(image: Image.Image) -> tuple[Image.Image, int]:
    best_image = image
    best_ccw = 0
    best_score = text_is_sideways(image)
    if best_score < 1.08:
        return image, 0
    for ccw in (90, 270):
        turned = rotate_upright(image, ccw)
        score = text_is_sideways(turned)
        if score + 0.08 < best_score:
            best_image = turned
            best_ccw = ccw
            best_score = score
    return best_image, best_ccw


def repair_image(image: Image.Image) -> tuple[Image.Image, int]:
    upright, ccw = stand_up(image)
    cropped = keep_barcode_side(upright.crop(foreground_box(upright)))
    x0, y0, x1, y1 = foreground_box(cropped)
    pad_x = int((x1 - x0) * 0.02)
    pad_y = int((y1 - y0) * 0.02)
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(cropped.size[0], x1 + pad_x)
    y1 = min(cropped.size[1], y1 + pad_y)
    return enhance_back(cropped.crop((x0, y0, x1, y1))), ccw


def foreground_boxes(image: Image.Image) -> list[tuple[int, int, int, int]]:
    width, height = image.size
    work = image.copy()
    work.thumbnail((800, 800))
    arr = np.asarray(work)
    scale_x = width / arr.shape[1]
    scale_y = height / arr.shape[0]
    border = np.concatenate(
        [
            arr[:10, :, :].reshape(-1, 3),
            arr[-10:, :, :].reshape(-1, 3),
            arr[:, :10, :].reshape(-1, 3),
            arr[:, -10:, :].reshape(-1, 3),
        ]
    )
    background = np.median(border, axis=0)
    distance = np.abs(arr.astype(np.int16) - background).sum(axis=2)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((3, 3), np.uint8))
    mask = np.where((distance > 42) | (edges > 0), 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    limit = arr.shape[0] * arr.shape[1] * 0.05
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if box_w * box_h < limit:
            continue
        boxes.append(
            (
                int(x * scale_x),
                int(y * scale_y),
                int((x + box_w) * scale_x),
                int((y + box_h) * scale_y),
            )
        )
    boxes.sort(key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True)
    return boxes


def source_for(manifest: dict, index: list[dict], barcode: str) -> Path | None:
    source = str((manifest.get(barcode) or {}).get("source") or "")
    if source and not source.startswith("http") and Path(source).is_file():
        return Path(source)
    for record in index:
        if record.get("excel_barcode") == barcode and record.get("center"):
            return Path(str(record["path"]))
    return None


def main() -> None:
    manifest = json.loads((ROOT / "output/catalog_pairs/manifest.json").read_text(encoding="utf-8"))
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for code in CODES:
        path = source_for(manifest, index, code)
        if path is None:
            print("no source", code, flush=True)
            continue
        repaired, ccw = repair_image(open_image_safely(path))
        thumb = repaired.copy()
        thumb.thumbnail((720, 720))
        thumb.save(OUT / f"{code}.jpg", quality=85)
        print(f"{code} rot {ccw} {repaired.size[0]}x{repaired.size[1]} {path.name}", flush=True)


if __name__ == "__main__":
    main()
