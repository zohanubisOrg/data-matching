"""Sanitizer module for raw image discovery, EXIF orientation, and format normalization."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageOps
import pillow_heif

# Register HEIC / HEIF opener for Apple iOS photography
pillow_heif.register_heif_opener()

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


@dataclass
class RawPhotoRecord:
    path: Path
    filename: str
    partition: str
    file_size: int
    fingerprint: str
    width: int
    height: int


class ImageSanitizer:
    """Discovers and normalizes raw photography from source folders."""

    PARTITION_MAPPING = {
        "G1_original": "G1",
        "G2_original": "G2",
        "G3_Original": "G3",
        "G4-original": "G4",
        "Nyt25.09.26": "Nyt",
    }

    def __init__(self, source_roots: Optional[List[Path]] = None):
        if source_roots is None:
            base_dir = Path("source-import")
            self.source_roots = [
                base_dir / "G1_original",
                base_dir / "G2_original",
                base_dir / "G3_Original",
                base_dir / "G4-original",
                base_dir / "Nyt25.09.26",
            ]
        else:
            self.source_roots = source_roots

    @staticmethod
    def calculate_fingerprint(file_path: Path) -> str:
        """Fast fingerprint using file size and first 64KB hash to prevent duplicate files instantly."""
        stat = file_path.stat()
        hasher = hashlib.md5()
        hasher.update(str(stat.st_size).encode())
        with open(file_path, "rb") as f:
            chunk = f.read(65536)
            hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def load_normalized_image(file_path: Path) -> Image.Image:
        """Load an image, apply EXIF auto-orientation, and convert to 8-bit RGB."""
        img = Image.open(file_path)
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img

    @staticmethod
    def create_preview(img: Image.Image, max_dim: int = 512) -> Image.Image:
        """Create a lightweight thumbnail preview for Pass 1 fast screening."""
        preview = img.copy()
        preview.thumbnail((max_dim, max_dim), Image.Resampling.BILINEAR)
        return preview

    def discover_raw_photos(self) -> Dict[str, List[RawPhotoRecord]]:
        """Scan source folders and index all valid raw photos by partition in sub-second time."""
        discovered: Dict[str, List[RawPhotoRecord]] = {
            "G1": [],
            "G2": [],
            "G3": [],
            "G4": [],
            "Nyt": [],
        }
        seen_fingerprints = set()

        for folder in self.source_roots:
            if not folder.exists():
                continue
            partition = self.PARTITION_MAPPING.get(folder.name, "OTHER")
            if partition not in discovered:
                discovered[partition] = []

            for entry in sorted(folder.iterdir()):
                if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                    file_size = entry.stat().st_size
                    if file_size < 1024:
                        continue

                    # Fast fingerprint
                    fp = self.calculate_fingerprint(entry)
                    if fp in seen_fingerprints:
                        continue
                    seen_fingerprints.add(fp)

                    try:
                        with Image.open(entry) as probe:
                            width, height = probe.size
                            # Check orientation tag if available
                            exif = probe.getexif() if hasattr(probe, "getexif") else None
                            orientation = exif.get(274, 1) if exif else 1
                            if orientation in (6, 8):
                                width, height = height, width
                    except Exception:
                        continue

                    record = RawPhotoRecord(
                        path=entry.resolve(),
                        filename=entry.name,
                        partition=partition,
                        file_size=file_size,
                        fingerprint=fp,
                        width=width,
                        height=height,
                    )
                    discovered[partition].append(record)

        return discovered
