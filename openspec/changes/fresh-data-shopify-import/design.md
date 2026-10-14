# Design: Fresh Data Shopify Import & Delivery Engine

## Context

See `proposal.md` for motivation. The dataset comprises 1,192 fresh images across 4 batches (`G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`). Previous runs generated cached vision OCR data and POS reconciliation mappings. This design details the clean execution strategy to regenerate clean image crops, standardized 65-column delivery files, 74-column consolidated masters, and 28-column Shopify CSVs.

## Goals / Non-Goals

**Goals:**
- Guarantee 100% clean-data provenance: exactly 1,192 source image records mapped.
- Zero rotation defects: 100% upright portrait orientation (Height > Width) across all generated `.jpg` and `.webp` front images.
- Complete 65-column schema compatibility with `G1_Master_Delivery_v2.xlsx`.
- Complete 28-column Shopify CSV compatibility with Danish HTML body description.

**Non-Goals:**
- Re-querying Gemini Vision API from scratch when valid cached OCR extractions exist.
- Modifying historical G1 delivery outputs.

## Decisions

### 1. Hybrid Cache-Augmented Pipeline
- **Decision**: Ingest the 1,192 file manifest directly from disk, match with persistent `g2_vision_cache.json` through `g5_vision_cache.json` for rich metadata, and apply sequential multi-shot pairing for back-label barcode propagation.
- **Rationale**: Reduces processing time from 30+ minutes to under 2 minutes while avoiding API rate limits and preserving 100% data fidelity.
- **Alternatives considered**: Full API re-scan (too slow, rate limits) or static Excel copy (carries dirty legacy artifacts).

### 2. Multi-Pass Crop & Orientation Enforcement
- **Decision**: Extract front packaging crops using calibrated bounding boxes with a 3-5% margin. If image width exceeds height, automatically rotate by $90^\circ$ or $270^\circ$ based on aspect ratio and text orientation.
- **Rationale**: Guarantees consistent aesthetic quality for web and catalog delivery without clipped packaging caps or labels.

### 3. Unified Exporter Architecture
- **Decision**: Implement a centralized script (`scripts/export_clean_fresh_catalog.py`) that exports:
  1. `output/shopify_import/front_images_jpg/<barcode>.jpg` and `.webp`
  2. `output/shopify_import/Master_G2_G5_Delivery_v2.xlsx` (65 columns)
  3. `output/shopify_import/Master_G2_G5_Consolidated.xlsx` (74 columns)
  4. `output/shopify_import/Master_G2_G5_Shopify_Import.csv` (28 columns)
- **Rationale**: Eliminates synchronization drift between delivery spreadsheets and image files.

## Risks / Trade-offs

- **[Risk]** Missing barcodes on standalone front shots → **[Mitigation]** Sequential multi-shot pairing matches front shots with back shots; POS lookup (`Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx`) assigns verified barcodes for unreadable labels; remaining items receive deterministic `NO_BARCODE_{batch}_{seq}.jpg`.
- **[Risk]** Barcode numbers being corrupted into scientific notation (`4.8E+12`) by Excel → **[Mitigation]** Write barcodes strictly as pure strings and format Excel cells with explicit text data types.
