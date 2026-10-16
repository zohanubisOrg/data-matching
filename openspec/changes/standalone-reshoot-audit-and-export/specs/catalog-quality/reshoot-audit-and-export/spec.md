# Spec Delta: Standalone Reshoot Audit & Customer Sheet Export

## Purpose
Cung cấp công cụ kiểm thử chất lượng toàn diện độc lập cho toàn bộ kho ảnh gốc của danh mục sản phẩm và xuất file Excel yêu cầu chụp lại chuẩn hóa cho khách hàng đối chiếu.

## ADDED Requirements

### Requirement: Đánh giá toàn bộ 5 kho ảnh gốc và đối soát với Master Catalog
Hệ thống SHALL quét toàn bộ ảnh có trong 5 thư mục nguồn (`G1_original`, `G2_original`, `G3_Original`, `G4-original`, `Nyt25.09.26`) bao gồm các định dạng `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic` và đối soát với toàn bộ 1.351 dòng sản phẩm trong catalog `Rabuta_master_SKU_categories.xlsx`.

#### Scenario: Quét đầy đủ các định dạng ảnh bao gồm HEIC
- **WHEN** công cụ audit chạy trên 5 thư mục nguồn
- **THEN** toàn bộ ảnh hợp lệ (kể cả ảnh `.heic` trong `G4-original` và `Nyt25.09.26`) đều được nạp và đối chiếu với mã barcode hoặc thứ tự sequence tương ứng trong danh mục

#### Scenario: Đối soát với toàn bộ 1.351 sản phẩm danh mục
- **WHEN** đối soát danh mục master
- **THEN** mỗi sản phẩm trong 1.351 dòng đều được phân loại trạng thái: có ảnh đạt chuẩn, có ảnh nhưng không đạt chuẩn, hoặc thiếu ảnh hoàn toàn

### Requirement: Phân loại nguyên nhân yêu cầu chụp lại theo đa tiêu chí
Hệ thống SHALL đánh giá chất lượng của từng sản phẩm dựa trên 5 tiêu chuẩn chất lượng hình ảnh thương mại điện tử và gán nhãn nguyên nhân chụp lại cụ thể cho các sản phẩm không đạt chuẩn.

#### Scenario: Sản phẩm thiếu ảnh hoàn toàn (MISSING_RAW)
- **WHEN** một SKU trong master catalog không có bất kỳ ảnh nào khớp mã vạch hoặc vị trí chụp trong 5 folder
- **THEN** hệ thống gán trạng thái `MISSING_RAW`, xếp mức độ ưu tiên `BẮT BUỘC`, và yêu cầu khách hàng cung cấp cả ảnh mặt trước và mặt sau có mã vạch

#### Scenario: Sản phẩm có ảnh nhưng không đọc được mã vạch (NO_BARCODE_FOUND)
- **WHEN** một SKU chỉ có ảnh mặt trước bao bì nhưng không có ảnh nào thể hiện rõ cụm mã vạch hợp lệ
- **THEN** hệ thống gán trạng thái `NO_BARCODE_FOUND`, yêu cầu chụp bổ sung ảnh mặt sau/đáy hộp chứa mã vạch và bảng dinh dưỡng

#### Scenario: Ảnh bị mờ hoặc mất nét chi tiết (POOR_FOCUS_OR_BLUR)
- **WHEN** ảnh sản phẩm có điểm độ nét Laplacian `blur_score < 35.0` hoặc độ sắc nét nhãn `label_sharpness < 15.0`
- **THEN** hệ thống gán trạng thái `POOR_FOCUS_OR_BLUR`, giải thích rõ bao bì/nhãn chữ bị mờ, và hướng dẫn khách hàng chụp lại với tay máy cố định và đủ ánh sáng

#### Scenario: Ảnh bị cắt cụt biên hoặc che khuất (TRUNCATED_OR_OCCLUDED)
- **WHEN** sản phẩm bị cắt chạm khung viền ngoài của ảnh gốc hoặc bị ngón tay che khuất bao bì
- **THEN** hệ thống gán trạng thái `TRUNCATED_OR_OCCLUDED`, yêu cầu chụp lại với khoảng cách xa hơn để lấy trọn vẹn 100% thân sản phẩm

### Requirement: Xuất file Excel yêu cầu chụp lại đồng bộ cấu trúc Master Excel
Hệ thống SHALL xuất file kết quả `Rabuta_Customer_Reshoot_Request.xlsx` bảo toàn 100% cấu trúc 31 cột gốc của file master catalog, sao chép nguyên vẹn từng hàng dữ liệu của sản phẩm cần chụp lại, đồng thời bổ sung các cột hướng dẫn nghiệp vụ chi tiết cho khách hàng.

#### Scenario: Bảo toàn cấu trúc 31 cột và sao chép dữ liệu SKU
- **WHEN** file Excel chụp lại được tạo
- **THEN** tất cả các cột gốc từ Cột A đến Cột AE (Barcode, Tên EN, Tên DA, Brand, Record ID, v.v.) được giữ nguyên vẹn dữ liệu cho từng SKU cần chụp lại

#### Scenario: Bổ sung 4 cột hướng dẫn chụp lại chuyên dụng
- **WHEN** xuất file cho khách hàng
- **THEN** hệ thống bổ sung 4 cột: `Mức độ ưu tiên chụp lại`, `Lý do chụp lại chi tiết (Tiếng Việt)`, `Góc chụp yêu cầu`, và `Hướng dẫn chụp chuẩn` với nội dung rõ ràng, dễ hiểu

#### Scenario: Nhúng ảnh thumbnail demo đối chiếu
- **WHEN** sản phẩm cần chụp lại có ảnh demo đối chiếu từ file gốc
- **THEN** thumbnail demo được nhúng trực quan vào bảng tính để khách hàng dễ dàng tìm kiếm sản phẩm mẫu trong kho thực tế
