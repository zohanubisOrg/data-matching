# Spec Delta

## Purpose
Defines the functional requirements and visual quality criteria for extracting, cleansing, and validating studio-grade front packshots, as well as embedding them into the customer's final delivery Excel file for rapid side-by-side inspection.

## ADDED Requirements

### Requirement: Upright Orientation and Physical Axis Locking
The system SHALL preserve the natural physical upright orientation of all photographed products using camera sensor EXIF tags and SHALL enforce vertical separation (X-axis) for all landscape photos (`width >= height`). The system SHALL NOT rotate images 180° based on barcode orientation or apply horizontal Y-axis splits that sever standing bottles, jars, or pouches.

#### Scenario: Multi-item separation on landscape bench photos
- **WHEN** a photo has `width >= height` containing two products placed side-by-side
- **THEN** the system splits the image strictly along the vertical X-axis and extracts the full vertical height of the front product without slicing the cap, body, or base.

#### Scenario: Upright bottle orientation
- **WHEN** an original camera photo contains an upright bottle with a rotated barcode
- **THEN** the system preserves the top-to-bottom orientation with the cap positioned in the upper half of the frame.

### Requirement: Anti-Guillotine and Packaging Integrity Validation
The system SHALL verify that no product edge exhibits a straight guillotine cut where a flat cut line spans greater than 40% of the bounding dimension, and SHALL guarantee that the entire packaging contour (including white fillings and liquid contents) remains intact.

#### Scenario: Detection and rejection of sliced products
- **WHEN** an extracted product bounding edge has more than 40% continuous non-white fill along a straight perimeter row or column
- **THEN** the system flags the extraction as defective and routes the product to the high-resolution official source fallback.

### Requirement: Chromatic Background Subtraction for Transparent Packaging
The system SHALL isolate transparent bags, cellophane noodles, dried mushrooms, and clear liquid bottles by subtracting background cardboard and table tones (`R > G > B` brown/tan color signatures) rather than applying enclosing convex hulls.

#### Scenario: Transparent vermicelli background removal
- **WHEN** a transparent bag of vermicelli resting on a brown cardboard sheet is processed
- **THEN** the system eliminates the cardboard paper background, preserves the individual noodle strands, and places the clean packshot on a pure `#FFFFFF` background.

### Requirement: High-Resolution Fallback via Official Sources
The system SHALL automatically obtain authentic high-resolution front packshots from Open Food Facts or directly from the customer's pre-embedded front photos in the final Excel file for any products missing original camera files, showing only back labels, or failing integrity checks.

#### Scenario: Products with missing camera photos or only back photos
- **WHEN** a catalog product has no camera file in the originals directory or only contains back photos
- **THEN** the system retrieves the official front packshot from Open Food Facts or the customer's embedded front photo column and formats it to 2400x2400 on pure `#FFFFFF`.

### Requirement: Side-by-Side 3-Column Verification in Final Excel
The system SHALL load the customer's final Excel file (`Rabuta_master_SKU_categories_ingredients_final.xlsx`) and insert Column 24 (`Ảnh mặt trước webshop`) and Column 25 (`Ảnh mặt sau`) directly adjacent to Column 23 (`Ảnh mặt trước`), preserving all existing customer front photos in Column 23 without data loss.

#### Scenario: Comparative inspection in final workbook
- **WHEN** the delivery Excel workbook is generated
- **THEN** Column 23 contains the customer's original front photo, Column 24 contains the new 2400x2400 studio front packshot, and Column 25 contains the untouched back label photo, enabling one-glance row-by-row verification.
