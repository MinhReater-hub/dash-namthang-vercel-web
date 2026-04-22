# Bộ file Dash đã nâng cấp sẵn

Bộ này đã được vá trực tiếp từ 2 file bạn gửi:
- `app.py`: thêm đăng nhập + phân quyền theo khu vực.
- `refresh_data.py`: giữ logic SQL -> Excel nhưng thêm cấu hình an toàn hơn.

## 1) Tài khoản đã hỗ trợ

Cấu trúc user nằm trong `users.json`:

```json
{
  "tong": {
    "password": "Tong@123456",
    "role": "admin",
    "regions": ["*"]
  },
  "cantho": {
    "password": "CanTho@123456",
    "role": "region",
    "regions": ["Cần Thơ"]
  }
}
```

Ý nghĩa:
- `regions: ["*"]` = xem toàn bộ dữ liệu.
- `regions: ["Cần Thơ"]` = chỉ xem dữ liệu Cần Thơ.
- Có thể gán nhiều khu vực cho 1 user.

## 2) Chạy local trước khi đưa lên online

### Bước 1
Tạo file `.env` từ `.env.example` rồi điền thông tin SQL Server.

Khi test local, để `SESSION_COOKIE_SECURE=false`. Khi deploy Render, đổi lại thành `true`.

### Bước 2
Chỉnh `users.json` đúng tài khoản thực tế.

### Bước 3
Cài thư viện:

```bash
pip install -r requirements.txt
```

### Bước 4
Chạy tạo dữ liệu Excel:

```bash
python refresh_data.py
```

### Bước 5
Chạy Dash:

```bash
python app.py
```

Mở trình duyệt tại:

```text
http://127.0.0.1:8050
```

## 3) Cách deploy online dễ nhất: Render + Docker

Với project này, cách ổn định nhất là dùng **Docker trên Render**, vì `refresh_data.py` đang dùng `pyodbc` để kết nối SQL Server và Linux cần cài ODBC Driver của Microsoft.

### Chuẩn bị
1. Tạo 1 repo GitHub.
2. Đẩy toàn bộ bộ file này lên GitHub.
3. Vào Render -> New -> Web Service.
4. Chọn repo GitHub của bạn.
5. Ở phần Language, chọn **Docker**.

### Thiết lập trên Render
- Health Check Path: `/healthz`
- Environment Variables: nhập các biến trong `.env.example`
- Nếu muốn dùng domain riêng, thêm ở phần Custom Domains.

### App sẽ chạy như thế nào
File `start.sh` đang làm 2 việc:
1. `python refresh_data.py`
2. `gunicorn ... wsgi:app`

Nghĩa là mỗi lần service khởi động:
- app sẽ lấy dữ liệu SQL,
- ghi file Excel,
- rồi mở Dash online.

## 4) Nếu muốn dữ liệu không mất sau khi redeploy

Render mặc định dùng filesystem tạm. Có 2 hướng:
- **Hướng A:** cứ để `refresh_data.py` chạy mỗi lần service start.
- **Hướng B:** gắn Persistent Disk trên Render nếu bạn muốn giữ file dưới thư mục `output/` qua các lần restart/redeploy.

## 5) Những gì đã được khóa quyền trong app

Không chỉ là ẩn menu. Hệ thống hiện khóa ở cả 4 lớp:
1. Chặn truy cập nếu chưa login.
2. Dropdown khu vực chỉ hiện khu vực user được phép xem.
3. Dữ liệu KPI / biểu đồ / bảng đều bị scope theo quyền user.
4. AI chat cũng không trả lời dữ liệu ngoài quyền của user.

## 6) Tạo thêm user khu vực

Ví dụ user chỉ xem Sóc Trăng:

```json
"soctrang": {
  "password": "SocTrang@123456",
  "role": "region",
  "regions": ["Sóc Trăng"],
  "display_name": "Quản lý Sóc Trăng"
}
```

Ví dụ user xem nhiều khu vực:

```json
"cum_mientay": {
  "password": "CumMienTay@123456",
  "role": "region",
  "regions": ["Cần Thơ", "Hậu Giang", "Sóc Trăng"],
  "display_name": "Cụm Miền Tây"
}
```

## 7) Đổi mật khẩu mặc định

Bắt buộc đổi các mật khẩu mẫu trong `users.json` trước khi public internet.

## 8) Lệnh chạy production nếu bạn tự host server Linux

```bash
python refresh_data.py
gunicorn --bind 0.0.0.0:10000 wsgi:app
```

## 9) Gợi ý triển khai thực tế cho bạn

Nếu mục tiêu là nhanh nhất để có link online:
1. Chạy local test trước.
2. Đưa bộ file này lên GitHub.
3. Deploy Render bằng Docker.
4. Nhập biến môi trường SQL.
5. Đăng nhập bằng tài khoản tổng trước để kiểm tra.
6. Sau đó tạo các user khu vực thật.
