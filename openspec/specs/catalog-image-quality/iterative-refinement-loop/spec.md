# Iterative Refinement Loop Specification

## Purpose

Cung cấp quy trình lặp tự động (10-loop convergence engine) nhằm đánh giá, tối ưu hóa thích ứng và nâng cao chất lượng toàn diện của bộ ảnh webshop mặt trước (`front-v3`) cho 1.350 SKU, bảo toàn tuyệt đối ảnh do người dùng tự chọn, và xuất file Excel đối chiếu 3 cột đạt chuẩn thị giác.

## Requirements

### Requirement: 10-Loop Iterative Refinement Engine
The system SHALL establish an automated iteration loop of up to 10 refinement cycles. Sau mỗi chu kỳ, hệ thống PHẢI tính toán các chỉ số độ nét trung bình (Laplacian Variance), tỷ lệ đạt chuẩn Nhóm 1, và tự động dừng khi chất lượng đạt trạng thái bão hòa (độ tăng trưởng nhỏ hơn 0.5% qua 2 chu kỳ liên tiếp).

#### Scenario: Thực thi vòng lặp tối ưu hóa chất lượng
- **WHEN** Quá trình 10-loop engine được kích hoạt
- **THEN** Hệ thống chạy tuần tự từng chu kỳ đánh giá, tinh chỉnh, đo lường chỉ số và ghi log vào `output/catalog_pairs/iteration_quality_metrics.json`

### Requirement: Adaptive Sharpening For User-Curated Photos Without Overwriting
The system SHALL apply multi-scale adaptive sharpening and bilateral edge preservation for all Group 2 products. Hệ thống TUYỆT ĐỐI KHÔNG làm cháy chi tiết, không tạo quầng halo và KHÔNG ĐƯỢC THAY THẾ bằng ảnh khác.

#### Scenario: Bảo tồn góc cắt và tối ưu độ nét ảnh Nhóm 2
- **WHEN** Xử lý bất kỳ ảnh nào thuộc danh sách Nhóm 2 trong các vòng lặp
- **THEN** File ảnh trong `front-v3` được giữ nguyên 100% kích thước và góc cắt ban đầu của người dùng, đồng thời độ nét cải thiện rõ rệt qua từng chu kỳ

### Requirement: Studio Alignment And White Background Enforcement For Restorations
The system SHALL format all Group 3 restored packshots onto a $2400 \times 2400$ pure white canvas `#FFFFFF`. Tỷ lệ an toàn 85%, 4 mép biên không còn pixel mờ, và sản phẩm được căn giữa chuẩn xác.

#### Scenario: Chuẩn hóa nền studio và tỷ lệ hiển thị
- **WHEN** Xử lý ảnh khôi phục Nhóm 3 trong chu kỳ tối ưu
- **THEN** Ảnh đầu ra trong `front-v3` đạt kích thước $2400 \times 2400$, nền trắng `#FFFFFF` tại các biên, không còn dấu vết cắt lẹm hay ảnh đôi

### Requirement: Multi-Column Visual Audit Spreadsheet Synchronization
The system SHALL update and synchronize the multi-column visual audit Excel spreadsheet with all 3 parallel image columns. Toàn bộ mã Drawing `cNvPr id` trong XML là duy nhất và tuần tự.

#### Scenario: Xuất file Excel kiểm tra mắt thường
- **WHEN** Hoàn tất toàn bộ chu kỳ lặp tối ưu
- **THEN** File Excel đối chiếu được tạo hoặc cập nhật hoàn chỉnh, không có lỗi khóa file và mở trơn tru trong Microsoft Excel
