from __future__ import annotations

import base64
import json
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from .barcode_validator import validate_ean_upc_checksum


class PackagingVisionResult(BaseModel):
    barcode: str | None = Field(default=None, description="Exact barcode digits on package if visible.")
    brand: str = Field(default="", description="Brand or manufacturer name visible on the product.")
    product_name: str = Field(default="", description="Original product title/name in original packaging language/English.")
    net_weight: str = Field(default="", description="Net weight, volume, or pack size (e.g., 50g, 100ml, 12x20g).")
    variant: str = Field(default="", description="Flavor, variant, or taste (e.g. Spicy, Wasabi, Seaweed, Original).")
    packaging_type: str = Field(default="", description="Bag, Can, Bottle, Box, etc.")
    front_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] coordinates (0-1000) of ONLY the FRONT packaging view.")
    barcode_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] coordinates (0-1000) of the BARCODE on the package.")
    confidence: float = Field(default=1.0)


PROMPT_PACKAGING = """
You are an expert product cataloger inspecting an imported grocery packaging photograph.
Both the FRONT and BACK sides of the product are displayed in this photo.
CRITICAL RULE: Extract ONLY text and facts strictly visible on the packaging. Never invent, hallucinate, or guess.

Analyze the photograph carefully:
1. brand: The brand or manufacturer name printed on the packaging (e.g. Orion, Khao Shong, VFOODS, Want Want, Hengshun, Kingzest, Cock Brand, etc.). Look closely at logos at the top or corners.
2. product_name: The prominent product title printed on the front packaging. If multilingual, include the primary English / Latin title or the prominent native title.
3. net_weight: Net weight or volume (e.g. '180g', '50g', '200ml', '227g / 8 oz').
4. variant: Flavor, taste, or style distinction (e.g. 'Wasabi', 'Soy Sauce', 'Seaweed', 'Sushi Vinegar').
5. packaging_type: 'Bag', 'Box', 'Bottle', 'Can', 'Tub', etc.
6. barcode: The exact numeric digits of the barcode printed on the package (or null if not clearly legible from full view).
7. front_box_2d: The 4 bounding box coordinates [ymin, xmin, ymax, xmax] (normalized from 0 to 1000) enclosing ONLY the FRONT packaging face of the product for an e-commerce website.
8. barcode_box_2d: The 4 bounding box coordinates [ymin, xmin, ymax, xmax] (normalized from 0 to 1000) enclosing the BARCODE area (the vertical stripes + numbers below it).

Return strictly valid JSON:
{
  "brand": "string",
  "product_name": "string",
  "net_weight": "string",
  "variant": "string",
  "packaging_type": "string",
  "barcode": "string or null",
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "barcode_box_2d": [ymin, xmin, ymax, xmax]
}
"""

PROMPT_ZOOM_BARCODE = """
This is a zoomed crop of a barcode on a product package.
Transcribe the EXACT numeric digits printed directly below the barcode stripes.
CRITICAL: Do NOT guess any digits. If any digit is unclear, return null.
Return strictly JSON:
{
  "barcode_digits": "exact digits (8, 12, 13, or 14 digits) or null"
}
"""


class GeminiVisionExtractor:
    def __init__(self, api_key: str | None = None, cache_path: Path | None = None):
        raw_keys = os.environ.get("GEMINI_API_KEYS", "")
        self.keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        if not self.keys:
            single = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if single:
                self.keys = [single.strip()]
        self._key_index = 0
        self.cache_path = cache_path or Path("output/g1_vision_cache.json")
        self.cache: dict[str, Any] = {}
        self._load_cache()
        self._clients: dict[str, Any] = {}

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _get_client(self):
        if not self.keys:
            raise ValueError("No valid GEMINI_API_KEY available.")
        key = self.keys[self._key_index % len(self.keys)]
        self._key_index += 1
        if key not in self._clients:
            from google import genai
            self._clients[key] = genai.Client(api_key=key, http_options={"timeout": 60000})
        return self._clients[key], key

    def _mark_key_failed(self, key: str, reason: str = ""):
        print(f"Warning: Disabling Gemini key {key[:8]}... due to: {reason}")
        if key in self.keys:
            self.keys.remove(key)
        if key in self._clients:
            del self._clients[key]

    def _prepare_image_bytes(self, image_path: Path, max_size: int = 1400) -> bytes:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            if max(w, h) > max_size:
                ratio = max_size / max(w, h)
                im = im.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=88)
            return buf.getvalue()

    def analyze_image(self, image_path: Path, retry_count: int = 3, force_fresh: bool = False) -> PackagingVisionResult:
        fname = image_path.name
        if not force_fresh and fname in self.cache:
            data = self.cache[fname]
            if "front_box_2d" in data and data.get("product_name"):
                return PackagingVisionResult(**data)

        img_bytes = self._prepare_image_bytes(image_path)
        models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview"]

        for m in models_to_try:
            for attempt in range(retry_count):
                if not self.keys:
                    print("All Gemini API keys exhausted.")
                    return PackagingVisionResult()
                client, used_key = self._get_client()
                try:
                    from google.genai import types

                    response = client.models.generate_content(
                        model=m,
                        contents=[
                            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                            PROMPT_PACKAGING,
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                        ),
                    )
                    raw_text = response.text or "{}"
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        parsed = parsed[0]
                    res = PackagingVisionResult(**parsed)
                    self.cache[fname] = res.model_dump()
                    self._save_cache()
                    return res
                except Exception as e:
                    err_str = str(e)
                    if "GenerateRequestsPerDay" in err_str or "PERMISSION_DENIED" in err_str:
                        self._mark_key_failed(used_key, err_str[:60])
                    elif "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                        time.sleep(2.0 * (attempt + 1))
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        break
                    else:
                        time.sleep(1.0)
        return PackagingVisionResult()

    def read_zoomed_barcode(self, crop_image: Image.Image, retry_count: int = 2) -> str | None:
        """Reads barcode digits from a high-resolution zoomed crop with strict checksum verification."""
        buf = BytesIO()
        crop_image.convert("RGB").save(buf, format="JPEG", quality=95)
        crop_bytes = buf.getvalue()

        models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview"]
        for m in models_to_try:
            for attempt in range(retry_count):
                if not self.keys:
                    return None
                client, used_key = self._get_client()
                try:
                    from google.genai import types

                    res = client.models.generate_content(
                        model=m,
                        contents=[
                            types.Part.from_bytes(data=crop_bytes, mime_type="image/jpeg"),
                            PROMPT_ZOOM_BARCODE,
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.0,
                        ),
                    )
                    parsed = json.loads(res.text or "{}")
                    raw_digits = parsed.get("barcode_digits")
                    if raw_digits:
                        cleaned = re.sub(r"[^\d]", "", str(raw_digits))
                        # Strict checksum verification: only accept mathematically valid barcodes
                        if validate_ean_upc_checksum(cleaned):
                            return cleaned
                    return None
                except Exception as e:
                    err_str = str(e)
                    if "GenerateRequestsPerDay" in err_str or "PERMISSION_DENIED" in err_str:
                        self._mark_key_failed(used_key, err_str[:60])
                    time.sleep(1.5)
        return None

