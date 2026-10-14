# Proposal

## Why

The current catalog export for 1,192 fresh images across G2–G5 suffers from data gaps in nutrition/ingredients and lacks embedded front packaging image thumbnails in `Master_G2_G5_Delivery_v2.xlsx`. Additionally, some multi-shot products (front/back photo pairs) were misclassified or yielded back-label crops instead of clean front packaging images. We need to integrate global food database enrichment (OpenFoodFacts), strict front-vs-back computer vision discrimination, sequential barcode pairing, and direct Excel thumbnail embedding (matching the customer's benchmark in `G1_Master_Delivery_v2.xlsx`).

## What Changes

- **Global Food Database Enrichment**: Query OpenFoodFacts API and local caches to populate Energy (kJ / kcal), Fat, Saturated Fat, Carbohydrates, Sugars, Protein, Salt, Ingredients list, Allergens, Brand, and Country of Origin.
- **EU FIC 1169/2011 Compliance**: Automatically apply nutrition declaration exemptions (Annex V) for raw agricultural produce, single-ingredient spices, and alcoholic beverages.
- **Strict Front-vs-Back Packaging Discrimination**: Use color saturation, text edge density, and barcode geometry to ensure cropped images are strictly front-of-pack (Mặt trước).
- **Sequential Multi-shot Barcode Pairing**: Pass barcodes scanned from back-label photos to their corresponding front-of-pack images.
- **Embedded Excel Thumbnails**: Embed high-definition front image thumbnails directly into Column 65 (Column `BM` - "Ảnh mặt trước") of `Master_G2_G5_Delivery_v2.xlsx` with standard row height (195pt) and column width (44.0).
- **Triple Output Synchronization**: Update `Master_G2_G5_Delivery_v2.xlsx`, `Master_G2_G5_Consolidated.xlsx`, and `Master_G2_G5_Shopify_Import.csv` with 100% synchronized, enriched data across all 1,192 products.

## Capabilities

### New Capabilities
- `clean-shopify-catalog-import`: Full pipeline for front-photo packaging cropping, multi-shot pairing, global food database enrichment (OpenFoodFacts), and triple artifact export with embedded Excel thumbnails.

### Modified Capabilities
<!-- None -->

## Impact

- Affected files: `scripts/export_clean_1192_catalog.py`, `src/product_mapper/enrichment/market_enricher.py`.
- Output deliverables: `output/shopify_import/Master_G2_G5_Delivery_v2.xlsx` (with embedded images), `output/shopify_import/Master_G2_G5_Consolidated.xlsx`, `output/shopify_import/Master_G2_G5_Shopify_Import.csv`, `output/shopify_import/front_images_jpg/`, and `output/shopify_import/front_images_webp/`.
