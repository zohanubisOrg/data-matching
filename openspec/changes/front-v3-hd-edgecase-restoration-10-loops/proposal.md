# Proposal: Dựng lại ảnh webshop toàn catalog từ ảnh gốc

## Why

Ảnh front-v3 bị ảnh hưởng trên toàn catalog bởi chọn nguồn thumbnail, nhầm mặt, gộp sản phẩm liền kề, xóa mất bao bì và sharpen nhiều lần. Người dùng đã đồng ý dựng lại từ 5 thư mục ảnh gốc; 5 mã critical là ví dụ hồi quy, không phải danh sách giới hạn phạm vi xử lý.

## What Changes

- Đối soát tất cả dòng/SKU của workbook có thẩm quyền, gồm P3 và nhóm từng tự chấm đạt. Không hardcode số dòng hoặc dùng số file làm số sản phẩm.
- Ưu tiên ảnh gốc trong source-import/G1_original, G2_original, G3_Original, G4-original và Nyt25.09.26; xác minh mapping, mặt trước và chất lượng vùng sản phẩm thực.
- Giữ đúng một đơn vị bán hoàn chỉnh: chai gồm nắp đến đáy; khay gồm khay, màng và thực phẩm; túi gồm thân, mép hàn, nhãn và nội dung. Tách từng instance dù chạm nhau hoặc có hơn hai góc chụp.
- Canvas 2400 x 2400, nền trắng, giữ tỷ lệ; cấm upscale RGB để đạt bố cục. Thiếu biên, bị che khuất, thiếu nét hoặc chưa rõ mặt phải có trạng thái nguồn/review riêng.
- Thay 10 vòng sharpen bằng ứng viên dựng từ nguồn bất biến, QA từng ảnh và xuất một lần. Giữ tên change cũ để không đứt liên kết; tên 10-loops không còn quy định thuật toán.
- Pilot 30-50 SKU bao phủ vật liệu, hình học và lỗi trước khi chạy toàn catalog. Pilot không thu hẹp phạm vi cuối cùng.
- Chỉ publish ảnh đạt QA vào front-v3 với snapshot/hash/rollback. Bảo vệ ảnh người dùng theo provenance. Xuất workbook đối chiếu riêng, giữ nguyên W/Y và dữ liệu sản phẩm.

## Capabilities

### New Capabilities
- `catalog-image-quality/hd-studio-edgecase-remediation`: Dựng mặt trước từ nguồn gốc trên toàn catalog, giữ nguyên đơn vị bán, tách các instance chạm nhau, kiểm tra native detail và nghiệm thu có bằng chứng.

### Modified Capabilities
- `catalog-image-quality/iterative-refinement-loop`: Thay sharpen tích lũy bằng ứng viên nguồn gốc và QA độc lập.
- `catalog-quality/audit-and-remediation`: Bỏ mặc định Master sạch/phân nhóm từ độ mờ; đối soát toàn catalog, bảo vệ ảnh người dùng theo provenance và giữ nguyên W/Y.

## Impact

Đích cuối vẫn là output/catalog_pairs/tagged/front-v3. Renderer, remediation và publisher phải dùng chung cổng kiểm tra, không ghi live qua đường tắt. Không sửa originals, customer_ground_truth, back-v2 hoặc tự upload Shopify. Mô hình/dependency cụ thể được chọn bằng benchmark trong môi trường thực. Spec này chưa chứng nhận thuật toán đã triển khai hoặc ảnh đã sửa.
