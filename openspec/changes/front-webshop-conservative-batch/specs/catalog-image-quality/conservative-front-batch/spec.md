# Spec Delta

## Purpose

Dựng ảnh webshop mặt trước từ ảnh gốc đã đối chiếu barcode, giữ trọn bao bì trên nền trắng, và phân loại mọi dòng catalog thành ảnh đạt hoặc hồ sơ khách cần chụp lại.

## ADDED Requirements

### Requirement: Ledger khớp barcode với đúng dòng catalog
Hệ thống SHALL đọc workbook thẩm quyền và lập một dòng sổ cái cho mỗi dòng có barcode, giữ nguyên barcode dạng chữ kể cả số 0 ở đầu, cùng số dòng Excel và Record ID. Hai Record ID khác nhau dùng chung một barcode MUST bị chặn cả hai, không được ghi đè ảnh của nhau.

#### Scenario: Khớp một barcode với một dòng
- **WHEN** một ảnh gốc có barcode trùng đúng một dòng catalog, kể cả khác biệt số 0 ở đầu đã được khai báo trong bảng biến thể
- **THEN** sổ cái gắn ảnh đó với đúng số dòng, barcode và Record ID của dòng đó

#### Scenario: Trùng barcode giữa hai sản phẩm
- **WHEN** hai Record ID khác nhau trong workbook mang cùng một barcode
- **THEN** cả hai dòng có trạng thái bị chặn vì xung đột định danh và không có ảnh webshop mới được ghi cho một trong hai dòng

### Requirement: Chỉ dùng ảnh gốc chưa qua xử lý webshop
Hệ thống SHALL chỉ lấy điểm ảnh sản xuất từ các thư mục ảnh gốc đã lọc. Hệ thống MUST NOT dùng ảnh trong thư mục webshop mặt trước hiện tại, ảnh mặt sau, ảnh thumbnail, hay ảnh đã cắt nền làm nguồn phục hồi. Thư mục ảnh gốc đã đánh dấu loại vì không có trong Excel MUST bị loại khỏi hàng đợi tự động.

#### Scenario: Bỏ qua ảnh webshop cũ
- **WHEN** dòng catalog chỉ tìm thấy ứng viên nằm trong thư mục webshop mặt trước đã xuất trước đó
- **THEN** dòng đó không được dựng ảnh mới từ ứng viên đó và giữ trạng thái thiếu nguồn gốc

### Requirement: Không cắt vào bao bì
Hệ thống SHALL giữ toàn bộ đơn vị bán nhìn thấy được, gồm nắp, đáy, mép hàn, nhãn và phần màng hoặc khay thuộc đơn vị đó. Mọi vùng nhận sản phẩm chỉ được nới ra phía nền. Hệ thống MUST NOT xẻ một khung ảnh thành hai nửa bằng nhau, MUST NOT đẩy đường cắt vào trong nhãn, và MUST NOT bào mask vào phía trong sản phẩm. Cạnh nhãn in và nếp gấp tối nằm trong một bao MUST NOT được dùng làm ranh giới giữa hai vỏ. Điểm ảnh màu bàn chạm biên khung MUST NOT bị tính là sản phẩm chạm biên. Nếu đường tách hai vỏ không nằm trên khe giữa hai vỏ hoặc lõi sản phẩm chạm biên khung ảnh, dòng đó MUST không nhận ảnh webshop mới từ khung đó.

#### Scenario: Ảnh hai vỏ đặt cạnh nhau có khe nền
- **WHEN** một khung chứa mặt sau có barcode và một mặt trước hoàn chỉnh, tách nhau bằng một khe nền
- **THEN** ảnh webshop chỉ lấy mặt không mang barcode bán lẻ, và vùng lấy ảnh bao trùm hết vỏ cộng thêm phần nền ở ngoài biên

#### Scenario: Đường cắt không chắc sẽ ăn vào vỏ
- **WHEN** không xác định được khe nền giữa hai vỏ, hoặc vùng sản phẩm chạm cạnh khung
- **THEN** hệ thống không xuất ảnh webshop từ khung đó và ghi trạng thái thiếu mặt trước đủ biên

