# SSI iBoard-like Backtest UI

## V46 Hotfix 9 — Chuyển khung thời gian khi RUN
- Khi người dùng đổi timeframe trong lúc RUN, trình duyệt khóa `replay-interval` ngay lập tức; không gửi thêm nhịp replay trong lúc server dựng lại nến.
- Giữ nguyên `replay-state`, con trỏ tick, phiên replay và trạng thái giao dịch trong giai đoạn chuyển đổi.
- Chỉ phản hồi có trigger `timeframe` và đúng timeframe đang chọn mới được mở khóa replay; kết quả interval đang bay tới từ khung cũ bị từ chối.
- Sau khi dựng biểu đồ xong, đồng hồ mô phỏng được neo lại theo thời điểm mô phỏng đã chụp trước khi dựng, để thời gian chuyển khung không làm đồng hồ chạy tiếp.
- Loại bỏ đăng ký clientside callback trùng lặp cùng ghi vào `price-chart.figure` và `replay-state.data`.
- Đã kiểm tra cú pháp Python và cú pháp JavaScript callback; chưa kiểm thử tích hợp trên Windows với DuckDB thực tế.

Giao diện mẫu xây bằng Python, Dash và Plotly dựa trên ảnh SSI iBoard. Mục tiêu hiện tại là dựng layout để phát triển back-test dần; đây không phải sản phẩm SSI, không kết nối tài khoản và không gửi lệnh thật.

## Chạy trên Windows
1. Giải nén `ssi_iboard_backtest.zip`.
2. Cài Python 3.10/3.11 64-bit.
3. Kiểm tra `DB_PATH` trong `config.py`. Mặc định là `F:\\New Projects\\Chung_Khoan\\GiaKhopLenh\\data\\database\\vn30f1m.duckdb`.
4. Chạy `run_dashboard.bat`. Lần đầu tự tạo môi trường `.venv` và cài thư viện.
5. Mở http://127.0.0.1:8050.

## Cấu trúc
- `app.py`: layout và callback giao diện.
- `config.py`: cấu hình app, database và khung thời gian.
- `data_access.py`: đọc DuckDB read-only, tạo OHLCV và dữ liệu mô phỏng dự phòng.
- `assets/style.css`: màu sắc, lưới bố cục và responsive.
- `requirements.txt`: thư viện cần cài.
- `run_dashboard.bat`: khởi chạy trên Windows.

## Dữ liệu
Đọc bảng `vn30f1m_ticks` với cột `DateTime`, `Price`, `Volume`; tối đa 500.000 tick mới nhất. Ứng dụng kết nối DuckDB ở chế độ chỉ đọc. Nếu DB không tồn tại hoặc schema không đúng, dùng dữ liệu mô phỏng để giao diện vẫn chạy. Sổ lệnh, tài sản và mini-chart hiện là số liệu minh họa. Đổi timeframe sẽ dựng lại nến OHLCV từ tick.

## Phạm vi hiện tại
Đây là bản dựng giao diện khởi đầu, chưa pixel-perfect. Chưa có engine back-test, phí, trượt giá, quản lý vị thế, replay tick hay kết nối giao dịch. Nút Long/Short chỉ ghi nhận lựa chọn trên giao diện.


## Cập nhật vùng đặt lệnh
- Ô `KL khác` đã được thay bằng ô nhập số lượng có thể gõ trực tiếp, kèm nút giảm/tăng.
- Các nút nhanh 1, 5, 10, 20 tự điền số lượng vào ô nhập.
- Có thông báo kiểm tra số nguyên và giới hạn mô phỏng 1–20 hợp đồng. Giới hạn này là placeholder UI, không phải hạn mức tài khoản SSI.
- Bổ sung các nút loại lệnh ATO, ATC, MTL, MOK, MAK; chọn nút sẽ làm nổi bật loại lệnh đang chọn.
- Long/Short hiển thị số lượng đang chọn cùng giá nhập. Mọi thao tác chỉ mô phỏng, chưa có engine back-test.


## Cập nhật biểu đồ và chế độ Back-Test
- Biểu đồ dùng trục thời gian nén theo thứ tự nến, vì vậy các khoảng không có giao dịch (qua đêm/ngày nghỉ) không tạo khoảng trống lớn trên trục X.
- Có thanh chọn ngày, giờ, phút, giây và nút RUN phía trên toàn bộ giao diện.
- Khi RUN, biểu đồ bắt đầu tại tick đầu tiên có thời gian lớn hơn hoặc bằng thời điểm đã chọn, sau đó lần lượt bổ sung tick lịch sử theo thứ tự thời gian. Replay dùng timestamp của từng bản ghi: mỗi nhịp 500 ms đưa vào tất cả tick có timestamp không lớn hơn đồng hồ mô phỏng; không bỏ bớt tick theo số lượng cố định.
- Khung thời gian biểu đồ: 1m, 5m, 15m, 30m, 1h, 4h, 1D.
- Đường giá hiện tại là nét đứt xanh mỏng, có độ mờ cao hơn.
- Dữ liệu vẫn được giới hạn bởi số tick `load_ticks()` trả về (mặc định 500.000 tick gần nhất); cần mở rộng bộ nạp theo ngày nếu muốn replay toàn bộ lịch sử dài hơn.


