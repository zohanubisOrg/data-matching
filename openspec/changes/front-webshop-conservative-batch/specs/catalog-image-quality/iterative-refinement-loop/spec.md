# Spec Delta

## REMOVED Requirements

### Requirement: 10-Loop Iterative Refinement Engine
**Reason**: Vòng lặp ghi lại JPEG và mài nét nhiều lần làm mất chi tiết, chạy chậm, và không sửa được ảnh đã cắt lẹm.
**Migration**: Mỗi dòng chỉ được dựng một lần từ ảnh gốc theo `catalog-image-quality/conservative-front-batch`. Không đọc chỉ số Laplacian của cả thư mục để quyết định chạy thêm vòng.

### Requirement: Adaptive Sharpening For User-Curated Photos Without Overwriting
**Reason**: Độ mờ toàn ảnh không chứng minh ảnh do người dùng chọn, và mài nét trên JPEG cũ không trả lại phần bao bì đã bị cắt.
**Migration**: Ảnh sản xuất luôn đi từ nguồn gốc bất biến. Không tăng nét trên file webshop đã xuất.

## MODIFIED Requirements

### Requirement: Studio Alignment And White Background Enforcement For Restorations
The system SHALL đặt mỗi ảnh webshop mặt trước đã nghiệm thu lên canvas $2400 \times 2400$ nền trắng `#FFFFFF`, sản phẩm căn giữa và không chạm bốn cạnh. Tỷ lệ chiếm chỗ MUST được khóa trước khi chạy lô và MUST không đòi hỏi phóng to điểm ảnh gốc. Hệ thống MUST NOT ghi ảnh này bằng cách sửa tiếp file trong thư mục webshop mặt trước hiện có.

#### Scenario: Chuẩn hóa nền studio và tỷ lệ hiển thị
- **WHEN** một dòng có vùng sản phẩm gốc đủ biên và đủ lớn để đặt lên canvas mà không phóng to
- **THEN** ảnh đầu ra đạt kích thước $2400 \times 2400$, nền trắng tại bốn góc, trọn vỏ sản phẩm, và được lưu thành file mới chứ không ghi đè JPEG webshop cũ

### Requirement: Multi-Column Visual Audit Spreadsheet Synchronization
The system SHALL cập nhật bản sao workbook đối chiếu sau khi có ảnh đạt. Cột ảnh webshop mặt trước nhận ảnh mới. Cột ảnh mặt trước gốc và cột ảnh mặt sau giữ nguyên nội dung đã nhúng. Toàn bộ mã Drawing `cNvPr id` trong XML MUST duy nhất và tuần tự. Workbook nguồn của khách MUST NOT bị thay thế tại chỗ.

#### Scenario: Xuất file Excel kiểm tra mắt thường
- **WHEN** lô ảnh đạt đã được kiểm tra và bản sao workbook được ghi
- **THEN** file mở được trong Microsoft Excel, cột webshop mặt trước khớp file ảnh mới, và hai cột ảnh còn lại không đổi so với workbook nguồn

## ADDED Requirements

### Requirement: Single native render
The system SHALL render each candidate once from an immutable original. A barcode SHALL have at most three total render attempts, each from an original source, with at most two allowlisted Python-selected repair recipes. The system MUST NOT open a prior rendered JPEG for sharpening, contrast adjustment or another processing pass. Semantic QA feedback may select an alternate original or a safer boundary recipe; ambiguous evidence terminates in REVIEW.

#### Scenario: Chạy lại một dòng đã đạt
- **WHEN** cùng một nguồn, cùng một vùng bao bì và cùng cấu hình dựng được chạy lại
- **THEN** hệ thống dùng lại ảnh đã đạt và không tạo thêm một thế hệ JPEG đã mài nét

#### Scenario: Sửa lỗi vùng chọn từ một nguồn mới
- **WHEN** semantic QA identifies a correctable subject-selection issue and another indexed original exists
- **THEN** Python renders a new candidate from that immutable original and reruns all gates; it does not edit the previous JPEG

#### Scenario: No safe repair remains
- **WHEN** two repair attempts were used, the available sources are exhausted, or the semantic boundary remains uncertain
- **THEN** the barcode ends in REVIEW without another render
