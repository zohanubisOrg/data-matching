# Tasks

## 1. Environment & Package Scaffolding

- [x] 1.1 Create `src/product_mapper/zohanubis/` directory structure and verify `__init__.py` exports clean modules.
- [x] 1.2 Verify local system libraries (`zxingcpp`, `cv2`, `PIL`, `openpyxl`, `torch`, `torchvision`, `rembg`, `pillow_heif`) and ensure clean imports and BiRefNet session availability.

## 2. Raw Ingestion, Parallel Barcode Scanning & Reconciliation

- [x] 2.1 Implement `sanitizer.py` to ingest raw images from the 5 original folders, apply EXIF auto-orientation, and decode Apple HEIC files into normalized RGB.
- [x] 2.2 Implement `barcode_scanner.py` using `ProcessPoolExecutor` with `zxingcpp`, CLAHE contrast enhancement, 4-angle rotation sweeps, and studio sequence proximity fallback.
- [x] 2.3 Implement `reconciler.py` to reconcile raw barcodes against `Rabuta_master_SKU_categories.xlsx`, write `Zohanubis_Missing_SKU_Report.xlsx`, and quarantine orphan photos.

## 3. Tiered Fast Screening & Hero Front-View Matching (Pass 1)

- [x] 3.1 Implement `hero_cropper.py` to detect multi-object scenes (companion jars or side-by-side bottles) and crop only the primary hero bounding box matching the demo aspect ratio.
- [x] 3.2 Implement `front_matcher.py` using Pass 1 downscaled previews (512px) to extract Column W demo embeddings, compute cosine similarity against non-barcode photos within the matching Record ID partition, and blacklist verified back photos.

## 4. Targeted Alpha Matting & Balanced Quality Gate Engine (Pass 2)

- [x] 4.1 Implement `matting_engine.py` executing Pass 2 deep matting (`rembg` with BiRefNet backend) exclusively on the 1,169 qualified front winners.
- [x] 4.2 Implement topological outer-contour flood-filling within `matting_engine.py` to permanently lock internal transparent windows (e.g., wonton pastry, jelly sweets) to 100% opacity.
- [x] 4.3 Implement `studio_standardizer.py` to place masked hero products on 2048 x 2048 px pure white canvases (`#FFFFFF`) with 80% area coverage, subtle contact shadow, and sRGB profile.
- [x] 4.4 Implement `quality_gate.py` with balanced 3-tier classification (`PASS`, `WARNING/SOFT-PASS`, `HARD-FAIL`), accommodating natural voids (spray nozzles, loop handles), and recording metrics in `zohanubis_audit_ledger.json`.

## 5. Atomic Excel Dual-Image Embedder & CLI Orchestration

- [x] 5.1 Implement `excel_embedder.py` to insert `Ảnh webshop` and `Ảnh mặt sau` columns into the master workbook and embed 400x400 px thumbnails with locked 120pt row height.
- [x] 5.2 Implement `scripts/run_zohanubis_pipeline.py` CLI orchestrating Stages 0 through 5 with flags (`--pilot`, `--workers`, `--all`, `--pass1-only`).
- [x] 5.3 Run an end-to-end pilot run on a multi-item sample batch across all 5 partitions and verify that output images, reports, and Excel workbooks pass all quality requirements without false rejections.

## 6. Customer Packshot Repository Ingestion & Clean Production Architecture

- [x] 6.1 Set output directory to `output/shopify-zohanubis-image/` partitioned into `webshop_front_hd/`, `webshop_back_hd/`, `customer_provided/`, and `reports/`.
- [x] 6.2 Ingest customer-provided front packshots from `source-import/customer-send-me-front-product` (379 files).
- [x] 6.3 Enforce strict skip rule: barcodes present in customer repository bypass BiRefNet AI matting, are standardized to 2048x2048 canvas, paired with studio back photos, and logged as `PASS (Customer)`.

## 7. Divide-and-Conquer Partition Engine for G4 & Nyt