## Điều chỉnh Back-Test theo cửa sổ lịch sử
- Hộp Giờ/Phút/Giây dùng nền trắng, chữ đen; danh sách xổ xuống cũng nền trắng/chữ đen để đọc rõ và chọn giá trị.
- Khi nhấn RUN, biểu đồ nạp trước lịch sử kết thúc ngay trước thời điểm chọn; tick từ thời điểm đó trở đi mới được đưa vào theo nhịp replay.
- Cửa sổ lịch sử trước mốc bắt đầu: 1m = 8 giờ; 5m = 8 ngày; 15m/30m = 15 ngày; 1h/4h = 30 ngày; 1D = 60 ngày.
- Khi đổi timeframe trong lúc Back-Test, cửa sổ lịch sử được tính lại theo timeframe mới nhưng vẫn giữ mốc thời gian bắt đầu replay.
- Thời gian mô phỏng bắt đầu bằng mốc người dùng chọn; trạng thái hiển thị thời gian lịch sử đã phát tới. Đồng hồ replay chạy wall-clock 1:1 với độ chính xác phần giây; các tick được đưa vào theo timestamp của chúng.


## Tinh chỉnh giao diện và tương tác biểu đồ
- Hộp ngày rộng 190px, lớn hơn rõ rệt các hộp giờ/phút/giây; hộp chọn khung thời gian dùng chữ đen trên nền trắng.
- Nến tăng có cả viền và phần thân màu xanh; nến giảm có cả viền và phần thân màu đỏ.
- Đường giá cuối cùng rõ hơn một chút nhưng vẫn có độ trong suốt.
- Bật crosshair ngang theo con trỏ, hiển thị giá tại vị trí con trỏ; nhấp phải trong vùng biểu đồ để sao chép giá gần vị trí đó.
- Kéo chuột trái để pan biểu đồ sang trái/phải. Tính năng copy dùng clipboard của trình duyệt; tùy chính sách trình duyệt, clipboard có thể chỉ hoạt động trong localhost/HTTPS.


## Sửa tương tác biểu đồ lần này
- Giữ trạng thái pan/zoom qua các lần cập nhật replay bằng cách đọc `relayoutData` và áp lại range trục X; giảm hiện tượng kéo xong bị bật về vị trí cũ.
- Chuột phải mở menu `Copy giá: <giá>`; chỉ khi nhấn mục đó mới copy giá vào clipboard.
- Đồng hồ dưới biểu đồ chạy theo thời gian mô phỏng bắt đầu từ mốc chọn: cứ 1 giây thực tăng 1 giây mô phỏng; các tick lịch sử chỉ xuất hiện khi thời gian mô phỏng đi tới timestamp của chúng.
- Bộ chọn khung thời gian chuyển sang HTML select native, hình chữ nhật vuông, nền trắng chữ đen để luôn thấy giá trị đang chọn.


## RUN / STOP và Copy giá
- Có nút STOP cạnh RUN. Khi RUN, các bộ chọn ngày/giờ/phút/giây và nút RUN bị khóa; STOP được bật. Chỉ STOP kết thúc replay và mở lại các bộ chọn.
- STOP đặt biểu đồ lại vùng lịch sử trước mốc đã chọn, đồng thời giữ mốc giờ làm điểm tham chiếu để chạy lại.
- Nếu thời điểm chọn nằm sau tick mới nhất trong DB, replay tự lùi về tick gần nhất có sẵn thay vì hiển thị biểu đồ trống với thông báo không có giao dịch. Trạng thái sẽ nói rõ việc dùng tick gần nhất.
- Khi đã phát hết tick đang có trong DB, đồng hồ mô phỏng vẫn tiếp tục chạy; chỉ nút STOP kết thúc Back-Test.
- Menu chuột phải Copy giá không còn bị đóng khi con trỏ rời vùng biểu đồ để đi tới nút Copy.


## Fix timeframe switch during replay
- Removed manual reuse of old ordinal X-axis ranges, which could point outside the new candle sequence after changing timeframe and leave only one candle visible.
- Plotly now preserves pan/zoom during updates within the same timeframe using `uirevision`, while a timeframe-specific `uirevision` resets the viewport when changing aggregation.
- Widened the timeframe dropdown from 62px to 82px so the selected label is not clipped.


## Fix giữ vị trí kéo biểu đồ
- JavaScript theo dõi sự kiện `plotly_relayout` để lưu phạm vi X do người dùng kéo.
- Sau mỗi lần Plotly vẽ lại do Back-Test cập nhật tick, nếu phạm vi X bị reset, ứng dụng áp lại phạm vi người dùng đã chọn.
- Phạm vi chỉ được giữ trong cùng một khung thời gian; khi đổi timeframe, phạm vi cũ không được áp vào trục nến mới.


## Tối ưu khi đổi khung giá

