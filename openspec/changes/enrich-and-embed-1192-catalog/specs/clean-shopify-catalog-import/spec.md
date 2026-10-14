# Spec Delta

## Purpose

Enriches the 1,192 fresh image catalog with global food database nutrition and metadata, enforces strict front-of-pack orientation, and produces synchronized client deliverables including Excel with embedded image thumbnails.

## ADDED Requirements

### Requirement: Global Food Database Market Enrichment
The system SHALL enrich product records using OpenFoodFacts API and local POS catalogs whenever an EAN/UPC barcode is identified, populating mandatory nutrition facts (energy kJ/kcal, fat, saturated fat, carbohydrates, sugars, protein, salt) and ingredient/allergen information.

#### Scenario: Barcode matched in OpenFoodFacts
- **WHEN** a valid barcode (e.g., 5701234567890) is processed
- **THEN** nutrition facts, ingredients, allergens, and brand fields are filled from the global catalog and local caches

#### Scenario: EU FIC Annex V Exemption applied
- **WHEN** a product is an exempt category (pure whole spices, raw single-ingredient agricultural grains, or alcoholic beverages >1.2% vol) and lacks numeric nutrition data
- **THEN** the nutrition basis field SHALL state the explicit EU FIC 1169/2011 Annex V exemption reason

### Requirement: Strict Front-vs-Back Discrimination & Multi-shot Pairing
The system SHALL discriminate front packaging photos from back label photos using color saturation, edge density, and barcode geometry, and propagate barcodes from back label shots to front-of-pack photos.

#### Scenario: Dual-side single photo (side-by-side)
- **WHEN** a raw image contains both front and back packaging side-by-side
- **THEN** the system crops strictly the front packaging half and ignores the back label half

#### Scenario: Multi-shot sequential pairing
- **WHEN** a product is captured across two sequential photos (front photo without barcode, back photo with barcode)
- **THEN** the system assigns the back photo's barcode to the front photo and generates the front crop under `<barcode>.jpg`

### Requirement: Embedded Front Image Thumbnails in Delivery v2 Excel
The system SHALL embed high-definition front packaging thumbnails directly into Column 65 (Column BM - "Ảnh mặt trước") of `Master_G2_G5_Delivery_v2.xlsx` for all 1,192 rows.

#### Scenario: Excel generation with visual thumbnails
- **WHEN** `Master_G2_G5_Delivery_v2.xlsx` is generated
- **THEN** every product row contains an embedded visual thumbnail in Column BM with row height set to 195pt and column width set to 44.0

### Requirement: Triple Synchronized Output Files
The system SHALL export 3 synchronized master files (`Master_G2_G5_Delivery_v2.xlsx`, `Master_G2_G5_Consolidated.xlsx`, `Master_G2_G5_Shopify_Import.csv`) and batch-specific spreadsheets containing exactly 1,192 rows.

#### Scenario: Triple export verification
- **WHEN** the pipeline finishes execution
- **THEN** all 3 master files contain exactly 1,192 rows, bar codes are preserved as text strings, and the dual image folders contain 1,192 front images in JPG and WEBP
