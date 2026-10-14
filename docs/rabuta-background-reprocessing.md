# Rabuta: xử lý lại background có bằng chứng nguồn

Ngày triển khai: 14/10/2026. Pipeline tạo **ảnh ứng viên chờ QA**, không chứng nhận toàn catalog.

## Thay đổi

- `package_packshot.py`: mask đường bao toàn bộ bao bì được kiểm tra độc lập; giữ RGB gốc bên trong, chỉ feather 1.5 pixel quanh biên. Không xóa màu carton, không chọn contour logo, không thêm chữ/nhãn.
- Candidate model được đối chiếu coverage/spill với boundary tham chiếu; bộ đo không tự cấp PASS. Phiên bản này dùng polygon kiểm tra bằng mắt, chưa benchmark model tự động mới.
- Chặn mask thủng/nhiều vùng rời/đụng biên nguồn; chặn cạnh dài sản phẩm dưới 600 px hoặc cạnh ngắn dưới 30 px. Đây là ngưỡng chống dùng preview, **không chứng nhận** độ sắc nét. Có ghi `source_resolution_warning` khi upscale.
- Canvas 2400×2400 #FFFFFF, scale đồng đều; cạnh dài chiếm 88% cho hình cao, 89% ngang, 84% gần vuông, 83% không đều. Có thể chỉ định `shape` sau review. Đây là chính sách Rabuta, không phải tiêu chuẩn Shopify.
- Runner gắn barcode + Record ID + dòng Excel với workbook, hash nguồn, kích thước sau EXIF, đúng mặt và một đơn vị bán. Kiểm tra collision trong **toàn workbook**, kể cả khi chạy một dòng.
- Mask lưu theo nguồn sau EXIF. Bản sao được xoay để dựng ảnh; metadata layout ghi rõ hệ tọa độ/phép xoay.
- Các helper `make_smart_packshot`, `render_studio_packshot`, `isolate_product`, `isolate_customer_packshot`, `format_to_canvas` yêu cầu `package_mask`. CLI healing thuộc nhánh này, kể cả `heal_61_fallback_items.py`, bị dừng trước khi ghi. Chuyển sang runner mới.
- QA preview không còn PASS; barcode không mặc nhiên là lỗi. QA delivery kiểm tra mọi ô dịch cột và hash W theo anchor; không kết luận PASS từ viền trắng.

## Chạy

Môi trường đã kiểm tra: `C:\Python313\python.exe`, Pillow 12.3.0, OpenCV 5.0.0.93, pillow-heif 1.8.0, NumPy hiện có. Không cài model/dependency mới. Pillow trên máy cao hơn giới hạn `<12` trong pyproject cũ; chưa kiểm chứng môi trường cài sạch theo manifest đó.

```powershell
C:\Python313\python.exe scripts/reprocess_rabuta_verified.py --records C:\Users\HP\Downloads\Rabuta_QA_Reprocess_Queue.jsonl --annotations output/catalog_pairs/reprocess-v4/pilot_annotations.jsonl --output-dir output/catalog_pairs/reprocess-v4/new-review-run
```

Output phải chưa tồn tại. Bỏ `--annotations` để chỉ lập danh sách nguồn ứng viên. Exit 2 báo còn blocker/review; exit 0 chỉ nghĩa tất cả dòng đã tạo ứng viên, **không phải QA PASS**. QA cấu trúc cũng trả 2 vì không đủ bằng chứng nghiệm thu hình ảnh.

Annotation JSONL cần: `excel_row`, `barcode` string, `record_id`, `source_path`, `source_sha256`, `source_size` sau EXIF, `identity_verified=true`, `single_product_verified=true`, `complete_package=true`, `face="front"`, `evidence`, `polygon` theo pixel nguồn. Tùy chọn `rotation_ccw` 0/90/180/270, `shape`. Không vẽ polygon quanh logo hoặc box chứa hai vật thể. Ca film rỗng cần matting đặt `film_matting_required=true` để chặn và review riêng.

