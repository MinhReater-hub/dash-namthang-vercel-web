# Hướng dẫn áp dụng gói nâng cấp Dashboard Nam Thắng V1

Gói này được thiết kế để bạn tự kiểm thử, tự commit và tự cập nhật GitHub/Vercel. Không có thao tác push hoặc deploy tự động trong gói.

## 1. Những file cần chép đè

Giữ nguyên cấu trúc thư mục và chép đè các file sau vào repository hiện tại:

- `app.py`
- `refresh_data.py`
- `build_dash_cache.py`
- `requirements.txt`
- `.env.example`, `.gitignore`, `.vercelignore`, `.dockerignore`
- `users.json.example`
- `automation/update_dashboard_daily.ps1`
- toàn bộ thư mục `tools/`
- toàn bộ file `output/cache/*.pkl.gz`

Không chép/commit `users.json`, `users.secure.json`, `.env`, `backup-cd/` hoặc `ngrok.exe`.

## 2. Sao lưu và tạo nhánh thử nghiệm

Tại thư mục repository trên Windows PowerShell:

```powershell
git status
git switch -c upgrade/dashboard-v1
```

Nếu `git status` đang có thay đổi thủ công chưa lưu, hãy sao lưu hoặc commit chúng trước. Không chép đè khi chưa biết rõ các thay đổi hiện tại.

Sau khi chép gói vào repository, kiểm tra:

```powershell
git status --short
git diff --check
```

## 3. Cài môi trường kiểm thử sạch

```powershell
py -3.12 -m venv .venv-test
.\.venv-test\Scripts\python.exe -m pip install --upgrade pip
.\.venv-test\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-test\Scripts\python.exe tools\smoke_test.py
```

Kết quả đúng phải có dòng `SMOKE TEST OK` và báo đủ 9 biểu đồ nâng cao.

Chạy giao diện local:

```powershell
.\.venv-test\Scripts\python.exe app.py
```

Mở `http://127.0.0.1:8050` và kiểm tra:

1. Đăng nhập được bằng tài khoản local.
2. KPI và số liệu chính khớp phiên bản hiện tại.
3. Bộ lọc năm, tháng, khu vực, loại hình, phòng ban, loại xe và số chỗ vẫn hoạt động.
4. Mỗi menu phân tích có thêm biểu đồ thứ 5 ở Trang 1.
5. Phóng to biểu đồ mới hoạt động.
6. Trang 2, bảng dữ liệu, tải dữ liệu và phân quyền khu vực vẫn hoạt động.

## 4. Chuyển cache sang định dạng nén

Gói đã kèm cache `.pkl.gz` tạo từ dữ liệu mới nhất trong repository và đã kiểm tra tương đương từng DataFrame. Nếu bạn muốn tự tạo lại từ `.pkl`:

```powershell
.\.venv-test\Scripts\python.exe tools\compress_existing_cache.py --force
```

Sau khi `smoke_test.py` thành công, sao lưu cache cũ rồi bỏ `.pkl` khỏi Git:

```powershell
New-Item -ItemType Directory -Force ..\cache-backup | Out-Null
Copy-Item .\output\cache\*.pkl ..\cache-backup\
git rm -- 'output/cache/*.pkl'
git add output/cache/*.pkl.gz
```

Automation hằng ngày đã được đổi sang xuất `pkl.gz`; không cần nén lại thủ công sau mỗi lần refresh.

## 5. Bắt buộc xử lý tài khoản trước khi deploy

Repository hiện từng chứa mật khẩu dạng rõ. Băm lại mật khẩu cũ không làm chúng an toàn vì mật khẩu đã lộ; phải đổi mật khẩu mới cho toàn bộ tài khoản.

Tạo tệp tài khoản mới bằng lời nhắc ẩn:

```powershell
.\.venv-test\Scripts\python.exe tools\prepare_secure_users.py --rotate
```

Kết quả là `users.secure.json`. File này đã được `.gitignore`; tuyệt đối không commit.

Tạo hai secret ngẫu nhiên riêng biệt:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Trước khi push code mới, vào **Vercel → Project → Settings → Environment Variables** và cấu hình cho Production/Preview:

