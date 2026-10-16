# Spec Delta

## REMOVED Requirements

### Requirement: Phục Hồi Nguồn Sạch Từ Master 1659 Cho Nhóm Lỗi Thuật Toán
**Reason**: Kho Master 1659 và ảnh webshop hiện tại không phải nguồn gốc. Dùng chúng để thay ảnh đã cắt làm mất chi tiết và không đối chiếu được barcode với năm thư mục ảnh gốc.
**Migration**: Thay ảnh lỗi bằng ảnh dựng từ thư mục gốc theo `catalog-image-quality/conservative-front-batch`. Dòng không có ảnh gốc chuyển sang workbook khách chụp lại.

## MODIFIED Requirements

### Requirement: 6 Tiêu Chí Đối Chiếu Đánh Giá Chất Lượng Thị Giác
Hệ thống SHALL chấm ảnh webshop mặt trước mới theo 6 tiêu chí sau, trên ảnh xuất ra chứ không trên thư mục webshop cũ:
1. Tính đơn lẻ: Chỉ chứa đúng 1 mặt trước của một đơn vị bán.
2. Tính toàn vẹn: Giữ vỏ, nắp, đáy, mép, nhãn và phần màng hoặc khay thuộc đơn vị đó.
3. Không cắt lẹm: Biên bao bì không bị cắt cụt bởi khung hay bởi mask.
4. Chiều đứng tự nhiên: Đúng hướng đọc nhãn.
5. Độ sắc nét: Nhãn đọc được từ điểm ảnh gốc, không do phóng to.
6. Đúng mặt trước: Khác mặt sau đang giữ ở cột mặt sau. Mã vạch in trên bao bì mặt trước được chọn được phép còn. Một mặt barcode tách riêng không được dùng làm mặt trước khi có mặt khác khớp ảnh cột W.

Ảnh không đạt một tiêu chí MUST NOT được nhúng vào cột webshop. Hệ thống MUST NOT xếp ảnh webshop cũ vào nhóm đạt chỉ vì độ nét hoặc vì đã tồn tại file.

#### Scenario: Phát hiện ảnh đạt chuẩn
- **WHEN** ảnh webshop mới thể hiện đúng 1 mặt trước, toàn vẹn bao bì, không cắt lẹm, đúng chiều, rõ từ nguồn gốc và khác mặt sau
- **THEN** hệ thống cho phép nhúng ảnh đó vào cột webshop và không công nhận file webshop cũ là đạt chỉ vì file đã tồn tại

#### Scenario: Phát hiện ảnh lỗi do thuật toán cũ
- **WHEN** ảnh webshop hiện có bị dính 2 đơn vị bán, bị cắt cụt, hoặc bị xóa mất vỏ bao bì
- **THEN** hệ thống không dùng ảnh đó làm nguồn thay thế và không gắn nhãn đạt cho dòng đó

### Requirement: Bảo Vệ & Nâng Nét Độc Lập Cho Ảnh Người Dùng Tự Lưu
Hệ thống SHALL NOT coi ảnh mờ, ảnh có mask hỏng, hoặc ảnh đang nằm trong thư mục webshop là ảnh người dùng đã chọn. Hệ thống MUST NOT mài nét tại chỗ để giữ những ảnh đó. Chỉ một bản ghi chọn tường minh, gắn với đúng dòng catalog, mới được giữ nguyên; mọi dòng khác có ảnh gốc đủ điều kiện MUST được dựng lại từ ảnh gốc.

#### Scenario: Xử lý ảnh người dùng tự lưu bị mờ
- **WHEN** file webshop mặt trước hiện có bị mờ hoặc bị cắt và không có bản ghi chọn tường minh cho đúng dòng
- **THEN** hệ thống không tăng nét file đó, không giữ nguyên góc cắt cũ, và dựng lại từ ảnh gốc khi nguồn đủ điều kiện

### Requirement: Đồng Bộ Excel Đối Chiếu Không Xung Đột XML
Hệ thống SHALL ghi bản sao workbook với ba cột nhìn: ảnh mặt trước gốc, ảnh webshop mặt trước mới, ảnh mặt sau hiện có. Cột gốc và cột mặt sau MUST giữ byte ảnh đã nhúng. Cột webshop chỉ nhận ảnh đã đạt. Thuộc tính Drawing `cNvPr id` MUST tuần tự và duy nhất. Dòng thiếu nguồn MUST nằm trong workbook chụp lại và MUST NOT nhận ảnh webshop mới.

#### Scenario: Mở file Excel đối chiếu trong Microsoft Excel
- **WHEN** người dùng mở bản sao workbook đối chiếu sau khi nhúng
- **THEN** Microsoft Excel mở trực tiếp trang tính, không xuất hiện hộp thoại cảnh báo sửa nội dung, cột webshop khớp ảnh đã đạt, và hai cột còn lại không đổi
