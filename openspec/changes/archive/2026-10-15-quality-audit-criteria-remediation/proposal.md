# Proposal: Bộ Tiêu Chí Đối Chiếu & Đánh Giá Chất Lượng và Xử Lý Catalog Webshop

## Why
Trong quá trình chuẩn hóa danh mục hình ảnh sản phẩm đưa lên webshop (`front-v3`), nhiều ảnh xuất hiện các lỗi thị giác nghiêm trọng: dính 2 gói sản phẩm trên kệ siêu thị (ảnh đôi), xóa phông quá mức làm mất vỏ bao bì chỉ chừa lại logo/ruột, cắt lẹm bao bì (guillotine cut), hoặc bị lật ngang 90 độ. 
Cần thiết lập một bộ tiêu chí đối chiếu thị giác 3 cột rõ ràng (`Ảnh mặt trước gốc` vs `Ảnh webshop mặt trước` vs `Ảnh mặt sau`), phân tách minh bạch giữa ảnh đã đạt chuẩn (bảo toàn), ảnh do người dùng tự lưu bị mờ (xử lý tăng nét riêng, tuyệt đối không đè), và ảnh lỗi do thuật toán cũ (thay thế bằng nguồn ảnh đơn sạch từ `Master_1659_Clean_Front_Images`).

## What Changes
- Thiết lập bảng 6 tiêu chí kiểm định chất lượng đối chiếu thị giác (Tính đơn lẻ 1 sản phẩm, Tính toàn vẹn 100% bao bì, Không cắt lẹm viền, Chiều đứng tự nhiên, Độ sắc nét không đục thủng chữ, Xác thực không trùng mặt sau).
- Thiết lập cơ chế phân loại 3 nhóm xử lý có kiểm soát:
  - **Nhóm 1 (Đạt chuẩn 100%)**: Giữ nguyên tuyệt đối trong `front-v3`.
  - **Nhóm 2 (Ảnh người dùng tự lưu cắt chuẩn nhưng bị mờ)**: Giữ nguyên bố cục và góc cắt của người dùng, đưa vào luồng tăng nét riêng biệt, **tuyệt đối không đè ảnh khác**.
  - **Nhóm 3 (Lỗi thuật toán cũ: ảnh đôi, cắt lẹm, mất vỏ)**: Tra cứu sang kho `Master_1659_Clean_Front_Images` để xử lý chuẩn hóa studio 2400x2400 và ghi đè có kiểm soát vào `front-v3`.
- Bổ sung công cụ rà soát tự động và tái nghiệm thu trực quan trên file Excel đối chiếu 3 cột mà không gây lỗi xung đột mã đồ họa XML.

## Capabilities

### New Capabilities
- `catalog-quality/audit-and-remediation`: Quy trình kiểm định chất lượng đối chiếu 3 cột, phân loại 3 nhóm và xử lý phục hồi bao bì chuẩn webshop.

### Modified Capabilities
*(Không có spec cũ nào bị thay đổi requirements)*

## Impact
- **Dữ liệu**: Kho ảnh `output/catalog_pairs/tagged/front-v3`, kho ảnh gốc `Master_1659_Clean_Front_Images`, file Excel đối chiếu `Rabuta_master_SKU_categories_ingredients_final_audit_v3.xlsx`.
- **Hệ thống**: Bảo toàn 100% các ảnh người dùng đã tự tay tra cứu/làm chuẩn; khắc phục dứt điểm các ca lỗi hiển thị trên website webshop.