- Trước khi tổng hợp OHLCV, biểu đồ chỉ lấy phần tick đủ cho tối đa khoảng 500 nến của timeframe đang chọn, thay vì resample toàn bộ 500.000 tick rồi mới cắt kết quả.
- Đã bỏ vòng JavaScript tự gọi `Plotly.relayout()` sau mỗi lần `plotly_afterplot`; việc giữ pan/zoom trong cùng timeframe giao cho `uirevision` của Plotly để tránh cạnh tranh với cập nhật figure của Dash.
- Khi đang Back-Test, biểu đồ vẫn cập nhật theo nhịp interval 1 giây; tốc độ thực tế còn phụ thuộc cấu hình máy và dung lượng dữ liệu.


## Tổng hợp các điểm đã sửa và kiểm tra trong bản hiện tại

- Chọn khung thời gian: trục X dùng chỉ số nến tuần tự để không tạo khoảng trống qua đêm/ngày nghỉ; `uirevision` riêng cho từng trục và timeframe để không mang tọa độ nến cũ sang timeframe mới.
- Phần lịch sử bên trái: bỏ bộ lọc `timeframe * 505` theo phút đồng hồ (đặc biệt làm khung 5m chỉ còn khoảng 42 giờ thay vì cửa sổ 8 ngày); giờ giới hạn theo cửa sổ lịch sử tương ứng với timeframe.
- Hiệu năng: dữ liệu vẫn được cắt theo cửa sổ trước khi resample; OHLCV hiển thị tối đa 500 nến để tránh tạo biểu đồ quá nặng.
- Back-Test: RUN khóa bộ chọn ngày/giờ và chính nút RUN; STOP kết thúc, mở lại bộ chọn và đưa biểu đồ về lịch sử trước mốc đã chọn. Khi đổi timeframe trong lúc RUN, mốc replay được giữ và cửa sổ lịch sử được tính lại theo khung mới.
- Mốc thời gian không có tick: dùng tick đầu tiên sau mốc; nếu mốc nằm sau dữ liệu mới nhất thì fallback về tick mới nhất và thông báo trạng thái.
- Pan/zoom: đã bỏ vòng JavaScript tự gọi `Plotly.relayout` sau mỗi lần vẽ; pan được giữ trong cùng timeframe bởi Plotly, nhưng phải reset khi chuyển khung để tránh phạm vi ordinal X cũ làm mất nến bên trái.
- Tương tác: crosshair giá theo con trỏ, menu chuột phải Copy giá không tự đóng khi rê sang nút Copy; bộ chọn timeframe rộng 82px.
- Vùng đặt lệnh mô phỏng: số lượng gõ trực tiếp, nút nhanh 1/5/10/20, +/- và các lựa chọn ATO/ATC/MTL/MOK/MAK; không gửi lệnh thật.

Lưu ý: kiểm tra cú pháp và logic tĩnh không thay thế kiểm thử tương tác trên trình duyệt Windows với DuckDB thực tế.


## Sửa mất nến bên trái khi chuyển khung thời gian
- Cửa sổ lịch sử biểu đồ được tăng theo khung: 1m = 5 ngày, 5m = 20 ngày, 15m = 45 ngày, 30m = 90 ngày, 1h = 180 ngày, 4h = 365 ngày, 1D = 730 ngày. Đây là cửa sổ lịch; số nến thực tế phụ thuộc số phiên và dữ liệu đang có trong DuckDB.
- Cửa sổ lịch sử Back-Test dùng cùng quy tắc để tránh khung biểu đồ hiển thị ít nến hơn vùng lịch sử replay cung cấp.
- Trục X dùng `uirevision` riêng theo timeframe, vì tọa độ X là chỉ số nến tuần tự. Khi đổi khung, trục tự tính lại phạm vi; khi cập nhật replay trong cùng khung, thao tác pan/zoom được giữ.
- Kiểm tra tĩnh đã chạy cho tất cả các timeframe 1m, 5m, 15m, 30m, 1h, 4h, 1D; cần xác nhận thêm bằng tương tác trình duyệt trên máy Windows với DuckDB thực tế.

### Bản sửa pan/zoom và độ trễ cập nhật

- Không ép `autorange=True` ở mỗi lần dựng figure. Plotly có thể giữ phạm vi X do người dùng kéo/zoom khi `uirevision` không đổi; đổi timeframe dùng key riêng để tự tính lại phạm vi.
- Khi Back-Test RUN, scheduler kiểm tra mỗi 500 ms. Figure chỉ dựng lại khi có tick mới đủ điều kiện theo timestamp replay; nếu chưa có tick mới thì giữ nguyên figure.
- Tối ưu tổng hợp OHLCV bằng cách tránh sắp xếp lại DataFrame khi dữ liệu đã theo thứ tự thời gian.
- Lưu ý: ứng dụng hiện phát lại dữ liệu đã có trong DuckDB; thay đổi này không tự kết nối API KBS để nhận tick trực tiếp mới.

