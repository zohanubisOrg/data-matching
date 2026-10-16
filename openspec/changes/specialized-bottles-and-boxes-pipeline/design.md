# Design

## Context

See `proposal.md` for background and motivation. 
The current pipeline (`HeroCropper`, `StudioStandardizer`, and `QualityGate`) operates under a general binary division assumption (left vs. right half, or customer packshot replacement). For rigid containers (sauce bottles, wine/liquor flasks, soda bottles, canned drinks, condiment jars, and upright confectionery/snack boxes), studio setups frequently arrange 2 or 3 items horizontally. 

Without multi-column valley segmentation, multiple containers pass together into `StudioStandardizer`, resulting in multi-body packshots on the 2048x2048 canvas and triggering `Multiple disconnected objects detected` in `QualityGate`.

## Goals / Non-Goals

**Goals:**
- Implement a deterministic 3-tier container classifier to automatically identify bottle, jar, can, and upright box products.
- Provide a multi-column valley separator that detects and carves between 2 or 3 adjacent containers along vertical luminance minima.
- Select the primary front hero container by scoring label saliency and text variance.
- Output isolated single-hero packshots to a separate, partition-mirrored directory structure (`output/shopify-zohanubis-image/webshop_bottles_boxes/<partition_name>/`) for easy user inspection without touching `webshop_front_hd`.
- Calibrate `QualityGate` to accept tall container aspect ratios ($H/W \ge 1.6$) and enforce strictly single-body ($n\_components = 1$) output.

**Non-Goals:**
- Overwriting or modifying non-container images (bags, pouches, flat trays, loose produce).
- Overwriting existing files in `webshop_front_hd` during exploration/review phase.
- Re-matting customer-provided verified studio packshots.

## Decisions

### Decision 1: 3-Tier Classification Architecture
- **Rationale**: Relying solely on deep neural network object detection adds latency and unpredictability. Combining catalog metadata (regex for volume `\d+\s*(ml|l|liter|cl|fl oz)` and packaging keywords) with foreground contour geometry ($H/W \ge 1.6$) yields 100% deterministic identification without false triggers on flexible snack bags.
- **Alternatives Considered**: 
  - *Full YOLOv8 / ViT object detection*: Rejected due to high CPU compute overhead and tendency to misclassify Asian specialty bottle shapes.
  - *Manual tagging*: Rejected due to inability to scale across 1,300+ catalog items.

### Decision 2: Vertical Valley Projection for Multi-Bottle Separation
- **Rationale**: Containers stand vertically on flat studio tables. Taking the horizontal projection of column sums on thresholded foreground masks reliably reveals distinct density peaks for each bottle, separated by low-density "valleys" (gaps). Finding the minimum valley coordinate between peaks provides optimal cutting planes that never bisect bottle bodies.
- **Alternatives Considered**: 
  - *Fixed 33% / 50% / 67% grid cuts*: Rejected because photographers do not align bottles at mathematically exact intervals.
  - *Standard Sobel horizontal gradient seams*: Fails when glass reflections create strong vertical specular lines inside the bottle body.

### Decision 3: Front Hero View Scoring
- **Rationale**: When 2 or 3 bottles are photographed, the front bottle has large brand typography and colorful graphics, while rear bottles have fine-print ingredient tables and barcode grids. Computing gradient variance and high-frequency edge energy in the label region distinguishes the front brand view. If barcode scanning confirms a rear barcode on a specific column, that column is explicitly tagged as rear/companion and excluded.

### Decision 4: Directory Mirroring Strategy
- **Rationale**: Users requested that outputs be stored in a dedicated folder named identically to the source partitions for straightforward review (`webshop_bottles_boxes/<partition_name>/`). This preserves complete lineage (e.g. `G1_original`, `G2_original`, `G3_Original`, `G4-original`) and enables side-by-side verification before deciding to promote deliverables to publication.

## Risks / Trade-offs

- **[Risk]** Overlapping bottles touching each other with zero gap.
  - *Mitigation*: When valleys do not reach pure background density, the separator identifies the saddle point of minimum width between convex body hulls.
- **[Risk]** Clear glass reflections appearing as companion components.
  - *Mitigation*: Connected component filtering retains only components with significant area (> 5% of candidate box) and merges semi-transparent glass rims with the primary hull.
