# Proposal

## Why

Existing legacy image processing pipelines in the catalog suffered from critical defects: aggressive thresholding punched holes through translucent and windowed packaging (e.g., wonton wrappers and jelly sweets), scene clustering failed to isolate primary products from companion jars or double-bottle shots, and workflows depended on stale intermediate caches. Furthermore, monolithic brute-force processing on 1,584 raw 4K/5K photos resulted in massive latency, while rigid, one-size-fits-all quality metrics falsely rejected valid products with natural geometric voids (such as trigger spray bottles, hanging loops, or handles).

`pipeline-zohanubis` is a brand-new, clean-sheet pipeline built to process 1,584 raw multi-angle images from 5 original source folders (`G1`, `G2`, `G3`, `G4`, `Nyt`) against `Rabuta_master_SKU_categories.xlsx`. It introduces a high-speed Tiered Two-Pass Architecture, multi-angle raw barcode verification with sequence proximity fallback, visual ground-truth front matching against Excel demo thumbnails, topological hole-filling for translucent materials, a balanced category-adaptive Quality Gate, and safe dual-image Excel embedding.

## What Changes

- **Divide-and-Conquer Multi-Strategy Architecture**:
  - *Strategy 1 (Standard Dual-Hero & 5 Structural Archetypes)*: For `G1`, `G2`, `G3`, and `Nyt` dual items, replaces naive 50/50 binary splitting with a multi-archetype layout classifier:
    1. `TRIPLE_VERTICAL_PANEL` (3 columns across X: Left = Barcode/Nutrition, Center = Front Packshot Hero, Right = Importer/Side; crops Center hero without bisecting it, discarding top background carton clutter e.g. `IMG_0885.jpeg` Shan Masala, `IMG_0018.jpeg` White Rabbit, `IMG_0500.jpeg` PAN).
    2. `HORIZONTAL_STACK` (2 or 3 horizontal bottles/pouches stacked vertically across Y: splits along Y-axis, extracting Top bottle as Front and Bottom barcode bottle as Back, e.g. `IMG_0123.jpeg` Kikkoman 1L, `IMG_0427.jpeg`–`IMG_0476.jpeg` FaThai lime juice, horizontal packets `IMG_0155.jpeg`, `IMG_0251.jpeg`, `IMG_0326.jpeg`).
    3. `STACKED_TUBS_GRID` (2x3 or 2x2 grid of round plastic tubs: separates rows at Y=0.50, isolating a single centered tub from the bottom row for the front packshot e.g. `IMG_0380.jpeg`, `IMG_0381.jpeg` Mae Pranom shrimp paste).
    4. `DUAL_TRAY_WRAPPED` & `SINGLE_FACE_CLEAR_BAG` (Dual sealed plastic trays: splits at X=0.50; applies topological flood-fill to prevent AI hollowing of transparent wrap on wonton dumplings `IMG_1399.jpeg`–`IMG_1429.jpeg` and dry food bags `IMG_5122.HEIC`–`IMG_5159.HEIC`).
    5. `DECONSTRUCTED_CARTON` (Unfolded flat cardboard packaging + blister cards: anchors SIFT feature matching directly to Column W demo image to isolate the primary assembled face box e.g. `IMG_0886.jpeg`–`IMG_0889.jpeg` Phở gà).
  - *Strategy 2 (Sequential Pair Architecture)*: For `Nyt25.09.26` (`IMG_5446.HEIC`–`IMG_5558.HEIC`), `G4-original` carton boxes (`G4-0066`–`G4-0097`), and `G4` special pairs (`G4-0005`, `G4-0006`), treats consecutive shots as front-and-back pairs (odd/front artwork face vs even/barcode side face). Eliminates split-cropping to preserve 100% of the product geometry.
  - *Strategy 3 (Single-Surface Bagged Produce Packshots)*: For `G4-original` fresh produce/vegetables/mushrooms in plastic bags (`G4-0001`–`G4-0037`), recognizes that products have only one face with barcode attached. Uses the full product as the front packshot without split cropping, applying enhanced boundary alpha softening and anti-hollowing to protect delicate plastic films and leafy contours.
  - *Cross-Partition Reshoot Mapping*: Automatically maps supplement/reshoot photos in `G4-original` (`20260917_115416908` to `20260917_140212341`) back to their true catalog records in `G1`, `G2`, and `G3`.
- **Partitioned Deliverables Subfolder Organization**:
  - Partitions `output/shopify-zohanubis-image/webshop_front_hd/` and `webshop_back_hd/` into source-dedicated subdirectories (`G1_original/`, `G2_original/`, `G3_Original/`, `G4-original/`, `Nyt25.09.26/`). Enables real-time transparency and instant visual verification of output per batch.
- **Quarantine Staging & Two-Stage Retry Loop**:
  - Non-blocking execution: Items flagged with `HARD_FAIL` or unseparated companion objects are staged into `output/shopify-zohanubis-image/quarantine_for_retry/<partition>/` with defect metadata.
  - After processing the full batch, a dedicated `Quarantine Healer` automatically retries quarantined items using relaxed SIFT thresholds, sequence proximity fallback, and conservative cropping before final sign-off.
- **5-Folder Concurrent Multi-Thread Execution**:
  - Leverages the host's 16 CPU cores and 32GB RAM to process all 5 source folders (`G1`, `G2`, `G3`, `G4`, `Nyt`) simultaneously across 5 independent worker streams. Employs thread-safe atomic merging for the final master Excel workbook.
