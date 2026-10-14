# Spec Delta: POS Reconciliation Engine

## Purpose

Ensures zero-hallucination barcode validation, reconciles visual products against internal POS master databases, and segregates unmatched items into review logs.

## ADDED Requirements

### Requirement: Zero-Hallucination Barcode Checksum Validation
The system SHALL validate every extracted barcode against GS1 Modulo-10 checksum rules or exact POS master catalog matching, rejecting synthetic or hallucinated barcodes.

#### Scenario: Barcode validation pass and fail
- **WHEN** a barcode is read from packaging
- **THEN** valid Modulo-10 checksums are confirmed, whereas invalid digits are flagged for secondary OCR recovery or manual review.

### Requirement: 4-Tier Difficult Barcode Recovery Pipeline
The system SHALL execute a multi-tier fallback chain for difficult images where direct scanning fails (wrinkled, curved, blurred, or glare-affected packaging):
1. **Tier 1**: Direct multi-angle barcode decoding at $0^\circ, 90^\circ, 180^\circ, 270^\circ$ with CLAHE contrast enhancement.
2. **Tier 2**: Dynamic high-resolution zoom crop on candidate barcode bounding box with Otsu binarization and unsharp sharpening.
3. **Tier 3**: Multimodal Vision Deep OCR on zoomed barcode box + Modulo-10 checksum enforcement.
4. **Tier 4**: Fallback POS reconciliation via supplier SKU, explicit packaging codes, and exact brand/name matching against Master Catalog.

#### Scenario: Recovering barcode from curved or motion-blurred packaging
- **WHEN** a raw photo cannot be decoded by standard barcode scanners
- **THEN** the system isolates the barcode region, applies contrast enhancement and deep vision transcription, verifying the checksum before assigning the barcode.

### Requirement: Multi-Tier POS Master Matching
The system SHALL match products against POS master inventories (`Products_imported_to_Shopbox_19_08_26_with_SKU.xlsx` and `Ten_hang_nhap.xlsx`) via exact barcode match, exact SKU match, and strict token-level reconciliation.

#### Scenario: Exact POS SKU assignment
- **WHEN** a product barcode or supplier SKU matches an active POS record
- **THEN** `Variant SKU` and official POS product names are mapped into the export dataset.
