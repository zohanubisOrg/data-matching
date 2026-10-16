# Design

## Context

See `proposal.md` for background and problem motivation. The current implementation in `src/product_mapper/zohanubis/` relies on two brittle assumptions:
1. Contour detection treats touching products as a single entity when no background pixels exist between them.
2. Cropping and centering heuristics assume the primary front item is situated in the horizontal center of the frame (`center_x`).
3. Binary or aggressive matting cuts erode transparent glass, leafy edges, and hanging tabs, while naive soft blending introduces muddy gray halos on white canvas.

This design establishes an archetype-aware zero-gap separation engine coupled with white-bleed defringing.

## Goals / Non-Goals

**Goals:**
- Detect multi-item touching clusters across all 4 major packaging archetypes (bottles, boxes, cans, pouches) using Column W aspect ratio deviation.
- Cleave touching clusters along physical contact boundaries (gradient seams, tangent valleys, V-grooves).
- Identify and isolate the true front hero item anywhere in the frame (Left, Center, or Right) via SIFT inlier count and deep visual cosine similarity against Column W demo ground truth.
- Eliminate gray halos on `#FFFFFF` canvases while preserving delicate outer edges via White-Bleed Defringing.
- Eliminate uint8 overflow and excessive contour wiping bugs.

**Non-Goals:**
- Modifying underlying neural model weights (uses existing ONNX runtimes for BiRefNet-Lite and U2Net).
- Modifying the catalog barcode reconciliation ledger or Excel schema.

## Decisions

### Decision 1: Universal Aspect Ratio Anomaly Trigger
- **Decision**: Trigger touching-cluster analysis whenever $\frac{(W/H)_{raw}}{(W/H)_{demo}} \ge 1.6$, even if `cv2.findContours` yields only a single connected component.
- **Rationale**: An individual product unit maintains a consistent aspect ratio. Two or three touching units widen the horizontal bounding box by a factor of 1.7 to 3.2, providing an invariant geometric trigger regardless of packaging material.
- **Alternatives Considered**: 
  - Watershed segmentation: Fails on non-convex packages and smooth pouch textures.
  - Relying on contour count: Fails completely on touching objects with zero whitespace gap.

### Decision 2: Packaging Archetype Cleaving Mechanics
- **Decision**: Dispatch cleaving by packaging geometry:
  1. *Hộp (Boxes)*: Compute $\text{Profile}(x) = \sum_y |\nabla_x I(x, y)|$ using Sobel-X. Peaks indicate the vertical contact line.
  2. *Lon (Cans)*: Detect elliptical chime rims at top and bottom; track minimum-intensity vertical path between adjacent cylinders.
  3. *Chai (Bottles)*: Compute contour concavities in upper 35% height to detect the V-groove formed by adjacent bottle shoulders; project vertically to base.
  4. *Gói (Pouches)*: Locate top/bottom crimp valleys; anchor bounding box to SIFT inlier quadrilateral of the front-facing label.
- **Rationale**: Physical contact geometry differs between planar boxes, cylindrical cans, and curved bottles. Tailored cleaving prevents diagonal cuts or severed corners.

### Decision 3: Discarding `center_x` in Favor of Ground-Truth Demo Scoring
- **Decision**: Remove all hardcoded assumptions that the front hero is centered. Crop candidate bounding boxes for all detected items (Left, Center, Right) and rank them by:
  $$\text{Score}(B_i) = 0.6 \cdot \text{CosineSim}(\text{Emb}(B_i), \text{Emb}_{demo}) + 0.4 \cdot \min\left(1.0, \frac{\text{Inliers}(B_i)}{20}\right)$$
  Select the candidate with the highest composite score.
- **Rationale**: Studio photographers frequently place the front product on the left or right to showcase side or back variants simultaneously. Only visual feature matching against Column W ground truth can reliably identify the correct item.

### Decision 4: White-Bleed Blending for Halo-Free Soft Boundaries
- **Decision**: In the transition alpha zone ($10 < \alpha < 180$), evaluate Euclidean color distance to the estimated studio backdrop. If $\text{dist} < 32.0$, shift RGB values:
  $$RGB_{adj} = \frac{\alpha}{255} \cdot RGB_{orig} + \left(1 - \frac{\alpha}{255}\right) \cdot [255, 255, 255]$$
- **Rationale**: Studio backdrops are already near-white ($RGB \approx 235\text{--}250$). Shifting borderline pixels towards pure white allows soft alpha edges to dissolve seamlessly into the `#FFFFFF` canvas without dark fringing, while maintaining 100% opacity over the product interior.

### Decision 5: Color Distance Clipping & Floor Reflection Filtering
- **Decision**:
  1. Clip channel difference sum: `np.clip(diff, 0, 255).astype(np.uint8)` in `HeroCropper._get_foreground_mask`.
  2. In `StudioStandardizer`, filter secondary contours only if they are flat floor-reflection strips ($Y_{centroid} > 0.85 \times H$ and $W/H > 4.5$). Retain all other secondary contours as legitimate product components.
- **Rationale**: Prevents uint8 wrap-around where high-contrast dark objects overflowed to 0 (falsely labeled as background), and preserves multi-piece packaging like hanging loops and 2-compartment wonton trays.

## Risks / Trade-offs

- **[Risk] Severe pouch overlap where front item is partially occluded** → *Mitigation*: If the best match score across all cleaved candidates is below 0.60, mark as `UNCERTAIN_TOUCHING_OVERLAP`, route to `quarantine_for_retry/`, and log in `Zohanubis_Missing_SKU_Report.xlsx`.
- **[Risk] Extra computation for SIFT matching multiple candidates** → *Mitigation*: Evaluated only when Aspect Ratio Anomaly is triggered (est. 5–10% of catalog), keeping overall pipeline throughput fast on 16 CPU cores.

## Verification Plan

1. Verify uint8 clipping on a synthetic high-contrast image (difference sum = 256 and 512).
2. Test G2 multi-bottle scenes (`IMG_0429` and similar) where front bottle is off-center (Left or Right).
3. Test 2 touching boxes (`IMG_0885` and similar) for vertical seam cleaving.
4. Verify soft-edge white-bleed on a transparent glass bottle and cellophane bag, ensuring zero dark halo on `#FFFFFF` canvas.
