from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from .barcode_validator import validate_ean_upc_checksum


class PackagingVisionResult(BaseModel):
    # 1. Identification & Names
    barcode: str | None = Field(default=None, description="Exact barcode digits printed on package.")
    product_name: str | None = Field(default="", description="Product title fallback.")
    literal_label_name: str | None = Field(default="", description="Tên nguyên văn trên nhãn.")
    full_name_en: str | None = Field(default="", description="Standardized English commercial full title (Brand + Variant + Name + Net Weight).")
    fuldt_navn_da: str | None = Field(default="", description="Danish translated commercial product title.")
    brand: str | None = Field(default="", description="Brand or manufacturer name visible on the product.")
    record_id: str | None = Field(default="", description="Sequential Record ID, e.g. G1-0001.")
    barcode_check_status: str | None = Field(default="Đúng checksum; đọc từ ảnh", description="Barcode verification status note.")
    name_source_notes: str | None = Field(default="Tên đầy đủ EN/DA chuẩn hóa từ nhãn; bản DA là bản dịch biên tập.", description="Translation or source notes.")
    variant: str | None = Field(default="", description="Flavor, variant, or taste (e.g. Wasabi, Soy Sauce, Original).")
    category: str | None = Field(default="Grocery", description="Editorial category (Snacks, Noodles, Sauces, Drinks, Condiments, etc.).")
    packaging: str | None = Field(default="Bag", description="Packaging format (Bag, Bottle, Box, Can, Resealable bag, etc.).")
    net_quantity: float | None = Field(default=None, description="Numeric net weight/volume value (e.g. 110.0, 500.0).")
    net_unit: str | None = Field(default="g", description="Net quantity unit (g, ml, kg, L, oz).")
    net_weight: str | None = Field(default="", description="Net weight string fallback.")
    unit_count: float | None = Field(default=None, description="Number of inner units/packs if multipack (e.g. 6).")
    barcode_text_read: str | None = Field(default="", description="Raw barcode text read from photo.")
    supplier_sku: str | None = Field(default="", description="Explicit supplier SKU printed on label.")
    other_printed_codes: str | None = Field(default="", description="FDA numbers, registration numbers, batch format codes.")

    # 2. Manufacturer & Supply Chain
    manufacturer: str | None = Field(default="", description="Manufacturer company name.")
    manufacturer_address: str | None = Field(default="", description="Manufacturer full postal address.")
    country_of_origin: str | None = Field(default="", description="Country of origin (e.g. Thailand, Vietnam, Japan, China).")
    origin_label_evidence: str | None = Field(default="", description="Literal text proof on packaging (e.g. PRODUCT OF THAILAND).")
    importer: str | None = Field(default="", description="EU/local importer company name (e.g. Asia Express Food, Beagley Copperman).")
    importer_address: str | None = Field(default="", description="Importer postal address.")
    distributor: str | None = Field(default="", description="Distributor entity if separate.")

    # 3. Ingredients & Localization
    ingredients_label_language: str | None = Field(default="", description="Raw ingredients text with language prefix (e.g. EN: WHEAT flour...).")
    ingredients_en: str | None = Field(default="", description="Full English ingredients list.")
    ingredienser_da: str | None = Field(default="", description="Full Danish (DA) translated ingredients list.")
    ingredient_translation_notes: str | None = Field(default="", description="Notes on ingredient source or translation.")

    # 4. Allergens & Warnings
    allergens_label: str | None = Field(default="", description="Literal allergen statement on label.")
    allergens_en: str | None = Field(default="", description="EU 14 major allergens in English.")
    allergener_da: str | None = Field(default="", description="EU 14 major allergens in Danish.")
    may_contain_label: str | None = Field(default="", description="Traces or cross-contamination statement (May contain...).")

    # 5. Nutrition Facts (per 100g / 100ml)
    nutrition_basis: str | None = Field(default="per 100 g", description="Basis of nutrition panel (per 100 g / per 100 ml).")
    energy_kj: float | None = Field(default=None, description="Energy in kJ.")
    energy_kcal: float | None = Field(default=None, description="Energy in kcal.")
    fat_g: float | None = Field(default=None, description="Total fat in grams.")
    saturates_g: float | None = Field(default=None, description="Saturated fatty acids in grams.")
    carbohydrate_g: float | None = Field(default=None, description="Total carbohydrates in grams.")
    sugars_g: float | None = Field(default=None, description="Total sugars in grams.")
    fibre_g: float | None = Field(default=None, description="Dietary fibre in grams.")
    protein_g: float | None = Field(default=None, description="Protein in grams.")
    salt_g: float | None = Field(default=None, description="Salt / sodium equivalent in grams.")
    other_nutrition_source: str | None = Field(default="", description="Other nutrition data or alternative serving panel details.")

    # 6. Usage, Storage & Compliance
    preparation_label: str | None = Field(default="", description="Preparation instructions on label.")
    preparation_en: str | None = Field(default="", description="Preparation instructions in English.")
    tilberedning_da: str | None = Field(default="", description="Preparation instructions in Danish.")
    storage_label: str | None = Field(default="", description="Storage instructions on packaging.")
    storage_en: str | None = Field(default="", description="Storage instructions in English.")
    opbevaring_da: str | None = Field(default="", description="Storage instructions in Danish.")
    warnings_label: str | None = Field(default="", description="Regulatory warnings (e.g. azo dyes E102 activity in children).")
    claims_certifications: str | None = Field(default="", description="Certifications and claims (Halal, Vegan, Non-GMO).")
    alcohol_vol: float | None = Field(default=None, description="Alcohol percentage (% vol) if applicable.")
    manufacture_date: str | None = Field(default="", description="Printed manufacture date (MFG).")
    best_before_expiry: str | None = Field(default="", description="Printed expiry / best before date (BBE/EXP).")
    lot_batch: str | None = Field(default="", description="Printed lot / batch code.")
    website_contact: str | None = Field(default="", description="Website URLs, emails, customer service numbers.")
    other_legible_info: str | None = Field(default="", description="Other legible text facts.")

    # 7. Coordinates & Cropping
    front_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] coordinates (0-1000) of ONLY the FRONT packaging view.")
    back_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] coordinates (0-1000) of the BACK packaging view.")
    barcode_box_2d: list[int] | None = Field(default=None, description="[ymin, xmin, ymax, xmax] coordinates (0-1000) of the BARCODE on the package.")
    front_rotation: int = 0
    back_rotation: int = 0
    confidence: float = Field(default=1.0)


