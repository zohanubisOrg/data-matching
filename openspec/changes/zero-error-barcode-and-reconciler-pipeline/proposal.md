# Proposal: Zero-Error Barcode Recognition and Robust Reconciler Pipeline

## Why

In the current photography processing pipeline across the 5 source folders (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`), the barcode scanner (`barcode_scanner.py`) hardcodes a 1600px downscale. This aggressively compresses thin barcode lines on cylindrical bottles (G2 sauces) and foil bags, causing 6 out of 8 photos in early sequences to fail barcode detection entirely.

Because photos fail barcode scanning, the reconciler (`reconciler.py`) activates a flawed "adjacent non-barcode candidate" assumption and a rigid 1-to-1 timeline gap interpolation. When photographers shoot duplicate shots (e.g. `IMG_0433` and `IMG_0434` for the same SKU) or skip items, this interpolation shifts product alignments by 1 or 2 rows—causing Product 3 (`G1-0003`, `G2-0003`) and subsequent items in Excel to be bound to completely wrong original photos with zero verification. Furthermore, downscaled 1024px bilinear matting masks and synthetic gray ellipse shadows degrade deliverable image quality. 

A hardened zero-error barcode scanning engine, coupled with cryptographic checksum verification and visual embedding ground-truth validation against Master Excel Column W, is required to eliminate 100% of barcode misidentifications and incorrect photo attachments.

## What Changes

- **Multi-Scale Pyramid Scanning**: Implement adaptive hierarchical scale passes: Pass 1 at 2400px (sweet spot for 24MP camera images), Pass 2 at 1600px + CLAHE contrast enhancement, Pass 3 at 3200px, and Pass 4 with morphological gradient ROI crop for tiny/dense barcodes.
- **Cylindrical Unwarping & Deep Learning Ensemble**: Integrate cylindrical projection unwarping for curved bottle labels (G2) and multi-engine ensemble (ZXing-C++ with fallback to OpenCV BarcodeDetector).
- **Cryptographic & Modulo-10 Checksum Enforcement**: Automatically validate Modulo-10 check digits on all EAN-13, UPC-A, and ITF-14 strings, discarding false positive patterns and specular noise.
- **Ablation of Blind Adjacent Guessing**: Remove blind adjacent non-barcode assignment (`idx - 1` / `idx + 1`) and unverified 1-to-1 timeline gap filling in `reconciler.py`. Unresolved photos are strictly classified as `ORPHAN` rather than silently misassigned.
- **Ground-Truth Visual Verification Gate**: Extract visual embeddings (MobileNetV3) from cropped packshots and verify cosine similarity against the customer's reference demo image embedded in Master Excel Column W. Flag any low-confidence match (< 0.82) as `VISUAL_MISMATCH` instead of inserting incorrect photos.
- **High-Resolution Guided Edge Refinement**: Replace 1024px bilinear mask upscaling with guided/bilateral edge filtering at native resolution, and replace synthetic flat gray ellipses with natural contact drop shadows.

## Capabilities

### New Capabilities
- `catalog-quality/zero-error-barcode-reconciler`: Implements 5-tier multi-scale barcode scanning, Modulo-10 checksum validation, zero-blind-guess reconciliation, and Column W visual embedding cross-checking.

### Modified Capabilities
<!-- None: No existing specs change their requirements -->

## Impact

- **Affected Modules**:
  - `src/product_mapper/zohanubis/barcode_scanner.py` (scale pyramid, CLAHE, checksum validator)
  - `src/product_mapper/zohanubis/reconciler.py` (strict pair resolution, orphan classification, removal of blind timeline interpolation)
  - `src/product_mapper/zohanubis/quality_gate.py` (visual similarity scoring against Column W)
  - `src/product_mapper/zohanubis/matting_engine.py` (guided filter mask upscaling)
  - `src/product_mapper/zohanubis/studio_standardizer.py` (natural floor contact shadow)
- **External Interfaces**: Master Excel catalog (`Rabuta_master_SKU_categories.xlsx`) and reshoot request exporter (`scripts/audit_and_export_reshoot_list.py`).
- **Dependencies**: Uses existing OpenCV, zxingcpp, Pillow, and lightweight torch/torchvision or OpenCV MobileNet for visual embeddings.
