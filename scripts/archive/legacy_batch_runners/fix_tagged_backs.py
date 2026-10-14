"""Keep one upright back from a tagged photo that still shows several packages.

A change is saved only when one panel carries this product's barcode, or when a
third panel is the nutrition label whose barcode the photo cut off. Single
products, including ones with a vertical barcode, are left as they are.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from product_mapper.vision.barcode_side_splitter import (  # noqa: E402
    _edge_profile,
    _local_gaps,
    _prepare,
    read_retail_barcodes,
    rotate_upright,
)

BACK_DIR = ROOT / "output/catalog_pairs/tagged/back"
PREVIEW = ROOT / "output/catalog_pairs/_back_audit_preview"
MANIFEST = ROOT / "output/catalog_pairs/manifest.json"
ACCEPTED_PATH = ROOT / "output/catalog_pairs/back_accepted.json"

PROTECTED = {
    "4901313938669",
    "8851028001690",
    "5027738014234",
    "8720301109067",
    "030891051195",
    "8801043951685",
    "4901740115237",
    "8850025001023",
    "044738102353",
    "0690225301244",
    "4045198940130",
    "5011308306317",
    "078895147087",
    "7629493190482",
    "8716789014436",
    "084909006745",
    "8801043157766",
}


def same_code(found: str, expected: str) -> bool:
    left = found.lstrip("0")
    right = expected.lstrip("0")
    if not left or not right:
        return False
    return left == right or left.endswith(right) or right.endswith(left)


def label_ink(image: Image.Image) -> float:
    probe = image.copy()
    probe.thumbnail((360, 360))
    gray = cv2.cvtColor(np.asarray(probe.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    horizontal = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    return float(edges.mean() + horizontal.mean() / 8.0)


def big_letters(image: Image.Image) -> float:
    probe = image.copy()
    probe.thumbnail((400, 400))
    gray = cv2.cvtColor(np.asarray(probe.convert("RGB")), cv2.COLOR_RGB2GRAY)
    dark = (gray < 90).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(dark, 8)
    frame = gray.shape[0] * gray.shape[1]
    area = 0
    for index in range(1, count):
        component = int(stats[index, cv2.CC_STAT_AREA])
        box_w = int(stats[index, cv2.CC_STAT_WIDTH])
        box_h = int(stats[index, cv2.CC_STAT_HEIGHT])
        if component < frame * 0.002 or component > frame * 0.20:
            continue
        if box_h > gray.shape[0] * 0.06 or box_w > gray.shape[1] * 0.10:
            area += component
    return area / frame


def product_text_score(image: Image.Image) -> tuple[float, float]:
    probe = image.copy()
    probe.thumbnail((480, 480))
    rgb = np.asarray(probe.convert("RGB"))
    arr = rgb.astype(np.int16)
    border = np.concatenate(
        [arr[:8].reshape(-1, 3), arr[-8:].reshape(-1, 3), arr[:, :8].reshape(-1, 3), arr[:, -8:].reshape(-1, 3)]
    )
    color = np.median(border, axis=0)
    distance = np.abs(arr - color).sum(axis=2)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    vertical = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    horizontal = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    energy = vertical + horizontal
    product = distance > 55
    if int(product.sum()) < 500:
        product = np.ones(gray.shape, dtype=bool)
    strong = energy > np.percentile(energy[product], 55)
    use = product & strong
    if int(use.sum()) < 300:
        use = product
    score = float(vertical[use].mean()) / max(float(horizontal[use].mean()), 1.0)
    sideways = 0
    counted = 0
    for row in np.array_split(np.arange(gray.shape[0]), 4):
        for col in np.array_split(np.arange(gray.shape[1]), 4):
            chosen = np.zeros(gray.shape, dtype=bool)
            chosen[row[0] : row[-1] + 1, col[0] : col[-1] + 1] = True
            chosen &= use
            if int(chosen.sum()) < 40:
                continue
            counted += 1
            ratio = float(vertical[chosen].mean()) / max(float(horizontal[chosen].mean()), 1.0)
            if ratio >= 1.35:
                sideways += 1
    return score, (sideways / counted if counted else 0.0)


def latin_upright(image: Image.Image) -> float:
    """Positive when Latin lines are heavier on top, as upright text is."""
    probe = image.copy()
    probe.thumbnail((640, 640))
    gray = cv2.cvtColor(np.asarray(probe.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 140)
    row = edges.mean(axis=1)
    if float(row.max()) <= 0:
        return 0.0
    active = row > float(row.max()) * 0.35
    score = 0.0
    weight = 0.0
    start: int | None = None
    for index, on in enumerate([*active.tolist(), False]):
        if on and start is None:
            start = index
        if not on and start is not None:
            if index - start >= 4:
                band = edges[start:index]
                half = max(1, band.shape[0] // 2)
                score += float(band[:half].mean()) - float(band[half:].mean())
                weight += 1.0
            start = None
    return score / weight if weight else 0.0


def _codes(image: Image.Image) -> set[str]:
    width, height = image.size
    regions = [
        image,
        image.crop((0, int(height * 0.42), width, height)),
        image.crop((int(width * 0.35), int(height * 0.40), width, height)),
    ]
    found: set[str] = set()
    for region in regions:
        probe = region.copy()
        probe.thumbnail((1600, 1600))
        found.update(hit.text for hit in read_retail_barcodes(probe))
        if found:
            return found
    return found


def _matches(image: Image.Image, expected: str) -> bool:
    return any(same_code(code, expected) for code in _codes(image))


def _is_band(original: Image.Image, panel: Image.Image) -> bool:
    panel_w, panel_h = panel.size
    width, height = original.size
    short_side = panel_h < height * 0.42 and panel_h < panel_w * 0.70
    thin_side = panel_w < width * 0.22
    return short_side or thin_side


def _all_cuts(image: Image.Image) -> list[tuple[str, list[float]]]:
    preview, _scale = _prepare(image, 800)
    arr = np.asarray(preview.convert("RGB"))
    found: list[tuple[float, str, list[float]]] = []
    for axis in ("x", "y"):
        gaps = [gap for gap in _local_gaps(_edge_profile(arr, axis), 0.32, 0.14) if 0.30 <= gap[0] <= 0.70]
        if len(gaps) >= 2:
            left, right = gaps[0][0], gaps[1][0]
            sizes = (left, right - left, 1.0 - right)
            if all(0.26 <= size <= 0.42 for size in sizes):
                found.append((min(gap[1] for gap in gaps[:2]) + 0.25, axis, [left, right]))
        usable = [gap for gap in gaps if gap[1] >= 0.46 and gap[2] >= 0.48 and 0.36 <= gap[0] <= 0.64]
        if usable:
            fraction, depth, balance = max(usable, key=lambda gap: (gap[2], -abs(gap[0] - 0.5)))
            found.append((balance, axis, [fraction]))
    found.sort(key=lambda item: (len(item[2]) == 1, -item[0]))
    return [(axis, cuts) for _score, axis, cuts in found]


def _panels_at(image: Image.Image, axis: str, cuts: list[float]) -> list[Image.Image]:
    width, height = image.size
    span = width if axis == "x" else height
    edges = [0, *[int(span * cut) for cut in cuts], span]
    panels: list[Image.Image] = []
    for start, end in zip(edges, edges[1:]):
        if end - start < span * 0.18:
            continue
        if axis == "x":
            panels.append(image.crop((start, 0, end, height)))
        else:
            panels.append(image.crop((0, start, width, end)))
    return panels


def _match_panel(panel: Image.Image, expected: str) -> bool:
    if _matches(panel, expected):
        return True
    width, height = panel.size
    inset = panel.crop(
        (int(width * 0.04), int(height * 0.08), int(width * 0.96), int(height * 0.92))
    )
    return _matches(inset, expected)


def package_count(image: Image.Image) -> int:
    """How many separate packages sit on the table, ignoring the border color."""
    probe = image.copy()
    probe.thumbnail((280, 280))
    arr = np.asarray(probe.convert("RGB")).astype(np.int16)
    border = np.concatenate(
        [arr[:6].reshape(-1, 3), arr[-6:].reshape(-1, 3), arr[:, :6].reshape(-1, 3), arr[:, -6:].reshape(-1, 3)]
    )
    distance = np.abs(arr - np.median(border, axis=0)).sum(axis=2)
    mask = (distance > 48).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    frame = arr.shape[0] * arr.shape[1]
    return sum(int(stats[index, cv2.CC_STAT_AREA]) > frame * 0.07 for index in range(1, count))


def _redness(image: Image.Image) -> float:
    probe = image.copy()
    probe.thumbnail((180, 180))
    arr = np.asarray(probe.convert("RGB"))
    red = (arr[:, :, 0] > 140) & (arr[:, :, 0] > arr[:, :, 1] + 25)
    return float(red.mean())


def _barcode_sits_beside(panel: Image.Image) -> bool:
    """A horizontal cut kept two bottles when the code sits at the far left or right."""
    width, height = panel.size
    regions = (
        (panel, 0),
        (panel.crop((0, int(height * 0.42), width, height)), 0),
        (panel.crop((int(width * 0.35), int(height * 0.40), width, height)), int(width * 0.35)),
    )
    for region, offset_x in regions:
        probe = region.copy()
        probe.thumbnail((1400, 1400))
        hits = read_retail_barcodes(probe)
        if not hits:
            continue
        center = sum(hit.center_x for hit in hits) / len(hits)
        center = center * region.size[0] / probe.size[0] + offset_x
        return center / width < 0.38 or center / width > 0.60
    return False


def _barcode_choice(panels: list[Image.Image], expected: str) -> Image.Image | None:
    matched = [index for index, panel in enumerate(panels) if _match_panel(panel, expected)]
    if len(matched) != 1:
        return None
    chosen = matched[0]
    if len(panels) < 3:
        return panels[chosen]
    letters = [big_letters(panel) for panel in panels]
    inks = [label_ink(panel) for panel in panels]
    quieter = [
        index
        for index in range(len(panels))
        if index != chosen and inks[index] >= 28 and letters[index] + 0.025 < letters[chosen]
    ]
    if letters[chosen] >= 0.045 and quieter:
        return panels[min(quieter, key=lambda index: letters[index])]
    return panels[chosen]


def looks_grouped(image: Image.Image) -> bool:
    width, height = image.size
    strips = (
        image,
        image.crop((0, 0, width, int(height * 0.42))),
        image.crop((0, int(height * 0.58), width, height)),
        image.crop((0, 0, int(width * 0.42), height)),
        image.crop((int(width * 0.58), 0, width, height)),
    )
    return any(package_count(strip) >= 2 for strip in strips)


def keep_back_panel(image: Image.Image, expected: str) -> Image.Image:
    if not looks_grouped(image):
        return image
    width, height = image.size
    area = width * height
    options = _all_cuts(image)
    for axis, cuts in options:
        if len(cuts) == 1:
            shifts = (0.0, 0.06, 0.10, 0.12, -0.06)
            for shift in shifts:
                moved = cuts[0] + shift
                if not 0.34 <= moved <= 0.66:
                    continue
                panels = _panels_at(image, axis, [moved])
                if len(panels) != 2 or any(_is_band(image, panel) for panel in panels):
                    continue
                shares = [panel.size[0] * panel.size[1] / area for panel in panels]
                if not all(0.30 <= share <= 0.66 for share in shares):
                    continue
                if any(label_ink(panel) < 16 for panel in panels):
                    continue
                if any(package_count(panel) >= 2 for panel in panels):
                    continue
                chosen = _barcode_choice(panels, expected)
                if chosen is None or package_count(chosen) >= 2:
                    continue
                if axis == "y" and _barcode_sits_beside(chosen):
                    continue
                return chosen
            continue
        panels = _panels_at(image, axis, cuts)
        if len(panels) != 3:
            continue
        shares = [panel.size[0] * panel.size[1] / area for panel in panels]
        if not all(0.24 <= share <= 0.42 for share in shares):
            continue
        if any(label_ink(panel) < 16 for panel in panels):
            continue
        if any(package_count(panel) >= 2 for panel in panels):
            continue
        chosen = _barcode_choice(panels, expected)
        if chosen is None:
            reds = [_redness(panel) for panel in panels]
            quiet = min(range(len(panels)), key=lambda index: reds[index])
            others = [reds[index] for index in range(len(panels)) if index != quiet]
            if min(others) - reds[quiet] >= 0.10 and label_ink(panels[quiet]) >= 28:
                chosen = panels[quiet]
        if chosen is not None and package_count(chosen) < 2:
            return chosen
    return image


def crop_empty_borders(image: Image.Image, expected: str) -> Image.Image:
    preview, _scale = _prepare(image, 700)
    arr = np.asarray(preview.convert("RGB"))
    width, height = image.size
    box = [0.0, 0.0, 1.0, 1.0]
    for axis, start_index, end_index in (("x", 0, 2), ("y", 1, 3)):
        gaps = [
            gap
            for gap in _local_gaps(_edge_profile(arr, axis), 0.20, 0.12)
            if gap[1] >= 0.85 and gap[2] <= 0.08 and 0.12 <= gap[0] <= 0.88
        ]
        if not gaps:
            continue
        inner_start = 0.0
        inner_end = 1.0
        for fraction, _depth, _balance in gaps:
            if fraction < 0.5:
                inner_start = max(inner_start, fraction)
            else:
                inner_end = min(inner_end, fraction)
        if inner_end - inner_start < 0.35:
            continue
        box[start_index] = inner_start
        box[end_index] = inner_end
    if box == [0.0, 0.0, 1.0, 1.0]:
        return image
    cropped = image.crop((int(width * box[0]), int(height * box[1]), int(width * box[2]), int(height * box[3])))
    share = (cropped.size[0] * cropped.size[1]) / (width * height)
    if share > 0.55 or share < 0.18 or not _matches(cropped, expected):
        return image
    return cropped


def _thumb(image: Image.Image) -> Image.Image:
    probe = image.copy()
    probe.thumbnail((1400, 1400))
    return probe


def _barcode_height(image: Image.Image) -> float | None:
    probe = _thumb(image)
    hits = read_retail_barcodes(probe)
    if not hits:
        return None
    return sum(hit.center_y for hit in hits) / len(hits) / probe.size[1]


def stand_up(image: Image.Image) -> tuple[Image.Image, int]:
    probe = _thumb(image)
    hits = read_retail_barcodes(probe)
    score, fraction = product_text_score(image)
    landscape = image.size[0] > image.size[1] * 1.35
    # A vertical barcode on an upright label (can, cup) must stay. A whole
    # bag lying on its side has the same barcode angle, but its text is sideways.
    package_on_its_side = landscape and score >= 1.40 and fraction >= 0.45
    if hits and min(hit.upright_ccw % 180 for hit in hits) == 90 and not package_on_its_side:
        return image, 0
    if score < 1.18 or fraction < 0.38:
        if not landscape:
            return image, 0
    options: list[tuple[float, int, Image.Image]] = []
    for ccw in (90, 270):
        turned = rotate_upright(image, ccw)
        turned_score, _fraction = product_text_score(turned)
        options.append((turned_score, ccw, turned))
    options.sort(key=lambda item: item[0])
    if not landscape and (options[0][0] > 0.98 or score - options[0][0] < 0.18):
        return image, 0
    if abs(options[0][0] - options[1][0]) < 0.10 or landscape:
        placed: list[tuple[float, int, Image.Image]] = []
        for _turned_score, ccw, turned in options:
            height = _barcode_height(turned)
            if height is None:
                continue
            placed.append((height, ccw, turned))
        if len(placed) >= 2 and placed[0][0] != placed[1][0]:
            placed.sort(reverse=True)
            if placed[0][0] >= 0.40 and placed[0][0] - placed[1][0] >= 0.12:
                return placed[0][2], placed[0][1]
        latin = sorted(
            ((latin_upright(turned), ccw, turned) for _score, ccw, turned in options),
            reverse=True,
        )
        if latin[0][0] - latin[1][0] >= 0.8:
            return latin[0][2], latin[0][1]
        return image, 0
    return options[0][2], options[0][1]


def locked_codes() -> set[str]:
    if not ACCEPTED_PATH.is_file():
        return set()
    data = json.loads(ACCEPTED_PATH.read_text(encoding="utf-8"))
    return {code for code, row in data.items() if isinstance(row, dict) and row.get("locked")}


def repair(image: Image.Image, expected: str) -> tuple[Image.Image, str]:
    if expected in PROTECTED or expected in locked_codes():
        return image, ""
    panel = keep_back_panel(image, expected)
    reason = ""
    if panel.size != image.size:
        reason = "panel"
        upright, ccw = stand_up(panel)
        if ccw:
            panel = upright
            reason = f"panel+rot{ccw}"
    else:
        bordered = crop_empty_borders(image, expected)
        if bordered.size != image.size:
            panel = bordered
            reason = "border"
    if not reason:
        return image, ""
    if min(panel.size) < 280 or _is_band(image, panel):
        return image, ""
    share = (panel.size[0] * panel.size[1]) / (image.size[0] * image.size[1])
    if share < 0.15:
        return image, ""
    return panel, reason


def _save_jpeg(image: Image.Image, path: Path) -> None:
    image.save(path, format="JPEG", quality=95, subsampling=0)
    webp = path.with_suffix(".webp")
    if webp.exists():
        webp.unlink()


def _update_manifest(changes: dict[str, tuple[Image.Image, str]]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for code, (image, reason) in changes.items():
        record = manifest.get(code)
        if not isinstance(record, dict):
            continue
        record["back_size"] = f"{image.size[0]}x{image.size[1]}"
        record["back_ok"] = True
        record["mode"] = "back_only"
        record["rotation"] = 90 if "rot90" in reason else 270 if "rot270" in reason else 0
        record["note"] = "kept the single upright back"
        record["ok"] = bool(record.get("front_ok"))
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, separators=(", ", ": ")), encoding="utf-8")


def main() -> None:
    apply = "--apply" in sys.argv
    codes = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    paths = [BACK_DIR / f"{code}_back.jpg" for code in codes] if codes else sorted(BACK_DIR.glob("*_back.jpg"))
    PREVIEW.mkdir(parents=True, exist_ok=True)
    changes: dict[str, tuple[Image.Image, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        code = path.name.replace("_back.jpg", "")
        image = Image.open(path).convert("RGB")
        fixed, reason = repair(image, code)
        if not reason:
            if codes:
                print(f"{code} {image.size[0]}x{image.size[1]} keep", flush=True)
            elif looks_grouped(image):
                thumb = image.copy()
                thumb.thumbnail((220, 220))
                thumb.save(PREVIEW / f"group_{code}.jpg", quality=70)
            continue
        changes[code] = (fixed, reason)
        print(
            f"{code} {image.size[0]}x{image.size[1]} -> {fixed.size[0]}x{fixed.size[1]} {reason}",
            flush=True,
        )
        before = image.copy()
        before.thumbnail((360, 360))
        after = fixed.copy()
        after.thumbnail((360, 360))
        pair = Image.new("RGB", (before.size[0] + after.size[0] + 8, max(before.size[1], after.size[1])), (40, 40, 40))
        pair.paste(before, (0, 0))
        pair.paste(after, (before.size[0] + 8, 0))
        pair.save(PREVIEW / f"pair_{code}.jpg", quality=75)
    log = PREVIEW / "changes.txt"
    log.write_text(
        "\n".join(f"{code} {image.size[0]}x{image.size[1]} {reason}" for code, (image, reason) in changes.items()),
        encoding="utf-8",
    )
    print("changed", len(changes), flush=True)
    if not apply:
        return
    for code, (fixed, _reason) in changes.items():
        _save_jpeg(fixed, BACK_DIR / f"{code}_back.jpg")
    if changes:
        _update_manifest(changes)


if __name__ == "__main__":
    main()
