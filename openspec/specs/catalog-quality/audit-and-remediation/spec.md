# catalog-quality/audit-and-remediation Specification

## Purpose
Thiết lập bộ tiêu chuẩn đối chiếu chất lượng hình ảnh mặt trước webshop (front-v3) dựa trên ảnh gốc khách hàng và ảnh mặt sau (back-v2), bảo toàn nguyên vẹn ảnh người dùng tự tìm kiếm và chắt lọc, đồng thời khắc phục triệt để các lỗi thị giác bằng nguồn sạch Master 1659.

## Requirements

### Requirement: 6 Tiêu Chí Đối Chiếu Đánh Giá Chất Lượng Thị Giác
Hệ thống SHALL đối chiếu từng sản phẩm trong file Excel 3 cột (Cột W: Ảnh mặt trước gốc của khách hàng, Cột X: Ảnh webshop mặt trước `front-v3`, Cột Y: Ảnh mặt sau `back-v2`) theo 6 tiêu chí:
1. Tính đơn lẻ: Chỉ chứa đúng 1 mặt trước của sản phẩm (không dính ảnh đôi 2 gói trên kệ).
2. Tính toàn vẹn: Bao bì tròn đầy 100% vỏ (không bị xóa mất vỏ chỉ còn ruột/logo).
3. Không cắt lẹm: Biên bao bì cong tự nhiên, không bị chém phẳng nắp hoặc cụt đáy.
4. Chiều đứng tự nhiên: Đúng dáng đứng đọc nhãn của sản phẩm (không xoay ngang 90 độ).
5. Độ sắc nét: Rõ ràng, nhãn mác đọc được, không bị mờ nhòe do upscale sai.
6. Xác thực mặt trước: Khác biệt rõ ràng so với mặt sau ở Cột Y.

#### Scenario: Phát hiện ảnh đạt chuẩn
- **WHEN** ảnh trong `front-v3` thể hiện đúng 1 mặt trước, toàn vẹn bao bì và rõ nét
- **THEN** hệ thống xếp sản phẩm vào Nhóm 1 (Đạt chuẩn 100%) và bảo toàn tuyệt đối, không thay đổi

#### Scenario: Phát hiện ảnh lỗi do thuật toán cũ
- **WHEN** ảnh trong `front-v3` bị dính 2 gói trên kệ, bị cắt cụt đáy, hoặc bị xóa mất vỏ bao bì
- **THEN** hệ thống gắn nhãn lỗi tương ứng và xếp vào Nhóm 3 để chuẩn bị thay thế từ Master 1659

### Requirement: Bảo Vệ & Nâng Nét Độc Lập Cho Ảnh Người Dùng Tự Lưu
Hệ thống SHALL phát hiện các ảnh trong `front-v3` do người dùng tự tra cứu và cắt chuẩn bố cục 1 sản phẩm nhưng bị mờ nhẹ do ảnh mạng, xếp vào Nhóm 2. Hệ thống SHALL NOT ghi đè hoặc thay thế các ảnh này bằng ảnh khác, mà chỉ áp dụng quy trình tăng cường độ sắc nét (Unsharp Masking / Texture Sharpening) trên đúng góc cắt gốc của người dùng.

#### Scenario: Xử lý ảnh người dùng tự lưu bị mờ
- **WHEN** ảnh trong `front-v3` có bố cục cắt chuẩn xác 1 mặt trước nhưng độ nét còn thấp
- **THEN** hệ thống giữ nguyên góc cắt của người dùng, không ghi đè từ Master 1659, và chạy bộ lọc tăng nét độc lập

### Requirement: Phục Hồi Nguồn Sạch Từ Master 1659 Cho Nhóm Lỗi Thuật Toán
Hệ thống SHALL tra cứu mã barcode của các sản phẩm Nhóm 3 sang kho `Master_1659_Clean_Front_Images`, chuẩn hóa sang canvas $2400 \times 2400$ nền trắng `#FFFFFF` và CHỈ ghi đè lên các file tương ứng trong `front-v3`.

#### Scenario: Thay thế ảnh lỗi thuật toán bằng Master 1659
- **WHEN** sản phẩm bị lỗi ảnh đôi hoặc mất vỏ bao bì và có file tương ứng trong Master 1659
- **THEN** hệ thống chuẩn hóa ảnh từ Master 1659 và ghi đè có kiểm soát vào `front-v3`

### Requirement: Đồng Bộ Excel Đối Chiếu Không Xung Đột XML
Hệ thống SHALL nhúng 3 cột song song (Ảnh gốc khách, Ảnh webshop `front-v3`, Ảnh mặt sau `back-v2`) vào file Excel đối chiếu và tự động chuẩn hóa toàn bộ thuộc tính Drawing `cNvPr id` tuần tự duy nhất để Microsoft Excel mở mượt mà không có thông báo lỗi.

#### Scenario: Mở file Excel đối chiếu trong Microsoft Excel
- **WHEN** người dùng mở file Excel đối chiếu 3 cột
- **THEN** Microsoft Excel mở trực tiếp trang tính, không xuất hiện hộp thoại cảnh báo 'We found a problem with some content'
