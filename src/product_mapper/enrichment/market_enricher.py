from __future__ import annotations

import json
import os
import re
import ssl
import urllib.request
from pathlib import Path
from typing import Any


class MarketCatalogEnricher:
    """Enriches product metadata (Nutrition Facts, Ingredients, Origin, Brand, Allergens)

    by querying global barcode databases (OpenFoodFacts API) and local cached catalogs.
    """

    def __init__(self, cache_file: Path | None = None):
        self.cache_file = cache_file or Path("output/g1_delivery/market_enrichment_cache.json")
        self.cache: dict[str, dict[str, Any]] = {}
        self._load_cache()

        # SSL context
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def _load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def lookup_barcode(self, barcode: str, timeout: int = 4) -> dict[str, Any]:
        """Queries OpenFoodFacts global catalog for detailed nutrition facts and specifications."""
        clean_bc = re.sub(r"[^\d]", "", str(barcode).strip())
        if not clean_bc or len(clean_bc) < 8 or clean_bc.startswith("NO_BARCODE"):
            return {}

        if clean_bc in self.cache:
            return self.cache[clean_bc]

        url = f"https://world.openfoodfacts.org/api/v2/product/{clean_bc}.json"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ShopifyPOSMapper/2.0 (food-catalog-audit)"},
        )

        result: dict[str, Any] = {}
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == 1 or "product" in data:
                    p = data.get("product", {})
                    nutriments = p.get("nutriments", {})

                    def to_float(val: Any) -> float | None:
                        if val is None or val == "":
                            return None
                        try:
                            return float(val)
                        except Exception:
                            return None

                    # Extract nutrition facts per 100g
                    energy_kcal = to_float(nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal") or nutriments.get("energy-kcal_value"))
                    energy_kj = to_float(nutriments.get("energy-kj_100g") or nutriments.get("energy-kj") or nutriments.get("energy_100g"))
                    fat_g = to_float(nutriments.get("fat_100g") or nutriments.get("fat"))
                    saturates_g = to_float(nutriments.get("saturated-fat_100g") or nutriments.get("saturated-fat"))
                    carbs_g = to_float(nutriments.get("carbohydrates_100g") or nutriments.get("carbohydrates"))
                    sugars_g = to_float(nutriments.get("sugars_100g") or nutriments.get("sugars"))
                    fibre_g = to_float(nutriments.get("fiber_100g") or nutriments.get("fiber"))
                    protein_g = to_float(nutriments.get("proteins_100g") or nutriments.get("proteins"))
                    salt_g = to_float(nutriments.get("salt_100g") or nutriments.get("salt") or (to_float(nutriments.get("sodium_100g")) * 2.5 if nutriments.get("sodium_100g") else None))
                    alcohol_vol = to_float(nutriments.get("alcohol_100g") or nutriments.get("alcohol"))

                    result = {
                        "barcode": clean_bc,
                        "product_name_en": p.get("product_name_en") or p.get("product_name") or "",
                        "brands": p.get("brands") or "",
                        "generic_name": p.get("generic_name_en") or p.get("generic_name") or "",
                        "categories": p.get("categories") or "",
                        "quantity": p.get("quantity") or "",
                        "packaging": p.get("packaging") or "",
                        "origin": p.get("origins") or p.get("countries") or "",
                        "manufacturer": p.get("manufacturing_places") or "",
                        "ingredients_en": p.get("ingredients_text_en") or p.get("ingredients_text") or "",
                        "allergens_en": p.get("allergens") or p.get("allergens_from_ingredients") or "",
                        "energy_kj": energy_kj,
                        "energy_kcal": energy_kcal,
                        "fat_g": fat_g,
                        "saturates_g": saturates_g,
                        "carbohydrate_g": carbs_g,
                        "sugars_g": sugars_g,
                        "fibre_g": fibre_g,
                        "protein_g": protein_g,
                        "salt_g": salt_g,
                        "alcohol_vol": alcohol_vol,
                    }
        except Exception:
            result = {}

        self.cache[clean_bc] = result
        self._save_cache()
        return result

    def enrich_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Fills in missing or empty fields in a product record using market catalog data."""
        bc = record.get("barcode", "")
        if not bc or str(bc).startswith("NO_BARCODE"):
            return record

        market_data = self.lookup_barcode(bc)
        if not market_data:
            return record

        # 1. Fill nutrition facts if missing
        if record.get("energy_kcal") is None and market_data.get("energy_kcal") is not None:
            record["energy_kcal"] = market_data["energy_kcal"]
        if record.get("energy_kj") is None and market_data.get("energy_kj") is not None:
            record["energy_kj"] = market_data["energy_kj"]
        if record.get("fat_g") is None and market_data.get("fat_g") is not None:
            record["fat_g"] = market_data["fat_g"]
        if record.get("saturates_g") is None and market_data.get("saturates_g") is not None:
            record["saturates_g"] = market_data["saturates_g"]
        if record.get("carbohydrate_g") is None and market_data.get("carbohydrate_g") is not None:
            record["carbohydrate_g"] = market_data["carbohydrate_g"]
        if record.get("sugars_g") is None and market_data.get("sugars_g") is not None:
            record["sugars_g"] = market_data["sugars_g"]
        if record.get("fibre_g") is None and market_data.get("fibre_g") is not None:
            record["fibre_g"] = market_data["fibre_g"]
        if record.get("protein_g") is None and market_data.get("protein_g") is not None:
            record["protein_g"] = market_data["protein_g"]
        if record.get("salt_g") is None and market_data.get("salt_g") is not None:
            record["salt_g"] = market_data["salt_g"]
        if record.get("alcohol_vol") is None and market_data.get("alcohol_vol") is not None:
            record["alcohol_vol"] = market_data["alcohol_vol"]

        # 2. Fill ingredients & allergens if empty
        if not record.get("ingredients_en") and market_data.get("ingredients_en"):
            record["ingredients_en"] = market_data["ingredients_en"]
        if not record.get("allergens_en") and market_data.get("allergens_en"):
            record["allergens_en"] = market_data["allergens_en"]

        # 3. Fill origin & manufacturer if empty
        if not record.get("country_of_origin") and market_data.get("origin"):
            record["country_of_origin"] = market_data["origin"]
        if not record.get("manufacturer") and market_data.get("manufacturer"):
            record["manufacturer"] = market_data["manufacturer"]

        # 4. Fill brand if empty
        if not record.get("brand") and market_data.get("brands"):
            record["brand"] = market_data["brands"]

        return record
