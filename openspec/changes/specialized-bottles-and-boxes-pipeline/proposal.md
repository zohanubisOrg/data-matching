# Proposal

## Why

Across existing deliverable batches (such as `G1_original`, `G2_original`, and `G3_Original`), more than 380 catalog items represent rigid liquid and food containers (glass bottles, beverage flasks, condiment jars, tin cans, and upright carton boxes). In raw studio photos (e.g. `IMG_1261`, `IMG_1268`, and `8850206111022`), photographers frequently place 2 to 3 containers side by side (front view, back view, and angle view). 

When background removal runs, the front bottle's label and body are extracted with exceptional sharpness; however, the pipeline currently lacks multi-column container topology separation and passes clusters of 2–3 containers directly onto the 2048x2048 canvas, triggering false-positive `HARD_FAIL` alerts in QualityGate. Furthermore, users require a dedicated review destination mirroring the original partition directory structure (e.g. `webshop_bottles_boxes/<partition>/`) to inspect isolated single-hero container packshots independently without overwriting existing outputs.

## What Changes

- **Automatic 3-Tier Container Classifier**: Intelligently detects bottles, jars, cans, and rigid boxes using catalog metadata (volume units such as `ml`/`L`, category keywords, container terminology), shape aspect ratios ($H/W \ge 1.6$), and horizontal lighting projection profiles.
- **Multi-Column Valley Separator**: Analyzes vertical luminance projections to detect multiple adjacent containers (2–3 bottles/cans/boxes) and carves precise vertical seam boundaries between them.
- **Front Hero Selector**: Evaluates label text, logo density, and barcode placement across detected container segments to isolate exclusively the primary front hero view.
- **Glass & Liquid Matting Guard**: Protects transparent glass necks, transparent PET liquid lines, and eliminates studio table mirror reflections.
- **Isolated Mirror Destination**: Outputs isolated single-hero packshots to a dedicated directory preserving the source partition name (e.g., `output/shopify-zohanubis-image/webshop_bottles_boxes/<partition_name>/[barcode]-front.jpg`), allowing direct side-by-side comparison without altering `webshop_front_hd`.

## Capabilities

### New Capabilities
- `catalog-image-quality/bottles-and-boxes-isolation`: Specialized identification, multi-column separation, and isolated single-hero packshot delivery for bottles, jars, cans, and boxes.

### Modified Capabilities
- None.

## Impact

- **Code modules**: Adds container classification and multi-column seam carving utilities in `src/product_mapper/zohanubis/` and execution script in `scripts/`.
- **Output paths**: Introduces `output/shopify-zohanubis-image/webshop_bottles_boxes/<partition_name>/` for non-destructive preview and verification.
- **QualityGate**: Adds adaptive inspection profile for tall container aspect ratios ($H/W$) and single-hero verification.
