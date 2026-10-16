# Tasks

## 1. Numerical Safety & Mathematical Rule Hardening

- [x] 1.1 Fix uint8 modulo overflow in `src/product_mapper/zohanubis/hero_cropper.py` by applying `np.clip(diff, 0, 255).astype(np.uint8)`. Verify on synthetic difference sums of 256 and 512 that outputs remain 255 instead of wrapping around to 0.
- [x] 1.2 Refactor secondary contour filtering in `src/product_mapper/zohanubis/studio_standardizer.py` to preserve multi-piece product geometry (quai treo, 2-compartment trays), dropping only flat floor reflections ($Y_{centroid} > 0.85 \times H$ and $W/H > 4.5$). Verify on multi-component sample that all valid components are retained.

## 2. Universal Zero-Gap Touching Object Separation

- [x] 2.1 Implement Aspect Ratio Anomaly detection in `src/product_mapper/zohanubis/hero_cropper.py` comparing raw bounding box $W/H$ against Column W demo aspect ratio. Verify anomaly flag activates when ratio exceeds 1.6.
- [x] 2.2 Implement packaging-archetype cleaving in `hero_cropper.py`: Sobel-X vertical seam peak detection for boxes, cylinder tangent shadow carving for cans, and upper 35% V-groove concavity detection for bottles. Verify cleaving splits touching clusters into distinct candidate boxes.
- [x] 2.3 Implement Demo Ground-Truth Candidate Selection in `hero_cropper.py`, ranking cleaved candidate boxes by SIFT inliers and visual cosine similarity against Column W demo. Verify system accurately selects the Front Hero when located on the Left, Center, or Right.

## 3. Soft-Edge Margin & White-Bleed Defringing

- [x] 3.1 Implement White-Bleed Defringing in `src/product_mapper/zohanubis/matting_engine.py`: in the soft transition margin ($10 < \alpha < 180$), blend pixel RGB towards `[255, 255, 255]` proportional to background proximity ($dist\_to\_bg < 32.0$). Verify borderline pixels dissolve smoothly into white.
- [x] 3.2 Update `src/product_mapper/zohanubis/studio_standardizer.py` to composite defringed RGBA onto the 2048x2048 `#FFFFFF` canvas. Verify transparent glass bottle and cellophane packaging boundaries render crisp without gray or muddy halos.

## 4. Pipeline Integration & Acceptance Verification

- [ ] 4.1 Update `scripts/run_zohanubis_pipeline.py` to integrate the enhanced touching separation engine and white-bleed defringing into partition streams. Verify pipeline executes without errors on G2 sample photography.
- [ ] 4.2 Execute acceptance benchmark suite (`scripts/test_benchmark_acceptance.py`) across touching box, multi-bottle, and complex packaging benchmarks. Verify all benchmarks achieve PASS with zero truncation and zero halos.
