# Tasks

## 1. Multi-Scale Pyramid & Checksum Scanner Engine

- [ ] 1.1 Implement Modulo-10 check digit validator in `src/product_mapper/zohanubis/barcode_scanner.py` for EAN-13, EAN-8, UPC-A, and ITF-14, and verify with unit test cases of valid and corrupted barcodes.
- [ ] 1.2 Implement adaptive resolution pyramid (2400px Tier 1, 1600px + CLAHE Tier 2, 3200px Tier 3, Morphological Scharr ROI Tier 4) in `_load_scaled_bgr` and `scan_single_image`.
- [ ] 1.3 Test scanner on previously failing cylindrical bottles (`IMG_0429.jpeg`, `IMG_0432.jpeg`, `IMG_0433.jpeg`, `IMG_0435.jpeg`, `IMG_0436.jpeg`) and verify 100% detection rate.

## 2. Reconciler Ablation & Zero-Guessing Architecture

- [ ] 2.1 Remove blind adjacent non-barcode assignment (`idx - 1` and `idx + 1`) from `reconciler.py` to stop false front packshot pairing.
- [ ] 2.2 Remove unverified 1-to-1 chronological timeline interpolation in `reconciler.py`; replace with strict duplicate shot coalescing and `ORPHAN` photo classification.
- [ ] 2.3 Verify that Product 3 (`G1-0003`, `G2-0003`) and subsequent products in Excel remain strictly aligned to their true physical barcodes without offset.

## 3. Visual Embedding Gate (Column W Verification)

- [ ] 3.1 Implement visual embedding extraction module in `src/product_mapper/zohanubis/quality_gate.py` using pre-trained MobileNetV3 / OpenCV DNN.
- [ ] 3.2 Add cosine similarity comparison between extracted candidate front packshots and the reference demo images in Master Excel Column W.
- [ ] 3.3 Set minimum acceptance threshold (0.82) and flag candidates below threshold as `VISUAL_MISMATCH`, preventing incorrect photo embedding.

## 4. High-Resolution Guided Alpha Matting & Contact Shadows

- [ ] 4.1 Update `src/product_mapper/zohanubis/matting_engine.py` to refine the 1024px rembg mask using guided edge filtering on the high-resolution source canvas.
- [ ] 4.2 Replace the synthetic flat gray ellipse in `src/product_mapper/zohanubis/studio_standardizer.py` with an ambient contact shadow matching product bottom geometry.
- [ ] 4.3 Verify sample deliverables have crisp boundaries without 15-30px soft bilinear blur or bottom oil-smudge artifacts.

## 5. Cross-Partition Verification & Full Regression Audit

- [ ] 5.1 Run pipeline test runner across representative sample sets from all 5 partitions (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`).
- [ ] 5.2 Validate that zero misalignments, zero false barcode assignments, and zero cascading index errors occur in the final Excel output.
