# Tasks

## 1. Tiền xử lý & Vá Dữ liệu Master 1.659 Sản Phẩm

- [x] 1.1 Xây dựng script làm sạch dữ liệu `scripts/preprocess_master_catalog_1659.py` để vá 4 sản phẩm khuyết thiếu Level 1/Level 2 (STT 9, 938, 1458, 1621), kiểm toán Modulo-10 cho 100% Barcode và bảo toàn số 0 ở đầu. Xác minh bằng lệnh chạy kiểm tra toàn bộ 1.659 dòng không còn giá trị null ở Level 1/2.
- [x] 1.2 Phân luồng dữ liệu Online (1.347 sản phẩm) vs Offline (312 sản phẩm), xuất file `output/reconciliation/Master_1659_Reconciled_Clean.xlsx` và `output/shopify_import_final/Shopify_Import_Online_Products_v2.csv`. Xác minh số lượng dòng đúng 1.347 sản phẩm online và kiểm tra cột `Type` (Level 1) cùng `Tags` (Level 2).

## 2. Pipeline Tiền Xử Lý & Cắt Ảnh HD Studio Từ 1.659 Ảnh Gốc

- [x] 2.1 Xây dựng module trích xuất ảnh HD `scripts/hd_studio_crop_pipeline.py` với chuẩn hóa EXIF orientation, phân tích hai mặt bao bì (loại trừ mặt barcode/bảng dinh dưỡng, giữ mặt trước thương hiệu), và tính toán bounding box có Safe Margin (+6% đến +8%). Xác minh bằng việc chạy thử nghiệm trên batch 20 ảnh mẫu và kiểm tra trực quan viền không bị cắt lẹm.
- [x] 2.2 Xây dựng module ghép Canvas nền trắng Studio (`#FFFFFF`) kích thước chuẩn và căn giữa quang học (Optical Center Alignment), xuất ảnh chất lượng cao `<barcode>.jpg` vào thư mục `output/shopify_import_final/HD_Studio_Front_Images/`. Xác minh ảnh đầu ra có độ phân giải tối thiểu 1200px chiều cao và tỷ lệ portrait.
- [x] 2.3 Thực thi batch toàn bộ 1.659 sản phẩm với đa tiến trình (ProcessPoolExecutor) và tích hợp Automated QC Gateway kiểm tra 100% ảnh đầu ra (báo cáo ảnh rỗng/lỗi). Xác minh báo cáo kiểm toán QC đạt 100% pass.

## 3. Cập Nhật Cổng Thẩm Định Web Inspection Portal

- [x] 3.1 Cập nhật `web/public/data/products.json` với dữ liệu mới gồm trường `category_level_1` và `category_level_2`, kèm link ảnh HD Studio mới. Xác minh file JSON được tạo hợp lệ và chứa đủ 1.659 sản phẩm.
- [x] 3.2 Cập nhật giao diện `web/src/components/FilterBar.tsx` để hỗ trợ lọc theo Dropdown Level 1 và Dropdown Level 2. Xác minh web build thành công (`npm run build`).

## 4. Đồng Bộ Shopify Live & Tái Cấu Trúc Menu 2 Tầng

- [x] 4.1 Cập nhật script `scripts/sync_to_shopify_live.py` để hỗ trợ upload ảnh HD mới lên Shopify CDN, cập nhật in-place `product_type = Category Level 1` và bổ sung `subcat:<Level 2>` vào `tags`. Chạy thử nghiệm dry-run trên 10 sản phẩm và xác minh kết quả API thành công.
- [x] 4.2 Xây dựng script `scripts/setup_nested_navigation_menu.py` sử dụng Shopify GraphQL Navigation API để tạo Menu chính 2 tầng lồng nhau (Nested Menu Items: Cấp 1 -> Cấp 2 tương ứng) và các Smart Collections tự động. Xác minh cấu trúc menu trên Shopify Admin.
- [x] 4.3 Thực thi sync toàn bộ 1.347 sản phẩm Online lên Live Store `rabuta.dk` và chạy script kiểm toán `scripts/audit_shopify_live_catalog.py` để nghiệm thu catalog 100% đạt chuẩn.
