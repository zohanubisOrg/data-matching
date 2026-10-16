# Tasks: Standalone Reshoot Audit & Customer Sheet Export

## 1. Core Audit Engine & Classifier Implementation

- [x] 1.1 Khởi tạo script độc lập `scripts/audit_and_export_reshoot_list.py` với cấu trúc CLI (`--excel`, `--output-excel`, `--min-blur`, `--partition`, `--force-rescan`) và xác minh parse arguments thành công.
- [x] 1.2 Tích hợp nạp và quét toàn bộ 5 thư mục ảnh gốc (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`) bao gồm cả định dạng `.heic` và nạp barcode scan cache để đạt tốc độ thực thi tức thì.
- [x] 1.3 Cài đặt bộ phân loại đa tiêu chí `ReshootClassifier`: phát hiện `MISSING_RAW`, `NO_BARCODE_FOUND`, `POOR_FOCUS_OR_BLUR`, `TRUNCATED_OR_OCCLUDED` và gán nhãn lý do chi tiết bằng tiếng Việt.

## 2. Customer Excel Exporter Implementation

- [x] 2.1 Xây dựng module sao chép 100% cấu trúc 31 cột gốc từ `Rabuta_master_SKU_categories.xlsx` và ghi nhận toàn bộ các dòng SKU cần chụp lại.
- [x] 2.2 Bổ sung 4 cột nghiệp vụ hướng dẫn khách hàng: `Mức độ ưu tiên chụp lại`, `Lý do chụp lại chi tiết`, `Góc chụp yêu cầu`, `Hướng dẫn chụp chuẩn` kèm styling màu sắc trực quan (hồng/vàng nhạt).
- [x] 2.3 Nhúng ảnh thumbnail mẫu từ Cột W của file gốc cho các SKU cần chụp lại để khách hàng dễ dàng đối chiếu mặt hàng khi tìm kiếm trong kho.

## 3. End-to-End Verification & Deliverables Delivery

- [x] 3.1 Chạy thử nghiệm script trên phân vùng `Nyt25.09.26` và `G4-original` để kiểm chứng khả năng phân loại và đọc ảnh HEIC.
- [x] 3.2 Chạy toàn bộ 1.351 sản phẩm danh mục master trên cả 5 thư mục ảnh gốc và xuất file deliverable `Rabuta_Customer_Reshoot_Request.xlsx`.
- [x] 3.3 Kiểm tra đối chiếu số lượng SKU được phân loại chụp lại, đảm bảo không có mã vạch nào bị sót và file Excel mở mượt mà không lỗi XML drawing.
