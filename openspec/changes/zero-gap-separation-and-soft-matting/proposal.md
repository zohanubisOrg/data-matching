# Proposal

## Why

In visual packshot production across studio partitions (specifically `G2_original`, `G1_original`, `G3_Original`, and `G4-original`), two critical failure modes degrade webshop catalog quality:
1. **Touching / Zero-Gap Multi-Item Clusters**: Studio photos frequently place multiple products (e.g. 3 standing fish sauce bottles, side-by-side spice boxes, touching tin cans, or overlapping seasoning pouches) directly adjacent with zero whitespace gap. Naive contour detection merges them into a single blob, bypassing hero isolation and resulting in multi-item clutter on the final single-SKU deliverable. Furthermore, current heuristics hardcode an assumption that the hero item is in the center (`center_x`), causing severe errors when the front hero is located on the left or right.
2. **Aggressive Edge Erosion vs. Dirty Halo Trade-off**: Aggressive alpha thresholding or morphological erosion shaves off delicate glass bottle boundaries, transparent plastic wrap crinkles, and quai treo / hanging tabs. Conversely, uncalibrated soft boundaries leave unsightly gray studio halos on `#FFFFFF` canvases. Concurrently, an integer overflow bug in `HeroCropper._get_foreground_mask` (`diff.astype(np.uint8)`) causes high-contrast dark objects to be erroneously classified as background.

This change delivers a **Universal Zero-Gap Touching Separation Engine** for all packaging archetypes (bottles, boxes, cans, pouches) guided by Column W demo ground-truth, establishes a **Soft-Edge Defringing & White-Bleed Blending Pipeline** to preserve translucent packaging margins, and closes mathematical edge-case loopholes across the cropping and standardizing modules.

## What Changes

- **Universal Zero-Gap Touching Object Separation (Bottles, Boxes, Cans, Pouches)**:
  - Implements **Aspect Ratio Anomaly Detection**: Compares candidate bounding box aspect ratio against the Column W demo image ($AR_{raw} \ge 1.6 \times AR_{demo}$). Flags multi-item touching clusters even when contour separation yields a single connected component.
  - Implements **Archetype-Specific Boundary Cleaving**:
    - *Boxes / Cartons*: Vertical high-gradient Sobel-X seam detection along straight contact lines.
    - *Cans / Tins*: Dual/triple rim detection and cylinder tangent shadow valley carving.
    - *Bottles*: V-groove concavity detection at the bottle shoulder/neck level.
    - *Pouches / Bags*: Heat-seal crimp valley and SIFT-anchored top-sheet boundary extraction.
  - Implements **Demo Ground-Truth Feature Localization**: Discards hardcoded `center_x` heuristics. Evaluates each candidate partition (Left, Center, Right) against Column W demo thumbnails via SIFT inliers and cosine visual embeddings, selecting strictly the true front hero item.
- **Soft-Edge Defringing & White-Bleed Blending**:
  - Implements a soft alpha transition zone ($15 \le \alpha \le 235$) preserving glass reflections, fine leafy herb tips, and clear plastic seams.
  - In the transition margin ($10 < \alpha < 180$), executes **White-Bleed Defringing**: whenever pixel colors are close to the light studio backdrop (`dist_to_bg < 32`), color luminance is blended towards `[255, 255, 255]` so that background residue seamlessly dissolves into the `#FFFFFF` canvas without dark or muddy halos.
- **Defensive Bug Fixes & Rule Hardening**:
  - Fixes uint8 modulo overflow in `HeroCropper._get_foreground_mask`: Replaces `diff.astype(np.uint8)` with `np.clip(diff, 0, 255).astype(np.uint8)`, preventing high-contrast dark products from wrapping around to zero and being falsely classified as background.
  - Hardens `StudioStandardizer.standardize`: Replaces blanket deletion of secondary contours with geometric floor-reflection filtering (discarding only flat horizontal bands with $Y > 0.85 \times H$ and $W/H > 4.5$), preserving legitimate multi-piece products (quai treo, 2-compartment wonton trays, attached accessories).
  - Enforces mutual exclusion in `FrontViewMatcher` when Column W demo images are absent, staging uncertain items to quarantine rather than duplicating assignments.

## Capabilities

### New Capabilities
- `catalog-image-quality/zero-gap-separation-and-soft-matting`: Defines requirements for universal zero-gap touching product separation across packaging archetypes, demo-guided left/center/right front hero selection, soft-edge white-bleed defringing, and robust foreground color distance clipping.

### Modified Capabilities
*(None)*

## Impact

- **Affected Code**: `src/product_mapper/zohanubis/hero_cropper.py`, `src/product_mapper/zohanubis/studio_standardizer.py`, `src/product_mapper/zohanubis/matting_engine.py`, `src/product_mapper/zohanubis/front_matcher.py`, and `scripts/run_zohanubis_pipeline.py`.
- **Deliverables**: Eliminates multi-object clutter on touching-product shots in `webshop_front_hd/`, prevents edge erosion on transparent bottles and pouches, and ensures 100% clean white `#FFFFFF` packshot backgrounds.
- **Dependencies**: Leverages existing standard stack (`cv2`, `numpy`, `PIL`, `torchvision`, `rembg`). Zero new third-party dependencies.
