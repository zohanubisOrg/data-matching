from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from ..models import DataQualityIssue, ProductImage
from ..parsing.filename_parser import parse_filename

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"
}


def open_image_safely(path: str | Path) -> Image.Image:
    """
    Opens an image file safely handling JPEG, PNG, WEBP, and HEIC formats,
    applying EXIF orientation transposition if present.
    """
    path = Path(path)
    img = Image.open(path)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def save_image_high_quality(
    img: Image.Image,
    output_path: str | Path,
    quality: int = 95,
    save_webp: bool = True,
) -> Path:
    """
    Saves image at native sensor resolution with high quality.
    Optionally generates a parallel .webp asset.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_path.suffix.casefold() in {".jpg", ".jpeg"}:
        img.save(output_path, format="JPEG", quality=quality, subsampling=0)
    elif output_path.suffix.casefold() == ".webp":
        img.save(output_path, format="WEBP", quality=quality, method=6)
    else:
        img.save(output_path)

    if save_webp and output_path.suffix.casefold() != ".webp":
        webp_path = output_path.with_suffix(".webp")
        img.save(webp_path, format="WEBP", quality=quality, method=6)

    return output_path


def load_images(directories: list[Path]) -> tuple[list[ProductImage], list[DataQualityIssue], dict]:
    results, issues, hashes = [], [], Counter()
    for directory in directories:
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                with Image.open(path) as image:
                    image.verify()
                hashes[hashlib.sha256(path.read_bytes()).hexdigest()] += 1
                results.append(parse_filename(path))
            except Exception as exc:
                issues.append(DataQualityIssue(issue_type="invalid image or filename", value=str(path), details=str(exc)))
    for digest, count in hashes.items():
        if count > 1:
            issues.append(DataQualityIssue(issue_type="duplicate image content", value=digest, count=count))
    all_files = [p for d in directories for p in d.rglob("*") if p.is_file()]
    parse_failures = sum(i.issue_type == "invalid image or filename" for i in issues)
    return (
        results,
        issues,
        {
            "total": len(results),
            "directories": {d.name: sum(1 for x in results if d in x.path.parents) for d in directories},
            "extensions": dict(Counter(p.suffix.casefold() for p in all_files)),
            "sources": dict(Counter(x.source for x in results)),
            "parse_success": len(results),
            "parse_failures": parse_failures,
        },
    )

