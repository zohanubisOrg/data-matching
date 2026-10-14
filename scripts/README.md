# HƯỚNG DẪN CẤU TRÚC SCRIPTS XỬ LÝ ẢNH & BARCODE

Thư mục `scripts/` đã được tinh gọn từ **163 files** xuống còn **15 script cốt lõi**, phục vụ chuyên biệt cho bài toán xuất ảnh `output/barcode_first` và mô hình nhận diện bao bì YOLO.

---

## 1. Nhóm Barcode-First Pipeline (Nhiệm vụ cốt lõi)
* **`barcode_first_pipeline.py`**: Pipeline trung tâm. Đọc barcode từ ảnh kho, đối chiếu danh mục `Rabuta.12.10.2026_original.xlsx`, xoay đứng và tách mặt trước (`front/`), mặt sau (`back/`).
* **`build_catalog_pairs.py`**: Ghép cặp ảnh đối ứng Mặt Trước & Mặt Sau cho từng barcode.
* **`accept_tagged_backs.py`**: Xác thực và chấp thuận các ảnh mặt sau đã được gắn barcode chuẩn.
* **`repair_catalog_backs.py`** & **`repair_back_geometry.py`**: Hiệu chỉnh hình học và tối ưu độ tương phản cho mặt sau.
* **`audit_tagged_fronts.py`**: Đánh giá chất lượng và tỷ lệ đứng của ảnh mặt trước.
* **`fill_missing_catalog_images.py`**: Quét và bù các sản phẩm chưa có ảnh hoàn chỉnh.

---

## 2. Nhóm Thị giác Máy tính YOLO & Studio Portrait
* **`cv_front_detector.py`**: Bộ phát hiện mặt trước Hybrid (kết hợp YOLO và OpenCV Heuristic).
* **`prepare_yolo_dataset.py`**: Tự động sinh dữ liệu train/val chuẩn YOLO từ 1.260 ảnh kho.
* **`train_yolo_packaging.py`**: Script huấn luyện YOLO (YOLO11n) nhận diện Front/Back/Barcode.
* **`compare_yolo_vs_cv_vs_gemini.py`**: Đối soát hiệu năng và IoU giữa YOLO, OpenCV và Gemini AI.
* **`hd_studio_crop_pipeline.py`**: Cắt ảnh chuẩn Studio nền trắng HD đưa lên CDN.
* **`fast_barcode_and_crop_fixer.py`**: Tiện ích xử lý nhanh các ảnh crop lỗi.
* **`detect_all_front_boxes.py`**: Trích xuất tọa độ hàng loạt mặt trước.

---

## 3. Các thư mục lưu trữ (Archive & Modules)
* **`scripts/archive/`**: Chứa 126 script cũ đã được phân loại an toàn:
  * `web_scraping/`: Các script và hình ảnh test crawl Google/Bing.
  * `legacy_excel_master/`: Các script build file Excel 1659 và 89 cột cũ.
  * `one_off_patches/`: Các script fix tạm theo từng lô (1-23, 24-49, 47 missing...).
  * `legacy_batch_runners/`: Các batch runner cũ (G2-G5).
  * `legacy_inspections/`: Các script inspect/audit tạm thời.
* **`scripts/shopify_store/`**: Chứa 22 script liên quan đến Shopify Admin API, GraphQL và dịch thuật 4 thứ tiếng.
