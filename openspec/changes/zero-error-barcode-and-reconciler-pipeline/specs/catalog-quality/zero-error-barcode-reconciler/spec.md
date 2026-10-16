# Spec Delta: catalog-quality/zero-error-barcode-reconciler

## Purpose

Provides a hardened zero-error barcode detection and photo reconciliation engine that eliminates false positives, prevents sequential misalignments across photo folders, and validates deliverable packshot fidelity against catalog ground truth.

## ADDED Requirements

### Requirement: Multi-Scale Pyramid Barcode Scanning
The barcode scanning system SHALL execute an adaptive multi-scale resolution pyramid across 4 discrete stages (2400px primary sweep, 1600px with CLAHE contrast enhancement, 3200px secondary sweep, and morphological Scharr gradient ROI localization) across 4 orthogonal rotation angles (0°, 90°, 180°, 270°) to detect barcodes regardless of packaging geometry or specular reflection.

#### Scenario: Barcode detected on curved bottle at high resolution
- **WHEN** a 24MP raw photo containing a cylindrical bottle (e.g., G2 sauce) is scanned
- **THEN** the system successfully reads the barcode at the 2400px pyramid tier where a 1600px downscale would compress barcode lines into unreadable artifacts

#### Scenario: Barcode detected under specular glare
- **WHEN** a glossy foil snack pouch (e.g., G1 or G3 snack) contains specular reflections washing out the barcode
- **THEN** the system triggers the 1600px CLAHE contrast enhancement tier to restore bar boundary contrast and decode the payload

### Requirement: Mathematical Checksum and Whitelist Filtering
The barcode scanning engine SHALL validate the Modulo-10 check digit for all EAN-13, EAN-8, UPC-A, and ITF-14 strings, and SHALL cross-reference all decoded candidates against the Master Catalog whitelist (including UPC/EAN leading zero normalization). Any string failing checksum validation or not present in the catalog whitelist SHALL be rejected immediately.

#### Scenario: Rejection of false positive line pattern
- **WHEN** packaging stripes or background wood grain produce an invalid candidate barcode string that fails Modulo-10 checksum
- **THEN** the system rejects the candidate and does not emit a false barcode payload

#### Scenario: Resolution of UPC-A to EAN-13 alias
- **WHEN** an item in the Master Catalog is stored as a 12-digit UPC or 13-digit EAN with leading zeros
- **THEN** the system normalizes both representations and matches the catalog product with 100% confidence

### Requirement: Zero-Guessing Reconciliation and Orphan Classification
The reconciler SHALL NOT perform blind adjacent non-barcode candidate assignment (`idx - 1` or `idx + 1`) and SHALL NOT perform chronological 1-to-1 timeline gap filling when unverified photos exist. Photos lacking readable barcodes that cannot be verified by visual similarity SHALL be explicitly classified as `ORPHAN` photos rather than misassigned to arbitrary catalog rows.

#### Scenario: Adjacent non-barcode photo is not misassigned
- **WHEN** a photo without a readable barcode is adjacent in filename sequence to a photo with a verified barcode
- **THEN** the reconciler treats the unread photo as an independent candidate rather than blindly assuming it is the front packshot of the neighboring product

#### Scenario: Duplicate shots of the same SKU do not offset subsequent products
- **WHEN** a photographer captures multiple shots of the same SKU in succession
- **THEN** the reconciler binds all valid shots to that single SKU and does not shift the alignment index of subsequent products

### Requirement: Visual Embedding Ground-Truth Verification
The reconciliation pipeline SHALL extract a visual feature embedding from each candidate front packshot and compute the cosine similarity against the customer's reference demo image embedded in Master Excel Column W. The candidate SHALL be accepted as the front packshot only if the cosine similarity is greater than or equal to 0.82; otherwise, it SHALL be flagged as `VISUAL_MISMATCH`.

#### Scenario: Successful visual verification
- **WHEN** an extracted front packshot matches the visual appearance, color palette, and packaging shape of the reference demo image in Column W with similarity >= 0.82
- **THEN** the system accepts the photo as the verified front packshot and embeds it in the deliverable catalog

#### Scenario: Rejection of visual mismatch
- **WHEN** a photo of a wrong product category (e.g. snack bag instead of soy sauce bottle) is evaluated against the Column W demo image resulting in similarity < 0.82
- **THEN** the system rejects the photo assignment, leaves the front slot empty or flagged, and emits a `VISUAL_MISMATCH` audit warning

### Requirement: Edge-Preserving High-Resolution Alpha Matting
The matting and packshot generation engine SHALL refine AI-generated matting masks at native resolution using guided edge filtering or bilateral contour refinement before background removal, and SHALL replace synthetic flat gray ellipses with natural ground-contact ambient drop shadows.

#### Scenario: Sharp packaging boundary extraction
- **WHEN** an item is extracted from a complex background
- **THEN** the deliverable mask preserves razor-sharp edges without the 15-30px soft bilinear blur caused by naive 1024px upscaling

#### Scenario: Realistic floor contact shadow
- **WHEN** the isolated product is placed on a pure white `#FFFFFF` studio canvas
- **THEN** the engine generates an ambient contact shadow matching the bottom footprint of the product without introducing flat gray elliptical artifacts under transparent packaging
