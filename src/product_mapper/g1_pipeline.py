from __future__ import annotations

import glob
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from .vision.barcode_validator import get_barcode_lookup_variants, validate_ean_upc_checksum
from .vision.gemini_vision import GeminiVisionExtractor, PackagingVisionResult


class G1ProductItem(BaseModel):
    # 1. Identification & Names
    barcode: str = ""
    literal_label_name: str = ""
    full_name_en: str = ""
    fuldt_navn_da: str = ""
    brand: str = ""
    record_id: str = ""
    barcode_check_status: str = "Đúng checksum; đọc từ ảnh"
    name_source_notes: str = "Tên đầy đủ EN/DA chuẩn hóa từ nhãn; bản DA là bản dịch biên tập."
    variant: str = ""
    category: str = "Grocery"
    packaging: str = "Bag"
    net_quantity: float | None = None
    net_unit: str = "g"
    unit_count: float | None = None
    barcode_text_read: str = ""
    supplier_sku: str = ""
    other_printed_codes: str = ""

    # 2. Manufacturer & Supply Chain
    manufacturer: str = ""
    manufacturer_address: str = ""
    country_of_origin: str = ""
    origin_label_evidence: str = ""
    importer: str = ""
    importer_address: str = ""
    distributor: str = ""

    # 3. Ingredients & Localization
    ingredients_label_language: str = ""
    ingredients_en: str = ""
    ingredienser_da: str = ""
    ingredient_translation_notes: str = ""

    # 4. Allergens & Warnings
    allergens_label: str = ""
    allergens_en: str = ""
    allergener_da: str = ""
    may_contain_label: str = ""

    # 5. Nutrition Facts (per 100g / 100ml)
    nutrition_basis: str = "per 100 g"
    energy_kj: float | None = None
    energy_kcal: float | None = None
    fat_g: float | None = None
    saturates_g: float | None = None
    carbohydrate_g: float | None = None
    sugars_g: float | None = None
    fibre_g: float | None = None
    protein_g: float | None = None
    salt_g: float | None = None
    other_nutrition_source: str = ""

    # 6. Usage, Storage & Compliance
    preparation_label: str = ""
    preparation_en: str = ""
    tilberedning_da: str = ""
    storage_label: str = ""
    storage_en: str = ""
    opbevaring_da: str = ""
    warnings_label: str = ""
    claims_certifications: str = ""
    alcohol_vol: float | None = None
    manufacture_date: str = ""
    best_before_expiry: str = ""
    lot_batch: str = ""
    website_contact: str = ""
    other_legible_info: str = ""

    # 7. Media & Cropping
    source_photo_filenames: str = ""
    selected_front_source: str = ""
    front_photo_limitations: str = ""
    front_photo_relative_filename: str = ""
    image_width_px: int = 0
    image_height_px: int = 0
    dong_nguon_anh_mat_truoc: str = ""
    anh_mat_truoc: str = ""

    # Additional Internal & POS Reconciliation fields
    pos_sku: str = ""
    pos_product_name: str = ""
    front_box_2d: list[int] = Field(default_factory=list)
    detection_method: str = "zxing_direct"
    status: str = "CONFIRMED"


