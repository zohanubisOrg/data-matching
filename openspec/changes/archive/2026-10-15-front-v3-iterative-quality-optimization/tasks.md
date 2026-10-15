# Tasks: Triển Khai 10 Vòng Lặp Tối Ưu Hóa Chất Lượng Ảnh front-v3

## 1. Xây Dựng Động Cơ Vòng Lặp 10 Chu Kỳ

- [x] 1.1 Viết kịch bản `scripts/run_iterative_refinement_loop.py` thiết lập bộ điều khiển lặp tối đa 10 chu kỳ, đo lường độ nét trung bình (Laplacian Variance), độ tương phản và tỷ lệ bao phủ canvas
- [x] 1.2 Tích hợp thuật toán tăng nét thích ứng đa tầng (Adaptive Multi-Scale Sharpening) cho Nhóm 2, giữ nguyên 100% góc cắt gốc và chống tạo quầng halo
- [x] 1.3 Tích hợp bộ kiểm tra và chuẩn hóa biên nền trắng tinh `#FFFFFF` (8px viền) và căn giữa quang học cho Nhóm 3

## 2. Thực Thi 10 Vòng Lặp Đo Lường & Tối Ưu Hóa Chất Lượng

- [x] 2.1 Thực thi vòng lặp qua từng chu kỳ, lưu trữ ảnh tối ưu vào `front-v3` và ghi nhận chỉ số vào `output/catalog_pairs/iteration_quality_metrics.json`
- [x] 2.2 Đánh giá tiêu chí hội tụ bão hòa ($\Delta Q < 0.5\%$) hoặc chạm mốc chu kỳ 10, xác nhận không có hiện tượng cháy hạt hay méo mó nhãn mác
- [x] 2.3 Xuất báo cáo phân tích cải tiến chất lượng toàn diện `output/catalog_pairs/iteration_final_summary.json`

## 3. Tái Tạo & Đồng Bộ File Excel Đối Chiếu 3 Cột

- [x] 3.1 Nhúng ảnh `front-v3` tối ưu nhất vào Cột 24 (X) cạnh Cột 23 (W - Khách) và Cột 25 (Y - `back-v2`) vào `output/catalog_pairs/Rabuta_master_SKU_categories_ingredients_final_audit_v3_remediated.xlsx`
- [x] 3.2 Chuẩn hóa toàn bộ mã Drawing `cNvPr id` trong file XML để đảm bảo tính duy nhất và tuần tự, không bị cảnh báo khi mở Excel
- [x] 3.3 Thử nghiệm đồng bộ sang file audit chính `Rabuta_master_SKU_categories_ingredients_final_audit_v3.xlsx` khi file được mở khóa
