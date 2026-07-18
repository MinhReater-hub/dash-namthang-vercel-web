"""Convert legacy output/cache/*.pkl files to verified gzip pickle caches."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


ALIASES = {
    "DiemTiepThi_KV_Thang": "KinhDoanh_DiemTiepThi_KV_Thang",
    "BienBan_KV_Thang": "KinhDoanh_BienBan_KV_Thang",
    "Driver_Options": "Daily_Driver_Options",
    "XeTrucThuoc_KV_Thang": "PhuongTien_XeTrucThuoc_KV_Thang",
    "XePhanQuyen_KV_Thang": "PhuongTien_XePhanQuyen_KV_Thang",
    "XeDangCo_XeTrucThuoc_KV_Ngay": "PhuongTien_XeTrucThuoc_KV_Ngay",
    "XeDangCo_XePhanQuyen_KV_Ngay": "PhuongTien_XePhanQuyen_KV_Ngay",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_exact_duplicate_alias(path: Path, cache_dir: Path) -> bool:
    canonical = ALIASES.get(path.stem)
    if not canonical:
        return False
    canonical_path = cache_dir / f"{canonical}.pkl"
    return canonical_path.is_file() and path.stat().st_size == canonical_path.stat().st_size and _sha256(path) == _sha256(canonical_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nén và kiểm tra cache pickle của dashboard.")
    parser.add_argument("--cache-dir", default="output/cache", help="Thư mục cache.")
    parser.add_argument("--remove-raw", action="store_true", help="Xóa .pkl sau khi kiểm tra thành công.")
    parser.add_argument("--force", action="store_true", help="Ghi đè .pkl.gz đã có.")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir).resolve()
    if not cache_dir.is_dir() or cache_dir.name != "cache":
        raise ValueError(f"Đường dẫn cache không hợp lệ: {cache_dir}")

    raw_files = sorted(cache_dir.glob("*.pkl"))
    if not raw_files:
        print("Không tìm thấy cache .pkl cần chuyển đổi.")
        return 0

    converted = 0
    skipped_aliases = 0
    raw_bytes = 0
    compressed_bytes = 0
    for source in raw_files:
        if _is_exact_duplicate_alias(source, cache_dir):
            skipped_aliases += 1
            print(f"Bỏ qua alias trùng dữ liệu: {source.name}")
            continue

        target = cache_dir / f"{source.stem}.pkl.gz"
        if target.exists() and not args.force:
            print(f"Đã tồn tại, bỏ qua: {target.name}")
            continue
        temp_target = cache_dir / f".{source.stem}.pkl.gz.tmp"
        frame = pd.read_pickle(source)
        frame.to_pickle(
            temp_target,
            compression={"method": "gzip", "compresslevel": 1, "mtime": 0},
        )
        verified = pd.read_pickle(temp_target, compression="gzip")
        if isinstance(frame, pd.DataFrame) and isinstance(verified, pd.DataFrame):
            pd.testing.assert_frame_equal(frame, verified, check_exact=True)
        elif not frame.equals(verified):
            raise ValueError(f"Cache sau nén không tương đương: {source.name}")
        temp_target.replace(target)

        raw_bytes += source.stat().st_size
        compressed_bytes += target.stat().st_size
        converted += 1
        print(f"OK {source.name} -> {target.name}")
        if args.remove_raw:
            source.unlink()

    saved = raw_bytes - compressed_bytes
    print(
        f"Hoàn tất: {converted} file, bỏ qua {skipped_aliases} alias trùng; "
        f"giảm {saved / (1024 ** 2):.2f} MiB trên các file đã chuyển đổi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
