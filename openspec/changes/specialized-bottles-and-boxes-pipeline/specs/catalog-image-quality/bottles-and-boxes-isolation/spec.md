# Spec Delta

## Purpose

Enables automated recognition, multi-column separation, and isolated single-hero studio packshot delivery for rigid containers including bottles, jars, cans, and upright boxes into a dedicated partition-mirrored directory.

## ADDED Requirements

### Requirement: Automated Multi-Tier Container Detection
The pipeline SHALL determine whether a candidate image belongs to the rigid container class (bottles, jars, cans, upright boxes) by synthesizing catalog metadata, bounding geometry aspect ratios, and horizontal projection signatures.

#### Scenario: Detection via volume unit metadata
- **WHEN** product title contains liquid volume indicators such as "ml", "L", "liter", "cl", or "fl oz"
- **THEN** pipeline marks the SKU as a rigid container and activates the container isolation workflow

#### Scenario: Detection via packaging keywords and category
- **WHEN** product title or category contains terms such as "sauce", "syrup", "vinegar", "juice", "drink", "oil", "bottle", "jar", "can", "tin", or "box"
- **THEN** pipeline marks the SKU as a rigid container candidate

#### Scenario: Visual confirmation via geometric aspect ratio
- **WHEN** product foreground contour exhibits height-to-width aspect ratio $H/W \ge 1.6$ with symmetric vertical silhouettes
- **THEN** pipeline confirms container topology and enables specialized tall-aspect ratio standardizer settings

### Requirement: Multi-Column Container Valley Separation
The pipeline SHALL analyze the horizontal projection of vertical foreground density to identify and separate multiple adjacent containers standing side-by-side in a single raw frame.

#### Scenario: Two adjacent bottles photographed together
- **WHEN** horizontal projection shows two distinct peak regions separated by a vertical valley with low foreground density
- **THEN** pipeline carves the vertical seam along the valley minimum and extracts the candidate regions independently

#### Scenario: Three adjacent bottles photographed in a row
- **WHEN** horizontal projection shows three distinct peaks across the frame
- **THEN** pipeline isolates all three container segments without waist-slicing or partial-body clipping

### Requirement: Primary Front Hero Selection
The pipeline SHALL evaluate all isolated container candidates in a multi-container photo and select exclusively the primary front hero view.

#### Scenario: Selection of front label view over rear specification view
- **WHEN** one container displays brand typography and high central text contrast while companion containers display ingredient tables or barcode grids
- **THEN** pipeline selects the front brand label container as the single hero packshot and discards companion rear/angle views

### Requirement: Dedicated Partition-Mirrored Output Destination
The pipeline SHALL output the isolated container deliverables into a dedicated parent folder while strictly preserving the source partition directory name.

#### Scenario: Output directory mirroring
- **WHEN** processing containers originating from partition `G1_original`, `G2_original`, `G3_Original`, or `G4-original`
- **THEN** deliverable packshots SHALL be written to `output/shopify-zohanubis-image/webshop_bottles_boxes/<partition_name>/[barcode]-front.jpg` without modifying `output/shopify-zohanubis-image/webshop_front_hd/<partition_name>/`

### Requirement: QualityGate Adaptive Profile for Containers
The QualityGate inspection SHALL adapt its component count and solidity thresholds for tall rigid containers.

#### Scenario: Clean single-hero container evaluation
- **WHEN** an isolated container packshot is evaluated by QualityGate
- **THEN** QualityGate SHALL verify that exactly one prominent connected component exists ($n\_components = 1$) and accept tall aspect ratios up to $H/W = 3.5$ without aspect distortion penalties
