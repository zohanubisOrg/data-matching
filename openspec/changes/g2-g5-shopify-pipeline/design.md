# Technical Design: G2-G5 Data Pipeline & Shopify 28-Column Import Engine

## Context

The system processes product packaging photos to produce both high-resolution front-view crops and rich multi-lingual product catalog records. See `proposal.md` for background. The project must process 1,196 images across G2 (480), G3 (469), G4 (123), and G5 (124) while generating exact 28-column Shopify CSV files.

## Goals / Non-Goals

**Goals:**
- Ingest and process all 4 image folders (`G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`) with zero format crashes on `.HEIC`/`.heic`.
- Automatically generate 28-column Shopify CSV and consolidated master Excel files where image columns point directly to the barcode-named front image (`<barcode>.jpg` / `https://rabuta.dk/cdn/shop/files/<barcode>.jpg`).
- Optimize image crop quality: Maintain original sensor pixel dimensions with maximum fidelity, isolate front side from 2-sided (front+back) raw photos, clean up background noise, and strictly enforce vertical upright portrait orientation ($H > W$).
- Persist results in batch cache files (`output/g2_vision_cache.json`, etc.) to allow instant incremental reruns.

**Non-Goals:**
- Modifying live Shopify store database directly via API (output is client-ready CSV for upload).
- Re-processing G1 legacy deliveries.

## Decisions

1. **HEIC Decoding via `pillow-heif`**:
   - *Rationale*: iOS devices capture in HEIC/HEIF by default. `pillow-heif` registers seamlessly with PIL Image openers without external dependencies.
   - *Alternative*: Converting all HEIC to JPEG with ImageMagick CLI (slower, requires extra disk space).

2. **Dedicated Shopify CSV & Master Excel Exporter Module (`src/product_mapper/reporting/shopify_exporter.py`)**:
   - *Rationale*: Consolidates all 28 Shopify columns and master Excel sheets, decoupling formatting from vision logic and ensuring `<barcode>.jpg` references.
   - *Alternative*: Inline CSV generation inside batch scripts.

3. **High-Fidelity Native Resolution Front Cropping & Anti-Inversion Engine**:
   - *Rationale*: For 2-sided photos (front and back side-by-side), AI isolates the front view coordinates with 3-5% margin padding. Cropping is performed at native image resolution with lossless or high-quality (quality=95+) encoding. An orientation verification stage validates text angle to prevent inverted ($180^\circ$) or sideways ($90^\circ / 270^\circ$) images.

4. **Multi-File Batch Runner (`scripts/run_batch_g2_g5.py`)**:
   - *Rationale*: Allows running individual batches (e.g. `--batch g2`) or all batches (`--batch all`) with progress logging and resume capability.

5. **4-Tier Difficult Image & Zero-NO_BARCODE Recovery Strategy**:
   - *Rationale*: Raw warehouse photos frequently suffer from plastic glare, curved surfaces, or motion blur. Rather than leaving items with NO_BARCODE:
     - Tier 1: Multi-angle ZXing decoding with CLAHE contrast enhancement ($0^\circ, 90^\circ, 180^\circ, 270^\circ$).
     - Tier 2: Zoom crop on barcode coordinates with Otsu adaptive thresholding.
     - Tier 3: High-resolution Gemini Vision Deep OCR on barcode region with GS1 Modulo-10 checksum check.
     - Tier 4: SKU/Brand text bridge matching against POS Master catalogs (`Products_imported_to_Shopbox...` and `Ten_hang_nhap.xlsx`).

6. **Crop Quality Acceptance Audit & Automated Re-Crop Engine (`scripts/audit_and_fix_faulty_crops.py`)**:
   - *Rationale*: To prevent delivering crops with severed product names, truncated logos, or chopped packaging margins:
     - Automated inspection checks bounding box aspect ratios, margin distances from product contours, and text coverage.
     - Any anomalous crop automatically triggers a targeted re-crop pass with expanded 8-10% padding or secondary layout prompt.
     - Automatically updates image files on disk and synchronizes paths in Excel/CSV reports.

## Risks / Trade-offs

- **[Risk] Gemini API Quota & Rate Limits on 1,196 images** → *Mitigation*: Leverage multi-key rotation, batch grouping, and disk caching (`output/<batch>_vision_cache.json`) so processed images are never called twice.
- **[Risk] Missing Barcodes on partial packaging** → *Mitigation*: Fall back to OCR zoom crop and POS SKU matching, flagging unmatched records with `Status: NEEDS_REVIEW` and fallback handles.
