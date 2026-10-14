"""Add front and back photos for Excel barcodes that have no warehouse picture.

A web photo is kept only when the barcode and the product name agree with the Excel row.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth  # noqa: E402
from product_mapper.ingestion.image_loader import save_image_high_quality  # noqa: E402
from product_mapper.vision.barcode_side_splitter import enhance_back, packshot_front  # noqa: E402
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants  # noqa: E402

TAGGED = ROOT / "output/catalog_pairs/tagged"
MANIFEST = ROOT / "output/catalog_pairs/manifest.json"
AGENT = "RabutaCatalog/1.0 (barcode photo check)"
STOP = {
    "sauce", "powder", "drink", "tea", "rice", "noodles", "noodle", "instant",
    "flavour", "flavor", "flavoured", "flavored", "ground", "hot", "extra",
    "original", "selected", "japanese", "thai", "soy", "milk", "juice", "paste",
    "curry", "mango", "green", "food", "foods", "brand", "with", "and", "the",
    "for", "style", "frozen", "dried", "pack", "carton", "nuts",
}


def ean13_from_gtin14(code: str) -> str:
    body = code[1:13]
    digits = [int(char) for char in body]
    total = 0
    weight = 3
    for digit in reversed(digits):
        total += digit * weight
        weight = 1 if weight == 3 else 3
    return body + str((10 - (total % 10)) % 10)


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if len(word) > 2 and word not in STOP and not word.isdigit()]


def names_agree(product: dict, off_name: str, off_brand: str) -> bool:
    off_tokens = set(tokens(f"{off_name} {off_brand}"))
    brand_tokens = tokens(product["brand"])
    name_tokens = tokens(product["name_en"])
    if brand_tokens and not any(token in off_tokens for token in brand_tokens):
        return False
    distinctive = [token for token in name_tokens if token not in brand_tokens]
    shared = [token for token in distinctive if token in off_tokens]
    if shared:
        return True
    if brand_tokens and any(token in off_tokens for token in name_tokens):
        return True
    return not brand_tokens and len(set(name_tokens) & off_tokens) >= 2


def lookup_codes(barcode: str) -> list[str]:
    codes = list(get_barcode_lookup_variants(barcode))
    if len(barcode) == 14 and barcode.isdigit():
        codes.extend(get_barcode_lookup_variants(ean13_from_gtin14(barcode)))
    return list(dict.fromkeys(codes))


def fetch_product(barcode: str) -> dict | None:
    for code in lookup_codes(barcode):
        url = (
            "https://world.openfoodfacts.org/api/v2/product/"
            f"{code}.json?fields=code,product_name,brands,image_front_url,image_ingredients_url,image_nutrition_url"
        )
        request = urllib.request.Request(url, headers={"User-Agent": AGENT})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
        if payload.get("status") != 1:
            continue
        return payload.get("product") or {}
    return None


def download(url: str) -> Image.Image | None:
    if not url:
        return None
    full = re.sub(r"\.\d+\.jpg$", ".full.jpg", url, flags=re.IGNORECASE)
    for candidate in dict.fromkeys([full, url]):
        request = urllib.request.Request(candidate, headers={"User-Agent": AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                image = Image.open(BytesIO(response.read())).convert("RGB")
        except Exception:
            continue
        if min(image.size) >= 200:
            return image
    return None


def main() -> None:
    products = load_ground_truth(EXCEL_SOURCE)
    by_code: dict[str, dict] = {}
    for product in products:
        by_code.setdefault(product["barcode"], product)
    have = {path.stem.replace("_front", "") for path in (TAGGED / "front").glob("*_front.jpg")}
    missing = [by_code[code] for code in by_code if code not in have]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
    both = front_only = rejected = absent = no_image = 0
    print(f"check {len(missing)}", flush=True)
    for index, product in enumerate(missing, 1):
        remote = fetch_product(product["barcode"])
        if remote is None:
            absent += 1
            continue
        off_name = str(remote.get("product_name") or "")
        off_brand = str(remote.get("brands") or "")
        if not names_agree(product, off_name, off_brand):
            rejected += 1
            print(f"  skip {product['barcode']} excel={product['name_en'][:42]!r} off={off_name[:42]!r}", flush=True)
            continue
        front_image = download(str(remote.get("image_front_url") or ""))
        back_image = download(str(remote.get("image_ingredients_url") or "")) or download(
            str(remote.get("image_nutrition_url") or "")
        )
        if front_image is None:
            no_image += 1
            print(f"  no photo {product['barcode']} {off_name[:48]}", flush=True)
            continue
        front = packshot_front(front_image)
        front_path = TAGGED / "front" / f"{product['barcode']}_front.jpg"
        front_path.parent.mkdir(parents=True, exist_ok=True)
        front.save(front_path, format="JPEG", quality=95, subsampling=0)
        back_path = ""
        back_size = ""
        if back_image is not None:
            back = enhance_back(back_image)
            dest = TAGGED / "back" / f"{product['barcode']}_back.jpg"
            save_image_high_quality(back, dest, quality=95, save_webp=False)
            back_path = str(dest)
            back_size = f"{back.size[0]}x{back.size[1]}"
            both += 1
        else:
            front_only += 1
        manifest[product["barcode"]] = {
            "mode": "web",
            "rotation": 0,
            "source": str(remote.get("image_front_url") or ""),
            "back_path": back_path,
            "back_ok": bool(back_path),
            "back_size": back_size,
            "front_path": str(front_path),
            "front_ok": True,
            "front_size": f"{front.size[0]}x{front.size[1]}",
            "note": f"Open Food Facts name match ({off_brand}; {off_name}).",
            "barcode": product["barcode"],
            "ok": True,
        }
        print(f"  saved {product['barcode']} back={bool(back_path)} {product['name_en'][:48]}", flush=True)
        if index % 25 == 0:
            print(f"  checked {index}/{len(missing)}", flush=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print(
        f"done both {both} front_only {front_only} name_rejected {rejected} not_found {absent} record_without_photo {no_image}",
        flush=True,
    )


if __name__ == "__main__":
    main()
