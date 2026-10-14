# Design: Two-Sided High-Resolution Product Image Pipeline

## Context
Xem chi tiết tại `proposal.md` và `specs/product-identity-image-pipeline/spec.md`.
Dữ liệu đầu vào chuẩn là file Excel `Rabuta.12.10.2026_original.xlsx` (1.351 sản phẩm). Kho ảnh thô tại kho trước đây bị lỗi cắt sai khung và mờ nên bị loại bỏ hoàn toàn, chuyển sang 100% khai thác ảnh mạng chất lượng cao (Online High-Res) có cơ chế đối soát danh tính nghiêm ngặt.

## Goals / Non-Goals

**Goals:**
- Xây dựng module trích xuất Ground Truth chuẩn xác từ Excel (Barcode, Full Name, Brand, Variant, Net Quantity).
- Xây dựng Multi-source Image Harvester: Open Food Facts API (ảnh RAW camera), EU Wholesalers (Asia Express Food artwork/packshot), và Google Image Search có khóa cứng `"{barcode}"`.
- Xây dựng Deterministic Identity Verifier: Bộ lọc từ chối cứng (Hard Conflict Filter) ngăn chặn 100% tình trạng lấy nhầm sản phẩm/biến thể.
- Xây dựng Studio Post-Processor: Tự động sửa xoay dọc (Portrait Orientation) và tách nền AI (Background Removal sang nền trắng `#FFFFFF` 1:1 1600x1600 px).
- Xây dựng Back Label Processor: Tăng độ tương phản nét chữ cho nhãn thành phần và dinh dưỡng.
- Xuất bộ ảnh phân loại vào `output/webshop_hd_delivery/front/` và `output/webshop_hd_delivery/back/`.
- Xuất báo cáo đối soát Excel và trang xem trước HTML Gallery trực quan để nghiệm thu Pilot 20 mã.

**Non-Goals:**
- Không sử dụng Generative AI để tự vẽ hoặc tái tạo nội dung nhãn thành phần/dinh dưỡng (tránh vi phạm quy định an toàn thực phẩm).
- Không tự ý nén nhỏ ảnh dưới 1000px để lấy cho đủ số lượng.
- Không tự động đẩy lên Shopify live khi chưa có sự nghiệm thu trực quan của người dùng.

## Decisions

### 1. Kiến trúc Pipeline: Deterministic Verification trước, Image Acquisition sau
- *Lý do*: Tránh tình trạng crawler tải ảnh bừa bãi rồi cố gắng phân loại. Bằng cách khóa chặt Barcode và đối chiếu `Variant` (hương vị) + `Brand` ngay từ khâu lọc URL và tiêu đề trang, loại bỏ 100% trường hợp lấy nhầm sản phẩm.
- *Lựa chọn thay thế*: Tìm kiếm ảnh thuần túy bằng Google Search -> Đã thử nghiệm và thất bại do Google tự ý gợi ý sản phẩm bán chạy khác cùng hãng.

### 2. Chiến lược 2 mặt độc lập (Front Studio & Back Label)
- *Mặt trước*: Bắt buộc qua bước AI Background Removal để đạt chuẩn studio e-commerce (nền trắng `#FFFFFF`, tỉ lệ 1:1, viền 8%).
- *Mặt sau*: Giữ nguyên bố cục bao bì hoặc nhãn in phẳng (Artwork), không xóa phông để tránh làm mất các dòng chữ nhỏ ở rìa nhãn. Chạy thuật toán unsharp mask / contrast enhancement để chữ đen trên nền bao bì sắc nét nhất.
- *Lựa chọn thay thế*: Dùng chung một thuật toán crop cho cả 2 mặt -> Dễ cắt mất thông tin dinh dưỡng của mặt sau.

### 3. Tách nền AI chạy cục bộ
- *Giải pháp*: Sử dụng thư viện tách nền AI (như `rembg` với model U2Net/BiRefNet hoặc OpenCV Contour Fallback) chạy trực tiếp trong môi trường Python, không phụ thuộc vào API bên ngoài có tính phí.

### 4. Báo cáo nghiệm thu trực quan qua HTML Dashboard
- *Lý do*: Giúp người quản lý (anh Thông Tiến) chỉ mất 2-3 phút duyệt qua 20 sản phẩm mẫu (40 ảnh 2 mặt) trên trình duyệt trước khi cho chạy hàng loạt 1.351 sản phẩm.

## Risks / Trade-offs

- **[Risk] Một số barcode hiếm không có ảnh mặt sau trên Internet**
  → *Mitigation*: Hệ thống dứt khoát không gán ảnh bừa bãi; ghi rõ trạng thái `CẦN CHỤP LẠI MẶT SAU TẠI KHO` trong file Excel để nhân viên kho chụp bổ sung bằng điện thoại.
- **[Risk] Tốc độ xử lý tách nền AI và tải ảnh HD**
  → *Mitigation*: Sử dụng cơ chế multithreading/caching thông minh, tải và xử lý theo từng batch 20-30 sản phẩm, lưu cache file gốc để không tải lại khi re-run.