## Sửa giữ pan/zoom và tăng khoảng cách giữa các nến
- OHLCV không còn bị cắt `tail(500)` trong hàm tổng hợp. Cắt đuôi làm chỉ số X của mọi cây nến cũ bị đổi mỗi khi có nến mới, khiến viewport kéo/zoom bị lệch khi Dash thay figure.
- Trong Back-Test, cửa sổ tick lịch sử được cố định theo mốc replay; chart không tự áp lại bộ lọc theo timestamp cuối đang tăng dần. Chỉ số X của nến đã tồn tại vì vậy giữ nguyên trong suốt replay.
- `relayoutData` được đọc và áp lại cho cả hai trục X khi cập nhật figure. Khi đổi timeframe, bỏ qua phạm vi số cũ để tránh mang tọa độ của timeframe trước sang khung mới.
- Mặc định hiển thị khoảng 110 nến gần nhất để nến dễ nhìn và cách nhau rõ hơn; vẫn giữ phần lịch sử còn lại để kéo sang trái. Đặt chiều rộng thân nến và cột volume là 0.62 đơn vị, cùng `bargap=0.32`.
- Đã kiểm tra cú pháp Python và tính toàn vẹn ZIP. Môi trường đóng gói không có Dash/DuckDB nên chưa thể chạy kiểm thử trình duyệt với database thực tế.


## Review bản đóng gói và sửa giữ viewport

- ZIP có một cấp thư mục duy nhất: `ssi_iboard_backtest/` chứa trực tiếp `app.py`, `config.py`, `data_access.py`, `assets/` và các tệp cần thiết.
- Không áp dụng `xaxis.range` từ `relayoutData` ở mỗi lần cập nhật replay; việc ghi range liên tục có thể ghi đè trạng thái pan/zoom người dùng vừa chọn.
- `uirevision` của trục X ổn định trong cùng timeframe để Plotly tự giữ viewport khi figure cập nhật.
- Chỉ đặt phạm vi mặc định 110 nến khi mở giao diện, RUN/STOP hoặc chuyển timeframe; cập nhật replay định kỳ không ép lại phạm vi.
- `run_dashboard.bat` chỉ cài dependencies khi môi trường chưa import được các thư viện, tránh cài đặt lại ở mỗi lần chạy.
- `requirements.txt` cho phép Dash 2.x–4.x (`dash>=2.18,<5`).


## Hotfix lỗi Plotly Candlestick `Bad property path: width`

- Đã loại bỏ `width=0.62` khỏi `go.Candlestick(...)`. Plotly Candlestick không hỗ trợ thuộc tính `width`; thuộc tính này hợp lệ với `go.Bar`, nhưng khiến ứng dụng dừng khi tạo biểu đồ.
- Giữ `width=0.62` cho biểu đồ Volume (`go.Bar`).
- Kiểm tra cú pháp Python và kiểm tra schema của trace Candlestick bằng Plotly nếu thư viện có sẵn trong môi trường đóng gói.


## Cập nhật bản sửa viewport, replay và dữ liệu

- Biểu đồ dùng Plotly `go.Candlestick` (nến) và `go.Bar` (khối lượng). Nét viền nến được tăng nhẹ; không đặt `width` lên Candlestick vì Plotly không hỗ trợ thuộc tính này.
- Trong RUN, phạm vi X được lưu trong `replay-state`. Nếu người dùng kéo sang trái, lần cập nhật tiếp theo giữ phạm vi thủ công; nếu phạm vi vẫn ở sát nến cuối, chế độ Follow sẽ dịch phạm vi để theo nến mới. Nút `Về nến mới nhất` bật lại Follow.
- Khi RUN, ứng dụng truy vấn phần đuôi DuckDB mỗi 500 ms, đọc tăng dần từ timestamp cuối cùng thay vì tải lại toàn bộ 500.000 tick. Dữ liệu mới chỉ xuất hiện nếu một tiến trình khác đang ghi tick vào DB; ứng dụng không tự gọi API KBS.
- Cache được gộp theo ID nếu schema có cột ID; nếu không có ID thì khử trùng lặp theo thời gian/giá/khối lượng.
- Kiểm thử logic Python/ZIP đã thực hiện; chưa thể kiểm thử trình duyệt Windows và dữ liệu DuckDB của người dùng trong môi trường đóng gói.


## Hotfix: nến OHLC, giữ vùng xem và replay theo timestamp

- `Candlestick.whiskerwidth=0` ẩn các vạch ngang nhỏ ở đầu/cuối râu nến; dữ liệu OHLC `open/high/low/close` và râu nến dọc vẫn giữ nguyên, không làm sai biên độ giá.
- Khi có thao tác pan/zoom mới từ người dùng, chuyển sang `Manual View` ngay; không tự suy luận trở lại `Follow Latest` chỉ vì vùng xem còn gần mép phải. Chỉ nút **Về nến mới nhất** bật lại Follow.
- Replay chạy bằng đồng hồ có phần giây lẻ và scheduler 500 ms. Mỗi chu kỳ đọc phần tick mới trong DuckDB, rồi đưa vào replay mọi bản ghi có `timestamp <= simulated_time` theo thứ tự thời gian. Biểu đồ chỉ dựng lại khi có tick mới đến thời điểm replay, không đợi 3 giây.
- Cache không cắt đuôi 500.000 dòng khi đang chạy, tránh dịch chỉ số cursor do xóa các dòng cũ trong khi replay.
- Y-axis dùng dữ liệu high/low thật của OHLC và tự scale theo dữ liệu; không dùng viewport X để tính chiều cao nến.
- Đây vẫn là đọc tăng dần từ DuckDB. Muốn có tick thị trường trực tiếp, một tiến trình KBS riêng vẫn cần ghi tick mới vào DuckDB.


