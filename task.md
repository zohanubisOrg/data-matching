# Task List: Nâng cấp Pipeline Ảnh Bao Bì Chuẩn Siêu Thị (P0 Technical Stack)

- [x] **Giai đoạn 1: Barcode Decoding Đa Tầng (Multi-pass ZXing-C++)**
  - [x] 1.1 Xây dựng `src/product_mapper/vision/multipass_barcode.py` (Full-frame + YOLO ROI crop + Deskew + CLAHE + Otsu Binarization) <!-- id: 1.1 -->
  - [x] 1.2 Tích hợp kiểm tra chuẩn mã GS1 Modulo-10 (EAN-13, EAN-8, UPC-A), giữ nguyên định dạng string <!-- id: 1.2 -->
  - [x] 1.3 Kiểm thử đơn vị trên tập ảnh barcode khó (chai lọ, bề mặt cong, nhăn mờ) <!-- id: 1.3 -->

- [x] **Giai đoạn 2: Đánh giá Chất lượng Ảnh (Image Quality Assessment - IQA)**
  - [x] 2.1 Xây dựng `src/product_mapper/vision/quality_assessment.py` (Tenengrad, Laplacian, Glare detection, Framing completeness) <!-- id: 2.1 -->
  - [x] 2.2 Tách biệt 2 bộ tiêu chí chấm điểm: `score_front` (thẩm mỹ bán hàng) và `score_back` (độ rõ nét thông tin/nhãn) <!-- id: 2.2 -->
  - [x] 2.3 Đo lường chất lượng cục bộ trên Bounding Box sản phẩm (không bị nhiễu bởi nền kho) <!-- id: 2.3 -->

- [x] **Giai đoạn 3: Phân loại Góc Chụp & Vị trí (View Classifier)**
  - [x] 3.1 Xây dựng `src/product_mapper/vision/view_classifier.py` (FRONT, BACK, SIDE, DETAIL, UNKNOWN) dựa trên đa tín hiệu (mật độ chữ, bảng dinh dưỡng, màu sắc, barcode) <!-- id: 3.1 -->
  - [x] 3.2 Tích hợp cơ chế trọng tài Gemini Structured Output cho các ca biên (edge cases) <!-- id: 3.2 -->

- [x] **Giai đoạn 4: Ghép cặp Sản phẩm Dựa trên Bằng chứng (Evidence-based Matching)**
  - [x] 4.1 Xây dựng `src/product_mapper/matching/product_matcher.py` đối soát với `Rabuta.12.10.2026_original.xlsx` <!-- id: 4.1 -->
  - [x] 4.2 Thiết lập kiểm tra xung đột thuộc tính: Brand, Product Name, Variant/Flavor, Net Weight <!-- id: 4.2 -->
  - [x] 4.3 Phân loại 3 trạng thái rõ ràng: `MATCHED`, `REVIEW_REQUIRED`, `REJECTED` <!-- id: 4.3 -->

- [x] **Giai đoạn 5: Tích hợp Luồng Xuất Ảnh Chuẩn Webshop & Kiểm thử**
  - [x] 5.1 Xây dựng pipeline xuất ảnh chuẩn `{barcode}-front.jpg` và `{barcode}-back.jpg` vào `output/catalog_pairs/tagged/front-v1` và `back-v1` (`scripts/run_p0_catalog_matcher.py`) <!-- id: 5.1 -->
  - [x] 5.2 Tạo file `manifest.json` ghi nhận đầy đủ audit trail, điểm IQA, bằng chứng ghép cặp <!-- id: 5.2 -->
  - [x] 5.3 Chạy kiểm thử đối soát trên tập mẫu kho thực tế đạt chuẩn 100% precision <!-- id: 5.3 -->
  - [x] 5.4 Xây dựng script nhúng trực tiếp ảnh vào file Excel giao khách (`scripts/embed_p0_images_to_excel.py`) <!-- id: 5.4 -->

- [ ] **Giai đoạn 6: Các Hạng Mục Cần Khắc Phục & Hoàn Thiện Tiếp Theo (Xem FUTURE_ROADMAP_AND_FIXES.md)**
  - [ ] 6.1 Giải quyết 375 dòng trong Queue Audit 2 (230 manual review, 139 missing native source, 2 identity conflicts) <!-- id: 6.1 -->
  - [ ] 6.2 Xử lý các ca bao bì biên (dòng 110 mép cắt, 134 film trong suốt, 140 mép trên, 818 góc nghiêng, 1340 bổ sung mặt trước) <!-- id: 6.2 -->
  - [ ] 6.3 Bổ sung tọa độ X/Y cho 181 dòng trong workbook bàn giao G1 <!-- id: 6.3 -->
  - [ ] 6.4 Định vị và gán ảnh mặt trước cho sản phẩm thứ 1.195 còn thiếu trên Shopify <!-- id: 6.4 -->
  - [ ] 6.5 Nén batch WebP tối ưu dung lượng (85-88% lossy, target ~50-100KB/ảnh cho 1.300+ ảnh) <!-- id: 6.5 -->
  - [ ] 6.6 Hoàn thiện benchmark phân tách nền tự động (U2-Net/YOLO) cho chai lọ, lon và bao bì trong suốt <!-- id: 6.6 -->