COLUMNS_65_MAPPING = [
    ("Barcode", "barcode"),
    ("Tên nguyên văn trên nhãn", "literal_label_name"),
    ("Full name (EN)", "full_name_en"),
    ("Fuldt navn (DA)", "fuldt_navn_da"),
    ("Brand", "brand"),
    ("Record ID", "record_id"),
    ("Kiểm tra barcode", "barcode_check_status"),
    ("Nguồn tên / ghi chú bản dịch", "name_source_notes"),
    ("Variant / flavour", "variant"),
    ("Category (editorial)", "category"),
    ("Packaging", "packaging"),
    ("Net quantity", "net_quantity"),
    ("Net unit", "net_unit"),
    ("Unit count", "unit_count"),
    ("Barcode text read from photo", "barcode_text_read"),
    ("Supplier SKU (explicit only)", "supplier_sku"),
    ("Other printed codes", "other_printed_codes"),
    ("Manufacturer", "manufacturer"),
    ("Manufacturer address", "manufacturer_address"),
    ("Country of origin", "country_of_origin"),
    ("Origin label evidence", "origin_label_evidence"),
    ("Importer", "importer"),
    ("Importer address", "importer_address"),
    ("Distributor", "distributor"),
    ("Ingredients (label / language)", "ingredients_label_language"),
    ("Ingredients (EN)", "ingredients_en"),
    ("Ingredienser (DA)", "ingredienser_da"),
    ("Ingredient translation / completeness", "ingredient_translation_notes"),
    ("Allergens (label)", "allergens_label"),
    ("Allergens (EN)", "allergens_en"),
    ("Allergener (DA)", "allergener_da"),
    ("May contain (label)", "may_contain_label"),
    ("Nutrition basis / preparation state", "nutrition_basis"),
    ("Energy (kJ)", "energy_kj"),
    ("Energy (kcal)", "energy_kcal"),
    ("Fat (g)", "fat_g"),
    ("Saturates (g)", "saturates_g"),
    ("Carbohydrate (g)", "carbohydrate_g"),
    ("Sugars (g)", "sugars_g"),
    ("Fibre (g)", "fibre_g"),
    ("Protein (g)", "protein_g"),
    ("Salt (g)", "salt_g"),
    ("Other nutrition / units / source", "other_nutrition_source"),
    ("Preparation (label)", "preparation_label"),
    ("Preparation (EN)", "preparation_en"),
    ("Tilberedning (DA)", "tilberedning_da"),
    ("Storage (label)", "storage_label"),
    ("Storage (EN)", "storage_en"),
    ("Opbevaring (DA)", "opbevaring_da"),
    ("Warnings (label)", "warnings_label"),
    ("Claims / certification marks", "claims_certifications"),
    ("Alcohol (% vol)", "alcohol_vol"),
    ("Manufacture date (printed)", "manufacture_date"),
    ("Best before / expiry (printed)", "best_before_expiry"),
    ("Lot / batch (printed)", "lot_batch"),
    ("Website / contact on label", "website_contact"),
    ("Other legible label information", "other_legible_info"),
    ("Source photo filenames", "source_photo_filenames"),
    ("Selected front source", "selected_front_source"),
    ("Front photo limitations", "front_photo_limitations"),
    ("Front photo relative filename", "front_photo_relative_filename"),
    ("Image width (px)", "image_width_px"),
    ("Image height (px)", "image_height_px"),
    ("Dòng nguồn ảnh mặt trước", "dong_nguon_anh_mat_truoc"),
    ("Ảnh mặt trước", "anh_mat_truoc"),
]