## Hotfix chống trạng thái Updating kéo dài

- Replay kiểm tra DuckDB theo chu kỳ 500 ms (không phải 3 giây). Mỗi nhịp dùng `timestamp` để lấy **toàn bộ** tick có thời gian đến hạn; chu kỳ kiểm tra chỉ quyết định độ trễ hiển thị tối đa, không giới hạn số bản ghi được xử lý.
- OHLCV được cập nhật tăng dần từ những tick mới vừa đến hạn. Không resample lại toàn bộ hàng trăm nghìn tick ở mỗi nhịp RUN.
- Bộ đệm `Datetime` dùng trực tiếp `Series.searchsorted()` để tìm cursor theo timestamp, tránh tạo lại `DatetimeIndex` 500.000 dòng ở mỗi callback.
- Gộp tick mới dùng `searchsorted()` để tìm đoạn timestamp trùng ở cuối cache, tránh quét toàn bộ dữ liệu cũ để khử trùng lặp.
- Khi không có tick mới đủ điều kiện, figure không được dựng lại; khi có tick mới, nến hiện tại được cập nhật OHLCV từ đúng các bản ghi mới.
- Nến dùng `whiskerwidth=0`, trục giá lấy High/Low thật trong vùng đang xem, và trạng thái pan/zoom tiếp tục tách khỏi callback replay để tránh tự nhảy về mép phải.


## Hotfix V8 — giữ khung nhìn khi RUN
- Callback replay đọc trực tiếp `price-chart.relayoutData` cùng với `viewport-state`.
- Khi ở Manual View, phạm vi X mới nhất từ trình duyệt được ưu tiên hơn Store riêng, tránh callback cập nhật Store chậm hơn vòng replay.
- Mỗi lần thay Figure do có tick mới sẽ dùng phạm vi X đã ghi nhận, thay vì để Plotly tự động chuyển về cây nến cuối.
- Nút “Về nến mới nhất” vẫn là thao tác chủ động để chuyển sang Follow Latest.


## Hotfix V9 — giữ Manual View khi đổi timeframe
- Khi đổi 1m/5m/15m trong lúc RUN, giữ nguyên chế độ Manual/Follow đang dùng.
- Không tái sử dụng chỉ số X dạng ordinal của timeframe cũ; tạo phạm vi X mới theo số nến của timeframe mới.
- Bỏ qua đúng một `relayoutData` cũ sau khi đổi timeframe để tránh lấy nhầm phạm vi từ biểu đồ trước.
- Trạng thái Follow Latest lấy từ `replay-state`; callback viewport riêng không được ghi đè nhầm trạng thái RUN.


## Hotfix V10 — đường giá hiện tại và cấu hình số tick
- Đường giá đóng cửa của nến mới nhất rõ hơn (màu xanh ngọc sáng, nét đứt dày hơn), kèm nhãn giá ở mép phải vùng giá.
- Giới hạn tick khởi động cấu hình bằng `TICK_LOAD_LIMIT` trong `config.py` (mặc định `500000`).
- Đặt `TICK_LOAD_LIMIT = 0` để tải toàn bộ tick; lưu ý có thể tiêu tốn nhiều RAM và thời gian khởi động.
- Có thể ghi đè bằng biến môi trường `TICK_LOAD_LIMIT` nếu cần.


## Hotfix V11 — công cụ vẽ xu hướng
- Bật Plotly mode bar trên biểu đồ VN30F1M, thêm công cụ `Draw line` để vẽ đường xu hướng và `Erase shape` để xóa đường đã vẽ. Có thể kéo chỉnh vị trí đường đã vẽ.
- Đường giá hiện tại nhạt hơn, mảnh hơn và dùng nét chấm nhỏ; nhãn giá bên phải vẫn được giữ.
- Các chức năng RUN, timeframe và cấu hình `TICK_LOAD_LIMIT` được giữ nguyên.

## V12 — Công cụ vẽ line trên biểu đồ
- Thanh công cụ có lựa chọn kiểu đường (liền/đứt/chấm/gạch-chấm), màu và độ dày 1–5 px. Có thể chọn trước khi vẽ; khi chọn một line đã vẽ, thay đổi các tùy chọn sẽ áp dụng cho line đó.
- Nhấn **Vẽ line**, sau đó kéo từ điểm đầu đến điểm cuối trên vùng giá. Nhấn **Esc** để thoát chế độ vẽ.
- Nhấp gần một line để chọn; nhấn **Delete** hoặc nút **Xóa line** để xóa.
- Các line được lưu trong `localStorage` của trình duyệt theo thời gian thực (timestamp) và mức giá, thay vì chỉ theo chỉ số nến. Vì vậy chúng được quy chiếu lại khi đổi khung 1m/5m/15m... và vẫn còn sau khi tải lại trang trên cùng trình duyệt. Nếu thời điểm đầu/cuối nằm ngoài cửa sổ lịch sử đang hiển thị, line tạm ẩn thay vì bị dồn về mép biểu đồ.
- Đây là lưu trữ cục bộ của trình duyệt/máy hiện tại; xóa dữ liệu trang hoặc dùng trình duyệt khác sẽ không có các line đã lưu.
- Đã kiểm tra cú pháp Python/JavaScript và tính toàn vẹn gói ZIP; cần kiểm thử thao tác vẽ/xóa trực tiếp trên trình duyệt Windows với dữ liệu DuckDB thực tế.


