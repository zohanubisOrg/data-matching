# Technical Design: Rebuild Catalog with HD Studio Images & 2-Tier Hierarchy

## Context

Dự án hiện có 1.659 ảnh gốc độ phân giải cao tại `source-import/` (G1-G4, Nyt25.09.26) và file Master cập nhật `Esbjerg_Asian_Market_Master_1659_updated.xlsx` chứa 16 nhóm Category Level 1 và hơn 60 nhóm Category Level 2. Xem `proposal.md` để nắm bối cảnh chi tiết.

## Goals / Non-Goals

**Goals:**
- Xây dựng pipeline tiền xử lý ảnh độc lập, bóc tách chính xác mặt trước bao bì với Safe Margin (+6% đến +8%), đặt trên Canvas nền trắng chuẩn Studio, không bao giờ cắt phạm mép.
- Làm sạch và vá dữ liệu khuyết thiếu đạt độ hoàn thiện 100% (1.659/1.659 sản phẩm có Level 1 và Level 2).
- Cập nhật catalog lên Shopify bằng phương pháp In-place (giữ nguyên ID sản phẩm và SEO handle), đồng thời tạo Main Menu 2 tầng lồng nhau (Nested Menu) và Smart Collections tự động.
- Cập nhật Web Inspection Portal để thẩm định trực quan Side-by-Side trước khi nghiệm thu.

**Non-Goals:**
- Không xóa hay thay đổi URL gốc/Product ID đã có trên Shopify nhằm tránh làm hỏng các liên kết SEO hiện hữu.
- Không đưa các mặt hàng tươi sống, đông lạnh có cờ `Online = Nej` lên web store.

## Decisions

### 1. Phân tách Mặt Trước vs Mặt Sau dựa trên Barcode Gradient & Saliency
- **Quyết định**: Quét phát hiện vùng mã vạch và bảng dinh dưỡng (text mật độ cao) để định vị Mặt Sau; phần bao bì còn lại chứa logo lớn và tên thương hiệu được định vị là Mặt Trước.
- **Lý do**: Đảm bảo 100% trường hợp ảnh chụp 2 mặt không bao giờ lấy nhầm mặt sau làm ảnh đại diện sản phẩm.
- **Phương án thay thế đã cân nhắc**: Lấy mặc định nửa bên trái hoặc bên phải -> Dễ sai nếu người chụp đặt sản phẩm đảo chiều.

### 2. Bounding Box với Safe Margin Symmetrical (+6% đến +8%)
- **Quyết định**: Hộp bao quanh sản phẩm sau khi phát hiện contour/saliency được mở rộng đều 4 cạnh thêm 6% đến 8% trước khi crop.
- **Lý do**: Ngăn chặn triệt để lỗi cắt lẹm nắp chai, góc mép túi kẹp, hoặc viền nhãn hiệu.
- **Phương án thay thế đã cân nhắc**: Crop sát viền đối tượng (Tight Crop) -> Dễ bị lẹm mép nếu bao bì uốn lượn hoặc có góc bo tròn.

### 3. Chuẩn hóa Canvas Studio Nền Trắng Thuần (`#FFFFFF`) và Tỷ lệ Đứng (Portrait)
- **Quyết định**: Sau khi bóc tách, ảnh được dán vào tâm Canvas nền trắng vuông (1600x1600) hoặc dọc (1200x1600) với tỷ lệ chiều cao >= chiều rộng.
- **Lý do**: Đáp ứng hoàn hảo giao diện thương mại điện tử đồng bộ, giao diện thẻ sản phẩm vuông/dọc không bị méo tỷ lệ.

### 4. Đồng bộ Shopify In-Place kết hợp Navigation GraphQL
- **Quyết định**: Dùng Shopify REST/GraphQL API để cập nhật đè Media Attachment, trường `product_type = Category Level 1`, và gán tag `subcat:<Category Level 2>`. Dùng GraphQL `menuUpdate` để tái cấu trúc Main Menu dạng 2 tầng (Nested Menu Items).
- **Lý do**: Bảo toàn dữ liệu đang chạy, đồng thời tạo trải nghiệm duyệt web phân cấp mạch lạc cho khách hàng.

## Risks / Trade-offs

- **[Risk] Thời gian xử lý cắt ảnh 1.659 sản phẩm**: Xử lý ảnh gốc độ phân giải cao có thể mất thời gian nếu chạy đơn luồng.
  - *Mitigation*: Sử dụng `concurrent.futures.ProcessPoolExecutor` đa luồng để tăng tốc độ xử lý hàng loạt xuống dưới 5 phút.
- **[Risk] Giới hạn Rate Limit của Shopify API (40 requests/s hoặc GraphQL bucket)**:
  - *Mitigation*: Tích hợp cơ chế tự động điều tiết tốc độ (Exponential Backoff khi gặp mã 429) trong script đồng bộ.
- **[Risk] Sản phẩm có bao bì màu trắng trên nền trắng kho**:
  - *Mitigation*: Sử dụng phân tích gradient kết hợp cạnh Canny và ngưỡng thích ứng (Adaptive Thresholding) để nhận diện đường bao chính xác.
