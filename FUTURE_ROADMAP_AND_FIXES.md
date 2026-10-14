# 🛠️ DANH SÁCH HẠNG MỤC CẦN KHẮC PHỤC & ĐỊNH HƯỚNG TƯƠNG LAI
## (FUTURE ROADMAP & KNOWN ISSUES TO FIX)
**Dự án:** Rabuta Shopify & POS Catalog Automation Suite  
**Cập nhật ngày:** Tháng 10/2026 | **Tình trạng:** Sẵn sàng cho đợt rà soát tiếp theo  

---

## 1. TỔNG HỢP TRẠNG THÁI HIỆN TẠI (SYSTEM BASELINE)

- **Barcode Decoding & GS1 Modulo-10**: Đã hoàn thành 100% (1.195 / 1.195 sản phẩm hợp lệ, zero-hallucination).
- **POS SKU Matching & Phân loại 16 nhóm**: 100% sản phẩm có mã SKU và nhóm hàng chính xác theo quy chuẩn khách hàng.
- **Shopify Live Catalog**: 1.195 sản phẩm trực tuyến, 8 Smart Collections, hỗ trợ 4 ngôn ngữ (`/`, `/en`, `/vi`, `/th`).
- **Web Portal Kiểm toán (`web/`)**: Next.js 16 + Tailwind v4 + React 19, tìm kiếm, lọc theo barcode, SKU, nhóm hàng và modal soi chi tiết.
- **Test Suite**: 84/84 tests pytest pass 100%.

---

## 2. CÁC HẠNG MỤC CHI TIẾT CẦN FIX TRONG TƯƠNG LAI

### 📌 HẠNG MỤC 1: Xử lý 375 dòng trong Queue Reprocessing (Queue Audit 2)
*(Chi tiết tại `docs/rabuta-background-reprocessing.md` và `scripts/reprocess_rabuta_verified.py`)*

| Phân loại | Số lượng | Mô tả chi tiết & Hành động cần làm |
| :--- | :---: | :--- |
| **`REPROCESSED_NEEDS_REVIEW`** | **4 dòng** | Đã tạo ảnh ứng viên: dòng 266 (Lobo), 304 (Cock mung beans), 669 (YumYum), 1089 (Bibigo pork). **Cần làm:** Soi mép ở độ phân giải gốc (native resolution), kiểm tra độ phủ (coverage) và lem viền (spill). |
| **`NEEDS_MANUAL_REVIEW`** | **230 dòng** | Đã tìm thấy file ảnh gốc trong kho nhưng cần kiểm tra thủ công. **Cần làm:** Xác nhận hướng đứng dọc, kiểm tra viền không bị cắt lẹm, kiểm tra độ phản xạ nilon/màng trong suốt. |
| **`BLOCKED_NEEDS_SOURCE`** | **139 dòng** | Chưa tìm thấy file ảnh gốc native ở đường dẫn đã tra. Ví dụ dòng 597 chưa có mapping native; dòng 1340 chỉ có ảnh mặt sau. **Cần làm:** Tra cứu lại kho ảnh mở rộng hoặc yêu cầu khách gửi ảnh chụp bổ sung. |
| **`BLOCKED_IDENTITY_CONFLICT`** | **2 dòng** | Xung đột mã định danh / barcode bị trùng lặp. Cụ thể mã `8938500075070` dùng chung cho 2 Record ID khác nhau. **Cần làm:** Tra cứu POS đối chiếu để tách hoặc hợp nhất Record ID chính xác. |

---

### 📌 HẠNG MỤC 2: Khắc phục các ca lỗi bao bì cụ thể (Packaging Edge Cases)
Qua đợt rà soát visual audit, đã khoanh vùng các trường hợp bất thường sau cần xử lý:

1. **Dòng 110**: Bao bì bị cắt mép (clipped edge). Cần điều chỉnh bounding box hoặc lấy frame ảnh chụp góc rộng hơn.
2. **Dòng 134 (Udon)**: Màng film trong suốt nằm sát biên mép túi. Cần áp dụng thuật toán Alpha Matting riêng (`film_matting_required=true`) thay vì cắt cứng.
3. **Dòng 140 (Soba)**: Sát mép / bị cắt biên trên. Cần bổ sung padding hoặc dùng ảnh nguồn đầy đủ.
4. **Dòng 818**: Bị thiếu biên bên trái/phải do góc chụp nghiêng.
5. **Dòng 1086**: Bao bì mặt trước bên phải sát sát biên khung hình.
6. **Dòng 1296**: Cần xác minh đơn vị bán lẻ (single pack) hay ảnh chụp thùng carton (carton box).
7. **Dòng 1340**: Ảnh hiện có chỉ là mặt sau (back face), cần bổ sung ảnh mặt trước chính diện.

---

### 📌 HẠNG MỤC 3: Bổ sung dữ liệu tọa độ X/Y cho 181 dòng trong Workbook Bàn giao G1
- **Hiện trạng:** Có 181 dòng trong file bàn giao chưa có tọa độ hộp bounding box (`[ymin, xmin, ymax, xmax]`) của bao bì.
- **Hành động cần làm:** Chạy script nhận diện tự động (`scripts/detect_all_front_boxes.py` hoặc `scripts/cv_front_detector.py`) kết hợp kiểm tra để điền đủ dữ liệu X/Y, giúp file Excel đạt 100% chuẩn kiểm toán.

---

### 📌 HẠNG MỤC 4: Hoàn thiện 1 sản phẩm còn thiếu ảnh trên Shopify
- **Hiện trạng:** 1.194 / 1.195 sản phẩm đã có ảnh studio đứng dọc trên Shopify CDN.
- **Hành động cần làm:** Đối soát danh sách sản phẩm live để xác định chính xác barcode/SKU của sản phẩm thứ 1.195 và gán ảnh mặt trước tương ứng.

---

### 📌 HẠNG MỤC 5: Tối ưu hóa dung lượng ảnh WebP (Batch WebP Compression)
- **Hiện trạng:** Một số ảnh canvas 2400×2400 hiện đang lưu ở định dạng WebP không nén / dung lượng lớn (1–4 MB/ảnh), khiến tổng thư mục `web/public/products/front/` nặng ~1.4 GB.
- **Hành động cần làm:**
  - Viết script nén hàng loạt (batch lossy WebP, quality 85–88%, kích thước canvas tối đa 1200–1600px cho web).
  - Mục tiêu đưa dung lượng trung bình về **~50–100 KB/ảnh**, giúp web portal tải siêu tốc và giảm tải băng thông repository / CDN.

---

### 📌 HẠNG MỤC 6: Huấn luyện & Hoàn thiện mô hình tách nền tự động (U2-Net / Custom YOLO)
- **Hiện trạng:** Thử nghiệm U2-Net trên các bao bì phức tạp cho độ phủ từ 59% đến 81%, chưa đạt ngưỡng nghiệm thu tự động (≥98.5% coverage, ≤2% spill).
- **Hành động cần làm:**
  - Mở rộng tập benchmark 20–30 mẫu gồm đủ 3 nhóm khó: chai lọ thủy tinh, lon kim loại có độ bóng lóa, và bao bì túi bóng kính trong suốt.
  - Tinh chỉnh mô hình segmentation hoặc kết hợp YOLO-OBB (Oriented Bounding Box) để đạt độ chuẩn xác cấp Studio.

---

### 📌 HẠNG MỤC 7: Kiểm toán định kỳ Live Shopify Store & Bản dịch
- **Hành động cần làm:**
  - Chạy `python scripts/audit_shopify_live_catalog.py` định kỳ để theo dõi trạng thái các sản phẩm mới thêm.
  - Đảm bảo 8 Smart Collections và hệ thống Subfolders 4 ngôn ngữ (`/`, `/en`, `/vi`, `/th`) luôn đồng bộ 100% khi khách cập nhật kho hàng Shopbox POS.