### Requirement: Một lần dựng nền trắng, không phóng to
Hệ thống SHALL xuất mỗi ảnh đạt trên canvas vuông 2400 điểm ảnh, nền trắng, sản phẩm căn giữa, không chạm bốn cạnh canvas. Điểm ảnh sản phẩm chỉ được thu nhỏ từ vùng gốc. Hệ thống MUST NOT phóng to vùng sản phẩm và MUST NOT mài hoặc ghi đè lại file JPEG đã xuất.

#### Scenario: Nguồn đủ lớn
- **WHEN** vùng sản phẩm gốc lớn hơn kích thước đặt trên canvas
- **THEN** ảnh xuất ra là 2400×2400, bốn góc trắng, sản phẩm nằm trọn bên trong và không sắc nét hơn bằng cách phóng điểm ảnh

#### Scenario: Nguồn rõ nhưng nhỏ hơn canvas
- **WHEN** toàn bộ vỏ đã đủ biên nhưng đặt lên 2400 mà không phóng to thì sản phẩm chiếm dưới ngưỡng chiếm chỗ đã khóa
- **THEN** hệ thống không xuất ảnh phóng to và chuyển dòng sang danh sách cần chụp lại

### Requirement: Mỗi dòng catalog có đúng một trạng thái
Hệ thống SHALL ghi trạng thái cho mọi dòng có barcode. Trạng thái được phép là ảnh đạt để nhúng, khách cần chụp lại, hoặc bị chặn vì xung đột định danh hay biên không đủ. Một dòng không được vừa có ảnh đạt vừa nằm trong danh sách chụp lại.

#### Scenario: Xử lý theo lô vẫn không bỏ sót dòng
- **WHEN** một lô từ 100 đến 200 dòng kết thúc hoặc được chạy lại
- **THEN** sổ cái vẫn có đúng một trạng thái cho mỗi dòng trong lô, và dòng đã đạt không bị dựng lại từ ảnh đã xuất

### Requirement: Danh sách khách tự chụp lại
Hệ thống SHALL xuất một workbook riêng cho các dòng không có ảnh gốc dùng được. Workbook đó MUST gồm số dòng, barcode, Record ID, tên sản phẩm và lý do. Các dòng này MUST NOT có ảnh webshop mới ở cột mặt trước.

#### Scenario: Dòng không có ảnh trong năm thư mục gốc
- **WHEN** sổ cái không tìm thấy ảnh gốc hợp lệ cho một barcode
- **THEN** dòng xuất hiện trong workbook khách chụp lại với lý do thiếu nguồn và không có file ảnh webshop mới

### Requirement: Ca lỗi phổ biến vẫn phải ra đúng mặt và đủ bao bì
Lấy sai mặt và ảnh mất chi tiết là lỗi chất lượng phổ biến, cùng mức với các ca bên dưới. Hệ thống MUST NOT ghi trạng thái đạt cho ảnh còn một mặt barcode tách riêng, mặt bên, mặt thành phần dinh dưỡng, hoặc ảnh bị cắt mất nắp, đáy, mép hàn, nhãn, màng, khay hay phần sản phẩm nhìn thấy được. Mã vạch in hoặc dán trên chính bao bì mặt trước được chọn không phải mặt barcode. Khi không tách được mặt trước một cách chắc, dòng MUST bị chặn thay vì nhận một mặt sai.

#### Scenario: Hai chai nằm ngang chồng lên nhau
- **WHEN** khung hình có hai chai nằm ngang, một chai mang nhãn thương hiệu và một chai mang barcode, khe giữa hai chai chạy dọc theo thân chai
- **THEN** ảnh webshop lấy trọn chai không mang barcode, gồm nắp và đáy, và không chứa thân chai có barcode

#### Scenario: Ba vỏ xếp hàng, mặt trước ở giữa
- **WHEN** ba chủ thể của cùng sản phẩm nằm thành một hàng, hai đầu là mặt bên và mặt barcode, chủ thể giữa là mặt thương hiệu
- **THEN** ảnh webshop lấy chủ thể giữa, giữ trọn nắp, đáy và phần bao bì nhô ra, và không chứa phần nào của hai chủ thể hai bên

