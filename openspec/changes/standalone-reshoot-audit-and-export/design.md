# Design: Standalone Reshoot Audit & Customer Sheet Export

## Context
See `proposal.md` for motivation.
Hiện tại trong `src/product_mapper/zohanubis/`, ta đã có các module nền tảng sẵn có:
- `ImageSanitizer`: quét và nạp ảnh đa định dạng (JPG, PNG, WebP, HEIC).
- `ParallelBarcodeScanner`: quét barcode đa luồng và tạo cache `barcode_scan_cache.json`.
- `BarcodeReconciler`: đối soát mã barcode với danh mục master `Rabuta_master_SKU_categories.xlsx` (1.351 dòng) và xử lý chuỗi sequence (G1, Nyt, G4).
- `QualityGate`: đánh giá độ nét Laplacian (`blur_score`), độ sắc nét nhãn Sobel (`label_sharpness`), độ lồi (`solidity`), số thành phần liên thông (`n_components`), mép cắt (`clipping_px`).

Việc tách riêng script audit cho phép chạy kiểm tra 1.572 ảnh gốc và đối soát với 1.351 SKU chỉ mất khoảng 15-30 giây (khi dùng barcode cache) thay vì hàng giờ chạy mô hình AI tách nền.

## Goals / Non-Goals

**Goals:**
- Tạo script độc lập `scripts/audit_and_export_reshoot_list.py` có thể chạy dòng lệnh linh hoạt (`--partition`, `--min-blur`, `--output-excel`).
- Đánh giá chất lượng toàn bộ 5 kho ảnh nguồn: `G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`.
- Tự động phân loại lý do chụp lại chi tiết bằng tiếng Việt: Thiếu ảnh, Không có mã vạch, Ảnh mờ out-of-focus, Bị cắt mép/che khuất, Lỗi kẹt quarantine.
- Xuất file Excel `Rabuta_Customer_Reshoot_Request.xlsx` giữ nguyên 100% cấu trúc 31 cột gốc của file master, chèn các hàng bị lỗi, và bổ sung 4 cột ghi chú hướng dẫn khách hàng chụp lại.

**Non-Goals:**
- Không thực hiện alpha matting (xóa phông nền AI) trong script này.
- Không sửa đổi hay ghi đè lên file gốc `Rabuta_master_SKU_categories.xlsx`.
- Không thay đổi logic chạy chính của `run_zohanubis_pipeline.py`.

## Decisions

### 1. Kiến trúc Script độc lập (`scripts/audit_and_export_reshoot_list.py`)
- *Quyết định*: Tận dụng các class lõi từ `src/product_mapper/zohanubis/` (`ImageSanitizer`, `BarcodeReconciler`, `QualityGate`) và cache quét mã vạch đã có trong `output/shopify-zohanubis-image/reports/barcode_scan_cache.json`.
- *Phương án thay thế đã cân nhắc*: Viết lại hoàn toàn độc lập từ đầu. *Lý do loại bỏ*: Dễ gây sai lệch logic đối soát mã barcode và thứ tự sequence giữa pipeline và script audit.

### 2. Cấu trúc bảng tính Excel xuất ra cho khách hàng
- *Quyết định*:
  - Giữ nguyên toàn bộ 31 cột gốc của file master (từ Cột A: Barcode đến Cột AE: Category Level 2).
  - Bổ sung 4 cột mới ở ngay sau các thông tin định danh chính hoặc ở cuối bảng:
    1. `Mức độ ưu tiên chụp lại` (`BẮT BUỘC` / `KHUYẾN NGHỊ`)
    2. `Lý do chụp lại chi tiết` (Tiếng Việt)
    3. `Góc chụp yêu cầu` (Mặt trước trực diện / Mặt sau có mã vạch / Cả 2 mặt)
    4. `Hướng dẫn chụp chuẩn` (Khoảng cách, ánh sáng, tránh che khuất)
  - Tô màu highlight trực quan (Hồng nhạt `FEE2E2` cho Bắt buộc, Vàng nhạt `FEF3C7` cho Khuyến nghị).
  - Bảo tồn ảnh thumbnail mẫu từ Cột W của file gốc để khách hàng dễ dàng đối chiếu mặt hàng khi đi tìm trong kho.

### 3. Ngưỡng phân loại chất lượng ảnh gốc (Quality Thresholds)
- *Critical (Bắt buộc chụp lại)*:
  - SKU hoàn toàn không có ảnh nào trong kho (`MISSING_RAW`).
  - SKU có ảnh mặt trước nhưng không tìm thấy ảnh mã vạch ở mặt sau/cạnh bên (`NO_BARCODE_FOUND`).
  - Ảnh mờ nặng: `blur_score < 25.0` hoặc chữ trên nhãn không đọc được `label_sharpness < 12.0`.
  - Ảnh bị cắt mất góc sản phẩm hoặc có vật che khuất lớn (`clipping_px <= 2` hoặc phát hiện mép đứt viền).
- *Warning (Khuyến nghị chụp lại nếu có mẫu)*:
  - Ảnh hơi soft (`25.0 <= blur_score < 40.0`).
  - Sản phẩm bao bì bóng bị lóa đèn flash mất 1 phần chữ nhỏ.

## Risks / Trade-offs

- **[Risk] File Excel có thể lớn nếu nhúng lại toàn bộ ảnh demo**:
  → *Mitigation*: Chỉ nhúng thumbnail demo đối với các dòng cần chụp lại (dự kiến khoảng 150-250 dòng), giảm đáng kể dung lượng file và tăng tốc độ ghi file.
- **[Risk] Các file iOS HEIC trong G4 và Nyt yêu cầu thư viện `pillow_heif`**:
  → *Mitigation*: Tái sử dụng `ImageSanitizer` đã đăng ký sẵn `pillow_heif.register_heif_opener()`, đảm bảo đọc mượt mà 100% file `.heic`.