PROMPT_LAYOUT_DETECTION = """
Analyze this packaging photo showing FRONT and BACK sides of an imported grocery item.
Return strictly valid JSON with coordinates [ymin, xmin, ymax, xmax] (0-1000) and clockwise rotation needed (0, 90, 180, or 270 degrees) to make each side upright and readable:
{
  "front_box_2d": [ymin, xmin, ymax, xmax],
  "front_rotation_to_upright": 0,
  "back_box_2d": [ymin, xmin, ymax, xmax],
  "back_rotation_to_upright": 0,
  "barcode_box_2d": [ymin, xmin, ymax, xmax]
}
"""

PROMPT_FRONT_INSPECTION = """
Inspect this high-resolution FRONT packaging photo of an imported grocery item.
Extract facts strictly visible on packaging in JSON:
{
  "brand": "string",
  "literal_label_name": "exact main product title as printed on front packaging",
  "full_name_en": "Standardized commercial English title: Brand + Variant + Product Name + Net Weight (e.g. Lotus Dorkbua Original Stick Biscuits 110 g)",
  "fuldt_navn_da": "Commercial Danish translated product title (e.g. Lotus Dorkbua originale kiksstænger 110 g)",
  "variant": "Flavor or variant distinction (e.g. Original, Wasabi, Seaweed)",
  "category": "Snacks, Noodles, Sauces, Condiments, Drinks, Canned, Rice & Grains, etc.",
  "packaging": "Bag, Box, Bottle, Can, Resealable bag, etc.",
  "net_quantity": number or null (e.g. 110.0),
  "net_unit": "g, ml, kg, L, oz",
  "unit_count": number or null (if multipack, e.g. 6)
}
"""

