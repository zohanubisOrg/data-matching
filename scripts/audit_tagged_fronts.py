"""Flag tagged fronts that are sideways, cut down to a logo, or still show two packs."""

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

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup  # noqa: E402
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants  # noqa: E402

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front"
OUT = ROOT / "output/catalog_pairs/_front_audit.json"


def content_mask(rgb: np.ndarray) -> np.ndarray:
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    white = (rgb.min(axis=2) > 236) & (spread < 18)
    return ~white


def text_score(gray: np.ndarray, mask: np.ndarray) -> float:
    if int(mask.sum()) < 80:
        return 1.0
    vertical = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    horizontal = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    energy = vertical + horizontal
    strong = mask & (energy > np.percentile(energy[mask], 60))
    if int(strong.sum()) < 40:
        strong = mask
    return float(vertical[strong].mean()) / max(float(horizontal[strong].mean()), 1.0)


def audit_one(path: Path) -> dict:
    image = Image.open(path).convert("RGB")
    image.thumbnail((480, 480))
    rgb = np.asarray(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mask = content_mask(rgb)
    height, width = mask.shape
    frame = width * height
    coverage = float(mask.mean())
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    blobs = []
    for index in range(1, count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < frame * 0.02:
            continue
        blobs.append(
            {
                "area": area / frame,
                "x": int(stats[index, cv2.CC_STAT_LEFT]),
                "y": int(stats[index, cv2.CC_STAT_TOP]),
                "w": int(stats[index, cv2.CC_STAT_WIDTH]),
                "h": int(stats[index, cv2.CC_STAT_HEIGHT]),
            }
        )
    blobs.sort(key=lambda item: item["area"], reverse=True)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        box = (0, 0, 0, 0)
    else:
        box = (int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1))
    box_w = max(1, box[2] - box[0])
    box_h = max(1, box[3] - box[1])
    reasons = []
    if coverage < 0.12:
        reasons.append("tiny")
    if box_w / width < 0.28 or box_h / height < 0.28:
        reasons.append("strip")
    ratio = box_w / box_h
    if ratio > 2.4 or ratio < 0.42:
        reasons.append("thin-product")
    score = text_score(gray, mask)
    if score >= 1.35:
        reasons.append("sideways")
    if len(blobs) >= 2 and blobs[1]["area"] >= 0.08:
        gap_x = blobs[0]["x"] > blobs[1]["x"] + blobs[1]["w"] or blobs[1]["x"] > blobs[0]["x"] + blobs[0]["w"]
        gap_y = blobs[0]["y"] > blobs[1]["y"] + blobs[1]["h"] or blobs[1]["y"] > blobs[0]["y"] + blobs[0]["h"]
        if gap_x or gap_y:
            reasons.append("two-packs")
    return {
        "code": path.name.replace("_front.jpg", ""),
        "file_size": list(Image.open(path).size),
        "coverage": round(coverage, 3),
        "box": [box[0] / width, box[1] / height, box_w / width, box_h / height],
        "text": round(score, 2),
        "blobs": len(blobs),
        "reasons": reasons,
    }


def main() -> None:
    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    excel = {product["barcode"] for product in products}
    rows = []
    for path in sorted(FRONT_DIR.glob("*_front.jpg")):
        row = audit_one(path)
        code = row["code"]
        canonical = lookup.get(code)
        if canonical is None:
            for variant in get_barcode_lookup_variants(code):
                if variant in lookup:
                    canonical = lookup[variant]
                    break
        row["excel"] = canonical or ""
        rows.append(row)
    have = {row["excel"] for row in rows if row["excel"]}
    missing = [product["barcode"] for product in products if product["barcode"] not in have]
    flagged = [row for row in rows if row["reasons"]]
    payload = {
        "excel_products": len(excel),
        "fronts": len(rows),
        "matched": sum(1 for row in rows if row["excel"]),
        "missing_front": missing,
        "flagged": flagged,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("fronts", len(rows), "flagged", len(flagged), "missing", len(missing), flush=True)
    counts: dict[str, int] = {}
    for row in flagged:
        for reason in row["reasons"]:
            counts[reason] = counts.get(reason, 0) + 1
    print(counts, flush=True)


if __name__ == "__main__":
    main()
