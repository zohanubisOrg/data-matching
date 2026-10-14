# Tasks

## 1. Engine Hardening & Defect Elimination

- [x] 1.1 In `scripts/studio_front_v3_extractor.py`, enforce strict Exif upright orientation and remove all artificial 180° rotations based on barcode angle. Verify upright orientation on `8888007100310`.
- [x] 1.2 In `scripts/studio_front_v3_extractor.py`, enforce pure vertical X-axis splitting for all images where `width >= height` and completely disable horizontal Y-axis splits. Verify full jar height on `8850206161102`.
- [x] 1.3 In `scripts/studio_front_v3_extractor.py`, remove `cv2.convexHull` and implement chromatic background subtraction to eliminate cardboard paper tones behind transparent bags. Verify clean white background on `8717703638608`.
- [x] 1.4 In `scripts/studio_front_v3_extractor.py`, implement anti-guillotine flat-edge rejection and automatic high-resolution fallback to Open Food Facts for missing/corrupted items. Verify rectangular pouch on `8886390204011`.

## 2. Catalog Batch Processing & Cleansing

- [x] 2.1 Execute batch regeneration across all 1,169 catalog items writing to `output/catalog_pairs/tagged/front-v3/`.
- [x] 2.2 Verify that all 5 user-flagged items are completely healed and show 0 defects.
- [x] 2.3 Run deep vision scan across all 1,169 regenerated packshots to confirm 0 guillotine cuts and 0 cardboard background leaks.

## 3. Side-by-Side 3-Column Excel Delivery

- [x] 3.1 Update `scripts/embed_v3_images_to_excel.py` to read `Rabuta_master_SKU_categories_ingredients_final.xlsx`, insert Column 24 (`Ảnh mặt trước webshop`) and Column 25 (`Ảnh mặt sau`) adjacent to Column 23 (`Ảnh mặt trước`), and anchor thumbnails to columns X and Y.
- [x] 3.2 Execute embedding script to generate `output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx`.
- [x] 3.3 Inspect the generated Excel file to verify that all 3 image columns are populated side-by-side with intact customer originals and new webshop packshots.
