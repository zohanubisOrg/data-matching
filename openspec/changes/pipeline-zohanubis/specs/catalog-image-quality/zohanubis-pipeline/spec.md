# Spec Delta

## Purpose

Defines an end-to-end e-commerce visual processing system that ingests raw studio assets, performs zero-cache barcode verification, matches hero front perspectives against catalog thumbnails using a tiered two-pass architecture, preserves fine structural details during background matting, enforces balanced category-adaptive quality gates, and outputs an embedded dual-image master workbook.

## ADDED Requirements

### Requirement: Pure-Source Ingestion and Format Normalization
The system SHALL ingest images exclusively from the 5 designated raw source directories (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`) and the master catalog spreadsheet (`Rabuta_master_SKU_categories.xlsx`). The system SHALL NOT read from stale output directories or legacy caches. The system SHALL decode Apple iOS HEIC/HEIF images and apply EXIF orientation transforms to ensure all working images are oriented right-side up in standard 8-bit RGB color.

#### Scenario: Normalizing camera orientations and formats
- **WHEN** raw photos with EXIF rotation tags or HEIC containers are ingested from `G4-original`
- **THEN** system decodes them into standard upright RGB images without chromatic shift or orientation errors

### Requirement: Direct Multi-Angle Barcode Scanning and Reconciliation
The system SHALL scan raw high-resolution photography directly across 4 rotational angles (0°, 90°, 180°, 270°) using a direct barcode decoding engine (`zxingcpp`) with CLAHE contrast enhancement. The system SHALL preserve barcode strings with leading zeros intact. When a barcode is obscured by glare, the system SHALL apply shooting sequence proximity heuristics (pairing adjacent timestamp shots in studio batches). Images bearing verified barcodes SHALL be classified as product back photos and mapped to corresponding catalog rows. The system SHALL generate `Zohanubis_Missing_SKU_Report.xlsx` listing all master catalog SKUs that lack a verified photographic match, and SHALL quarantine photos whose barcodes do not appear in the catalog.

#### Scenario: Detecting rotated barcodes on cylindrical packaging
- **WHEN** a raw back photo has a barcode rotated 90 degrees on a can or curved bottle
- **THEN** system successfully reads the barcode, preserves leading zeros, and maps it to the matching catalog row

#### Scenario: Barcode glare fallback via sequence proximity
- **WHEN** a back photo has specular glare on the barcode but is immediately preceded or followed by an identified product shot in the studio shoot sequence
- **THEN** system validates the mapping via sequence proximity and logs the fallback method

#### Scenario: Generating missing SKU gap report
- **WHEN** a product in the master Excel catalog has no matching barcode photo in the raw sources
- **THEN** system appends the SKU, Barcode, Title, and Record ID to `Zohanubis_Missing_SKU_Report.xlsx` with status `MISSING_PHOTO`

### Requirement: Tiered Screening and Ground-Truth Front Matching
The system SHALL implement a Tiered Two-Pass screening mechanism to maximize throughput. In Pass 1, candidate images within each Record ID partition SHALL be downscaled to 512px for rapid visual feature embedding and aspect-ratio validation against the Column W demo thumbnail. The system SHALL select the single highest-scoring candidate as the front winner. When photos contain secondary clutter objects (such as companion jars or side-by-side bottles), the system SHALL isolate the primary hero item before passing it to high-resolution matting. The system SHALL permanently blacklist verified back photos from front-photo selection.

#### Scenario: Eliminating secondary companion jars
- **WHEN** a raw product photograph contains a hero jar on the right and a partial companion jar on the left
- **THEN** system detects the hero bounding box matching the catalog demo thumbnail and crops out the companion jar before matting

#### Scenario: Selecting front view matching demo thumbnail
- **WHEN** multiple non-barcode photos exist for a given product
- **THEN** system computes visual feature similarity against the Column W demo thumbnail and selects the photo with the highest similarity score

### Requirement: Detail-Preserving Matting with Topological Protection
In Pass 2, the system SHALL run deep alpha matting (`rembg` with BiRefNet or BriaRmBg backend) exclusively on the 1,169 qualified front winners. The system SHALL apply outer-contour topological hole-filling on the product boundary, ensuring that interior transparent plastic windows (such as clear packaging showing wonton pastry or jelly candies) and internal text are not hollowed out or marked as background. The system SHALL retain continuous soft alpha transitions along thin boundaries, bottle necks, and fragile edges without aliasing or jagged cuts.

#### Scenario: Preserving translucent packaging windows
- **WHEN** a product has a transparent window revealing internal contents on a white photo background
- **THEN** system preserves 100% opacity over internal contents while cleanly eliminating the external studio background

#### Scenario: Preserving thin translucent boundaries
- **WHEN** a product packaging features fine hanging loops, thin straps, or clear bottle glass
- **THEN** system retains the boundary details with soft alpha blending rather than aggressive binary clipping

### Requirement: Webshop Studio Standardization and Balanced Quality Gate
The system SHALL place the masked hero product onto a 2048 x 2048 px square canvas with a pure white background (`#FFFFFF`), centered horizontally and vertically, with the product occupying 78% to 82% of the canvas area. The system SHALL apply a subtle natural contact shadow at the base and assign the standard `sRGB IEC61966-2.1` color profile. The system SHALL evaluate quality using a balanced, category-adaptive 3-tier classification:
1. `PASS`: Meets all framing, single-component, and solidity thresholds (solidity >= 0.75 for solid packaging, >= 0.60 for spray bottles/handled items).
2. `WARNING / SOFT-PASS`: Valid products with natural geometric voids (handles, spray nozzles) or moderate edge variance; these SHALL be published to the catalog while flagged in the ledger for optional review.
3. `HARD-FAIL`: Triggered only on true technical defects (un-cropped secondary objects, severe canvas clipping > 10%, or extreme blur).
Metrics for 100% of products SHALL be recorded in `zohanubis_audit_ledger.json`.

#### Scenario: Passing clean studio packshot
- **WHEN** a processed front packshot meets standard framing, solidity, and sharpness thresholds
- **THEN** system marks the asset as `PASS` and records quality metrics in `zohanubis_audit_ledger.json`

#### Scenario: Soft-pass for product with natural handles or spray trigger
- **WHEN** a spray bottle with a trigger or a shopping bag with a handle has a solidity score of 0.68
- **THEN** system marks the asset as `WARNING_ACCEPT`, embeds it into the catalog, and records the geometric warning in the audit ledger without breaking execution

#### Scenario: Hard-failing true technical defects
- **WHEN** a processed image has unremoved companion objects or is severely clipped against canvas boundaries
- **THEN** system flags the asset with `HARD_FAIL` and schedules it for triage

### Requirement: Customer Pre-Made Packshot Ingestion and AI Matting Bypass
The system SHALL index customer-provided front product images from `source-import/customer-send-me-front-product/`. For any catalog item whose barcode matches a customer-provided image, the system SHALL bypass AI background removal (BiRefNet matting) and hero isolation. The system SHALL standardize the customer image directly onto a 2048 x 2048 px pure white `#FFFFFF` canvas, save it to both `webshop_front_hd/` and `customer_provided/`, and log the item as `PASS (Customer)`. If a raw studio photo with a matching barcode exists, the system SHALL extract the high-resolution back packaging photo into `webshop_back_hd/`.

#### Scenario: Bypassing AI matting for customer-supplied front packshot
- **WHEN** a product in the catalog has a matching barcode in `customer-send-me-front-product`
- **THEN** system standardizes the customer image to 2048x2048 canvas, skips BiRefNet neural matting, saves to `webshop_front_hd/` and `customer_provided/`, extracts the back photo from studio photography if available, and marks the decision as `PASS (Customer)`

### Requirement: Divide-and-Conquer Partition Processing for G4 and Nyt
The system SHALL support specialized partition handling strategies tailored to the studio shooting characteristics of `G4-original` and `Nyt25.09.26`:
1. **Sequential Pair Resolution (Nyt sequence `IMG_5446.HEIC`–`IMG_5558.HEIC`, G4 cartons `G4-0066`–`G4-0097`, and G4 produce pairs `G4-0005`, `G4-0006`)**: The system SHALL recognize consecutive photo sequences as dedicated front-and-back pairs. The photo without a barcode SHALL be selected as the Front Photo, and the adjacent photo bearing the barcode SHALL be designated as the Back Photo. The system SHALL NOT perform split-hero cropping on sequential pair photos.
2. **Single-Surface Bagged Produce Handling (`G4-0001`–`G4-0037`)**: The system SHALL recognize that fresh produce, herbs, and bagged food items contain only a single front packaging surface with the barcode label attached. The system SHALL use the full isolated product as the front packshot without split cropping, and SHALL apply boundary alpha softening to preserve delicate leafy contours and translucent packaging film.
3. **Carton Box Geometry Preservation (`G4-0066`–`G4-0097`)**: For large cardboard carton boxes, the system SHALL preserve linear box edges and rectangular boundaries during matting, preventing corner erosion or false void clipping.
4. **Cross-Partition Reshoot Mapping**: The system SHALL resolve barcodes from studio supplement photos in `G4-original` (`20260917_115416908` to `20260917_140212341`) globally against master catalog rows in partitions `G1`, `G2`, and `G3`.

#### Scenario: Processing sequential front and back photos in Nyt
- **WHEN** sequential photos `IMG_5447.HEIC` (no barcode) and `IMG_5448.HEIC` (barcode `6925487994878`) are evaluated in `Nyt25.09.26`
- **THEN** system assigns `IMG_5447.HEIC` intact as the front packshot and `IMG_5448.HEIC` intact as the back photo for `N25-0002`, without split cropping

#### Scenario: Processing single-surface fresh vegetable packshot in G4
- **WHEN** a bagged coriander product (`G4-0001`, `20260916_110713311_iOS.heic`) bearing barcode `8850060110360` is processed
- **THEN** system treats the full photo as the single front packshot, preserves translucent bag film, and centers it on the 2048x2048 canvas

#### Scenario: Resolving cross-partition reshoot from G4 to G1
- **WHEN** photo `20260917_115416908_iOS.heic` in `G4-original` bears barcode `8852023664248`
- **THEN** system maps the photo to `G1-0009` in partition G1 and registers it in the catalog

### Requirement: Atomic Dual-Image Excel Embedding
The system SHALL generate a new master workbook (`Rabuta_master_SKU_categories_zohanubis.xlsx`) containing two newly inserted columns adjacent to `Ảnh mặt trước`: `Ảnh webshop` (processed front view) and `Ảnh mặt sau` (verified back view). The system SHALL embed memory-optimized 400 x 400 px thumbnails directly into the spreadsheet cells, locking row height to 120pt and column widths uniformly. The system SHALL concurrently archive 2048 x 2048 px HD assets into `output/shopify-zohanubis-image/webshop_front_hd/` and `output/shopify-zohanubis-image/webshop_back_hd/`.

#### Scenario: Embedding twin images without corrupting file size
- **WHEN** 1,169 front and back images are embedded into the master workbook
- **THEN** system generates an intact `.xlsx` file under 120MB that opens smoothly in desktop spreadsheet software without XML drawing errors

### Requirement: Multi-Archetype Hero Object Isolation for Adjacent and Stacked Compositions
The system SHALL support 5 distinct structural layout archetypes for multi-view studio photographs in partitions `G1`, `G2`, and `G3`, replacing naive 50/50 binary orthogonal partitioning:
1. **Triple Vertical Panel (`TRIPLE_VERTICAL_PANEL`)**: When 3 vertical panels or packages sit side-by-side (e.g. `IMG_0885.jpeg`, `IMG_0018.jpeg`, `IMG_0500.jpeg`), the system SHALL detect 3 density columns across the X-axis (`0.0–0.34`, `0.34–0.65`, `0.65–1.0`). The system SHALL extract the central panel (`0.34–0.65`) as the Front Packshot Hero, discard background shipping cartons above the product boundary (`Y < 0.30`), and designate the barcode-bearing panel as the Back photo.
2. **Horizontal Stack (`HORIZONTAL_STACK`)**: When 2 or 3 cylindrical bottles or pouches lie horizontally across X and stack vertically across Y (e.g. `IMG_0123.jpeg`, `IMG_0427.jpeg`–`IMG_0476.jpeg`, `IMG_0155.jpeg`), the system SHALL detect horizontal orientation (`bounding box aspect ratio > 1.8`) and partition strictly along the Y-axis. The system SHALL extract the top bottle (`Y < 0.35`) as the Front Packshot and the bottom barcode bottle (`Y > 0.65`) as the Back photo, without bisecting bottle bodies.
3. **Stacked Tubs Grid (`STACKED_TUBS_GRID`)**: When round tubs are arranged in a 2x3 or 2x2 grid (e.g. `IMG_0380.jpeg`, `IMG_0381.jpeg`), the system SHALL split rows at `Y = 0.50`. The system SHALL designate the top barcode row as the Back source and isolate a single centered tub from the bottom row (`X: 0.35–0.65`) as the Front Packshot Hero, eliminating adjacent sibling tubs.
4. **Dual Tray & Clear Bag Wrap (`DUAL_TRAY_WRAPPED`)**: For dual-tray frozen food products (e.g. `IMG_1399.jpeg`–`IMG_1429.jpeg`), the system SHALL split down the center seam (`X = 0.50`), assigning the product tray as Front and the seasoning/barcode tray as Back. The system SHALL enforce topological flood-filling to protect internal contents and clear shrink-wrap from AI matting hollowing.
5. **Deconstructed Flat Carton (`DECONSTRUCTED_CARTON`)**: For unfolded flat cartons with detached blister cards (e.g. `IMG_0886.jpeg`–`IMG_0889.jpeg`), the system SHALL execute SIFT feature matching directly against the Column W demo thumbnail to isolate the primary assembled face box, discarding unfolded carton flaps.

#### Scenario: Isolating center packshot from triple vertical panel
- **WHEN** raw photo `IMG_0885.jpeg` containing 3 box panels and a background shipping carton is evaluated
- **THEN** system isolates the intact central Shan Meat Masala box without bisecting the meat dish artwork or including the top carton box, and places it on a 2048x2048 white canvas

#### Scenario: Splitting horizontal bottle stack along Y-axis
- **WHEN** raw photo `IMG_0123.jpeg` (Kikkoman 1L bottles) or `IMG_0427.jpeg` (FaThai 3 bottles) is evaluated
- **THEN** system partitions along the Y-axis, extracting the top bottle intact as Front and bottom barcode bottle as Back, with zero vertical cuts through bottle bodies

#### Scenario: Isolating single tub from 2x3 stacked grid
- **WHEN** raw photo `IMG_0380.jpeg` (Mae Pranom shrimp paste) with 6 tubs is evaluated
- **THEN** system separates the top barcode row from the bottom artwork row, isolates only the central bottom tub, and delivers a single isolated packshot

### Requirement: Partition Subfolder Delivery and Quarantine Staging Architecture
The system SHALL organize output assets into source-dedicated subdirectories under `output/shopify-zohanubis-image/`:
- `webshop_front_hd/<partition>/` and `webshop_back_hd/<partition>/` for partitions `G1_original/`, `G2_original/`, `G3_Original/`, `G4-original/`, `Nyt25.09.26/`.
When an item encounters a quality gate failure or unseparated companion objects, the system SHALL NOT abort execution. The system SHALL stage the item into `quarantine_for_retry/<partition>/` with defect metadata. Upon completing the initial pass for a partition, the system SHALL execute an automated `Quarantine Healer` utilizing relaxed SIFT matching, sequence proximity fallback, and conservative bounding boxes to heal quarantined items.

#### Scenario: Quarantine staging and automated healing
- **WHEN** a difficult product candidate fails initial component count or solidity checks
- **THEN** system stages it into `quarantine_for_retry/<partition>/`, finishes the folder batch, and runs the healing loop to resolve the defect before catalog finalization

### Requirement: 5-Folder Concurrent Multi-Thread Execution
The system SHALL execute processing across all 5 source folders (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`) simultaneously utilizing the host's 16 CPU cores and 32GB RAM. Each partition worker SHALL operate as an independent execution stream writing to its dedicated partition subdirectories without thread race conditions. Upon completion of all 5 partition streams, the system SHALL execute a thread-safe atomic merge to embed all front and back thumbnails into `Rabuta_master_SKU_categories_zohanubis.xlsx`.

#### Scenario: Running 5 folders concurrently without memory or race defects
- **WHEN** the pipeline orchestrator is launched with `--all`
- **THEN** all 5 partition streams execute concurrently with 2–3 worker threads each, completing the full catalog within the allocated resource envelope

### Requirement: Production Acceptance Sign-off Criteria
Before final sign-off, the system SHALL pass an automated verification test across a representative benchmark set:
1. `IMG_0885.jpeg` (Triple Vertical Panel): Central box extracted intact with solidity >= 0.85 and zero background carton inclusion.
2. `IMG_0123.jpeg` & `IMG_0429.jpeg` (Horizontal Stacks): Bottles extracted intact without waist slicing.
3. `IMG_0380.jpeg` (Stacked Tubs): Exactly 1 single tub extracted on 2048x2048 canvas.
4. `G4-0001` (Single-Surface Bag): Translucent bag film intact without edge erosion.
5. `N25-0002` (`IMG_5447.HEIC`/`IMG_5448.HEIC`): Intact sequential front and back pairing.
6. Partition Output Verification: All 5 partition subfolders exist and are populated.
7. Quarantine Rate: Final unresolved quarantine count <= 5% of total catalog items.

#### Scenario: Automated benchmark verification for production sign-off
- **WHEN** the acceptance benchmark suite is executed on the representative edge-case test set
- **THEN** system successfully extracts the intact central packshot from `IMG_0885.jpeg`, splits `IMG_0123.jpeg` and `IMG_0429.jpeg` along the Y-axis without slicing bottle bodies, extracts a single isolated tub from `IMG_0380.jpeg`, populates all 5 partition directories, and maintains unresolved quarantine items below 5%



