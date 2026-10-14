/opsx-apply# Proposal: G2-G5 Data Pipeline & Shopify 28-Column Import Engine

## Why

We need to ingest and reconcile 1,196 new raw product photographs across 4 batch folders (`G2_original`, `G3_Original`, `G4-original`, and `Nyt25.09.26` / G5). The current pipeline must be upgraded to support HEIC image formats from iOS devices, improve packaging crop accuracy with upright orientation, and directly export a standardized 28-column Shopify CSV import dataset matching the client's live production store (`Rabuta.dk`).

## What Changes

- **HEIC Image Format Support**: Native decoding for `.HEIC`/`.heic` iOS camera captures via `pillow-heif` across all batch ingestion pipelines.
- **Multi-Pass Barcode Recovery & Difficult Image Engine**:
  - Eliminates "NO_BARCODE" failures via a 4-tier recovery hierarchy (Multi-angle ZXing + CLAHE $\rightarrow$ High-Res Zoom Bounding Box Binarization $\rightarrow$ Multimodal Vision Deep OCR with Modulo-10 checksum $\rightarrow$ Supplier SKU & POS Catalog Reconciliation).
  - Specialized preprocessing for difficult packaging (curved bottles, wrinkled bags, glare, small labels, and motion blur).
- **Enhanced Image Quality & Orientation Normalization**:
  - Auto-upright rotation detection ensuring vertical upright portrait orientation (Height > Width), strictly eliminating upside-down or sideways images.
  - Front packaging view cropped from 2-sided (front/back side-by-side) warehouse photos with background clean-up and edge preservation.
  - Original resolution preservation: Cropped front images maintain original scale and maximum fidelity without unnecessary downsampling.
  - **Automated Crop Audit & Re-processing Loop**: Performs automated QA checks on all cropped images to detect clipped text, cut-off packaging caps/bottoms, or distorted aspect ratios, automatically triggering re-cropping with adjusted bounding boxes until 100% compliant.
  - Dual asset generation: `<barcode>.jpg` and high-fidelity `<barcode>.webp`.
- **Master Excel & Shopify CSV Consolidation**:
  - Image columns in both Excel master and Shopify CSV point canonically to the front packaging image named by barcode (`<barcode>.jpg` / `https://rabuta.dk/cdn/shop/files/<barcode>.jpg`).
  - Direct generation of client-ready CSV containing all 28 Shopify fields (`Handle`, `Title`, `Body (HTML)`, `Vendor`, `Product Category`, `Type`, `Tags`, `Variant SKU`, `Variant Grams`, `Variant Barcode`, `Image Src`, `SEO Title`, `SEO Description`, etc.).
  - Preserves exact text barcode format (preventing Excel/CSV scientific notation errors like `4.8E+12`).
  - Formats rich Danish HTML description compliant with EU Regulation 1169/2011 (Ingredients, Allergens, Nutrition Facts table, Storage, Preparation).
- **Multi-Batch Pipeline Execution**:
  - Processing workflows for G2 (480 images), G3 (469 images), G4 (123 images), and G5 (124 images) with persistent cache and POS reconciliation.

## Capabilities

### New Capabilities
- `shopify-catalog-import`: Direct generation of consolidated master Excel and standard 28-column Shopify product import CSV files with Danish localization, structured HTML body, and canonical barcode-referenced front image paths.
- `batch-image-processing`: Multi-format image ingestion (JPEG, HEIC), front packaging extraction from multi-view/2-sided photos at original dimensions with maximum quality, background cleaning, and strict upright portrait orientation enforcement.
- `pos-reconciliation-engine`: Zero-hallucination barcode validation, POS master matching against Shopbox & supplier catalogues, and segregation of ambiguous items.

### Modified Capabilities
*(None - first OpenSpec baseline)*

## Impact

- **Affected Code**: `src/product_mapper/g1_pipeline.py`, `src/product_mapper/vision/gemini_vision.py`, `scripts/prepare_web_delivery.py`, and new batch runners in `scripts/`.
- **Dependencies**: `pillow-heif` added for HEIC support.
- **Output Artifacts**: `output/shopify_import/` containing batch CSVs, master 65-column Excel sheets, and canonical product crops.
