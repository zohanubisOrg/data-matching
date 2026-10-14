# Tasks: Enriched Catalog Export & Embedded Excel Pipeline

## 1. Front-vs-Back Computer Vision & Barcode Pairing

- [x] 1.1 Ingest all 1,192 fresh images and apply front-vs-back discrimination to isolate front-of-pack panels
- [x] 1.2 Implement multi-shot sequential pairing to propagate barcodes from back photos to front-of-pack crops
- [x] 1.3 Export 1,192 HD front packaging image crops to `output/shopify_import/front_images_jpg/` and `front_images_webp/`

## 2. Global Food Database Market Enrichment

- [x] 2.1 Integrate `MarketCatalogEnricher` (OpenFoodFacts API + local vision caches) to populate Nutrition, Ingredients, Allergens, Brand, and Origin
- [x] 2.2 Apply POS SKU reconciliation (`Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx`) for all matching barcodes
- [x] 2.3 Enforce EU FIC 1169/2011 Annex V exemption rules for raw agricultural spices and alcoholic beverages

## 3. Triple Artifact Export with Embedded Excel Thumbnails

- [x] 3.1 Generate `output/shopify_import/Master_G2_G5_Delivery_v2.xlsx` with exact 65 columns and embedded front packaging thumbnails in Column 65 (`BM3` .. `BM1194`)
- [x] 3.2 Generate `output/shopify_import/Master_G2_G5_Consolidated.xlsx` (74 columns) and `Master_G2_G5_Shopify_Import.csv` (28 columns)
- [x] 3.3 Verify row count (exactly 1,192 products), embedded image count, and text-string barcode integrity across all deliverables
