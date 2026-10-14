# Spec Delta: catalog-data-reconciliation

## Purpose

Cung cấp khả năng tiền xử lý, kiểm toán số học GS1 Modulo-10, vá các bản ghi phân loại khuyết thiếu, và chuẩn hóa cấu trúc dữ liệu 2 tầng (Level 1 và Level 2) cho toàn bộ 1.659 sản phẩm siêu thị Rabuta.

## ADDED Requirements

### Requirement: Impute Missing Category Hierarchy
The system SHALL identify and impute missing Category Level 1 and Level 2 values in the customer master dataset to ensure 100% complete classification.

#### Scenario: Missing categories are imputed accurately
- **WHEN** raw dataset contains rows with missing Level 1 or Level 2 values (STT 9, 938, 1458, 1621)
- **THEN** the system imputes STT 9 Level 2 as "Nuts & Seeds", STT 938 as "Bønner" -> "Beans & Pulses", and STT 1458/1621 as "Diverse" -> "Other Asian Specialties", achieving 1.659 / 1.659 (100.0%) coverage.

### Requirement: Validate Barcode Checksum and String Formatting
The system SHALL validate 100% of product barcodes against the GS1 Modulo-10 checksum algorithm and strictly preserve leading zeros and string types without scientific notation.

#### Scenario: Barcode validation and string preservation
- **WHEN** product barcodes are processed from the master catalog
- **THEN** every barcode passes GS1 Modulo-10 verification or exact POS match, with zero scientific notation (`E+`) errors and preserved leading zeros.

### Requirement: Filter Online Deliverables and Segregate Offline Items
The system SHALL segregate the 1.659 master products into an Online active catalog of 1.347 valid shipping products and an Offline set of 312 fresh/frozen items.

#### Scenario: Accurate online filtering
- **WHEN** the catalog is partitioned for Shopify publication
- **THEN** items flagged `Online = Nej` (perishables, heavy rice sacks, raw fish/shrimp) are excluded from web store publishing.
