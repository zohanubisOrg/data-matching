# Design: Hardened Packshot Extractor & Final Excel Embedding

## Context
See `proposal.md` for motivation. The pipeline operates under a strict 2-hour delivery window on Windows with Python 3.13. The customer provided a final locked workbook: `source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx` containing 1,351 rows, with Column 23 (`Ảnh mặt trước`) pre-populated with customer front photos.

## Goals / Non-Goals

**Goals:**
- Eliminate all 423 guillotine cuts, 121 cardboard leaks, upside-down bottles, and missing front fallbacks in `output/catalog_pairs/tagged/front-v3/`.
- Maintain 100% preservation of untouched `output/catalog_pairs/tagged/back-v2/` images.
- Generate `output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx` with Column 23 (Customer Original), Column 24 (Webshop Front v3), and Column 25 (Back Label v2) side-by-side.

**Non-Goals:**
- Re-processing `back-v2` images (already verified and accepted by customer).
- Overwriting the original customer source file `Rabuta_master_SKU_categories_ingredients_final.xlsx`.

## Decisions

### 1. Hardened Orientation & Splitting Strategy
- **Decision**: Read Exif orientation tag via `ImageOps.exif_transpose` and lock the orientation strictly to the physical camera. For all images where `width >= height`, enforce vertical X-axis seam splitting between $0.35$ and $0.65$. Forbid any horizontal Y-axis splitting.
- **Alternative considered**: Adaptive Y-axis splitting based on energy valleys. *Rejected* because label seams and jar neck grooves register higher contrast valleys than side-by-side jar gaps, repeatedly slicing jars across the middle.

### 2. Chromatic Background Elimination over Convex Hull
- **Decision**: Discard `cv2.convexHull`. When isolating transparent noodle bags and clear bottles, sample background tones from image borders (cardboard brown: $R > 130, G: 100..180, B: 60..140, R > G > B$) and mask them out using chromatic thresholding combined with morphology closing.
- **Alternative considered**: Pure `rembg` u2net. *Rejected* because it erases white noodles, liquid contents, and uniform cyan/teal pouch packaging.

### 3. Hierarchical Image Source Resolution
- **Decision**: 
  1. *Tier 1*: Camera photos in `output/catalog_pairs/originals/{barcode}/`.
  2. *Tier 2*: Open Food Facts API (`/api/v0/product/{barcode}.json`) for official high-resolution studio packshots.
  3. *Tier 3*: Extract customer front photos embedded in Column 23 of `Rabuta_master_SKU_categories_ingredients_final.xlsx`.
- **Alternative considered**: Falling back to `front-v2`. *Rejected* because `front-v2` contains the legacy flawed crops.

### 4. Openpyxl 3-Column Comparative Embedding
- **Decision**: Load `Rabuta_master_SKU_categories_ingredients_final.xlsx`, call `ws.insert_cols(24, 2)`, assign Column 24 (`Ảnh mặt trước webshop`) and Column 25 (`Ảnh mặt sau`), and anchor thumbnails to `X{row}` and `Y{row}` while Column 23 (`Ảnh mặt trước` at `W{row}`) remains completely intact.
- **Alternative considered**: Replacing Column 23. *Rejected* because the user explicitly requested side-by-side comparison with the customer's original front photo.

## Risks / Trade-offs

- **[Risk] High runtime exceeding the 2-hour window** → **Mitigation**: Process in parallel or selective pass: only apply web search to the ~80 missing or corrupted items, and run thumbnail batch caching for fast Excel embedding.
- **[Risk] Openpyxl memory consumption with 2,700 images** → **Mitigation**: Generate compact 120px JPEG thumbnails in `thumbnails_cache/`, keeping the final Excel file size under 150 MB and preventing Excel crashing.