#### Scenario: Ba vỏ xếp hàng, mặt trước ở một đầu
- **WHEN** ba chủ thể nằm thành một hàng và chủ thể khớp ảnh mặt trước của khách nằm ở một đầu
- **THEN** ảnh webshop lấy chủ thể ở đầu đó, không theo quy tắc vị trí

#### Scenario: Một túi thực phẩm chỉ có một mặt
- **WHEN** khung chỉ có một đơn vị bán là túi hoặc khay thực phẩm, nhãn barcode dán trên chính túi đó
- **THEN** ảnh webshop giữ trọn màng, mép hàn và phần thực phẩm bên trong, và không cắt theo cạnh nhãn hay theo hình thực phẩm

#### Scenario: Rau củ trong một bao
- **WHEN** khung là một bó rau hoặc một lưới củ, tem barcode nằm trên cùng bao đó
- **THEN** ảnh webshop giữ cả bao, gồm lá, thân, rễ hoặc toàn bộ củ trong lưới, và không tách tem thành một mặt thứ hai

#### Scenario: Thùng carton
- **WHEN** một thùng hiện hai mặt in gặp nhau ở nếp gấp và không có khe nền giữa hai mặt đó
- **THEN** hệ thống không xẻ thùng theo nếp gấp. Khi khung có nhiều thùng tách rời và mặt đối diện barcode cũng chỉ là mặt chữ hoặc mặt thành phần, dòng bị chặn thay vì nhận mặt đó

#### Scenario: Ảnh gốc đã tách sẵn mặt trước và mặt sau
- **WHEN** cùng một barcode có một ảnh chỉ một mặt hàng và một ảnh khác là mặt barcode
- **THEN** hệ thống dùng ảnh không phải mặt barcode, và không chạy bước cắt nhiều chủ thể trên ảnh chỉ có một bao

#### Scenario: Cụm chai đứng dính nhau
- **WHEN** khung có hai hoặc ba chai gia vị đứng cạnh nhau và một chai mang barcode
- **THEN** ảnh webshop lấy chai không mang barcode, đường cắt đi qua khe giữa các chai, và MUST NOT xẻ dọc giữa một chai

#### Scenario: Một vỏ nằm ngang
- **WHEN** một đơn vị bán nằm xoay theo cạnh dài, kể cả khay nhiều cốc hoặc một gói nằm ngang, và khung không có vỏ thứ hai
- **THEN** ảnh webshop giữ trọn vỏ đó và MUST NOT coi cạnh dài là một vỏ thứ hai

#### Scenario: Hai túi cùng màu dính nhau
- **WHEN** hai túi cùng màu đứng cạnh nhau, barcode nằm trên túi bên phải, và túi đó có mặt thành phần hoặc chữ in dọc
- **THEN** ảnh webshop chỉ còn túi bên trái với nhãn thương hiệu và ảnh thực phẩm còn nguyên, không còn mặt thành phần, không còn chữ in dọc của túi bên phải, và không còn nền bàn

#### Scenario: Một đống rau không phải cặp mặt trước mặt sau
- **WHEN** khung là một đống rau củ không đều, không phải một cặp mặt barcode và mặt trước
- **THEN** ảnh webshop giữ cả đống và MUST NOT tách đống thành một mặt giả rồi bỏ phần còn lại

#### Scenario: Một túi thủy sản không có mặt thứ hai
- **WHEN** khung chỉ có một túi thủy sản, hoặc một túi cùng khay của túi đó, và không có mặt in thứ hai
- **THEN** ảnh webshop giữ túi, mép hàn, màng và khay, và MUST NOT bịa thêm một mặt để cắt

#### Scenario: Nhiều thùng xếp chồng không có mặt khớp duy nhất
- **WHEN** nhiều món hàng xếp chồng nhưng không chủ thể nào vượt ngưỡng khớp duy nhất với ảnh mặt trước
- **THEN** dòng bị chặn để review và hệ thống MUST NOT chọn mặt thành phần theo vị trí xa barcode

