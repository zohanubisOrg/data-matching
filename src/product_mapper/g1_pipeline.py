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
    barcode: str = ""
    brand: str = ""
    product_name: str = ""
    net_weight: str = ""
    variant: str = ""
    pos_sku: str = ""
    pos_product_name: str = ""
    original_image: str = ""
    website_front_image: str = ""
    front_box_2d: list[int] = Field(default_factory=list)
    cropped_width: int = 0
    cropped_height: int = 0
    detection_method: str = "zxing_direct"
    status: str = "CONFIRMED"


GROUND_TRUTH_CONFIRMED = {
    "IMG_0027.jpeg": {
        "barcode": "8720812774334",
        "brand": "SweetMellow (TXMM)",
        "product_name": "Jelly-like Sweets",
        "net_weight": "320 g",
        "variant": "Assorted Fruit / Mixed Fruit",
    },
    "IMG_0075.jpeg": {
        "barcode": "6971438291909",
        "brand": "KINGZEST",
        "product_name": "Seasoned Vinegar for Sushi",
        "net_weight": "200 ml",
        "variant": "Sushi Vinegar",
    },
    "IMG_0118.jpeg": {
        "barcode": "084909004147",
        "brand": "COCK Brand",
        "product_name": "Black Sesame Seed",
        "net_weight": "227 g / 8 oz",
        "variant": "Black Sesame Seed",
    },
    "IMG_0137.jpeg": {
        "barcode": "6902253866256",
        "brand": "Fish Well Brand",
        "product_name": "Shirataki Noodles Knot",
        "net_weight": "260 g (Drained: 132 g)",
        "variant": "Knot / Shirataki Konjac Noodles",
    },
    "IMG_0140.jpeg": {
        "barcode": "4316734091365",
        "brand": "ITA-SAN",
        "product_name": "Ramen Noodles",
        "net_weight": "200 g",
        "variant": "Japanese-style Ramen",
    },
    "IMG_0164.jpeg": {
        "barcode": "8936036028041",
        "brand": "Orion",
        "product_name": "Kẹo Họng Vị Bạc Hà Thảo Mộc",
        "net_weight": "84 g",
        "variant": "Bạc Hà Thảo Mộc",
    },
}


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

        # Robust POS Lookup with leading-zero variants normalization
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
                        # Index raw barcode and standard normalized variants
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
        """Zooms into high-resolution barcode region, enhances contrast, and decodes with strict validation."""
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

                # 1. Try optical zxing across 4 rotations
                enhanced = ImageEnhance.Contrast(crop_bc).enhance(2.2)
                for rot in [0, 90, 180, 270]:
                    im_rot = enhanced if rot == 0 else enhanced.rotate(rot, expand=True)
                    for r in zxingcpp.read_barcodes(im_rot):
                        t = str(r.text).strip()
                        if t.isdigit() and (validate_ean_upc_checksum(t) or self.find_pos(t)):
                            return t

                # 2. Vision AI Super-Resolution Zoom (Strict Checksum Verified)
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

    def run(self, limit: int | None = None) -> list[G1ProductItem]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.website_images_dir.mkdir(parents=True, exist_ok=True)

        all_files = sorted(
            list(self.images_dir.glob("*.jpeg")) + list(self.images_dir.glob("*.jpg"))
        )
        if limit:
            all_files = all_files[:limit]

        print(f"Loaded {len(all_files)} images from {self.images_dir}")

        existing_products: dict[str, G1ProductItem] = {}
        json_path = self.output_dir / "G1_products.json"
        if json_path.exists():
            try:
                raw_list = json.loads(json_path.read_text("utf-8"))
                for item in raw_list:
                    p = G1ProductItem(**item)
                    if p.original_image:
                        existing_products[p.original_image] = p
            except Exception:
                pass

        print("Scanning direct barcodes with zxing-cpp...")
        zxing_map = self.scan_barcodes_zxing(all_files)

        products: list[G1ProductItem] = []

        for idx, img_path in enumerate(all_files, 1):
            fname = img_path.name

            # Fast skip ONLY if product has confirmed barcode, non-empty product name, and web image exists
            if fname in existing_products:
                cached_p = existing_products[fname]
                has_web = (self.output_dir / cached_p.website_front_image).exists()
                if cached_p.status == "CONFIRMED" and cached_p.product_name and has_web:
                    print(f"[{idx}/{len(all_files)}] (SKIP CACHED) {fname} -> {cached_p.barcode} ({cached_p.product_name})")
                    products.append(cached_p)
                    continue

            # Ground Truth Override check
            if fname in GROUND_TRUTH_CONFIRMED:
                gt = GROUND_TRUTH_CONFIRMED[fname]
                primary_barcode = gt["barcode"]
                v_res = self.vision.analyze_image(img_path)
                dest_filename = f"{primary_barcode}.jpeg"
                dest_path = self.website_images_dir / dest_filename
                c_w, c_h = self._crop_front_image(img_path, v_res.front_box_2d, dest_path)
                pos_info = self.find_pos(primary_barcode)
                prod = G1ProductItem(
                    barcode=primary_barcode,
                    brand=gt["brand"],
                    product_name=gt["product_name"],
                    net_weight=gt["net_weight"],
                    variant=gt["variant"],
                    pos_sku=pos_info.get("sku", ""),
                    pos_product_name=pos_info.get("name", ""),
                    original_image=fname,
                    website_front_image=str(dest_path.relative_to(self.output_dir)),
                    front_box_2d=v_res.front_box_2d or [],
                    cropped_width=c_w,
                    cropped_height=c_h,
                    detection_method="ground_truth_confirmed",
                    status="CONFIRMED",
                )
                products.append(prod)
                print(f"[{idx}/{len(all_files)}] (GROUND TRUTH) {fname} -> {primary_barcode} ({gt['product_name']})")
                continue

            print(f"[{idx}/{len(all_files)}] Processing {fname}...")

            # Run Vision AI (3 active keys in round-robin -> sleep only 1.0s)
            time.sleep(1.0)
            v_res = self.vision.analyze_image(img_path)

            primary_barcode = zxing_map.get(fname)
            detection_method = "zxing_direct"

            # Fallback 1: Vision full view with strict checksum check
            if not primary_barcode and v_res.barcode:
                digits_only = re.sub(r"[^\d]", "", v_res.barcode)
                if len(digits_only) >= 8 and (validate_ean_upc_checksum(digits_only) or self.find_pos(digits_only)):
                    primary_barcode = digits_only
                    detection_method = "vision_full_view"

            # Fallback 2: High-Resolution Zoom & Crop Recovery
            if not primary_barcode and v_res.barcode_box_2d:
                print(f"  --> Zooming into barcode region for {fname}...")
                recovered_bc = self._recover_barcode_via_zoom(img_path, v_res.barcode_box_2d)
                if recovered_bc:
                    primary_barcode = recovered_bc
                    detection_method = "high_res_zoom"
                    print(f"  --> RECOVERED via zoom: {primary_barcode}!")

            # POS cross-reference with automatic name enrichment
            pos_info = self.find_pos(primary_barcode) if primary_barcode else {}
            pos_sku = pos_info.get("sku", "")
            pos_name = pos_info.get("name", "")
            pos_official = pos_info.get("official_name", "")

            # Product Name resolution: packaging title preferred, POS name fallback if packaging text unclear
            final_product_name = v_res.product_name.strip()
            if not final_product_name and pos_name:
                final_product_name = pos_name
            elif not final_product_name and pos_official:
                final_product_name = pos_official

            final_brand = v_res.brand.strip()
            if not final_brand and pos_official and " " in pos_official:
                # If packaging brand logo is unclear, take first token of POS official name
                candidate_brand = pos_official.split()[0]
                if len(candidate_brand) >= 3:
                    final_brand = candidate_brand

            if not primary_barcode:
                primary_barcode = f"NO_BARCODE_{Path(fname).stem}"
                status = "NO_BARCODE_MANUAL_REVIEW"
            else:
                status = "CONFIRMED"

            # Crop Front Image for Website
            dest_filename = f"{primary_barcode}.jpeg"
            dest_path = self.website_images_dir / dest_filename
            c_w, c_h = self._crop_front_image(img_path, v_res.front_box_2d, dest_path)

            prod = G1ProductItem(
                barcode=primary_barcode,
                brand=final_brand,
                product_name=final_product_name,
                net_weight=v_res.net_weight,
                variant=v_res.variant,
                pos_sku=pos_sku,
                pos_product_name=pos_name,
                original_image=fname,
                website_front_image=str(dest_path.relative_to(self.output_dir)),
                front_box_2d=v_res.front_box_2d or [],
                cropped_width=c_w,
                cropped_height=c_h,
                detection_method=detection_method,
                status=status,
            )
            products.append(prod)

            if idx % 10 == 0:
                self._export_results(products)

        self._export_results(products)
        try:
            from scripts.prepare_web_delivery import sync_web_assets
            print("\nTriggering auto-sync to web/public for Vercel deployment...")
            sync_web_assets()
        except Exception as e:
            print(f"Notice: Web auto-sync skipped: {e}")
        return products

    def _export_results(self, products: list[G1ProductItem]) -> None:
        rows = []
        for p in products:
            rows.append({
                "Barcode": p.barcode,
                "Brand": p.brand,
                "Original Product Name": p.product_name,
                "Net Weight": p.net_weight,
                "Variant": p.variant,
                "POS SKU": p.pos_sku,
                "POS Product Name": p.pos_product_name,
                "Website Front Image": p.website_front_image,
                "Cropped Dimensions (WxH)": f"{p.cropped_width}x{p.cropped_height}",
                "Barcode Method": p.detection_method,
                "Original Raw Image": p.original_image,
                "Status": p.status,
            })
        df = pd.DataFrame(rows)
        excel_path = self.output_dir / "G1_products.xlsx"
        try:
            df.to_excel(excel_path, index=False)
        except PermissionError:
            backup_excel = self.output_dir / "G1_products_latest.xlsx"
            try:
                df.to_excel(backup_excel, index=False)
            except Exception:
                pass

        json_path = self.output_dir / "G1_products.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([p.model_dump() for p in products], f, ensure_ascii=False, indent=2)

        html_path = self.output_dir / "G1_visual_report.html"
        self._generate_html_report(products, html_path)

    def _generate_html_report(self, products: list[G1ProductItem], html_path: Path) -> None:
        cards_html = []
        for p in products:
            status_color = "#10b981" if p.status == "CONFIRMED" else "#f59e0b"
            front_rel = f"website_front_images/{Path(p.website_front_image).name}"
            raw_rel = f"../../G1_original/{p.original_image}"
            card = f"""
            <div style="border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-bottom: 24px; background: white; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08); display: flex; gap: 24px; align-items: center;">
                <div style="flex: 0 0 220px; text-align: center;">
                    <div style="font-weight: 600; font-size: 13px; color: #0284c7; margin-bottom: 6px;">ẢNH MẶT TRƯỚC WEBSITE</div>
                    <img src="{front_rel}" style="max-width: 100%; max-height: 220px; border-radius: 8px; object-fit: contain; background: #f8fafc; border: 1px solid #cbd5e1;" />
                    <div style="font-size: 11px; color: #64748b; margin-top: 6px;">Kích thước: {p.cropped_width}x{p.cropped_height} px</div>
                </div>
                <div style="flex: 0 0 160px; text-align: center; border-left: 1px dashed #e2e8f0; padding-left: 16px;">
                    <div style="font-weight: 500; font-size: 12px; color: #64748b; margin-bottom: 6px;">ẢNH GỐC (2 MẶT)</div>
                    <img src="{raw_rel}" style="max-width: 100%; max-height: 160px; border-radius: 6px; object-fit: contain; opacity: 0.85;" />
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">{p.original_image}</div>
                </div>
                <div style="flex: 1; padding-left: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <span style="font-size: 18px; font-weight: bold; color: #0f172a;">{p.product_name or 'Chưa rõ tên (Cần kiểm tra)'}</span>
                        <span style="background: {status_color}; color: white; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600;">{p.status}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px; color: #334155;">
                        <div><strong>Barcode:</strong> <span style="font-family: monospace; background: #f1f5f9; padding: 3px 8px; border-radius: 4px; font-weight: 600;">{p.barcode}</span> <small style="color: #64748b;">({p.detection_method})</small></div>
                        <div><strong>Thương hiệu (Brand):</strong> {p.brand or '---'}</div>
                        <div><strong>Khối lượng (Net Wt):</strong> {p.net_weight or '---'}</div>
                        <div><strong>Variant / Vị:</strong> {p.variant or '---'}</div>
                        <div><strong>Khớp POS SKU:</strong> <span style="font-weight: 600; color: #0f766e;">{p.pos_sku or '---'}</span></div>
                        <div><strong>Tên POS:</strong> {p.pos_product_name or '---'}</div>
                        <div><strong>File Website:</strong> <code style="color: #0284c7;">{Path(p.website_front_image).name}</code></div>
                    </div>
                </div>
            </div>
            """
            cards_html.append(card)

        html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <title>G1 Products - Báo cáo tách ảnh mặt trước Website</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; margin: 0; padding: 30px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #0f172a; margin-bottom: 6px; }}
        .subtitle {{ color: #64748b; margin-bottom: 24px; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Báo Cáo Tách Ảnh Mặt Trước & Trích Xuất Barcode G1_original</h1>
        <div class="subtitle">Đã nâng cấp thuật toán: Kiểm tra Checksum quốc tế + Zoom cận cảnh độ phân giải 5K + Đối chiếu POS tự động.</div>
        {''.join(cards_html)}
    </div>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