## V12 Line Tools Hotfix 3
- Vẽ line bằng hai lần nhấp chuột: chọn điểm thứ nhất rồi chọn điểm thứ hai; không cần giữ và kéo chuột. Nhấn Esc để hủy thao tác đang chờ.
- Nhấp vào line để chọn; các điều khiển màu, kiểu nét và độ dày được nạp theo line đang chọn. Thay đổi điều khiển sẽ cập nhật line đã chọn. Dùng Delete/Backspace hoặc nút Xóa line để xóa.
- Line được lưu theo timestamp và giá trong localStorage. Khi đổi timeframe hoặc figure được dựng lại, các line được chiếu lại theo timestamp; nếu endpoint nằm ngoài cửa sổ dữ liệu đang tải, vị trí X được ngoại suy theo khoảng nến điển hình để line không bị loại khỏi bộ lưu.


## V13 — Quản lý lệnh và vị thế mô phỏng
- Chọn **AUTO** để bật chế độ **MAK**; nhấn LONG/SHORT mở hộp xác nhận với giá replay hiện tại, xác nhận thì khớp ngay. Tắt AUTO để đặt lệnh giới hạn: nhập giá, chọn LONG/SHORT, lệnh xuất hiện trong sổ lệnh chờ khớp.
- Lệnh chờ khớp được khớp theo tick replay: LONG khi giá thị trường chạm/đi xuống dưới giá đặt; SHORT khi giá chạm/đi lên trên giá đặt. Chuyển timeframe không reset sổ lệnh hoặc vị thế.
- Các lệnh chờ có nút Sửa/Hủy. Lệnh đã khớp/hủy được giữ trong sổ để xem lịch sử. Khối lượng phải là số nguyên dương; nếu trống/sai, ứng dụng hiển thị hộp thoại nhắc nhập.
- Vị thế được netting: khớp cùng chiều tăng vị thế và tính giá vốn bình quân; khớp ngược chiều đóng vị thế hiện tại, nếu khối lượng vượt vị thế hiện tại thì phần dư mở vị thế ngược chiều. Lãi/lỗ thực hiện dùng `POINT_VALUE_VND` làm hệ số giá trị điểm.
- Phí mô phỏng là `FEE_PER_CONTRACT_VND` cho mỗi hợp đồng khớp ở cả chiều vào/ra; tài sản ròng = tài sản ban đầu + lãi/lỗ đã thực hiện - phí. Tiền có thể rút theo yêu cầu hiển thị bằng tổng lãi/lỗ ròng.
- Giới hạn ký quỹ dựa trên tài sản ròng và `MARGIN_PER_CONTRACT_VND`; các giá trị được cấu hình trong `config.py` hoặc biến môi trường. Mặc định: tài sản ban đầu 100.000.000 ₫, ký quỹ 9.000.000 ₫/HĐ, phí 70.000 ₫/HĐ/lần khớp, hệ số điểm 100.000 ₫/điểm, mã đặt lệnh VN30FM1.
- Trạng thái lệnh/vị thế/chi phí được giữ trong `dcc.Store` kiểu session để không mất khi đổi timeframe trong phiên trình duyệt. Đây là công cụ paper-trading/backtest, không gửi lệnh thật và chưa thay thế quy tắc phí/ký quỹ chính thức của công ty chứng khoán.

## V14 – Position close/reverse and withdrawable cash

- Withdrawable cash follows the requested formula: net assets − total P/L − fees.
- Added an open-position summary showing LONG/SHORT, quantity, entry price, and mark-to-market unrealized P/L (green for LONG/positive, red for SHORT/negative).
- Added Close and Reverse actions. Each opens a modal for a trigger price and creates a pending simulated order; the action is processed when replay ticks reach the order's limit condition.
- Limit order price remains the user-entered fixed price. MAK uses the current replay price when the user confirms the market-order modal.
- Reverse action places twice the current position quantity in the opposite direction, so the existing position is closed and the same quantity opens in the opposite direction if fully filled.

## V14 Hotfix 1 — xử lý giá lệnh và AUTO/MAK
- Lệnh LONG có giá đặt >= giá replay hiện tại sẽ khớp ngay tại giá replay hiện tại.
- Bổ sung đối xứng cho SHORT: giá đặt <= giá replay hiện tại sẽ khớp tại giá replay hiện tại.
- Bật chế độ AUTO/MAK hoặc chọn loại lệnh MAK sẽ xóa ô giá; lệnh thị trường lấy giá replay hiện tại khi xác nhận.
- Chọn ATO/ATC/MTL/MOK sẽ trở lại chế độ nhập giá giới hạn và giữ nguyên giá hiện có.


