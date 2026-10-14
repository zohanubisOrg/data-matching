# Proposal: Rebuild Master Catalog with HD Studio Images & 2-Tier Hierarchy

## Why

Khách hàng (anh Thông Tiến Nguyễn, Rabuta Asian Supermarket) vừa cung cấp bộ phân loại cập nhật 2 tầng (`Category Level 1` và `Category Level 2`) trong file `Esbjerg_Asian_Market_Master_1659_updated.xlsx` và yêu cầu chuẩn hóa toàn bộ danh mục để cập nhật lên Shopify. Để đảm bảo catalog đạt chất lượng cao nhất (Studio standard), loại bỏ hoàn toàn các lỗi cắt ảnh trước đây (cắt lẹm mép, méo góc, nhầm mặt sau, tỷ lệ không đều), và đồng bộ chính xác hệ thống danh mục 2 tầng lên Live Store `rabuta.dk`, chúng ta cần tái thiết lập toàn diện pipeline tiền xử lý ảnh và tiền xử lý dữ liệu từ 1.659 ảnh gốc độ phân giải cao.

## What Changes

- **Tiền xử lý & Vá Dữ liệu 100%**: Vá 4 bản ghi bị khuyết thiếu Category Level 1/Level 2 trong file khách gửi, kiểm toán GS1 Modulo-10 checksum 100% mã vạch, chuẩn hóa kiểu chuỗi không lỗi số mũ, khớp 1:1 POS SKU Shopbox.
- **Pipeline Tiền xử lý & Cắt ảnh HD Studio**: Chuẩn hóa EXIF chiều dọc, phân tách thông minh 2 mặt bao bì (loại trừ mặt sau có barcode/bảng dinh dưỡng, giữ mặt trước thương hiệu), AI Bounding Box với Safe Margin +6% đến +8% chống lẹm mép, đặt trên Canvas nền trắng Studio 1600x1600 / 1200x1600, cân giữa tự động.
- **Cổng Kiểm toán Chất lượng Tự động (Automated QC Gateway)**: Kiểm tra tự động 100% ảnh đầu ra (kích thước, tỷ lệ chân dung, không ảnh rỗng/lỗi).
- **Đồng bộ Shopify In-Place & Menu 2 Tầng**: Cập nhật đè ảnh HD chất lượng cao lên Shopify CDN, gán Product Type = Level 1, Tags = Level 2, thiết lập Main Navigation Menu 2 tầng (Nested dropdown) và Smart Collections tự động.
- **Cập nhật Web Inspection Portal**: Cập nhật dữ liệu và ảnh mới lên cổng web để đối chiếu Side-by-Side (Ảnh cắt vs Ảnh gốc).

## Capabilities

### New Capabilities
- `catalog-data-reconciliation`: Tiền xử lý, kiểm toán Modulo-10, vá dữ liệu khuyết thiếu và chuẩn hóa cấu trúc phân loại 2 tầng (Level 1 & Level 2) cho toàn bộ 1.659 sản phẩm.
- `hd-image-studio-pipeline`: Pipeline tiền xử lý và cắt ảnh bao bì mặt trước chất lượng cao từ 1.659 ảnh gốc, canvas nền trắng studio, căn giữa và kiểm định tự động 100%.
- `shopify-live-store-sync`: Đồng bộ catalog sản phẩm, tải ảnh lên Shopify CDN, thiết lập Smart Collections và Menu điều hướng 2 tầng trên cửa hàng live `rabuta.dk`.

### Modified Capabilities
None. (Dự án bắt đầu chuẩn hóa hệ thống specs mới cho đợt nâng cấp toàn diện này).

## Impact

- **Ảnh sản phẩm**: 1.659 ảnh sản phẩm mới được cắt sắc nét, đặt tên chuẩn theo `<barcode>.jpg`, lưu trữ tại thư mục sản phẩm sạch để tải lên Shopify CDN.
- **Dữ liệu**: Bảng tính Master và file import Shopify được nâng cấp bổ sung đầy đủ trường phân loại Level 1 & Level 2.
- **Cửa hàng Shopify**: Cập nhật hình ảnh, Product Type, Tags và Navigation Menu trên `https://rabuta.dk`.
- **Web Portal**: Cập nhật dữ liệu trên `https://web-mu-seven-60.vercel.app`.
