# Tasks

## 1. Hybrid Neural Matting Engine (BiRefNet-general-lite + U2Net)

- [x] 1.1 Implement dual-engine support in `src/product_mapper/zohanubis/matting_engine.py` allowing dynamic model switching between `u2net` and `birefnet-general-lite`. Verify both model sessions instantiate without error.
- [x] 1.2 Implement category-based direct BiRefNet routing in `matting_engine.py` for herbs, produce, translucent bags, hanging handles, and glass bottles. Verify routing logic flags complex packaging keywords.
- [x] 1.3 Implement Dynamic Quality Escalation in `matting_engine.py`: inspect U2Net mask solidity (< 0.90) or multi-component fragmentation (> 1) and automatically re-mat using `birefnet-general-lite`. Verify escalation triggers on test translucent packaging.
- [x] 1.4 Refactor `apply_topological_hole_filling` in `matting_engine.py` to reduce morphology kernel size from 51px to 5px, preserving sharp box corners and exterior fine boundaries. Verify sharp corners are retained on cardboard carton samples.

## 2. Strict Bijective Mapping & Zero-Duplicate Guard

- [x] 2.1 Implement `assigned_raw_photos` mutual exclusion set in `src/product_mapper/zohanubis/reconciler.py` and `front_matcher.py`, ensuring a raw studio photo is assigned to at most one catalog SKU and permanently removed from future candidate pools. Verify no photo is assigned twice.
- [x] 2.2 Implement G1 Chronological Sequence Timeline Interpolator in `reconciler.py` mapping unreadable photos (`IMG_0006`, `IMG_0007`) to their immediate sequence SKUs (`G1-0005`, `G1-0006`). Verify sequence alignment on `IMG_0001` through `IMG_0020`.
- [x] 2.3 Implement `AntiDuplicateGuard` in `src/product_mapper/zohanubis/studio_standardizer.py` to compute output image SHA-256 hashes per partition. Enforce immediate rejection and quarantine staging on any hash collision. Verify duplicate saves are blocked.

## 3. Ground-Truth Dual-Hero Orientation

- [x] 3.1 Update `src/product_mapper/zohanubis/hero_cropper.py` to split dual-hero scenes into candidate halves A and B, compute visual embeddings against Column W demo thumbnails, and assign the higher-similarity half as Front. Verify front orientation matches demo ground truth.
- [x] 3.2 Ensure `demo_img` is consistently passed to `hero_cropper.isolate_front` across `run_zohanubis_pipeline.py` and partition scripts (including G2). Verify demo image is present during G2 front isolation.

## 4. Decoupled Partition CLI & Deferred Excel Embedding

- [x] 4.1 Update `scripts/run_zohanubis_pipeline.py` to isolate folder execution when `--partition <name>` is passed, outputting solely to `webshop_front_hd/<partition>/` and `webshop_back_hd/<partition>/` without opening or modifying Excel files. Verify standalone partition run completes without Excel touching.
- [x] 4.2 Implement standalone `--embed-only` mode in `scripts/run_zohanubis_pipeline.py` to scan generated HD assets across partitions and execute batch embedding into `Rabuta_master_SKU_categories_zohanubis.xlsx` in a single atomic pass. Verify `--embed-only` generates an intact workbook with dual thumbnails.

## 5. Verification & Acceptance

- [x] 5.1 Execute verification test on G1 first 25 items (`IMG_0001`–`IMG_0025`): verify 100% unique SHA-256 hashes, zero duplicates, and correct sequential SKU assignment.
- [x] 5.2 Execute verification test on representative complex packaging items (`IMG_0427`, `IMG_0885`, `IMG_1399`): verify BiRefNet preserves sharp rectangular box corners, transparent wraps, and bottle waists.
- [x] 5.3 Verify that running a single folder partition (`--partition G1`) generates output exclusively in `webshop_front_hd/G1_original/` and leaves master Excel untouched.

