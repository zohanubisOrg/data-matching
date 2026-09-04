# Tiêu Chí Nghiệm Thu Cuối Cùng & Definition of Done (DoD)
## Dự Án: Data Matching Barcode & Sản Phẩm (Shopify POS Reconciliation)

Tài liệu này xác lập tiêu chuẩn nghiệm thu duy nhất và chính thức cho sản phẩm bàn giao cuối cùng. 
**Nghiệm thu được xác định dựa trên CHẤT LƯỢNG OUTPUT THỰC TẾ, không dựa trên phương thức cài đặt hay cấu trúc mã nguồn.**

---

## I. Definition of Done (DoD)

> **Công việc Data Matching được xem là hoàn thành và đạt nghiệm thu khi toàn bộ dữ liệu POS, dữ liệu nhà cung cấp và kho hình ảnh được xử lý thành một dataset đầu ra có khả năng truy vết đầy đủ; mỗi sản phẩm đã được xác nhận phải được gắn đúng Barcode/SKU, đúng tên và đúng hình ảnh tương ứng. Các hình ảnh đã match được chuẩn hóa và lưu vào kho output theo Barcode hoặc identifier thống nhất để có thể sử dụng trực tiếp cho bước import lên website. Toàn bộ record không đủ thông tin để xác định chính xác phải được tách riêng dưới trạng thái Review/Unmatched, không được tự động gán sai. Không được làm mất hoặc thay đổi Barcode/SKU gốc, không được merge nhầm các variant hoặc sản phẩm có tên tương tự. Sau quá trình xử lý phải có mapping file và báo cáo tổng hợp để đối chiếu 100% dữ liệu đầu vào với kết quả đầu ra.**

**Quy tắc một câu:**
> **DONE = Mọi ảnh và mọi sản phẩm đều có trạng thái rõ ràng (100% Accounted For); những record đã MATCHED thì đúng 100%, những record chưa chắc chắn được tách riêng sang REVIEW/UNMATCHED, và folder ảnh cuối chuẩn hóa theo Barcode (`<barcode>.jpg`) có thể dùng thẳng để đưa lên website.**

---

## II. Cấu Trúc Bàn Giao Đầu Ra Bắt Buộc

Sau khi chạy pipeline với bộ dữ liệu thật, cấu trúc thư mục `/output` bắt buộc:

```text
/output
├── matched-images/
│   ├── <barcode>.jpg
│   ├── <barcode>_2.jpg  (nếu sản phẩm có nhiều ảnh)
│   └── ...
│
├── unmatched-images/
│   ├── <original_filename>.jpg
│   └── ...
│
├── result.xlsx / result.csv
├── reconciliation_report.txt
├── mapping_result.xlsx
├── customer_review.xlsx
└── review_report.html
```

### Cấu Trúc Bảng `result.xlsx` / `result.csv`:
Bao gồm chính xác 7 cột bắt buộc:
| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| **Barcode** | Mã Barcode thực tế từ POS (giữ nguyên gốc) | `5017689000332` |
| **SKU** | Mã SKU thực tế từ POS (giữ nguyên gốc) | `B-001` |
| **Original Name** | Tên gốc của sản phẩm trên POS | `GT APP 500ML` |
| **Final Name** | Tên chuẩn hóa, usable, không bịa thông tin | `Green Tea Apple 500ml` |
| **Original Image** | Tên file ảnh gốc từ nhà cung cấp | `heuschen_10050_tea.jpg` |
| **Final Image** | Tên file ảnh chuẩn hóa theo Barcode | `5017689000332.jpg` |
| **Status** | Trạng thái phân loại | `MATCHED`, `REVIEW`, `UNMATCHED` |

---

## III. Bảng 15 Tiêu Chí Pass / Fail Cuối Cùng

| # | Tiêu chí | Điều kiện PASS |
|---|---|---|
| **1** | **Đọc đầy đủ input** | 100% file ảnh và dòng dữ liệu được nạp đầy đủ, nếu có lỗi file hỏng phải báo cáo rõ. |
| **2** | **Accounted records** | 100% record đầu vào đều có trạng thái định danh (`MATCHED`, `REVIEW`, `UNMATCHED`, `INVALID`). |
| **3** | **Correct matching** | 100% record trong tập `MATCHED` / `APPROVED` phải đúng cùng một sản phẩm thực tế. Nghi ngờ phải tách riêng, không được match đại. |
| **4** | **Barcode integrity** | 100% Barcode giữ nguyên định dạng chuỗi từ POS, không làm rơi số 0 ở đầu, không AI tự sinh barcode. |
| **5** | **SKU integrity** | 100% SKU được bảo toàn nguyên vẹn, không chỉnh sửa. |
| **6** | **Image correctness** | Ảnh khớp chính xác với sản phẩm về variant, chủng loại, không lệch sản phẩm. |
| **7** | **Filename chuẩn hóa** | Ảnh output trong `matched-images/` được đặt tên chuẩn hóa theo `<barcode>.jpg` (đánh số `_2`, `_3` nếu nhiều ảnh). |
| **8** | **Name normalization** | Tên sản phẩm cuối sạch sẽ, đọc được, không bịa đặt dung tích hay hương vị không có căn cứ. |
| **9** | **Ambiguous data** | Mọi trường hợp mơ hồ, điểm số ngang nhau hoặc thiếu dữ liệu bắt buộc chuyển sang `REVIEW` hoặc `UNMATCHED`. |
| **10** | **Duplicate / Variant** | Không merge nhầm các sản phẩm/SKU khác nhau kể cả khi trùng tên; bảo toàn identity của từng SKU. |
| **11** | **Output folder** | Thư mục đầu ra sẵn sàng cho bước upload và import trực tiếp lên website / Shopify. |
| **12** | **Mapping file** | File mapping (`result.xlsx` / `result.csv`) có khả năng truy vết hoàn chỉnh từ input gốc đến output cuối. |
| **13** | **Summary Report** | Báo cáo đối chiếu số liệu (Reconciliation Report) cân đối chính xác: `Matched + Review + Unmatched + Error = Total Input`. |
| **14** | **Data loss** | Không mất bất kỳ ảnh hay record nào mà không có lý do được ghi nhận trong báo cáo. |
| **15** | **Wrong silent match** | **0 trường hợp match sai âm thầm.** |

---

## IV. Báo Cáo Đối Chiếu Số Lượng (Reconciliation Formula)

```text
Images Accounting:
  Total Input Images
  = Matched Images (trong matched-images/)
  + Review Images (trong unmatched-images/)
  + Unmatched Images (trong unmatched-images/)
  + Invalid Files (nếu có)

POS Products Accounting:
  Total POS Products
  = Matched POS Products (có ảnh tương ứng)
  + POS Products chưa có ảnh (cần nhập thêm hoặc chụp mới)
```
