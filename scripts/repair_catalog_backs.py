"""Replace the audited back images with a full label.

Warehouse photos are cut again from the original file. Web photos use an
Open Food Facts upload of the whole package when the saved file is only
an ingredients strip.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import INDEX_PATH, export_product, open_at  # noqa: E402
from product_mapper.ingestion.image_loader import save_image_high_quality  # noqa: E402
from product_mapper.vision.barcode_side_splitter import (  # noqa: E402
    _largest_box,
    _prepare,
    enhance_back,
    packshot_front,
    read_retail_barcodes,
)
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants  # noqa: E402

TAGGED = ROOT / "output/catalog_pairs/tagged"
MANIFEST = ROOT / "output/catalog_pairs/manifest.json"
AGENT = "RabutaCatalog/1.0 (barcode photo check)"
# The sales face sits the other way up from the ingredients bag.
FLIP_FRONT = {"030891051195"}
WEB_CODES = [
    "084909000774", "084909000781", "084909000798", "084909001948",
    "8850030116163", "8851011113263", "8934804026817", "8720301109388",
    "8888003110306", "8934743042909", "640700003231", "3760344351073",
    "022392573184", "8851876003006", "8850058004121", "3474930309897",
    "078895300024", "020717230156", "087703002685", "4260028480086",
    "8720301100736", "8854334005031",
]


def ean13_from_gtin14(code: str) -> str:
    body = code[1:13]
    digits = [int(char) for char in body]
    total = 0
    weight = 3
    for digit in reversed(digits):
        total += digit * weight
        weight = 1 if weight == 3 else 3
    return body + str((10 - (total % 10)) % 10)


def lookup_codes(barcode: str) -> list[str]:
    codes = list(get_barcode_lookup_variants(barcode))
    if len(barcode) == 14 and barcode.isdigit():
        codes.extend(get_barcode_lookup_variants(ean13_from_gtin14(barcode)))
    return list(dict.fromkeys(codes))


def load_index(codes: set[str]) -> dict[str, dict]:
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    found: dict[str, dict] = {}
    for record in records:
        code = record.get("excel_barcode")
        if code in codes and code not in found and record.get("center"):
            found[code] = record
    return found


def write_pair(barcode: str, back: Image.Image, front: Image.Image, manifest: dict, **fields: object) -> None:
    back_path = TAGGED / "back" / f"{barcode}_back.jpg"
    front_path = TAGGED / "front" / f"{barcode}_front.jpg"
    save_image_high_quality(back, back_path, quality=95, save_webp=False)
    save_image_high_quality(front, front_path, quality=95, save_webp=False)
    current = manifest.get(barcode) or {}
    current.update(fields)
    current["back_path"] = str(back_path)
    current["back_size"] = f"{back.size[0]}x{back.size[1]}"
    current["back_ok"] = True
    current["front_path"] = str(front_path)
    current["front_size"] = f"{front.size[0]}x{front.size[1]}"
    current["front_ok"] = True
    current["barcode"] = barcode
    current["ok"] = True
    manifest[barcode] = current


def repair_warehouse(manifest: dict) -> None:
    codes = {"5027738014234", "030891051195", "8720301109067", "8801043951685"}
    records = load_index(codes)
    for barcode in ("5027738014234", "030891051195", "8720301109067"):
        result = export_product(records[barcode], barcode, output_dir=TAGGED)
        if barcode in FLIP_FRONT:
            front_path = TAGGED / "front" / f"{barcode}_front.jpg"
            turned = Image.open(front_path).transpose(Image.Transpose.ROTATE_180)
            save_image_high_quality(turned, front_path, quality=95, save_webp=False)
            result["front_size"] = f"{turned.size[0]}x{turned.size[1]}"
            result["note"] = (result.get("note") or "") + " Front turned to match the upright sales face."
        manifest[barcode] = {**manifest.get(barcode, {}), **result, "barcode": barcode, "ok": True}
        print(f"warehouse {barcode} {result['mode']} rot {result['rotation']} back {result['back_size']}", flush=True)

    carton_record = records["8801043951685"]
    carton, _x, _y = open_at(carton_record, 0)
    preview, scale = _prepare(carton, 900)
    box = _largest_box(np.asarray(preview), (0, 0, preview.size[0], preview.size[1]))
    full = tuple(int(round(value / scale)) for value in box)
    panel = carton.crop(full)
    write_pair(
        "8801043951685",
        enhance_back(panel),
        packshot_front(panel),
        manifest,
        mode="back_only",
        rotation=0,
        source=carton_record["path"],
        note="Kept the whole carton face. The side strip was not a separate package.",
    )
    print(f"warehouse 8801043951685 carton {full}", flush=True)


def fetch_json(barcode: str) -> dict | None:
    for code in lookup_codes(barcode):
        url = f"https://world.openfoodfacts.org/api/v2/product/{code}.json?fields=code,images"
        request = urllib.request.Request(url, headers={"User-Agent": AGENT})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
        if payload.get("status") == 1 and payload.get("product"):
            return payload["product"]
    return None


def folder_from_manifest(row: dict) -> str:
    source = str(row.get("source") or "")
    match = re.search(r"/products/((?:\d{3}/){3}\d+)/", source)
    return match.group(1) if match else ""


def download_off(folder: str, image_id: str) -> Image.Image | None:
    url = f"https://images.openfoodfacts.org/images/products/{folder}/{image_id}.jpg"
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            image = Image.open(BytesIO(response.read())).convert("RGB")
    except Exception:
        return None
    if min(image.size) < 280:
        return None
    return image


def barcode_matches(image: Image.Image, expected: str) -> bool:
    expected_forms = set(get_barcode_lookup_variants(expected))
    for hit in read_retail_barcodes(image):
        if hit.text in expected_forms or expected in set(get_barcode_lookup_variants(hit.text)):
            return True
    return False


def choose_web_back(barcode: str, product: dict, folder: str) -> Image.Image | None:
    images = product.get("images") or {}
    front_ids = {
        str(value.get("imgid"))
        for key, value in images.items()
        if key.startswith("front") and isinstance(value, dict) and value.get("imgid") is not None
    }
    label_ids = {
        str(value.get("imgid"))
        for key, value in images.items()
        if key.startswith(("ingredients", "nutrition", "packaging"))
        and isinstance(value, dict)
        and value.get("imgid") is not None
    }
    ranked: list[tuple[int, int, str]] = []
    for key, value in images.items():
        if not key.isdigit() or not isinstance(value, dict) or key in front_ids:
            continue
        sizes = (value.get("sizes") or {}).get("full") or {}
        width = int(sizes.get("w") or 0)
        height = int(sizes.get("h") or 0)
        if width < 400 or height < 400:
            continue
        if max(width, height) / max(1, min(width, height)) > 3.2:
            continue
        label_first = 1 if key in label_ids else 0
        ranked.append((label_first, width * height, key))
    ranked.sort(reverse=True)
    chosen: Image.Image | None = None
    for _label, _area, image_id in ranked[:6]:
        image = download_off(folder, image_id)
        if image is None:
            continue
        if barcode_matches(image, barcode):
            return image
        if chosen is None:
            chosen = image
    return chosen


def repair_web(manifest: dict) -> None:
    for barcode in WEB_CODES:
        row = manifest.get(barcode) or {}
        folder = folder_from_manifest(row)
        product = fetch_json(barcode)
        if product is None or not folder:
            print(f"web {barcode} no record", flush=True)
            continue
        image = choose_web_back(barcode, product, folder)
        if image is None:
            print(f"web {barcode} no full back", flush=True)
            continue
        back = enhance_back(image)
        current = TAGGED / "back" / f"{barcode}_back.jpg"
        if current.is_file():
            old = Image.open(current)
            if back.size[1] <= old.size[1] and max(back.size) <= max(old.size):
                print(f"web {barcode} kept {old.size[0]}x{old.size[1]}", flush=True)
                continue
        dest = TAGGED / "back" / f"{barcode}_back.jpg"
        save_image_high_quality(back, dest, quality=95, save_webp=False)
        row.update(
            {
                "back_path": str(dest),
                "back_ok": True,
                "back_size": f"{back.size[0]}x{back.size[1]}",
                "note": (row.get("note") or "") + " Back replaced with the full package photo.",
            }
        )
        manifest[barcode] = row
        print(f"web {barcode} back {back.size[0]}x{back.size[1]}", flush=True)


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repair_warehouse(manifest)
    repair_web(manifest)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print("manifest updated", flush=True)


if __name__ == "__main__":
    main()
