# Hướng Dẫn Deploy G1 Visual Portal Lên Vercel

Cổng thông tin trực quan **G1 Visual Portal** được xây dựng bằng **Next.js 16 (App Router) + React 19 + Tailwind CSS v4**, thiết kế phong cách **Futuristic Dark Mode & Glassmorphism** để khách hàng có thể kiểm tra trực tiếp qua trình duyệt trên máy tính hoặc điện thoại di động.

---

## 🌟 Các Tính Năng Nổi Bật Dành Cho Khách Hàng

1. **Dashboard Chỉ Số Trực Quan**:
   - Thống kê tỷ lệ Barcode đã xác nhận, số lượng khớp POS Shopbox, số lượng cần rà soát thủ công.
2. **Tìm Kiếm & Lọc Đa Chiều Siêu Nhanh**:
   - Tìm kiếm live theo: Barcode, Tên sản phẩm, Thương hiệu (Brand), POS SKU, Tên POS.
   - Lọc theo Tab trạng thái: *Tất cả*, *Đã xác định*, *Khớp POS*, *Cần kiểm tra*.
   - Lọc theo danh mục Thương hiệu.
   - Sắp xếp linh hoạt: Thứ tự gốc, Tên A-Z, Thương hiệu A-Z, Barcode 0-9.
3. **Chuyển Đổi 2 Chế Độ Xem (View Mode)**:
   - **Lưới (Grid)**: Thẻ ảnh trực quan, phóng to khi hover, copy barcode 1-chạm.
   - **Bảng (Table)**: Dạng bảng tính đậm đặc (dense spreadsheet) giúp duyệt nhanh hàng trăm sản phẩm cùng lúc.
4. **Modal Đối Chiếu 2 Mặt Bao Bì (Side-by-Side Inspection)**:
   - Đặt song song **Ảnh mặt trước Website** và **Ảnh chụp bao bì gốc 2 mặt** để khách hàng đối soát trực quan.
   - Hỗ trợ phím mũi tên `←` `→` trên bàn phím để chuyển nhanh giữa các sản phẩm.
5. **Xuất Báo Cáo Tại Chỗ**:
   - Nút **Xuất CSV** tải ngay danh sách đang lọc về máy.
   - Nút **Tải JSON** để tích hợp hệ thống.

---

## 🚀 Hướng Dẫn Deploy Lên Vercel

### Cách 1: Deploy Ngay Bằng Vercel CLI (Khuyên Dùng - Có Link Trong 1 Phút)

1. Mở PowerShell hoặc Terminal tại thư mục `d:\Work\shopify`:
   ```powershell
   cd d:\Work\shopify\web
   npx vercel
   ```
2. Làm theo hướng dẫn trên màn hình:
   - Đăng nhập tài khoản Vercel (nếu chưa đăng nhập).
   - Chọn `Y` để thiết lập project mới.
   - Đặt tên project (ví dụ: `g1-visual-portal`).
   - Chọn đường dẫn `./` (vì đang ở trong thư mục `web`).
3. Sau 30–60 giây, Vercel sẽ trả về đường link trực tiếp (dạng `https://g1-visual-portal.vercel.app`) để bạn gửi cho khách hàng.

---

### Cách 2: Deploy Qua GitHub (Tự Động Cập Nhật Khi Push)

1. Đẩy mã nguồn dự án lên GitHub của bạn:
   ```powershell
   git add .
   git commit -m "feat: complete G1 delivery pipeline and Vercel web portal"
   git push origin main
   ```
2. Truy cập [vercel.com](https://vercel.com) $\rightarrow$ Nhấn **Add New...** $\rightarrow$ **Project**.
3. Chọn Repository GitHub vừa push.
4. Trong phần **Root Directory**, nhấn Edit và chọn thư mục: `web` (hoặc để mặc định vì file `vercel.json` ở thư mục gốc đã tự động cấu hình).
5. Nhấn **Deploy**.

---

## 💻 Cách Xem Trước Trực Tiếp Trên Máy (Localhost)

Nếu bạn muốn kiểm tra giao diện trước trên máy tính:
```powershell
cd d:\Work\shopify\web
npm run dev
```
Mở trình duyệt truy cập: **`http://localhost:3000`**

---

## 🔄 Cập Nhật Dữ Liệu Khi Quét Thêm Ảnh Mới

Khi pipeline Python chạy xong toàn bộ các ảnh hoặc có dữ liệu cập nhật mới trong `output/g1_delivery/`, bạn chỉ cần chạy lệnh sau để tự động tối ưu ảnh WebP và cập nhật web:
```powershell
python scripts/prepare_web_delivery.py
```
Sau đó commit hoặc chạy `npx vercel --prod` để cập nhật dữ liệu mới lên trang web!
