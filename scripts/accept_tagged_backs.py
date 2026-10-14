"""Accept clean tagged backs, keep one file per barcode, and list reshoots.

Processed photos are written only into tagged/back. Images that already pass
are recorded in back_accepted.json so a later repair does not overwrite them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from openpyxl import Workbook
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from barcode_first_pipeline import EXCEL_SOURCE, load_ground_truth, truth_lookup  # noqa: E402
from fix_tagged_backs import PROTECTED, keep_back_panel, rotate_upright  # noqa: E402
from product_mapper.vision.barcode_side_splitter import enhance_back  # noqa: E402
from product_mapper.vision.barcode_validator import get_barcode_lookup_variants  # noqa: E402
from repair_catalog_backs import barcode_matches, download_off, fetch_json, folder_from_manifest  # noqa: E402

BACK_DIR = ROOT / "output/catalog_pairs/tagged/back"
MANIFEST = ROOT / "output/catalog_pairs/manifest.json"
ACCEPTED_PATH = ROOT / "output/catalog_pairs/back_accepted.json"
RESHOOT_PATH = ROOT / "output/catalog_pairs/khach_chup_lai_mat_sau.xlsx"

# Visually checked: this turn stands the package so the label reads upright.
TURNS = {
    "0634158960055": 270,
    "3379140063228": 90,
    "3447573606227": 270,
    "4045198762428": 90,
    "4045198925724": 270,
    "4045198963504": 270,
    "4806011822688": 270,
    "6920802311347": 270,
    "6924187845909": 270,
    "8716789008176": 90,
    "8717624008221": 270,
    "8720663434142": 270,
    "8801043022699": 270,
    "8801043157735": 270,
    "8801043157759": 270,
    "8850987193026": 270,
    "8852018800279": 270,
}
STRIP_CODES = {"8720301109388", "8851011113263"}
# The can label is upright. The vertical word on the left is printed that way.
VISUALLY_OK = {"8850035051001"}

VERIFIED = PROTECTED | {
    "050561846326",
    "074261041218",
    "857451000314",
    "3447573606029",
    "4045198908734",
    "8850931040307",
    "8936014313398",
    "011747616041",
    "044738210690",
    "084909006257",
    "5011308307062",
    "8801043018470",
    "8935024143353",
    "8852646244544",
    "4045198925922",
    "8850035081329",
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


def canonical(code: str, lookup: dict[str, str]) -> str:
    if code in lookup:
        return lookup[code]
    for variant in get_barcode_lookup_variants(code):
        if variant in lookup:
            return lookup[variant]
    return code


def assess(path: Path) -> dict:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    probe = image.copy()
    probe.thumbnail((480, 480))
    rgb = np.asarray(probe)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    content = ~((rgb.min(axis=2) > 236) & (spread < 18))
    coverage = float(content.mean())
    frame = content.size
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(content.astype(np.uint8), 8)
    blobs = []
    for index in range(1, count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < frame * 0.04:
            continue
        blobs.append(
            (
                area / frame,
                int(stats[index, cv2.CC_STAT_LEFT]),
                int(stats[index, cv2.CC_STAT_TOP]),
                int(stats[index, cv2.CC_STAT_WIDTH]),
                int(stats[index, cv2.CC_STAT_HEIGHT]),
            )
        )
    blobs.sort(reverse=True)
    vertical = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    horizontal = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    energy = vertical + horizontal
    strong = content & (energy > np.percentile(energy, 55))
    if int(strong.sum()) < 40:
        strong = content
    text = float(vertical[strong].mean()) / max(float(horizontal[strong].mean()), 1.0) if int(strong.sum()) else 1.0
    sharp = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    reasons: list[str] = []
    if coverage < 0.10:
        reasons.append("tiny")
    if min(width, height) < 400:
        reasons.append("small-file")
    if len(blobs) >= 2 and blobs[1][0] >= 0.12:
        left, right = blobs[0], blobs[1]
        apart_x = left[1] > right[1] + right[3] or right[1] > left[1] + left[3]
        apart_y = left[2] > right[2] + right[4] or right[2] > left[2] + left[4]
        if apart_x or apart_y:
            reasons.append("two-packs")
    if text >= 1.45 and width > height * 1.15:
        reasons.append("sideways")
    score = sharp + coverage * 80 + min(width, height) / 20
    score -= 400 * len(reasons)
    if path.stem.replace("_back", "") in VERIFIED:
        score += 5000
    return {
        "path": path,
        "code": path.stem.replace("_back", ""),
        "size": (width, height),
        "bytes": path.stat().st_size,
        "coverage": round(coverage, 3),
        "text": round(text, 2),
        "sharp": round(sharp, 1),
        "reasons": reasons,
        "score": score,
    }


def save_back(image: Image.Image, path: Path) -> None:
    image.save(path, format="JPEG", quality=95, subsampling=0)
    webp = path.with_suffix(".webp")
    if webp.exists():
        webp.unlink()


def full_web_back(barcode: str, manifest: dict) -> Image.Image | None:
    row = manifest.get(barcode) or {}
    folder = folder_from_manifest(row)
    product = fetch_json(barcode)
    if product is None or not folder:
        return None
    images = product.get("images") or {}
    ranked: list[tuple[int, str]] = []
    for key, value in images.items():
        if not key.isdigit() or not isinstance(value, dict):
            continue
        sizes = (value.get("sizes") or {}).get("full") or {}
        width = int(sizes.get("w") or 0)
        height = int(sizes.get("h") or 0)
        if min(width, height) < 500:
            continue
        if max(width, height) / max(1, min(width, height)) > 2.6:
            continue
        ranked.append((width * height, key))
    ranked.sort(reverse=True)
    for _area, image_id in ranked[:6]:
        image = download_off(folder, image_id)
        if image is None:
            continue
        if min(image.size) < 500 or max(image.size) / max(1, min(image.size)) > 2.6:
            continue
        if barcode_matches(image, barcode):
            return image
    return None


def apply_fixes(manifest: dict) -> list[str]:
    locked: set[str] = set()
    if ACCEPTED_PATH.is_file():
        stored = json.loads(ACCEPTED_PATH.read_text(encoding="utf-8"))
        locked = {code for code, row in stored.items() if isinstance(row, dict) and row.get("locked")}
    changed: list[str] = []
    for code, ccw in TURNS.items():
        if code in locked:
            continue
        path = BACK_DIR / f"{code}_back.jpg"
        with Image.open(path) as opened:
            image = opened.convert("RGB")
        turned = rotate_upright(image, ccw)
        if code == "8801043157735":
            width, height = turned.size
            turned = turned.crop((int(width * 0.36), 0, width, height))
        save_back(turned, path)
        changed.append(code)
        print(f"turn {code} rot{ccw} {turned.size[0]}x{turned.size[1]}", flush=True)

    if "8720165077120" not in locked:
        sausage_path = BACK_DIR / "8720165077120_back.jpg"
        with Image.open(sausage_path) as opened:
            sausage = opened.convert("RGB")
        panel = keep_back_panel(sausage, "8720165077120")
        if panel.size != sausage.size and min(panel.size) >= 400:
            save_back(panel, sausage_path)
            changed.append("8720165077120")
            print(f"panel 8720165077120 {panel.size[0]}x{panel.size[1]}", flush=True)

    if "8850035051001" not in locked:
        can_path = BACK_DIR / "8850035051001_back.jpg"
        with Image.open(can_path) as opened:
            cans = opened.convert("RGB")
        width, height = cans.size
        can = cans.crop((0, int(height * 0.50), int(width * 0.58), height))
        save_back(can, can_path)
        changed.append("8850035051001")
        print(f"can 8850035051001 {can.size[0]}x{can.size[1]}", flush=True)

    for code in sorted(STRIP_CODES):
        if code in locked:
            continue
        path = BACK_DIR / f"{code}_back.jpg"
        downloaded = full_web_back(code, manifest)
        if downloaded is None:
            print(f"strip {code} no matching web photo", flush=True)
            continue
        back = enhance_back(downloaded)
        save_back(back, path)
        changed.append(code)
        print(f"web {code} {back.size[0]}x{back.size[1]}", flush=True)
    return changed


def main() -> None:
    apply = "--apply" in sys.argv
    products = load_ground_truth(EXCEL_SOURCE)
    lookup = truth_lookup(products)
    by_excel = {product["barcode"]: product for product in products}
    rows = [assess(path) for path in sorted(BACK_DIR.glob("*_back.jpg"))]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(canonical(row["code"], lookup), []).append(row)
    duplicates = {code: items for code, items in groups.items() if len(items) > 1}
    present = set(groups)
    missing = [product for product in products if product["barcode"] not in present]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
    reshoot = []
    for product in missing:
        record = manifest.get(product["barcode"], {})
        if record.get("mode") == "web" and record.get("back_ok"):
            continue
        reshoot.append(product)
    flagged = [row for row in rows if row["reasons"] and row["code"] not in VERIFIED]
    print(
        f"backs {len(rows)} excel {len(by_excel)} matched {len(present & set(by_excel))} "
        f"duplicates {len(duplicates)} flagged {len(flagged)} reshoot {len(reshoot)}",
        flush=True,
    )
    for code, items in sorted(duplicates.items()):
        ranked = sorted(items, key=lambda item: item["score"], reverse=True)
        print(
            "dup",
            code,
            "keep",
            ranked[0]["code"],
            [(item["code"], item["size"], item["reasons"]) for item in ranked],
            flush=True,
        )
    if not apply:
        return

    removed = 0
    for code, items in duplicates.items():
        ranked = sorted(items, key=lambda item: item["score"], reverse=True)
        keeper = ranked[0]
        dest = BACK_DIR / f"{code}_back.jpg"
        if keeper["path"] != dest:
            with Image.open(keeper["path"]) as opened:
                image = opened.convert("RGB")
            save_back(image, dest)
        for item in ranked[1:]:
            if item["path"] != dest and item["path"].exists():
                item["path"].unlink()
                removed += 1
        if keeper["path"] != dest and keeper["path"].exists():
            keeper["path"].unlink()
            removed += 1

    changed = apply_fixes(manifest)
    for code in changed:
        path = BACK_DIR / f"{code}_back.jpg"
        with Image.open(path) as opened:
            size = opened.size
        record = manifest.get(code)
        if isinstance(record, dict):
            record["back_size"] = f"{size[0]}x{size[1]}"
            record["back_ok"] = True
            if code in TURNS:
                record["rotation"] = TURNS[code]
            record["note"] = "kept the single upright back"
    if changed:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, separators=(", ", ": ")), encoding="utf-8")

    accepted: dict[str, dict] = {}
    still_flagged = []
    for path in sorted(BACK_DIR.glob("*_back.jpg")):
        row = assess(path)
        if row["code"] in STRIP_CODES and row["reasons"]:
            still_flagged.append(row)
            continue
        if row["code"] in VERIFIED or row["code"] in VISUALLY_OK or not row["reasons"]:
            accepted[row["code"]] = {
                "locked": True,
                "size": f"{row['size'][0]}x{row['size'][1]}",
                "reasons": row["reasons"],
            }
        elif row["reasons"]:
            still_flagged.append(row)
    ACCEPTED_PATH.write_text(json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8")

    strip_left = {row["code"] for row in still_flagged if row["code"] in STRIP_CODES}
    for code in sorted(strip_left):
        product = by_excel.get(code)
        if product is None or any(item["barcode"] == code for item in reshoot):
            continue
        reshoot.append(product)

    book = Workbook()
    sheet = book.active
    sheet.title = "Chup lai mat sau"
    sheet.append(["Barcode", "Ten tieng Anh", "Ten tieng Dan Mach", "Thuong hieu", "Ly do"])
    for product in reshoot:
        reason = "Khong co anh mat sau trong kho va khong co anh mang da doi chieu"
        if product["barcode"] in strip_left:
            reason = "Chi con dai chu tren nhan, khong doc duoc barcode va khong co anh mang khop ma"
        sheet.append(
            [
                product["barcode"],
                product["name_en"],
                product["name_da"],
                product["brand"],
                reason,
            ]
        )
    book.save(RESHOOT_PATH)
    preview = ROOT / "output/catalog_pairs/_orient_preview"
    if preview.exists():
        for thumb in preview.glob("*.jpg"):
            thumb.unlink()
        preview.rmdir()
    print(
        f"removed_duplicates {removed} turned {len(changed)} locked {len(accepted)} "
        f"still_flagged {len(still_flagged)} reshoot {len(reshoot)}",
        flush=True,
    )
    for row in still_flagged:
        print(f"open {row['code']} {row['size']} {row['reasons']}", flush=True)


if __name__ == "__main__":
    main()
