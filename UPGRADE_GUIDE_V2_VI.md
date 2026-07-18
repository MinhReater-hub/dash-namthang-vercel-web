# Hướng dẫn áp dụng Dashboard Nam Thắng V2

V2 được áp dụng trên repository đã merge V1. Gói không tự push GitHub hoặc deploy Vercel; bạn vẫn kiểm thử trên nhánh riêng trước khi merge vào `main`.

## 1. Nội dung V2

- Sửa tự động lỗi chữ kiểu `TÃ...` do JSON UTF-8 bị Windows PowerShell đọc theo ANSI.
- Sửa cả tên hiển thị và phạm vi khu vực, tránh tài khoản khu vực mất dữ liệu vì tên địa bàn bị lỗi mã hóa.
- Header responsive: tên tài khoản co gọn, badge/logo chuyển sang chế độ compact trên màn hình nhỏ.
- Banner trạng thái dữ liệu dùng toàn bộ chiều ngang.
- Tối ưu card, filter, bảng, modal, nút điều hướng và chiều cao biểu đồ cho tablet/mobile.
- Mỗi menu Trang 1 có thêm biểu đồ chuyên sâu thứ 6, tổng cộng 9 biểu đồ V2.
- Automation hằng ngày dừng an toàn nếu repository không đứng ở nhánh `main`.

## 2. Tạo nhánh thử nghiệm

Tại PowerShell:

```powershell
Set-Location C:\Projects\dash-namthang-fresh
git switch main
git pull --ff-only origin main
git status
git switch -c upgrade/dashboard-v2
```

Chỉ tiếp tục khi `git status` báo working tree sạch.

## 3. Chép file V2

Giải nén gói và chép toàn bộ nội dung bên trong vào:

```text
C:\Projects\dash-namthang-fresh
```

Chọn thay thế file trùng tên. V2 không chứa `.env`, `users.json`, `users.secure.json` hoặc cache dữ liệu.

## 4. Kiểm thử tự động

Có thể dùng lại môi trường `.venv` của V1:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\smoke_test.py
```

Kết quả đúng có các chỉ dấu:

```text
SMOKE TEST OK
advanced_chart=9
deepdive_chart=9
utf8_repair=ok
```

## 5. Chạy local và kiểm tra mobile

```powershell
$env:SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
$env:DASH_USERS_FILE = "users.secure.json"
$env:DASH_AUTH_STRICT = "1"
$env:DASH_AUTH_ALLOW_PLAINTEXT = "0"
$env:SESSION_COOKIE_SECURE = "0"
.\.venv\Scripts\python.exe app.py
```

Mở `http://127.0.0.1:8050`. Dùng Chrome/Edge DevTools (`F12` → Toggle device toolbar) để thử tối thiểu các chiều rộng 390 px, 430 px, 768 px và desktop.

Kiểm tra:

1. Tên tài khoản tiếng Việt hiển thị đúng.
2. Header không tràn ngang; trên điện thoại tên tài khoản/logo tự co gọn.
3. Banner trạng thái dữ liệu và nút tải Excel không chồng nhau.
4. Filter dùng được bằng thao tác chạm.
5. Card KPI và biểu đồ xếp một cột hợp lý trên mobile.
6. Bảng dữ liệu cuộn ngang được.
7. Mỗi menu Trang 1 có biểu đồ chuyên sâu thứ 6 và có thể phóng to.

## 6. Sửa tận gốc `DASH_USERS_JSON`

V2 tự phục hồi chuỗi mojibake đang có, nhưng vẫn nên ghi lại biến Vercel bằng JSON UTF-8 đúng. Lệnh quan trọng là có `-Encoding UTF8`:

```powershell
$usersJson = Get-Content .\users.secure.json -Raw -Encoding UTF8 |
    ConvertFrom-Json |
    ConvertTo-Json -Depth 10 -Compress
$usersJson | Set-Clipboard
```

Vào **Vercel → Project → Settings → Environment Variables**, sửa `DASH_USERS_JSON` cho cả Preview và Production bằng nội dung clipboard. Không đổi mật khẩu.

## 7. Kiểm tra automation hằng ngày

Trước khi chạy task:

```powershell
git branch --show-current
git status
```

Phải là `main` và working tree sạch. V2 bổ sung chốt chặn để task báo lỗi rõ ràng nếu ai đó để repository ở nhánh khác.

## 8. Commit và Preview

```powershell
git add app.py automation/update_dashboard_daily.ps1 tools/smoke_test.py
git add UPGRADE_GUIDE_V1_VI.md UPGRADE_GUIDE_V2_VI.md UPGRADE_REPORT_V2_VI.md
git diff --cached --check
git commit -m "Upgrade dashboard mobile UX and deep analytics V2"
git push -u origin upgrade/dashboard-v2
```

Chờ Vercel Preview đạt `Ready`, kiểm tra `/healthz`, đăng nhập, mobile và đủ 9 menu trước khi merge vào `main`.