PROMPT_BACK_INSPECTION = """
Inspect this high-resolution BACK packaging / Nutrition & Importer label of an imported food item under EU Regulation 1169/2011.
Extract facts strictly visible on the packaging into valid JSON:
{
  "ingredients_label_language": "string with original language indicator",
  "ingredients_en": "Full English ingredients list",
  "ingredienser_da": "Full Danish translated ingredients list",
  "allergens_label": "Literal allergen text on package",
  "allergens_en": "EU major allergens in English",
  "allergener_da": "EU major allergens in Danish",
  "may_contain_label": "May contain traces statement",
  "nutrition_basis": "per 100 g or per 100 ml",
  "energy_kj": number or null,
  "energy_kcal": number or null,
  "fat_g": number or null,
  "saturates_g": number or null,
  "carbohydrate_g": number or null,
  "sugars_g": number or null,
  "fibre_g": number or null,
  "protein_g": number or null,
  "salt_g": number or null,
  "other_nutrition_source": "string",
  "country_of_origin": "Country name (e.g. Thailand, Vietnam, Japan, China, Korea)",
  "origin_label_evidence": "Literal origin text (e.g. PRODUCT OF THAILAND)",
  "manufacturer": "Manufacturer company name",
  "manufacturer_address": "Manufacturer postal address",
  "importer": "EU importer company name (e.g. Asia Express Food, Beagley Copperman, Heuschen & Schrouff)",
  "importer_address": "Importer address",
  "distributor": "Distributor name if any",
  "storage_en": "Storage instructions in English",
  "opbevaring_da": "Storage instructions in Danish",
  "preparation_en": "Preparation instructions in English",
  "tilberedning_da": "Preparation instructions in Danish",
  "warnings_label": "Warning statements (e.g. E102 activity in children)",
  "claims_certifications": "Halal, Vegan, Non-GMO, Gluten-Free",
  "alcohol_vol": number or null,
  "manufacture_date": "Printed MFG date",
  "best_before_expiry": "Printed BBE / Expiry date",
  "lot_batch": "Printed lot / batch code",
  "website_contact": "URLs, emails, phones on label"
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
        self.lock = threading.Lock()
        raw_keys = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        self.keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        for k, v in os.environ.items():
            if k.startswith("GEMINI_API_KEY_") or k.startswith("GOOGLE_API_KEY_"):
                if v.strip() and v.strip() not in self.keys:
                    self.keys.append(v.strip())

        if api_key and api_key.strip() not in self.keys:
            self.keys.append(api_key.strip())

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
        with self.lock:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(self.cache_path, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _get_client(self):
        with self.lock:
            if not self.keys:
                raise ValueError("No valid GEMINI_API_KEY available.")
            key = self.keys[self._key_index % len(self.keys)]
            self._key_index += 1
            if key not in self._clients:
                from google import genai
                self._clients[key] = genai.Client(api_key=key, http_options={"timeout": 60000})
            return self._clients[key], key

    def _mark_key_failed(self, key: str, reason: str = ""):
        with self.lock:
            print(f"Warning: Disabling Gemini key {key[:8]}... due to: {reason}")
            if key in self.keys:
                self.keys.remove(key)
            if key in self._clients:
                del self._clients[key]

    def _call_gemini_json(self, img_bytes: bytes, prompt: str, retry_count: int = 3) -> dict[str, Any]:
        models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview"]
        for m in models_to_try:
            for attempt in range(retry_count):
                if not self.keys:
                    return {}
                client, used_key = self._get_client()
                try:
                    from google.genai import types

                    response = client.models.generate_content(
                        model=m,
                        contents=[
                            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                            prompt,
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
                    return parsed if isinstance(parsed, dict) else {}
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
        return {}

    def analyze_image_deep(self, image_path: Path, force_fresh: bool = False) -> PackagingVisionResult:
        """Runs the 3-Stage Multi-Crop High-Resolution Vision Pipeline with Thread Safety."""
        fname = image_path.name
        if not force_fresh and fname in self.cache:
            data = self.cache[fname]
            if data.get("full_name_en") and (data.get("energy_kcal") is not None or data.get("ingredients_en")):
                return PackagingVisionResult(**data)

        from ..ingestion.image_loader import open_image_safely

        orig_im = open_image_safely(image_path)
        w, h = orig_im.size

        # Stage 1: Layout & Orientation Detection
        buf_low = io.BytesIO()
        orig_im.resize((1200, int(1200 * h / w))).save(buf_low, format="JPEG", quality=85)
        layout = self._call_gemini_json(buf_low.getvalue(), PROMPT_LAYOUT_DETECTION)

        def _norm_box(b: Any) -> list[int] | None:
            if not b:
                return None
            if isinstance(b, list):
                if len(b) > 0 and isinstance(b[0], list):
                    b = b[0]
                if len(b) == 4:
                    try:
                        return [int(round(float(x))) for x in b]
                    except Exception:
                        return None
            return None

        front_box = _norm_box(layout.get("front_box_2d"))
        back_box = _norm_box(layout.get("back_box_2d"))
        barcode_box = _norm_box(layout.get("barcode_box_2d"))
        rot_f = int(layout.get("front_rotation_to_upright", 0) or 0)
        rot_b = int(layout.get("back_rotation_to_upright", 0) or 0)

        front_dict: dict[str, Any] = {}
        back_dict: dict[str, Any] = {}

        # Stage 2: High-Resolution Front Inspection with 3-5% adaptive padding
        if front_box and len(front_box) == 4:
            ymin, xmin, ymax, xmax = front_box
            pad_w = int((xmax - xmin) * 0.04)
            pad_h = int((ymax - ymin) * 0.04)
            left = max(0, int((xmin - pad_w) * w / 1000))
            top = max(0, int((ymin - pad_h) * h / 1000))
            right = min(w, int((xmax + pad_w) * w / 1000))
            bottom = min(h, int((ymax + pad_h) * h / 1000))
            if right > left and bottom > top:
                crop_front = orig_im.crop((left, top, right, bottom))
                if rot_f != 0:
                    crop_front = crop_front.rotate(-rot_f, expand=True)
                buf_f = io.BytesIO()
                crop_front.save(buf_f, format="JPEG", quality=92)
                front_dict = self._call_gemini_json(buf_f.getvalue(), PROMPT_FRONT_INSPECTION)

        # Stage 3: High-Resolution Back Inspection
        if back_box and len(back_box) == 4:
            ymin, xmin, ymax, xmax = back_box
            pad_w = int((xmax - xmin) * 0.03)
            pad_h = int((ymax - ymin) * 0.03)
            left = max(0, int((xmin - pad_w) * w / 1000))
            top = max(0, int((ymin - pad_h) * h / 1000))
            right = min(w, int((xmax + pad_w) * w / 1000))
            bottom = min(h, int((ymax + pad_h) * h / 1000))
            if right > left and bottom > top:
                crop_back = orig_im.crop((left, top, right, bottom))
                if rot_b != 0:
                    crop_back = crop_back.rotate(-rot_b, expand=True)
                crop_back_enh = ImageEnhance.Contrast(crop_back).enhance(1.15)
                buf_b = io.BytesIO()
                crop_back_enh.save(buf_b, format="JPEG", quality=92)
                back_dict = self._call_gemini_json(buf_b.getvalue(), PROMPT_BACK_INSPECTION)

        # Merge results and sanitize None values for strings
        merged = {**back_dict, **front_dict}
        merged["front_box_2d"] = front_box
        merged["back_box_2d"] = back_box
        merged["barcode_box_2d"] = barcode_box
        merged["front_rotation"] = rot_f
        merged["back_rotation"] = rot_b
        merged["product_name"] = merged.get("full_name_en") or merged.get("literal_label_name") or ""

        numeric_or_list_keys = {
            "energy_kj", "energy_kcal", "fat_g", "saturates_g", "carbohydrate_g",
            "sugars_g", "fibre_g", "protein_g", "salt_g", "alcohol_vol", "net_quantity",
            "unit_count", "front_box_2d", "back_box_2d", "barcode_box_2d", "front_rotation",
            "back_rotation", "confidence"
        }
        clean_merged = {}
        for k, v in merged.items():
            if v is None and k not in numeric_or_list_keys:
                clean_merged[k] = ""
            else:
                clean_merged[k] = v

        res = PackagingVisionResult(**clean_merged)
        with self.lock:
            self.cache[fname] = res.model_dump()
        self._save_cache()
        return res

    def read_zoomed_barcode(self, crop_image: Image.Image, retry_count: int = 2) -> str | None:
        """Reads barcode digits from a high-resolution zoomed crop with strict checksum verification."""
        buf = BytesIO()
        crop_image.convert("RGB").save(buf, format="JPEG", quality=95)
        crop_bytes = buf.getvalue()

        parsed = self._call_gemini_json(crop_bytes, PROMPT_ZOOM_BARCODE, retry_count=retry_count)
        raw_digits = parsed.get("barcode_digits")
        if raw_digits:
            cleaned = re.sub(r"[^\d]", "", str(raw_digits))
            if validate_ean_upc_checksum(cleaned):
                return cleaned
        return None
