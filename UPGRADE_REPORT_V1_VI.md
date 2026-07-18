# Báo cáo nâng cấp Dashboard Nam Thắng V1

Ngày kiểm thử: 18/07/2026
Phạm vi: bản sao cục bộ của `MinhReater-hub/dash-namthang-vercel-web` tại commit `612a3a3`.

## Kết quả chính

| Hạng mục | Trước | Sau nâng cấp/kiểm thử |
|---|---:|---:|
| Cache pickle trong repository | 177,99 MiB | 26,35 MiB (`pkl.gz`) |
| Giảm kích thước cache | — | 151,64 MiB, khoảng 85% |
| Warm Daily trên bản kiểm thử | khoảng 1,39 giây | khoảng 0,18 giây |
| Callback Python cho Daily aggregation | hàng nghìn lời gọi theo group | built-in/vectorized, có fallback tương thích |
| Biểu đồ nâng cao bổ sung | 0 | 9 biểu đồ, mỗi menu Trang 1 thêm 1 |
| Dependency Vercel | không khóa phiên bản | khóa phiên bản đã smoke-test |
| Mật khẩu production | hỗ trợ plaintext mặc định | strict mode dùng `password_hash`, hỗ trợ `DASH_USERS_JSON` |

Số đo phụ thuộc máy và cold/warm state; dùng để so sánh cùng môi trường kiểm thử, không phải SLA production.

## Nâng cấp hiệu năng và triển khai

- Hỗ trợ đọc `.pkl.gz`, ưu tiên cache nén trước `.pkl` cũ.
- Giữ fallback đọc `.pkl`, Parquet và Feather để tương thích ngược.
- Đổi pipeline `refresh_data.py` và automation sang tạo gzip level 1.
- Không tạo các cache alias có nội dung trùng nhau.
- Loại khỏi Vercel bundle: Excel, raw pickle, `ngrok.exe`, backup, tài khoản và file công cụ local.
- Pin các phiên bản Dash, Plotly, pandas, NumPy, Flask, Werkzeug và Gunicorn đã kiểm thử.
- Tối ưu Daily aggregation: cache numeric/pre-aggregated dùng phép cộng vectorized; dữ liệu raw, khóa trùng hoặc định danh text vẫn chạy nhánh cũ khi cần.

## Nâng cấp giao diện và biểu đồ

Giữ nguyên cấu trúc menu, filter, KPI và hai tầng phân tích. Hàng cuối Trang 1 trước đây chỉ dùng nửa chiều ngang được lấp bằng biểu đồ nâng cao có zoom:

| Menu | Biểu đồ mới |
|---|---|
| Doanh thu | Pareto đóng góp khu vực + đường lũy kế 80% |
| Loại hình | Pareto doanh thu theo khu vực, bám filter loại hình/hình thức kinh doanh |
| Hợp đồng | Pareto số cuốc theo khu vực |
| Quản lý nhân viên | Heatmap tháng × khu vực |
| Quản lý tài xế | Heatmap tháng × khu vực |
| Điểm tiếp thị | Pareto chi phí theo khu vực |
| Biên bản | Heatmap khu vực × tháng cho số tiền chênh lệch/đã xử lý |
| Xe trực thuộc | Heatmap khu vực × loại xe |
| Xe phân quyền | Heatmap khu vực × loại xe |

Mọi biểu đồ mới dùng cùng nguồn DataFrame và cùng bộ lọc/phân quyền hiện có; không tạo số liệu giả.

## Nâng cấp bảo mật

- Production/Vercel mặc định bật `DASH_AUTH_STRICT`.
- Strict mode không chấp nhận mật khẩu rõ và không tạo `admin/admin123` dự phòng.
- Hỗ trợ user store qua biến `DASH_USERS_JSON` để không bundle file tài khoản.
- Bắt buộc `SECRET_KEY` mạnh khi chạy production.
- Cookie production mặc định `Secure`, `HttpOnly`, `SameSite=Lax`.
- Xóa session cũ trước khi tạo session đăng nhập mới.
- Thêm security headers cơ bản.
- Warm endpoint production yêu cầu token.
- Thêm công cụ tương tác để xoay và băm mật khẩu bằng Werkzeug.

Lưu ý: mã nguồn không thể tự thu hồi mật khẩu/secret đã lộ trong lịch sử Git. Chủ repository phải xoay credential và xử lý lịch sử ở bước riêng.

## Kiểm thử đã chạy

- `py_compile` cho `app.py`, pipeline cache và toàn bộ công cụ mới.
- `pip check`: không có dependency hỏng.
- Import local và mô phỏng Vercel strict mode.
- Flask smoke: `/healthz`, `/login`, `/`, `/_dash-layout`, `/_dash-dependencies`.
- Đăng nhập hash trong strict mode; xác nhận plaintext bị từ chối.
- Kiểm tra token của `/_warm`.
- Dựng đủ 9 biểu đồ nâng cao từ dữ liệu thật.
- So sánh DataFrame Daily trước/sau tối ưu bằng `assert_frame_equal(check_exact=True)`.
- Kiểm tra fallback với khóa trùng và định danh text.
- Đọc lại từng cache gzip sau khi ghi và so sánh chính xác với cache gốc.
- Smoke test tổng hợp: 12 cache trọng yếu, 518.193 dòng, 83 callback và 9 advanced chart.

## Những việc chủ repository cần tự xác nhận

- Kiểm thử trực quan trên màn hình desktop/mobile với tài khoản thật.
- So sánh KPI theo checklist nghiệp vụ.
- Cấu hình biến môi trường Vercel trước khi push.
- Xoay toàn bộ password/secret cũ.
- Xem Vercel Preview và log build trước khi merge.
- Chỉ sau khi đạt các bước trên mới cập nhật `main`.
