# Báo cáo nâng cấp Dashboard Nam Thắng V2

Ngày kiểm thử: 18/07/2026

Base: `main` sau khi merge PR V1, commit `beb4c40`.

## Kết quả chính

| Hạng mục | V1 | V2 |
|---|---:|---:|
| Callback Dash | 83 | 92 |
| Biểu đồ nâng cao Trang 1 | 9 | 18 tổng cộng: 9 V1 + 9 V2 |
| Sửa lỗi JSON UTF-8/ANSI | Không | Có, áp dụng cho tên tài khoản và phạm vi khu vực |
| Header mobile | Co giãn cơ bản | Compact theo breakpoint, chống tràn tên/badge/logo |
| Banner trạng thái dữ liệu | 8/12 cột desktop | Toàn chiều ngang |
| Automation sai nhánh | Có thể commit nhầm nhánh hiện tại | Dừng an toàn nếu nhánh khác `main` |

## Biểu đồ chuyên sâu mới

- Doanh thu, Loại hình, Hợp đồng, Nhân viên, Tài xế, Điểm tiếp thị và Biên bản: biểu đồ động lượng theo tháng gồm giá trị thực tế, trung bình trượt 3 kỳ và tăng trưởng MoM.
- Xe trực thuộc và Xe phân quyền: ma trận bong bóng quy mô đội xe × độ đa dạng loại xe, có đường trung vị tạo bốn vùng quyết định.
- Mỗi biểu đồ dùng đúng DataFrame, filter và phạm vi tài khoản hiện có; không tạo dữ liệu giả.
- Callback chỉ dựng biểu đồ khi menu và Trang 1 tương ứng đang mở.

## Responsive/mobile

- Header dùng flex không xuống dòng, tiêu đề có ellipsis và action area compact.
- Ẩn tên tài khoản trên tablet; ẩn badge và chuyển wordmark sang `NTG` trên điện thoại nhỏ.
- Tăng kích thước vùng chạm, tối ưu card padding và chiều cao biểu đồ.
- Chip điều hành cuộn ngang thay vì ép tràn.
- Bảng Dash hỗ trợ cuộn ngang bằng thao tác chạm.
- Offcanvas, modal zoom, AI launcher và nút chuyển trang được giới hạn theo viewport.

## Sửa lỗi chữ trong ảnh người dùng

Nguyên nhân được tái hiện: Windows PowerShell 5.1 đọc `users.secure.json` UTF-8 không BOM theo ANSI khi lệnh `Get-Content` thiếu `-Encoding UTF8`. JSON sau đó vẫn hợp lệ nhưng tên tiếng Việt và khu vực đã thành mojibake trước khi dán lên Vercel.

V2 xử lý hai lớp:

1. Runtime tự sửa các chuỗi UTF-8 bị giải mã nhầm Windows-1252, chỉ chấp nhận kết quả khi điểm mojibake giảm.
2. Hướng dẫn tạo `DASH_USERS_JSON` đã thêm `Get-Content -Encoding UTF8` để sửa tận gốc biến môi trường.

## Kiểm thử đã chạy

- `py_compile` cho `app.py` và công cụ kiểm thử.
- `git diff --check` không có lỗi khoảng trắng.
- Smoke test 12 cache trọng yếu, 518.193 dòng.
- Dựng thành công 9 biểu đồ V1 và 9 biểu đồ V2 từ dữ liệu thật.
- Kiểm thử strict auth bằng JSON mojibake mô phỏng: sửa đúng display name, khu vực và đăng nhập hash thành công.
- Kết quả tổng hợp: `callback=92`, `advanced_chart=9`, `deepdive_chart=9`, `utf8_repair=ok`.

## Việc cần xác nhận trên thiết bị thật

- Kiểm tra trực quan ở Chrome/Edge desktop và ít nhất một điện thoại thật.
- So sánh số liệu biểu đồ V2 với bảng chi tiết theo filter nghiệp vụ.
- Xác nhận Vercel Preview và Production đều nhận `DASH_USERS_JSON` UTF-8 đúng.

