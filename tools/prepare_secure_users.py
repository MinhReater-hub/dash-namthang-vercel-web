"""Create a password-hashed user store for local use or DASH_USERS_JSON.

Examples:
  python tools/prepare_secure_users.py --rotate
  python tools/prepare_secure_users.py --input users.json --output users.secure.json --force

The script never prints passwords or the resulting JSON. Use --rotate after any
password file has been committed or shared publicly.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from werkzeug.security import generate_password_hash


def _read_store(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Tệp tài khoản phải là một JSON object không rỗng.")
    return payload


def _prompt_new_password(username: str) -> str:
    while True:
        password = getpass.getpass(f"Mật khẩu MỚI cho {username} (ít nhất 12 ký tự): ")
        if len(password) < 12:
            print("Mật khẩu quá ngắn. Vui lòng nhập lại.")
            continue
        confirm = getpass.getpass(f"Nhập lại mật khẩu cho {username}: ")
        if password != confirm:
            print("Hai lần nhập không khớp. Vui lòng nhập lại.")
            continue
        return password


def _secure_store(store: dict, rotate: bool) -> tuple[dict, int, int]:
    secured: dict = {}
    rotated = 0
    reused = 0
    for username, raw_record in store.items():
        if not isinstance(raw_record, dict):
            raise ValueError(f"Tài khoản {username!r} không phải JSON object.")
        record = dict(raw_record)
        existing_hash = str(record.get("password_hash") or "").strip()
        plain_password = record.pop("password", None)

        if rotate:
            record["password_hash"] = generate_password_hash(_prompt_new_password(str(username)))
            rotated += 1
        elif existing_hash:
            record["password_hash"] = existing_hash
        elif plain_password not in [None, ""]:
            record["password_hash"] = generate_password_hash(str(plain_password))
            reused += 1
        else:
            raise ValueError(f"Tài khoản {username!r} không có password hoặc password_hash.")

        record["is_active"] = bool(record.get("is_active", True))
        secured[str(username)] = record
    return secured, rotated, reused


def main() -> int:
    parser = argparse.ArgumentParser(description="Băm mật khẩu tài khoản dashboard bằng Werkzeug.")
    parser.add_argument("--input", default="users.json", help="Tệp JSON nguồn.")
    parser.add_argument("--output", default="users.secure.json", help="Tệp JSON bảo mật đầu ra.")
    parser.add_argument("--rotate", action="store_true", help="Nhập mật khẩu mới cho từng tài khoản.")
    parser.add_argument("--force", action="store_true", help="Cho phép ghi đè tệp đầu ra.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    if input_path == output_path:
        raise ValueError("Tệp đầu ra phải khác tệp nguồn.")
    if not input_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp nguồn: {input_path}")
    if output_path.exists() and not args.force:
        raise FileExistsError(f"Tệp đầu ra đã tồn tại: {output_path}. Dùng --force để ghi đè.")

    secured, rotated, reused = _secure_store(_read_store(input_path), rotate=bool(args.rotate))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(secured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass

    print(f"Đã tạo {output_path.name}: {len(secured)} tài khoản, xoay mới {rotated}, băm lại mật khẩu cũ {reused}.")
    if reused:
        print("CẢNH BÁO: mật khẩu cũ đã được băm nhưng chưa được thay đổi. Hãy chạy lại với --rotate trước khi deploy.")
    print("Không commit tệp đầu ra. Dùng nội dung tệp làm DASH_USERS_JSON trên Vercel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
