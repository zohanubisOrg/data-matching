#!/usr/bin/env python3
"""Export one warehouse folder into front-v2 and back-v2.

Photos in the folder are already oriented for the sales face. The barcode is
used to name the product and to decide which panel is the back. The opposite
panel is the webshop front.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import ImageOps

from barcode_first_pipeline import load_ground_truth, truth_lookup
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality
from product_mapper.vision.barcode_side_splitter import (
    enhance_back,
    packshot_front,
    panel_halves,
    predict_split,
    read_retail_barcodes,
    scan_file,
    split_sides,
)
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants

EXCEL_SOURCE = ROOT / "source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
_TRUTH_CODES: set[str] = set()


def _init_worker(codes: list[str]) -> None:
    global _TRUTH_CODES
    _TRUTH_CODES = set(codes)


def _scan_task(path_str: str) -> dict:
    try:
        record = scan_file(Path(path_str), _TRUTH_CODES)
    except Exception as exc:
        return {"path": path_str, "barcode": None, "error": str(exc), "codes": []}
    return record


def _crop(image, box):
    return image.crop(box)


def _barcode_still_present(image, expected: str) -> bool:
    expected_forms = set(get_barcode_lookup_variants(expected))
    for hit in read_retail_barcodes(image):
        if hit.text in expected_forms or expected in set(get_barcode_lookup_variants(hit.text)):
            return True
    return False


def _front_kept_back(image, expected: str) -> bool:
    expected_forms = set(get_barcode_lookup_variants(expected))
    width, height = image.size
    for hit in read_retail_barcodes(image):
        forms = set(get_barcode_lookup_variants(hit.text))
        same = hit.text in expected_forms or expected in forms
        if same and hit.area > (width * height * 0.012):
            return True
    return False


def _open_oriented(record: dict):
    image = open_image_safely(record["path"])
    if record.get("mirrored"):
        image = ImageOps.mirror(image)
    return image, float(record["center"][0]), float(record["center"][1])


def export_pair(record: dict, barcode: str, front_dir: Path, back_dir: Path) -> dict:
    image, center_x, center_y = _open_oriented(record)
    sides = split_sides(image, center_x, center_y, 0)
    note = ""
    back = enhance_back(_crop(image, sides.back))
    back_ok = _barcode_still_present(back, barcode)
    if not back_ok:
        half = panel_halves(image, center_x, center_y, 0)
        candidate = enhance_back(_crop(image, half.back))
        if _barcode_still_present(candidate, barcode):
            back = candidate
            sides = half
            back_ok = True
            note = "Used the barcode half after the first back crop lost the code."
        else:
            note = "Back crop lost the barcode."

    front_crop = _crop(image, sides.front) if sides.front is not None else None
    if front_crop is not None and _front_kept_back(front_crop, barcode):
        front_crop = None
        note = (note + " " if note else "") + "Front crop still contained the back barcode."

    back_path = back_dir / f"{barcode}-back.jpg"
    if back_ok:
        save_image_high_quality(back, back_path, quality=94, save_webp=False)
    front_path = ""
    front_ok = False
    if front_crop is not None and back_ok:
        front = packshot_front(front_crop)
        dest = front_dir / f"{barcode}-front.jpg"
        save_image_high_quality(front, dest, quality=95, save_webp=False)
        front_path = str(dest)
        front_ok = True
    image.close()
    return {
        "barcode": barcode,
        "source": record["path"],
        "mode": sides.mode,
        "back_ok": back_ok,
        "front_ok": front_ok,
        "back_file": str(back_path) if back_ok else "",
        "front_file": front_path,
        "note": note.strip(),
    }


def _photo_rank(record: dict) -> tuple:
    mode = predict_split(
        int(record["width"]),
        int(record["height"]),
        float(record["center"][0]),
        float(record["center"][1]),
        0,
    )
    both = 0 if mode == "back_only" else 1
    return (both, float(record.get("area") or 0), int(record["width"]) * int(record["height"]))


def run(source: Path, tag: str, workers: int) -> None:
    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    files = sorted(path for path in source.iterdir() if path.is_file() and path.suffix.lower() in EXTENSIONS)
    print(f"Folder {source.name}: {len(files)} photos, Excel barcodes {len(products)}", flush=True)

    records: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(list(lookup),)) as pool:
        futures = [pool.submit(_scan_task, str(path)) for path in files]
        total = len(futures)
        for done, future in enumerate(as_completed(futures), start=1):
            records.append(future.result())
            if done % 25 == 0 or done == total:
                found = sum(1 for row in records if row.get("barcode"))
                print(f"  scanned {done}/{total}  barcode {found}", flush=True)

    by_excel: dict[str, list[dict]] = defaultdict(list)
    no_barcode = []
    not_in_excel = []
    for record in records:
        barcode = record.get("barcode")
        if not barcode:
            no_barcode.append(record)
            continue
        excel_barcode = lookup.get(barcode)
        if excel_barcode is None:
            for variant in get_barcode_lookup_variants(barcode):
                if variant in lookup:
                    excel_barcode = lookup[variant]
                    break
        record["excel_barcode"] = excel_barcode
        if excel_barcode:
            by_excel[excel_barcode].append(record)
        else:
            not_in_excel.append(record)

    out_base = ROOT / "output" / "catalog_pairs" / "tagged"
    front_dir = out_base / f"front-{tag}"
    back_dir = out_base / f"back-{tag}"
    front_dir.mkdir(parents=True, exist_ok=True)
    back_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    both = 0
    back_only = 0
    for index, (barcode, photos) in enumerate(sorted(by_excel.items()), start=1):
        ordered = sorted(photos, key=_photo_rank, reverse=True)
        chosen = None
        for record in ordered:
            try:
                result = export_pair(record, barcode, front_dir, back_dir)
            except Exception as exc:
                result = {
                    "barcode": barcode,
                    "source": record.get("path", ""),
                    "back_ok": False,
                    "front_ok": False,
                    "note": str(exc),
                }
            if result.get("front_ok") and result.get("back_ok"):
                chosen = result
                break
            if chosen is None and result.get("back_ok"):
                chosen = result
        if chosen is None:
            chosen = {
                "barcode": barcode,
                "source": ordered[0]["path"],
                "back_ok": False,
                "front_ok": False,
                "note": "Split failed on every photo of this barcode.",
            }
        product = next((item for item in products if item["barcode"] == barcode), None)
        chosen["name_en"] = product["name_en"] if product else ""
        chosen["brand"] = product["brand"] if product else ""
        chosen["photo_count"] = len(photos)
        manifest[barcode] = chosen
        if chosen.get("front_ok") and chosen.get("back_ok"):
            both += 1
        elif chosen.get("back_ok"):
            back_only += 1
        if index % 20 == 0 or index == len(by_excel):
            print(f"  exported {index}/{len(by_excel)}  both sides {both}", flush=True)

    manifest_path = ROOT / "output" / "catalog_pairs" / f"manifest_{source.name}_{tag}.json"
    report = {
        "source": str(source),
        "photos": len(files),
        "photos_with_barcode": sum(1 for row in records if row.get("barcode")),
        "photos_without_barcode": len(no_barcode),
        "barcodes_not_in_excel": len(not_in_excel),
        "excel_products_with_photo": len(by_excel),
        "both_sides": both,
        "back_only": back_only,
        "front_dir": str(front_dir),
        "back_dir": str(back_dir),
        "products": manifest,
        "no_barcode_files": [Path(row["path"]).name for row in no_barcode],
        "not_in_excel": [
            {"barcode": row.get("barcode"), "file": Path(row["path"]).name} for row in not_in_excel
        ],
    }
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Done {source.name}: both sides {both}, back only {back_only}, "
        f"no barcode {len(no_barcode)}, not in Excel {len(not_in_excel)}",
        flush=True,
    )
    print(f"Front: {front_dir}", flush=True)
    print(f"Back:  {back_dir}", flush=True)
    print(f"Report: {manifest_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one oriented photo folder to front-v2 and back-v2")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--tag", default="v2")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run(args.source, args.tag, args.workers)


if __name__ == "__main__":
    main()
