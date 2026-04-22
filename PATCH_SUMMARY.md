# Tóm tắt chỉnh sửa

## app.py
- Thêm đăng nhập bằng Flask session ở đường dẫn `/login` và `/logout`.
- Thêm phân quyền theo `regions` cho từng user.
- Khóa dữ liệu ở lõi lọc dữ liệu để user khu vực không xem được khu vực khác.
- Khóa luôn danh sách khu vực trong dropdown/filter theo phạm vi user.
- Khóa cả AI chat để không trả lời vùng ngoài quyền.
- Thêm route `/healthz` để Render health check.
- Giữ nguyên cấu trúc Dash chính, chỉ bọc thêm lớp auth + scope dữ liệu.

## refresh_data.py
- Thêm validate biến môi trường.
- Thêm mặc định START_DATE / END_DATE an toàn hơn.
- Cho phép cấu hình driver ODBC và file output bằng biến môi trường.
- Giữ nguyên logic lấy SQL -> tổng hợp -> ghi Excel.