- [x] 7.1 Implement Sequential-Pair resolver for `Nyt25.09.26` (`IMG_5446.HEIC`–`IMG_5558.HEIC`) mapping odd non-barcode photos as intact Front packshots and adjacent even barcode photos as Back photos without split-cropping.
- [x] 7.2 Implement Carton Box resolver for `G4-original` (`G4-0066`–`G4-0097`) pairing front artwork carton faces with side/shipping barcode faces without split-cropping, preserving linear box geometry.
- [x] 7.3 Implement Single-Surface Produce resolver for `G4-original` (`G4-0001`–`G4-0037`) treating bagged produce as full-face front packshots with boundary alpha softening for translucent plastic wrap, and pairing 2 special two-shot items (`G4-0005`, `G4-0006`).
- [x] 7.4 Implement Global Cross-Partition Reconciler to map G4 supplement photos (`20260917_115416908` to `20260917_140212341`) to master catalog items across `G1`, `G2`, and `G3`.

## 8. Multi-Archetype Isolation, Partition Delivery & 5-Folder Concurrency Engine

- [x] 8.1 Implement 5-Archetype layout classifier in `hero_cropper.py`:
  - `TRIPLE_VERTICAL_PANEL` (detect 3 density columns across X; extract central hero `X: 0.34–0.65`; clip upper carton background `Y < 0.30`).
  - `HORIZONTAL_STACK` (detect horizontal ratio `W/H > 1.8`; split along Y-axis into Top Front and Bottom Barcode Back).
  - `STACKED_TUBS_GRID` (split rows at `Y = 0.50`; extract isolated central bottom tub `X: 0.35–0.65`).
  - `DUAL_TRAY_WRAPPED` (split at `X = 0.50` with topological outer contour flood-fill protecting clear plastic film).
  - `DECONSTRUCTED_CARTON` (SIFT template matching anchored to Column W demo to bound primary face box).
- [x] 8.2 Implement source-dedicated partition subfolder routing in `run_zohanubis_pipeline.py`:
  - Route front outputs to `output/shopify-zohanubis-image/webshop_front_hd/<partition>/`.
  - Route back outputs to `output/shopify-zohanubis-image/webshop_back_hd/<partition>/`.
- [x] 8.3 Implement non-blocking Quarantine Staging and Two-Stage Retry Loop:
  - Stage `HARD_FAIL` or unseparated objects into `quarantine_for_retry/<partition>/` without breaking batch execution.
  - Implement `QuarantineHealer` executing 3-tier fallback (relaxed SIFT, sequence proximity photo, conservative bounding box).
- [x] 8.4 Implement 5-Folder Concurrent Multi-Thread Execution:
  - Dispatch all 5 source folders (`G1`, `G2`, `G3`, `G4`, `Nyt`) in parallel using a 16-core CPU process pool.
  - Implement thread-safe atomic merge of all 5 partition results into `Rabuta_master_SKU_categories_zohanubis.xlsx`.
- [ ] 8.5 Execute Automated Acceptance Verification on Benchmark Test Suite:
  - `IMG_0885.jpeg` (Shan Meat Masala: center box intact, no bisecting, zero shipping box text).
  - `IMG_0123.jpeg` & `IMG_0429.jpeg` (Horizontal bottles: split along Y, zero waist slicing).
  - `IMG_0380.jpeg` (Stacked tubs: exactly 1 single isolated tub packshot).
  - `IMG_1399.jpeg` (Dual wonton tray: split down center seam, no hollowing of wonton pastry).
  - `IMG_0886.jpeg` (Phở gà: assembled front box extracted via SIFT).
  - G4/Nyt regression check: zero split-cropping on carton boxes and bagged coriander produce.
- [ ] 8.6 Launch Full Concurrent Production Run across all 5 folders simultaneously:
  - Generate final `Rabuta_master_SKU_categories_zohanubis.xlsx` with dual embedded thumbnails.
  - Archive all 2048x2048 HD assets across partition subfolders and deliver `Zohanubis_Missing_SKU_Report.xlsx` and `zohanubis_audit_ledger.json`.

