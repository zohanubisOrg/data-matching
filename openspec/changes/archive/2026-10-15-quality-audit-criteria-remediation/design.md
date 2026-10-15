# Design: Hệ Thống Đối Chiếu 3 Cột, Phân Loại 3 Nhóm & Phục Hồi front-v3

## Context
Xem `proposal.md` và `specs/catalog-quality/audit-and-remediation/spec.md`.
Thực trạng dữ liệu:
- File Excel `Rabuta_master_SKU_categories_ingredients_final_audit_v3.xlsx` đã nhúng đúng 3 cột: Cột 23 (Ground Truth khách), Cột 24 (`front-v3`), Cột 25 (`back-v2`).
- Kho `Master_1659_Clean_Front_Images` chứa 1.659 ảnh đơn độ phân giải cao 2000-4000px sạch sẽ.
- Kho `front-v3` chứa cả các ảnh người dùng tự tìm kiếm và tải về.

## Goals / Non-Goals

**Goals:**
- Tự động rà soát định lượng và đối chiếu thị giác từng dòng giữa `front-v3` và ảnh gốc khách hàng.
- Phân nhóm chính xác:
  - Nhóm 1: Đạt chuẩn -> Bảo toàn 100%.
  - Nhóm 2: Ảnh người dùng tự lưu cắt chuẩn bị mờ -> Tăng nét cục bộ bằng Unsharp Masking / Contrast, KHÔNG đè.
  - Nhóm 3: Lỗi thuật toán cũ (ảnh đôi, cắt lẹm, mất vỏ) -> Lấy nguồn sạch từ Master 1659 xử lý canvas 2400x2400 và ghi đè có kiểm soát vào `front-v3`.
- Tự động re-index mã `cNvPr id` trong `xl/drawings/drawing1.xml` của file Excel để mở không bị cảnh báo lỗi.

**Non-Goals:**
- Không tạo thêm các thư mục mới lạ như `front-v4`, `front-v5` làm rối loạn quy trình của người dùng.
- Không tự ý đè ảnh khác lên các sản phẩm người dùng đã tự tay tra cứu/lưu về.

## Decisions

### Quyết định 1: Phân tách Nhóm 2 (Ảnh người dùng tự lưu bị mờ) dựa trên Bố Cục Cắt
- **Lý do**: Khi đối chiếu tỷ lệ khung hình với ảnh khách ($|AR_{v3} - AR_{khach}| \le 0.25$) và không bị cắt phẳng biên (flatness < 0.35) nhưng Laplacian < 300, đây chính là ảnh đơn người dùng đã cắt chuẩn nhưng nguồn mạng bị mờ.
- **Xử lý**: Áp dụng bộ lọc Unsharp Masking ($r=2.0, \text{amount}=1.5$) giữ nguyên góc cắt của người dùng.
- **Giải pháp thay thế bị loại bỏ**: Không đè ảnh từ Master 1659 vào nhóm này vì sẽ vi phạm nguyên tắc bảo toàn công sức của người dùng.

### Quyết định 2: Chỉ lấy Master 1659 cho Nhóm 3 (Lỗi thuật toán rõ rệt)
- **Lý do**: Khi phát hiện lỗi dính ảnh đôi ($AR_{v3} > 1.55 \times AR_{khach}$), mất vỏ ($AR_{v3}$ teo nhỏ) hoặc cắt lẹm (flatness > 0.50), tra cứu chính xác barcode sang `Master_1659_Clean_Front_Images` để đóng gói canvas 2400x2400 nền trắng `#FFFFFF`.

### Quyết định 3: Khắc phục lỗi Drawing ID Excel trực tiếp trong tệp nén ZIP
- **Lý do**: Openpyxl tự động gán trùng ID khi thêm ảnh hàng loạt. Ta giải nén XML nội bộ, đánh số tuần tự `id="1"` đến `id="N"` cho `<xdr:cNvPr>` rồi nén lại. Excel sẽ mở mượt mà 100%.

## Risks / Trade-offs

- [Risk] Mã barcode trong `Master_1659` có tiền tố STT dạng `0001_8850157516457_...` → [Mitigation] Sử dụng regex tra cứu linh hoạt `*_<barcode>_*.jpg` và xử lý số 0 ở đầu.
- [Risk] File Excel bị khóa (PermissionError) nếu người dùng đang mở → [Mitigation] Lưu sang bản snapshot mới hoặc copy đè an toàn khi file không bị khóa.
