import hashlib
from collections import Counter
from pathlib import Path

from PIL import Image

from ..models import DataQualityIssue, ProductImage
from ..parsing.filename_parser import parse_filename


def load_images(directories: list[Path]) -> tuple[list[ProductImage], list[DataQualityIssue], dict]:
    results, issues, hashes = [], [], Counter()
    for directory in directories:
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}: continue
            try:
                with Image.open(path) as image: image.verify()
                hashes[hashlib.sha256(path.read_bytes()).hexdigest()] += 1
                results.append(parse_filename(path))
            except Exception as exc:
                issues.append(DataQualityIssue(issue_type="invalid image or filename", value=str(path), details=str(exc)))
    for digest, count in hashes.items():
        if count > 1: issues.append(DataQualityIssue(issue_type="duplicate image content", value=digest, count=count))
    all_files = [p for d in directories for p in d.rglob("*") if p.is_file()]
    parse_failures = sum(i.issue_type == "invalid image or filename" for i in issues)
    return results, issues, {"total": len(results), "directories": {d.name: sum(1 for x in results if d in x.path.parents) for d in directories}, "extensions": dict(Counter(p.suffix.casefold() for p in all_files)), "sources": dict(Counter(x.source for x in results)), "parse_success": len(results), "parse_failures": parse_failures}
