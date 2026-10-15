# Tasks: Triển Khai Kiểm Định & Xử Lý front-v3 Theo Bộ Tiêu Chí

## 1. Kiểm Tra & Phân Loại 3 Nhóm Đối Chiếu Thị Giác

- [x] 1.1 Quét đối chiếu toàn bộ 1.350 SKU giữa Cột 24 (`front-v3`), Cột 23 (Ground Truth khách) và Cột 25 (`back-v2`), ghi nhận chi tiết vào ledger `output/catalog_pairs/front_v3_detailed_inspection.json` và xác minh file tồn tại
- [x] 1.2 Phân loại danh sách sản phẩm thành 3 nhóm rõ rệt:
  - Nhóm 1: Đạt chuẩn 100% (bảo toàn).
  - Nhóm 2: Ảnh người dùng tự lưu cắt chuẩn bị mờ (chuyển luồng tăng nét riêng).
  - Nhóm 3: Lỗi thuật toán cũ (ảnh đôi, cắt lẹm, mất vỏ).
  và xác minh qua báo cáo tổng hợp `output/catalog_pairs/front_v3_triage_summary.json`

## 2. Xử Lý Tăng Nét Độc Lập Cho Nhóm 2 (Tuyệt Đối Không Ghi Đè)

- [x] 2.1 Giữ nguyên 100% bố cục và góc cắt gốc của người dùng cho các sản phẩm Nhóm 2, áp dụng bộ lọc tăng nét Unsharp Masking & Detail Enhancement, lưu cập nhật vào `front-v3` và xác minh chỉ số độ nét Laplacian tăng trên 30%
- [x] 2.2 Xác nhận không có bất kỳ file nào thuộc Nhóm 2 bị thay thế hoặc ghi đè bằng ảnh khác ngoài góc cắt gốc của người dùng

## 3. Khôi Phục Nguồn Sạch Master 1659 Cho Nhóm 3

- [x] 3.1 Tra cứu các sản phẩm Nhóm 3 sang kho `Master_1659_Clean_Front_Images` theo mã barcode
- [x] 3.2 Chuẩn hóa ảnh từ Master 1659 lên canvas studio $2400 \times 2400$ nền trắng tinh `#FFFFFF`, lề an toàn 85%, và ghi đè có kiểm soát vào đúng các file tương ứng trong `front-v3`
- [x] 3.3 Xác minh các file Nhóm 3 trong `front-v3` không còn lỗi ảnh đôi, không còn mép cắt guillotine, và đầy đủ 100% vỏ bao bì

## 4. Tái Nghiệm Thu & Cập Nhật File Excel 3 Cột

- [x] 4.1 Quét tái nghiệm thu 100% thư mục `front-v3` và xuất báo cáo nghiệm thu hoàn tất `output/catalog_pairs/front_v3_final_qa_verdict.json`
- [x] 4.2 Cập nhật file Excel đối chiếu `Rabuta_master_SKU_categories_ingredients_final_audit_v3.xlsx` hiển thị phiên bản `front-v3` mới nhất cạnh Cột W và Cột Y
- [x] 4.3 Chuẩn hóa tuần tự toàn bộ mã Drawing `cNvPr id` trong XML của file Excel và xác minh mở mượt mà trong Microsoft Excel không có bất kỳ cảnh báo nào
