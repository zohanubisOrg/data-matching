# Spec Delta: clean-shopify-catalog-import

## Purpose

Provides end-to-end ingestion of 1,192 fresh raw packaging photographs across 4 batch folders, auto-upright portrait image extraction, and export of standardized 65-column master delivery workbooks alongside 28-column Shopify CSVs for store import.

## ADDED Requirements

### Requirement: Strict 1192 Source File Ingestion
The pipeline SHALL exclusively ingest the 1,192 verified raw product photographs from `source-import/G2_original` (476), `source-import/G3_Original` (469), `source-import/G4-original` (123), and `source-import/Nyt25.09.26` (124) without including foreign test artifacts.

#### Scenario: Ingestion and validation of manifest
- **WHEN** the ingestion pipeline runs against `source-import/`
- **THEN** it counts exactly 1,192 source image files across the 4 batch folders and reports 0 corrupt files

### Requirement: Upright Portrait Packaging Crop Extraction
The system SHALL detect and isolate the front packaging view from multi-view/side-by-side raw warehouse photographs with a 3-5% protective margin and strictly enforce vertical portrait orientation (Height > Width).

#### Scenario: Extraction of front packaging image
- **WHEN** processing an image from `source-import/`
- **THEN** it exports `<barcode>.jpg` to `output/shopify_import/front_images_jpg/` and `<barcode>.webp` to `output/shopify_import/front_images_webp/` with portrait dimensions and zero edge clipping

### Requirement: Standard 65-Column Master Delivery Export
The system SHALL export a comprehensive delivery workbook matching the exact 65 columns and structure of `G1_Master_Delivery_v2.xlsx`.

#### Scenario: Master Delivery 65-column workbook generation
- **WHEN** export is triggered
- **THEN** `output/shopify_import/Master_G2_G5_Delivery_v2.xlsx` is generated with 65 standardized columns, row 1 empty title margin, row 2 headers, and pure text string barcode formats

### Requirement: Standard 28-Column Shopify CSV Export
The system SHALL export a client-ready 28-column Shopify CSV file with localized Danish HTML descriptions complying with EU Regulation 1169/2011.

#### Scenario: Shopify CSV generation
- **WHEN** export is triggered
- **THEN** `output/shopify_import/Master_G2_G5_Shopify_Import.csv` is generated with all 28 Shopify columns and `Image Src` pointing canonically to `https://rabuta.dk/cdn/shop/files/<barcode>.jpg`
