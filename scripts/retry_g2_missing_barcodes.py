#!/usr/bin/env python3
"""Second pass for G2 photos whose first scan found no barcode.

A code that is in the Excel catalog is exported into front-v2 and back-v2.
A code that is not in the Excel catalog is removed from the source folder.
A photo that still has no readable code is moved to g2-barcode-check.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.ingestion.image_loader import open_image_safely
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants, validate_ean_upc_checksum
from run_folder_front_back_v2 import export_pair

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
SOURCE = ROOT / "source-import/G2_original"
FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front-v2"
BACK_DIR = ROOT / "output/catalog_pairs/tagged/back-v2"
CHECK_DIR = ROOT / "output/catalog_pairs/tagged/g2-barcode-check"
RETAIL = zxingcpp.BarcodeFormat.EANUPC

NOT_IN_EXCEL = [
    ("8857118730075", "IMG_0458.jpeg"),
    ("4938321679055", "IMG_0619.jpeg"),
    ("1379741002277", "IMG_0639.jpeg"),
    ("0185098000078", "IMG_0651.jpeg"),
    ("0770461100136", "IMG_0820.jpeg"),
    ("0977617020199", "IMG_0837.jpeg"),
    ("0978805902716", "IMG_0855.jpeg"),
    ("0730891051026", "IMG_0929.jpeg"),
]

NO_BARCODE = [
    "IMG_0445.jpeg", "IMG_0446.jpeg", "IMG_0439.jpeg", "IMG_0443.jpeg", "IMG_0447.jpeg",
    "IMG_0449.jpeg", "IMG_0450.jpeg", "IMG_0455.jpeg", "IMG_0470.jpeg", "IMG_0471.jpeg",
    "IMG_0482.jpeg", "IMG_0487.jpeg", "IMG_0492.jpeg", "IMG_0511.jpeg", "IMG_0513.jpeg",
    "IMG_0518.jpeg", "IMG_0520.jpeg", "IMG_0526.jpeg", "IMG_0527.jpeg", "IMG_0528.jpeg",
    "IMG_0529.jpeg", "IMG_0532.jpeg", "IMG_0538.jpeg", "IMG_0549.jpeg", "IMG_0551.jpeg",
    "IMG_0553.jpeg", "IMG_0555.jpeg", "IMG_0554.jpeg", "IMG_0571.jpeg", "IMG_0565.jpeg",
    "IMG_0569.jpeg", "IMG_0570.jpeg", "IMG_0573.jpeg", "IMG_0594.jpeg", "IMG_0578.jpeg",
    "IMG_0588.jpeg", "IMG_0603.jpeg", "IMG_0616.jpeg", "IMG_0637.jpeg", "IMG_0640.jpeg",
    "IMG_0647.jpeg", "IMG_0659.jpeg", "IMG_0665.jpeg", "IMG_0654.jpeg", "IMG_0679.jpeg",
    "IMG_0684.jpeg", "IMG_0710.jpeg", "IMG_0691.jpeg", "IMG_0709.jpeg", "IMG_0741.jpeg",
    "IMG_0768.jpeg", "IMG_0772.jpeg", "IMG_0810.jpeg", "IMG_0800.jpeg", "IMG_0801.jpeg",
    "IMG_0825.jpeg", "IMG_0835.jpeg", "IMG_0826.jpeg", "IMG_0839.jpeg", "IMG_0847.jpeg",
    "IMG_0850.jpeg", "IMG_0861.jpeg", "IMG_0866.jpeg", "IMG_0865.jpeg", "IMG_0912.jpeg",
    "IMG_0921.jpeg", "IMG_0923.jpeg", "IMG_0924.jpeg", "IMG_0926.jpeg",
]


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _windows(width: int, height: int) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    for y_frac in (0.0, 0.30, 0.55):
        for x_frac in (0.0, 0.30, 0.55):
            x0 = int(width * x_frac)
            y0 = int(height * y_frac)
            x1 = int(min(width, width * (x_frac + 0.52)))
            y1 = int(min(height, height * (y_frac + 0.50)))
            if x1 - x0 > 80 and y1 - y0 > 80:
                boxes.append((x0, y0, x1, y1))
    return boxes


def _prepare(crop: Image.Image) -> tuple[Image.Image, float]:
    long_side = max(crop.size)
    scale = 1.0
    if long_side < 1800:
        scale = 1800 / long_side
    elif long_side > 2400:
        scale = 2400 / long_side
    if abs(scale - 1.0) > 0.01:
        crop = crop.resize(
            (max(1, int(crop.size[0] * scale)), max(1, int(crop.size[1] * scale))),
            Image.Resampling.LANCZOS,
        )
    gray = ImageOps.autocontrast(ImageOps.grayscale(crop))
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(np.array(gray))
    return Image.fromarray(clahe), scale


def _from_zxing(result, box: tuple[int, int, int, int], scale: float) -> dict | None:
    text = _digits(result.text)
    if not validate_ean_upc_checksum(text):
        return None
    points = []
    for name in ("top_left", "top_right", "bottom_right", "bottom_left"):
        point = getattr(result.position, name)
        points.append(((float(point.x) / scale) + box[0], (float(point.y) / scale) + box[1]))
    center_x = sum(point[0] for point in points) / 4.0
    center_y = sum(point[1] for point in points) / 4.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "text": text,
        "engine": "zxing",
        "center": [center_x, center_y],
        "area": max(1.0, (max(xs) - min(xs)) * (max(ys) - min(ys))),
    }


def _from_opencv(info, points, box: tuple[int, int, int, int], scale: float) -> dict | None:
    texts = info if isinstance(info, (list, tuple)) else [info]
    text = ""
    for item in texts:
        digits = _digits(item)
        if validate_ean_upc_checksum(digits):
            text = digits
            break
    if not text or points is None:
        return None
    array = np.asarray(points, dtype=float).reshape(-1, 2)
    if array.size < 4:
        return None
    center_x = float(array[:, 0].mean()) / scale + box[0]
    center_y = float(array[:, 1].mean()) / scale + box[1]
    area = max(1.0, (array[:, 0].max() - array[:, 0].min()) * (array[:, 1].max() - array[:, 1].min())) / (scale * scale)
    return {"text": text, "engine": "opencv", "center": [center_x, center_y], "area": area}


def hard_read(path: Path) -> dict | None:
    image = open_image_safely(path)
    width, height = image.size
    detector = cv2.barcode.BarcodeDetector()
    hits: list[dict] = []
    for box in _windows(width, height):
        prepared, scale = _prepare(image.crop(box))
        for result in zxingcpp.read_barcodes(
            prepared,
            formats=RETAIL,
            try_rotate=True,
            try_downscale=True,
            try_invert=True,
        ):
            hit = _from_zxing(result, box, scale)
            if hit is not None:
                hits.append(hit)
        info, points, _straight = detector.detectAndDecode(cv2.cvtColor(np.array(prepared), cv2.COLOR_GRAY2BGR))
        opencv_hit = _from_opencv(info, points, box, scale)
        if opencv_hit is not None:
            hits.append(opencv_hit)
        if any(hit["engine"] == "zxing" for hit in hits):
            break
    image.close()
    if not hits:
        return None
    zxing_hits = [hit for hit in hits if hit["engine"] == "zxing"]
    pool = zxing_hits or hits
    return max(pool, key=lambda hit: hit["area"])


def _excel_barcode(text: str, lookup: dict[str, str]) -> str | None:
    for variant in get_barcode_lookup_variants(text):
        if variant in lookup:
            return lookup[variant]
    return None


def _delete_named(barcode: str) -> list[str]:
    removed = []
    variants = set(get_barcode_lookup_variants(barcode))
    variants.add(barcode)
    for folder in (FRONT_DIR, BACK_DIR):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            stem = path.stem
            code = stem.replace("-front", "").replace("-back", "")
            if code in variants:
                path.unlink()
                removed.append(str(path))
    return removed


def _delete_source(name: str) -> str:
    path = SOURCE / name
    if path.exists():
        path.unlink()
        return str(path)
    return ""


def _clear_debug_files() -> None:
    if not CHECK_DIR.exists():
        return
    for path in CHECK_DIR.iterdir():
        if path.is_file() and not path.name.startswith("IMG_"):
            path.unlink()


def main() -> None:
    _clear_debug_files()
    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    lookup = truth_lookup(load_ground_truth(EXCEL_SOURCE))

    removed_sources = []
    removed_exports = []
    for barcode, name in NOT_IN_EXCEL:
        removed_exports.extend(_delete_named(barcode))
        deleted = _delete_source(name)
        if deleted:
            removed_sources.append(name)
    print(f"Removed {len(removed_sources)} source photos whose barcode is not in Excel.", flush=True)

    matched: list[dict] = []
    extra: list[dict] = []
    unread: list[str] = []
    for index, name in enumerate(NO_BARCODE, start=1):
        path = SOURCE / name
        if not path.exists():
            print(f"  {index}/{len(NO_BARCODE)} {name} missing", flush=True)
            continue
        hit = hard_read(path)
        if hit is None:
            unread.append(name)
            print(f"  {index}/{len(NO_BARCODE)} {name} no barcode", flush=True)
            continue
        excel_barcode = _excel_barcode(hit["text"], lookup)
        record = {
            "file": name,
            "read": hit["text"],
            "engine": hit["engine"],
            "excel_barcode": excel_barcode,
            "center": [round(hit["center"][0], 1), round(hit["center"][1], 1)],
            "area": round(hit["area"], 1),
        }
        if excel_barcode:
            matched.append(record)
            print(f"  {index}/{len(NO_BARCODE)} {name} -> {excel_barcode}", flush=True)
        elif hit["engine"] == "zxing":
            extra.append(record)
            print(f"  {index}/{len(NO_BARCODE)} {name} -> {hit['text']} not in Excel", flush=True)
        else:
            unread.append(name)
            print(f"  {index}/{len(NO_BARCODE)} {name} weak read {hit['text']}", flush=True)

    by_barcode: dict[str, list[dict]] = {}
    for record in matched:
        by_barcode.setdefault(record["excel_barcode"], []).append(record)

    exported = []
    for barcode, photos in by_barcode.items():
        best = max(photos, key=lambda item: item["area"])
        image = open_image_safely(SOURCE / best["file"])
        scan_record = {
            "path": str(SOURCE / best["file"]),
            "center": best["center"],
            "mirrored": False,
            "width": image.size[0],
            "height": image.size[1],
        }
        image.close()
        front_exists = (FRONT_DIR / f"{barcode}-front.jpg").exists()
        back_exists = (BACK_DIR / f"{barcode}-back.jpg").exists()
        if front_exists and back_exists:
            exported.append({**best, "skipped": "pair already exported"})
            continue
        result = export_pair(scan_record, barcode, FRONT_DIR, BACK_DIR)
        exported.append({**best, "front_ok": result.get("front_ok"), "back_ok": result.get("back_ok"), "note": result.get("note", "")})
        print(f"  exported {barcode} front={result.get('front_ok')} back={result.get('back_ok')}", flush=True)

    for record in extra:
        removed_exports.extend(_delete_named(record["read"]))
        deleted = _delete_source(record["file"])
        if deleted:
            removed_sources.append(record["file"])

    moved = []
    for name in unread:
        source = SOURCE / name
        if not source.exists():
            continue
        destination = CHECK_DIR / name
        if destination.exists():
            destination.unlink()
        shutil.move(str(source), str(destination))
        moved.append(name)

    report = {
        "removed_not_in_excel": [name for _barcode, name in NOT_IN_EXCEL if name in removed_sources or True],
        "deleted_source_files": removed_sources,
        "deleted_export_files": removed_exports,
        "newly_matched": exported,
        "newly_not_in_excel": extra,
        "still_unreadable": moved,
        "check_folder": str(CHECK_DIR),
    }
    report_path = ROOT / "output/catalog_pairs/g2_barcode_retry.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Done. matched {len(exported)}, not in Excel removed {len(extra)}, "
        f"moved to check {len(moved)}",
        flush=True,
    )
    print(f"Check folder: {CHECK_DIR}", flush=True)
    print(f"Report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
