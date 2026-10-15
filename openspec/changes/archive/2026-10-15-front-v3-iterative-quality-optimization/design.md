# Design: 10-Iteration Convergence Architecture for Front-v3 Packshot Quality

## Context

Xem chi tiết động lực và bối cảnh tại `proposal.md`. Sau bước khắc phục ban đầu, thư mục `output/catalog_pairs/tagged/front-v3` đã giải quyết toàn bộ các lỗi thuật toán thô. Thiết kế này tập trung vào cấu trúc vòng lặp 10 chu kỳ (10-loop convergence engine) để tối ưu chất lượng quang học và thẩm mỹ chuẩn webshop thương mại điện tử.

## Goals / Non-Goals

**Goals:**
- Thiết lập kịch bản thực thi vòng lặp 10 chu kỳ (`scripts/run_iterative_refinement_loop.py`) tự động đo lường và tinh chỉnh chất lượng ảnh.
- Thuật toán tăng nét thích ứng cho Nhóm 2 (Adaptive Multi-pass Sharpening) giúp chữ trên nhãn mác nét căng nhưng không sinh quầng sáng (halo) và không tăng hạt (grain).
- Kiểm tra và làm sạch 100% biên nền canvas cho Nhóm 3, bảo đảm 8px viền ngoài cùng đạt trắng tinh `#FFFFFF`.
- Ghi nhận báo cáo định lượng qua từng chu kỳ: Laplacian trung bình, độ tương phản, số lượng ảnh đạt chuẩn loại 1.
- Tự động dừng sớm nếu chỉ số chất lượng bão hòa (tốc độ cải thiện < 0.5% qua 2 chu kỳ).
- Đồng bộ và nhúng lại 3 cột ảnh vào file Excel đối chiếu với toàn bộ mã Drawing XML duy nhất.

**Non-Goals:**
- Không thay đổi hoặc xử lý lại kho ảnh mặt sau [`back-v2`](file:///d:/Work/shopify/output/catalog_pairs/tagged/back-v2) đã được chắt lọc chuẩn.
- Không thay thế hoặc làm biến dạng góc cắt nguyên bản của Nhóm 2 (ảnh người dùng tự lưu).

## Decisions

### 1. Kiến Trúc Vòng Lặp Hội Tụ (Convergence Loop Controller)
- **Thiết kế**: Mỗi vòng lặp $i \in [1, 10]$ sẽ thực hiện 4 pha:
  1. *Audit & Measure*: Quét toàn bộ 1.350 ảnh, tính toán Laplacian variance, phát hiện điểm biên, đo độ tương phản.
  2. *Adaptive Refine*: Tinh chỉnh tham số (radius, percent, threshold) dựa trên khoảng cách giữa chỉ số hiện tại và ngưỡng mục tiêu.
  3. *Validate & Log*: Ghi nhận metric của chu kỳ $i$ vào `iteration_quality_metrics.json`.
  4. *Convergence Check*: Nếu độ tăng trưởng chất lượng toàn hệ thống $\Delta Q < 0.5\%$, kích hoạt ngắt sớm (Early Stopping) để bảo vệ ảnh không bị xử lý thừa.
- **Phương án thay thế đã cân nhắc**: Chạy 1 pass cứng với thông số cố định. *Lý do loại bỏ*: Dễ gây cháy nét cho ảnh vốn đã khá nét hoặc không đủ nét cho ảnh mờ.

### 2. Thuật Toán Tăng Nét Thích Ứng Không Quầng (Halo-Free Adaptive Sharpening)
- Sử dụng kết hợp bộ lọc Unsharp Masking có điều kiện ngưỡng (Thresholding) và Bilateral Filter nhằm bảo vệ các vùng nền phẳng, chỉ tăng nét các cạnh chữ và logo của bao bì.
- Giữ nguyên 100% bounding box và canvas ban đầu của người dùng cho Nhóm 2.

### 3. Cơ Chế Xử Lý Khóa File Excel & XML Drawing Sequence
- File Excel đối chiếu luôn được ghi vào `Rabuta_master_SKU_categories_ingredients_final_audit_v3_remediated.xlsx` (tránh lỗi khóa file của Windows khi người dùng đang mở xem) và tự động đồng bộ sang file chính khi người dùng đóng Excel.
- Tái lập chỉ mục Drawing ID từ 1 đến N trong `drawing1.xml` bằng `clean_xml_drawing_ids`.

## Risks / Trade-offs

- **[Risk]** Xử lý lặp lại có thể làm tăng nhiễu hạt (noise/artifacts) nếu chạy liên tục mà không kiểm soát.
  → **Mitigation**: Thiết lập bộ kiểm soát giới hạn trên (saturation/noise clipping filter) và cơ chế bão hòa: khi ảnh đã đạt độ nét tối ưu, vòng lặp sau sẽ tự động bỏ qua (bypass).
- **[Risk]** Thời gian chạy 10 vòng lặp cho 1.350 ảnh có thể lâu nếu xử lý lại từ đầu.
  → **Mitigation**: Cache thumbnail và chỉ xử lý thực sự các ảnh cần tối ưu thêm trong từng chu kỳ.
