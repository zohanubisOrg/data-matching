import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from ..models import DataQualityIssue, ProductImage
from ..parsing.filename_parser import parse_filename

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _duplicate_content_issues(paths_by_size: dict[int, list[Path]]) -> list[DataQualityIssue]:
    """Hash only same-size files; exact byte duplicates must have identical size."""
    hashes: Counter[str] = Counter()
    for paths in paths_by_size.values():
        if len(paths) < 2:
            continue
        for path in paths:
            hashes[_sha256_file(path)] += 1
    return [
        DataQualityIssue(issue_type="duplicate image content", value=digest, count=count)
        for digest, count in hashes.items()
        if count > 1
    ]


def load_images(directories: list[Path]) -> tuple[list[ProductImage], list[DataQualityIssue], dict]:
    results: list[ProductImage] = []
    issues: list[DataQualityIssue] = []
    filenames: Counter[str] = Counter()
    extensions: Counter[str] = Counter()
    image_paths_by_size: dict[int, list[Path]] = defaultdict(list)

    for directory in directories:
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.casefold()
            if suffix not in _IMAGE_SUFFIXES:
                continue
            extensions[suffix] += 1
            try:
                with Image.open(path) as image:
                    image.verify()
                image_paths_by_size[path.stat().st_size].append(path)
                filenames[path.name.casefold()] += 1
                results.append(parse_filename(path))
            except Exception as exc:
                issues.append(
                    DataQualityIssue(
                        issue_type="invalid image or filename",
                        value=str(path),
                        details=str(exc),
                    )
                )

    issues.extend(_duplicate_content_issues(image_paths_by_size))

    for filename, count in filenames.items():
        if count > 1:
            issues.append(
                DataQualityIssue(
                    issue_type="duplicate image filename",
                    field="filename",
                    value=filename,
                    count=count,
                    details="Knowledge-base decisions keyed only by filename are unsafe for duplicate names.",
                )
            )

    parse_failures = sum(issue.issue_type == "invalid image or filename" for issue in issues)
    return results, issues, {
        "total": len(results),
        "directories": {
            directory.name: sum(1 for image in results if directory in image.path.parents)
            for directory in directories
        },
        "extensions": dict(extensions),
        "sources": dict(Counter(image.source for image in results)),
        "parse_success": len(results),
        "parse_failures": parse_failures,
        "duplicate_filenames": sum(1 for count in filenames.values() if count > 1),
        "duplicate_hash_candidates": sum(len(paths) for paths in image_paths_by_size.values() if len(paths) > 1),
    }
