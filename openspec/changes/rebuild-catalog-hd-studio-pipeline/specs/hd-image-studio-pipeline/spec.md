# Spec Delta: hd-image-studio-pipeline

## Purpose

Cung cấp pipeline bóc tách ảnh mặt trước sản phẩm đạt chuẩn High Definition Studio từ 1.659 ảnh kho gốc, tích hợp AI Saliency, viền an toàn chống lẹm mép, căn giữa canvas nền trắng, và cổng kiểm toán chất lượng tự động.

## ADDED Requirements

### Requirement: EXIF Orientation and Color Space Normalization
The system SHALL correct EXIF orientation tags to guarantee upright portrait orientation and normalize color profile to standard sRGB.

#### Scenario: Normalizing camera orientation
- **WHEN** raw warehouse photos captured on mobile devices are ingested
- **THEN** images are rotated upright according to EXIF tags before any cropping or segmentation begins.

### Requirement: Dual-Face Segmentation and Front View Selection
The system SHALL analyze the two packaging faces in the raw warehouse photo and select the authentic Front face (brand logo, product name) while rejecting the Back face (barcode, nutrition table).

#### Scenario: Correct front face isolation
- **WHEN** a photo contains both front and back packaging sides
- **THEN** the system identifies the back side by detecting the barcode / dense text block, and designates the opposing side as the front face.

### Requirement: Bounding Box Extraction with Safe Margin
The system SHALL extract the front product packaging with an intentional safety margin (+6% to +8%) to prevent any cropping of corners, edges, caps, or brand text.

#### Scenario: Safe packaging extraction
- **WHEN** packaging boundaries are detected by AI saliency / contour analysis
- **THEN** the crop box is expanded symmetrically by 6-8%, ensuring zero cutoff across all packaging boundaries.

### Requirement: Studio Canvas Standardization and Automated QC
The system SHALL place the extracted product onto a pure white canvas (`#FFFFFF`) with center alignment, and execute an automated quality control check verifying dimensions and aspect ratio.

#### Scenario: Studio canvas and QC verification
- **WHEN** the front crop is finalized
- **THEN** it is placed onto a standardized canvas with minimum height 1200px, aspect ratio height >= width, and saved as high-resolution `<barcode>.jpg` with automated validation passing 100%.
