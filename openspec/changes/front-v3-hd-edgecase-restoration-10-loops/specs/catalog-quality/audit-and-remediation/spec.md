# Catalog audit and remediation contract corrections

## MODIFIED Requirements

### Requirement: 6 Tiêu Chí Đối Chiếu Đánh Giá Chất Lượng Thị Giác
The system SHALL reevaluate every authoritative catalog record using identity/front evidence, exactly one complete unit, complete boundaries, correct orientation, genuine native readability and preserved package detail/background quality. P3, Group 1 and aggregate sharpness labels MUST NOT bypass review. Legitimate single-face packages SHALL receive documented exceptions rather than automatic rejection for resembling Y or containing barcodes.

#### Scenario: Phát hiện ảnh đạt chuẩn
- **WHEN** an existing front satisfies every per-record gate with deciding evidence
- **THEN** it is recorded as VERIFIED_EXISTING and preserved without unnecessary processing

#### Scenario: Phát hiện ảnh lỗi do thuật toán cũ
- **WHEN** an output merges instances, loses packaging, clips cap/base or retains only a label
- **THEN** it is a critical defect considered for reconstruction from a complete verified native source

#### Scenario: Record was not flagged previously
- **WHEN** a record belonged to former P3 or an auto-passed group
- **THEN** it receives the same source and image-quality review as flagged records

### Requirement: Bảo Vệ & Nâng Nét Độc Lập Cho Ảnh Người Dùng Tự Lưu
The system SHALL preserve explicitly user-selected originals and framing using provenance. Layout/blur heuristics MUST NOT identify ownership. Optional enhancement SHALL be separate, retain genuine details and receive independent review; unsupported details SHALL remain unresolved rather than generated.

#### Scenario: Xử lý ảnh người dùng tự lưu bị mờ
- **WHEN** provenance identifies a user-selected image with insufficient clarity
- **THEN** its original remains unchanged and a reviewed alternative or explicit source/review disposition is produced instead of automatic live sharpening

### Requirement: Phục Hồi Nguồn Sạch Từ Master 1659 Cho Nhóm Lỗi Thuật Toán
The system SHALL prioritize the five native source datasets and verify identity, face, completeness, local focus and native package resolution per candidate. Master 1659 and other derivatives MUST NOT be presumed clean/high resolution. Only approved replacements SHALL reach front-v3 through guarded publication.

#### Scenario: Thay thế ảnh lỗi thuật toán bằng Master 1659
- **WHEN** a Master match exists
- **THEN** it is an unverified candidate, rejected if inadequate, and replaced by an eligible native-source candidate when available

#### Scenario: No eligible complete source
- **WHEN** all candidates are incomplete, occluded, too small or genuinely unreadable
- **THEN** the record remains BLOCKED_NEEDS_SOURCE without a fabricated or enlarged replacement

### Requirement: Đồng Bộ Excel Đối Chiếu Không Xung Đột XML
The system SHALL create a separate comparison workbook for accepted X replacements, preserve W/Y media bytes/anchors and product data, and validate unique drawing IDs and consistent relationships. Saving a workbook or counting images alone MUST NOT establish image QA PASS.

#### Scenario: Mở file Excel đối chiếu trong Microsoft Excel
- **WHEN** comparison export completes
- **THEN** structural checks pass and the accepted full-resolution image manifest remains the quality evidence, with any unperformed Excel application check explicitly reported
