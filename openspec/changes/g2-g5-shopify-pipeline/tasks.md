# Tasks: G2-G5 Data Pipeline & Shopify 28-Column Import Engine

## 1. Environment & Multi-Format Ingestion Setup

- [x] 1.1 Verify HEIC support via `pillow-heif` and create unified image loader utility handling `.jpg`, `.jpeg`, `.HEIC`, and `.heic` formats
- [x] 1.2 Scan and catalog all 1,196 images across `G2_original` (480), `G3_Original` (469), `G4-original` (123), and `Nyt25.09.26` (124) into a structured manifest

## 2. Shopify 28-Column Exporter & Master Consolidation Module

- [x] 2.1 Implement `src/product_mapper/reporting/shopify_exporter.py` generating all 28 Shopify columns (`Handle`, `Title`, `Body (HTML)`, `Vendor`, `Product Category`, `Type`, `Tags`, `Variant SKU`, `Variant Grams`, `Variant Barcode`, `Image Src`, `SEO Title`, `SEO Description`, etc.)
- [x] 2.2 Implement Danish HTML generator for `Body (HTML)` formatting ingredients, allergens, nutrition facts table, and storage instructions according to EU Regulation 1169/2011
- [x] 2.3 Verify `Variant Barcode` formatting preserves pure string digits and prevents scientific notation (`4.8E+12`)
- [x] 2.4 Add consolidation generator for Master Excel workbook with the front image column pointing strictly to `<barcode>.jpg`

## 3. Image Cropping, 2-Sided Separation & Orientation Enhancements

- [x] 3.1 Upgrade front packaging detector to accurately isolate the front side from 2-sided (front and back side-by-side) warehouse photos with adaptive 3-5% margin padding
- [x] 3.2 Implement background cleanup and native sensor resolution crop extraction (no lossy downscaling)
- [x] 3.3 Implement strict auto-upright rotation check ensuring all cropped images are in vertical portrait orientation (Height > Width) with 0% upside-down or sideways errors
- [x] 3.4 Add dual asset export generating both `<barcode>.jpg` (high quality) and optimized `<barcode>.webp` into `output/shopify_import/images/`
- [x] 3.5 Implement automated Crop Quality Audit & Re-Crop script (`scripts/audit_and_fix_faulty_crops.py`) that detects clipped text/edges and automatically re-crops faulty items

## 4. Multi-Tier Barcode Recovery & Difficult Image Processing

- [x] 4.1 Implement multi-angle ZXing + CLAHE contrast preprocessing for low-contrast barcode stripes
- [x] 4.2 Implement adaptive zoom crop & Otsu binarization for curved, wrinkled, and glare-affected packaging
- [x] 4.3 Implement Gemini Vision Deep OCR fallback with Modulo-10 checksum verification on zoomed barcode region
- [x] 4.4 Implement POS text-bridge reconciliation (Supplier SKU / Brand / Literal Name) to recover verified barcodes for unreadable labels

## 5. Batch Pipeline Execution & Reconciliation (G2, G3, G4, G5)

- [x] 5.1 Build batch processing runner `scripts/run_batch_g2_g5.py` with multi-key Gemini rate limiting and persistent disk caching
- [x] 5.2 Execute Batch G2 pipeline and verify initial Shopify CSV, Master Excel, & front image crops
- [x] 5.3 Execute Batch G3, G4, and G5 pipelines with POS master catalog reconciliation and 0% false NO_BARCODE rate
- [x] 5.4 Generate final combined Master Shopify CSV, 65-column Master Excel, and Reconciliation Audit Report
