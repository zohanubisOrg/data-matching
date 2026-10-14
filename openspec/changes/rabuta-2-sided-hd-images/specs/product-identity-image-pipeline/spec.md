# Spec Delta

## Purpose

Hệ thống cung cấp giải pháp tự động đối soát danh tính sản phẩm (Product Identity Resolution) và thu thập, kiểm duyệt chất lượng bộ ảnh 2 mặt siêu nét (Front Studio Packshot và Back Ingredients/Nutrition Label) từ file danh mục gốc để phục vụ đăng tải thương mại điện tử trên Shopify.

## ADDED Requirements

### Requirement: Deterministic Identity Resolution & Hard Conflict Guardrail
Hệ thống BẮT BUỘC phải thực hiện đối soát danh tính sản phẩm dựa trên các trường thông tin chuẩn từ file Excel (`Barcode`, `Brand`, `Variant / flavour`, `Net quantity`) trước khi tiến hành chấp thuận hình ảnh. Hệ thống SHALL từ chối ngay lập tức mọi hình ảnh hoặc nguồn tìm kiếm có sự xung đột về thương hiệu, khác biệt về biến thể hương vị hoặc không tương thích về trọng lượng/quy cách đóng gói.

#### Scenario: Chặn xung đột hương vị (Variant Conflict)
- **WHEN** Sản phẩm trong file Excel có Variant là "Coconut" nhưng kết quả tìm kiếm hoặc tiêu đề ảnh từ web chứa từ khóa "Mangosteen" hoặc hương vị khác
- **THEN** Hệ thống SHALL loại bỏ ứng viên ảnh này ngay lập tức, không lưu trữ và không hạ tiêu chuẩn để chọn nhầm sản phẩm

#### Scenario: Chặn xung đột quy cách đóng gói (Weight Conflict)
- **WHEN** Sản phẩm trong file Excel có quy cách là "180 g (6 packs)" nhưng kết quả tìm kiếm biểu thị gói lẻ "100 g"
- **THEN** Hệ thống SHALL đánh dấu xung đột trọng lượng và từ chối tải ảnh này làm ảnh đại diện

### Requirement: Two-Sided Image Acquisition Standards
Hệ thống SHALL thu thập và kiểm duyệt độc lập hai mặt hình ảnh cho mỗi sản phẩm đạt tiêu chuẩn chất lượng cao dành cho webshop:
1. Mặt trước (Front Packshot): Độ phân giải tối thiểu 1600x1600 px, ảnh sắc nét, hiển thị trọn vẹn sản phẩm.
2. Mặt sau (Back Label): Ảnh nhãn thành phần và bảng dinh dưỡng (Ingredients & Nutrition Facts), độ phân giải tối thiểu 1600 px, văn bản thành phần và các thông số dinh dưỡng phải đọc được rõ ràng khi phóng to.

#### Scenario: Thu thập ảnh mặt trước đạt chuẩn
- **WHEN** Hệ thống tìm thấy ảnh mặt trước từ nguồn phân phối chính hãng hoặc Open Food Facts có độ phân giải >= 1600 px
- **THEN** Hệ thống SHALL tải về bản gốc có độ phân giải cao nhất và đưa vào công đoạn hậu kỳ Studio

#### Scenario: Thu thập ảnh mặt sau nhãn thành phần
- **WHEN** Hệ thống tra cứu được Artwork label từ nhà phân phối hoặc ảnh camera gốc (raw full) của Open Food Facts chứa bảng thành phần và dinh dưỡng
- **THEN** Hệ thống SHALL tải về, kiểm tra tính đọc được của văn bản, tăng tương phản nét chữ và lưu vào thư mục ảnh mặt sau

### Requirement: Studio Post-Processing for Front Packshot
Hệ thống SHALL tự động xử lý hậu kỳ cho ảnh mặt trước:
1. Tự động chuẩn hóa định hướng hình ảnh (Auto-rotation) để sản phẩm luôn đứng thẳng (portrait).
2. Tách nền bằng mô hình AI, loại bỏ hoàn toàn phông nền thừa, đặt sản phẩm trên nền trắng tinh khiết `#FFFFFF`.
3. Đóng khung chuẩn tỷ lệ vuông 1:1 (kích thước 1600x1600 px), căn giữa sản phẩm với khoảng đệm an toàn 8%.

#### Scenario: Tự động tách nền và chuẩn hóa khung vuông
- **WHEN** Ảnh mặt trước gốc có nền bối cảnh (kệ hàng, mặt bàn, màu xám)
- **THEN** Hệ thống SHALL tách sạch nền, đổ nền trắng `#FFFFFF`, căn giữa và lưu trữ dưới định dạng JPEG chất lượng cao (quality >= 92) và WebP

### Requirement: Decision Routing & Audit Reporting
Hệ thống SHALL phân loại kết quả đầu ra của mỗi sản phẩm vào 3 trạng thái phân minh và xuất báo cáo đối soát đối chứng (Audit Report) kèm trang HTML Gallery xem trước:
- `Tier 1 (Verified)`: Đủ 2 ảnh HD mặt trước và mặt sau, khớp chính xác 100% dữ liệu.
- `Tier 2 (Review Needed)`: Ảnh đạt độ nét nhưng cần người kiểm duyệt xác nhận.
- `Tier 3 (Retake Flagged)`: Không có ảnh chuẩn trên mạng hoặc ảnh quá mờ nhòe -> Cắm cờ "CẦN CHỤP LẠI TẠI KHO".

#### Scenario: Cắm cờ yêu cầu chụp lại tại kho
- **WHEN** Một mã barcode không có ảnh đạt chuẩn trên mạng hoặc ảnh mặt sau không thể đọc được chữ
- **THEN** Hệ thống SHALL đánh dấu trạng thái "CẦN CHỤP LẠI TẠI KHO" trong file Excel báo cáo, tuyệt đối không lấy ảnh rác hoặc ảnh mờ để thay thế
