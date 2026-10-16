# Design

## Context

See [proposal.md](file:///D:/Work/shopify/openspec/changes/pipeline-zohanubis/proposal.md) for motivation and problem background.

The system processes 1,351 catalog items from `source-import/Rabuta_master_SKU_categories.xlsx` against 1,584 raw studio photographs distributed across 5 original directories:
- `G1_original` (467 images)
- `G2_original` (413 images)
- `G3_Original` (462 images)
- `G4-original` (119 images, Apple HEIC)
- `Nyt25.09.26` (123 images)

Legacy approaches suffered from high latency due to un-optimized brute-force execution and rigid, one-size-fits-all quality rules that falsely rejected legitimate non-convex items (spray bottles, bags with handles).

## Goals / Non-Goals

**Goals:**
- **Zero Cache Guarantee**: Ingest strictly from raw sources, performing live barcode scanning and visual feature matching from scratch.
- **High-Throughput Two-Pass Processing**: Sift candidates on downscaled 512px thumbnails (Pass 1), running expensive 2048px deep matting only on the 1,169 qualified front winners (Pass 2).
- **Partitioned Search**: Map Record ID prefixes (`G1-`, `G2-`, `G3-`, `G4-`, `N25-`) directly to their corresponding raw folders, cutting search complexity by 80%.
- **Single Hero Object Extraction**: Detect and crop the primary product bounding box, discarding secondary companion jars or side-by-side bottles.
- **Topological Window Protection**: Ensure packaging windows (e.g., wonton wrappers, jelly candies) and internal text are never punched out or hollowed by the background matting engine.
- **Balanced Category-Adaptive Quality Gate**: Implement 3-tier severity (`PASS`, `WARNING/SOFT-PASS`, `HARD-FAIL`) avoiding false rejections for products with natural handles or spray nozzles.
- **Lightweight Master Excel**: Embed 400x400 px optimized thumbnails into the new columns while saving pristine 2048x2048 HD assets to disk, maintaining a workbook file size under 120MB.
- **Full Traceability**: Log 100% of product decisions and quality scores in `zohanubis_audit_ledger.json`.

**Non-Goals:**
- In-place modification or destruction of original camera raw files.
- Direct Shopify Cloud API synchronization (handled in a separate ingestion step).
- Reusing or patching legacy scripts in `scripts/run_front_v5_batch.py`.

## Decisions

### 1. Tiered Two-Pass Processing Architecture
- **Choice**: Separate the pipeline into Pass 1 (Fast Screening) and Pass 2 (Targeted High-Resolution Matting).
  - *Pass 1*: Downscale all 1,584 raw photos to 512px previews in memory. Execute `zxingcpp` barcode scans, EXIF orientation, and MobileNetV3/DINOv2 visual embeddings in parallel. Determine the single winning front photo per product.
  - *Pass 2*: Run full-res deep matting (`rembg` with BiRefNet backend) only on the 1,169 winning front photos.
- **Rationale**: Eliminates running expensive neural matting on the ~415 secondary or back photos, reducing execution time by >30%.
- **Alternative Considered**: Running full-res matting on every photo before selecting the front view. *Rejected*: Highly inefficient and memory-intensive.

### 2. Multi-Process Concurrency for I/O and Barcode Decoding
- **Choice**: Use `concurrent.futures.ProcessPoolExecutor` with worker count matching physical CPU cores (e.g., 4–8 workers) for Pass 1 image loading, HEIC conversion, and multi-angle barcode sweeps.
- **Rationale**: CPU-bound operations (image decoding, rotation, barcode analysis) scale linearly with multiple cores, keeping GPU/memory available for batch model inference.

### 3. Sequence Proximity Fallback for Obscured Barcodes
- **Choice**: When a back photo suffers from specular glare or severe wrinkling that degrades barcode reading, detect consecutive shooting order (`IMG_0004.jpeg` followed by `IMG_0005.jpeg`) within the studio batch.
- **Rationale**: Studio photographers capture front and back shots in direct temporal sequence. Proximity heuristic resolves difficult glare cases without requiring customer re-shoots.

### 4. Hero Object Cropper with Connected Components
- **Choice**: When multiple bounding boxes are detected (e.g. a hero jar alongside a companion jar), crop only the bounding box with the highest similarity to the Column W demo image before passing it to the matting engine.
- **Rationale**: Eliminates the artifact seen in legacy runs where partial companion jars were left floating in the packshot.
- **Alternative Considered**: Full-image matting followed by post-matting component deletion. *Rejected*: Post-matting often merges touching bottles into a single irregular component.

### 5. Alpha Matting with Topological Flood-Fill Hole Protection
- **Choice**: High-resolution alpha matting (`rembg` BiRefNet/BriaRmBg) combined with an outer-perimeter structural flood-fill.
- **Rationale**: Identifies the outermost boundary contour of the product. Every pixel inside this closed perimeter is locked to foreground (Alpha = 1.0), guaranteeing that internal transparent windows (such as wonton dough or jelly sweets) are never treated as background. Outer boundaries retain soft, continuous alpha gradients to avoid jagged cuts.
- **Alternative Considered**: Standard binary thresholding (`mask > 128`). *Rejected*: Causes catastrophic hole-punching and jagged aliasing on transparent packaging.

### 6. Balanced Category-Adaptive Quality Gate Matrix
- **Choice**: Replace rigid hard-failure thresholds with a 3-tier severity matrix:
  - `PASS`: Solidity >= 0.75 (or >= 0.60 for handles/triggers), n_components == 1, zero boundary contact.
  - `WARNING / SOFT-PASS`: Naturally non-convex products (spray bottles with nozzles, pouches with loop handles) or slight blur. Embedded into Excel and flagged in `zohanubis_audit_ledger.json` for optional review.
  - `HARD-FAIL`: Only for true defects: unremoved companion objects (n_components > 1 with large area), severe clipping (> 10% area against canvas edge), or severe corruption.
- **Rationale**: Prevents valid complex-geometry packaging from being blocked while stopping true visual defects from entering the catalog.

### 7. Dual-Tier Asset Architecture for Master Excel
- **Choice**: Generate two distinct asset tiers:
  1. **Embedded Thumbnails**: 400x400 px WebP/JPEG (~50KB) embedded into the workbook cells with fixed 120pt row heights.
  2. **Webshop HD Master Files**: 2048x2048 px JPEG/PNG saved in `output/shopify-zohanubis-image/webshop_front_hd/` and `output/shopify-zohanubis-image/webshop_back_hd/`.
- **Rationale**: Avoids workbook bloat and Excel XML drawing crashes that occur when embedding full-resolution images for 1,350 rows.

### 8. Divide-and-Conquer Multi-Strategy Handling for Complex Partitions (G4 & Nyt)
- **Choice**: Implement three distinct operational strategies mapped to studio photography paradigms:
  1. *Dual-Hero Co-located Strategy (G1, G2, G3, Nyt Tofu/Mychinh)*: Front and back are captured in the same photograph. Apply SIFT feature matching against Column W demo images and orthogonal barcode coordinate partitioning to isolate the front hero and back packaging.
  2. *Sequential Pair Strategy (Nyt `IMG_5446.HEIC`–`IMG_5558.HEIC`, G4 cartons `G4-0066`–`G4-0097`, G4 pairs `G4-0005`, `G4-0006`)*: Consecutive photographs represent separate front and back angles. Odd/non-barcode photos are mapped intact as Front, while even/barcode photos are mapped intact as Back. Disable split-cropping to retain 100% of carton box and pouch geometry.
  3. *Single-Surface Strategy (G4 produce `G4-0001`–`G4-0037`)*: Bagged vegetables, fresh herbs, and mushrooms have only a single packaging surface with the barcode label attached. Disable split-cropping, take the full product as the front packshot, and apply enhanced boundary alpha softening to preserve translucent plastic wrap without jagged aliasing.
  4. *Global Cross-Partition Reconciliation*: Supplement photos in G4 (`20260917_115416908` to `20260917_140212341`) are resolved against all catalog rows across G1, G2, and G3 rather than restricted to G4.
- **Rationale**: Eliminates false hero-cropping on sequential pairs and prevents destructive background matting on fresh produce and carton boxes.

### 9. Multi-Archetype Hero Layout Classifier for Adjacent & Stacked Compositions
- **Choice**: Upgrade `HeroCropper` to `MultiArchetypeHeroCropper` supporting 5 distinct structural layouts:
  1. *Triple Vertical Panel*: Uses vertical X-axis projection histogram to detect 3 density peaks. Extracts the central packshot hero (`X: 0.34–0.65`) while clipping out upper shipping box text (`Y < 0.30`).
  2. *Horizontal Stack*: Detects horizontal aspect ratio (`W/H > 1.8`). Enforces horizontal partitioning along the Y-axis (`Y1 ≈ 0.35`, `Y2 ≈ 0.65`), taking the top item as Front and bottom barcode item as Back.
  3. *Stacked Tubs Grid*: Detects 2x3 grid via connected components. Splits rows at `Y = 0.50`, designating the top row for barcodes and isolating the central bottom tub (`X: 0.35–0.65`) for the front packshot.
  4. *Dual Tray Frozen Wrap*: Splits at `X = 0.50` and engages contour flood-filling to seal transparent plastic film against AI matting hollowing.
  5. *Deconstructed Carton SIFT Matching*: Computes SIFT keypoints against the Column W demo thumbnail to bound only the primary front panel, disregarding unfolded flaps.
- **Rationale**: Eliminates the catastrophic bisecting and waist-slicing caused by naive 50/50 binary splits.

### 10. Partition Subfolder Delivery Structure
- **Choice**: Structure HD outputs into source-dedicated subdirectories: `webshop_front_hd/<partition>/` and `webshop_back_hd/<partition>/`.
- **Rationale**: Provides real-time visibility into per-folder processing status and simplifies batch visual audits.

### 11. Non-Blocking Quarantine Staging & Two-Stage Healing Loop
- **Choice**: Items failing initial quality checks or component isolation are staged to `quarantine_for_retry/<partition>/` without aborting the batch. A secondary `Quarantine Healer` runs upon folder completion using relaxed SIFT thresholds and sequence fallback.
- **Rationale**: Keeps the primary pipeline fast and unobstructed while ensuring difficult edge cases receive dedicated remediation.

### 12. 5-Folder Concurrent Multi-Thread Execution Architecture
- **Choice**: Dispatch all 5 source folders (`G1`, `G2`, `G3`, `G4`, `Nyt`) as independent parallel streams using a process pool tuned to the 16 CPU cores (2–3 worker threads per partition). Excel embedding is performed in a final atomic merge step.
- **Rationale**: Slashes total execution time by ~4x compared to sequential folder processing while maintaining thread-safety and zero file write collisions.

## Risks / Trade-offs

- **[Risk] High-resolution batch processing memory overhead**
  → *Mitigation*: Stream Pass 2 in micro-batches (batch size 4–8) with explicit `gc.collect()` and PyTorch CPU/GPU cache evacuation.
- **[Risk] Apple HEIC decoding incompatibilities**
  → *Mitigation*: `pillow_heif` is verified present in the environment; automatic conversion to RGB ensures smooth downstream handling.
- **[Risk] Excel drawing anchor misalignment on different spreadsheet viewers**
  → *Mitigation*: Use openpyxl `OneCellAnchor` with explicit pixel offsets and exact row height / column width definitions matching the aspect ratio.
- **[Risk] Multi-process resource contention across 5 folders**
  → *Mitigation*: Allocate 3 worker threads per partition (15 total on 16-core CPU) and cap intermediate thumbnail proxies to 1200px to maintain memory under 12GB.