### Requirement: Định nghĩa ảnh đạt
Một ảnh webshop mặt trước SHALL được coi là đạt chỉ khi đồng thời thỏa sáu tiêu chí. Mỗi tiêu chí MUST có cổng tự động pass/fail đo trên canvas đã dựng và trên ảnh gốc. Ngưỡng ghi ở đây là giá trị khởi điểm; ngưỡng chỉ được đổi sau khi đo lại trên toàn bộ bộ ảnh mẫu đã gắn nhãn, không đổi theo một ảnh đơn lẻ.

- Q1 Nền trắng sạch: canvas 2400×2400 RGB. Phân biệt mask sản phẩm đầy đủ với envelope chữ nhật có thể giữ để bảo vệ màng trong suốt. Ngoài envelope, ít nhất 99,5% điểm ảnh có cả ba kênh từ 250 trở lên. Bốn ô góc 64×64 có trung bình từ 253 trở lên. Envelope MUST được kiểm tra riêng theo Q2/Q3; không được nới để che sản phẩm hoặc lỗi nền.
- Q2 Đủ bao bì: đường biên sản phẩm MUST được xác nhận đầy đủ trong ảnh gốc và không bị cắt bởi mép khung. Mask sản phẩm phải phủ ít nhất 99,5% lõi bao bì được đánh giá độc lập; lỗ kín bên trong không quá 0,5% diện tích sản phẩm. Mọi đường phân cách giữa chủ thể có ít nhất 90% điểm ảnh là nền. Nắp, đáy, mép hàn, góc xé, màng, khay và phần nhô ra MUST được giữ. Thiếu bằng chứng hoàn chỉnh thì cổng trượt.
- Q3 Một đơn vị bán, envelope nền thừa chỉ được là hình chữ nhật: màng, cửa sổ trong suốt và mép túi MUST được giữ, không khoét thành trắng. Nền bàn hoặc bìa chỉ được giữ bên trong envelope chữ nhật khi phần không trắng lấp đầy hình chữ nhật đó ít nhất 90%. Nền thừa ngoài envelope không quá 9% diện tích sản phẩm; không còn mảnh rời nào lớn hơn 1% diện tích sản phẩm. Envelope bị giới hạn bởi tối đa 18% chiều dài sản phẩm và phần lề có thể đặt trên canvas; nếu không thể giữ đủ sản phẩm và lề thì trả về xử lý.
- Q4 Đúng mặt trước: chủ thể được chọn MUST có một điểm khớp duy nhất với ảnh mặt trước khách cung cấp ở cột W, cao hơn mọi chủ thể khác và cao hơn ảnh mặt sau cột Y nếu có, qua cả ngưỡng tuyệt đối và biên chênh lệch đã khóa. Điểm khớp ngang hoặc hòa MUST bị trả về xử lý. Vị trí trái/phải/giữa, xa/gần barcode và thứ tự candidate MUST NOT quyết định mặt. Thiếu tham chiếu đáng tin cậy thì chỉ được chấp nhận khi có bằng chứng duyệt mắt độc lập gắn với barcode, Record ID và hash ảnh; barcode trên chính bao bì mặt trước được phép.
- Q5 Đúng hình dạng và độ nét: tỷ lệ đồng nhất được tính trên bbox sản phẩm đầy đủ, không gồm envelope nền. Tỷ lệ scale MUST <=1. Cạnh dài bbox sản phẩm bằng 2064 ± 2 điểm ảnh; lề canvas tối thiểu 48 điểm ảnh; sai lệch tỷ lệ khung không quá 0,5%. Chỉ xoay theo bội số 90 độ. JPEG chất lượng 95, 4:4:4, ghi một lần. Đo trên file JPEG đã lưu.
- Q6 Đúng định danh và provenance: barcode trong tên file trùng barcode dòng sổ cái; Record ID không xung đột; fingerprint nguồn/tham chiếu/cấu hình và SHA-256 đầu ra khớp evidence hiện hành.

