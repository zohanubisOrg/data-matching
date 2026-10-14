# Kế hoạch Triển khai Tích hợp Mô hình YOLO Nhận diện Mặt Trước & Mặt Sau Sản Phẩm

## 1. Mục tiêu
Nâng cấp pipeline thị giác máy tính bằng cách tích hợp mô hình **YOLO (YOLOv8 / YOLO11)** nhằm:
- Nhận diện chính xác vị trí Bounding Box (Mặt trước `front`, Mặt sau `back`, Mã vạch `barcode`) với độ trễ cực thấp (~15-30ms) và chi phí API bằng 0.
- Loại bỏ hoàn toàn lỗi "cắt cụt mép ảnh" (faulty crop) thường gặp khi để Gemini tự ước lượng tọa độ 0-1000.
- Cắt ảnh studio dọc chuẩn portrait (tỉ lệ chiều cao > chiều rộng, padding an toàn 3-4%) trước khi đẩy lên Shopify CDN hoặc gửi cho Gemini trích xuất dữ liệu dinh dưỡng/thành phần.

---

## 2. Các Bước Thực Hiện

### Giai đoạn 1: Chuẩn bị Môi trường & Dataset Huấn luyện
1. **Cài đặt thư viện:**
   - Cài đặt `ultralytics` (`torch`, `torchvision`).
2. **Sinh Dataset tự động từ Cache hiện có (Pseudo-labeling):**
   - Viết script `scripts/prepare_yolo_dataset.py`:
     - Tận dụng hơn 1.196 mẫu đã cache tọa độ chính xác trong `output/shopify_import/g2_g5_front_boxes.json` và `output/g1_delivery/front_layout_boxes.json`.
     - Tự động chuyển đổi sang chuẩn YOLO (`images/train`, `images/val`, `labels/train`, `labels/val`, file cấu hình `packaging.yaml`).
     - Định nghĩa 3 classes:
       - `0: product_front` (Mặt trước sản phẩm)
       - `1: product_back` (Mặt sau / nhãn dinh dưỡng)
       - `2: barcode` (Vùng mã vạch)

### Giai đoạn 2: Huấn luyện & Đóng gói Model YOLO
1. **Huấn luyện mô hình nhẹ (YOLOv8n / YOLO11n):**
   - Viết script `scripts/train_yolo_packaging.py`.
   - Cấu hình phù hợp phần cứng: GPU NVIDIA GeForce GTX 1650 (4GB VRAM), batch size 8–16, imgsz 640, epochs 30–50.
   - Xuất trọng số tối ưu: `weights/packaging_yolo_best.pt` và phiên bản siêu nhẹ `weights/packaging_yolo.onnx` (để chạy cực nhanh với onnxruntime sẵn có).

### Giai đoạn 3: Xây dựng Module YOLO Detector
1. **Tạo module `src/product_mapper/vision/yolo_detector.py`:**
   - Nhận ảnh đầu vào (PIL hoặc đường dẫn Path).
   - Trả về cấu trúc dữ liệu chuẩn hóa tương thích với pipeline hiện tại:
     - `front_box_2d: [ymin, xmin, ymax, xmax]` (thang 0-1000).
     - `back_box_2d: [ymin, xmin, ymax, xmax]` (thang 0-1000).
     - `barcode_box_2d: [ymin, xmin, ymax, xmax]` (thang 0-1000).
     - `confidence: float`.
     - Hỗ trợ auto-crop và căn chỉnh xoay thẳng đứng (portrait upright).

### Giai đoạn 4: Tích hợp vào Pipeline Đa Tầng (Hybrid Pipeline)
1. Cập nhật `scripts/cv_front_detector.py` hoặc tạo runner ưu tiên:
   - **Tầng 1 (YOLO):** Chạy trước. Nếu phát hiện front/back/barcode với độ tin cậy $>0.75 \rightarrow$ dùng ngay kết quả crop của YOLO.
   - **Tầng 2 (OpenCV Heuristic):** Dự phòng nếu YOLO không tìm thấy hoặc trọng số chưa tải.
   - **Tầng 3 (Gemini Multimodal VLM):** Chỉ gửi ảnh crop chất lượng cao đã cắt viền đẹp để đọc OCR, dịch 4 thứ tiếng và bóc tách bảng dinh dưỡng EU 1169/2011.

### Giai đoạn 5: Thử nghiệm & Đối chiếu Kết quả (Benchmark)
1. Viết script kiểm thử so sánh: `scripts/compare_yolo_vs_cv_vs_gemini.py`.
2. Kiểm tra trên tập mẫu thực tế (mì Hảo Hảo, snack Dorkbua, v.v.).
3. Đánh giá: Độ ôm sát mép bao bì (IoU), tốc độ suy luận (ms), và chất lượng ảnh crop.
