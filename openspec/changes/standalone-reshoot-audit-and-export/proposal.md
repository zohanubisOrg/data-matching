# Proposal: Standalone Reshoot Audit & Customer Sheet Export

## Why
Trong pipeline packshot thương mại điện tử `pipeline-zohanubis`, việc xác định sản phẩm thiếu ảnh hoặc ảnh chất lượng kém trước đây gắn liền với quá trình chạy xử lý matting toàn bộ. Khi cần nhanh chóng rà soát và yêu cầu khách hàng chụp lại ảnh bổ sung cho 1.351 SKU trên danh mục `Rabuta_master_SKU_categories.xlsx`, việc phải chạy lại pipeline AI nặng nề là không hiệu quả. Cần một công cụ kiểm thử chất lượng và trích xuất danh sách chụp lại (reshoot audit script) hoàn toàn độc lập, có thể đánh giá toàn bộ 5 kho ảnh gốc (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`), phát hiện các SKU thiếu ảnh, ảnh mờ, mất mã vạch hoặc bị lỗi cắt xén, đồng thời xuất ra file Excel danh sách chụp lại chuẩn format 1-to-1 với file master cho khách hàng đối chiếu.

## What Changes
- **Tách riêng Standalone Script**: Xây dựng script độc lập `scripts/audit_and_export_reshoot_list.py` không phụ thuộc vào tiến trình matting/chạy nặng của pipeline, có thể chạy trong vài chục giây nhờ tận dụng cache quét mã vạch và cơ chế đọc trực tiếp.
- **Đánh giá toàn diện 5 folder ảnh gốc**: Quét toàn bộ 1.572 ảnh gốc thuộc 5 phân vùng (`G1`, `G2`, `G3`, `G4`, `Nyt25.09.26`) bao gồm cả định dạng iOS `.heic` và ảnh `.jpg`.
- **Phân loại lỗi đa tiêu chí (Multi-Criteria Reshoot Classifier)**:
  - *MISSING_RAW*: Không tìm thấy bất kỳ ảnh nào khớp với SKU trong kho ảnh.
  - *NO_BARCODE_FOUND*: Có ảnh mặt trước nhưng không tìm thấy ảnh có mã vạch hợp lệ ở mặt sau/cạnh bên.
  - *POOR_FOCUS_OR_BLUR*: Ảnh gốc bị out nét, rung tay, mờ nhãn (`blur_score < 35.0` hoặc `label_sharpness < 15.0`).
  - *TRUNCATED_OR_OCCLUDED*: Ảnh bị cắt đứt biên ngoài bao bì ngay từ ảnh gốc hoặc bị ngón tay che khuất.
  - *PIPELINE_QUARANTINE*: Ảnh đã qua xử lý nhưng thất bại (vỡ khuôn hình, thủng thân, lệch tỉ lệ so với mẫu demo).
- **Xuất file Excel đối chiếu chuẩn khách hàng (`Rabuta_Customer_Reshoot_Request.xlsx`)**:
  - Giữ nguyên 100% cấu trúc 31 cột gốc của `Rabuta_master_SKU_categories.xlsx`.
  - Clone chính xác từng dòng dữ liệu của các SKU cần chụp lại.
  - Bổ sung 4 cột phân tích chuyên dụng: `Mức độ ưu tiên chụp lại`, `Lý do chụp lại chi tiết (Tiếng Việt)`, `Góc chụp yêu cầu`, và `Hướng dẫn chụp chuẩn`.
  - Giữ nguyên ảnh demo đối chiếu từ file gốc giúp khách hàng nhận diện nhanh sản phẩm trong kho.

## Capabilities

### New Capabilities
- `catalog-quality/reshoot-audit-and-export`: Độc lập hóa quy trình kiểm tra chất lượng ảnh thô của 5 thư mục gốc, đối soát với 1.351 sản phẩm danh mục master, phân loại lý do chụp lại và kết xuất bảng biểu Excel đối chiếu đồng bộ.

### Modified Capabilities
*(Không có requirement nào của các spec trước bị thay đổi)*

## Impact
- **Mã nguồn mới**: Thêm script `scripts/audit_and_export_reshoot_list.py` và module hỗ trợ nếu cần.
- **Dữ liệu đầu ra**: Tạo file `output/shopify-zohanubis-image/reports/Rabuta_Customer_Reshoot_Request.xlsx` (và bản copy root tiện dụng).
- **Tương thích**: Không can thiệp hay làm gián đoạn pipeline chính `run_zohanubis_pipeline.py`.
