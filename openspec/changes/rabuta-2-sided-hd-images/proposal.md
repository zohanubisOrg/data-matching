# Proposal: Rabuta Two-Sided High-Resolution Product Image Pipeline

## Why

Khách hàng (anh Thông Tiến) yêu cầu một folder ảnh chất lượng cao để nạp vào webshop Shopify cho danh mục sản phẩm từ file `Rabuta.12.10.2026_original.xlsx` (1.351 sản phẩm). Mỗi sản phẩm bắt buộc phải có **đủ 2 ảnh chất lượng cao**:
1. **Ảnh mặt trước (Front Packshot)**: Giới thiệu hàng, siêu nét (>= 1600px), tách nền đưa về nền trắng studio `#FFFFFF`, căn giữa 1:1.
2. **Ảnh mặt sau (Back Label)**: Nhãn thành phần và bảng dinh dưỡng (Ingredients & Nutrition Facts), chữ số sắc nét, zoom vào đọc được rõ ràng.

Trước đây, việc tự động crop từ ảnh chụp thô tại kho dẫn tới ảnh mờ, lệch góc, nhầm mặt trước/sau khiến khách hàng phàn nàn. Khi chuyển sang tìm kiếm mạng, script lại gặp lỗi đối sánh thực thể lỏng lẻo (lấy nhầm sang sản phẩm khác cùng hãng như Thạch Dừa lấy nhầm Măng Cụt, bánh 180g lấy nhầm 100g, hoặc lấy phải thumbnail 400px bị nén mờ).

Do đó, cần xây dựng một **Product Identity Resolution & Image Verification Pipeline** chuyên biệt: định danh thực thể chính xác dựa trên Barcode + Brand + Variant + Trọng lượng trước khi tìm ảnh, kiểm duyệt độ phân giải khắt khe, xóa phông nền trắng mặt trước, và bóc tách nhãn thành phần mặt sau.

## What Changes

- **Chuẩn hóa & Khóa cứng dữ liệu định danh (Ground Truth Ingestion)**: Đọc file `Rabuta.12.10.2026_original.xlsx`, trích xuất 5 trường neo: Barcode, Full Name, Brand, Variant/Flavour, Net Quantity.
- **Xác thực danh tính đa nguồn (Multi-source Identity Resolution)**:
  - Tra cứu GTIN/Barcode trên Open Food Facts API & Portal nhà phân phối Châu Âu (Asia Express Food, Heuschen & Schrouff).
  - Khóa tìm kiếm Search Engine với cú pháp tuyệt đối `"{barcode}"` + bộ lọc kích thước Large.
  - Bộ lọc chặn cứng 3 lớp (Hard Conflict Filter): Loại bỏ ngay lập tức nếu sai Brand, xung đột Variant (vd: tìm Coconut mà gặp Mangosteen), hoặc sai trọng lượng.
- **Hậu kỳ Studio tự động cho Mặt trước**:
  - Tự động xoay đứng (Auto-rotation portrait).
  - Tách nền AI (Background Removal), đưa về phông trắng `#FFFFFF` 1:1 1600x1600px, padding an toàn 8%.
- **Thu thập & Tăng cường nét chữ cho Mặt sau (Back Label)**:
  - Ưu tiên Artwork label / Product Sheet từ nhà phân phối B2B.
  - Lấy ảnh gốc camera Open Food Facts (`ingredients_xx.full.jpg` >= 2500px), nắn thẳng và tăng tương phản (Sharpen/Contrast) để nét chữ thành phần dễ đọc.
  - Cào sẵn text mô tả thành phần & dinh dưỡng để hỗ trợ nạp Shopify.
- **Phân hạng đầu ra & Báo cáo đối soát 2 mặt**:
  - `Tier 1 (Verified)`: Đủ 2 ảnh HD mặt trước & mặt sau.
  - `Tier 2 (Review Needed)`: Ảnh đạt nhưng cần kiểm tra thủ công.
  - `Tier 3 (Retake Flagged)`: Không có ảnh nét trên mạng -> Đánh dấu đỏ để kho chụp lại thực tế.
- **Thử nghiệm Pilot 20 sản phẩm mẫu (40 ảnh)**: Chạy thử nghiệm và xuất trang HTML Dashboard trực quan để duyệt chất lượng trước khi mở rộng toàn bộ 1.351 sản phẩm.

## Capabilities

### New Capabilities
- `product-identity-image-pipeline`: Hệ thống đối soát danh tính sản phẩm, thu thập ảnh đa nguồn có kiểm duyệt 2 mặt (Front Studio + Back Ingredients Label), hậu kỳ xóa phông và xuất báo cáo đối soát cho Shopify.

### Modified Capabilities
*(Không có spec cũ nào bị thay đổi)*

## Impact
- **Dữ liệu đầu vào**: `source-import/new_source_from_customer/12-10-new-requirment/Rabuta.12.10.2026_original.xlsx`.
- **Thư mục đầu ra**:
  - `output/webshop_hd_delivery/front/{barcode}_front.jpg`
  - `output/webshop_hd_delivery/back/{barcode}_back.jpg`
  - `output/Rabuta_2_Sided_Pilot_Audit.xlsx`
  - `output/pilot_20_gallery.html`
- **Môi trường & Công cụ**: Python 3.13, Pillow, OpenCV, Requests, OpenPyXL, mô hình tách nền Studio.