## Reset Back-Test
Dùng nút **↺ Reset Back-Test** trên thanh Back-Test để xóa danh sách lệnh, lệnh chờ, vị thế đang mở, P/L đã thực hiện và phí; tài sản được khôi phục về `INITIAL_NET_ASSET_VND` trong `config.py`. Thao tác này không xóa tick trong DuckDB hoặc các đường line được lưu trong localStorage của trình duyệt.


## V14 Hotfix 2 — RUN viewport và P/L runtime
- Ưu tiên viewport đã lưu khi RUN đang chạy, tránh relayoutData cũ kéo biểu đồ về nến mới nhất.
- Giữ vùng xem thủ công khi RUN bắt đầu; Follow Latest chỉ theo dõi khi được chọn chủ động.
- Tổng lãi/lỗ hiển thị theo P/L đã thực hiện + P/L chưa chốt - phí; P/L chưa chốt dùng giá tick replay hiện tại.


### UI hotfix — assets and inline position layout
- Removed automatic bottom-pushing of the Assets panel so it appears directly below the Dư mua/Dư bán summary.
- Changed the quantity field layout to a vertical full-width layout so the inline position block and quantity validation no longer fall into the narrow label grid column or become clipped.

## V45 — Preload Once + In-Memory Batch Replay
- Dữ liệu tick back-test được nạp vào `_TICKS_CACHE` một lần và không còn truy vấn `load_ticks_since()` trong lúc RUN. Muốn dùng bộ dữ liệu mới sau khi DB thay đổi, hãy khởi động lại ứng dụng.
- Mỗi nhịp replay xử lý tối đa `REPLAY_BATCH_TICKS` (mặc định 10.000) tick từ RAM; nếu đồng hồ mô phỏng đi trước cursor, các nhịp kế tiếp xử lý tiếp phần backlog, không bỏ qua tick.
- Biểu đồ được gửi lại độc lập: khi có nến mới hoặc đã quá `CHART_REFRESH_SECONDS` (mặc định 1,25 giây). Các cập nhật replay-state vẫn tiếp tục để engine lệnh/P&L xử lý từng tick đã phát.
- Hai thông số có thể cấu hình trong `.env`: `REPLAY_BATCH_TICKS` và `CHART_REFRESH_SECONDS`. Batch nhỏ hơn giúp STOP phản hồi nhanh hơn; batch lớn hơn tăng thông lượng.
- Giữ nguyên logic timestamp replay, lệnh chờ, khớp lệnh, vị thế, phí/P&L, reset tài khoản, line drawing và xử lý viewport.
- STOP vẫn được xử lý qua callback Dash; mỗi lượt bị giới hạn batch để tránh một callback quét hàng triệu tick. Đây chưa phải background worker riêng; nếu CPU/figure nặng vẫn gây chậm, bước tiếp theo là tách replay engine thành worker có cờ dừng độc lập.


## V46 — Tốc độ Back-Test 2× / 5× / 15× / 30×
- Thêm bốn nút tốc độ cạnh STOP; nút đang chọn được tô xanh. Tốc độ mặc định 1× cho đến khi chọn một mức mới.
- Tốc độ thay đổi đồng hồ mô phỏng, không bỏ qua tick: mọi tick có timestamp đến hạn vẫn được xử lý tuần tự qua các batch `REPLAY_BATCH_TICKS`. Nếu tốc độ mô phỏng đi trước bộ xử lý, replay bắt kịp qua các lượt tiếp theo.
- Khi đổi tốc độ trong lúc RUN, mốc đồng hồ được neo lại theo thời gian mô phỏng hiện tại để tránh nhảy giờ.
- Thanh replay được làm gọn bằng cách giới hạn chiều rộng dropdown giờ/phút/giây và cho trạng thái sử dụng phần không gian còn lại.
- Các callback lệnh, vị thế, tài sản, line và timeframe được giữ nguyên.


## V46 Hotfix 1 — tốc độ 1×
- Thêm nút 1× vào nhóm tốc độ replay; chọn 1× để chạy theo thời gian thực.
- Các tốc độ 2×, 5×, 15×, 30× giữ nguyên.


## V46 Hotfix 2 — timeframe switch during RUN
- Synchronized `last_chart_update_wall` to `time.monotonic()` everywhere; fixes the mixed-clock bug that could suppress periodic candle refreshes after a timeframe switch.
- On timeframe changes, old `viewport-state` and `relayoutData` X ranges are ignored because they use ordinal candle indices from the previous timeframe.
- The chart layout `uirevision` is now timeframe-specific, forcing Plotly to reset incompatible axis/layout state on timeframe changes while preserving state within the same timeframe.
- Replay batch processing, preload cache, speed controls (1x/2x/5x/15x/30x), order matching, P/L, and line-drawing JavaScript are otherwise unchanged.