Các Q1–Q6 measurement của Python và semantic evidence của Gemini SHALL được lưu với kiểu/nguồn riêng. Nếu Q2/Q3 có mask được duyệt độc lập thì áp dụng các ngưỡng số ở trên; Gemini MUST NOT tuyên bố đã đo tỷ lệ pixel. Khi không có mask độc lập, schema-validated Gemini evidence có thể xác nhận `complete/no-clipping`, `single-unit/package-preserved` hoặc trả REVIEW; không ghi phần trăm mask giả. Q4 cần một front reference W đáng tin cậy hoặc review bằng mắt độc lập được gắn barcode, Record ID và hash. W/Y mâu thuẫn hoặc nguồn front/back không xác định rõ thì REVIEW. Thiếu model evidence không thể PASS.

#### Scenario: Mặt trước sạch trên nền trắng
- **WHEN** canvas chỉ còn một sản phẩm khớp ảnh cột W, nền trắng, đủ bao bì và đúng tỷ lệ
- **THEN** cả sáu cổng đều pass và dòng được ghi là đạt

#### Scenario: Nền chữ nhật quanh bao bì trong suốt
- **WHEN** một bao trong suốt còn đủ màng và phần bìa quanh bao nằm trọn trong một hình chữ nhật
- **THEN** ảnh qua Q3

#### Scenario: Nền bàn còn quanh sản phẩm
- **WHEN** canvas có một vệt bìa hoặc bàn không lấp đầy hình chữ nhật quanh sản phẩm
- **THEN** dòng được trả về xử lý, không có file ảnh đạt và không được nhúng

#### Scenario: Chủ thể được chọn không khớp ảnh mặt trước của khách
- **WHEN** chủ thể có điểm khớp với ảnh cột W thấp hơn một chủ thể khác trong cùng khung, hoặc khớp ảnh cột Y hơn ảnh cột W
- **THEN** dòng được trả về xử lý vì sai mặt, kể cả khi canvas sạch

#### Scenario: Hai chủ thể bằng điểm hoặc thiếu tham chiếu đáng tin cậy
- **WHEN** hai chủ thể bằng điểm, khoảng cách dưới ngưỡng, hoặc ảnh cột W không đủ tin cậy để so sánh
- **THEN** hệ thống không chọn theo barcode, vị trí hoặc thứ tự candidate; dòng vào review trừ khi có bằng chứng duyệt mắt độc lập gắn với barcode, Record ID và hash ảnh

#### Scenario: Mã vạch nằm trên bao bì được chọn
- **WHEN** đơn vị bán được chọn khớp ảnh cột W và mã vạch bán lẻ in hoặc dán trên chính bao bì đó
- **THEN** ảnh webshop qua Q4 dù canvas còn đọc được mã vạch đó

#### Scenario: Ảnh gốc chỉ có mặt sau
- **WHEN** mọi chủ thể trong mọi ảnh gốc của barcode đều là mặt barcode, mặt thành phần hoặc mặt dinh dưỡng
- **THEN** dòng vào workbook khách chụp lại và không có ảnh webshop

### Requirement: Cổng QA trả ảnh chưa đạt về xử lý
Hệ thống SHALL chạy sáu cổng trước khi ghi trạng thái đạt. Ảnh trượt bất kỳ cổng nào MUST nhận trạng thái review/reshoot, MUST NOT có đường dẫn accepted và MUST NOT được nhúng. Ảnh trả về được thử lại với ảnh gốc khác của cùng barcode. Khi hết ảnh gốc, dòng đi vào workbook khách chụp lại kèm cổng đã trượt. Mỗi quyết định MUST ghi kết quả từng gate, phép đo, fingerprint nguồn/tham chiếu/cấu hình và SHA-256 ảnh. Lỗi nặng gồm sai mặt, mất bao bì, còn sản phẩm thứ hai, còn một mặt barcode tách khỏi bao bì đã chọn, méo hoặc phóng to, sai định danh. Lỗi nặng MUST NOT nằm trong phần 5% được phép sai. Trạng thái ACCEPTED không tự phát hành lô.

#### Scenario: Cổng trượt trên ảnh gốc đầu, ảnh gốc thứ hai đạt
- **WHEN** ảnh gốc đầu tiên của một barcode trượt một cổng và ảnh gốc thứ hai qua cả sáu cổng
- **THEN** dòng được ghi là đạt từ ảnh gốc thứ hai, và sổ cái lưu lý do trượt của ảnh đầu

