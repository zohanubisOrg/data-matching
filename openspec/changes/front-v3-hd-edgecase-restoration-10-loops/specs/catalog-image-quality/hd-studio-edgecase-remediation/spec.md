# Native-source full-catalog packshot reconstruction

## Purpose

Provide authentic, sharp webshop front images for every Rabuta catalog record by selecting complete retail units from verified native photographs, preserving details and explicitly reporting unresolved sources rather than inventing content.

## ADDED Requirements

### Requirement: Full catalog scope and identity reconciliation
The system SHALL evaluate every authoritative catalog record, including previously unflagged or auto-passed records, using Record ID, workbook row and barcode as text. Examples and earlier queues MUST NOT limit scope. Conflicting identities and missing records SHALL remain in final reconciliation.

#### Scenario: Five examples are supplied
- **WHEN** five critical image examples are supplied
- **THEN** their failure modes enter regression coverage and the complete catalog remains in scope

#### Scenario: Products share an output barcode
- **WHEN** distinct identities would overwrite one filename
- **THEN** publication is blocked until the identity/filename conflict is explicitly resolved

### Requirement: Authentic native sources
The system SHALL prioritize verified originals from the five declared source datasets, preserve their bytes and record path, hash, oriented dimensions and identity evidence. Historical manifests, thumbnails and folder names MUST NOT establish source quality by themselves.

#### Scenario: Mapped source is inadequate
- **WHEN** a source is tiny, missing, ambiguous or inconsistent
- **THEN** the system searches the native inventory or reports unresolved identity/source status

### Requirement: One complete retail unit
The system SHALL preserve exactly one intended sale unit including its packaging, contents, label and physical perimeter. A tray includes foam and film; a bag includes sealed margins and contents; a bottle includes cap, shoulders, sides and base.

#### Scenario: Tray contents remain without the tray
- **WHEN** an output keeps turmeric or beans but removes the retail tray or wrapper
- **THEN** it fails package-completeness QA even if the food appears sharp

#### Scenario: Only printed graphics or label survive
- **WHEN** text, logo, artwork or label remains while the package is deleted
- **THEN** it is a critical segmentation defect, not a blur-only enhancement case

### Requirement: Adjacent instance separation
The system SHALL select the intended product independently of neighbors, including touching/overlapping instances and photographs with more than two objects. Fixed half-image cuts or absence of a gap MUST NOT establish safe boundaries.

#### Scenario: Three bottles touch
- **WHEN** front, back and side views touch without a visible gap
- **THEN** the candidate contains only the intended complete visible bottle, including cap and base, without neighbor fragments, or returns unresolved boundary/source status

#### Scenario: Two bags form one connected mask
- **WHEN** identifying and nutrition faces merge into one component
- **THEN** the candidate is rejected as multiple instances rather than accepted as one product

### Requirement: Evidence-based front with single-face exceptions
The system SHALL identify the intended front using product/package evidence. Barcode presence alone MUST NOT reject a legitimate front or single identifying face. Assignment uncertainty SHALL prevent automatic acceptance.

#### Scenario: One identifying label has barcode
- **WHEN** only one supplied identifying face includes barcode and ingredients
- **THEN** the exception is documented/reviewed while the complete retail unit is preserved

### Requirement: Native boundary and material preservation
The system SHALL retain white/light packaging and opaque labels, explicitly handle transparent/reflective boundaries and exclude background without deleting similar-colored product regions. Unknown, occluded or source-clipped package parts MUST NOT be generated.

#### Scenario: Source omits an edge
- **WHEN** the original frame or an occluding neighbor hides required package boundaries
- **THEN** an alternate complete photograph is sought and BLOCKED_NEEDS_SOURCE is reported if none is available

#### Scenario: Product resembles background
- **WHEN** white tray/cap or brown food/glass resembles the shooting surface
- **THEN** complete package boundaries determine retention, not global brightness/color removal

### Requirement: Native product detail without RGB enlargement
The system SHALL measure the selected native product region and prohibit RGB upscaling to meet layout. Accepted output MUST preserve readable source label detail, natural boundaries and color without invented text, halos or clipping. Global megapixels alone MUST NOT establish eligibility.

#### Scenario: Native package is too small
- **WHEN** desired occupancy on the 2400 canvas requires scale greater than one
- **THEN** another adequate source is selected or insufficient-source status is reported without enlargement

#### Scenario: Large source lacks detail
- **WHEN** a high-megapixel source is unfocused or glare-clipped
- **THEN** it is not accepted merely because dimensions exceed a threshold

### Requirement: Consistent lossless master and final export
The system SHALL produce a 2400 x 2400 sRGB image with preserved aspect ratio, centered complete product and shape-appropriate spacing. The lossless master background outside the product/matting boundary SHALL be pure white; delivered JPEG SHALL retain that appearance without visible compression artifacts.

#### Scenario: Product shapes differ
- **WHEN** rendering a tall bottle or horizontal bag
- **THEN** the product retains its actual shape and appropriate spacing rather than being stretched to common dimensions

### Requirement: Per-record evidence and honest completion
The system SHALL record source/identity evidence, native package size, mask evidence, output hash, deciding quality findings and disposition per record. Aggregate sharpness or border scores MUST NOT establish QA PASS. Unaccepted records SHALL retain blocked, review or failed states.

#### Scenario: Aggregate score is high
- **WHEN** incomplete or merged output has high sharpness and white outer border
- **THEN** the per-record gate fails and the output remains outside accepted delivery

### Requirement: Pilot coverage before full publication
The system SHALL verify representative and held-out examples of adjacent instances, materials, identity, source clipping and genuine blur before full publication. The five critical examples and an actual three-touching-bottle case SHALL be included without limiting full-catalog scope.

#### Scenario: Example lacks complete source
- **WHEN** a clipped example has no complete alternate source
- **THEN** correct blocking satisfies regression safety while the image remains explicitly unaccepted

### Requirement: Guarded replacement and protected assets
The system SHALL preserve originals, W/Y media and product fields, protect explicitly user-selected fronts and publish only accepted replacements with baseline hashes, backups and rollback evidence. Run completion MUST NOT imply all records passed.

#### Scenario: Live image changes after baseline
- **WHEN** a live front differs from the expected hash
- **THEN** automatic replacement is refused and the changed file is preserved for reconciliation
