"""
Google Images Deep Harvester for extracting original high-resolution packshot URLs.
Parses embedded JavaScript payloads while ignoring low-resolution gstatic thumbnails.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class HarvestedCandidate:
    url: str
    source: str
    width: Optional[int] = None
    height: Optional[int] = None


class GoogleImagesHarvester:
    """Extracts original full-resolution image URLs from Google Images search results."""

    SEARCH_BASE = "https://www.google.com/search?tbm=isch&tbs=isz:l&hl=en&q={query}"
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    ]

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        min_dim: int = 600,
        rate_limit_delay: tuple[float, float] = (1.0, 2.5),
        session: Optional[requests.Session] = None,
    ):
        self.cache_dir = cache_dir or Path("output/shopify-zohanubis-image/.cache/google_images")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_dim = min_dim
        self.rate_limit_delay = rate_limit_delay
        self.session = session or requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,da;q=0.8",
            "Referer": "https://www.google.com/",
        }

    def _cache_path(self, query: str) -> Path:
        safe_key = re.sub(r"[^\w\-_\.]", "_", query)[:64]
        return self.cache_dir / f"{safe_key}.json"

    def parse_image_urls_from_html(self, html_text: str) -> List[HarvestedCandidate]:
        """Extracts full-resolution image URLs from Google Images HTML/JS payload."""
        candidates: List[HarvestedCandidate] = []
        seen_urls = set()

        # Pattern 1: JSON array ["url", width, height] commonly found in Google Image data chunks
        pattern_json = re.compile(
            r'\["(https?://[^"]+?\.(?:jpg|jpeg|png|webp))",\s*(\d+),\s*(\d+)\]',
            re.IGNORECASE,
        )
        for match in pattern_json.finditer(html_text):
            img_url, w_str, h_str = match.groups()
            if self._is_valid_url(img_url, seen_urls):
                try:
                    w, h = int(w_str), int(h_str)
                    if w >= self.min_dim or h >= self.min_dim:
                        candidates.append(
                            HarvestedCandidate(
                                url=img_url,
                                source="Google_Images_DeepPayload",
                                width=w,
                                height=h,
                            )
                        )
                        seen_urls.add(img_url)
                except Exception:
                    pass

        # Pattern 2: Fallback URL search ignoring Google internal domains
        pattern_raw = re.compile(
            r'https?://[a-zA-Z0-9_\-\./]+?\.(?:jpg|jpeg|png|webp)',
            re.IGNORECASE,
        )
        for url in pattern_raw.findall(html_text):
            if self._is_valid_url(url, seen_urls):
                candidates.append(
                    HarvestedCandidate(
                        url=url,
                        source="Google_Images_Fallback",
                    )
                )
                seen_urls.add(url)

        return candidates

    def _is_valid_url(self, url: str, seen: set) -> bool:
        if url in seen:
            return False
        # Filter out Google internal / thumbnail CDNs
        disallowed = [
            "gstatic.com",
            "google.com",
            "googleusercontent.com",
            "wikimedia.org",
            "wikipedia.org",
            "schema.org",
        ]
        low = url.lower()
        if any(d in low for d in disallowed):
            return False
        return True

    def search_candidates(self, query: str, limit: int = 5, use_cache: bool = True) -> List[HarvestedCandidate]:
        """Searches Google Images and returns verified candidate image records."""
        clean_query = query.strip()
        if not clean_query:
            return []

        cpath = self._cache_path(clean_query)
        if use_cache and cpath.exists():
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [
                        HarvestedCandidate(
                            url=item["url"],
                            source=item["source"],
                            width=item.get("width"),
                            height=item.get("height"),
                        )
                        for item in data
                    ]
            except Exception:
                pass

        # Apply rate limiting delay
        delay = random.uniform(self.rate_limit_delay[0], self.rate_limit_delay[1])
        time.sleep(delay)

        encoded_q = urllib.parse.quote_plus(clean_query)
        search_url = self.SEARCH_BASE.format(query=encoded_q)

        try:
            resp = self.session.get(search_url, headers=self._get_headers(), timeout=10.0)
            if resp.status_code == 200:
                candidates = self.parse_image_urls_from_html(resp.text)[:limit]
                # Save cache
                try:
                    payload = [
                        {"url": c.url, "source": c.source, "width": c.width, "height": c.height}
                        for c in candidates
                    ]
                    with open(cpath, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2)
                except Exception:
                    pass
                return candidates
            else:
                logger.warning(f"Google Images returned HTTP {resp.status_code} for query: {clean_query}")
        except Exception as e:
            logger.debug(f"Google Images request failed for '{clean_query}': {e}")

        return []
