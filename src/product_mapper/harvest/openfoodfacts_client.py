"""
OpenFoodFacts REST API Client for retrieving canonical product packshot imagery by EAN/UPC barcode.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)


class OpenFoodFactsClient:
    """Client for querying the OpenFoodFacts V2 Product API."""

    BASE_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
    USER_AGENT = "RabutaEcomPackshotBot/1.0 (contact@rabuta.dk)"

    def __init__(
        self,
        timeout: float = 8.0,
        cache_dir: Optional[Path] = None,
        session: Optional[requests.Session] = None,
    ):
        self.timeout = timeout
        self.cache_dir = cache_dir or Path("output/shopify-zohanubis-image/.cache/openfoodfacts")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self._last_request_time = 0.0

    def _upgrade_to_full_res(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        # Replace .400.jpg, .200.jpg with .full.jpg
        return re.sub(r"\.\d+\.jpg$", ".full.jpg", url)

    def fetch_product_data(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Queries OpenFoodFacts for product JSON metadata with local disk cache."""
        clean_bc = str(barcode or "").strip()
        if not clean_bc:
            return None

        cache_file = self.cache_dir / f"{clean_bc}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Polite rate limiting (1.0 second between external calls)
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        url = self.BASE_URL.format(barcode=clean_bc)
        try:
            self._last_request_time = time.time()
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("status") == 1:
                    product = payload.get("product", {})
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(product, f, indent=2)
                    except Exception:
                        pass
                    return product
            elif resp.status_code == 404:
                return None
            elif resp.status_code == 429:
                logger.warning(f"OpenFoodFacts rate limited for barcode {clean_bc}. Backing off.")
                time.sleep(3.0)
            else:
                logger.warning(f"OpenFoodFacts API returned status {resp.status_code} for barcode {clean_bc}")
        except Exception as e:
            logger.debug(f"OpenFoodFacts request failed for {clean_bc}: {e}")
        return None

    def get_front_packshot_url(self, barcode: str) -> Optional[str]:
        """Resolves the best available front packshot image URL for a barcode."""
        product = self.fetch_product_data(barcode)
        if not product:
            return None

        # 1. Primary explicit front image URL
        front_url = product.get("image_front_url")
        if front_url and front_url.startswith("http"):
            return self._upgrade_to_full_res(front_url)

        # 2. Selected front display language variations
        selected_front = (
            product.get("selected_images", {})
            .get("front", {})
            .get("display", {})
        )
        if isinstance(selected_front, dict):
            for lang in ["en", "da", "de", "fr", "vi", "th", "ja", "ko", "zh"]:
                candidate = selected_front.get(lang)
                if candidate and candidate.startswith("http"):
                    return self._upgrade_to_full_res(candidate)
            # Pick any language if preferred languages not present
            for candidate in selected_front.values():
                if candidate and isinstance(candidate, str) and candidate.startswith("http"):
                    return self._upgrade_to_full_res(candidate)

        # 3. Fallback generic product image URL
        img_url = product.get("image_url")
        if img_url and img_url.startswith("http"):
            return self._upgrade_to_full_res(img_url)

        return None
