"""Copy Excel-matched originals, then cut front and back without scanning again."""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import (  # noqa: E402
    INDEX_PATH,
    OUTPUT_DIR,
    _rank,
    export_product,
    load_ground_truth,
    EXCEL_SOURCE,
)
from product_mapper.ingestion.image_loader import save_image_high_quality  # noqa: E402
from product_mapper.vision.barcode_side_splitter import enhance_back, packshot_front  # noqa: E402
from PIL import Image  # noqa: E402

PAIRS = ROOT / "output/catalog_pairs"
ORIGINALS = PAIRS / "originals"
TAGGED = PAIRS / "tagged"
AGENT = "RabutaCatalog/1.0 (barcode photo check)"


def _export_job(payload: tuple[dict, str]) -> dict:
    record, barcode = payload
    try:
        result = export_product(record, barcode, output_dir=TAGGED)
        result["barcode"] = barcode
        result["ok"] = True
    except Exception as exc:
        result = {"barcode": barcode, "ok": False, "error": str(exc), "source": record.get("path", "")}
    return result


def _download(url: str) -> Image.Image | None:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            image = Image.open(BytesIO(response.read())).convert("RGB")
    except Exception:
        return None
    if min(image.size) < 200:
        return None
    return image


def _copy_originals(grouped: dict[str, list[dict]]) -> int:
    copied = 0
    for barcode, group in grouped.items():
        folder = ORIGINALS / barcode
        folder.mkdir(parents=True, exist_ok=True)
        for record in group:
            source = Path(record["path"])
            dest = folder / f"{source.parent.name}_{source.name}"
            if not dest.exists():
                shutil.copy2(source, dest)
                copied += 1
    return copied


def _web_fill(exported: dict[str, dict]) -> int:
    previous = json.loads((OUTPUT_DIR / "export_results.json").read_text(encoding="utf-8"))
    added = 0
    for barcode, row in previous.items():
        if barcode in exported:
            continue
        source = str(row.get("source") or "")
        if not source.startswith("http"):
            continue
        image = _download(source)
        if image is None:
            continue
        front = packshot_front(image)
        front_path = TAGGED / "front" / f"{barcode}_front.jpg"
        front_path.parent.mkdir(parents=True, exist_ok=True)
        front.save(front_path, format="JPEG", quality=95, subsampling=0)
        back_path = ""
        back_size = ""
        old_back = Path(str(row.get("back_path") or ""))
        if old_back.is_file():
            dest = TAGGED / "back" / f"{barcode}_back.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            back = enhance_back(Image.open(old_back).convert("RGB"))
            save_image_high_quality(back, dest, quality=95, save_webp=False)
            back_path = str(dest)
            back_size = f"{back.size[0]}x{back.size[1]}"
        exported[barcode] = {
            "mode": "web",
            "rotation": 0,
            "source": source,
            "back_path": back_path,
            "back_ok": bool(back_path),
            "back_size": back_size,
            "front_path": str(front_path),
            "front_ok": True,
            "front_size": f"{front.size[0]}x{front.size[1]}",
            "note": row.get("note") or "Front from Open Food Facts, full package kept.",
            "barcode": barcode,
            "ok": True,
        }
        added += 1
        print(f"  web {barcode}", flush=True)
    return added


def main() -> None:
    products = load_ground_truth(EXCEL_SOURCE)
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        barcode = record.get("excel_barcode")
        if barcode and record.get("center"):
            grouped[barcode].append(record)
    copied = _copy_originals(grouped)
    print(f"originals copied {copied} for {len(grouped)} barcodes", flush=True)
    jobs = [(max(group, key=_rank), barcode) for barcode, group in grouped.items()]
    exports: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_export_job, job) for job in jobs]
        total = len(futures)
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            exports[result["barcode"]] = result
            if not result.get("ok"):
                print("fail", result.get("barcode"), result.get("error"), flush=True)
            if done % 50 == 0 or done == total:
                fronts = sum(1 for item in exports.values() if item.get("front_ok"))
                print(f"  tagged {done}/{total} fronts {fronts}", flush=True)
    web = _web_fill(exports)
    print(f"web filled {web}", flush=True)
    (PAIRS / "manifest.json").write_text(json.dumps(exports, ensure_ascii=False), encoding="utf-8")
    excel_codes = {product["barcode"] for product in products}
    print(
        f"excel {len(excel_codes)} tagged {len(excel_codes & set(exports))} missing {len(excel_codes - set(exports))}",
        flush=True,
    )


if __name__ == "__main__":
    main()
