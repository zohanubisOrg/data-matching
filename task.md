# Task List: Chẩn đoán & Nâng cấp Toàn diện Catalog Front-V3

## 0. Giao thức Cộng tác Trực tiếp cùng Người Dùng (Live User Collaboration)
- [x] Thiết lập ledger `output/catalog_pairs/user_verified_overrides.json` để ghi nhận ưu tiên cao nhất từ User <!-- id: 0.1 -->
- [/] **Quy tắc ghi đè người dùng (User Override Priority)**: Bất kỳ ảnh nào người dùng xác nhận đạt/cập nhật trực tiếp sẽ được đánh dấu `USER_VERIFIED_PASSED`, bảo vệ tuyệt đối và không để bất kỳ subagent nào ghi đè. <!-- id: 0.2 -->


## 1. Sao lưu An Toàn & Chẩn đoán Toàn diện (Đã Hoàn Thành)
- [x] 1.1 Sao lưu toàn bộ 1.178 file `front-v3` sang `output/catalog_pairs/front-v3-backups/before-enhancement-2026-10-15/` (có snapshot.json) <!-- id: 1.1 -->
- [x] 1.2 Quét chẩn đoán đo độ nét (Laplacian/Tenengrad) và tính toàn vẹn cấu trúc cho 100% (1.178 file) trong `front-v3` <!-- id: 1.2 -->
- [x] 1.3 Đã xuất báo cáo phân loại chi tiết:
  - **326 files (27.7%) `PASSED_SHARP`**: Đạt chuẩn sắc nét -> **Bảo toàn tuyệt đối, không đụng vào!**
  - **316 files (26.8%) `PASSED_BLURRY`**: Cắt đúng bao bì nhưng bị mờ/soft focus -> Chuyển **Subagent 1** làm nét.
  - **62 files (5.3%) `STRUCTURAL_ERROR`**: Sai kích thước (447x447, 600x600...), viền dính bẩn -> Chuyển **Subagent 2** sửa lỗi canvas.
  - **474 files (40.2%) `TOO_BLURRY_OR_DAMAGED`**: Quá mờ không cứu nét được -> Chuyển **Subagent 3** tìm nguồn nét từ Google Search. <!-- id: 1.3 -->

## 2. Triển khai Subagents & Rollback Theo Yêu Cầu Người Dùng
- [x] Đã dừng toàn bộ 4 Subagent theo lệnh dừng của Người dùng <!-- id: 2.1 -->
- [x] Đã Audit toàn diện 476 file bị thay đổi bởi các subagent (lưu tại `output/catalog_pairs/revert_audit_subagents_2026-10-15.json`) <!-- id: 2.2 -->
- [x] ĐÃ REVERT 100% TOÀN BỘ 476 FILE VỀ BẢN LƯU CỦA NGƯỜI DÙNG:
  - Đối soát mã băm SHA-256 trên 1.178 file trong `front-v3` so với bản snapshot: **0 sai lệch (100% byte-for-byte trùng khớp)**.
  - Bảo toàn tuyệt đối mọi ảnh Người dùng đã tự lưu và tự xử lý. <!-- id: 2.3 -->

## 3. Nhúng 3 Cột Đối Chiếu Song Song Vào Master Excel (Đã Hoàn Thành)
- [x] 3.1 Sao lưu bản gốc `Rabuta_master_SKU_categories_ingredients_final.original_backup.xlsx` an toàn tuyệt đối <!-- id: 3.1 -->
- [x] 3.2 Nhúng thành công 3 cột song song trên 1.351 sản phẩm:
  - Cột 23 (W): `Ảnh mặt trước` (1.349 ảnh gốc của khách hàng - ground truth)
  - Cột 24 (X): `Ảnh webshop mặt trước` (1.176 ảnh từ `output/catalog_pairs/tagged/front-v3`)
  - Cột 25 (Y): `Ảnh mặt sau` (1.170 ảnh từ `output/catalog_pairs/tagged/back-v2`)