## V46 Hotfix 3 — atomic timeframe switch
- Detect timeframe changes by comparing `replay-state.timeframe` with the currently selected timeframe, even if Dash reports `replay-interval` or another Input as the primary trigger.
- Rebuild candle aggregation and reset the ordinal X viewport before the normal replay-interval path can append ticks to a cache built for a different timeframe.
- Keep the already processed replay cursor during the switch rather than jumping to wall-clock `sim_now`; this prevents skipping ticks/fills when a fast replay has a processing backlog.
- Preserve the existing speed, order, P/L, preload, and line-drawing logic.


## V46 Hotfix 4 — timeframe switch while RUN is active
- The timeframe transition branch now also triggers when the selected timeframe differs from the timeframe stored in replay state, even if the overlapping Dash request is reported as a replay interval.
- During a switch, rebuild candles only through the last *processed* tick cursor. Do not seek to the wall-clock replay time, which can be ahead of the batch processor and skip ticks.
- Re-anchor the new timeframe's ordinal X range around the rebuilt candle set. Preserve the running state, speed anchors, processed cursor, order/position/account state, and line data.
- Existing preload, replay batching, speed controls, order matching, P/L, and drawing behavior are otherwise unchanged.


## V46 Hotfix 5 — fast timeframe switch at 15x/30x
- Timeframe changes no longer aggregate every tick from the original replay start. They rebuild the new timeframe from a bounded recent display window around the last processed cursor, using `chart_window_duration(tf)`.
- Preserve `replay_idx` (the original replay anchor) and `cursor` (the last processed tick) separately. The switch never advances the processing cursor to wall-clock simulated time.
- This targets the long blocking aggregation observed when switching timeframes at 30x. Tick order, replay batching, order matching, P/L/account state, speed anchors, and line storage remain unchanged.


## V46 Hotfix 5 — fast timeframe switch at 15x/30x
- Rebuild the new timeframe from a bounded recent display window around the last processed cursor, not from every tick since the original replay start.
- Preserve `replay_idx` (original replay anchor) and `cursor` (last processed tick) separately; never advance the processing cursor to wall-clock simulated time during a switch.
- This reduces blocking aggregation when switching timeframe at high speed. Replay batching, order matching, P/L/account state, speed controls, and line storage remain unchanged.


## V46 Hotfix 7 — RUN timeframe-switch race/performance

- Candle cache is isolated by replay session **and timeframe**, so an interval request already in flight for the old timeframe cannot overwrite the new timeframe's OHLCV cache.
- Chart figures are sent through a timeframe-tagged payload. A small clientside guard rejects late responses whose timeframe no longer matches the selected timeframe.
- Tick-to-candle append is vectorized with pandas resampling instead of iterating over every tick in Python.
- Replay cursor and selected timeframe logic are preserved; no tick is skipped by this patch.

Validation: Python syntax compilation and ZIP integrity checks. This environment does not have the user's Windows DuckDB database or browser session, so end-to-end latency still needs to be checked on that machine.

## V46 Hotfix 8 — atomic replay response commit
- The replay callback no longer writes the chart, replay state, interval enabled flag, status, and control disabled flags as independent server outputs.
- Server responses are delivered as one candidate result. A single clientside gate commits the chart and replay lifecycle outputs together only when the response still matches the selected timeframe and current replay session/cursor.
- Late interval responses cannot resurrect a stopped run, regress the replay cursor, restore an old speed anchor, or disable the interval after a newer RUN response.
- This targets the failure where timeframe switching during RUN caused both chart updates and tick progression to stop. Static checks only; verify with the user's Windows/DuckDB workload.

## V46 Hotfix 10 — Chuyển timeframe bất đồng bộ và cache nến
- Khi RUN đang hoạt động, thao tác đổi timeframe được xác nhận ngay; vùng trạng thái riêng cạnh bộ chọn timeframe hiển thị `Đang chuyển khung thời gian sang ...` và dùng `aria-live` để trình duyệt thông báo trạng thái.
- Nhịp replay được khóa trong khi worker nền tổng hợp nến và dựng Plotly Figure. Bộ chọn timeframe tạm khóa trong thời gian chuyển đổi để tránh xếp chồng nhiều yêu cầu nặng.
- Một `dcc.Interval` riêng kiểm tra kết quả chuyển đổi mỗi 200 ms; giao diện không phải chờ một callback đồng bộ dài mới có thể hiển thị trạng thái.
- Tạo cache nến lịch sử theo timeframe ở worker nền sau khi nạp tick. Khi cache sẵn sàng, chuyển khung lấy các nến đã đóng từ cache và chỉ tổng hợp lại nến đang mở đến đúng con trỏ replay, tránh rò rỉ dữ liệu tương lai vào back-test.
- Nếu cache chưa sẵn sàng hoặc lỗi, dùng nhánh tổng hợp cửa sổ hiển thị làm dự phòng. Việc giữ con trỏ tick, mốc đồng hồ mô phỏng và trạng thái giao dịch vẫn theo luồng chuyển khung hiện có.
- Đã kiểm tra cú pháp Python, cú pháp JavaScript callback và thử đối chiếu logic tổng hợp nến cache với cách resample trực tiếp trên dữ liệu tổng hợp nhỏ. Chưa kiểm thử tích hợp Dash + DuckDB trên Windows thực tế.
