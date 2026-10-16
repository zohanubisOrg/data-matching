# Proposal: Web Packshot Harvesting & Gemini Enhancement Pipeline

## Why

Following the comprehensive catalog audit, **722 SKUs** are currently marked as requiring reshooting (`Rabuta_Customer_Reshoot_Request.xlsx`). Requesting the merchant to manually reshoot all 722 items imposes severe operational delay, cost, and friction. 

Since the majority of these items are standardized imported Asian FMCG products with recognized international EAN/UPC barcodes, official high-resolution, pre-isolated packshots exist online (via OpenFoodFacts, European wholesale distributors, and Google Images). Implementing an automated multi-tier web harvester with Gemini semantic verification, Google Images full-resolution extraction, and a 4-layer quality assurance pipeline ($2048 \times 2048\text{ px}$, Chroma 4:4:4, Laplacian score $\ge 50.0$) can recover an estimated 40%–60% (300–450 items) into production-ready webshop packshots, dramatically reducing the customer's reshooting workload to only truly unfindable items.

## What Changes

- **Automated Multi-Tier Web & Google Images Harvester**: Queries OpenFoodFacts API, wholesale distributor networks, and Google Images (extracting original full-resolution images via `tbm=isch&tbs=isz:l`, discarding low-res thumbnails).
- **Fail-Safe Gemini Semantic & Visual Verification**: Validates downloaded candidate images against Master Catalog metadata (Brand, Name, Variant/Flavor, Weight) and aspect ratio anchors from Column W demo photos to reject wrong flavors, sizes, or packaging versions.
- **Backtracking & Candidate Retry Queue**: Automatically backtracks to alternate candidates or query mutations (`"{barcode}" "{brand}"`, `"{brand}" "{variant}" "{net_qty}"`) if the primary candidate fails verification; safely aborts to the reshoot list if no candidate passes.
- **Lightweight 2048x2048 Studio Canvas Standardization**: Bounding-box trims pre-matted web images, centers them on pure white `#FFFFFF` canvases with standard 84% product scale, bypassing heavy neural matting when backgrounds are already clean.
- **4-Layer High-Definition Quality Enhancement**:
  - Edge-preserving Bilateral Filter to remove JPEG compression artifacts without blurring text.
  - Lanczos-4 mathematical resampling for smooth, anti-aliased scaling to $2048 \times 2048\text{ px}$.
  - Adaptive Unsharp Masking (`radius=1.2`, `amount=130%`) to sharpen brand typography, nutritional text, and borders.
  - JPEG Quality 95 with Chroma Subsampling 4:4:4 (`subsampling=0`) to preserve 100% color contrast on labels.
  - Post-save Laplacian sharpness inspection (requiring variance $\ge 50.0$); auto-aborts to reshoot if blurry.
- **Canonical Output Standardization**: Saves approved packshots strictly as `{barcode}-front.jpg` in `output/shopify-zohanubis-image/webshop_front_hd/Front/`.
- **Automated Catalog Re-Audit & Deliverable Sync**: Re-runs audit reconciliation to transition recovered products to `PASS`, embed them in `Rabuta_master_SKU_categories-image.xlsx`, and shrink `Rabuta_Customer_Reshoot_Request.xlsx` to the reduced set.

## Capabilities

### New Capabilities
- `catalog-quality/web-harvest-and-enhancement`: Automated querying, verification, canvas standardization to 2048x2048 px, and catalog reconciliation for webshop packshots.

### Modified Capabilities
- `catalog-quality/audit-and-remediation`: Enhanced to ingest web-harvested HD packshots and dynamically decrement the active customer reshoot deliverable count.

## Impact

- **New Scripts/Modules**: `scripts/harvest_and_enhance_webshop_packshots.py` and supporting harvester module in `src/product_mapper/harvest/`.
- **Storage/Artifacts**: Generates verified `{barcode}-front.jpg` images in `webshop_front_hd/Front/`.
- **Deliverables**: Directly shrinks `Rabuta_Customer_Reshoot_Request.xlsx` from 722 items down to only unrecoverable items, and enriches `Rabuta_master_SKU_categories-image.xlsx` and `Shopify_Rabuta_Webshop_Online_Only.csv`.
- **Dependencies**: Uses `requests`, `beautifulsoup4`, `Pillow`, `openpyxl`, and existing Gemini Vision client configurations.