#### Scenario: Mọi ảnh gốc đều trượt
- **WHEN** mọi ảnh gốc của một barcode đều trượt ít nhất một cổng
- **THEN** dòng không có ảnh webshop và vào workbook khách chụp lại kèm tên cổng đã trượt

### Requirement: Đo chất lượng trên ma trận phủ, không trên một ảnh
Hệ thống SHALL đánh giá mọi thay đổi thuật toán trên bộ ảnh mẫu gắn nhãn gồm ít nhất 1000 ảnh, rút ngẫu nhiên theo tỷ lệ của năm thư mục ảnh gốc. Mỗi ảnh mẫu có nhãn nhóm bao bì (chai lọ, lon, túi mềm, hộp giấy, khay trong, rau củ), số chủ thể, bố cục, vị trí mặt trước, và các thuộc tính khó (trong suốt, màu trắng, nền trắng, dính nhau, nằm ngang, chạm cạnh, lẫn đồ khác). Báo cáo MUST cho tỷ lệ đạt và tỷ lệ lỗi theo từng nhóm và từng cổng. Một thay đổi chỉ được nhận khi không nhóm nào tăng lỗi nặng.

#### Scenario: Sửa thuật toán cho một ảnh
- **WHEN** một thay đổi làm đúng một ảnh nhưng làm tăng lỗi nặng ở bất kỳ nhóm nào trong bộ mẫu
- **THEN** thay đổi đó bị từ chối

### Requirement: Điều kiện phát hành lô
Sau khi các cổng tự động chạy xong, hệ thống SHALL rút ngẫu nhiên theo nhóm ít nhất 93 ảnh từ đúng tập accepted và kiểm tra hash trước khi duyệt bằng mắt. Mỗi nhóm có từ 30 ảnh đạt trở lên MUST có ít nhất 8 ảnh trong mẫu. Lô chỉ được phát hành khi mẫu không có lỗi nặng và có tối đa 1 lỗi nhẹ. Với mẫu ngẫu nhiên độc lập, quy tắc này hỗ trợ mức lỗi tổng thể không quá 5% ở độ tin cậy một phía 95%; 8 ảnh mỗi nhóm MUST NOT được hiểu là bằng chứng độ tin cậy 95% cho từng nhóm. Một lỗi nặng trong một nhóm trả toàn bộ ảnh accepted của nhóm đó về xử lý. Release record MUST khóa seed, barcode/Record ID, output hash, báo cáo gate và quyết định người duyệt. Tỷ lệ dòng có ảnh accepted trên tổng catalog MUST được báo cáo riêng và không thay cho tỷ lệ chất lượng.

#### Scenario: Mẫu duyệt có một lỗi nặng
- **WHEN** mẫu duyệt có một ảnh sai mặt trong nhóm hộp giấy
- **THEN** lô không được phát hành và mọi ảnh đạt của nhóm hộp giấy trả về xử lý

#### Scenario: Mẫu duyệt đạt
- **WHEN** 93 ảnh duyệt không có lỗi nặng và có tối đa một lỗi nhẹ
- **THEN** lô được phát hành để nhúng vào bản sao workbook

### Requirement: Nhúng cột webshop chỉ sau khi ảnh đạt
Hệ thống SHALL nhúng ảnh đã đạt vào cột ảnh webshop mặt trước của một bản sao workbook. Cột ảnh mặt trước gốc và cột ảnh mặt sau MUST giữ nguyên byte ảnh đã nhúng. Workbook khách đang dùng làm nguồn MUST NOT bị ghi đè tại chỗ. Ảnh chưa đạt MUST NOT xuất hiện ở cột webshop.

#### Scenario: Cập nhật cột webshop
- **WHEN** một dòng có ảnh đạt và bản sao workbook được xuất
- **THEN** cột webshop mặt trước của dòng đó hiển thị ảnh mới, còn cột ảnh gốc và cột mặt sau không đổi so với workbook nguồn
