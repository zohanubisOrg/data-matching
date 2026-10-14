# Proposal: Hardened Front-v3 Packshot Extraction & Final Excel 3-Column Verification

## Why
Visual audit of 1,169 generated front packshots revealed severe hidden defects (guillotine slicing of jars/pouches in 423 items, cardboard background retention in 121 items, upside-down bottle orientation, and 61 fallback items to broken front-v2) that bypassed naive geometrical thresholds. With a strict 2-hour customer delivery deadline, we must harden the extraction pipeline to permanently eliminate these failure modes and provide a rapid visual verification mechanism directly within the customer's final file (`Rabuta_master_SKU_categories_ingredients_final.xlsx`) via a side-by-side 3-column layout.

## What Changes
- **Anti-Guillotine & Axis Locking**: Restrict multi-item separation to vertical X-axis for all landscape/bench photos (`w >= h`); forbid horizontal Y-axis mid-cuts that sever jars, bottles, or pouches.
- **Cardboard Background & Chromatic Subtraction**: Completely eliminate `cv2.convexHull` that enclosed background cardboard in polygonal shapes. Replace with chromatic background subtraction that cleanly lifts transparent noodle bags and clear containers onto pure `#FFFFFF`.
- **Exif Orientation Preservation**: Anchor upright orientation strictly to camera Exif tags; eliminate artificial 180° flips driven by rotated barcodes.
- **Official Web & Source Fallback**: For products missing original camera photos (61 items) or showing only back faces, fetch high-resolution front packshots from Open Food Facts or directly parse customer front photos embedded in Column 23 of the final Excel file.
- **3-Column Verification Embedding in Final Excel**: In `Rabuta_master_SKU_categories_ingredients_final.xlsx`, insert Column 24 (`Ảnh mặt trước webshop` from `front-v3`) and Column 25 (`Ảnh mặt sau` from `back-v2`) right next to Column 23 (`Ảnh mặt trước`), preserving all original customer images for instant comparative review.

## Capabilities

### New Capabilities
- `catalog-packshot`: Comprehensive specifications for studio-grade front packshot generation, defect-free edge validation, background purity, and multi-column Excel delivery.

### Modified Capabilities
*(None - no prior specs exist in repository)*

## Impact
- **Code**: `scripts/studio_front_v3_extractor.py`, `scripts/embed_v3_images_to_excel.py`, `scripts/resolve_all_remaining_and_audit.py`.
- **Data**: Output folder `output/catalog_pairs/tagged/front-v3/` completely cleansed of guillotine cuts and cardboard leaks.
- **Delivery**: New embedded delivery file `output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx` containing original, webshop front, and back label images side-by-side.