class G1BatchPipeline:
    def __init__(
        self,
        images_dir: Path = Path("G1_original"),
        output_dir: Path = Path("output/g1_delivery"),
        pos_file: Path = Path("Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx"),
        api_key: str | None = None,
    ):
        self.images_dir = images_dir
        self.output_dir = output_dir
        self.website_images_dir = output_dir / "website_front_images"
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.vision = GeminiVisionExtractor(api_key=self.api_key, cache_path=output_dir / "g1_vision_cache.json")
        self.barcode_cache_file = output_dir / "g1_barcodes_cache.json"

        # POS Lookup with leading-zero variants normalization
        self.pos_lookup: dict[str, dict[str, str]] = {}
        if pos_file.exists():
            try:
                df = pd.read_excel(pos_file)
                df["Bar Code"] = df["Bar Code"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
                for _, r in df.iterrows():
                    bc = str(r["Bar Code"]).strip()
                    if bc and bc != "nan":
                        info = {
                            "sku": str(r.get("Sku Code", "")).strip(),
                            "name": str(r.get("Product Name ", "")).strip(),
                            "official_name": str(r.get("Oficial Name ", "")).strip(),
                        }
                        for var in get_barcode_lookup_variants(bc):
                            self.pos_lookup[var] = info
            except Exception as e:
                print(f"Warning: could not load POS lookup: {e}")

    def find_pos(self, barcode: str) -> dict[str, str]:
        if not barcode:
            return {}
        for var in get_barcode_lookup_variants(barcode):
            if var in self.pos_lookup:
                return self.pos_lookup[var]
        return {}

    def scan_barcodes_zxing(self, files: list[Path]) -> dict[str, str | None]:
        import zxingcpp

        cache: dict[str, str | None] = {}
        if self.barcode_cache_file.exists():
            try:
                with open(self.barcode_cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                cache = {}

        updated = False
        for f in files:
            fname = f.name
            if fname in cache:
                continue
            try:
                with Image.open(f) as im:
                    results = zxingcpp.read_barcodes(im)
                    valid = [
                        str(r.text).strip()
                        for r in results
                        if getattr(r, "text", None)
                        and str(r.text).strip().isdigit()
                        and len(str(r.text).strip()) >= 8
                    ]
                    cache[fname] = valid[0] if valid else None
                    updated = True
            except Exception:
                cache[fname] = None
                updated = True

        if updated:
            self.barcode_cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.barcode_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)

        return cache

    def _recover_barcode_via_zoom(self, img_path: Path, box_2d: list[int] | None) -> str | None:
        import zxingcpp

        if not box_2d or len(box_2d) != 4:
            return None

        try:
            with Image.open(img_path) as orig_im:
                w, h = orig_im.size
                ymin, xmin, ymax, xmax = box_2d
                left = max(0, int(xmin * w / 1000) - 30)
                top = max(0, int(ymin * h / 1000) - 30)
                right = min(w, int(xmax * w / 1000) + 30)
                bottom = min(h, int(ymax * h / 1000) + 30)

                if right <= left or bottom <= top:
                    return None

                crop_bc = orig_im.crop((left, top, right, bottom))
                cw, ch = crop_bc.size
                if ch > cw * 1.2:
                    crop_bc = crop_bc.rotate(90, expand=True)

                enhanced = ImageEnhance.Contrast(crop_bc).enhance(2.2)
                for rot in [0, 90, 180, 270]:
                    im_rot = enhanced if rot == 0 else enhanced.rotate(rot, expand=True)
                    for r in zxingcpp.read_barcodes(im_rot):
                        t = str(r.text).strip()
                        if t.isdigit() and (validate_ean_upc_checksum(t) or self.find_pos(t)):
                            return t

                digits = self.vision.read_zoomed_barcode(crop_bc)
                if digits:
                    if validate_ean_upc_checksum(digits) or self.find_pos(digits):
                        return digits

        except Exception as e:
            print(f"Error in zoom recovery for {img_path.name}: {e}")
        return None

    def _crop_front_image(self, src_path: Path, box_2d: list[int] | None, dest_path: Path) -> tuple[int, int]:
        with Image.open(src_path) as im:
            w, h = im.size
            if not box_2d or len(box_2d) != 4:
                im.save(dest_path, format="JPEG", quality=95)
                return w, h

            ymin, xmin, ymax, xmax = box_2d
            left = int(xmin * w / 1000)
            top = int(ymin * h / 1000)
            right = int(xmax * w / 1000)
            bottom = int(ymax * h / 1000)

            if right <= left or bottom <= top:
                im.save(dest_path, format="JPEG", quality=95)
                return w, h

            pad_x = int((right - left) * 0.015)
            pad_y = int((bottom - top) * 0.015)
            left = max(0, left - pad_x)
            top = max(0, top - pad_y)
            right = min(w, right + pad_x)
            bottom = min(h, bottom + pad_y)

            cropped = im.crop((left, top, right, bottom))
            cropped.save(dest_path, format="JPEG", quality=95)
            return cropped.size

    def export_excel_65(self, products: list[G1ProductItem], excel_path: Path) -> None:
        """Exports exactly formatted Excel conforming to customer-send-me.xlsx (Row 0 blank, Row 1 headers, Row 2.. data)."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"

        # Row 1 is empty in customer-send-me.xlsx
        # Row 2 contains headers
        headers = [col_title for col_title, _ in COLUMNS_65_MAPPING]
        ws.append([])  # Blank row 1
        ws.append(headers)  # Row 2

        for p in products:
            row_data = []
            for _, attr_name in COLUMNS_65_MAPPING:
                val = getattr(p, attr_name, "")
                if val is None:
                    row_data.append(None)
                elif isinstance(val, (int, float)):
                    row_data.append(val)
                else:
                    row_data.append(str(val))
            ws.append(row_data)

        excel_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(excel_path)
        print(f"Successfully exported 65-column Master Excel to: {excel_path}")
