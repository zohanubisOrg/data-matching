# Iterative refinement contract corrections

## MODIFIED Requirements

### Requirement: 10-Loop Iterative Refinement Engine
The system SHALL evaluate reproducible candidates built from immutable native sources instead of requiring ten cumulative enhancement cycles. Each candidate SHALL pass independent product, face, package, boundary, native-resolution and readability gates. Fixed cycle counts, aggregate scores or repeated JPEG processing MUST NOT establish convergence or QA PASS.

#### Scenario: Thực thi vòng lặp tối ưu hóa chất lượng
- **WHEN** the historical refinement entrypoint is invoked
- **THEN** it uses the source-based candidate/QA workflow or exits with migration guidance, without repeatedly sharpening or overwriting live JPEGs

#### Scenario: Candidate parameters change
- **WHEN** boundary or source selection is refined
- **THEN** the next candidate is rebuilt from its original source with recorded parameters and evaluated independently of earlier JPEG output

### Requirement: Adaptive Sharpening For User-Curated Photos Without Overwriting
The system SHALL identify user-curated images only through explicit provenance, preserve their original files/framing and evaluate optional conservative enhancement separately. Blur metrics MUST NOT infer ownership. Enhancement SHALL NOT invent missing detail or be mandatory when genuine readability cannot be supported.

#### Scenario: Bảo tồn góc cắt và tối ưu độ nét ảnh Nhóm 2
- **WHEN** an explicitly user-selected image is softly focused
- **THEN** its original remains unchanged and any enhanced candidate requires readability/halo review before replacement consideration

#### Scenario: Package loss resembles softness
- **WHEN** only a label or printed fragment survives
- **THEN** it is a package defect and is not protected or enhanced solely because its sharpness metric is low

### Requirement: Studio Alignment And White Background Enforcement For Restorations
The system SHALL place complete accepted units on a 2400 x 2400 white canvas with shape-appropriate spacing, preserved aspect ratio and no RGB enlargement. Full background, package boundaries and neighbor exclusion SHALL be checked rather than only the outer border.

#### Scenario: Chuẩn hóa nền studio và tỷ lệ hiển thị
- **WHEN** a restored front is rendered
- **THEN** the intended unit is complete, upright and centered with retained native detail and no neighboring product or shooting surface

### Requirement: Multi-Column Visual Audit Spreadsheet Synchronization
The system SHALL create a separate comparison workbook containing accepted X changes while preserving W/Y media bytes, anchors and product fields. Drawing relationships and unique nonvisual IDs SHALL be validated. Thumbnails MUST NOT replace full-resolution delivery/QA evidence. Source/delivery workbooks MUST NOT be silently replaced.

#### Scenario: Xuất file Excel kiểm tra mắt thường
- **WHEN** accepted fronts are exported for comparison
- **THEN** only corresponding X images change and preservation/reconciliation checks pass before completion is reported

#### Scenario: Workbook is locked
- **WHEN** the intended comparison workbook cannot be saved
- **THEN** export is pending or failed, without switching authority or reporting success