| Biến | Giá trị |
|---|---|
| `SECRET_KEY` | Secret ngẫu nhiên thứ nhất |
| `DASH_WARM_TOKEN` | Secret ngẫu nhiên thứ hai |
| `DASH_AUTH_STRICT` | `1` |
| `DASH_AUTH_ALLOW_PLAINTEXT` | `0` |
| `SESSION_COOKIE_SECURE` | `1` |
| `DASH_WARM_REQUIRE_TOKEN` | `1` |
| `DASH_USERS_JSON` | JSON đã băm từ `users.secure.json` |

Để đưa JSON lên clipboard ở dạng một dòng:

```powershell
$users = Get-Content .\users.secure.json -Raw -Encoding UTF8 | ConvertFrom-Json
$users | ConvertTo-Json -Depth 10 -Compress | Set-Clipboard
```

Dán clipboard vào giá trị `DASH_USERS_JSON`, lưu biến rồi xóa clipboard nếu máy đang dùng chung.

Với automation local, thêm vào `.env`:

```text
DASH_CACHE_FORMATS=pkl.gz
DASH_USERS_FILE=users.secure.json
DASH_AUTH_ALLOW_PLAINTEXT=0
```

## 6. Gỡ file nhạy cảm khỏi commit mới

Sau khi đã xoay toàn bộ mật khẩu/secret:

```powershell
git rm --cached users.json
git rm --cached ngrok.exe
git rm -r --cached backup-cd
```

Các lệnh trên chỉ gỡ file khỏi commit mới; dữ liệu vẫn tồn tại trong lịch sử Git cũ. Vì repository công khai, cần tiếp tục:

- đổi mọi mật khẩu tài khoản dashboard cũ;
- đổi secret Flask, token ngrok/Telegram và thông tin SQL nếu từng xuất hiện trong file backup;
- lên kế hoạch làm sạch lịch sử bằng `git filter-repo` ở một đợt riêng, vì thao tác đó sẽ viết lại lịch sử và ảnh hưởng người đang clone repository.

## 7. Kiểm tra phần thay đổi trước khi commit

```powershell
git status --short
git diff --check
git diff --stat
git diff --cached --stat
```

Chỉ stage đúng các file đã kiểm tra. Không dùng `git add .` nếu chưa rà file nhạy cảm.

Ví dụ:

```powershell
git add app.py refresh_data.py build_dash_cache.py requirements.txt
git add .env.example .gitignore .vercelignore .dockerignore users.json.example
git add automation/update_dashboard_daily.ps1 tools UPGRADE_GUIDE_V1_VI.md UPGRADE_REPORT_V1_VI.md
git add output/cache/*.pkl.gz
git status --short
```

Sau khi tự xác nhận, bạn mới commit và push:

```powershell
git commit -m "Upgrade dashboard performance, security and executive charts"
git push -u origin upgrade/dashboard-v1
```

Nên mở Pull Request và xem Vercel Preview trước khi merge vào `main`.

## 8. Kiểm tra sau khi Vercel deploy

1. `/healthz` trả về `ok`.
2. Đăng nhập thử một tài khoản admin và ít nhất một tài khoản khu vực.
3. Tài khoản khu vực không nhìn thấy dữ liệu ngoài phạm vi.
4. Mở đủ Home, Daily và 9 menu phân tích; kiểm tra cả Trang 1/Trang 2.
5. So sánh KPI, tổng doanh thu, số cuốc và các bảng với bản đang chạy.
6. Kiểm tra log Vercel không còn lỗi kích thước function hoặc thiếu cache.
7. Dùng `/healthz` cho hệ thống giám sát công khai. `/_warm` yêu cầu token và không nên công khai URL có token.

Vercel hiện giới hạn bundle Python function ở 500 MB chưa nén; xem tài liệu chính thức tại <https://vercel.com/docs/functions/limitations>.

## 9. Hoàn tác

Nếu Preview hoặc Production có lỗi:

1. Không merge nhánh thử nghiệm, hoặc dùng `git revert` với commit nâng cấp.
2. Khôi phục deployment ổn định trước đó trong Vercel.
3. Không đưa lại mật khẩu rõ vào repository; giữ `SECRET_KEY` và `DASH_USERS_JSON` mới.
4. Gửi log build/runtime và ảnh màn hình lỗi để xử lý tiếp.
