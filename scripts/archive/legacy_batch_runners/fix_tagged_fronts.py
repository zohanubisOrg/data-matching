"""Replace a tagged front that is only a package edge with the sales face from the original photo."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from audit_tagged_fronts import content_mask  # noqa: E402
from product_mapper.ingestion.image_loader import open_image_safely, save_image_high_quality  # noqa: E402
from repair_held_fronts import _accepted, _rotate_if_lying, deliver, sales_face  # noqa: E402

FRONT_DIR = ROOT / "output/catalog_pairs/tagged/front"
ORIG_DIR = ROOT / "output/catalog_pairs/originals"
PREVIEW = ROOT / "output/catalog_pairs/_front_fix_preview"
BACKUP = ROOT / "output/catalog_pairs/_front_before_pair_fix"
AUDIT = ROOT / "output/catalog_pairs/_front_audit.json"
MANIFEST = ROOT / "output/catalog_pairs/manifest.json"
ALREADY = {
    "4316734091365",
    "8801005000185",
    "8852052000055",
    "8851613101392",
}

SEVERE = [
    "4316734091365",
    "5027324001181",
    "6954132815688",
    "788821122124",
    "8716789016089",
    "8720663432667",
    "8801005000185",
    "8850060110049",
    "8850060110063",
    "8850643068132",
    "8851613101392",
    "8852052000055",
    "8853095006134",
    "8857118730082",
]


def _original(code: str) -> Path | None:
    folder = ORIG_DIR / code
    if not folder.exists():
        return None
    files = [path for path in folder.iterdir() if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_size)


def choose_sales_face(image: Image.Image, code: str) -> Image.Image | None:
    """One sales face. The seam has to be empty table, and a barcode on the brand face stays."""
    face, _reason = sales_face(image, code)
    return face


def _content_width(image: Image.Image) -> float:
    small = image.copy()
    small.thumbnail((480, 480))
    arr = np.asarray(small.convert("RGB"))
    ink = ~((arr.min(axis=2) > 236) & ((arr.max(axis=2) - arr.min(axis=2)) < 18))
    columns = ink.any(axis=0)
    if not columns.any():
        return 0.0
    indexes = np.flatnonzero(columns)
    return float(indexes[-1] - indexes[0] + 1) / columns.size


def _finish(face: Image.Image, code: str) -> tuple[Image.Image | None, str]:
    del code
    turned, ccw = _rotate_if_lying(face)
    shot = deliver(turned)
    if not _accepted(shot):
        return None, "rejected"
    reason = f"face+rot{ccw}" if ccw else "face"
    return shot, reason


def repair_front(code: str) -> tuple[Image.Image | None, str]:
    source = _original(code)
    if source is None:
        return None, "no-original"
    image = open_image_safely(source).convert("RGB")
    face = choose_sales_face(image, code)
    if face is None:
        return None, "no-split"
    return _finish(face, code)


def _targets() -> list[dict]:
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    chosen = []
    for row in data["flagged"]:
        code = row["code"]
        if code in ALREADY:
            continue
        width = row["box"][2]
        reasons = row["reasons"]
        pair = "two-packs" in reasons
        sliver = width < 0.28 and (row["text"] >= 1.28 or width < 0.20 or "strip" in reasons)
        if pair or sliver:
            chosen.append(row)
    return chosen


def _note_manifest(updates: dict[str, tuple[int, int]]) -> None:
    if not updates:
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for code, size in updates.items():
        entry = manifest.get(code)
        if not isinstance(entry, dict):
            continue
        entry["front_size"] = f"{size[0]}x{size[1]}"
        entry["front_ok"] = True
        entry["note"] = "Replaced the edge or pair crop with the upright sales face."
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    apply = "--apply" in sys.argv
    extra = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if extra:
        rows = [{"code": code, "box": [0, 0, 0, 0], "reasons": []} for code in extra]
    elif "--from-audit" in sys.argv:
        rows = _targets()
    else:
        rows = [{"code": code, "box": [0, 0, 0, 0], "reasons": []} for code in SEVERE]
    PREVIEW.mkdir(parents=True, exist_ok=True)
    updates: dict[str, tuple[int, int]] = {}
    for row in rows:
        code = row["code"]
        old_width = float(row["box"][2]) if row["box"][2] else 0.0
        fixed, reason = repair_front(code)
        new_width = _content_width(fixed) if fixed is not None else 0.0
        pair = "two-packs" in row["reasons"]
        wider = new_width >= max(0.30, old_width * 1.45) if old_width else new_width >= 0.30
        # A taller existing bottle is already the full package. A shorter result is only the neck.
        old_file = FRONT_DIR / f"{code}_front.jpg"
        shorter = False
        if fixed is not None and old_file.exists() and old_width:
            previous = Image.open(old_file).convert("RGB")
            previous.thumbnail((480, 480))
            rows_mask = content_mask(np.asarray(previous))
            ys = np.where(rows_mask)[0]
            old_height = float(ys[-1] - ys[0] + 1) / rows_mask.shape[0] if len(ys) else 0.0
            current = fixed.copy()
            current.thumbnail((480, 480))
            rows_mask = content_mask(np.asarray(current))
            ys = np.where(rows_mask)[0]
            new_height = float(ys[-1] - ys[0] + 1) / rows_mask.shape[0] if len(ys) else 0.0
            shorter = old_height > 0.55 and new_height < old_height * 0.72
        keep = fixed is not None and not shorter and (pair or wider or not extra and "--from-audit" not in sys.argv)
        print(
            code,
            reason,
            f"{old_width:.2f}->{new_width:.2f}",
            "SAVE" if keep and apply else ("ok" if keep else "skip"),
            flush=True,
        )
        if fixed is None or not keep:
            continue
        thumb = fixed.copy()
        thumb.thumbnail((800, 800))
        thumb.save(PREVIEW / f"{code}.jpg", quality=85)
        if apply:
            dest = FRONT_DIR / f"{code}_front.jpg"
            BACKUP.mkdir(parents=True, exist_ok=True)
            if dest.exists() and not (BACKUP / dest.name).exists():
                shutil.copy2(dest, BACKUP / dest.name)
            save_image_high_quality(fixed, dest, quality=95, save_webp=False)
            updates[code] = fixed.size
    _note_manifest(updates)
    print("saved", len(updates), flush=True)


if __name__ == "__main__":
    main()
