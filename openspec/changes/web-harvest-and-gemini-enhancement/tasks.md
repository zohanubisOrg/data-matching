# Tasks: Web Packshot Harvesting & Gemini Enhancement

## 1. Multi-Tier Harvester & Google Images Deep Extractor

- [x] 1.1 Implement OpenFoodFacts client in `src/product_mapper/harvest/openfoodfacts_client.py` fetching `image_front_url` by barcode, with verification via sample query unit test.
- [x] 1.2 Implement Google Images deep extractor in `src/product_mapper/harvest/google_images_harvester.py` querying with `tbs=isz:l`, parsing embedded JavaScript payloads to extract original high-res image URLs (ignoring gstatic thumbnails), with rate-limit jitter backoff and local disk cache.
- [x] 1.3 Add candidate download and pre-filter pipeline rejecting images $< 600\text{ px}$ or invalid file extensions.

## 2. Gemini Semantic Auditor & Visual Anchor Validation

- [x] 2.1 Implement Column W thumbnail extractor & aspect ratio validator in `src/product_mapper/harvest/visual_anchor.py` comparing bounding box ratios ($W/H$) and rejecting candidates with $> 25\%$ aspect drift.
- [x] 2.2 Implement Gemini Vision packaging auditor in `src/product_mapper/harvest/gemini_auditor.py` with structured JSON schema checking brand identity, flavor/variant, and single front-facing orientation.
- [x] 2.3 Implement candidate retry queue and backtracking logic that iterates through up to 3 candidate images per SKU, mutating search queries before safely aborting to the reshoot list.

## 3. Lightweight 2048x2048 Canvas Standardization & 4-Layer HD Enhancement

- [x] 3.1 Implement auto-bounding box detection and margin trimming in `src/product_mapper/harvest/canvas_standardizer.py` for pre-matted white (RGB $\ge 248$) or transparent background images.
- [x] 3.2 Implement canvas centering onto $2048 \times 2048\text{ px}$ pure white background (`#FFFFFF`) with 84% target dimension scaling ($1720\text{ px}$) using mathematical Lanczos-4 resampling.
- [x] 3.3 Implement edge-preserving Bilateral Filter to suppress JPEG compression artifacts and adaptive Unsharp Masking (`radius=1.2`, `amount=130%`) to sharpen label typography.
- [x] 3.4 Save approved outputs strictly as `webshop_front_hd/Front/{barcode}-front.jpg` using JPEG Quality 95 and Chroma Subsampling 4:4:4 (`subsampling=0`).
- [x] 3.5 Implement post-save Laplacian sharpness inspection; verify variance score $\ge 50.0$, automatically purging any output failing the sharpness threshold and reverting to reshoot.

## 4. End-to-End Orchestrator & Catalog Re-Export

- [x] 4.1 Create CLI orchestrator `scripts/harvest_and_enhance_webshop_packshots.py` reading the 722 SKUs from `Rabuta_Customer_Reshoot_Request.xlsx` and processing them through the harvest & enhancement pipeline.
- [x] 4.2 Integrate automatic re-audit trigger executing `audit_and_export_reshoot_list.py` to regenerate `Rabuta_master_SKU_categories-image.xlsx` and `Rabuta_Customer_Reshoot_Request.xlsx`.
- [x] 4.3 Re-export updated Shopify CSV files (`Shopify_Rabuta_Webshop_Online_Only.csv` and `Shopify_Rabuta_Master_Catalog.csv`) reflecting newly recovered products.
- [x] 4.4 Run validation on a test batch of 20 reshoot SKUs and verify output resolution (2048x2048 px), barcode filename formatting, and reshoot count decrement.