- **Customer Pre-Made Packshot Bypass**: Ingests 379 pre-made front packshots from `source-import/customer-send-me-front-product`, skipping AI background matting entirely, standardizing onto 2048x2048 white canvas, and pairing with studio back photos.
- **Pure-Source & Zero-Cache Pipeline**: Processes exclusively from raw inputs (`Rabuta_master_SKU_categories.xlsx` and the 5 original source directories). Completely eliminates reliance on legacy outputs (`output/barcode_hd_images_updated`, previous pipeline runs, or stale caches).
- **Tiered Two-Pass Architecture for High Throughput**: 
  - *Pass 1 (Fast Screening on 512px Thumbnails)*: Ultra-fast barcode scanning (`zxingcpp`), EXIF orientation, and lightweight visual feature embedding (DINOv2/MobileNetV3) to isolate the single winning front photo per product.
  - *Pass 2 (Targeted High-Fidelity Matting)*: Deep neural matting runs *only* on the qualified front winners, slashing total pipeline processing time by over 30%.
- **Direct Multi-Angle Barcode Scanning with Sequence Fallback**: Scans raw 4K/5K images across 4 angles (0°, 90°, 180°, 270°) with CLAHE contrast enhancement and string preservation. Incorporates studio shooting sequence heuristics (adjacent shots in batch) when barcodes have specular glare.
- **Automated Gap Analysis & Reconciliation**: Reconciles raw barcode scans against the 1,351 master Excel rows, automatically generating `Zohanubis_Missing_SKU_Report.xlsx` for missing SKUs and quarantining orphan images.
- **Hero Object Isolation & Aspect-Ratio Verified Front Matching**: Detects multi-object bounding boxes to isolate single hero products (discarding companion jars/bottles) and matches front photos against Column W demo thumbnails using combined visual embeddings and aspect-ratio sanity checks.
- **Detail-Preserving Matting with Topological Protection**: Implements soft alpha matting (BiRefNet/RMBG via `rembg`) paired with structural flood-filling on outer contours to ensure transparent packaging windows (wonton wrappers, candies) and delicate bottle contours are never hollowed out.
- **Studio Webshop Standardization**: Normalizes front images onto a 2048 x 2048 px square canvas, pure white `#FFFFFF` background, centered with 80% area coverage, subtle contact shadow, and sRGB color profile.
- **Balanced & Category-Adaptive Quality Gate**: Replaces rigid rejection thresholds with a balanced 3-tier classification (`PASS`, `WARNING/SOFT-PASS`, `HARD-FAIL`). Accommodates products with natural voids (spray nozzles, hanging handles) without false rejections, logging full audit metrics in `zohanubis_audit_ledger.json`.
- **Atomic Dual-Embed Excel Exporter**: Inserts two new columns adjacent to `Ảnh mặt trước` (`Ảnh webshop` and `Ảnh mặt sau`), embedding optimized 400x400 thumbnails to keep the workbook responsive (<100MB) while archiving 2048x2048 HD assets in standalone directories.

## Capabilities

### New Capabilities
- `catalog-image-quality/zohanubis-pipeline`: Defines the complete end-to-end specifications for tiered two-pass raw ingestion, direct barcode verification, multi-archetype hero isolation, 5-folder concurrency, partitioned output structures, quarantine retry staging, topological detail-preserving matting, balanced category-adaptive quality gates, and dual-image Excel embedding.

### Modified Capabilities
*(None)*

## Impact

- **New Code**: Adds `scripts/run_zohanubis_pipeline.py` and dedicated engine modules under `src/product_mapper/zohanubis/` (`sanitizer.py`, `barcode_matcher.py`, `front_matcher.py`, `matting_engine.py`, `quality_gate.py`, `excel_embedder.py`, `hero_cropper.py`).
- **Input Sources**: `source-import/Rabuta_master_SKU_categories.xlsx`, `source-import/customer-send-me-front-product`, and 5 raw studio directories (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`).
- **Deliverables**: Generated under `output/shopify-zohanubis-image/`:
  - `Rabuta_master_SKU_categories_zohanubis.xlsx` (Master workbook with embedded webshop front & back images)
  - `webshop_front_hd/<partition>/` (All 2048x2048 front packshots organized by partition)
  - `webshop_back_hd/<partition>/` (High-res studio back photos isolated from raw photography)
  - `customer_provided/` (Standardized 2048x2048 packshots provided by customer)
  - `quarantine_for_retry/<partition>/` (Staged defective images evaluated by healing loop)
  - `reports/` (Audit ledger `zohanubis_audit_ledger.json`, gap report `Zohanubis_Missing_SKU_Report.xlsx`, master Excel)
- **Acceptance Criteria**:
  1. *Triple Vertical Panel Isolation*: Products like `IMG_0885.jpeg` (Shan Meat Masala) extract the intact central front packshot without horizontal bisecting or inclusion of background shipping boxes.
  2. *Horizontal Stack Separation*: Horizontal bottles/packets like `IMG_0123.jpeg` (Kikkoman) and `IMG_0427.jpeg`–`IMG_0476.jpeg` (FaThai) are cleanly separated along the horizontal axis without slicing bottle bodies.
  3. *Stacked Tubs Isolation*: Grids like `IMG_0380.jpeg` (Mae Pranom) extract a single standalone centered tub without neighboring tub clumps.
  4. *Zero Regression on G4 & Nyt*: Sequential pairs and single-surface fresh produce retain 100% of their geometry without false split-cropping.
  5. *5-Folder Concurrent Execution*: All 5 folders execute in parallel without thread race conditions, memory leaks, or file write collisions.
  6. *Two-Stage Quarantine Healing*: Quarantined items undergo automated fallback retries, achieving >= 95% automated delivery rate.
- **Dependencies**: Uses verified local environment libraries (`zxingcpp`, `cv2`, `PIL`, `openpyxl`, `torch`, `torchvision`, `rembg`, `pillow_heif`, `psutil`).

