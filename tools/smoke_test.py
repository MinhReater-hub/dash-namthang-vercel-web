"""Local, read-only smoke test for the upgraded dashboard package."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd


REQUIRED_CACHES = [
    "DoanhThu_Thang_KhuVuc.pkl.gz",
    "DoanhThu_LH_KV_Thang.pkl.gz",
    "HopDong_KV_Thang.pkl.gz",
    "DoanhThu_Ngay_Checker.pkl.gz",
    "DoanhThu_Ngay_TaiXe.pkl.gz",
    "Daily_Driver_Options.pkl.gz",
    "KinhDoanh_DiemTiepThi_KV_Thang.pkl.gz",
    "KinhDoanh_BienBan_KV_Thang.pkl.gz",
    "NhanSu_NhanVien_KV_Thang.pkl.gz",
    "NhanSu_TaiXe_KV_Thang.pkl.gz",
    "PhuongTien_XeTrucThuoc_KV_Ngay.pkl.gz",
    "PhuongTien_XePhanQuyen_KV_Ngay.pkl.gz",
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ["VERCEL"] = "0"
    os.environ["DASH_PRODUCTION"] = "0"
    os.environ.setdefault("DASH_LOG_BOOT_TIMING", "0")

    cache_root = root / "output" / "cache"
    checked_rows = 0
    for name in REQUIRED_CACHES:
        path = cache_root / name
        if not path.is_file() or path.stat().st_size <= 100:
            raise FileNotFoundError(f"Cache bắt buộc bị thiếu/rỗng: {path}")
        frame = pd.read_pickle(path, compression="gzip")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"Cache không phải DataFrame: {path}")
        checked_rows += len(frame)

    started = time.perf_counter()
    import app

    client = app.server.test_client()
    health = client.get("/healthz")
    login = client.get("/login")
    if health.status_code != 200 or health.get_data(as_text=True) != "ok":
        raise RuntimeError(f"Health check thất bại: HTTP {health.status_code}")
    if login.status_code != 200 or "Đăng nhập" not in login.get_data(as_text=True):
        raise RuntimeError(f"Trang đăng nhập thất bại: HTTP {login.status_code}")

    advanced_targets = [target for target in app.ZOOM_TARGETS if target.endswith("p1-advanced")]
    deepdive_targets = [target for target in app.ZOOM_TARGETS if target.endswith("p1-deepdive")]
    if len(advanced_targets) != len(app.DASH_PREFIXES):
        raise RuntimeError("Chưa đăng ký đủ biểu đồ nâng cao/zoom cho các menu.")
    if len(deepdive_targets) != len(app.DASH_PREFIXES):
        raise RuntimeError("Chưa đăng ký đủ biểu đồ chuyên sâu V2/zoom cho các menu.")
    for prefix in app.DASH_PREFIXES:
        filters = {"year": None if prefix in app.FLEET_MENU_PREFIXES else app.DEFAULT_YEAR, "months": []}
        figure, _rows, meta = app._build_p1_advanced_chart(prefix, filters, "light")
        if figure is None or not isinstance(meta, dict):
            raise RuntimeError(f"Không dựng được biểu đồ nâng cao cho menu {prefix}.")
        deep_figure, _deep_rows, deep_meta = app._build_p1_deepdive_chart(prefix, filters, "light")
        if deep_figure is None or not isinstance(deep_meta, dict):
            raise RuntimeError(f"Không dựng được biểu đồ chuyên sâu V2 cho menu {prefix}.")

    if app._repair_utf8_mojibake("TÃ i khoáº£n DEV") != "Tài khoản DEV":
        raise RuntimeError("Không sửa được mojibake tên tài khoản.")
    if app._normalize_region_list(["Ráº¡ch GiÃ¡"]) != ["Rạch Giá"]:
        raise RuntimeError("Không sửa được mojibake phạm vi khu vực.")

    print(
        f"SMOKE TEST OK | cache={len(REQUIRED_CACHES)} file/{checked_rows:,} dòng | "
        f"callback={len(app.dash_app.callback_map)} | advanced_chart={len(advanced_targets)} | "
        f"deepdive_chart={len(deepdive_targets)} | utf8_repair=ok | "
        f"elapsed={time.perf_counter() - started:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
