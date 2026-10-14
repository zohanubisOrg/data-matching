# Tasks

## 1. Ground Truth & Identity Engine Setup

- [x] 1.1 Xây dựng module trích xuất Ground Truth từ `Rabuta.12.10.2026_original.xlsx` và kiểm tra đọc chính xác các trường Barcode, Brand, Variant, Net Quantity của 20 sản phẩm mẫu
- [x] 1.2 Xây dựng bộ lọc Deterministic Identity Matcher với cơ chế chặn cứng (Hard Conflict Filter) loại bỏ sai lệch về Brand, Variant (vd: Coconut vs Mangosteen), và Net Quantity

## 2. Multi-Source Harvester (Front & Back)

- [x] 2.1 Xây dựng harvester cho Open Food Facts API lấy ảnh RAW camera gốc (`.full.jpg` >= 2500px) cho cả Mặt trước và Mặt sau (Ingredients/Packaging)
- [x] 2.2 Xây dựng harvester cho EU B2B Distributors & Google Search khóa cứng `"{barcode}"` kèm bộ lọc Large Image và xác thực nội dung chống thumbnail nén

## 3. Image Post-Processing Studio

- [x] 3.1 Xây dựng module xử lý Mặt trước: Tự động sửa xoay dọc (Portrait), tách nền AI đưa về nền trắng tinh `#FFFFFF`, căn giữa khung vuông 1:1 (1600x1600 px)
- [x] 3.2 Xây dựng module xử lý Mặt sau: Giữ nguyên nhãn phẳng, tăng tương phản nét chữ (Sharpen & Contrast Enhancement) để đọc rõ thành phần dinh dưỡng

## 4. Pilot 20 Execution & Verification

- [x] 4.1 Chạy pipeline thử nghiệm trên 20 sản phẩm đầu tiên, lưu 40 file ảnh vào `output/webshop_hd_delivery/front/` và `output/webshop_hd_delivery/back/`
- [x] 4.2 Xuất bảng đối soát `output/Rabuta_2_Sided_Pilot_Audit.xlsx` và trang web xem trước trực quan `output/pilot_20_gallery.html` để người dùng nghiệm thu