Nếu gọi `run_reprocessing` trực tiếp từ Python, truyền `catalog_records` chứa toàn bộ identity catalog để phát hiện collision toàn cục; CLI đã làm bằng workbook.

## Kết quả thực tế

Run chính: `output/catalog_pairs/reprocess-v4/pilot-reviewed-code-2026-10-14/`.

| Trạng thái | Dòng |
|---|---:|
| REPROCESSED_NEEDS_REVIEW | 4 |
| NEEDS_MANUAL_REVIEW, có file nguồn ứng viên | 230 |
| BLOCKED_NEEDS_SOURCE, chưa thấy nguồn native ở vị trí đã tra | 139 |
| BLOCKED_IDENTITY_CONFLICT | 2 |
| Tổng queue audit 2 | 375 |

Ảnh mới: dòng 266 (Lobo), 304 (Cock mung beans), 669 (YumYum), 1089 (bibigo pork). Boundary đánh dấu trên view 1000 px rồi chuyển về native; cần soi lại mép ở native resolution. Phản xạ/film giữ theo nguồn, chưa giải quyết matting film rỗng. Có source overlay, mask native, PNG 2400 và hash mỗi record. Không dùng cutout cũ để phục hồi.

Ca đã xem chưa tạo output: 110 bị cắt mép; 134 Udon có film sát biên; 140 Soba sát/cắt biên trên; 818 thiếu biên bên; 1086 front bên phải sát biên; 597 chưa thấy nguồn native trong mapping; 1296 cần xác minh đơn vị bán/ảnh carton; 1340 nguồn đã thấy chỉ là mặt sau. Cần ảnh khác hoặc xác minh/chụp lại. Không coi mọi source candidate là mặt trước hợp lệ.

Chưa xử lý xong 375 dòng, chưa kiểm tra native toàn catalog, chưa bổ sung đủ mặt sau và chưa thay X/Y trong workbook. 4 mẫu không thay thế benchmark 20–30 mẫu gồm chai/lon/bao bì trong và ảnh vốn đúng; cần thêm nguồn/mask kiểm chứng để mở rộng.

## Kiểm chứng

- 74 pytest tests passed; compile 9 file thay đổi thành công.
- Review độc lập phát hiện và đã sửa: collision khi chạy subset, fallback padding ghi front-v3, mask xoay lệch provenance; có kiểm thử RED→GREEN riêng.
- 0 ô dữ liệu lệch; 1349 ảnh W byte-for-byte giữ nguyên so với nguồn. Workbook delivery SHA-256 vẫn `c8a58d9a294799cd4bb12c13bf32109ef8681d096875dd84ddca23d947c1eb11`.
- QA cấu trúc báo BLOCKED: 181 dòng thiếu X/Y và hai Record ID dùng chung barcode `8938500075070`. Không có catalog PASS.

Thử u2net cached trên crop nguồn cùng các polygon tham chiếu (neutral padding 60, alpha >20), không dùng model proposal làm ảnh giao:

| Dòng | Coverage bao bì tham chiếu | Spill ngoài bao bì | Candidate được giữ? |
|---|---:|---:|---|
| 266 | 67.25% | 0.74% | Không |
| 304, nguồn HEIC khác ảnh chẩn đoán ban đầu | 81.69% | 0.77% | Không |
| 669 | 99.23% | 6.75% | Không |
| 1089 | 59.25% | 0.57% | Không |

Ngưỡng chẩn đoán hiện tại coverage ≥98.5%, spill ≤2% chỉ dùng để loại ứng viên trong thí nghiệm; cần hiệu chỉnh trên benchmark rộng hơn, không chứng minh QA PASS. File `u2net_vs_verified_boundary.json` lưu nguồn và hash mask tham chiếu. Kết quả cho thấy có ca thiếu thân và có ca giữ dư nền dù đã crop đúng sản phẩm.
