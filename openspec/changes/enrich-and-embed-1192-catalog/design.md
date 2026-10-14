# Design

## Context

See `proposal.md` for motivation. The codebase already contains:
1. `MarketCatalogEnricher` (`src/product_mapper/enrichment/market_enricher.py`) for querying OpenFoodFacts and caching barcode data.
2. `cv_front_detector.py` for isolating front packaging panels vs back labels.
3. OpenPyXL workbook image attachment mechanism (`OpenpyxlImage`) established in `scripts/generate_perfect_thumbnails_and_master.py`.

## Goals / Non-Goals

**Goals:**
- Ingest all 1,192 fresh images from `source-import/` (G2: 476, G3: 469, G4: 123, G5: 124).
- Apply `MarketCatalogEnricher` on all resolved barcodes to populate all nutrition and ingredient fields.
- Discriminate front vs back packaging and crop strictly the front panel.
- Embed thumbnail images directly into Column 65 (`BM`) in `Master_G2_G5_Delivery_v2.xlsx`.
- Synchronize `Master_G2_G5_Consolidated.xlsx` (74 cols) and `Master_G2_G5_Shopify_Import.csv` (28 cols).

**Non-Goals:**
- Modifying or reprocessing legacy G1 batch files.
- Modifying raw input images in `source-import/`.

## Decisions

### 1. Market Database Enrichment Pipeline
- **Choice**: Call `MarketCatalogEnricher` for each item with a valid barcode. If the barcode is present in OpenFoodFacts or local caches, enrich Energy, Fat, Carbs, Sugars, Protein, Salt, Ingredients, Allergens, Brand, and Origin.
- **Rationale**: Fills data gaps reliably without manual entry.

### 2. Embedded Images in Excel
- **Choice**: Use `openpyxl.drawing.image.Image` to attach HD thumbnails to Column 65 (`BM3` .. `BM1194`) with row height 195pt and col width 44.0.
- **Rationale**: Matches the customer's exact benchmark in `G1_Master_Delivery_v2.xlsx`.

### 3. Front-vs-Back Computer Vision Logic
- **Choice**: If an image contains side-by-side packaging, compare color saturation (front is higher) and edge density (back text is denser) and barcode centroid to isolate the front half.

## Risks / Trade-offs

- [Risk: Large Excel file size due to 1,192 embedded images] → Mitigation: Resize thumbnails to max 250px height / LANCZOS JPEG quality 90 before embedding to keep Excel file around 40-70MB.
- [Risk: OpenFoodFacts rate limits] → Mitigation: Use local cache (`g2_vision_cache.json`, `g3_vision_cache.json`, etc.) first and fallback to POS catalog.
