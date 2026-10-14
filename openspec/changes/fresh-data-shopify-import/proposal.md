# Proposal: Fresh Data Shopify Import & 65-Column Delivery Pipeline

## Why

The client reported a discrepancy between the 1,192 input photographs across 4 batch folders (`G2_original`, `G3_Original`, `G4-original`, and `Nyt25.09.26`) and previous consolidated exports (which contained extra test artifacts or needed alignment with the 65-column delivery standard). We need a fresh, clean-data pipeline that ingests strictly the 1,192 verified source images, enforces strict portrait packaging crops with zero distortions, and produces standardized outputs including the 65-column master delivery workbook matching `G1_Master_Delivery_v2.xlsx`, the 74-column consolidated master, and the 28-column Shopify import CSV.

## What Changes

- **Strict 1,192 Source Manifest Ingestion**: Filter and process exclusively the 1,192 valid raw image files from the 4 batch folders (G2: 476, G3: 469, G4: 123, G5: 124), eliminating any extraneous test artifacts (`att.*.jpeg`).
- **High-Fidelity Front Packaging Extraction & Strict Portrait Orientation**:
  - Automatically detect and crop the front packaging from warehouse side-by-side shots (814 landscape images) with a 3-5% margin padding.
  - Enforce strict upright vertical portrait orientation (Height > Width, 0% upside-down or sideways) for all 1,192 outputs.
  - Export dual web assets: `output/shopify_import/front_images_jpg/<barcode>.jpg` and `output/shopify_import/front_images_webp/<barcode>.webp`.
- **Hybrid Multi-Tier Barcode & Metadata Recovery**:
  - Reuse cached high-confidence Gemini Vision OCR extractions for nutrition tables, ingredients, allergens, and storage in Danish (EU Regulation 1169/2011).
  - Apply sequential multi-shot pairing to transfer back-label barcode and nutrition facts to front-facing packaging records.
  - Fall back to POS catalog lookup (`Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx`) for unreadable labels.
- **Triple Output Generation**:
  - `Master_G2_G5_Delivery_v2.xlsx`: Exact 65-column schema matching `G1_Master_Delivery_v2.xlsx` with preserved string barcodes.
  - `Master_G2_G5_Consolidated.xlsx`: 74-column engineering master with 2D bounding boxes, rotation angles, and confidence metrics.
  - `Master_G2_G5_Shopify_Import.csv`: Standard 28-column Shopify CSV ready for direct upload to `Rabuta.dk`.

## Capabilities

### New Capabilities
- `clean-shopify-catalog-import`: Ingests clean multi-format raw batches (1,192 images), extracts upright front product crops (`.jpg` / `.webp`), and exports standardized 65-column Master Delivery workbooks and 28-column Shopify CSV files with Danish localization.

### Modified Capabilities
*(None - initial baseline for clean data pipeline)*

## Impact

- **Affected Code**: `scripts/finalize_all_clean.py`, `scripts/export_g2_g5_master_delivery_65.py`, `src/product_mapper/reporting/shopify_exporter.py`.
- **Dependencies**: `pillow`, `pillow-heif`, `openpyxl`, `pandas`, `zxingcpp`.
- **Output Artifacts**: `output/shopify_import/` containing `front_images_jpg/`, `front_images_webp/`, `Master_G2_G5_Delivery_v2.xlsx`, `Master_G2_G5_Consolidated.xlsx`, and `Master_G2_G5_Shopify_Import.csv`.