- [x] 3.3 Đồng bộ hoàn tất vào 3 vị trí file sẵn sàng kiểm tra:
  - `source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx`
  - `output/catalog_pairs/Rabuta_master_SKU_categories_ingredients_final_audit.xlsx`
  - `output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx` <!-- id: 3.2 -->

## 4. Kiểm định & Cập nhật Hoàn thiện front-v4 (Đã Hoàn Thành)
- [x] 4.1 Triển khai hệ sinh thái 4 Subagents (Checker, Reviewer, QA, Decision Engine) <!-- id: 4.1 -->
- [x] 4.2 Agent 4 sản xuất thành công toàn bộ danh mục `output/catalog_pairs/tagged/front-v4` (1.349 file):
  - 100% đạt chuẩn kích thước 2400x2400 studio canvas với viền trắng tinh khiết `#FFFFFF` (lỗi canvas về 0).
  - Giữ nguyên 693 ảnh đạt chuẩn từ v3.
  - Khôi phục bao bì nguyên vẹn từ HD Studio (138 file) và front-v2 (130 file).
  - Khắc phục các ca lật nhầm 90 độ về dáng đứng tự nhiên.
- [x] 4.3 Nhúng toàn bộ ảnh `front-v4` mới nhất vào Master Excel đối chiếu 3 cột song song:
  - Cột 23 (W): `Ảnh mặt trước` (Ảnh gốc khách hàng - 1.349 ảnh)
  - Cột 24 (X): `Ảnh webshop mặt trước (v4)` (1.350 ảnh từ front-v4)
  - Cột 25 (Y): `Ảnh mặt sau` (1.170 ảnh từ back-v2)
- [x] 4.4 Lưu và đồng bộ hoàn tất vào:
  - `output/catalog_pairs/Rabuta_master_SKU_categories_ingredients_final_audit_v4.xlsx`
  - `output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx`
  - `source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx` <!-- id: 4.2 -->

## 5. Cập nhật Pipeline Zohanubis Trước Khi Chạy Giao Hàng Hàng Loạt
- [x] 5.1 **Fix Crop (HeroCropper)**: Tích hợp SIFT Homography RANSAC 4 góc demo cho mọi sản phẩm có demo; cải tiến phát hiện biên vật thể thực thay vì tỷ lệ cố định; gắn cờ không chắc sang review. <!-- id: 5.1 -->
- [x] 5.2 **Fix Mask & Detail Preservation (MattingEngine)**: Phân biệt lỗ thật (quai treo - trùng màu nền studio) vs lỗ khoét rỗng (ruột bao bì); không xóa viền nhựa/chi tiết mỏng ngoài solid mask; bảo toàn góc hộp. <!-- id: 5.2 -->
- [x] 5.3 **Fix Resolution Pipeline (run_zohanubis_pipeline.py)**: Dò tọa độ crop trên proxy, crop trên ảnh nguồn full resolution trước khi standardizer đưa về 2048px (cả front và back). <!-- id: 5.3 -->
- [x] 5.4 **Fix Quality Gate (quality_gate.py & run_zohanubis_pipeline.py)**: Thêm kiểm tra đứt biên khi crop; đối chiếu độ nguyên vẹn với demo/ảnh nguồn; đánh giá chất lượng ảnh back (kiểm tra barcode đọc được); đánh giá thực chất ảnh khách. <!-- id: 5.4 -->
- [x] 5.5 **Fix Healing Loop (run_zohanubis_pipeline.py)**: Tuyệt đối giữ nguyên HARD_FAIL khi retry (n_components > 1, clipping, rỗng); không dùng solidity >= 0.50 để ép nhận ảnh lỗi vào giao hàng; giữ trong quarantine. <!-- id: 5.5 -->
- [x] 5.6 **Fix Reconciler & Pair Matching (reconciler.py & front_matcher.py)**: Không gán cứng ảnh liền kề không barcode; đối chiếu xác minh với Column W demo qua visual embedding trước khi chấp nhận cặp ảnh. <!-- id: 5.6 -->

