# Design: Zero-Error Barcode and Robust Reconciler Pipeline

## Context

See `proposal.md` for background and motivation. The existing codebase relies on `barcode_scanner.py` (fixed downscaling to 1600px), `reconciler.py` (which blindly assumes adjacent photos without barcodes are front packshots, and fills timeline gaps with 1-to-1 assumption), `matting_engine.py` (which creates soft blurry boundaries via 1024px bilinear mask upscaling), and `studio_standardizer.py` (flat gray elliptical drop shadow).

## Goals / Non-Goals

**Goals:**
- Eliminate barcode false negatives on cylindrical bottles (G2) and shiny foil packaging (G1, G3) via adaptive multi-scale pyramid scanning.
- Prevent all sequential cascading misalignments by eliminating blind adjacent guessing and unverified timeline interpolation.
- Establish an automated visual verification gate using deep feature embeddings compared against Master Excel Column W demo thumbnails.
- Improve deliverable packshot sharpness and edge fidelity with native-resolution guided alpha matting and natural ambient contact shadow.

**Non-Goals:**
- Modifying customer physical cameras, lenses, or lighting hardware.
- Full text OCR for multi-language ingredient extraction (covered by separate downstream pipelines).
- Re-architecting the 28-column Shopify CSV exporter schema.

## Decisions

### 1. Adaptive Multi-Scale Pyramid Scanner vs Fixed-Scale Sweep
- **Decision**: Implement a 4-tiered pyramid:
  1. `Tier 1 (2400px)`: Sweet spot for 24MP phone photos where cylindrical barcodes maintain adequate bar width (>2.5px) without exceeding ZXing's window.
  2. `Tier 2 (1600px + CLAHE)`: Activated for glossy pouches with specular hot spots.
  3. `Tier 3 (3200px)`: For wide-angle distant shots.
  4. `Tier 4 (Morphological ROI)`: Scharr horizontal gradient + close filter `(21, 3)` to isolate barcode bounding box and upscale 400%.
- **Alternatives Considered**: Full-resolution (5712px) sweep across all photos—rejected due to excessive memory consumption and ZXing binarizer window overflow on high-contrast edges.

### 2. Modulo-10 Checksum & Catalog Whitelist Enforcement
- **Decision**: Validate Modulo-10 checksum for EAN-13, EAN-8, UPC-A, and ITF-14. Only barcodes existing in `Rabuta_master_SKU_categories.xlsx` (or verifiable alias with leading zeroes) are accepted.
- **Alternatives Considered**: Relaxed string acceptance—rejected because background textures and framing artifacts (e.g. `A6951957205656A`) can corrupt SKU mapping.

### 3. Ablation of Blind Adjacent Guessing & Strict Orphan Classification
- **Decision**: In `reconciler.py`, delete the `idx - 1` and `idx + 1` non-barcode assignment. If a photo has no barcode and is not confirmed as part of a dual-hero shot, classify it as `ORPHAN_UNMATCHED`.
- **Alternatives Considered**: Maintaining timeline gap interpolation with fuzzy tolerance—rejected because duplicate shots of the same SKU (e.g. `IMG_0433` and `IMG_0434` for `G2-0005`) inevitably trigger cascading row misalignment.

### 4. Visual Embedding Cross-Check Against Column W
- **Decision**: Extract 512-d feature vectors from the candidate front packshot and the Column W demo thumbnail using a lightweight pre-trained MobileNetV3 backbone. Compute cosine similarity:
  $$\text{sim}(u, v) = \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
  - $\ge 0.82$: Approved for delivery embedding.
  - $< 0.82$: Marked as `VISUAL_MISMATCH`, preventing false photo attachment.
- **Alternatives Considered**: Raw pixel MSE/SSIM—rejected because demo images differ in lighting, crop angle, and background from warehouse raw photos.

### 5. High-Resolution Guided Edge Refinement & Contact Drop Shadow
- **Decision**: Upscale 1024px rembg alpha masks to original resolution using OpenCV Guided Filter (`cv2.ximgproc.guidedFilter` or custom fast bilateral filter) guided by the original high-res grayscale image. Replace static gray ellipse with bottom-edge gaussian blur contact shadow.
- **Alternatives Considered**: Training an end-to-end 4K matting network—rejected due to inference latency and GPU VRAM constraints.

## Risks / Trade-offs

- **[Risk] Increased Scanning Time per Image** → **Mitigation**: Multi-scale passes are early-terminating. 95% of photos resolve at Tier 1 (2400px), so subsequent tiers (CLAHE, 3200px, ROI) only run on unmapped exceptions.
- **[Risk] Missing Demo Image in Column W for rare SKUs** → **Mitigation**: If Column W is empty, fallback to catalog metadata verification (brand, category, net quantity) and flag for human review rather than rejecting.
- **[Risk] Memory Spikes during 3200px / High-Res Matting** → **Mitigation**: Process photos sequentially or in bounded thread pools (max 2 workers on Windows), explicitly invoking garbage collection after each large canvas export.

## Migration Plan

1. Update `barcode_scanner.py` with multi-scale pyramid and checksum validator.
2. Refactor `reconciler.py` to remove blind adjacent pairing and integrate Column W demo visual embedding matching.
3. Update `matting_engine.py` and `studio_standardizer.py` for edge-preserving guided matting and natural contact shadow.
4. Run validation on test batches across all 5 partitions (`G1`, `G2`, `G3`, `G4`, `Nyt`) to verify 0 misalignments.
