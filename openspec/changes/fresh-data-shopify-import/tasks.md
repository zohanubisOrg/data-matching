# Tasks: Fresh Data Shopify Import & 65-Column Delivery Pipeline

## 1. Clean Manifest & Input Preprocessing

- [x] 1.1 Ingest exact 1,192 image manifest from `source-import/` (G2: 476, G3: 469, G4: 123, G5: 124) and verify 0 foreign test artifacts
- [x] 1.2 Verify multi-format native decoding for JPEG, JPG, and HEIC iOS camera formats across all 1,192 images

## 2. Image Cropping & Upright Orientation Normalization

- [x] 2.1 Implement clean front packaging crop extractor with 3-5% protective border margins
- [x] 2.2 Enforce strict upright portrait orientation (Height > Width) with 0% inverted or landscape images
- [x] 2.3 Export dual image assets to `output/shopify_import/front_images_jpg/<barcode>.jpg` and `output/shopify_import/front_images_webp/<barcode>.webp`

## 3. Barcode & Metadata Synchronization

- [x] 3.1 Synchronize Vision Cache metadata (Danish Title, Ingredients, Nutrition, Allergens, Storage) for all 1,192 items
- [x] 3.2 Execute sequential multi-shot pairing to propagate back-label barcodes to front shots
- [x] 3.3 Apply POS catalog lookup (`Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx`) for unreadable items

## 4. Triple Artifact Export & Quality Verification

- [x] 4.1 Generate `output/shopify_import/Master_G2_G5_Delivery_v2.xlsx` with exact 65 columns matching `G1_Master_Delivery_v2.xlsx`
- [x] 4.2 Generate `output/shopify_import/Master_G2_G5_Consolidated.xlsx` with 74 technical columns
- [x] 4.3 Generate `output/shopify_import/Master_G2_G5_Shopify_Import.csv` with 28 standard Shopify columns and HTML body
- [x] 4.4 Verify record count (exactly 1,192 items) and text-string barcode integrity across all output spreadsheets
