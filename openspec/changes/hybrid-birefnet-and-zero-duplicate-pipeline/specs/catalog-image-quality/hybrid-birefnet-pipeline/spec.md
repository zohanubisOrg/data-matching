# Spec Delta

## Purpose

Defines visual processing behavior for zero-duplicate bijective studio photography mapping, chronological sequence alignment, demo-verified dual-hero orientation, hybrid neural matting (BiRefNet-general-lite and U2Net) with auto-escalation, isolated partition runs, and deferred Excel embedding.

## ADDED Requirements

### Requirement: Zero-Duplicate Bijective Output Guarantee
The system SHALL enforce a strict bijective mapping between raw studio photography and catalog SKUs: each raw photograph file SHALL be assigned to at most one catalog product. Once a photograph is assigned to a product, the system SHALL permanently exclude that photograph from the candidate pool for all other catalog products. Before saving any generated packshot into `webshop_front_hd/<partition>/`, the system SHALL compute its cryptographic hash (SHA-256) and verify that no identical image has been previously generated in that partition. If a hash collision is detected, the system SHALL immediately reject the duplicate and route the defective SKU to quarantine.

#### Scenario: Preventing duplicate image reuse across multiple SKUs
- **WHEN** raw photo `IMG_0006.jpeg` has already been assigned to SKU `G1-0005`
- **THEN** system excludes `IMG_0006.jpeg` from all candidate sets for subsequent SKUs (e.g. `G1-0036`, `G1-0037`), ensuring zero cross-product image duplication

#### Scenario: Blocking save on identical output image hash
- **WHEN** an output packshot for a SKU yields an identical SHA-256 hash to an already generated packshot in the partition directory
- **THEN** system flags an anti-duplicate violation, prevents writing the redundant file, and logs the incident in quarantine

### Requirement: Chronological Sequence Timeline Interpolation for G1
For partition `G1_original`, the system SHALL recognize the 1-to-1 chronological shooting timeline between sequential studio raw files (`IMG_0001.jpeg` through `IMG_0460.jpeg`) and catalog rows (`G1-0001` through `G1-0460`). When barcode scanning fails on an individual studio photo due to specular glare or packaging curvature, the system SHALL interpolate the product identity strictly using its immediate chronological predecessor and successor photos in the shoot sequence. The system SHALL NOT perform global or wide-window visual drift matching across unrelated catalog partitions.

#### Scenario: Chronologically resolving unreadable barcode in G1
- **WHEN** photo `IMG_0006.jpeg` fails initial barcode detection but is situated immediately between `IMG_0005.jpeg` (mapped to `G1-0004`) and `IMG_0008.jpeg` (mapped to `G1-0007`)
- **THEN** system maps `IMG_0006.jpeg` specifically to `G1-0005` based on sequence timeline interpolation and eliminates it from any distant candidate matches

### Requirement: Ground-Truth Dual-Hero Front and Back Orientation
When evaluating multi-view studio photographs in partitions `G1`, `G2`, and `G3` containing both front and back packshot views, the system SHALL partition the photograph into candidate halves (left/right for landscape, or top/bottom for stacked items) and compute visual feature embeddings for both halves against the Column W ground-truth demo thumbnail. The half exhibiting the higher cosine similarity score to the demo thumbnail SHALL be designated as the Front Packshot Hero, and the opposite half SHALL be designated as the Back Packshot Hero. The system SHALL NOT rely exclusively on the horizontal position of detected barcodes (`bc_x`) to infer front orientation.

#### Scenario: Selecting true front face on inverted barcode placement
- **WHEN** a packaging photo features a front hero on the right side and an import barcode sticker on the left side
- **THEN** system compares visual feature embeddings of both halves with Column W demo, identifies the right half as the true front hero, and avoids front/back inversion

### Requirement: Hybrid Matting Engine with Dynamic Quality Escalation
The system SHALL operate a dual-engine hybrid neural matting architecture:
1. **Complex Packaging Mode (`birefnet-general-lite`)**: For products featuring transparent cellophane windows, produce/herbs/vegetables, glass bottles, hanging sombrero loops, or complex packaging margins, the system SHALL execute deep matting using `birefnet-general-lite` at native 1024x1024 resolution to retain sharp box vertices, plastic wrap folds, and delicate packaging contours.
2. **Standard Packaging Mode (`u2net`)**: For standard, opaque, high-contrast packaging (solid carton boxes, tin cans, opaque plastic jars), the system SHALL execute fast matting using `u2net` (sub-second per image).
3. **Dynamic Quality Escalation**: When standard `u2net` matting is executed, the system SHALL inspect the generated alpha mask. If the mask exhibits interior hollowing (solidity < 0.90) or multi-component fragmentation, the system SHALL automatically escalate the image to `birefnet-general-lite` for high-fidelity rematting.
4. **Morphological Filter Restraint**: The system SHALL constrain morphological closing filters to a maximum kernel size of 5x5 px, preventing rounding of rectangular box corners or blurring of package boundaries.
5. **Customer Packshot Bypass**: The system SHALL bypass AI neural matting for all 379 verified customer packshots, standardizing them directly onto 2048x2048 white canvases.

#### Scenario: Escalating hollowed translucent packaging to BiRefNet
- **WHEN** an initial U2Net matting pass on a translucent packaging window produces a hollowed mask with solidity < 0.90
- **THEN** system automatically escalates the product to `birefnet-general-lite`, regenerating a solid 1024px mask with preserved packaging borders and transparent window details

#### Scenario: High-speed processing for opaque tin can
- **WHEN** an opaque tin can product is evaluated
- **THEN** system executes fast U2Net matting in under 1 second, validates mask solidity >= 0.95, and approves the packshot without unnecessary BiRefNet latency

### Requirement: Decoupled Single-Folder Partition Execution
The system SHALL support standalone folder execution via `--partition <name>` (e.g. `G1`, `G2`, `G3`, `G4`, `Nyt`). During folder execution, the system SHALL write generated high-resolution assets exclusively to `output/shopify-zohanubis-image/webshop_front_hd/<partition>/` and `webshop_back_hd/<partition>/`. The system SHALL NOT attempt to modify, lock, or embed images into the master Excel workbook during single-folder partition execution.

#### Scenario: Running single folder partition G1
- **WHEN** the operator runs `run_zohanubis_pipeline.py --partition G1`
- **THEN** system processes all products in `G1_original`, outputs high-resolution assets directly into `webshop_front_hd/G1_original/` and `webshop_back_hd/G1_original/`, records audit logs, and exits without opening or modifying master Excel files

### Requirement: Deferred Standalone Master Excel Embedding
The system SHALL provide a dedicated standalone command flag (`--embed-only`) that inserts and embeds dual 400x400 px thumbnails (`Ảnh webshop` and `Ảnh mặt sau`) into `Rabuta_master_SKU_categories_zohanubis.xlsx`. The system SHALL execute this command as an independent post-processing operation only after the operator has visually audited and confirmed that the target threshold of 1,169 front packshots has been produced across the partition subdirectories.

#### Scenario: Executing standalone batch embedding on verified deliverables
- **WHEN** the operator invokes the pipeline with `--embed-only` after all 5 partitions are completed and verified
- **THEN** system scans existing files in `webshop_front_hd/` and `webshop_back_hd/`, embeds 400x400 thumbnails into `Rabuta_master_SKU_categories_zohanubis.xlsx` at 120pt row height in a single atomic pass, and creates a backup of the catalog
