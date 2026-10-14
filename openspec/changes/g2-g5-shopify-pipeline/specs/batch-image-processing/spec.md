# Spec Delta: Batch Image Processing

## Purpose

Provides high-throughput multi-format packaging image ingestion, smart bounding box crop with margin padding, and auto-upright portrait orientation normalization.

## ADDED Requirements

### Requirement: Support for Apple iOS HEIC Image Format
The system SHALL ingest and decode high-resolution `.HEIC` and `.heic` images alongside `.jpeg` and `.jpg` image formats without manual conversion.

#### Scenario: Ingesting HEIC warehouse photo
- **WHEN** a batch containing `.heic` or `.HEIC` images is processed
- **THEN** the image is opened seamlessly, EXIF tags are preserved, and resolution is maintained for vision analysis.

### Requirement: Smart Front Packaging Crop with Adaptive Margin Padding & Original Resolution
The system SHALL isolate ONLY the front packaging view from raw photos (including 2-sided front-and-back side-by-side photos), applying 3% to 5% adaptive margin padding around the perimeter, and exporting the crop at full original sensor resolution with maximum image fidelity without downsampling.

#### Scenario: Cropping front package from two-sided photo
- **WHEN** 2D coordinates `[ymin, xmin, ymax, xmax]` are detected for the front view in a multi-view photo
- **THEN** only the front packaging is isolated, background noise is handled, boundaries are padded safely, and full native resolution is preserved.

### Requirement: Auto-Upright Portrait Mode Normalization & Anti-Inversion
The system SHALL ensure cropped front images are strictly oriented upright in vertical portrait mode (Height > Width), detecting and correcting orientation angles ($0^\circ, 90^\circ, 180^\circ, 270^\circ$) so no products appear upside-down or sideways.

#### Scenario: Correcting horizontal or upside-down packaging photos
- **WHEN** a product is photographed horizontally or inverted
- **THEN** the system rotates the crop to stand vertically upright before saving canonically as `<barcode>.jpg` and `<barcode>.webp`.

### Requirement: Quality Acceptance Audit & Automated Re-Crop Protocol
The system SHALL perform automated quality acceptance audits on all generated crops to detect faulty crops (such as cut-off product edges, clipped branding, truncated weight labels, or clipped bottle caps/bottoms), automatically re-running the bounding box detection with expanded adaptive margins and re-generating clean assets until 100% acceptance criteria is met.

#### Scenario: Detecting and repairing a clipped product crop
- **WHEN** an initial crop cuts off product text or package boundaries
- **THEN** the QA audit flags the item, re-computes expanded bounding coordinates from the raw source photo, regenerates the `<barcode>.jpg` crop, and updates master datasets.
