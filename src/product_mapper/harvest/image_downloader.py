"""
Candidate Image Downloader and Pre-Filter Pipeline.
Validates HTTP response, image decodability, resolution (>= 600px), and valid format.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple
from PIL import Image
import requests

logger = logging.getLogger(__name__)


class ImageDownloaderAndFilter:
    """Safely downloads and validates candidates against resolution and format thresholds."""

    ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

    def __init__(self, min_dim: int = 600, timeout: float = 12.0, session: Optional[requests.Session] = None):
        self.min_dim = min_dim
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        })

    def download_and_validate(self, url: str) -> Tuple[Optional[Image.Image], Optional[bytes], str]:
        """
        Downloads image from URL and validates format and minimum dimension.
        Returns: (PIL.Image or None, raw_bytes or None, reason_message)
        """
        clean_url = str(url or "").strip()
        if not clean_url or not clean_url.startswith("http"):
            return None, None, "Invalid URL"

        try:
            resp = self.session.get(clean_url, timeout=self.timeout)
            if resp.status_code != 200:
                return None, None, f"HTTP Error {resp.status_code}"

            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type and not any(ext in content_type for ext in ["image", "octet-stream", "jpeg", "png", "webp"]):
                return None, None, f"Invalid Content-Type: {content_type}"

            raw_bytes = resp.content
            if len(raw_bytes) < 500:  # Image smaller than 500 bytes is likely empty or tracking pixel
                return None, None, f"Payload too small: {len(raw_bytes)} bytes"

            img = Image.open(io.BytesIO(raw_bytes))
            img_format = img.format.upper() if img.format else ""

            if img_format not in self.ALLOWED_FORMATS:
                return None, None, f"Unsupported format: {img_format}"

            w, h = img.size
            if w < self.min_dim and h < self.min_dim:
                return None, None, f"Resolution too low ({w}x{h} < {self.min_dim}px)"

            return img, raw_bytes, "OK"

        except Exception as e:
            return None, None, f"Download failed: {e}"
