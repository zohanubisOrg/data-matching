# Proposal: 10-Iteration Convergence Loop For Optimal Front-v3 Packshot Quality

## Why

Sau khi hoàn thành đợt xử lý phân loại 3 nhóm ban đầu (565 SKU đạt chuẩn, 84 SKU ảnh người dùng lưu được tăng nét bảo toàn góc cắt, 701 SKU khôi phục từ Master 1659 và ảnh gốc), toàn bộ catalog đã giải quyết triệt để các lỗi thô (ảnh đôi, lẹm mép, mất vỏ). Tuy nhiên, để đạt chất lượng chuẩn studio thương mại điện tử cao cấp nhất (độ sắc nét đồng đều tối đa, không bị viền gai halo, căn giữa chuẩn xác, viền nền trắng tuyệt đối 100% #FFFFFF), cần thiết lập một quy trình lặp tự động (10-loop convergence engine) để đo lường, tối ưu hóa thích ứng qua từng vòng lặp cho đến khi đạt điểm bão hòa chất lượng tối ưu nhất.

## What Changes

- **10-Loop Refinement Engine**: Xây dựng kịch bản thực thi vòng lặp tối ưu hóa chất lượng ảnh (tối đa 10 vòng lặp có cơ chế tự dừng khi đạt hội tụ bão hòa).
- **Đánh Giá & Tối Ưu Thích Ứng Theo Nhóm**:
  - **Nhóm 1**: Kiểm định bảo toàn, kiểm tra viền nền studio 4 góc đạt chuẩn trắng tinh `(255, 255, 255)`.
  - **Nhóm 2 (Ảnh người dùng tự lưu)**: Áp dụng thuật toán tăng nét thích ứng nhiều tầng (Multi-Scale Adaptive Sharpening + Bilateral Edge Preservation) qua từng vòng lặp, nâng dần chỉ số Laplacian lên ngưỡng tối ưu mà **tuyệt đối không làm vỡ hạt, không tạo viền gai (ringing/halo) và giữ nguyên 100% bố cục cắt gốc**.
  - **Nhóm 3 (Ảnh khôi phục)**: Chuẩn hóa căn giữa quang học (optical center of mass), chuẩn hóa tỷ lệ chiếm dụng canvas $85\% \pm 2\%$, làm sạch nền biên không để sót pixel mờ.
- **Metric Tracking & Logging**: Ghi nhận bảng đo lường chất lượng sau mỗi vòng lặp (`output/catalog_pairs/iteration_quality_metrics.json`) bao gồm: Laplacian Variance trung bình, tỷ lệ đạt chuẩn Nhóm 1, tỷ lệ hội tụ.
- **Tái Nghiệm Thu & Xuất Excel 3 Cột**: Xuất kết quả cuối cùng vào `Rabuta_master_SKU_categories_ingredients_final_audit_v3_remediated.xlsx` (và đồng bộ sang file audit chính khi đóng Excel), bảo đảm 100% Drawing ID XML duy nhất.

## Capabilities

### New Capabilities
- `catalog-image-quality/iterative-refinement-loop`: Quy trình tự động lặp 10 vòng tối ưu hóa chất lượng ảnh webshop mặt trước (`front-v3`), nâng cao độ nét thích ứng, chuẩn hóa nền studio, và đối chiếu song song 3 cột trong Excel.

### Modified Capabilities
*(Không có)*

## Impact
- Thư mục ảnh `output/catalog_pairs/tagged/front-v3`: Được nâng cấp đạt chất lượng cao nhất sau 10 vòng lặp.
- File Excel kiểm tra `Rabuta_master_SKU_categories_ingredients_final_audit_v3_remediated.xlsx` (và `Rabuta_master_SKU_categories_ingredients_final_audit_v3.xlsx`): Nhúng phiên bản ảnh hoàn hảo nhất.
- Thư mục `back-v2` và ảnh Ground Truth của khách: Được bảo toàn nguyên vẹn 100% để đối chiếu mắt thường.
