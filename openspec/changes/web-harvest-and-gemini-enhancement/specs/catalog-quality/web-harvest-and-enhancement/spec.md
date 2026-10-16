# Spec Delta: Web Harvest and Enhancement

## Purpose

Enables automated multi-tier internet harvesting, semantic validation, and canvas standardization for missing or defective product packshots to minimize customer reshoot overhead.

## ADDED Requirements

### Requirement: Multi-Tier Barcode Web & Google Images Harvesting
The system SHALL query external data sources in prioritized tiers (Tier 1: OpenFoodFacts API, Tier 2: Wholesale Asian distributor catalogs, Tier 3: Google Images deep original image extraction) using exact-match barcode queries (`"{barcode}"`) and structured metadata fallbacks (`"{brand}" "{variant}" "{net_qty}"`). For Google Images, the system SHALL enforce `tbs=isz:l` (large images only) and extract the original full-resolution image URL from the embedded JavaScript payload, discarding low-resolution gstatic thumbnails.

#### Scenario: Exact OpenFoodFacts EAN Match
- **WHEN** an item's EAN-13 barcode exists in the OpenFoodFacts database with front packshot imagery
- **THEN** the system downloads the highest-resolution candidate image and skips search engine queries.

#### Scenario: Fallback to Google Images Deep Extraction
- **WHEN** Tier 1 yields no valid images for an EAN barcode
- **THEN** the system queries Google Images with `"{barcode}"`, extracts the original host URL (ignoring gstatic thumbnails), and downloads candidate images with width and height $\ge 600\text{ px}$.

### Requirement: Gemini Semantic Validation and Visual Anchoring
The system SHALL evaluate candidate images using Gemini Vision against Master Catalog metadata (Brand, Name, Variant/Flavor, Net Quantity) and compare aspect ratios against the Column W reference demo image to reject false positives.

#### Scenario: Rejection of Mismatched Flavor or Variant
- **WHEN** a candidate image matches the brand but depicts a different flavor or variant than the catalog specification
- **THEN** Gemini Vision flags `flavor_matches: false` and the candidate is rejected, triggering candidate backtracking.

#### Scenario: Aspect Ratio Anomaly Rejection
- **WHEN** a candidate image's bounding box aspect ratio deviates by more than 25% from the Column W demo packaging anchor
- **THEN** the candidate is flagged as an invalid size format and rejected.

### Requirement: Webshop Packshot Studio Quality & Human Hand Exclusion
The system SHALL strictly enforce e-commerce studio packshot criteria, automatically rejecting any candidate image containing human body parts, casual domestic room backgrounds, crumpled packaging, or harsh smartphone flash glare.

#### Scenario: Rejection of Human Hands or Fingers Holding Product
- **WHEN** a candidate image contains human skin-colored clusters (> 3% total ratio or > 1% border perimeter contact) or is flagged by Gemini Vision as being held by a person
- **THEN** the system immediately rejects the candidate, logs `Human hand/body detected holding product`, and aborts candidate to reshoot list.

#### Scenario: Rejection of Casual / Domestic / Non-Studio Backgrounds
- **WHEN** an image's border background is not pure studio white (perimeter mean brightness < 236.0 or std > 22.0) and is not transparent
- **THEN** the system rejects the image as a non-studio consumer snapshot.

### Requirement: Studio Canvas Standardization (2048x2048 px)
The system SHALL normalize approved candidate images onto a square $2048 \times 2048\text{ px}$ pure white background (`#FFFFFF`), scaling the product to occupy $84\% \pm 2\%$ of the canvas dimension, bypassing neural network matting when background pixels are already clean white (RGB $\ge 248$) or transparent, and save strictly as `{barcode}-front.jpg`.

#### Scenario: Centering Pre-Matted Images onto Webshop Canvas
- **WHEN** an approved candidate image has a clean white or transparent background
- **THEN** the system auto-crops the product bounding box, centers it with 164 px standard margins on a $2048 \times 2048$ canvas, and writes to `output/shopify-zohanubis-image/webshop_front_hd/Front/{barcode}-front.jpg`.

### Requirement: 4-Layer High-Definition Quality Enhancement
The system SHALL enhance candidate images using an edge-preserving bilateral filter to suppress JPEG compression artifacts, Lanczos-4 mathematical resampling for scaling, adaptive unsharp masking (`radius=1.2`, `amount=130%`) for text crispness, JPEG encoding with Chroma Subsampling 4:4:4 (`quality=95`, `subsampling=0`), and a post-save Laplacian sharpness inspection requiring a variance score $\ge 50.0$.

#### Scenario: Passing Crisp Packshot with Laplacian Score
- **WHEN** an enhanced $2048 \times 2048$ image is written to disk and achieves a post-save Laplacian score $\ge 50.0$
- **THEN** the image is validated as production-ready and recorded as a successful harvest.

#### Scenario: Aborting Blurry Upscaled Image
- **WHEN** an upscaled image achieves a post-save Laplacian score $< 50.0$
- **THEN** the system rejects the file, deletes the low-quality output, and retains the SKU in the customer reshoot deliverable.

### Requirement: Dynamic Reshoot List Reconciliation
The system SHALL synchronize newly generated `{barcode}-front.jpg` images back into the Master Catalog and decrement the active count in `Rabuta_Customer_Reshoot_Request.xlsx`.

#### Scenario: Transition Recovered SKU from Reshoot to PASS
- **WHEN** `{barcode}-front.jpg` is generated and verified for a previously flagged reshoot product
- **THEN** the product's status transitions from `RESHOOT` to `PASS`, Column X `Ảnh webshop (Front)` receives the new embedded thumbnail, and the row is excluded from the customer reshoot spreadsheet.
