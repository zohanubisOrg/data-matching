# Proposal

## Why

Ảnh webshop mặt trước đang nhúng ở cột X lấy từ `front-v3` bị cắt lẹm và mất chi tiết, trong khi đường sửa bằng polygon thủ công chỉ xuất được một phần nhỏ catalog và không kịp hạn 23:00 ngày 15/10/2026. Cần một lô xử lý từ ảnh gốc, giữ nguyên bao bì, nền trắng, và chỉ nhúng những ảnh đã qua cổng kiểm tra.

## What Changes

- Dựng mặt trước webshop từ năm thư mục ảnh gốc đã lọc (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`), đối chiếu barcode với workbook khách, không dùng `front-v3`, thumbnail, hay ảnh đã cắt làm nguồn.
- Cấm cắt xuyên bao bì: không xẻ nửa khung theo khoảng cách, không đẩy đường cắt vào nhãn, không bào mask vào trong. Mask chỉ được nới ra ngoài; nếu biên không chắc thì giữ nguyên pixel sản phẩm và chuyển dòng sang chờ nguồn.
- Xuất một lần lên canvas 2400×2400 nền trắng, chỉ thu nhỏ, không phóng to RGB, không mài JPEG nhiều vòng.
- Chạy theo lô khoảng 150 dòng, có sổ cái nối lại được. Mỗi dòng có một trạng thái: ảnh đạt, thiếu ảnh để khách chụp lại, hoặc bị chặn vì trùng barcode / sai mặt / biên không đủ.
- Chọn mặt trước bằng kết quả khớp duy nhất với ảnh cột W và so sánh cột Y khi có; barcode chỉ định vị chủ thể. Không suy ra mặt từ trái/phải/xa/gần hay thứ tự file.
- Tách trạng thái `ACCEPTED` (đã qua Q1–Q6 với bằng chứng và hash hiện hành) khỏi phát hành lô. Chỉ nhúng sau báo cáo theo nhóm và duyệt mắt gắn với đúng tập ảnh.
- Các ca lỗi phổ biến là cổng chất lượng: chai nằm ngang, ba vỏ xếp hàng, túi thực phẩm một mặt, rau củ một bao, thùng carton, và ảnh đã tách sẵn mặt trước với mặt sau. Lấy sai mặt hoặc mất bao bì thì không được ghi là đạt.
- Thêm Gemini Pro làm semantic quality gate trên candidate đã qua kiểm tra file, canvas, hình học và định danh của Python. Gemini so ảnh nguồn, output và W/Y để nhận diện sai mặt, mất chi tiết, nhiều đơn vị và nền ngoài bao; kết quả có cấu trúc `PASS`, `REVIEW`, `FAIL` kèm bằng chứng.
- Mỗi barcode được tối đa ba lần render từ ảnh gốc bất biến. Candidate và mọi lần thử nằm trong run riêng; chỉ ảnh qua cả hai tầng QA mới được đưa vào `front-v5`.
- Pilot shadow giới hạn 200 lượt gọi Gemini, lưu model/prompt/version và kết quả. Thay model, prompt hoặc thuật toán phải chạy regression và holdout có nhãn; không tự sửa code hoặc hạ ngưỡng.
- **BREAKING:** Đường sản xuất không còn ghi đè `front-v3` bằng vòng sharpen hay bằng kho Master 1659. Cột Y (`back-v2`) và cột W (ảnh gốc khách) giữ nguyên. Cột X chỉ nhận ảnh mới đã qua cổng, ghi vào bản workbook sao chép đã kiểm tra.

## Capabilities

### New Capabilities

- `catalog-image-quality/conservative-front-batch`: Đối soát barcode, chọn mặt trước từ ảnh gốc, cắt nền theo mask nới rộng, xuất lô và tệp khách cần chụp lại.
- `catalog-image-quality/front-gemini-quality-gate`: Đánh giá semantic có bằng chứng, vòng sửa giới hạn, cache theo nội dung và promotion an toàn qua các runner.

### Modified Capabilities

- `catalog-image-quality/iterative-refinement-loop`: Bỏ vòng lặp mài nét 10 lần trên JPEG đã xuất. Mỗi ảnh chỉ được dựng một lần từ nguồn gốc bất biến.
- `catalog-image-quality/conservative-front-batch`: Mọi runner dùng chung candidate → Python gate → Gemini gate → promotion; thiếu bằng chứng hoặc kết quả Gemini không hợp lệ đều không được đạt.
- `catalog-quality/audit-and-remediation`: Giữ 6 tiêu chí nhìn. Nguồn thay thế là ảnh gốc đã đối barcode, không phải Master 1659. Cột X lấy từ thư mục xuất mới. Dòng không có ảnh gốc đi vào workbook chụp lại, không bị gán là đạt.

## Impact

- Renderer dùng chung `src/product_mapper/vision/package_packshot.py` phải từ chối mask bào vào trong và từ chối phóng to.
- `barcode_side_splitter.separate_joined_packages` và đường cắt theo preview 720–900 px không được dùng làm cắt sản xuất.
- Workbook thẩm quyền: `source-import/new_source_from_customer/14-10-new-requirment-final/Rabuta_master_SKU_categories_ingredients_final.xlsx` (cột A barcode, E Record ID, W ảnh gốc, X webshop mặt trước, Y mặt sau). File này không bị ghi đè tại chỗ.
- Ảnh đầu ra mới nằm ngoài `front-v3`. `back-v2` không đổi. Không upload Shopify.
