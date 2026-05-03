"""Build Dash sheet cache before deployment.

Usage:
  python build_dash_cache.py

Environment variables:
  DASH_EXCEL_FILE / OUTPUT_EXCEL_FILE: source workbook path
  DASH_CACHE_DIR: output cache directory, default output/cache
  DASH_CACHE_SHEETS: optional comma-separated sheet names to cache
  DASH_CACHE_FORMATS: comma-separated formats: parquet,feather,pkl (default: parquet,pkl)

The dashboard can read .parquet, .feather, and .pkl from DASH_CACHE_DIR.
This script is safe for Vercel build steps: if no workbook is found it exits 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd


def norm_text(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_")


def first_existing(candidates: list[str]) -> Path | None:
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw)
        if p.exists() and p.is_file():
            return p
    return None


def write_cache(df: pd.DataFrame, out_base: Path, formats: set[str]) -> dict:
    written: dict[str, str] = {}
    out_base.parent.mkdir(parents=True, exist_ok=True)

    if "parquet" in formats:
        try:
            fp = out_base.with_suffix(".parquet")
            df.to_parquet(fp, index=False)
            written["parquet"] = str(fp)
        except Exception as exc:
            written["parquet_error"] = str(exc)

    if "feather" in formats:
        try:
            fp = out_base.with_suffix(".feather")
            df.reset_index(drop=True).to_feather(fp)
            written["feather"] = str(fp)
        except Exception as exc:
            written["feather_error"] = str(exc)

    if "pkl" in formats:
        try:
            fp = out_base.with_suffix(".pkl")
            df.to_pickle(fp)
            written["pkl"] = str(fp)
        except Exception as exc:
            written["pkl_error"] = str(exc)

    return written


def main() -> int:
    started = time.perf_counter()
    excel_file = first_existing([
        os.getenv("DASH_EXCEL_FILE", ""),
        os.getenv("OUTPUT_EXCEL_FILE", ""),
        "output/bao_cao_doanh_thu_tong_hop.xlsx",
        "bao_cao_doanh_thu_tong_hop.xlsx",
        "data/bao_cao_doanh_thu_tong_hop.xlsx",
        "/mnt/data/bao_cao_doanh_thu_tong_hop.xlsx",
    ])
    cache_dir = Path(os.getenv("DASH_CACHE_DIR", "output/cache"))
    formats = {x.strip().lower() for x in os.getenv("DASH_CACHE_FORMATS", "parquet,pkl").split(",") if x.strip()}
    formats = formats & {"parquet", "feather", "pkl"}
    if not formats:
        formats = {"pkl"}

    if excel_file is None:
        print("[dash-cache] No Excel workbook found. Skipping cache build.")
        return 0

    print(f"[dash-cache] Source workbook: {excel_file}")
    print(f"[dash-cache] Cache directory: {cache_dir}")
    print(f"[dash-cache] Formats: {', '.join(sorted(formats))}")

    book = pd.ExcelFile(excel_file)
    only_sheets_raw = os.getenv("DASH_CACHE_SHEETS", "").strip()
    if only_sheets_raw:
        requested = [x.strip() for x in only_sheets_raw.split(",") if x.strip()]
        sheet_names = [x for x in requested if x in book.sheet_names]
        missing = [x for x in requested if x not in book.sheet_names]
        if missing:
            print(f"[dash-cache] Missing requested sheets: {missing}")
    else:
        sheet_names = list(book.sheet_names)

    manifest = {
        "source": str(excel_file),
        "cache_dir": str(cache_dir),
        "formats": sorted(formats),
        "sheets": {},
    }

    for sheet_name in sheet_names:
        try:
            t0 = time.perf_counter()
            df = book.parse(sheet_name=sheet_name)
            names = list(dict.fromkeys([str(sheet_name), norm_text(sheet_name)]))
            sheet_info = {
                "rows": int(len(df)),
                "cols": int(len(df.columns)),
                "written": {},
                "elapsed_s": None,
            }
            for name in names:
                if not name:
                    continue
                written = write_cache(df, cache_dir / name, formats)
                sheet_info["written"][name] = written
            sheet_info["elapsed_s"] = round(time.perf_counter() - t0, 3)
            manifest["sheets"][str(sheet_name)] = sheet_info
            print(f"[dash-cache] Cached {sheet_name}: rows={len(df):,} cols={len(df.columns):,} elapsed={sheet_info['elapsed_s']}s")
        except Exception as exc:
            manifest["sheets"][str(sheet_name)] = {"error": str(exc)}
            print(f"[dash-cache] ERROR {sheet_name}: {exc}", file=sys.stderr)

    manifest["elapsed_s"] = round(time.perf_counter() - started, 3)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dash-cache] Done in {manifest['elapsed_s']}s. Manifest: {cache_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
