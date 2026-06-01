
from pathlib import Path
import re
from datetime import datetime
from io import BytesIO
import base64
import math
import copy
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from dash import Dash, html, dcc, Input, Output, State, ctx, dash_table, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import unicodedata
from dash.exceptions import PreventUpdate
import os
import urllib.request
import json
import hmac
import time
import hashlib
from functools import wraps, lru_cache
from flask import Flask, request, session, redirect, url_for, render_template_string, has_request_context, send_file
from werkzeug.security import check_password_hash

VN_TZ = "Asia/Ho_Chi_Minh"

# =========================================================
# LIGHT UI + COMPANY LOGO
# =========================================================
APP_LIGHT_BG = "#f5f7fb"
CARD_LIGHT_BG = "#ffffff"
BORDER_LIGHT = "#dfe5ef"
TEXT_LIGHT_UI = "#1f2937"
MUTED_LIGHT_UI = "#667085"
FONT_UI_FAMILY = '"Inter", "SF Pro Display", "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif'

EXEC_SHADOW = "0 20px 45px rgba(15, 23, 42, 0.08)"
EXEC_SHADOW_SOFT = "0 14px 28px rgba(15, 23, 42, 0.06)"
EXEC_RADIUS = "22px"

def _resolve_first_existing_path(candidates):
    for p in candidates:
        try:
            pp = Path(p)
            if pp.exists():
                return pp
        except Exception:
            continue
    return None

LOGO_PATH = _resolve_first_existing_path([
    "/mnt/data/Logo NamThangGroup không nền.png",
    "Logo NamThangGroup không nền.png",
    "assets/Logo NamThangGroup không nền.png",
])
DASH_EMBED_LOGO_DATA_URI = str(os.getenv("DASH_EMBED_LOGO_DATA_URI", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}

def _load_logo_data_uri(path: Path | None):
    """Return a cacheable logo URL by default; embed base64 only when explicitly requested."""
    try:
        if path is None or not path.exists():
            return None
        if not DASH_EMBED_LOGO_DATA_URI:
            try:
                parts = list(path.parts)
                if "assets" in parts:
                    rel = "/".join(parts[parts.index("assets") + 1:])
                    if rel:
                        return "/assets/" + rel
            except Exception:
                pass
            return "/company-logo"
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception:
        pass
    return None

COMPANY_LOGO_SRC = _load_logo_data_uri(LOGO_PATH)

# =========================================================
# GREEN ACCENT
# =========================================================
GREEN_PRIMARY = "#16a34a"
GREEN_BORDER = "#22c55e"
GREEN_SOFT = "#dcfce7"
GREEN_SHADOW = "rgba(34,197,94,0.18)"
GREEN_SHADOW_STRONG = "rgba(34,197,94,0.28)"
NAVY_PRIMARY = "#0f172a"
SLATE_PRIMARY = "#334155"
AMBER_PRIMARY = "#f59e0b"

PAGE_NAV_LEFT_BASE = {
    "position": "fixed",
    "top": "50%",
    "left": "16px",
    "zIndex": 9999,
}
PAGE_NAV_RIGHT_BASE = {
    "position": "fixed",
    "top": "50%",
    "right": "16px",
    "zIndex": 9999,
}

def to_vn_datetime(series: pd.Series, assume_tz_if_naive: str = VN_TZ) -> pd.Series:
    s = pd.to_datetime(series, errors="coerce")
    try:
        if getattr(s.dt, "tz", None) is not None:
            return s.dt.tz_convert(VN_TZ).dt.tz_localize(None)
        return s.dt.tz_localize(assume_tz_if_naive).dt.tz_convert(VN_TZ).dt.tz_localize(None)
    except Exception:
        return pd.to_datetime(series, errors="coerce")


# =========================================================
# REAL DATA CUTOFF - hide future / synthetic-looking periods
# =========================================================
ALLOW_SYNTHETIC_PROXY_DATA = str(os.getenv("DASH_ALLOW_SYNTHETIC_PROXY_DATA", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}

# =========================================================
# GLOBAL PERFORMANCE SWITCHES
# =========================================================
DASH_FAST_MODE = str(os.getenv("DASH_FAST_MODE", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_SERVERLESS_FAST_PRESET = str(os.getenv("DASH_SERVERLESS_FAST_PRESET", os.getenv("VERCEL", "0"))).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_CACHE_DF_COPY_MODE = os.getenv("DASH_CACHE_DF_COPY_MODE", "shallow" if DASH_FAST_MODE else "deep").strip().lower()
DASH_GLOBAL_FILTER_CACHE = str(os.getenv("DASH_GLOBAL_FILTER_CACHE", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_GLOBAL_FILTER_CACHE_MAX = int(os.getenv("DASH_GLOBAL_FILTER_CACHE_MAX", "512" if DASH_SERVERLESS_FAST_PRESET else "768"))
DASH_REGION_SCOPE_CACHE_MAX = int(os.getenv("DASH_REGION_SCOPE_CACHE_MAX", "256" if DASH_SERVERLESS_FAST_PRESET else "384"))
DASH_ZOOM_STORE_MAX_ROWS = int(os.getenv("DASH_ZOOM_STORE_MAX_ROWS", "80" if DASH_SERVERLESS_FAST_PRESET else "200"))
DASH_FIGURE_STORE_MAX_ROWS = int(os.getenv("DASH_FIGURE_STORE_MAX_ROWS", "40" if DASH_SERVERLESS_FAST_PRESET else str(DASH_ZOOM_STORE_MAX_ROWS)))
DASH_KPI_STORE_MAX_ROWS = int(os.getenv("DASH_KPI_STORE_MAX_ROWS", "32" if DASH_SERVERLESS_FAST_PRESET else "80"))
DASH_OPTIONAL_SHEET_RESOLVE_CACHE_MAX = int(os.getenv("DASH_OPTIONAL_SHEET_RESOLVE_CACHE_MAX", "192" if DASH_SERVERLESS_FAST_PRESET else "256"))
DASH_LOG_BOOT_TIMING = str(os.getenv("DASH_LOG_BOOT_TIMING", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_LOG_CALLBACK_TIMING = str(os.getenv("DASH_LOG_CALLBACK_TIMING", os.getenv("DASH_LOG_BOOT_TIMING", "0"))).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_EXCEL_AUTO_DISCOVER = str(os.getenv("DASH_EXCEL_AUTO_DISCOVER", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_PREFER_PARQUET_CACHE = str(os.getenv("DASH_PREFER_PARQUET_CACHE", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_BOOT_SKIP_EXCEL_WHEN_CACHE_READY = str(os.getenv("DASH_BOOT_SKIP_EXCEL_WHEN_CACHE_READY", "1" if DASH_SERVERLESS_FAST_PRESET else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_LAZY_OPEN_EXCEL_ON_CACHE_MISS = str(os.getenv("DASH_LAZY_OPEN_EXCEL_ON_CACHE_MISS", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_CACHE_DIR = Path(os.getenv("DASH_CACHE_DIR", "output/cache"))
DASH_CACHE_STALE_GRACE_SECONDS = int(os.getenv("DASH_CACHE_STALE_GRACE_SECONDS", "3600"))
# Vercel/serverless cold-start guard: when prebuilt cache files are present,
# do not download/open the large Excel workbook just to serve Home/Daily.
DASH_CACHE_FIRST_BOOT = str(os.getenv("DASH_CACHE_FIRST_BOOT", "1" if DASH_SERVERLESS_FAST_PRESET else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_DATA_VERSION = str(os.getenv("DASH_DATA_VERSION", os.getenv("VERCEL_GIT_COMMIT_SHA", ""))).strip()
DASH_ZOOM_STORE_INCLUDE_FIGURE = str(os.getenv("DASH_ZOOM_STORE_INCLUDE_FIGURE", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_ZOOM_FORCE_FIGURE_FOR_CHARTS = str(os.getenv("DASH_ZOOM_FORCE_FIGURE_FOR_CHARTS", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_GRAPH_LEAN_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
    "staticPlot": False,
}
DASH_CLIENT_PRELOAD_AFTER_BOOT = str(os.getenv("DASH_CLIENT_PRELOAD_AFTER_BOOT", "0" if DASH_SERVERLESS_FAST_PRESET else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_CLIENT_PRELOAD_MODE = os.getenv("DASH_CLIENT_PRELOAD_MODE", "light" if DASH_SERVERLESS_FAST_PRESET else "interactive").strip().lower()
DASH_CLIENT_PRELOAD_DELAY_MS = int(os.getenv("DASH_CLIENT_PRELOAD_DELAY_MS", "5000" if DASH_SERVERLESS_FAST_PRESET else "650"))
DASH_ZOOM_COMPACT_FIGURE = str(os.getenv("DASH_ZOOM_COMPACT_FIGURE", "1" if DASH_SERVERLESS_FAST_PRESET else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_ZOOM_OPEN_CACHE_MAX = int(os.getenv("DASH_ZOOM_OPEN_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
DASH_ZOOM_DRILL_CACHE_MAX = int(os.getenv("DASH_ZOOM_DRILL_CACHE_MAX", "160" if DASH_SERVERLESS_FAST_PRESET else "256"))
DASH_DAILY_LOAD_SEAT_DATA = str(os.getenv("DASH_DAILY_LOAD_SEAT_DATA", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
# Daily menu speed mode: avoid duplicated Plotly figure payloads in hidden zoom stores.
# The browser already has the visible graph figure, so zoom retrieves it lazily on click.
DASH_DAILY_LAZY_ZOOM_FIGURES = str(os.getenv("DASH_DAILY_LAZY_ZOOM_FIGURES", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
# Home uses the same browser-side lazy zoom pattern as Daily so the visible
# graph figure is not duplicated in hidden dcc.Store payloads.
DASH_HOME_LAZY_ZOOM_FIGURES = str(os.getenv("DASH_HOME_LAZY_ZOOM_FIGURES", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_DAILY_TABLE_MAX_ROWS = int(os.getenv("DASH_DAILY_TABLE_MAX_ROWS", "750" if DASH_SERVERLESS_FAST_PRESET else "1500"))
# Driver-specific breakdown sheets are heavy and only needed after a driver filter is selected.
DASH_DAILY_LAZY_DRIVER_DETAIL = str(os.getenv("DASH_DAILY_LAZY_DRIVER_DETAIL", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_WARM_ALLOW_DEEP_PRELOAD = str(os.getenv("DASH_WARM_ALLOW_DEEP_PRELOAD", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DASH_WARM_INCLUDE_TOUCH_SUMS = str(os.getenv("DASH_WARM_INCLUDE_TOUCH_SUMS", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}


def _graph_config(extra: dict | None = None) -> dict:
    """Small browser-side performance default for normal dashboard graphs."""
    cfg = dict(DASH_GRAPH_LEAN_CONFIG)
    if isinstance(extra, dict):
        cfg.update(extra)
    return cfg

def _return_df_cached(dff: pd.DataFrame) -> pd.DataFrame:
    """Return cached DataFrames quickly while keeping caller isolation for new columns."""
    if not isinstance(dff, pd.DataFrame):
        return dff
    try:
        if DASH_CACHE_DF_COPY_MODE in {"none", "view", "off"}:
            return dff
        if DASH_CACHE_DF_COPY_MODE in {"shallow", "fast"}:
            return dff.copy(deep=False)
    except Exception:
        pass
    return dff.copy()


def _perf_log(label: str, started: float, extra: str = "") -> None:
    if not (DASH_LOG_BOOT_TIMING or DASH_LOG_CALLBACK_TIMING):
        return
    try:
        suffix = f" {extra}" if extra else ""
        print(f"[DASH PERF] {label}: {time.perf_counter() - started:.3f}s{suffix}")
    except Exception:
        pass


def timed_callback(label: str):
    def _decorator(func):
        @wraps(func)
        def _wrapped(*args, **kwargs):
            started = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                if DASH_LOG_CALLBACK_TIMING:
                    _perf_log(f"callback:{label}", started)
        return _wrapped
    return _decorator


_BOOT_STARTED = time.perf_counter()


def _stable_list_key(values):
    if values is None:
        return ()
    if isinstance(values, (list, tuple, set)):
        return tuple(sorted(str(x) for x in values if str(x).strip()))
    return (str(values),) if str(values).strip() else ()


def _df_cache_signature(dff: pd.DataFrame):
    if not isinstance(dff, pd.DataFrame):
        return ("none", 0, ())
    return (id(dff), len(dff), tuple(map(str, dff.columns)))


def _now_vn_naive() -> pd.Timestamp:
    """Current Vietnam time as a timezone-naive Timestamp for safe DataFrame comparison."""
    try:
        return pd.Timestamp.now(tz=VN_TZ).tz_localize(None)
    except Exception:
        return pd.Timestamp.now()


def _current_vn_month_start() -> pd.Timestamp:
    try:
        return _now_vn_naive().to_period("M").to_timestamp()
    except Exception:
        return pd.Timestamp.today().to_period("M").to_timestamp()


def _current_vn_day_start() -> pd.Timestamp:
    try:
        return _now_vn_naive().normalize()
    except Exception:
        return pd.Timestamp.today().normalize()


def _coerce_month_start(series_like) -> pd.Series:
    try:
        return pd.to_datetime(series_like, errors="coerce").dt.to_period("M").dt.to_timestamp()
    except Exception:
        return pd.Series([pd.NaT] * len(series_like))


def _apply_real_data_cutoff(dff: pd.DataFrame, month_col: str = "thang_nam_vn", day_col: str | None = None) -> pd.DataFrame:
    """
    Keep only periods that have actually happened in Vietnam time.
    This prevents future months/days from appearing in cards, charts, filters and exports.
    """
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return dff.copy() if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    out = dff.copy()

    month_candidates = []
    if month_col and month_col in out.columns:
        month_candidates.append(month_col)
    for c in ["thang_nam_vn", "thang_nam"]:
        if c in out.columns and c not in month_candidates:
            month_candidates.append(c)

    if month_candidates:
        c = month_candidates[0]
        months = _coerce_month_start(out[c])
        cutoff_month = _current_vn_month_start()
        out = out[(months.isna()) | (months <= cutoff_month)].copy()

    day_candidates = []
    if day_col and day_col in out.columns:
        day_candidates.append(day_col)
    for c in ["ngay_du_lieu", "ngay_bao_cao", "ngay", "date", "report_date"]:
        if c in out.columns and c not in day_candidates:
            day_candidates.append(c)

    if day_candidates:
        c = day_candidates[0]
        try:
            days = pd.to_datetime(out[c], errors="coerce")
            if getattr(days.dt, "tz", None) is not None:
                days = days.dt.tz_convert(VN_TZ).dt.tz_localize(None)
            days = pd.to_datetime(days, errors="coerce").dt.normalize()
            cutoff_day = _current_vn_day_start()
            out = out[(days.isna()) | (days <= cutoff_day)].copy()
        except Exception:
            pass
    return out.copy()


def _apply_real_data_cutoff_inplace_to_globals(names: list[str]) -> None:
    """Small utility used during boot to sanitize loaded frames without changing app structure."""
    g = globals()
    for name in names:
        obj = g.get(name)
        if isinstance(obj, pd.DataFrame):
            g[name] = _apply_real_data_cutoff(obj).reset_index(drop=True)


def fmt_vn(n) -> str:
    try:
        if n is None or (isinstance(n, float) and pd.isna(n)):
            return "0"
        return f"{float(n):,.0f}".replace(",", ".")
    except Exception:
        return str(n)

def fmt_pct(n, digits: int = 1) -> str:
    try:
        if n is None or (isinstance(n, float) and pd.isna(n)):
            return "0%"
        return f"{float(n):.{digits}f}%"
    except Exception:
        return "0%"

FIND_COL_CACHE = {}
FIND_COL_FUZZY_CACHE = {}
FIND_COL_CACHE_MAX = int(os.getenv("DASH_FIND_COL_CACHE_MAX", "12000" if DASH_SERVERLESS_FAST_PRESET else "20000"))


def _columns_cache_signature(df: pd.DataFrame):
    try:
        return tuple(map(str, df.columns))
    except Exception:
        return ()


def _cache_get(cache: dict, key):
    try:
        if key in cache:
            return True, cache[key]
    except Exception:
        pass
    return False, None


def _cache_set(cache: dict, key, value):
    try:
        if len(cache) > FIND_COL_CACHE_MAX:
            cache.clear()
        cache[key] = value
    except Exception:
        pass
    return value


def find_col(df: pd.DataFrame, candidates):
    if df is None or not isinstance(df, pd.DataFrame):
        return None
    candidate_key = tuple(str(c) for c in (candidates if isinstance(candidates, (list, tuple, set)) else [candidates]))
    cache_key = (_columns_cache_signature(df), candidate_key)
    hit, value = _cache_get(FIND_COL_CACHE, cache_key)
    if hit:
        return value

    cols = list(df.columns)
    norm = {str(c).strip().lower(): c for c in cols}
    for cand in candidate_key:
        key = str(cand).strip().lower()
        if key in norm:
            return _cache_set(FIND_COL_CACHE, cache_key, norm[key])

    # Fallback chuẩn hoá tiếng Việt/Unicode để bắt các cột có dấu, có khoảng trắng,
    # dấu gạch dưới hoặc ký tự đặc biệt khác nhau giữa các file Excel thật.
    try:
        norm2 = {norm_text(c): c for c in cols}
        compact = {re.sub(r"[^a-z0-9]+", "", norm_text(c)): c for c in cols}
        for cand in candidate_key:
            key2 = norm_text(cand)
            if key2 in norm2:
                return _cache_set(FIND_COL_CACHE, cache_key, norm2[key2])
            key3 = re.sub(r"[^a-z0-9]+", "", key2)
            if key3 in compact:
                return _cache_set(FIND_COL_CACHE, cache_key, compact[key3])
    except Exception:
        pass
    return _cache_set(FIND_COL_CACHE, cache_key, None)

def find_col_fuzzy(df: pd.DataFrame, candidates):
    """Find a column with accent, whitespace, underscore and case tolerant matching."""
    if df is None or not isinstance(df, pd.DataFrame):
        return None
    candidate_key = tuple(str(c) for c in (candidates if isinstance(candidates, (list, tuple, set)) else [candidates]))
    cache_key = (_columns_cache_signature(df), candidate_key)
    hit, value = _cache_get(FIND_COL_FUZZY_CACHE, cache_key)
    if hit:
        return value

    direct = find_col(df, candidate_key)
    if direct is not None:
        return _cache_set(FIND_COL_FUZZY_CACHE, cache_key, direct)
    try:
        norm_candidates = [norm_text(c) for c in candidate_key if str(c).strip()]
        col_norm = {norm_text(c): c for c in list(df.columns)}
        for cand in norm_candidates:
            if cand in col_norm:
                return _cache_set(FIND_COL_FUZZY_CACHE, cache_key, col_norm[cand])
        compact_candidates = [c.replace(" ", "") for c in norm_candidates if c]
        compact_cols = {norm_text(c).replace(" ", ""): c for c in list(df.columns)}
        for cand in compact_candidates:
            if cand in compact_cols:
                return _cache_set(FIND_COL_FUZZY_CACHE, cache_key, compact_cols[cand])
        for c in list(df.columns):
            cn = norm_text(c)
            ccompact = cn.replace(" ", "")
            for cand in norm_candidates:
                if not cand:
                    continue
                cand_compact = cand.replace(" ", "")
                if cand in cn or cn in cand or cand_compact in ccompact or ccompact in cand_compact:
                    return _cache_set(FIND_COL_FUZZY_CACHE, cache_key, c)
    except Exception:
        return _cache_set(FIND_COL_FUZZY_CACHE, cache_key, None)
    return _cache_set(FIND_COL_FUZZY_CACHE, cache_key, None)

@lru_cache(maxsize=int(os.getenv("DASH_NORM_TEXT_CACHE_MAX", "200000" if DASH_SERVERLESS_FAST_PRESET else "300000")))
def _norm_text_cached_scalar(s: str) -> str:
    s = (s.replace("\u200b", " ")
           .replace("\ufeff", " ")
           .replace("\xa0", " ")
           .replace("\t", " ")
           .replace("\r", " ")
           .replace("\n", " "))
    s = s.strip().lower()
    s = s.replace("đ", "d")
    s = s.replace("hđ", "hop dong").replace("hd", "hop dong")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_text(s: str) -> str:
    if s is None:
        return ""
    try:
        if not isinstance(s, str) and pd.isna(s):
            return ""
    except Exception:
        pass
    try:
        return _norm_text_cached_scalar(str(s))
    except Exception:
        return ""

LH_CANON = ["Xe Công ty", "Xe thương quyền hợp tác", "Xe thương quyền trả góp"]
HD_CANON = ["Hợp đồng thường", "Tuyến chiến lược", "Xe tiện chuyến"]

LH_MAP = {
    "xe cong ty": "Xe Công ty",
    "xe thuong quyen hop tac": "Xe thương quyền hợp tác",
    "xe thuong quyen htkd": "Xe thương quyền hợp tác",
    "xe thuong quyen hop dong hop tac": "Xe thương quyền hợp tác",
    "xe thuong quyen tra gop": "Xe thương quyền trả góp",
    "xe cong ty ": "Xe Công ty",
}

HD_MAP = {
    "hop dong thuong": "Hợp đồng thường",
    "tuyen chien luoc": "Tuyến chiến lược",
    "xe tien chuyen": "Xe tiện chuyến",
    "hop dong thong thuong": "Hợp đồng thường",
    "hop dong binh thuong": "Hợp đồng thường",
    "hop dong thuong le": "Hợp đồng thường",
    "hop dong thuong quy": "Hợp đồng thường",
    "hop dong thuong (thuong)": "Hợp đồng thường",
    "hop dong  thuong": "Hợp đồng thường",
    "hop dong thuong ": "Hợp đồng thường",
    "hd thuong": "Hợp đồng thường",
    "tuyen chuyen luoc": "Tuyến chiến lược",
}

_MAP_TO_CANON_NORM_CACHE = {}


def _mapping_norm_cached(mapping: dict) -> dict:
    try:
        key = tuple(sorted((str(k), str(v)) for k, v in (mapping or {}).items()))
        cached = _MAP_TO_CANON_NORM_CACHE.get(key)
        if cached is not None:
            return cached
        out = {norm_text(k): v for k, v in (mapping or {}).items()}
        if len(_MAP_TO_CANON_NORM_CACHE) > 128:
            _MAP_TO_CANON_NORM_CACHE.clear()
        _MAP_TO_CANON_NORM_CACHE[key] = out
        return out
    except Exception:
        return {norm_text(k): v for k, v in (mapping or {}).items()}


def map_to_canon(series: pd.Series, mapping: dict) -> pd.Series:
    s = series.astype(str).map(norm_text)
    out = s.map(_mapping_norm_cached(mapping))
    m = out.isna()
    if m.any():
        ss = s[m]
        out.loc[m & ss.str.contains(r"\bhop dong\b") & ss.str.contains(r"\bthuong\b")] = "Hợp đồng thường"
        out.loc[m & ss.str.contains(r"\btuyen\b") & (ss.str.contains("chien luoc") | ss.str.contains("chuyen luoc"))] = "Tuyến chiến lược"
        out.loc[m & ss.str.contains(r"\bxe\b") & ss.str.contains("tien chuyen")] = "Xe tiện chuyến"
        out.loc[m & ss.str.contains("xe cong ty", na=False)] = "Xe Công ty"
        out.loc[m & ss.str.contains("thuong quyen", na=False) & (ss.str.contains("hop tac", na=False) | ss.str.contains("htkd", na=False))] = "Xe thương quyền hợp tác"
        out.loc[m & ss.str.contains("thuong quyen", na=False) & ss.str.contains("tra gop", na=False)] = "Xe thương quyền trả góp"
    return out.fillna("Khác")

# =========================
# DATA
# =========================
def _score_excel_workbook_for_dashboard(path: Path) -> int:
    """
    Score an Excel workbook by sheet names so deployments do not go blank when
    the exported file name/path changes. This only selects an existing real file;
    it never creates or synthesizes data.
    """
    try:
        if path is None or not path.exists() or path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
            return -1
        book = pd.ExcelFile(path)
        compact_names = {_sheet_name_key(x) if "_sheet_name_key" in globals() else re.sub(r"[^a-z0-9]+", "", norm_text(x)) for x in book.sheet_names}
        score = 0
        core = {
            "doanhthuthangkhuvuc": 90,
            "doanhthulhkvthang": 70,
            "hopdongkvthang": 60,
        }
        vehicle = {
            "phuongtien": 45,
            "quanlyphuongtien": 55,
            "danhsachphuongtien": 55,
            "danhsachxe": 55,
            "quanlyxe": 55,
            "xetructhuoc": 70,
            "xephanquyen": 70,
            "xecongty": 65,
            "xethuongquyen": 65,
            "xehoptac": 60,
            "xedoitac": 60,
            "xetragop": 60,
            "xedien": 55,
            "xexang": 55,
            "fleet": 55,
            "vehicle": 55,
            "vehicles": 55,
        }
        daily = {
            "doanhthungaychecker": 95,
            "doanhthungaylhchecker": 75,
            "doanhthungayhinhthuc": 70,
            "doanhthungayluong": 65,
            "doanhthungaysocho": 65,
            "doanhthungaytaixe": 65,
        }
        for key, pts in core.items():
            if key in compact_names:
                score += pts
        for key, pts in daily.items():
            if key in compact_names:
                score += pts
        for token, pts in vehicle.items():
            if any(token in name or name in token for name in compact_names):
                score += pts
        # Prefer the conventional report name when scores are tied.
        if "bao_cao_doanh_thu_tong_hop" in path.name.lower():
            score += 20
        return score
    except Exception:
        return -1


def _cache_file_candidates_boot_fast(sheet_name: str) -> list[Path]:
    """Small early-boot cache lookup used before EXCEL_FILE/_cache helpers exist."""
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(sheet_name)).strip("_")
    names = [str(sheet_name), safe_name]
    out = []
    seen = set()
    for name in names:
        if not str(name).strip():
            continue
        for suffix in (".parquet", ".feather", ".pkl"):
            fp = DASH_CACHE_DIR / f"{name}{suffix}"
            key = str(fp)
            if key not in seen:
                seen.add(key)
                out.append(fp)
    return out


def _sheet_cache_group_exists_boot_fast(sheet_names) -> bool:
    try:
        for name in sheet_names if isinstance(sheet_names, (list, tuple, set)) else [sheet_names]:
            if any(fp.exists() and fp.stat().st_size > 0 for fp in _cache_file_candidates_boot_fast(str(name))):
                return True
    except Exception:
        return False
    return False


def _cache_first_boot_ready() -> bool:
    """Return True when enough prebuilt cache files exist to skip DATA_URL cold-start download."""
    if not DASH_CACHE_FIRST_BOOT:
        return False
    default_groups = [
        ["DoanhThu_Thang_KhuVuc"],
        ["DoanhThu_LH_KV_Thang"],
        ["HopDong_KV_Thang"],
        ["DoanhThu_Ngay_Checker", "DoanhThu_Ngay_TheoNgay", "DoanhThuNgayChecker", "doanhthungaychecker", "Sheet1"],
        ["DoanhThu_Ngay_LH_Checker", "DoanhThu_Ngay_LoaiHinh", "DoanhThuNgay_LoaiHinh", "DoanhThu_LH_Ngay_Checker"],
        ["DoanhThu_Ngay_HinhThuc", "DoanhThu_Ngay_HinhThucKD", "DoanhThuNgay_HinhThuc", "DoanhThu_HinhThuc_Ngay"],
    ]
    raw = str(os.getenv("DASH_CACHE_FIRST_REQUIRED_SHEET_GROUPS", "")).strip()
    if raw:
        groups = []
        for group in raw.split(";"):
            names = [x.strip() for x in group.replace(",", "|").split("|") if x.strip()]
            if names:
                groups.append(names)
    else:
        groups = default_groups
    if not groups:
        return False
    ready = all(_sheet_cache_group_exists_boot_fast(group) for group in groups)
    if ready and (DASH_LOG_BOOT_TIMING or DASH_LOG_CALLBACK_TIMING):
        print(f"[DATA] Cache-first boot ready; skipping remote Excel download. cache_dir={DASH_CACHE_DIR}")
    return ready


REMOTE_EXCEL_ERROR = None


def _remote_excel_url() -> str:
    return str(
        os.getenv("DATA_URL")
        or os.getenv("DASH_DATA_URL")
        or os.getenv("EXCEL_DATA_URL")
        or ""
    ).strip()


def _validate_excel_file_bytes(path: Path) -> tuple[bool, str]:
    """Validate that the file is a real .xlsx workbook, not a Git LFS pointer/HTML error."""
    try:
        if path is None or not path.exists():
            return False, f"File không tồn tại: {path}"
        size = path.stat().st_size
        head = path.read_bytes()[:160]
        if head.startswith(b"version https://git-lfs.github.com/spec/v1"):
            return False, "File đang là Git LFS pointer, không phải Excel thật."
        if head.lstrip().lower().startswith(b"<!doctype html") or head.lstrip().lower().startswith(b"<html"):
            return False, "URL đang trả về HTML, không phải file Excel thật."
        if not head.startswith(b"PK"):
            return False, f"File tải về không giống .xlsx thật. Size={size}, header={head[:40]!r}"
        return True, f"OK size={size}"
    except Exception as e:
        return False, str(e)


def _download_dashboard_excel_from_url() -> Path | None:
    """Download the real Excel file to /tmp on Vercel when DATA_URL is configured."""
    global REMOTE_EXCEL_ERROR
    data_url = _remote_excel_url()
    if not data_url:
        return None

    filename = os.getenv("DASH_REMOTE_EXCEL_FILENAME", "bao_cao_doanh_thu_tong_hop.xlsx")
    target_dir = Path(os.getenv("DASH_REMOTE_EXCEL_DIR", "/tmp"))
    target_path = target_dir / filename
    timeout = int(os.getenv("DASH_REMOTE_EXCEL_TIMEOUT", "120"))

    try:
        target_dir.mkdir(parents=True, exist_ok=True)

        # Reuse a valid warm-cache file in /tmp when the serverless instance is warm.
        if target_path.exists():
            ok, msg = _validate_excel_file_bytes(target_path)
            if ok:
                print(f"[DATA] Using cached remote Excel: {target_path} ({msg})")
                return target_path
            try:
                target_path.unlink()
            except Exception:
                pass

        print(f"[DATA] Downloading Excel from DATA_URL to {target_path} ...")
        req = urllib.request.Request(
            data_url,
            headers={
                "User-Agent": "NamThang-Dash/1.0",
                "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/octet-stream,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            target_path.write_bytes(resp.read())

        ok, msg = _validate_excel_file_bytes(target_path)
        print(f"[DATA] Remote Excel check: {msg}")
        if not ok:
            REMOTE_EXCEL_ERROR = (
                "DATA_URL không trả về file Excel thật. "
                f"Chi tiết: {msg}. Hãy dùng link raw/download thật, không dùng link trang GitHub preview."
            )
            try:
                target_path.unlink()
            except Exception:
                pass
            return None
        return target_path
    except Exception as e:
        REMOTE_EXCEL_ERROR = f"Không tải được Excel từ DATA_URL: {e}"
        print(f"[DATA] {REMOTE_EXCEL_ERROR}")
        return None


def _resolve_dashboard_excel_file(candidates) -> Path | None:
    # On Vercel, prefer prebuilt Parquet/Feather/Pickle caches when they are ready.
    # This avoids downloading/opening the large Excel workbook during cold start.
    if _cache_first_boot_ready():
        return None

    # On Vercel, prefer DATA_URL when cache-first is not ready so the Excel file is not bundled.
    remote_path = _download_dashboard_excel_from_url()
    if remote_path is not None:
        return remote_path

    env_file = os.getenv("DASH_EXCEL_FILE") or os.getenv("OUTPUT_EXCEL_FILE")
    if env_file:
        env_path = _resolve_first_existing_path([env_file])
        if env_path is not None:
            ok, msg = _validate_excel_file_bytes(env_path)
            if ok:
                return env_path
            print(f"[DATA] Ignoring invalid DASH_EXCEL_FILE/OUTPUT_EXCEL_FILE: {msg}")

    # 1) Keep original exact-path behavior first, but ignore LFS pointer files.
    exact = _resolve_first_existing_path(candidates)
    if exact is not None:
        ok, msg = _validate_excel_file_bytes(exact)
        if ok:
            return exact
        print(f"[DATA] Ignoring invalid local Excel candidate {exact}: {msg}")

    # 2) Optional advanced discovery. This is expensive on serverless cold starts,
    # so it is disabled by default for production/Vercel.
    if not DASH_EXCEL_AUTO_DISCOVER:
        return None

    search_roots = []
    for raw in [".", "output", "data", "assets", "/mnt/data"]:
        try:
            root = Path(raw)
            if root.exists() and root.is_dir():
                search_roots.append(root)
        except Exception:
            continue

    discovered = []
    seen = set()
    for root in search_roots:
        try:
            for fp in root.rglob("*.xls*"):
                try:
                    rp = fp.resolve()
                    if str(rp) in seen:
                        continue
                    seen.add(str(rp))
                    score = _score_excel_workbook_for_dashboard(rp)
                    if score > 0:
                        discovered.append((score, rp.stat().st_mtime, rp))
                except Exception:
                    continue
        except Exception:
            continue
    if not discovered:
        return None
    discovered.sort(key=lambda x: (-x[0], -x[1], str(x[2])))
    return discovered[0][2]


EXCEL_FILE = _resolve_dashboard_excel_file([
    "output/bao_cao_doanh_thu_tong_hop.xlsx",
    "/mnt/data/bao_cao_doanh_thu_tong_hop.xlsx",
    "bao_cao_doanh_thu_tong_hop.xlsx",
    "/mnt/data/doanhthungaychecker.xlsx",
    "doanhthungaychecker.xlsx",
])

DATA_LOAD_ERROR = None
DATA_LOAD_ERRORS = []
EXCEL_BOOK = None

def _empty_dashboard_df(kind: str) -> pd.DataFrame:
    base_cols = ["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc"]
    if kind == "lh":
        base_cols += ["loai_hinh_std"]
    if kind == "hd":
        base_cols += ["loai_hop_dong_std"]
    return pd.DataFrame(columns=list(dict.fromkeys(base_cols)))


def _cache_file_candidates(sheet_name: str) -> list[Path]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(sheet_name)).strip("_")
    names = [sheet_name, safe_name]
    out = []
    for name in names:
        if not name:
            continue
        out.append(DASH_CACHE_DIR / f"{name}.parquet")
        out.append(DASH_CACHE_DIR / f"{name}.feather")
        out.append(DASH_CACHE_DIR / f"{name}.pkl")
    seen = set()
    unique = []
    for item in out:
        key = str(item)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _cache_file_is_fresh_enough(fp: Path) -> bool:
    try:
        if not fp.exists():
            return False
        if EXCEL_FILE is not None and Path(EXCEL_FILE).exists():
            excel_mtime = Path(EXCEL_FILE).stat().st_mtime
            cache_mtime = fp.stat().st_mtime
            # Allow a small timestamp drift because refresh_data.py may write
            # Dash cache while the Excel writer is still closing the workbook.
            if cache_mtime + DASH_CACHE_STALE_GRACE_SECONDS < excel_mtime:
                return False
    except Exception:
        pass
    return True


def _existing_cache_file_candidates(sheet_name: str) -> list[Path]:
    try:
        files = [fp for fp in _cache_file_candidates(sheet_name) if _cache_file_is_fresh_enough(fp)]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return [fp for fp in _cache_file_candidates(sheet_name) if fp.exists()]


def _sheet_cache_exists(sheet_name: str) -> bool:
    try:
        return any(_existing_cache_file_candidates(str(sheet_name)))
    except Exception:
        return False


def _all_sheet_caches_exist(sheet_names) -> bool:
    try:
        return bool(sheet_names) and all(_sheet_cache_exists(x) for x in sheet_names)
    except Exception:
        return False


def _ensure_excel_book_opened() -> bool:
    global EXCEL_BOOK, _excel_sheet_name_list, _excel_sheet_names
    if EXCEL_BOOK is not None:
        return True
    if EXCEL_FILE is None or not DASH_LAZY_OPEN_EXCEL_ON_CACHE_MISS:
        return False
    try:
        started = time.perf_counter()
        EXCEL_BOOK = pd.ExcelFile(EXCEL_FILE)
        _excel_sheet_name_list = list(EXCEL_BOOK.sheet_names)
        _excel_sheet_names = set(_excel_sheet_name_list)
        if DASH_LOG_BOOT_TIMING:
            _perf_log("lazy_open_excel_book", started, f"excel={EXCEL_FILE}")
        return True
    except Exception as e:
        try:
            DATA_LOAD_ERRORS.append(f"lazy_open_excel: {e}")
        except Exception:
            pass
        EXCEL_BOOK = None
        return False


def _parse_cached_sheet(sheet_name: str) -> pd.DataFrame | None:
    if not DASH_PREFER_PARQUET_CACHE:
        return None
    for fp in _existing_cache_file_candidates(sheet_name):
        try:
            if not fp.exists():
                continue
            started = time.perf_counter()
            suffix = fp.suffix.lower()
            if suffix == ".parquet":
                out = pd.read_parquet(fp)
            elif suffix == ".feather":
                out = pd.read_feather(fp)
            elif suffix == ".pkl":
                out = pd.read_pickle(fp)
            else:
                continue
            if DASH_LOG_BOOT_TIMING:
                _perf_log(f"read_cache:{sheet_name}", started, f"rows={len(out):,} file={fp}")
            return out
        except Exception as e:
            DATA_LOAD_ERRORS.append(f"cache:{sheet_name}: {e}")
    return None


def _read_core_sheet(sheet_name: str, kind: str) -> pd.DataFrame:
    if EXCEL_BOOK is not None:
        return _parse_excel_sheet_or_empty(EXCEL_BOOK, sheet_name, kind)
    cached = _parse_cached_sheet(sheet_name)
    return cached if isinstance(cached, pd.DataFrame) else _empty_dashboard_df(kind)


def _parse_excel_sheet_or_empty(book: pd.ExcelFile, sheet_name: str, kind: str) -> pd.DataFrame:
    cached = _parse_cached_sheet(sheet_name)
    if isinstance(cached, pd.DataFrame):
        return cached
    try:
        started = time.perf_counter()
        out = book.parse(sheet_name=sheet_name)
        if DASH_LOG_BOOT_TIMING:
            _perf_log(f"read_excel:{sheet_name}", started, f"rows={len(out):,}")
        return out
    except Exception as e:
        DATA_LOAD_ERRORS.append(f"{sheet_name}: {e}")
        return _empty_dashboard_df(kind)


df_dt = _empty_dashboard_df("dt")
df_lh = _empty_dashboard_df("lh")
df_hd = _empty_dashboard_df("hd")

_core_started = time.perf_counter()
try:
    _core_sheet_names = ["DoanhThu_Thang_KhuVuc", "DoanhThu_LH_KV_Thang", "HopDong_KV_Thang"]
    _can_skip_excel_book = bool(
        EXCEL_FILE is not None
        and DASH_BOOT_SKIP_EXCEL_WHEN_CACHE_READY
        and DASH_PREFER_PARQUET_CACHE
        and _all_sheet_caches_exist(_core_sheet_names)
    )
    if EXCEL_FILE is not None and not _can_skip_excel_book:
        EXCEL_BOOK = pd.ExcelFile(EXCEL_FILE)
    df_dt = _read_core_sheet("DoanhThu_Thang_KhuVuc", "dt")
    df_lh = _read_core_sheet("DoanhThu_LH_KV_Thang", "lh")
    df_hd = _read_core_sheet("HopDong_KV_Thang", "hd")
    if DATA_LOAD_ERRORS:
        DATA_LOAD_ERROR = "Lỗi đọc một số sheet/cache: " + " | ".join(DATA_LOAD_ERRORS[:3])
except Exception as e:
    EXCEL_BOOK = None
    DATA_LOAD_ERROR = f"Lỗi mở dữ liệu dashboard: {e}"
    df_dt = _empty_dashboard_df("dt")
    df_lh = _empty_dashboard_df("lh")
    df_hd = _empty_dashboard_df("hd")

if EXCEL_FILE is None and all(x.empty for x in [df_dt, df_lh, df_hd]):
    if REMOTE_EXCEL_ERROR:
        DATA_LOAD_ERROR = REMOTE_EXCEL_ERROR
    else:
        DATA_LOAD_ERROR = "Không tìm thấy file Excel/cache dữ liệu. Hãy kiểm tra DATA_URL, DASH_EXCEL_FILE hoặc DASH_CACHE_DIR."
if REMOTE_EXCEL_ERROR and DATA_LOAD_ERROR is None:
    DATA_LOAD_ERROR = REMOTE_EXCEL_ERROR
if DASH_LOG_BOOT_TIMING:
    _perf_log("core_data_load", _core_started, f"excel={EXCEL_FILE} cache_dir={DASH_CACHE_DIR}")

for df in [df_dt, df_lh, df_hd]:
    df["thang_nam"] = pd.to_datetime(df["thang_nam"]).dt.to_period("M").dt.to_timestamp()
    df["thang_nam_vn"] = to_vn_datetime(df["thang_nam"])
    df["thang_nam_vn"] = pd.to_datetime(df["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()
    df["thang_label"] = df["thang_nam_vn"].dt.strftime("%m/%Y")
    df["nam"] = df["thang_nam_vn"].dt.year

REGION_CANON_MAP = {
    "ct": "Cần Thơ",
    "hg": "Hậu Giang",
    "st": "Sóc Trăng",
    "pq": "Phú Quốc",
    "rg": "Rạch Giá",
    "bl": "Bạc Liêu",
    "cm": "Cà Mau",
    "vl": "Vĩnh Long",
    "ag": "An Giang",
    "c t": "Cần Thơ",
    "h g": "Hậu Giang",
    "s t": "Sóc Trăng",
    "p q": "Phú Quốc",
    "r g": "Rạch Giá",
    "b l": "Bạc Liêu",
    "c m": "Cà Mau",
    "v l": "Vĩnh Long",
    "a g": "An Giang",
    "can tho": "Cần Thơ",
    "tp can tho": "Cần Thơ",
    "tp. can tho": "Cần Thơ",
    "thanh pho can tho": "Cần Thơ",
    "cần thơ": "Cần Thơ",
    "cantho": "Cần Thơ",
    "hau giang": "Hậu Giang",
    "hậu giang": "Hậu Giang",
    "haugiang": "Hậu Giang",
    "soc trang": "Sóc Trăng",
    "sóc trăng": "Sóc Trăng",
    "soctrang": "Sóc Trăng",
    "phu quoc": "Phú Quốc",
    "phú quốc": "Phú Quốc",
    "phuquoc": "Phú Quốc",
    "rach gia": "Rạch Giá",
    "rạch giá": "Rạch Giá",
    "rachgia": "Rạch Giá",
    "bac lieu": "Bạc Liêu",
    "bạc liêu": "Bạc Liêu",
    "baclieu": "Bạc Liêu",
    "ca mau": "Cà Mau",
    "cà mau": "Cà Mau",
    "camau": "Cà Mau",
    "vinh long": "Vĩnh Long",
    "vĩnh long": "Vĩnh Long",
    "vinhlong": "Vĩnh Long",
    "an giang": "An Giang",
    "angiang": "An Giang",
}
PINNED_REGIONS = ["Cần Thơ"]

def canon_region_name(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s0 = re.sub(r"\s+", " ", str(x)).strip()
    key = norm_text(s0)
    if key in REGION_CANON_MAP:
        return REGION_CANON_MAP[key]
    return s0

for df in [df_dt, df_lh, df_hd]:
    if "khu_vuc" in df.columns:
        df["khu_vuc"] = df["khu_vuc"].apply(canon_region_name)

# Preserve full-period core sheets for the Phuong tien bridge.
# Revenue/business menus still use the real-data cutoff below, but fleet menus have
# no year/month UI and must not be wiped out by the global current-month cutoff.
df_dt_all_periods = df_dt.copy()
df_lh_all_periods = df_lh.copy()
df_hd_all_periods = df_hd.copy()

# Hide future months immediately after loading the core sheets so proxy/fallback
# datasets cannot inherit not-yet-real periods from the revenue base.
_apply_real_data_cutoff_inplace_to_globals(["df_dt", "df_lh", "df_hd"])


# =========================
# AUTH / RBAC
# =========================
def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

def _auth_users_candidates() -> list[Path]:
    out = []
    env_path = os.getenv("DASH_USERS_FILE")
    if env_path:
        out.append(Path(env_path))
    out.extend([
        Path("users.json"),
        Path("/mnt/data/users.json"),
        Path("config/users.json"),
    ])
    seen = []
    for item in out:
        try:
            rp = item.resolve()
        except Exception:
            rp = item
        if str(rp) not in seen:
            seen.append(str(rp))
    return [Path(x) for x in seen]

def _default_user_store() -> dict:
    return {
        "admin": {
            "display_name": "Quản trị tổng",
            "password": os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123"),
            "role": "admin",
            "regions": ["*"],
        }
    }

AUTH_USER_STORE_CACHE = {"signature": None, "source": None, "users": None}


def _auth_user_store_signature():
    for candidate in _auth_users_candidates():
        try:
            if candidate.exists():
                st = candidate.stat()
                return ("file", str(candidate.resolve()), int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))))
        except Exception:
            continue
    return ("default", str(os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")))


def _auth_store_source() -> str:
    sig = _auth_user_store_signature()
    if AUTH_USER_STORE_CACHE.get("signature") == sig and AUTH_USER_STORE_CACHE.get("source"):
        return AUTH_USER_STORE_CACHE["source"]
    source = "default"
    if sig and len(sig) >= 2 and sig[0] == "file":
        source = str(sig[1])
    AUTH_USER_STORE_CACHE["signature"] = sig
    AUTH_USER_STORE_CACHE["source"] = source
    return source

def _normalize_region_list(values) -> list[str]:
    values = values if isinstance(values, list) else ([values] if values not in [None, ""] else [])
    out = []
    for item in values:
        canon = canon_region_name(item)
        if canon is None:
            continue
        canon = str(canon).strip()
        if canon:
            out.append(canon)
    return list(dict.fromkeys(out))

def _normalize_auth_user_record(username: str, raw: dict) -> dict:
    raw = raw or {}
    regions = raw.get("regions", raw.get("region", []))
    if raw.get("all_regions") is True:
        regions = ["*"]
    if isinstance(regions, str):
        regions = [regions]
    role_raw = str(raw.get("role", "")).strip().lower()
    regions_norm = _normalize_region_list(regions)
    is_admin = role_raw in {"admin", "super", "global", "all"} or ("*" in [str(x).strip() for x in regions if x is not None])
    return {
        "username": str(username).strip(),
        "display_name": str(raw.get("display_name") or raw.get("full_name") or username).strip(),
        "role": "admin" if is_admin else "region",
        "regions": [] if is_admin else regions_norm,
        "password": raw.get("password"),
        "password_hash": raw.get("password_hash"),
        "is_active": bool(raw.get("is_active", True)),
    }

def load_auth_user_store() -> dict:
    sig = _auth_user_store_signature()
    if AUTH_USER_STORE_CACHE.get("signature") == sig and isinstance(AUTH_USER_STORE_CACHE.get("users"), dict):
        return AUTH_USER_STORE_CACHE["users"]

    store = None
    for candidate in _auth_users_candidates():
        try:
            if candidate.exists():
                store = json.loads(candidate.read_text(encoding="utf-8"))
                break
        except Exception:
            continue
    if store is None:
        store = _default_user_store()
    users = {}
    if isinstance(store, dict):
        for username, payload in store.items():
            rec = _normalize_auth_user_record(username, payload if isinstance(payload, dict) else {})
            if rec["username"] and rec.get("is_active", True):
                users[rec["username"]] = rec
    AUTH_USER_STORE_CACHE["signature"] = sig
    AUTH_USER_STORE_CACHE["source"] = "default" if not sig or sig[0] != "file" else str(sig[1])
    AUTH_USER_STORE_CACHE["users"] = users
    return users

def _verify_password(user_record: dict, password: str) -> bool:
    if not user_record:
        return False
    raw_password = "" if password is None else str(password)
    hashed = user_record.get("password_hash")
    if hashed:
        try:
            return bool(check_password_hash(str(hashed), raw_password))
        except Exception:
            return False
    plain = user_record.get("password")
    if plain is None:
        return False
    return hmac.compare_digest(str(plain), raw_password)

def current_auth_user() -> dict | None:
    if not has_request_context():
        return None
    raw = session.get("dash_auth_user")
    if not isinstance(raw, dict):
        return None
    username = str(raw.get("username", "")).strip()
    if not username:
        return None
    users = load_auth_user_store()
    rec = users.get(username)
    if rec is None:
        return None
    return {
        "username": rec["username"],
        "display_name": rec.get("display_name") or rec["username"],
        "role": rec.get("role", "region"),
        "regions": rec.get("regions", []),
    }

def current_user_region_scope():
    if not has_request_context():
        return None
    user = current_auth_user()
    if user is None:
        return []
    if user.get("role") == "admin":
        return None
    return _normalize_region_list(user.get("regions", []))

def user_can_access_region(region_name) -> bool:
    scope = current_user_region_scope()
    if scope is None:
        return True
    region = canon_region_name(region_name)
    if region is None:
        return False
    return str(region) in {str(x) for x in scope}

def filter_regions_for_current_user(regions) -> list[str]:
    values = _normalize_region_list(regions)
    scope = current_user_region_scope()
    if scope is None:
        return values
    scope_set = {str(x) for x in scope}
    return [r for r in values if str(r) in scope_set]

REGION_SCOPE_DF_CACHE = {}

def _region_scope_cache_key(scope):
    if scope is None:
        return None
    return tuple(sorted(str(x) for x in scope))

def apply_region_scope_to_df(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or not isinstance(dff, pd.DataFrame):
        return pd.DataFrame()
    scope = current_user_region_scope()
    cache_key = (_df_cache_signature(dff), _region_scope_cache_key(scope))
    cached = REGION_SCOPE_DF_CACHE.get(cache_key)
    if isinstance(cached, pd.DataFrame):
        return _return_df_cached(cached)

    out = dff
    if "khu_vuc" in out.columns and scope is not None:
        scope_set = {str(x) for x in scope}
        if not scope_set:
            out = out.iloc[0:0]
        else:
            out = out[out["khu_vuc"].astype(str).isin(scope_set)]

    if len(REGION_SCOPE_DF_CACHE) > DASH_REGION_SCOPE_CACHE_MAX:
        REGION_SCOPE_DF_CACHE.clear()
    REGION_SCOPE_DF_CACHE[cache_key] = out.copy(deep=False)
    return _return_df_cached(out)

def _is_safe_next_path(next_path: str | None) -> bool:
    if next_path is None:
        return False
    value = str(next_path).strip()
    return bool(value.startswith("/")) and not value.startswith("//")

LOGIN_PAGE_TEMPLATE = """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ app_title }}</title>
  <style>
    :root{
      --bg:#f5f7fb;
      --card:#ffffff;
      --text:#0f172a;
      --muted:#64748b;
      --green:#16a34a;
      --green-dark:#14532d;
      --border:#dfe5ef;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      min-height:100vh;
      display:flex;
      align-items:center;
      justify-content:center;
      padding:24px;
      background:linear-gradient(135deg,#0f172a 0%, #14532d 55%, #16a34a 100%);
      font-family:Arial, Helvetica, sans-serif;
      color:var(--text);
    }
    .shell{
      width:100%;
      max-width:460px;
      background:rgba(255,255,255,0.96);
      border:1px solid rgba(255,255,255,0.35);
      border-radius:28px;
      box-shadow:0 30px 60px rgba(15,23,42,0.26);
      overflow:hidden;
    }
    .hero{
      padding:22px 24px 12px;
      background:linear-gradient(180deg,rgba(22,163,74,0.08) 0%, rgba(255,255,255,0.0) 100%);
      text-align:center;
    }
    .logo{
      width:84px;
      height:84px;
      object-fit:contain;
      margin-bottom:12px;
    }
    h1{
      margin:0;
      font-size:24px;
      line-height:1.15;
      font-weight:900;
      color:#0f172a;
    }
    .sub{
      margin-top:8px;
      color:var(--muted);
      font-size:13px;
      line-height:1.55;
    }
    form{
      padding:20px 24px 24px;
    }
    label{
      display:block;
      font-size:12px;
      font-weight:800;
      color:#334155;
      margin-bottom:8px;
      text-transform:uppercase;
      letter-spacing:.4px;
    }
    input{
      width:100%;
      border:1px solid var(--border);
      border-radius:16px;
      padding:13px 14px;
      font-size:14px;
      outline:none;
      margin-bottom:14px;
      background:#ffffff;
    }
    input:focus{
      border-color:var(--green);
      box-shadow:0 0 0 4px rgba(22,163,74,0.10);
    }
    button{
      width:100%;
      border:none;
      border-radius:16px;
      padding:13px 14px;
      font-size:14px;
      font-weight:900;
      color:#ffffff;
      cursor:pointer;
      background:linear-gradient(135deg,var(--green) 0%, var(--green-dark) 100%);
      box-shadow:0 16px 30px rgba(22,163,74,0.18);
    }
    .error{
      margin-bottom:12px;
      padding:12px 14px;
      border-radius:14px;
      background:#fef2f2;
      color:#991b1b;
      border:1px solid #fecaca;
      font-size:13px;
      line-height:1.45;
    }
    .hint{
      margin-top:14px;
      padding:12px 14px;
      border-radius:14px;
      background:#f8fafc;
      color:#475569;
      border:1px solid #e2e8f0;
      font-size:12px;
      line-height:1.55;
    }
    .hint strong{
      color:#0f172a;
    }
    .login-build-signature{
      position:fixed;
      right:18px;
      bottom:14px;
      z-index:5;
      text-align:right;
      color:rgba(255,255,255,0.82);
      font-size:11px;
      line-height:1.45;
      letter-spacing:.25px;
      text-shadow:0 6px 18px rgba(15,23,42,0.36);
      user-select:none;
    }
    .login-build-signature strong{
      display:block;
      color:#ffffff;
      font-size:12px;
      font-weight:900;
      letter-spacing:.35px;
    }
    .login-build-signature span{
      display:block;
      font-weight:700;
      opacity:.92;
    }
    @media (max-width: 576px){
      .login-build-signature{
        left:18px;
        right:18px;
        bottom:10px;
        text-align:center;
        font-size:10px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      {% if logo_src %}
      <img src="{{ logo_src }}" alt="Logo công ty" class="logo">
      {% endif %}
      <h1>{{ app_title }}</h1>
      <div class="sub">Đăng nhập để mở dashboard. Tài khoản tổng xem toàn bộ dữ liệu, tài khoản khu vực chỉ xem đúng khu vực được phân quyền.</div>
    </div>
    <form method="post" action="{{ url_for('login') }}">
      <input type="hidden" name="next" value="{{ next_path }}">
      {% if error %}
      <div class="error">{{ error }}</div>
      {% endif %}
      <label for="username">Tài khoản</label>
      <input id="username" name="username" type="text" autocomplete="username" placeholder="Nhập tài khoản" required>
      <label for="password">Mật khẩu</label>
      <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Nhập mật khẩu" required>
      <button type="submit">Đăng nhập vào dashboard</button>
      {% if default_hint %}
      <div class="hint"><strong>Lưu ý:</strong> Chưa tìm thấy file <code>users.json</code>, hệ thống đang dùng user mặc định để bạn test nhanh: <strong>admin / admin123</strong>. Hãy tạo file <code>users.json</code> trước khi public.</div>
      {% endif %}
    </form>
  </div>
  <div class="login-build-signature">
    <strong>Dashboard engineered by Nguyen Huu Minh</strong>
    <span>Full-stack Dash Architecture • RBAC Matrix • DataOps Pipeline • Production Observability</span>
  </div>
</body>
</html>
"""
try:
    _excel_sheet_name_list = list(EXCEL_BOOK.sheet_names) if EXCEL_BOOK is not None else []
    _excel_sheet_names = set(_excel_sheet_name_list)
except Exception:
    _excel_sheet_name_list = []
    _excel_sheet_names = set()

_OPTIONAL_SHEET_CACHE = {}
_OPTIONAL_SHEET_SAMPLE_CACHE = {}
_OPTIONAL_SHEET_RESOLVE_CACHE = {}

def _sheet_name_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm_text(value or ""))

def _sheet_compact_name(value) -> str:
    return _sheet_name_key(value)

def _parse_optional_sheet_cached(sheet_name: str, sample_only: bool = False):
    cache = _OPTIONAL_SHEET_SAMPLE_CACHE if sample_only else _OPTIONAL_SHEET_CACHE
    cache_key = str(sheet_name)
    if cache_key not in cache:
        cached_df = None if sample_only else _parse_cached_sheet(sheet_name)
        if isinstance(cached_df, pd.DataFrame):
            cache[cache_key] = cached_df
        elif EXCEL_BOOK is not None and sheet_name in _excel_sheet_names:
            started = time.perf_counter()
            if sample_only:
                cache[cache_key] = EXCEL_BOOK.parse(sheet_name=sheet_name, nrows=12)
            else:
                cache[cache_key] = EXCEL_BOOK.parse(sheet_name=sheet_name)
            if DASH_LOG_BOOT_TIMING:
                _perf_log(f"read_optional_excel:{sheet_name}", started, f"sample={sample_only} rows={len(cache[cache_key]) if isinstance(cache.get(cache_key), pd.DataFrame) else '-'}")
        else:
            cache[cache_key] = None
    cached = cache.get(cache_key)
    return _return_df_cached(cached) if isinstance(cached, pd.DataFrame) else cached

_OPTIONAL_SHEET_ALIAS_COMPACT = {
    "xdt": [
        "xdt", "xe dt", "xe_dt", "phuong tien xdt",
        "phuong tien xe truc thuoc", "xe truc thuoc", "truc thuoc",
        "xe cong ty", "xe thuoc cong ty", "xe so huu", "so huu",
        "phuong tien xe dien", "xe dien", "dien",
        "owned fleet", "owned vehicle", "company vehicle", "fleet owned", "vehicle owned",
    ],
    "xpq": [
        "xpq", "xe pq", "xe_pq", "phuong tien xpq",
        "phuong tien xe phan quyen", "xe phan quyen", "phan quyen",
        "uy quyen", "thuong quyen", "nhuong quyen", "xe hop tac", "hop tac",
        "xe doi tac", "doi tac", "xe tra gop", "tra gop",
        "phuong tien xe xang", "xe xang", "xang",
        "delegated fleet", "delegated vehicle", "franchise fleet", "partner vehicle",
    ],
}
_OPTIONAL_SHEET_ALIAS_COMPACT = {
    k: [_sheet_compact_name(v) for v in vals if _sheet_compact_name(v)]
    for k, vals in _OPTIONAL_SHEET_ALIAS_COMPACT.items()
}

def _vehicle_sample_score(sample_df: pd.DataFrame | None) -> int:
    if sample_df is None or not isinstance(sample_df, pd.DataFrame) or sample_df.empty:
        return 0
    cols = [norm_text(c) for c in sample_df.columns]
    probes = [
        "bien kiem soat", "bien so", "bks", "license plate", "plate",
        "so tai", "ma tai", "vehicle no", "taxi no",
        "loai xe", "dong xe", "model", "nhan hieu", "hang xe",
        "so cho", "cho ngoi", "suc chua", "seat",
        "nhien lieu", "fuel", "dien xang",
        "khu vuc", "chi nhanh", "don vi", "region",
        "nhom xe", "phan loai xe", "hinh thuc so huu", "hinh thuc quan ly",
    ]
    score = 0
    for probe in probes:
        if any(probe in c or c in probe for c in cols):
            score += 1
    return score

def _vehicle_sample_has_usable_columns(sample_df: pd.DataFrame | None) -> bool:
    return _vehicle_sample_score(sample_df) >= 2

def _read_optional_sheet(candidates, menu_key: str | None = None):
    candidates = candidates if isinstance(candidates, list) else ([candidates] if candidates else [])
    # Production fast path: try cache files by candidate sheet name before touching Excel.
    # This is intentionally allowed for menu_key too, so Vercel can serve fleet/HR/Biz
    # from prebuilt cache without opening the large workbook on cold start.
    if DASH_PREFER_PARQUET_CACHE:
        for candidate in candidates:
            cached_df = _parse_cached_sheet(str(candidate).strip())
            if isinstance(cached_df, pd.DataFrame):
                return _return_df_cached(cached_df)
    if EXCEL_BOOK is None and not _ensure_excel_book_opened():
        return None
    resolve_key = (tuple(str(x).strip() for x in candidates), str(menu_key or ""), tuple(map(str, _excel_sheet_name_list)))
    resolved_sheet_name = _OPTIONAL_SHEET_RESOLVE_CACHE.get(resolve_key, "__cache_miss__")
    if resolved_sheet_name != "__cache_miss__":
        return _parse_optional_sheet_cached(resolved_sheet_name) if resolved_sheet_name else None
    if not candidates and menu_key not in _OPTIONAL_SHEET_ALIAS_COMPACT:
        _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = None
        return None
    try:
        sheet_names = list(_excel_sheet_name_list or EXCEL_BOOK.sheet_names)
        exact_map = {str(x).strip(): x for x in sheet_names}
        norm_map = {_sheet_compact_name(x): x for x in sheet_names}

        for sheet_name in candidates:
            candidate = str(sheet_name).strip()
            if candidate and candidate in exact_map:
                _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = exact_map[candidate]
                if len(_OPTIONAL_SHEET_RESOLVE_CACHE) > DASH_OPTIONAL_SHEET_RESOLVE_CACHE_MAX:
                    _OPTIONAL_SHEET_RESOLVE_CACHE.clear()
                return _parse_optional_sheet_cached(exact_map[candidate])

        for sheet_name in candidates:
            candidate_key = _sheet_compact_name(sheet_name)
            actual_sheet = norm_map.get(candidate_key)
            if actual_sheet:
                _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = actual_sheet
                if len(_OPTIONAL_SHEET_RESOLVE_CACHE) > DASH_OPTIONAL_SHEET_RESOLVE_CACHE_MAX:
                    _OPTIONAL_SHEET_RESOLVE_CACHE.clear()
                return _parse_optional_sheet_cached(actual_sheet)

        scored = []
        for real_name in sheet_names:
            compact = _sheet_compact_name(real_name)
            if not compact:
                continue
            best_score = 0
            for idx, candidate in enumerate(candidates):
                ckey = _sheet_compact_name(candidate)
                if len(ckey) < 5:
                    continue
                if ckey in compact or compact in ckey:
                    best_score = max(best_score, 70 - idx)
            if best_score > 0:
                scored.append((best_score, real_name))
        if scored:
            scored = sorted(scored, key=lambda x: (-x[0], sheet_names.index(x[1])))
            _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = scored[0][1]
            if len(_OPTIONAL_SHEET_RESOLVE_CACHE) > DASH_OPTIONAL_SHEET_RESOLVE_CACHE_MAX:
                _OPTIONAL_SHEET_RESOLVE_CACHE.clear()
            return _parse_optional_sheet_cached(scored[0][1])

        if menu_key in _OPTIONAL_SHEET_ALIAS_COMPACT:
            aliases = list(_OPTIONAL_SHEET_ALIAS_COMPACT.get(menu_key, []))
            aliases.extend([_sheet_compact_name(x) for x in candidates if _sheet_compact_name(x)])
            scored = []
            for real_name in sheet_names:
                compact = _sheet_compact_name(real_name)
                if not compact:
                    continue
                best_score = 0
                for idx, alias in enumerate(aliases):
                    if len(alias) < 2:
                        continue
                    if alias in compact:
                        best_score = max(best_score, 120 - idx)
                if best_score > 0:
                    sample = _parse_optional_sheet_cached(real_name, sample_only=True)
                    best_score += min(_vehicle_sample_score(sample), 12)
                    scored.append((best_score, real_name))
            if scored:
                scored = sorted(scored, key=lambda x: (-x[0], sheet_names.index(x[1])))
                _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = scored[0][1]
                if len(_OPTIONAL_SHEET_RESOLVE_CACHE) > DASH_OPTIONAL_SHEET_RESOLVE_CACHE_MAX:
                    _OPTIONAL_SHEET_RESOLVE_CACHE.clear()
                return _parse_optional_sheet_cached(scored[0][1])
        _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = None
    except Exception as e:
        try:
            DATA_LOAD_ERRORS.append(f"optional_sheet:{menu_key or 'generic'}: {e}")
        except Exception:
            pass
        _OPTIONAL_SHEET_RESOLVE_CACHE[resolve_key] = None
        return None
    return None

def _discover_vehicle_generic_sheet() -> pd.DataFrame | None:
    if EXCEL_BOOK is None:
        return None
    try:
        sheet_names = list(_excel_sheet_name_list or EXCEL_BOOK.sheet_names)
        vehicle_name_tokens = [
            "phuongtien", "quanlyphuongtien", "danhsachphuongtien", "tonghopphuongtien",
            "danhsachxe", "quanlyxe", "phuongtienkvthang", "xekvthang",
            "vehicle", "vehicles", "fleet", "carlist",
        ]
        scored = []
        for real_name in sheet_names:
            compact = _sheet_compact_name(real_name)
            name_score = 0
            for idx, token in enumerate(vehicle_name_tokens):
                token_key = _sheet_compact_name(token)
                if token_key and token_key in compact:
                    name_score = max(name_score, 100 - idx)
            if compact in {"xe", "car", "cars", "fleet"}:
                name_score = max(name_score, 80)
            sample = _parse_optional_sheet_cached(real_name, sample_only=True)
            col_score = _vehicle_sample_score(sample)
            if name_score > 0 or col_score >= 4:
                scored.append((name_score + min(col_score, 16) * 8, real_name))
        if not scored:
            return None
        scored = sorted(scored, key=lambda x: (-x[0], sheet_names.index(x[1])))
        return _parse_optional_sheet_cached(scored[0][1])
    except Exception as e:
        try:
            DATA_LOAD_ERRORS.append(f"vehicle_generic_discovery: {e}")
        except Exception:
            pass
        return None

def _prepare_optional_menu_df(raw_df: pd.DataFrame | None) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return _empty_dashboard_df("dt")
    dff = raw_df.copy()
    if "thang_nam" not in dff.columns:
        month_col = find_col(dff, ["thang_nam", "thang", "month", "month_date", "period"])
        if month_col:
            dff["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce")
    if "thang_nam" not in dff.columns:
        return _empty_dashboard_df("dt")
    if "khu_vuc" not in dff.columns:
        region_col = find_col(dff, ["khu_vuc", "region", "kv", "area"])
        if region_col:
            dff["khu_vuc"] = dff[region_col]
    if "khu_vuc" not in dff.columns:
        dff["khu_vuc"] = "Tổng hợp"
    metric_col = find_col(dff, ["tong_doanh_thu", "gia_tri", "chi_phi", "diem", "tong_gia_tri", "value"])
    count_col = find_col(dff, ["tong_so_cuoc", "so_luong", "so_nhan_vien", "so_tai_xe", "so_xe", "count"])
    if metric_col and metric_col != "tong_doanh_thu":
        dff["tong_doanh_thu"] = pd.to_numeric(dff[metric_col], errors="coerce").fillna(0)
    elif "tong_doanh_thu" not in dff.columns:
        dff["tong_doanh_thu"] = 0
    if count_col and count_col != "tong_so_cuoc":
        dff["tong_so_cuoc"] = pd.to_numeric(dff[count_col], errors="coerce").fillna(0)
    elif "tong_so_cuoc" not in dff.columns:
        dff["tong_so_cuoc"] = 0
    dff["thang_nam"] = pd.to_datetime(dff["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff["thang_nam_vn"] = to_vn_datetime(dff["thang_nam"])
    dff["thang_nam_vn"] = pd.to_datetime(dff["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()
    dff["thang_label"] = dff["thang_nam_vn"].dt.strftime("%m/%Y")
    dff["nam"] = dff["thang_nam_vn"].dt.year
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name)
    cols = ["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc"]
    extra_cols = [c for c in dff.columns if c not in cols]
    return dff[cols + extra_cols].copy()


def _parse_vehicle_seat_series(series_like: pd.Series) -> pd.Series:
    s = pd.Series(series_like).astype(str).str.extract(r"(\d+)")[0]
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _parse_vehicle_month_series(series_like) -> pd.Series:
    raw = pd.Series(series_like)
    try:
        parsed = pd.to_datetime(raw, errors="coerce", dayfirst=True)
    except Exception:
        parsed = pd.Series([pd.NaT] * len(raw), index=raw.index)
    try:
        numeric_raw = pd.to_numeric(raw, errors="coerce")
        if numeric_raw.notna().any():
            excel_serial = pd.to_datetime(numeric_raw, errors="coerce", unit="D", origin="1899-12-30")
            serial_ok = excel_serial.dt.year.between(2021, int(_now_vn_naive().year) + 1, inclusive="both")
            parsed_year = pd.to_datetime(parsed, errors="coerce").dt.year
            parsed_bad = parsed.isna() | parsed_year.lt(2021) | parsed_year.gt(int(_now_vn_naive().year) + 1)
            parsed = parsed.mask(parsed_bad & serial_ok, excel_serial)
    except Exception:
        pass
    try:
        return pd.to_datetime(parsed, errors="coerce").dt.to_period("M").dt.to_timestamp()
    except Exception:
        return pd.Series([pd.NaT] * len(raw), index=raw.index)


def _vehicle_text_value_mask(series_like, aliases: list[str]) -> pd.Series:
    s = pd.Series(series_like).fillna("").astype(str).map(lambda x: _sheet_compact_name(x))
    aliases = [_sheet_compact_name(a) for a in aliases if _sheet_compact_name(a)]
    if not aliases:
        return pd.Series([False] * len(s), index=s.index)
    mask = pd.Series([False] * len(s), index=s.index)
    for alias in aliases:
        if alias:
            mask = mask | s.str.contains(re.escape(alias), na=False)
    return mask



VEHICLE_SCOPE_COLUMN_CANDIDATES = [
    "nhom_phuong_tien", "nhom phuong tien", "nhom_xe", "nhom xe",
    "loai_so_huu", "loai so huu", "hinh_thuc_so_huu", "hinh thuc so huu",
    "hinh_thuc_quan_ly", "hinh thuc quan ly", "loai_quan_ly", "loai quan ly",
    "phan_loai_xe", "phan loai xe", "loai_hinh_xe", "loai hinh xe",
    "nguon_xe", "nguon xe", "hinh_thuc_khai_thac", "hinh thuc khai thac",
    "loai_khai_thac", "loai khai thac", "nhom_nhien_lieu", "nhom nhien lieu",
    "nhien_lieu", "nhien lieu", "loai_nhien_lieu", "loai nhien lieu",
    "dien_xang", "dien xang", "fuel", "fuel_type", "energy_type",
    "loai_xe", "loai xe", "loai_phuong_tien", "loai phuong tien",
    "dong_xe", "dong xe", "ten_loai_xe", "ten loai xe", "model",
    "ownership", "owner_type", "fleet_type", "vehicle_group", "vehicle_type_group",
]


def _vehicle_scope_candidate_columns(raw_df: pd.DataFrame) -> list[str]:
    if raw_df is None or raw_df.empty:
        return []
    cols = []
    for cand in VEHICLE_SCOPE_COLUMN_CANDIDATES:
        col = find_col_fuzzy(raw_df, [cand])
        if col is not None and col in raw_df.columns and col not in cols:
            cols.append(col)
    name_markers = [
        "nhom", "loai", "phan loai", "so huu", "quan ly", "nguon", "khai thac",
        "nhien lieu", "dien xang", "fuel", "energy", "ownership", "fleet", "vehicle",
    ]
    for col in raw_df.columns:
        cn = norm_text(col)
        if any(marker in cn for marker in name_markers) and col not in cols:
            cols.append(col)
    return cols


def _vehicle_aliases_for_menu(menu_key: str | None) -> list[str]:
    if menu_key == "xdt":
        return [
            "xdt", "xe dt", "xe truc thuoc", "truc thuoc", "xe cong ty", "cong ty",
            "thuoc cong ty", "so huu", "tai san", "xe so huu", "xe dien", "dien",
            "owned", "company", "company vehicle", "owned fleet", "owned vehicle",
        ]
    if menu_key == "xpq":
        return [
            "xpq", "xe pq", "xe phan quyen", "phan quyen", "uy quyen", "u y quyen",
            "thuong quyen", "nhuong quyen", "hop tac", "doi tac", "tra gop",
            "xe xang", "xang", "delegated", "franchise", "partner",
        ]
    return []


def _vehicle_scope_mask_any_column(raw_df: pd.DataFrame, menu_key: str | None):
    if raw_df is None or raw_df.empty or menu_key not in {"xdt", "xpq"}:
        return None
    aliases = _vehicle_aliases_for_menu(menu_key)
    if not aliases:
        return None
    mask = pd.Series(False, index=raw_df.index)
    matched_any_column = False
    for col in _vehicle_scope_candidate_columns(raw_df):
        try:
            col_mask = _vehicle_text_value_mask(raw_df[col], aliases)
            if bool(col_mask.any()):
                mask = mask | col_mask
                matched_any_column = True
        except Exception:
            continue
    return mask if matched_any_column and bool(mask.any()) else None




def _vehicle_wide_count_column(raw_df: pd.DataFrame, menu_key: str | None):
    """Detect real wide-format count columns such as 'Xe trực thuộc' or 'Số xe phân quyền'."""
    if raw_df is None or raw_df.empty or menu_key not in {"xdt", "xpq"}:
        return None
    aliases = [_sheet_compact_name(x) for x in _vehicle_aliases_for_menu(menu_key) if _sheet_compact_name(x)]
    if not aliases:
        return None
    blocked = [
        "tien", "doanhthu", "chiphi", "dongia", "tyle", "tile", "phantram", "pct", "percent",
        "socho", "tongsocho", "seat", "seats", "succhua", "bienso", "bienkiemsoat", "bks",
        "sotai", "matai", "ngay", "date", "thangnam", "thang", "nam", "year",
    ]
    count_markers = ["soluong", "sl", "soxe", "tongxe", "count", "quantity", "vehiclecount", "fleetcount", "xe"]
    best_col = None
    best_score = -1
    for col in raw_df.columns:
        ckey = _sheet_compact_name(col)
        if not ckey:
            continue
        if not any(alias in ckey for alias in aliases):
            continue
        if any(bad in ckey for bad in blocked):
            continue
        numeric = pd.to_numeric(raw_df[col], errors="coerce")
        numeric_n = int(numeric.notna().sum())
        if numeric_n <= 0:
            continue
        score = numeric_n
        if float(numeric.fillna(0).abs().sum()) > 0:
            score += 100
        if any(marker in ckey for marker in count_markers):
            score += 25
        if score > best_score:
            best_score = score
            best_col = col
    return best_col


def _extract_vehicle_wide_category_df(raw_df: pd.DataFrame, menu_key: str | None) -> pd.DataFrame:
    """Convert a real summary sheet with XDT/XPQ columns into the standard vehicle input frame."""
    if raw_df is None or raw_df.empty or menu_key not in {"xdt", "xpq"}:
        return pd.DataFrame()
    count_col = _vehicle_wide_count_column(raw_df, menu_key)
    if count_col is None:
        return pd.DataFrame()

    month_col = find_col_fuzzy(raw_df, [
        "thang_nam", "tháng năm", "thang/nam", "tháng/năm", "thang nam", "tháng", "thang",
        "month", "month_date", "period", "ky_bao_cao", "kỳ báo cáo", "ngay_du_lieu", "ngày dữ liệu",
        "ngay_bao_cao", "ngày báo cáo", "report_date", "ngay_cap_nhat", "ngày cập nhật",
    ])
    year_col = find_col_fuzzy(raw_df, ["nam", "năm", "year", "report_year", "nam_bao_cao", "năm báo cáo"])
    region_col = find_col_fuzzy(raw_df, [
        "khu_vuc", "khu vực", "khu vuc", "region", "kv", "area", "ten_khu_vuc", "tên khu vực",
        "chi_nhanh", "chi nhánh", "chi nhanh", "don_vi", "đơn vị", "don vi", "tram", "trạm", "tuyen", "tuyến",
    ])
    type_col = find_col_fuzzy(raw_df, [
        "loai_xe", "loại xe", "loai xe", "dong_xe", "dòng xe", "dong xe", "model",
        "nhan_hieu", "nhãn hiệu", "hang_xe", "hãng xe", "ten_loai_xe", "tên loại xe",
    ])
    fuel_col = find_col_fuzzy(raw_df, ["nhien_lieu", "nhiên liệu", "loai_nhien_lieu", "loại nhiên liệu", "fuel", "fuel_type"])
    seat_col = find_col_fuzzy(raw_df, ["so_cho", "số chỗ", "so cho", "seat", "seats", "seat_count", "suc_chua", "sức chứa"])

    out = pd.DataFrame(index=raw_df.index)
    if month_col is not None:
        try:
            month_num = pd.to_numeric(raw_df[month_col], errors="coerce")
            year_num = pd.to_numeric(raw_df[year_col], errors="coerce") if year_col is not None else pd.Series(np.nan, index=raw_df.index)
            numeric_month_ok = month_num.between(1, 12, inclusive="both") & year_num.between(2020, int(_now_vn_naive().year) + 1, inclusive="both")
            rebuilt = pd.to_datetime(dict(year=year_num.fillna(_now_vn_naive().year).astype(int), month=month_num.fillna(1).astype(int), day=1), errors="coerce")
            out["thang_nam"] = raw_df[month_col]
            out.loc[numeric_month_ok, "thang_nam"] = rebuilt.loc[numeric_month_ok]
        except Exception:
            out["thang_nam"] = raw_df[month_col]
    elif year_col is not None:
        try:
            y = pd.to_numeric(raw_df[year_col], errors="coerce").fillna(_now_vn_naive().year).astype(int)
            out["thang_nam"] = pd.to_datetime(dict(year=y, month=1, day=1), errors="coerce")
        except Exception:
            out["thang_nam"] = _current_vn_month_start()
    else:
        out["thang_nam"] = _current_vn_month_start()

    out["khu_vuc"] = raw_df[region_col] if region_col else "Tổng hợp"
    out["loai_xe"] = raw_df[type_col] if type_col else ("Tổng xe trực thuộc" if menu_key == "xdt" else "Tổng xe phân quyền")
    out["nhom_nhien_lieu"] = raw_df[fuel_col] if fuel_col else "Chưa rõ nhiên liệu"
    out["so_luong_xe"] = pd.to_numeric(raw_df[count_col], errors="coerce").fillna(0)
    if seat_col:
        out["so_cho"] = raw_df[seat_col]
    out = out[pd.to_numeric(out["so_luong_xe"], errors="coerce").fillna(0).abs() > 0].copy()
    try:
        VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"wide:{count_col}")
    except Exception:
        pass
    return out

def _filter_vehicle_scope_by_menu(dff: pd.DataFrame, menu_key: str | None) -> pd.DataFrame:
    if menu_key not in {"xdt", "xpq"} or dff is None or dff.empty:
        return dff
    mask = _vehicle_scope_mask_any_column(dff, menu_key)
    if mask is not None and bool(mask.any()):
        return dff.loc[mask].copy()
    return dff

def _series_numeric_or_presence(series_like, default_value=0) -> pd.Series:
    s = pd.Series(series_like)
    numeric = pd.to_numeric(s, errors="coerce")
    if len(s) > 0 and numeric.notna().sum() >= max(1, int(len(s) * 0.65)):
        return numeric.fillna(0)
    present = s.fillna("").astype(str).str.strip().ne("")
    return present.astype(float).where(present, float(default_value))


def _prepare_vehicle_menu_df(raw_df: pd.DataFrame | None, menu_key: str | None = None) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return _empty_dashboard_df("dt")
    dff = raw_df.copy()
    dff = _filter_vehicle_scope_by_menu(dff, menu_key)
    if dff.empty:
        return _empty_dashboard_df("dt")

    month_col = find_col_fuzzy(dff, [
        "thang_nam", "tháng năm", "thang/nam", "tháng/năm", "thang nam", "tháng", "thang",
        "month", "month_date", "period", "ky_bao_cao", "kỳ báo cáo", "ngay_du_lieu", "ngày dữ liệu",
        "ngay_bao_cao", "ngày báo cáo", "report_date",
        "updatedat", "updated_at", "ngay_cap_nhat", "ngày cập nhật", "ngay cap nhat",
        "createdat", "created_at", "ngay_tao", "ngày tạo", "ngay tao",
    ])
    year_col = find_col_fuzzy(dff, ["nam", "năm", "year", "report_year", "nam_bao_cao", "năm báo cáo"])
    if month_col is not None:
        parsed_months = _parse_vehicle_month_series(dff[month_col])
        try:
            month_num = pd.to_numeric(dff[month_col], errors="coerce")
            year_num = pd.to_numeric(dff[year_col], errors="coerce") if year_col is not None else pd.Series(np.nan, index=dff.index)
            numeric_month_ok = month_num.between(1, 12, inclusive="both") & year_num.between(2020, int(_now_vn_naive().year) + 1, inclusive="both")
            parsed_year = pd.to_datetime(parsed_months, errors="coerce").dt.year
            parsed_bad = parsed_months.isna() | parsed_year.lt(2020) | parsed_year.gt(int(_now_vn_naive().year) + 1)
            rebuilt = pd.to_datetime(dict(year=year_num.fillna(_now_vn_naive().year).astype(int), month=month_num.fillna(1).astype(int), day=1), errors="coerce")
            parsed_months = parsed_months.mask(numeric_month_ok & parsed_bad, rebuilt)
        except Exception:
            pass
        dff["thang_nam"] = parsed_months.where(parsed_months.notna(), _current_vn_month_start())
    else:
        dff["thang_nam"] = _current_vn_month_start()

    dff["thang_nam"] = pd.to_datetime(dff["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff = dff[dff["thang_nam"].notna()].copy()
    if dff.empty:
        return _empty_dashboard_df("dt")

    region_col = find_col_fuzzy(dff, [
        "khu_vuc", "khu vực", "khu vuc", "region", "kv", "area", "ten_khu_vuc", "tên khu vực",
        "chi_nhanh", "chi nhánh", "chi nhanh", "don_vi", "đơn vị", "don vi", "tram", "trạm", "tuyen", "tuyến",
    ])
    type_col = find_col_fuzzy(dff, [
        "loai_xe", "loại xe", "loai xe", "loai_phuong_tien", "loại phương tiện", "loai phuong tien",
        "dong_xe", "dòng xe", "dong xe", "model", "vehicle_model",
        "nhan_hieu", "nhãn hiệu", "nhan hieu", "hang_xe", "hãng xe", "hang xe", "ten_loai_xe", "tên loại xe",
    ])
    fuel_col = find_col_fuzzy(dff, [
        "nhom_nhien_lieu", "nhóm nhiên liệu", "nhom nhien lieu", "nhien_lieu", "nhiên liệu", "nhien lieu",
        "loai_nhien_lieu", "loại nhiên liệu", "loai nhien lieu",
        "dien_xang", "điện xăng", "dien xang", "fuel", "fuel_type", "energy_type",
    ])

    count_col = find_col_fuzzy(dff, [
        "so_luong_xe", "số lượng xe", "so luong xe", "so_xe", "số xe", "so xe",
        "tong_so_cuoc", "so_luong", "số lượng", "soluong", "quantity", "count", "sl",
    ])
    seat_total_col = find_col_fuzzy(dff, [
        "tong_so_cho", "tổng số chỗ", "tong so cho", "so_cho_tong", "số chỗ tổng", "so cho tong",
        "tong_cho", "tổng chỗ", "tong cho", "total_seats",
    ])
    seat_avg_col = find_col_fuzzy(dff, [
        "so_cho_binh_quan_xe", "số chỗ bình quân xe", "so cho binh quan xe", "avg_seat_per_vehicle", "avg_seats",
    ])
    seat_value_col = find_col_fuzzy(dff, [
        "so_cho", "số chỗ", "so cho", "socho", "cho_ngoi", "chỗ ngồi", "cho ngoi",
        "seat", "seats", "seat_count", "suc_chua", "sức chứa",
    ])
    plate_count_col = find_col_fuzzy(dff, [
        "so_bien_kiem_soat", "số biển kiểm soát", "so bien kiem soat",
        "bien_kiem_soat", "biển kiểm soát", "bien_so", "biển số",
        "so_bks", "bks", "count_plate", "license_plate", "plate", "plate_count", "bien_so_count",
    ])
    sotai_count_col = find_col_fuzzy(dff, [
        "so_so_tai", "số số tài", "so so tai", "so_tai", "số tài", "so tai",
        "ma_tai", "mã tài", "ma tai", "so_tai_distinct", "count_so_tai", "vehicle_no", "taxi_no", "so_tai_count",
    ])

    dff["khu_vuc"] = dff[region_col] if region_col else "Tổng hợp"
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")

    dff["loai_xe"] = dff[type_col] if type_col else "Chưa rõ loại xe"
    dff["loai_xe"] = dff["loai_xe"].fillna("Chưa rõ loại xe").astype(str).str.strip()
    dff.loc[dff["loai_xe"].eq(""), "loai_xe"] = "Chưa rõ loại xe"

    dff["nhom_nhien_lieu"] = dff[fuel_col] if fuel_col else "Chưa rõ nhiên liệu"
    dff["nhom_nhien_lieu"] = dff["nhom_nhien_lieu"].fillna("Chưa rõ nhiên liệu").astype(str).str.strip()
    dff.loc[dff["nhom_nhien_lieu"].eq(""), "nhom_nhien_lieu"] = "Chưa rõ nhiên liệu"

    if count_col:
        count_series = pd.to_numeric(dff[count_col], errors="coerce")
        dff["so_luong_xe"] = count_series.where(count_series > 0, np.nan).fillna(1)
    elif plate_count_col:
        dff["so_luong_xe"] = _series_numeric_or_presence(dff[plate_count_col], default_value=1).replace(0, 1)
    elif sotai_count_col:
        dff["so_luong_xe"] = _series_numeric_or_presence(dff[sotai_count_col], default_value=1).replace(0, 1)
    else:
        dff["so_luong_xe"] = 1

    if seat_total_col:
        dff["tong_so_cho"] = pd.to_numeric(dff[seat_total_col], errors="coerce").fillna(0)
    elif seat_value_col:
        seats_each = _parse_vehicle_seat_series(dff[seat_value_col])
        dff["tong_so_cho"] = seats_each * pd.to_numeric(dff["so_luong_xe"], errors="coerce").fillna(1)
    else:
        dff["tong_so_cho"] = 0

    if plate_count_col:
        dff["so_bien_kiem_soat"] = _series_numeric_or_presence(dff[plate_count_col], default_value=0)
    else:
        dff["so_bien_kiem_soat"] = dff["so_luong_xe"]

    if sotai_count_col:
        dff["so_so_tai"] = _series_numeric_or_presence(dff[sotai_count_col], default_value=0)
    else:
        dff["so_so_tai"] = dff["so_luong_xe"]

    if seat_avg_col:
        dff["so_cho_binh_quan_xe"] = pd.to_numeric(dff[seat_avg_col], errors="coerce").fillna(0)
    else:
        dff["so_cho_binh_quan_xe"] = np.where(dff["so_luong_xe"] > 0, dff["tong_so_cho"] / dff["so_luong_xe"], 0)

    dff["tong_doanh_thu"] = dff["so_luong_xe"]
    dff["tong_so_cuoc"] = dff["tong_so_cho"]

    group_cols = ["thang_nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu"]
    dff = dff.groupby(group_cols, as_index=False).agg(
        so_luong_xe=("so_luong_xe", "sum"),
        tong_so_cho=("tong_so_cho", "sum"),
        so_bien_kiem_soat=("so_bien_kiem_soat", "sum"),
        so_so_tai=("so_so_tai", "sum"),
    )
    dff["so_cho_binh_quan_xe"] = np.where(dff["so_luong_xe"] > 0, dff["tong_so_cho"] / dff["so_luong_xe"], 0)
    dff["so_cho_loc"] = pd.to_numeric(dff["so_cho_binh_quan_xe"], errors="coerce").fillna(0).round().astype(int)
    dff.loc[dff["so_cho_loc"] < 0, "so_cho_loc"] = 0
    dff["nhan_so_cho"] = np.where(dff["so_cho_loc"] > 0, dff["so_cho_loc"].astype(str) + " chỗ", "Chưa rõ số chỗ")
    dff["tong_doanh_thu"] = dff["so_luong_xe"]
    dff["tong_so_cuoc"] = dff["tong_so_cho"]

    dff["thang_nam_vn"] = to_vn_datetime(dff["thang_nam"])
    dff["thang_nam_vn"] = pd.to_datetime(dff["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()
    dff["thang_label"] = dff["thang_nam_vn"].dt.strftime("%m/%Y")
    dff["nam"] = dff["thang_nam_vn"].dt.year

    ordered_cols = [
        "thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc",
        "loai_xe", "nhom_nhien_lieu",
        "so_luong_xe", "tong_so_cho", "so_cho_binh_quan_xe", "so_cho_loc", "nhan_so_cho",
        "so_bien_kiem_soat", "so_so_tai",
        "tong_doanh_thu", "tong_so_cuoc"
    ]
    extra_cols = [c for c in dff.columns if c not in ordered_cols]
    return dff[ordered_cols + extra_cols].copy()


def _prepare_marketing_menu_df(raw_df: pd.DataFrame | None) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return _empty_dashboard_df("dt")
    dff = raw_df.copy()

    month_col = find_col(dff, ["thang_nam", "thang/nam", "thang nam", "thang", "month", "month_date", "period"])
    if month_col is None:
        return _empty_dashboard_df("dt")
    dff["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff = dff[dff["thang_nam"].notna()].copy()
    if dff.empty:
        return _empty_dashboard_df("dt")

    region_col = find_col(dff, ["khu_vuc", "khu vuc", "region", "kv", "area"])
    dff["khu_vuc"] = dff[region_col] if region_col else "Tổng hợp"
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")

    amount_col = find_col(dff, ["tong_doanh_thu", "tong_phai_chi", "tong phai chi", "chi_phi", "tong_tien", "tong tien", "gia_tri", "value"])
    count_col = find_col(dff, ["tong_so_cuoc", "so_diem_tiep_thi", "so diem tiep thi", "so_luong", "so_diem", "count"])

    dff["tong_doanh_thu"] = pd.to_numeric(dff[amount_col], errors="coerce").fillna(0) if amount_col else 0
    dff["tong_so_cuoc"] = pd.to_numeric(dff[count_col], errors="coerce").fillna(0) if count_col else 0
    dff["tong_phai_chi"] = pd.to_numeric(dff.get("tong_phai_chi", dff["tong_doanh_thu"]), errors="coerce").fillna(0)
    dff["so_diem_tiep_thi"] = pd.to_numeric(dff.get("so_diem_tiep_thi", dff["tong_so_cuoc"]), errors="coerce").fillna(0)

    numeric_candidates = [
        "tong_phai_chi", "so_diem_tiep_thi", "so_ho_so_hoa_hong",
        "tong_da_chi_du", "tong_chua_chi_du", "tong_khong_chi",
        "so_ho_so_da_chi_du", "so_ho_so_chua_chi_du", "so_ho_so_khong_chi",
        "so_diem_moi_ky_hd", "so_loai_hinh_kd", "chi_phi_binh_quan_moi_diem", "chi_phi_binh_quan_moi_ho_so"
    ]
    for c in numeric_candidates:
        if c in dff.columns:
            dff[c] = pd.to_numeric(dff[c], errors="coerce").fillna(0)

    dff["thang_nam_vn"] = to_vn_datetime(dff["thang_nam"])
    dff["thang_nam_vn"] = pd.to_datetime(dff["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()
    dff["thang_label"] = dff["thang_nam_vn"].dt.strftime("%m/%Y")
    dff["nam"] = dff["thang_nam_vn"].dt.year

    ordered_cols = [
        "thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc",
        "tong_doanh_thu", "tong_so_cuoc",
        "tong_phai_chi", "so_diem_tiep_thi", "so_ho_so_hoa_hong",
        "tong_da_chi_du", "tong_chua_chi_du", "tong_khong_chi",
        "so_ho_so_da_chi_du", "so_ho_so_chua_chi_du", "so_ho_so_khong_chi",
        "so_diem_moi_ky_hd", "so_loai_hinh_kd", "chi_phi_binh_quan_moi_diem", "chi_phi_binh_quan_moi_ho_so"
    ]
    for c in ordered_cols:
        if c not in dff.columns:
            dff[c] = 0 if c not in ["khu_vuc", "thang_label"] else ""
    extra_cols = [c for c in dff.columns if c not in ordered_cols]
    return dff[ordered_cols + extra_cols].copy()


def _prepare_bienban_menu_df(raw_df: pd.DataFrame | None) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return _empty_dashboard_df("dt")
    dff = raw_df.copy()

    month_col = find_col(dff, ["thang_nam", "thang", "month", "month_date", "period"])
    if month_col is None:
        return _empty_dashboard_df("dt")
    dff["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff = dff[dff["thang_nam"].notna()].copy()
    if dff.empty:
        return _empty_dashboard_df("dt")

    region_col = find_col(dff, ["khu_vuc", "region", "kv", "area"])
    dff["khu_vuc"] = dff[region_col] if region_col else "Tổng hợp"
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")

    amount_col = find_col(dff, ["tong_tien_de_xuat", "tong_tien", "gia_tri", "tong_gia_tri", "value"])
    collected_col = find_col(dff, ["so_tien_thu_duoc", "tien_thu_duoc", "tong_doanh_thu", "so_tien_thu", "da_thu"])
    processed_col = find_col(dff, ["so_tien_da_xu_ly", "tien_da_xu_ly", "gia_tri_da_xu_ly"])
    debt_col = find_col(dff, ["so_tien_con_no", "con_no", "con_lai", "tien_con_no", "outstanding"])
    count_col = find_col(dff, ["so_bien_ban", "tong_so_cuoc", "so_luong", "count"])
    processed_count_col = find_col(dff, ["so_bien_ban_da_xu_ly", "count_da_xu_ly"])
    collected_count_col = find_col(dff, ["so_bien_ban_thu_hoan_tat", "count_thu_hoan_tat"])

    dff["tong_tien_de_xuat"] = pd.to_numeric(dff[amount_col], errors="coerce").fillna(0) if amount_col else 0
    dff["so_tien_con_no"] = pd.to_numeric(dff[debt_col], errors="coerce").fillna(0) if debt_col else 0
    if collected_col:
        dff["so_tien_thu_duoc"] = pd.to_numeric(dff[collected_col], errors="coerce").fillna(0)
    else:
        dff["so_tien_thu_duoc"] = (dff["tong_tien_de_xuat"] - dff["so_tien_con_no"]).clip(lower=0)
    if processed_col:
        dff["so_tien_da_xu_ly"] = pd.to_numeric(dff[processed_col], errors="coerce").fillna(0)
    else:
        dff["so_tien_da_xu_ly"] = dff["tong_tien_de_xu_ly"] if "tong_tien_de_xu_ly" in dff.columns else dff["tong_tien_de_xuat"]
    dff["so_bien_ban"] = pd.to_numeric(dff[count_col], errors="coerce").fillna(0) if count_col else 0
    dff["so_bien_ban_da_xu_ly"] = pd.to_numeric(dff[processed_count_col], errors="coerce").fillna(0) if processed_count_col else dff["so_bien_ban"]
    dff["so_bien_ban_thu_hoan_tat"] = pd.to_numeric(dff[collected_count_col], errors="coerce").fillna(0) if collected_count_col else 0

    dff["tong_doanh_thu"] = dff["so_tien_thu_duoc"]
    dff["tong_so_cuoc"] = dff["so_bien_ban"]
    dff["thang_nam_vn"] = to_vn_datetime(dff["thang_nam"])
    dff["thang_nam_vn"] = pd.to_datetime(dff["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()
    dff["thang_label"] = dff["thang_nam_vn"].dt.strftime("%m/%Y")
    dff["nam"] = dff["thang_nam_vn"].dt.year

    ordered_cols = [
        "thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc",
        "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no",
        "so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
        "tong_doanh_thu", "tong_so_cuoc"
    ]
    for c in ordered_cols:
        if c not in dff.columns:
            dff[c] = 0 if c not in ["khu_vuc", "thang_label"] else ""
    return dff[ordered_cols].copy()


def _optional_or_proxy_bienban_menu_df() -> pd.DataFrame:
    raw = _read_optional_sheet(OPTIONAL_MENU_SHEET_CANDIDATES.get("bb", []))
    prepared = _prepare_bienban_menu_df(raw)
    if prepared is not None and not prepared.empty:
        return prepared
    fallback = _build_proxy_menu_dataset("bb")
    if fallback is None or fallback.empty:
        return prepared if prepared is not None else _empty_dashboard_df("dt")
    fallback = fallback.copy()
    fallback["tong_tien_de_xuat"] = pd.to_numeric(fallback.get("tong_doanh_thu", 0), errors="coerce").fillna(0)
    fallback["so_tien_thu_duoc"] = fallback["tong_tien_de_xuat"]
    fallback["so_tien_da_xu_ly"] = fallback["tong_tien_de_xuat"]
    fallback["so_tien_con_no"] = 0
    fallback["so_bien_ban"] = pd.to_numeric(fallback.get("tong_so_cuoc", 0), errors="coerce").fillna(0)
    fallback["so_bien_ban_da_xu_ly"] = fallback["so_bien_ban"]
    fallback["so_bien_ban_thu_hoan_tat"] = fallback["so_bien_ban"]
    cols = [
        "thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc",
        "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no",
        "so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
        "tong_doanh_thu", "tong_so_cuoc"
    ]
    for c in cols:
        if c not in fallback.columns:
            fallback[c] = 0 if c not in ["khu_vuc", "thang_label"] else ""
    return fallback[cols].copy()


def _prepare_hr_menu_df(raw_df: pd.DataFrame | None) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return _empty_dashboard_df("dt")
    dff = raw_df.copy()
    month_col = find_col(dff, ["thang_nam", "thang", "month", "month_date", "period"])
    if month_col is None:
        return _empty_dashboard_df("dt")
    dff["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff = dff[dff["thang_nam"].notna()].copy()
    if dff.empty:
        return _empty_dashboard_df("dt")

    region_col = find_col(dff, ["khu_vuc", "region", "kv", "area"])
    dept_col = find_col(dff, ["bo_phan", "don_vi_ct", "don_vi", "phong_ban", "phong ban", "department"])

    dff["khu_vuc"] = dff[region_col] if region_col else "Tổng hợp"
    dff["bo_phan"] = dff[dept_col] if dept_col else "Tất cả bộ phận"

    fallback_count = find_col(dff, ["so_luong_nhan_su", "so_nhan_vien", "so_tai_xe", "tong_so_cuoc", "so_luong", "count"])
    if fallback_count:
        dff["so_luong_nhan_su"] = pd.to_numeric(dff[fallback_count], errors="coerce").fillna(0)
    else:
        dff["so_luong_nhan_su"] = 0

    hr_numeric_cols = [
        "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec",
        "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam",
        "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
        "ty_le_tang", "ty_le_giam", "ty_le_giu_chan", "chi_phi"
    ]
    for col in hr_numeric_cols:
        if col not in dff.columns:
            dff[col] = 0
        dff[col] = pd.to_numeric(dff[col], errors="coerce").fillna(0)

    lifecycle_sum = dff[[c for c in ["so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"] if c in dff.columns]].sum(axis=1)
    dff["so_luong_nhan_su"] = np.where(
        dff["so_luong_nhan_su"] > 0,
        dff["so_luong_nhan_su"],
        np.where(lifecycle_sum > 0, lifecycle_sum, dff["so_vao_lam"].clip(lower=0))
    )

    dff["headcount_dau_ky"] = dff["headcount_dau_ky"].where(dff["headcount_dau_ky"] > 0, (dff["so_luong_nhan_su"] - dff["so_vao_lam"] + dff["so_nghi_viec"]).clip(lower=0))
    dff["so_giu_on_dinh"] = dff["so_giu_on_dinh"].where(dff["so_giu_on_dinh"] > 0, (dff["so_luong_nhan_su"] - dff["so_vao_lam"]).clip(lower=0))
    dff["ty_le_tang"] = np.where(dff["headcount_dau_ky"] > 0, dff["so_vao_lam"] / dff["headcount_dau_ky"] * 100.0, np.where(dff["so_vao_lam"] > 0, 100.0, 0.0))
    dff["ty_le_giam"] = np.where(dff["headcount_dau_ky"] > 0, dff["so_nghi_viec"] / dff["headcount_dau_ky"] * 100.0, 0.0)
    dff["ty_le_giu_chan"] = np.where(dff["headcount_dau_ky"] > 0, dff["so_giu_on_dinh"] / dff["headcount_dau_ky"] * 100.0, np.where(dff["so_luong_nhan_su"] > 0, 100.0, 0.0))
    dff["tong_doanh_thu"] = dff["so_luong_nhan_su"]
    dff["tong_so_cuoc"] = dff["so_vao_lam"]

    dff["thang_nam_vn"] = to_vn_datetime(dff["thang_nam"])
    dff["thang_nam_vn"] = pd.to_datetime(dff["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()
    dff["thang_label"] = dff["thang_nam_vn"].dt.strftime("%m/%Y")
    dff["nam"] = dff["thang_nam_vn"].dt.year
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")
    dff["bo_phan"] = dff["bo_phan"].fillna("Tất cả bộ phận").astype(str).str.strip()
    dff.loc[dff["bo_phan"].eq(""), "bo_phan"] = "Tất cả bộ phận"

    ordered_cols = [
        "thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "bo_phan",
        "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec",
        "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam",
        "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
        "ty_le_tang", "ty_le_giam", "ty_le_giu_chan",
        "tong_doanh_thu", "tong_so_cuoc", "chi_phi"
    ]
    for c in ordered_cols:
        if c not in dff.columns:
            dff[c] = 0 if c not in ["khu_vuc", "bo_phan", "thang_label"] else ""
    return dff[ordered_cols].copy()


def _optional_or_proxy_hr_menu_df(menu_key: str) -> pd.DataFrame:
    raw = _read_optional_sheet(OPTIONAL_MENU_SHEET_CANDIDATES.get(menu_key, []))
    prepared = _prepare_hr_menu_df(raw)
    if prepared is not None and not prepared.empty and float(pd.to_numeric(prepared.get("so_luong_nhan_su", 0), errors="coerce").fillna(0).sum()) > 0:
        return prepared
    fallback = _build_proxy_menu_dataset(menu_key)
    if fallback is None or fallback.empty:
        return prepared if prepared is not None else _empty_dashboard_df("dt")
    fallback = fallback.copy()
    fallback["bo_phan"] = "Tất cả bộ phận"
    fallback["so_luong_nhan_su"] = pd.to_numeric(fallback.get("tong_so_cuoc", 0), errors="coerce").fillna(0)
    fallback["so_vao_lam"] = 0
    fallback["so_nghi_viec"] = 0
    fallback["so_duoi_1_nam"] = 0
    fallback["so_tu_1_den_3_nam"] = 0
    fallback["so_tren_3_nam"] = 0
    fallback["headcount_dau_ky"] = fallback["so_luong_nhan_su"]
    fallback["so_giu_on_dinh"] = fallback["so_luong_nhan_su"]
    fallback["bien_dong_thuan"] = 0
    fallback["ty_le_tang"] = 0
    fallback["ty_le_giam"] = 0
    fallback["ty_le_giu_chan"] = 100
    return fallback

def _proxy_source_df() -> pd.DataFrame:
    source = pd.DataFrame()
    if not df_dt.empty:
        source = df_dt.copy()
    elif not df_hd.empty:
        source = df_hd.copy()
    elif not df_lh.empty:
        source = df_lh.copy()
    if source.empty:
        return _empty_dashboard_df("dt")
    if "tong_doanh_thu" not in source.columns:
        source["tong_doanh_thu"] = 0
    if "tong_so_cuoc" not in source.columns:
        source["tong_so_cuoc"] = 0
    base = source.groupby(["thang_nam_vn", "thang_label", "nam", "khu_vuc"], as_index=False).agg({
        "tong_doanh_thu": "sum",
        "tong_so_cuoc": "sum"
    })
    base["thang_nam"] = base["thang_nam_vn"]
    return base[["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc"]].copy()

_PROXY_BASE = _proxy_source_df()

def _build_proxy_menu_dataset(menu_key: str) -> pd.DataFrame:
    # Strict real-data mode: never synthesize values unless explicitly enabled.
    # Set DASH_ALLOW_SYNTHETIC_PROXY_DATA=1 only for demo/testing environments.
    # Riêng Phương tiện luôn dùng dữ liệu thật, không tạo proxy/ảo.
    if str(menu_key) in {"xdt", "xpq"}:
        return _empty_dashboard_df("dt")
    if not ALLOW_SYNTHETIC_PROXY_DATA:
        return _empty_dashboard_df("dt")
    if _PROXY_BASE.empty:
        return _empty_dashboard_df("dt")
    g = _PROXY_BASE.copy()
    month_no = pd.to_datetime(g["thang_nam_vn"]).dt.month.astype(float)
    region_values = sorted(g["khu_vuc"].astype(str).dropna().unique().tolist())
    region_order = {r: i + 1 for i, r in enumerate(region_values)}
    region_idx = g["khu_vuc"].astype(str).map(region_order).fillna(1).astype(float)
    rev = pd.to_numeric(g["tong_doanh_thu"], errors="coerce").fillna(0.0)
    trips = pd.to_numeric(g["tong_so_cuoc"], errors="coerce").fillna(0.0)
    if float(trips.max()) <= 0:
        trips = np.maximum(rev / 500000.0, 1)
    phase_map = {
        "emp": 0.25,
        "drv": 0.75,
        "mkt": 1.10,
        "bb": 1.45,
        "xdt": 1.80,
        "xpq": 2.20,
    }
    season = 1.0 + 0.08 * np.sin((month_no - 1.0) / 12.0 * 2.0 * np.pi + phase_map.get(menu_key, 0.0))
    region_adj = 1.0 + region_idx * 0.012

    out = g.copy()
    if menu_key == "emp":
        out["tong_doanh_thu"] = np.round(np.maximum(rev * 0.082 * season * region_adj, 0))
        out["tong_so_cuoc"] = np.round(np.maximum(18, (trips / 185.0) * season * (1.0 + region_idx * 0.010)))
    elif menu_key == "drv":
        out["tong_doanh_thu"] = np.round(np.maximum(rev * 0.116 * season * region_adj, 0))
        out["tong_so_cuoc"] = np.round(np.maximum(24, (trips / 120.0) * season * (1.0 + region_idx * 0.012)))
    elif menu_key == "mkt":
        out["tong_doanh_thu"] = np.round(np.maximum((trips / 12.0) * season * (28.0 + region_idx * 1.8), 0))
        out["tong_so_cuoc"] = np.round(np.maximum(3, (trips / 760.0) * season))
    elif menu_key == "bb":
        out["tong_doanh_thu"] = np.round(np.maximum((trips / 640.0) * (3200000.0 + region_idx * 150000.0) * season, 0))
        out["tong_so_cuoc"] = np.round(np.maximum(2, (trips / 680.0) * season))
    elif menu_key == "xdt":
        out["tong_doanh_thu"] = np.round(np.maximum(rev * 0.128 * season * region_adj, 0))
        out["tong_so_cuoc"] = np.round(np.maximum(9, (trips / 235.0) * season))
    elif menu_key == "xpq":
        out["tong_doanh_thu"] = np.round(np.maximum(rev * 0.096 * season * region_adj, 0))
        out["tong_so_cuoc"] = np.round(np.maximum(7, (trips / 265.0) * season))
    else:
        return _empty_dashboard_df("dt")

    cols = ["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc"]
    return out[cols].copy()

OPTIONAL_MENU_SHEET_CANDIDATES = {
    "emp": ["NhanSu_NhanVien_KV_Thang", "QuanLyNhanVien_KV_Thang", "NhanVien_KV_Thang"],
    "drv": ["NhanSu_TaiXe_KV_Thang", "QuanLyTaiXe_KV_Thang", "TaiXe_KV_Thang"],
    "mkt": ["KinhDoanh_DiemTiepThi_KV_Thang", "DiemTiepThi_KV_Thang", "TiepThi_KV_Thang"],
    "bb": ["KinhDoanh_BienBan_KV_Thang", "BienBan_KV_Thang"],
    "xdt": [
        "PhuongTien_XeTrucThuoc_KV_Thang", "XeTrucThuoc_KV_Thang",
        "PhuongTien_Xe_TrucThuoc_KV_Thang", "Xe_TrucThuoc_KV_Thang",
        "PhuongTien_XeTrucThuoc", "XeTrucThuoc", "Xe_Truc_Thuoc", "Xe trực thuộc",
        "PhuongTien_TrucThuoc_KV_Thang", "PhuongTien_TrucThuoc", "TrucThuoc",
        "XeCongTy_KV_Thang", "Xe_CongTy_KV_Thang", "XeCongTy", "Xe_Cong_Ty", "Xe công ty",
        "XeThuocCongTy_KV_Thang", "XeThuocCongTy", "Xe thuộc công ty",
        "XeSoHuu_KV_Thang", "Xe_SoHuu_KV_Thang", "XeSoHuu", "Xe_So_Huu", "Xe sở hữu",
        "PhuongTien_XeDien_KV_Thang", "XeDien_KV_Thang", "PhuongTien_XeDien", "XeDien", "Xe_Dien", "Xe điện",
        "XDT", "XeDT", "Xe_DT", "OwnedFleet_KV_Thang", "OwnedFleet", "CompanyVehicle",
    ],
    "xpq": [
        "PhuongTien_XePhanQuyen_KV_Thang", "XePhanQuyen_KV_Thang",
        "PhuongTien_Xe_PhanQuyen_KV_Thang", "Xe_PhanQuyen_KV_Thang",
        "PhuongTien_XePhanQuyen", "XePhanQuyen", "Xe_Phan_Quyen", "Xe phân quyền",
        "PhuongTien_PhanQuyen_KV_Thang", "PhuongTien_PhanQuyen", "PhanQuyen",
        "XeThuongQuyen_KV_Thang", "Xe_ThuongQuyen_KV_Thang", "XeThuongQuyen", "Xe thương quyền",
        "XeNhuongQuyen_KV_Thang", "XeNhuongQuyen", "Xe nhượng quyền",
        "XeHopTac_KV_Thang", "Xe_HopTac_KV_Thang", "XeHopTac", "Xe hợp tác",
        "XeDoiTac_KV_Thang", "XeDoiTac", "Xe đối tác",
        "XeTraGop_KV_Thang", "XeTraGop", "Xe trả góp",
        "PhuongTien_XeXang_KV_Thang", "XeXang_KV_Thang", "PhuongTien_XeXang", "XeXang", "Xe_Xang", "Xe xăng",
        "XPQ", "XePQ", "Xe_PQ", "DelegatedFleet_KV_Thang", "DelegatedFleet", "FranchiseFleet", "PartnerVehicle",
    ],
}

OPTIONAL_MENU_GENERIC_VEHICLE_SHEET_CANDIDATES = [
    "PhuongTien_KV_Thang", "QuanLyPhuongTien_KV_Thang", "PhuongTien_Thang_KhuVuc",
    "Xe_KV_Thang", "QuanLyXe_KV_Thang", "DanhSachXe_KV_Thang",
    "PhuongTien", "Phương tiện", "QuanLyPhuongTien", "Quản lý phương tiện",
    "DanhSachPhuongTien", "DanhSach_PhuongTien", "Danh sách phương tiện",
    "DanhSachXe", "Danh_Sach_Xe", "Danh sách xe",
    "TongHopPhuongTien", "TongHop_PhuongTien", "Tổng hợp phương tiện",
    "QuanLyXe", "Quản lý xe", "Xe", "Vehicle", "Vehicles", "Fleet",
]


VEHICLE_LOAD_DIAGNOSTICS = {"xdt": [], "xpq": []}

def _vehicle_group_filter_mask(raw_df: pd.DataFrame, menu_key: str):
    if raw_df is None or raw_df.empty:
        return None
    if menu_key == "xdt":
        patterns = [
            "xe truc thuoc", "truc thuoc", "xdt", "xe dt",
            "xe cong ty", "cong ty", "thuoc cong ty",
            "so huu", "tai san",
            "xe dien", "dien", "electric", "ev",
            "owned", "company", "company vehicle", "owned fleet",
        ]
        blocked_patterns = [
            "xe phan quyen", "phan quyen", "xpq", "xe pq", "thuong quyen",
            "nhuong quyen", "hop tac", "doi tac", "tra gop", "xe xang", "xang",
            "delegated", "franchise", "partner",
        ]
    elif menu_key == "xpq":
        patterns = [
            "xe phan quyen", "phan quyen", "xpq", "xe pq",
            "uy quyen", "u y quyen", "thuong quyen", "nhuong quyen",
            "hop tac", "doi tac", "tra gop",
            "xe xang", "xang", "gasoline", "petrol",
            "delegated", "franchise", "partner",
        ]
        blocked_patterns = [
            "xe truc thuoc", "truc thuoc", "xdt", "xe dt", "xe cong ty",
            "thuoc cong ty", "so huu", "tai san", "xe dien", "dien", "owned",
        ]
    else:
        return None

    explicit_candidates = [
        "nhom_phuong_tien", "nhóm phương tiện", "nhom phuong tien",
        "nhom_xe", "nhóm xe", "nhom xe",
        "loai_so_huu", "loại sở hữu", "loai so huu",
        "hinh_thuc_so_huu", "hình thức sở hữu", "hinh thuc so huu",
        "hinh_thuc_quan_ly", "hình thức quản lý", "hinh thuc quan ly",
        "loai_quan_ly", "loại quản lý", "loai quan ly",
        "phan_loai_xe", "phân loại xe", "phan loai xe",
        "loai_hinh_xe", "loại hình xe", "loai hinh xe",
        "nguon_xe", "nguồn xe", "nguon xe",
        "hinh_thuc_khai_thac", "hình thức khai thác", "hinh thuc khai thac",
        "loai_khai_thac", "loại khai thác", "loai khai thac",
        "nhom_nhien_lieu", "nhóm nhiên liệu", "nhom nhien lieu",
        "loai_nhien_lieu", "loại nhiên liệu", "loai nhien lieu",
        "nhien_lieu", "nhiên liệu", "nhien lieu",
        "dien_xang", "điện xăng", "dien xang",
        "fuel", "fuel_type", "energy_type", "dong_co", "động cơ", "dong co",
        "ownership", "owner_type", "fleet_type", "vehicle_group", "vehicle_type_group",
    ]

    cols = []
    for cand in explicit_candidates:
        col = find_col_fuzzy(raw_df, [cand])
        if col and col in raw_df.columns and col not in cols:
            cols.append(col)

    # Last-resort scan for real classification columns with custom names.
    for col in raw_df.columns:
        if col in cols:
            continue
        try:
            s_col = raw_df[col]
            if not (pd.api.types.is_object_dtype(s_col) or pd.api.types.is_string_dtype(s_col) or pd.api.types.is_categorical_dtype(s_col)):
                continue
            n = norm_text(col)
            non_null = s_col.dropna()
            unique_ratio = non_null.astype(str).nunique(dropna=True) / max(1, len(non_null)) if len(non_null) else 1
            if unique_ratio <= 0.85 or any(token in n for token in ["loai", "nhom", "phan", "hinh thuc", "nguon", "nhien lieu", "fuel", "dien", "xang"]):
                cols.append(col)
        except Exception:
            continue

    if not cols:
        return None

    s = raw_df[cols].astype(str).agg(" ".join, axis=1).map(norm_text)
    mask = pd.Series(False, index=raw_df.index)
    for pattern in patterns:
        pat = norm_text(pattern)
        if pat:
            mask = mask | s.str.contains(re.escape(pat), na=False)
    blocked = pd.Series(False, index=raw_df.index)
    for pattern in blocked_patterns:
        pat = norm_text(pattern)
        if pat:
            blocked = blocked | s.str.contains(re.escape(pat), na=False)
    mask = mask & ~blocked
    return mask if bool(mask.any()) else None

def _read_vehicle_source_sheet(menu_key: str):
    raw = _read_optional_sheet(OPTIONAL_MENU_SHEET_CANDIDATES.get(menu_key, []), menu_key=menu_key)
    if isinstance(raw, pd.DataFrame) and not raw.empty:
        return raw

    generic = _read_optional_sheet(OPTIONAL_MENU_GENERIC_VEHICLE_SHEET_CANDIDATES)
    if not isinstance(generic, pd.DataFrame) or generic.empty:
        generic = _discover_vehicle_generic_sheet()
    if not isinstance(generic, pd.DataFrame) or generic.empty:
        return raw

    wide = _extract_vehicle_wide_category_df(generic, menu_key)
    if isinstance(wide, pd.DataFrame) and not wide.empty:
        return wide

    mask = _vehicle_group_filter_mask(generic, menu_key)
    if mask is None:
        try:
            DATA_LOAD_ERRORS.append(
                f"PhuongTien/{menu_key}: tìm thấy sheet phương tiện tổng nhưng không thấy cột phân loại xe trực thuộc/phân quyền hoặc cột tổng {menu_key.upper()}."
            )
            VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append("generic_found_no_scope_or_wide_column")
        except Exception:
            pass
        return raw
    filtered = generic.loc[mask].copy()
    if not filtered.empty:
        try:
            VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"row_scope:{len(filtered)}")
        except Exception:
            pass
        return filtered
    return raw


def _read_vehicle_any_real_sheet(menu_key: str):
    """Scan every workbook sheet for real fleet data. No synthetic/proxy values."""
    if EXCEL_BOOK is None or menu_key not in {"xdt", "xpq"}:
        return None
    try:
        sheet_names = list(_excel_sheet_name_list or EXCEL_BOOK.sheet_names)
    except Exception:
        return None
    aliases = [_sheet_compact_name(x) for x in _vehicle_aliases_for_menu(menu_key) if _sheet_compact_name(x)]
    generic_tokens = ["phuongtien", "quanlyphuongtien", "danhsachphuongtien", "tonghopphuongtien", "danhsachxe", "quanlyxe", "xe", "vehicle", "fleet", "asset", "taisan", "taxi", "qlpt"]
    scored = []
    for sheet_name in sheet_names:
        try:
            sample = _parse_optional_sheet_cached(sheet_name, sample_only=True)
        except Exception:
            sample = None
        if sample is None or not isinstance(sample, pd.DataFrame) or sample.empty:
            continue
        compact = _sheet_compact_name(sheet_name)
        name_score = 0
        if any(alias and alias in compact for alias in aliases):
            name_score += 140
        if any(_sheet_compact_name(tok) in compact for tok in generic_tokens if _sheet_compact_name(tok)):
            name_score += 70
        if compact in {"xdt", "xedt", "xedien", "xetructhuoc", "xecongty"} and menu_key == "xdt":
            name_score += 160
        if compact in {"xpq", "xepq", "xexang", "xephanquyen", "xethuongquyen"} and menu_key == "xpq":
            name_score += 160
        col_score = _vehicle_sample_score(sample) * 14
        value_score = 0
        try:
            if _vehicle_wide_count_column(sample, menu_key) is not None:
                value_score += 120
        except Exception:
            pass
        try:
            sample_mask = _vehicle_group_filter_mask(sample, menu_key)
            if sample_mask is not None and bool(sample_mask.any()):
                value_score += 120
        except Exception:
            pass
        try:
            text_cols = [c for c in sample.columns if pd.api.types.is_object_dtype(sample[c]) or pd.api.types.is_string_dtype(sample[c])]
            if text_cols:
                joined = sample[text_cols].astype(str).agg(" ".join, axis=1).map(_sheet_compact_name)
                if any(bool(joined.str.contains(re.escape(alias), na=False).any()) for alias in aliases if alias):
                    value_score += 90
        except Exception:
            pass
        total_score = name_score + col_score + value_score
        if total_score >= 80 and (name_score >= 70 or col_score >= 42 or value_score >= 90):
            scored.append((total_score, name_score, value_score, col_score, sheet_name))
    scored.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3], sheet_names.index(x[4]) if x[4] in sheet_names else 9999))
    for total_score, name_score, value_score, col_score, sheet_name in scored:
        try:
            full = _parse_optional_sheet_cached(sheet_name)
        except Exception:
            continue
        if full is None or not isinstance(full, pd.DataFrame) or full.empty:
            continue
        wide = _extract_vehicle_wide_category_df(full, menu_key)
        if isinstance(wide, pd.DataFrame) and not wide.empty:
            VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"auto_scan_wide:{sheet_name}")
            return wide
        try:
            mask = _vehicle_group_filter_mask(full, menu_key)
        except Exception:
            mask = None
        if mask is not None and bool(mask.any()):
            filtered = full.loc[mask].copy()
            if not filtered.empty:
                VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"auto_scan_row:{sheet_name}:{len(filtered)}")
                return filtered
        if name_score >= 120 and _vehicle_sample_has_usable_columns(full):
            VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"auto_scan_dedicated:{sheet_name}")
            return full.copy()
    return None


def _build_vehicle_activity_bridge_from_lh(menu_key: str) -> pd.DataFrame:
    """Last-resort real-data bridge from DoanhThu_LH_KV_Thang. No synthetic/random values."""
    source_lh = globals().get("df_lh_all_periods", df_lh)
    if source_lh is None or not isinstance(source_lh, pd.DataFrame) or source_lh.empty:
        source_lh = df_lh
    if menu_key not in {"xdt", "xpq"} or source_lh is None or not isinstance(source_lh, pd.DataFrame) or source_lh.empty:
        return _empty_dashboard_df("dt")
    src = source_lh.copy()
    type_col = find_col_fuzzy(src, ["loaihinh_hoptac", "loai_hinh_hop_tac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình", "loaihinh", "loai hinh", "type", "loai", "nhom_xe", "nhóm xe"])
    if type_col is None or type_col not in src.columns:
        return _empty_dashboard_df("dt")
    norm_type = src[type_col].astype(str).map(norm_text)
    if menu_key == "xdt":
        mask = norm_type.str.contains("xe cong ty|xe truc thuoc|truc thuoc|cong ty|xe dien|so huu", regex=True, na=False)
        bridge_label = "Xe công ty / trực thuộc"
    else:
        mask = norm_type.str.contains("thuong quyen|tra gop|hop tac|phan quyen|nhuong quyen|doi tac|xe xang", regex=True, na=False)
        bridge_label = "Xe thương quyền / phân quyền"
    src = src.loc[mask].copy()
    if src.empty:
        return _empty_dashboard_df("dt")
    if "thang_nam" not in src.columns:
        mcol = find_col_fuzzy(src, ["thang_nam", "tháng năm", "thang", "tháng", "month", "period"])
        src["thang_nam"] = _parse_vehicle_month_series(src[mcol]) if mcol else _current_vn_month_start()
    src["thang_nam"] = pd.to_datetime(src["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    src["thang_nam_vn"] = pd.to_datetime(src.get("thang_nam_vn", src["thang_nam"]), errors="coerce").dt.to_period("M").dt.to_timestamp()
    src["thang_label"] = src["thang_nam_vn"].dt.strftime("%m/%Y")
    src["nam"] = src["thang_nam_vn"].dt.year
    if "khu_vuc" not in src.columns:
        rcol = find_col_fuzzy(src, ["khu_vuc", "khu vực", "region", "kv", "area", "chi_nhanh", "chi nhánh", "don_vi", "đơn vị"])
        src["khu_vuc"] = src[rcol] if rcol else "Tổng hợp"
    src["khu_vuc"] = src["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")
    rev_col = find_col_fuzzy(src, ["tong_doanh_thu", "tổng doanh thu", "doanh_thu", "doanh thu", "revenue", "amount"])
    trip_col = find_col_fuzzy(src, ["tong_so_cuoc", "tổng số cuốc", "so_cuoc", "số cuốc", "cuoc", "trip", "trips", "count"])
    src["tong_doanh_thu"] = pd.to_numeric(src[rev_col], errors="coerce").fillna(0) if rev_col else 0
    src["tong_so_cuoc"] = pd.to_numeric(src[trip_col], errors="coerce").fillna(0) if trip_col else 0
    src["loai_xe"] = src[type_col].fillna(bridge_label).astype(str).str.strip()
    src.loc[src["loai_xe"].eq(""), "loai_xe"] = bridge_label
    src["nhom_nhien_lieu"] = "Dữ liệu hoạt động thực tế"
    g = src.groupby(["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu"], as_index=False).agg(tong_doanh_thu=("tong_doanh_thu", "sum"), tong_so_cuoc=("tong_so_cuoc", "sum"))
    g["so_luong_xe"] = pd.to_numeric(g["tong_so_cuoc"], errors="coerce").fillna(0)
    g["tong_so_cho"] = 0
    g["so_cho_binh_quan_xe"] = 0
    g["so_cho_loc"] = 0
    g["nhan_so_cho"] = "Không áp dụng"
    g["so_bien_kiem_soat"] = 0
    g["so_so_tai"] = 0
    g["du_lieu_nguon"] = "activity_from_lh"
    g["ghi_chu_nguon"] = "Không có sheet đội xe; hiển thị dữ liệu thật từ DoanhThu_LH_KV_Thang theo loại hình xe."
    g = g[pd.to_numeric(g["so_luong_xe"], errors="coerce").fillna(0) > 0].copy()
    if not g.empty:
        VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"activity_bridge_lh:{len(g)}")
    ordered_cols = ["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu", "so_luong_xe", "tong_so_cho", "so_cho_binh_quan_xe", "so_cho_loc", "nhan_so_cho", "so_bien_kiem_soat", "so_so_tai", "tong_doanh_thu", "tong_so_cuoc", "du_lieu_nguon", "ghi_chu_nguon"]
    return g[[c for c in ordered_cols if c in g.columns]].copy()


def _first_present_column(dff: pd.DataFrame, candidates: list[str]):
    try:
        col = find_col_fuzzy(dff, candidates)
        return col if col in dff.columns else None
    except Exception:
        return None


def _normalize_activity_source_for_fleet(src: pd.DataFrame, menu_key: str, source_name: str, type_candidates: list[str]) -> pd.DataFrame:
    """
    Convert an existing real operational table into the fleet schema as a last-resort
    visual bridge. It does not invent months, regions, revenue, trips or random values.
    It only reuses rows already present in loaded Excel sheets.
    """
    if src is None or not isinstance(src, pd.DataFrame) or src.empty or menu_key not in {"xdt", "xpq"}:
        return _empty_dashboard_df("dt")

    dff = src.copy()
    if dff.empty:
        return _empty_dashboard_df("dt")

    month_col = _first_present_column(dff, [
        "thang_nam", "tháng năm", "thang/nam", "tháng/năm", "thang nam", "tháng", "thang",
        "month", "month_date", "period", "ky_bao_cao", "kỳ báo cáo", "ngay_du_lieu", "ngày dữ liệu",
        "ngay_bao_cao", "ngày báo cáo", "report_date",
    ])
    if month_col is not None:
        dff["thang_nam"] = _parse_vehicle_month_series(dff[month_col])
    elif "thang_nam_vn" in dff.columns:
        dff["thang_nam"] = _parse_vehicle_month_series(dff["thang_nam_vn"])
    else:
        return _empty_dashboard_df("dt")

    dff["thang_nam"] = pd.to_datetime(dff["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff = dff[dff["thang_nam"].notna()].copy()
    if dff.empty:
        return _empty_dashboard_df("dt")

    region_col = _first_present_column(dff, [
        "khu_vuc", "khu vực", "khu vuc", "region", "kv", "area", "ten_khu_vuc", "tên khu vực",
        "chi_nhanh", "chi nhánh", "chi nhanh", "don_vi", "đơn vị", "don vi", "tram", "trạm",
    ])
    dff["khu_vuc"] = dff[region_col] if region_col else "Tổng hợp"
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")

    type_col = _first_present_column(dff, type_candidates)
    menu_label = "Xe trực thuộc" if menu_key == "xdt" else "Xe phân quyền"
    if type_col:
        dff["loai_xe"] = dff[type_col].fillna("").astype(str).str.strip()
        dff.loc[dff["loai_xe"].eq(""), "loai_xe"] = f"{menu_label} • dữ liệu hoạt động chưa phân loại"
    else:
        dff["loai_xe"] = f"{menu_label} • dữ liệu hoạt động chưa phân loại"

    dff["nhom_nhien_lieu"] = f"Dữ liệu thật từ {source_name}"

    rev_col = _first_present_column(dff, [
        "tong_doanh_thu", "tổng doanh thu", "doanh_thu", "doanh thu", "revenue", "amount",
        "tong_tien", "tổng tiền", "gia_tri", "giá trị", "value",
    ])
    trip_col = _first_present_column(dff, [
        "tong_so_cuoc", "tổng số cuốc", "so_cuoc", "số cuốc", "cuoc", "cuốc", "trip", "trips",
        "so_luong", "số lượng", "count", "quantity",
    ])

    dff["tong_doanh_thu"] = pd.to_numeric(dff[rev_col], errors="coerce").fillna(0) if rev_col else 0
    trips = pd.to_numeric(dff[trip_col], errors="coerce").fillna(0) if trip_col else pd.Series(0, index=dff.index)

    # Prefer true trip/count fields. If absent, count real source rows so the menu
    # can still render a transparent "data points" bridge instead of a blank page.
    has_real_count = bool(float(pd.to_numeric(trips, errors="coerce").fillna(0).sum()) > 0)
    dff["_fleet_activity_metric"] = trips if has_real_count else 1

    dff["thang_nam_vn"] = to_vn_datetime(dff["thang_nam"])
    dff["thang_nam_vn"] = pd.to_datetime(dff["thang_nam_vn"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    dff["thang_label"] = dff["thang_nam_vn"].dt.strftime("%m/%Y")
    dff["nam"] = dff["thang_nam_vn"].dt.year

    g = dff.groupby(
        ["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu"],
        as_index=False,
    ).agg(
        tong_doanh_thu=("tong_doanh_thu", "sum"),
        so_luong_xe=("_fleet_activity_metric", "sum"),
    )

    g = g[pd.to_numeric(g["so_luong_xe"], errors="coerce").fillna(0) > 0].copy()
    if g.empty:
        return _empty_dashboard_df("dt")

    g["tong_so_cuoc"] = g["so_luong_xe"]
    g["tong_so_cho"] = 0
    g["so_cho_binh_quan_xe"] = 0
    g["so_cho_loc"] = 0
    g["nhan_so_cho"] = "Không áp dụng"
    g["so_bien_kiem_soat"] = 0
    g["so_so_tai"] = 0
    g["du_lieu_nguon"] = "activity_bridge_real_unclassified"
    g["ghi_chu_nguon"] = (
        f"Không tìm thấy sheet/cột đội xe đủ chuẩn cho {menu_label}; "
        f"menu đang hiển thị dữ liệu hoạt động thật từ {source_name}, không dùng dữ liệu ảo."
    )
    g["fleet_bridge_metric"] = "cuoc" if has_real_count else "dong_du_lieu"
    try:
        VEHICLE_LOAD_DIAGNOSTICS.setdefault(menu_key, []).append(f"activity_bridge_any:{source_name}:{len(g)}")
    except Exception:
        pass

    ordered_cols = [
        "thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc",
        "loai_xe", "nhom_nhien_lieu", "so_luong_xe", "tong_so_cho",
        "so_cho_binh_quan_xe", "so_cho_loc", "nhan_so_cho",
        "so_bien_kiem_soat", "so_so_tai", "tong_doanh_thu", "tong_so_cuoc",
        "du_lieu_nguon", "ghi_chu_nguon", "fleet_bridge_metric",
    ]
    return g[[c for c in ordered_cols if c in g.columns]].copy()


def _build_vehicle_any_real_activity_bridge(menu_key: str) -> pd.DataFrame:
    """
    Highest-safety fallback for the two Phương tiện menus:
    show real loaded operational data with explicit source labels rather than
    blank menus or synthetic/proxy values.
    """
    candidate_sources = [
        ("DoanhThu_LH_KV_Thang", globals().get("df_lh_all_periods", df_lh), [
            "loaihinh_hoptac", "loai_hinh_hop_tac", "loại hình hợp tác", "loai hinh hop tac",
            "loai_hinh_std", "loai_hinh", "loại hình", "loaihinh", "loai hinh", "type", "loai",
        ]),
        ("HopDong_KV_Thang", globals().get("df_hd_all_periods", df_hd), [
            "loai_hopdong", "loai_hop_dong", "loại hợp đồng", "loai hop dong",
            "loai_hop_dong_std", "loaihd", "loai_hd", "phan_loai", "nhom_hop_dong",
        ]),
        ("DoanhThu_Thang_KhuVuc", globals().get("df_dt_all_periods", df_dt), [
            "nhom_phuong_tien", "nhóm phương tiện", "loai_xe", "loại xe", "loai_hinh", "loại hình",
        ]),
    ]
    for source_name, source_df, type_candidates in candidate_sources:
        bridge = _normalize_activity_source_for_fleet(source_df, menu_key, source_name, type_candidates)
        if bridge is not None and not bridge.empty:
            return bridge
    return _empty_dashboard_df("dt")


def _fleet_emergency_display_df(menu_key: str, current_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return the best available real dataframe for a fleet menu without synthetic data.

    This function is intentionally permissive: it is only used for xdt/xpq when
    normal fleet data is empty after page filters/cutoffs. It reuses real rows
    already loaded from the workbook and labels the source transparently.
    """
    if menu_key not in {"xdt", "xpq"}:
        return _empty_dashboard_df("dt")
    candidates = []
    if isinstance(current_df, pd.DataFrame) and not current_df.empty:
        candidates.append(current_df)
    try:
        candidates.append(_build_vehicle_activity_bridge_from_lh(menu_key))
    except Exception:
        pass
    try:
        candidates.append(_build_vehicle_any_real_activity_bridge(menu_key))
    except Exception:
        pass
    for candidate in candidates:
        if isinstance(candidate, pd.DataFrame) and not candidate.empty:
            return candidate.copy()
    return _empty_dashboard_df("dt")


def _optional_or_proxy_menu_df(menu_key: str) -> pd.DataFrame:
    raw = _read_optional_sheet(OPTIONAL_MENU_SHEET_CANDIDATES.get(menu_key, []))
    prepared = _prepare_optional_menu_df(raw)
    if prepared is None or prepared.empty:
        return _build_proxy_menu_dataset(menu_key)
    return prepared


def _optional_or_proxy_marketing_menu_df() -> pd.DataFrame:
    raw = _read_optional_sheet(OPTIONAL_MENU_SHEET_CANDIDATES.get("mkt", []))
    prepared = _prepare_marketing_menu_df(raw)
    if prepared is None or prepared.empty:
        return _build_proxy_menu_dataset("mkt")
    return prepared


def _optional_or_proxy_vehicle_menu_df(menu_key: str) -> pd.DataFrame:
    # Fleet menus are strict real-data only. No synthetic/proxy values are injected here.
    # Load priority:
    # 1) exact/dedicated vehicle sheets
    # 2) generic vehicle sheets / universal sheet scan
    # 3) classified real LH activity bridge
    # 4) unclassified real operational bridge so the UI never goes blank when real data exists
    raw = _read_vehicle_source_sheet(menu_key)
    prepared = _prepare_vehicle_menu_df(raw, menu_key=menu_key)
    if prepared is not None and not prepared.empty:
        return prepared

    raw = _read_vehicle_any_real_sheet(menu_key)
    prepared = _prepare_vehicle_menu_df(raw, menu_key=menu_key)
    if prepared is not None and not prepared.empty:
        return prepared

    bridge = _build_vehicle_activity_bridge_from_lh(menu_key)
    if bridge is not None and not bridge.empty:
        return bridge

    bridge = _build_vehicle_any_real_activity_bridge(menu_key)
    if bridge is not None and not bridge.empty:
        return bridge

    return _empty_dashboard_df("dt")



DAILY_CHECKER_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_Checker", "DoanhThu_Ngay_TheoNgay", "DoanhThuNgayChecker", "doanhthungaychecker", "Sheet1"
]
DAILY_CHECKER_LH_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_LH_Checker", "DoanhThu_Ngay_LoaiHinh", "DoanhThuNgay_LoaiHinh", "DoanhThu_LH_Ngay_Checker"
]
DAILY_CHECKER_HINHTHUC_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_HinhThuc", "DoanhThu_Ngay_HinhThucKD", "DoanhThuNgay_HinhThuc", "DoanhThu_HinhThuc_Ngay"
]
DAILY_CHECKER_LH_HINHTHUC_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_LH_HinhThuc", "DoanhThu_Ngay_LoaiHinh_HinhThuc",
    "DoanhThuNgay_LH_HinhThuc", "DoanhThu_LH_HinhThuc_Ngay",
]
DAILY_CHECKER_LUONG_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_Luong", "DoanhThu_Ngay_LoaiLuong", "DoanhThuNgay_Luong"
]
DAILY_CHECKER_SOCHO_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_SoCho", "DoanhThu_Ngay_Seat", "DoanhThuNgay_SoCho"
]
DAILY_CHECKER_TAIXE_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_TaiXe", "DoanhThu_Ngay_Driver", "DoanhThuNgay_TaiXe"
]

DAILY_CHECKER_TAIXE_LH_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_TaiXe_LH", "DoanhThu_Ngay_Driver_LH", "DoanhThuNgay_TaiXe_LoaiHinh"
]
DAILY_CHECKER_TAIXE_HINHTHUC_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_TaiXe_HinhThuc", "DoanhThu_Ngay_Driver_HinhThuc", "DoanhThuNgay_TaiXe_HinhThuc"
]
DAILY_CHECKER_TAIXE_LH_HINHTHUC_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_TaiXe_LH_HinhThuc", "DoanhThu_Ngay_Driver_LH_HinhThuc",
    "DoanhThuNgay_TaiXe_LH_HinhThuc",
]
DAILY_CHECKER_TAIXE_LUONG_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_TaiXe_Luong", "DoanhThu_Ngay_Driver_Luong", "DoanhThuNgay_TaiXe_Luong"
]
DAILY_CHECKER_TAIXE_SOCHO_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_TaiXe_SoCho", "DoanhThu_Ngay_Driver_SoCho", "DoanhThuNgay_TaiXe_SoCho"
]
DAILY_CHECKER_RAW_SHEET_CANDIDATES = [
    "DoanhThu_Ngay_Raw_Checker", "DoanhThu_Ngay_Raw", "DoanhThuNgay_Raw", "Raw_DoanhThuNgayChecker"
]

DASH_LOAD_DAILY_RAW_CHECKER = str(os.getenv("DASH_LOAD_DAILY_RAW_CHECKER", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}



def _daily_checker_empty_df(extra_cols=None) -> pd.DataFrame:
    cols = [
        "ngay_du_lieu", "thang_nam", "thang_nam_vn", "ngay_label", "thang_label", "nam", "khu_vuc",
        "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe",
        "doanh_thu_binh_quan_cuoc", "doanh_thu_binh_quan_xe", "cuoc_binh_quan_xe", "km_co_khach_ratio",
        "tong_km", "so_luong", "nguon_du_lieu",
    ]
    if extra_cols:
        cols += [c for c in extra_cols if c not in cols]
    return pd.DataFrame(columns=cols)


def _series_from_col_or_default(dff: pd.DataFrame, col_name, default_value=None):
    if col_name and col_name in dff.columns:
        return dff[col_name]
    return pd.Series([default_value] * len(dff), index=dff.index)


def _prepare_daily_checker_menu_df(raw_df: pd.DataFrame | None, category_candidates=None, category_name: str | None = None, source_label: str = "Doanh thu ngày checker") -> pd.DataFrame:
    extra_cols = [category_name] if category_name else []
    if raw_df is None or not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return _daily_checker_empty_df(extra_cols)
    dff = raw_df.copy()
    date_col = find_col_fuzzy(dff, [
        "ngay_du_lieu", "ngày dữ liệu", "ngay du lieu", "thoi_gian_tao", "thời gian tạo", "thoi gian tao",
        "ngay", "date", "report_date", "ngay_bao_cao", "ngày báo cáo", "created_at", "updated_at", "timestamp"
    ])
    if date_col is None:
        return _daily_checker_empty_df(extra_cols)
    month_col = find_col_fuzzy(dff, ["thang_nam", "tháng năm", "thang nam", "thang/nam", "month", "period"])
    region_col = find_col_fuzzy(dff, ["khu_vuc", "khu vực", "khu vuc", "region", "area", "chi_nhanh", "chi nhánh", "don_vi", "đơn vị"])
    revenue_col = find_col_fuzzy(dff, ["tong_doanh_thu", "tổng doanh thu", "doanh_thu", "doanh thu", "revenue", "amount"])
    trip_col = find_col_fuzzy(dff, ["tong_so_cuoc", "tổng số cuốc", "so_cuoc", "số cuốc", "so cuoc", "trips", "trip_count"])
    km_vd_col = find_col_fuzzy(dff, ["sokm_vandoanh", "số km vận doanh", "so km van doanh", "km_van_doanh", "km vận doanh", "tong_km", "tổng km"])
    km_khach_col = find_col_fuzzy(dff, ["sokm_cokhach", "số km có khách", "so km co khach", "km_co_khach", "km có khách", "km_khach"])
    car_count_col = find_col_fuzzy(dff, ["so_xe", "số xe", "so xe", "bks", "bien_kiem_soat", "biển kiểm soát", "bien_so"])
    driver_count_col = find_col_fuzzy(dff, ["so_tai_xe", "số tài xế", "so tai xe", "ho_ten", "họ tên", "tai_xe", "tài xế", "driver"])
    sotai_col = find_col_fuzzy(dff, ["so_tai", "số tài", "so tai", "ma_tai", "mã tài"])
    category_col = None
    if category_candidates:
        category_col = find_col_fuzzy(dff, category_candidates)
    if category_col is None and category_name and category_name in dff.columns:
        category_col = category_name

    work = pd.DataFrame(index=dff.index)
    work["ngay_du_lieu"] = pd.to_datetime(dff[date_col], errors="coerce").dt.normalize()
    if month_col:
        work["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    else:
        work["thang_nam"] = work["ngay_du_lieu"].dt.to_period("M").dt.to_timestamp()
    work["khu_vuc"] = _series_from_col_or_default(dff, region_col, "Tổng hợp").fillna("Tổng hợp").astype(str).str.strip()
    work.loc[work["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"
    work["khu_vuc"] = work["khu_vuc"].apply(canon_region_name)
    work["tong_doanh_thu"] = pd.to_numeric(_series_from_col_or_default(dff, revenue_col, 0), errors="coerce").fillna(0)
    work["tong_so_cuoc"] = pd.to_numeric(_series_from_col_or_default(dff, trip_col, 0), errors="coerce").fillna(0)
    work["sokm_vandoanh"] = pd.to_numeric(_series_from_col_or_default(dff, km_vd_col, 0), errors="coerce").fillna(0)
    work["sokm_cokhach"] = pd.to_numeric(_series_from_col_or_default(dff, km_khach_col, 0), errors="coerce").fillna(0)
    work["so_xe_raw"] = _series_from_col_or_default(dff, car_count_col, None)
    work["so_tai_xe_raw"] = _series_from_col_or_default(dff, driver_count_col, None)
    work["so_tai_raw"] = _series_from_col_or_default(dff, sotai_col, None)
    if category_name:
        work[category_name] = _series_from_col_or_default(dff, category_col, "Chưa rõ").fillna("Chưa rõ").astype(str).str.strip()
        work.loc[work[category_name].eq(""), category_name] = "Chưa rõ"
    work = work[work["ngay_du_lieu"].notna()].copy()
    if work.empty:
        return _daily_checker_empty_df(extra_cols)

    def _count_or_nunique(series):
        s = pd.Series(series)
        numeric = pd.to_numeric(s, errors="coerce")
        if numeric.notna().sum() >= max(1, int(len(s) * 0.65)):
            return float(numeric.fillna(0).sum())
        return float(s.fillna("").astype(str).str.strip().replace({"": pd.NA}).dropna().nunique())

    group_cols = ["ngay_du_lieu", "thang_nam", "khu_vuc"] + ([category_name] if category_name else [])
    out = work.groupby(group_cols, as_index=False, dropna=False).agg(
        tong_doanh_thu=("tong_doanh_thu", "sum"),
        tong_so_cuoc=("tong_so_cuoc", "sum"),
        sokm_vandoanh=("sokm_vandoanh", "sum"),
        sokm_cokhach=("sokm_cokhach", "sum"),
        so_xe=("so_xe_raw", _count_or_nunique),
        so_tai_xe=("so_tai_xe_raw", _count_or_nunique),
        so_tai=("so_tai_raw", _count_or_nunique),
    )
    out["doanh_thu_binh_quan_cuoc"] = out["tong_doanh_thu"] / out["tong_so_cuoc"].replace(0, 1)
    out["doanh_thu_binh_quan_xe"] = out["tong_doanh_thu"] / out["so_xe"].replace(0, 1)
    out["cuoc_binh_quan_xe"] = out["tong_so_cuoc"] / out["so_xe"].replace(0, 1)
    out["km_co_khach_ratio"] = out["sokm_cokhach"] / out["sokm_vandoanh"].replace(0, 1) * 100
    out["tong_km"] = out["sokm_vandoanh"]
    out["so_luong"] = out["so_xe"]
    out["thang_nam_vn"] = to_vn_datetime(out["thang_nam"])
    out["thang_nam_vn"] = pd.to_datetime(out["thang_nam_vn"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    out["ngay_label"] = pd.to_datetime(out["ngay_du_lieu"], errors="coerce").dt.strftime("%d/%m/%Y")
    out["thang_label"] = out["thang_nam_vn"].dt.strftime("%m/%Y")
    out["nam"] = out["thang_nam_vn"].dt.year
    out["nguon_du_lieu"] = source_label
    front_cols = [
        "ngay_du_lieu", "thang_nam", "thang_nam_vn", "ngay_label", "thang_label", "nam", "khu_vuc",
        "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe",
        "doanh_thu_binh_quan_cuoc", "doanh_thu_binh_quan_xe", "cuoc_binh_quan_xe", "km_co_khach_ratio",
        "tong_km", "so_luong", "nguon_du_lieu",
    ] + ([category_name] if category_name else [])
    other_cols = [c for c in out.columns if c not in front_cols]
    return out[front_cols + other_cols].sort_values(["ngay_du_lieu", "khu_vuc"]).reset_index(drop=True)


def _read_daily_checker_df(candidates, category_candidates=None, category_name: str | None = None, source_label: str = "Doanh thu ngày checker") -> pd.DataFrame:
    raw = _read_optional_sheet(candidates)
    prepared = _prepare_daily_checker_menu_df(raw, category_candidates=category_candidates, category_name=category_name, source_label=source_label)
    return prepared if prepared is not None else _daily_checker_empty_df([category_name] if category_name else [])


def _read_daily_checker_multi_category_df(candidates, category_specs: list[tuple[str, list[str]]], source_label: str = "Doanh thu ngày checker") -> pd.DataFrame:
    """Read an already-aggregated Daily sheet while preserving multiple category columns.

    Used for combined filters such as loaihinh_hoptac + hinhthuc_kinhdoanh so Dash
    can filter the intersection without loading raw row-level checker data on Vercel.
    """
    raw = _read_optional_sheet(candidates)
    extra_cols = [name for name, _ in (category_specs or [])]
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return _daily_checker_empty_df(extra_cols)
    dff = raw.copy()
    date_col = find_col_fuzzy(dff, [
        "ngay_du_lieu", "ngày dữ liệu", "ngay du lieu", "thoi_gian_tao", "thời gian tạo", "thoi gian tao",
        "ngay", "date", "report_date", "ngay_bao_cao", "ngày báo cáo", "created_at", "updated_at", "timestamp"
    ])
    if date_col is None:
        return _daily_checker_empty_df(extra_cols)
    month_col = find_col_fuzzy(dff, ["thang_nam", "tháng năm", "thang nam", "thang/nam", "month", "period"])
    region_col = find_col_fuzzy(dff, ["khu_vuc", "khu vực", "khu vuc", "region", "area", "chi_nhanh", "chi nhánh", "don_vi", "đơn vị"])
    revenue_col = find_col_fuzzy(dff, ["tong_doanh_thu", "tổng doanh thu", "doanh_thu", "doanh thu", "revenue", "amount"])
    trip_col = find_col_fuzzy(dff, ["tong_so_cuoc", "tổng số cuốc", "so_cuoc", "số cuốc", "so cuoc", "trips", "trip_count"])
    km_vd_col = find_col_fuzzy(dff, ["sokm_vandoanh", "số km vận doanh", "so km van doanh", "km_van_doanh", "km vận doanh", "tong_km", "tổng km"])
    km_khach_col = find_col_fuzzy(dff, ["sokm_cokhach", "số km có khách", "so km co khach", "km_co_khach", "km có khách", "km_khach"])
    car_count_col = find_col_fuzzy(dff, ["so_xe", "số xe", "so xe", "bks", "bien_kiem_soat", "biển kiểm soát", "bien_so"])
    driver_count_col = find_col_fuzzy(dff, ["so_tai_xe", "số tài xế", "so tai xe", "ho_ten", "họ tên", "tai_xe", "tài xế", "driver"])
    sotai_col = find_col_fuzzy(dff, ["so_tai", "số tài", "so tai", "ma_tai", "mã tài"])
    bks_col = find_col_fuzzy(dff, ["bks", "biển kiểm soát", "bien_kiem_soat", "bien so", "bien_so"])
    driver_col = find_col_fuzzy(dff, ["ho_ten", "họ tên", "ho ten", "tai_xe", "tài xế", "driver"])

    out = pd.DataFrame(index=dff.index)
    out["ngay_du_lieu"] = pd.to_datetime(dff[date_col], errors="coerce").dt.normalize()
    if month_col:
        out["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    else:
        out["thang_nam"] = out["ngay_du_lieu"].dt.to_period("M").dt.to_timestamp()
    out["khu_vuc"] = _series_from_col_or_default(dff, region_col, "Tổng hợp").fillna("Tổng hợp").astype(str).str.strip()
    out.loc[out["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"
    out["khu_vuc"] = out["khu_vuc"].apply(canon_region_name)
    out["tong_doanh_thu"] = pd.to_numeric(_series_from_col_or_default(dff, revenue_col, 0), errors="coerce").fillna(0)
    out["tong_so_cuoc"] = pd.to_numeric(_series_from_col_or_default(dff, trip_col, 0), errors="coerce").fillna(0)
    out["sokm_vandoanh"] = pd.to_numeric(_series_from_col_or_default(dff, km_vd_col, 0), errors="coerce").fillna(0)
    out["sokm_cokhach"] = pd.to_numeric(_series_from_col_or_default(dff, km_khach_col, 0), errors="coerce").fillna(0)
    out["so_xe"] = pd.to_numeric(_series_from_col_or_default(dff, car_count_col, 0), errors="coerce").fillna(0)
    out["so_tai_xe"] = pd.to_numeric(_series_from_col_or_default(dff, driver_count_col, 0), errors="coerce").fillna(0)
    out["so_tai"] = _series_from_col_or_default(dff, sotai_col, out["so_tai_xe"])
    out["bks"] = _series_from_col_or_default(dff, bks_col, out["so_xe"])
    if driver_col is not None and driver_col in dff.columns:
        out["ho_ten"] = dff[driver_col].fillna("Chưa rõ tài xế").astype(str).str.strip()
        out.loc[out["ho_ten"].eq(""), "ho_ten"] = "Chưa rõ tài xế"

    for target_col, candidates2 in (category_specs or []):
        col = find_col_fuzzy(dff, candidates2)
        default_value = "Chưa rõ hình thức" if str(target_col) == "hinhthuc_kinhdoanh" else "Chưa rõ loại hình"
        out[target_col] = _series_from_col_or_default(dff, col, default_value).fillna(default_value).astype(str).str.strip()
        out.loc[out[target_col].eq(""), target_col] = default_value

    out = out[out["ngay_du_lieu"].notna()].copy()
    if out.empty:
        return _daily_checker_empty_df(extra_cols)
    out["doanh_thu_binh_quan_cuoc"] = out["tong_doanh_thu"] / out["tong_so_cuoc"].replace(0, 1)
    out["doanh_thu_binh_quan_xe"] = out["tong_doanh_thu"] / out["so_xe"].replace(0, 1)
    out["cuoc_binh_quan_xe"] = out["tong_so_cuoc"] / out["so_xe"].replace(0, 1)
    out["km_co_khach_ratio"] = out["sokm_cokhach"] / out["sokm_vandoanh"].replace(0, 1) * 100
    out["tong_km"] = out["sokm_vandoanh"]
    out["so_luong"] = out["so_xe"]
    out["thang_nam_vn"] = to_vn_datetime(out["thang_nam"])
    out["thang_nam_vn"] = pd.to_datetime(out["thang_nam_vn"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    out["ngay_label"] = pd.to_datetime(out["ngay_du_lieu"], errors="coerce").dt.strftime("%d/%m/%Y")
    out["thang_label"] = out["thang_nam_vn"].dt.strftime("%m/%Y")
    out["nam"] = out["thang_nam_vn"].dt.year
    out["nguon_du_lieu"] = source_label
    front_cols = [
        "ngay_du_lieu", "thang_nam", "thang_nam_vn", "ngay_label", "thang_label", "nam", "khu_vuc",
        "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe",
        "doanh_thu_binh_quan_cuoc", "doanh_thu_binh_quan_xe", "cuoc_binh_quan_xe", "km_co_khach_ratio",
        "tong_km", "so_luong", "nguon_du_lieu",
    ] + extra_cols + ["so_tai", "bks", "ho_ten"]
    other_cols = [c for c in out.columns if c not in front_cols]
    return out[[c for c in front_cols if c in out.columns] + other_cols].sort_values(["ngay_du_lieu", "khu_vuc"]).reset_index(drop=True)


def _prepare_daily_raw_checker_df(raw_df: pd.DataFrame | None) -> pd.DataFrame:
    raw_cols = [
        "ngay_du_lieu", "thang_nam", "thang_nam_vn", "ngay_label", "thang_label", "nam", "khu_vuc",
        "bks", "so_tai", "ho_ten", "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach",
        "loaihinh_hoptac", "hinhthuc_kinhdoanh", "loai_luong", "so_cho", "so_cho_num", "nguon_du_lieu",
    ]
    if raw_df is None or not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame(columns=raw_cols)
    dff = raw_df.copy()
    date_col = find_col_fuzzy(dff, [
        "ngay_du_lieu", "ngày dữ liệu", "ngay du lieu", "thoi_gian_tao", "thời gian tạo", "thoi gian tao",
        "ngay", "date", "report_date", "ngay_bao_cao", "ngày báo cáo", "created_at", "updated_at", "timestamp"
    ])
    if date_col is None:
        return pd.DataFrame(columns=raw_cols)
    month_col = find_col_fuzzy(dff, ["thang_nam", "tháng năm", "thang nam", "thang/nam", "month", "period"])
    region_col = find_col_fuzzy(dff, ["khu_vuc", "khu vực", "khu vuc", "region", "area", "chi_nhanh", "chi nhánh", "don_vi", "đơn vị"])
    bks_col = find_col_fuzzy(dff, ["bks", "bien_kiem_soat", "biển kiểm soát", "bien_so", "biển số"])
    sotai_col = find_col_fuzzy(dff, ["so_tai", "số tài", "so tai", "ma_tai", "mã tài"])
    driver_col = find_col_fuzzy(dff, ["ho_ten", "họ tên", "ho ten", "tai_xe", "tài xế", "tai xe", "ten_tai_xe", "driver"])
    revenue_col = find_col_fuzzy(dff, ["tong_doanh_thu", "tổng doanh thu", "doanh_thu", "doanh thu", "revenue", "amount"])
    trip_col = find_col_fuzzy(dff, ["tong_so_cuoc", "tổng số cuốc", "so_cuoc", "số cuốc", "so cuoc", "trips", "trip_count"])
    km_vd_col = find_col_fuzzy(dff, ["sokm_vandoanh", "số km vận doanh", "so km van doanh", "km_van_doanh", "km vận doanh", "tong_km", "tổng km"])
    km_khach_col = find_col_fuzzy(dff, ["sokm_cokhach", "số km có khách", "so km co khach", "km_co_khach", "km có khách", "km_khach"])
    lh_col = find_col_fuzzy(dff, ["loaihinh_hoptac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình"])
    ht_col = find_col_fuzzy(dff, ["hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh"])
    luong_col = find_col_fuzzy(dff, ["loai_luong", "loại lương", "loai luong"])
    socho_col = find_col_fuzzy(dff, ["so_cho", "số chỗ", "so cho", "seat", "seats"])

    out = pd.DataFrame(index=dff.index)
    out["ngay_du_lieu"] = pd.to_datetime(dff[date_col], errors="coerce").dt.normalize()
    if month_col:
        out["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    else:
        out["thang_nam"] = out["ngay_du_lieu"].dt.to_period("M").dt.to_timestamp()
    out["khu_vuc"] = _series_from_col_or_default(dff, region_col, "Tổng hợp").fillna("Tổng hợp").astype(str).str.strip()
    out.loc[out["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"
    out["khu_vuc"] = out["khu_vuc"].apply(canon_region_name)
    out["bks"] = _series_from_col_or_default(dff, bks_col, None)
    out["so_tai"] = _series_from_col_or_default(dff, sotai_col, None)
    out["ho_ten"] = _series_from_col_or_default(dff, driver_col, "Chưa rõ tài xế").fillna("Chưa rõ tài xế").astype(str).str.strip()
    out.loc[out["ho_ten"].eq(""), "ho_ten"] = "Chưa rõ tài xế"
    out["tong_doanh_thu"] = pd.to_numeric(_series_from_col_or_default(dff, revenue_col, 0), errors="coerce").fillna(0)
    out["tong_so_cuoc"] = pd.to_numeric(_series_from_col_or_default(dff, trip_col, 0), errors="coerce").fillna(0)
    out["sokm_vandoanh"] = pd.to_numeric(_series_from_col_or_default(dff, km_vd_col, 0), errors="coerce").fillna(0)
    out["sokm_cokhach"] = pd.to_numeric(_series_from_col_or_default(dff, km_khach_col, 0), errors="coerce").fillna(0)
    for col_name, source_col, default_value in [
        ("loaihinh_hoptac", lh_col, "Chưa rõ loại hình"),
        ("hinhthuc_kinhdoanh", ht_col, "Chưa rõ hình thức"),
        ("loai_luong", luong_col, "Chưa rõ loại lương"),
        ("so_cho", socho_col, "Chưa rõ số chỗ"),
    ]:
        out[col_name] = _series_from_col_or_default(dff, source_col, default_value).fillna(default_value).astype(str).str.strip()
        out.loc[out[col_name].eq(""), col_name] = default_value
    out["so_cho_num"] = pd.to_numeric(out["so_cho"].astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(0)
    out = out[out["ngay_du_lieu"].notna()].copy()
    if out.empty:
        return pd.DataFrame(columns=raw_cols)
    out["thang_nam_vn"] = to_vn_datetime(out["thang_nam"])
    out["thang_nam_vn"] = pd.to_datetime(out["thang_nam_vn"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    out["ngay_label"] = out["ngay_du_lieu"].dt.strftime("%d/%m/%Y")
    out["thang_label"] = out["thang_nam_vn"].dt.strftime("%m/%Y")
    out["nam"] = out["thang_nam_vn"].dt.year
    out["nguon_du_lieu"] = "SQL dbo.doanhthungaychecker aggregate"
    return out[raw_cols].sort_values(["ngay_du_lieu", "khu_vuc", "ho_ten"]).reset_index(drop=True)


def _read_daily_driver_grouped_df(candidates) -> pd.DataFrame:
    raw = _read_optional_sheet(candidates)
    prepared = _prepare_daily_raw_checker_df(raw)
    return prepared if prepared is not None else _prepare_daily_raw_checker_df(None)


def _read_daily_raw_checker_df() -> pd.DataFrame:
    if not DASH_LOAD_DAILY_RAW_CHECKER:
        return _prepare_daily_raw_checker_df(None)
    raw = _read_optional_sheet(DAILY_CHECKER_RAW_SHEET_CANDIDATES)
    prepared = _prepare_daily_raw_checker_df(raw)
    return prepared if prepared is not None else _prepare_daily_raw_checker_df(None)



# =========================================================
# LAZY BOOT DATA LOADING
# =========================================================
# Mặc định bật lazy boot để cold start trên Vercel không phải nạp toàn bộ
# Daily/HR/Biz/Fleet ngay lúc import app.py. Dữ liệu vẫn được nạp đúng khi
# người dùng mở menu tương ứng hoặc khi gọi warm endpoint với preload.
DASH_BOOT_LAZY_DATA = str(os.getenv("DASH_BOOT_LAZY_DATA", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
_BOOT_DATA_LOADED = {"daily": False, "hr": False, "biz": False, "fleet": False}
_BOOT_DATA_LOADING = set()
DAILY_DRIVER_DETAIL_LOADED = False


def _df_reset_in_place(target: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    """Replace a DataFrame object in-place so existing callback closures keep seeing fresh data."""
    if not isinstance(source, pd.DataFrame):
        source = pd.DataFrame()
    if isinstance(target, pd.DataFrame):
        try:
            pd.DataFrame.__init__(target, source.copy(deep=False))
            return target
        except Exception:
            pass
    return source.copy(deep=False)


def _assign_loaded_frames(frame_map: dict, cutoff_names: list[str] | None = None) -> None:
    g = globals()
    for name, value in frame_map.items():
        old = g.get(name)
        if isinstance(old, pd.DataFrame) and isinstance(value, pd.DataFrame):
            g[name] = _df_reset_in_place(old, value)
        else:
            g[name] = value
    if cutoff_names:
        _apply_real_data_cutoff_inplace_to_globals(cutoff_names)
    try:
        REGION_SCOPE_DF_CACHE.clear()
    except Exception:
        pass
    try:
        COMMON_FILTER_CACHE.clear()
    except Exception:
        pass
    try:
        DAILY_FILTER_CACHE.clear()
        DAILY_SOURCE_PREP_CACHE.clear()
        DAILY_DRIVER_SOURCE_CACHE.clear()
        DAILY_LATEST_OUTPUT_CACHE.clear()
        DAILY_TABLE_FRAME_CACHE.clear()
        DAILY_DATE_BOUNDS_CACHE.clear()
        DAILY_FLEET_AVAILABLE_CACHE.clear()
    except Exception:
        pass
    try:
        HOME_OUTPUT_CACHE.clear()
    except Exception:
        pass
    try:
        PAGE_LAYOUT_CACHE.clear()
    except Exception:
        pass
    try:
        if "df_daily_taixe_lh_checker" in frame_map or "df_daily_taixe_hinhthuc_checker" in frame_map or "df_daily_taixe_lh_hinhthuc_checker" in frame_map:
            globals()["DAILY_DRIVER_DETAIL_LOADED"] = not DASH_DAILY_LAZY_DRIVER_DETAIL
    except Exception:
        pass


def _load_daily_boot_frames(log: bool = True) -> dict:
    data = {
        "df_daily_checker": _read_daily_checker_df(DAILY_CHECKER_SHEET_CANDIDATES, source_label="Doanh thu ngày checker"),
        "df_daily_lh_checker": _read_daily_checker_df(
            DAILY_CHECKER_LH_SHEET_CANDIDATES,
            category_candidates=["loaihinh_hoptac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình"],
            category_name="loaihinh_hoptac",
            source_label="Loại hình ngày checker",
        ),
        "df_daily_hinhthuc_checker": _read_daily_checker_df(
            DAILY_CHECKER_HINHTHUC_SHEET_CANDIDATES,
            category_candidates=["hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh"],
            category_name="hinhthuc_kinhdoanh",
            source_label="Hình thức kinh doanh ngày checker",
        ),
        "df_daily_lh_hinhthuc_checker": _read_daily_checker_multi_category_df(
            DAILY_CHECKER_LH_HINHTHUC_SHEET_CANDIDATES,
            category_specs=[
                ("loaihinh_hoptac", ["loaihinh_hoptac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình"]),
                ("hinhthuc_kinhdoanh", ["hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh"]),
            ],
            source_label="Loại hình + hình thức ngày checker",
        ),
        "df_daily_luong_checker": _read_daily_checker_df(
            DAILY_CHECKER_LUONG_SHEET_CANDIDATES,
            category_candidates=["loai_luong", "loại lương", "loai luong"],
            category_name="loai_luong",
            source_label="Loại lương ngày checker",
        ),
        "df_daily_socho_checker": (_read_daily_checker_df(
            DAILY_CHECKER_SOCHO_SHEET_CANDIDATES,
            category_candidates=["so_cho", "số chỗ", "so cho"],
            category_name="so_cho",
            source_label="Số chỗ ngày checker",
        ) if DASH_DAILY_LOAD_SEAT_DATA else pd.DataFrame()),
        "df_daily_taixe_checker": _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_SHEET_CANDIDATES),
        "df_daily_taixe_lh_checker": (pd.DataFrame() if DASH_DAILY_LAZY_DRIVER_DETAIL else _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_LH_SHEET_CANDIDATES)),
        "df_daily_taixe_hinhthuc_checker": (pd.DataFrame() if DASH_DAILY_LAZY_DRIVER_DETAIL else _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_HINHTHUC_SHEET_CANDIDATES)),
        "df_daily_taixe_lh_hinhthuc_checker": (pd.DataFrame() if DASH_DAILY_LAZY_DRIVER_DETAIL else _read_daily_checker_multi_category_df(
            DAILY_CHECKER_TAIXE_LH_HINHTHUC_SHEET_CANDIDATES,
            category_specs=[
                ("loaihinh_hoptac", ["loaihinh_hoptac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình"]),
                ("hinhthuc_kinhdoanh", ["hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh"]),
            ],
            source_label="Tài xế + loại hình + hình thức ngày checker",
        )),
        "df_daily_taixe_luong_checker": (pd.DataFrame() if DASH_DAILY_LAZY_DRIVER_DETAIL else _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_LUONG_SHEET_CANDIDATES)),
        "df_daily_taixe_socho_checker": (_read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_SOCHO_SHEET_CANDIDATES) if DASH_DAILY_LOAD_SEAT_DATA else pd.DataFrame()),
        "df_daily_raw_checker": _read_daily_raw_checker_df(),
    }
    if log:
        try:
            d0 = data["df_daily_checker"]
            print(f"[DAILY CHECKER LOAD] rows={len(d0)} revenue={pd.to_numeric(d0.get('tong_doanh_thu', 0), errors='coerce').fillna(0).sum():.0f} trips={pd.to_numeric(d0.get('tong_so_cuoc', 0), errors='coerce').fillna(0).sum():.0f}")
        except Exception:
            pass
    return data


def _load_hr_boot_frames(log: bool = True) -> dict:
    data = {
        "df_emp": _optional_or_proxy_hr_menu_df("emp"),
        "df_drv": _optional_or_proxy_hr_menu_df("drv"),
    }
    if log:
        try:
            print(f"[HR LOAD] emp_rows={len(data['df_emp'])} drv_rows={len(data['df_drv'])} emp_headcount={pd.to_numeric(data['df_emp'].get('so_luong_nhan_su', 0), errors='coerce').fillna(0).sum():.0f} drv_headcount={pd.to_numeric(data['df_drv'].get('so_luong_nhan_su', 0), errors='coerce').fillna(0).sum():.0f}")
        except Exception:
            pass
    return data


def _load_biz_boot_frames(log: bool = True) -> dict:
    return {
        "df_mkt": _optional_or_proxy_marketing_menu_df(),
        "df_bb": _optional_or_proxy_bienban_menu_df(),
    }


def _load_fleet_boot_frames(log: bool = True) -> dict:
    data = {
        "df_xdt": _optional_or_proxy_vehicle_menu_df("xdt"),
        "df_xpq": _optional_or_proxy_vehicle_menu_df("xpq"),
    }
    if log:
        try:
            _xdt_total = pd.to_numeric(data["df_xdt"].get("so_luong_xe", 0), errors="coerce").fillna(0).sum() if isinstance(data["df_xdt"], pd.DataFrame) else 0
            _xpq_total = pd.to_numeric(data["df_xpq"].get("so_luong_xe", 0), errors="coerce").fillna(0).sum() if isinstance(data["df_xpq"], pd.DataFrame) else 0
            print(f"[FLEET LOAD] xdt_rows={len(data['df_xdt'])} xdt_total={_xdt_total:.0f} xpq_rows={len(data['df_xpq'])} xpq_total={_xpq_total:.0f}")
            print(f"[FLEET LOAD] xdt_diag={VEHICLE_LOAD_DIAGNOSTICS.get('xdt', [])[:4]} xpq_diag={VEHICLE_LOAD_DIAGNOSTICS.get('xpq', [])[:4]}")
        except Exception:
            pass
    return data


if DASH_BOOT_LAZY_DATA:
    # Lightweight placeholders: keep layout/callback structure intact but avoid loading
    # optional datasets during module import/cold start.
    df_daily_checker = _daily_checker_empty_df()
    df_daily_lh_checker = _daily_checker_empty_df(["loaihinh_hoptac"])
    df_daily_hinhthuc_checker = _daily_checker_empty_df(["hinhthuc_kinhdoanh"])
    df_daily_lh_hinhthuc_checker = _daily_checker_empty_df(["loaihinh_hoptac", "hinhthuc_kinhdoanh"])
    df_daily_luong_checker = _daily_checker_empty_df(["loai_luong"])
    df_daily_socho_checker = _daily_checker_empty_df(["so_cho"])
    df_daily_taixe_checker = _prepare_daily_raw_checker_df(None)
    df_daily_taixe_lh_checker = _prepare_daily_raw_checker_df(None)
    df_daily_taixe_hinhthuc_checker = _prepare_daily_raw_checker_df(None)
    df_daily_taixe_lh_hinhthuc_checker = _prepare_daily_raw_checker_df(None)
    df_daily_taixe_luong_checker = _prepare_daily_raw_checker_df(None)
    df_daily_taixe_socho_checker = _prepare_daily_raw_checker_df(None)
    df_daily_raw_checker = _prepare_daily_raw_checker_df(None)
    df_emp = _empty_dashboard_df("dt")
    df_drv = _empty_dashboard_df("dt")
    df_mkt = _empty_dashboard_df("dt")
    df_bb = _empty_dashboard_df("dt")
    df_xdt = _empty_dashboard_df("dt")
    df_xpq = _empty_dashboard_df("dt")
else:
    _assign_loaded_frames(_load_daily_boot_frames(log=True), ["df_daily_checker", "df_daily_lh_checker", "df_daily_hinhthuc_checker", "df_daily_lh_hinhthuc_checker", "df_daily_luong_checker", "df_daily_socho_checker", "df_daily_taixe_checker", "df_daily_taixe_lh_checker", "df_daily_taixe_hinhthuc_checker", "df_daily_taixe_lh_hinhthuc_checker", "df_daily_taixe_luong_checker", "df_daily_taixe_socho_checker", "df_daily_raw_checker"])
    _assign_loaded_frames(_load_hr_boot_frames(log=True), ["df_emp", "df_drv"])
    _assign_loaded_frames(_load_biz_boot_frames(log=False), ["df_mkt", "df_bb"])
    _assign_loaded_frames(_load_fleet_boot_frames(log=True), None)
    _BOOT_DATA_LOADED.update({"daily": True, "hr": True, "biz": True, "fleet": True})


def _fleet_is_activity_bridge_df(dff: pd.DataFrame) -> bool:
    try:
        if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty or "du_lieu_nguon" not in dff.columns:
            return False
        src = dff["du_lieu_nguon"].astype(str)
        return bool(src.eq("activity_from_lh").any() or src.str.contains("activity", case=False, na=False).any())
    except Exception:
        return False


FLEET_ACTIVITY_BRIDGE = {
    "xdt": _fleet_is_activity_bridge_df(df_xdt),
    "xpq": _fleet_is_activity_bridge_df(df_xpq),
}

def _fleet_bridge_metric_kind(dff: pd.DataFrame) -> str:
    try:
        if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
            return "vehicle"
        if "fleet_bridge_metric" in dff.columns:
            vals = [str(x) for x in dff["fleet_bridge_metric"].dropna().astype(str).unique().tolist()]
            if "dong_du_lieu" in vals:
                return "dong_du_lieu"
            if "cuoc" in vals:
                return "cuoc"
        if _fleet_is_activity_bridge_df(dff):
            return "cuoc"
    except Exception:
        pass
    return "vehicle"

FLEET_BRIDGE_METRIC_KIND = {
    "xdt": _fleet_bridge_metric_kind(df_xdt),
    "xpq": _fleet_bridge_metric_kind(df_xpq),
}

def _fleet_metric_label(prefix: str) -> str:
    kind = FLEET_BRIDGE_METRIC_KIND.get(prefix, "vehicle")
    if kind == "dong_du_lieu":
        return "Dòng dữ liệu hoạt động"
    if kind == "cuoc":
        return "Số cuốc phương tiện"
    return "Số lượng xe"

def _fleet_unit_label(prefix: str) -> str:
    kind = FLEET_BRIDGE_METRIC_KIND.get(prefix, "vehicle")
    if kind == "dong_du_lieu":
        return "dòng"
    if kind == "cuoc":
        return "cuốc"
    return "xe"

def _build_vehicle_type_options(dff: pd.DataFrame):
    if dff is None or dff.empty or "loai_xe" not in dff.columns:
        return []
    metric_col = "so_luong_xe" if "so_luong_xe" in dff.columns else ("tong_so_cuoc" if "tong_so_cuoc" in dff.columns else None)
    if metric_col:
        order = dff.groupby("loai_xe", as_index=False)[metric_col].sum().sort_values(metric_col, ascending=False)["loai_xe"].astype(str).tolist()
    else:
        order = sorted(dff["loai_xe"].astype(str).dropna().unique().tolist())
    return [{"label": x, "value": x} for x in order if str(x).strip()]

VEHICLE_TYPE_OPTIONS = {
    "xdt": _build_vehicle_type_options(df_xdt),
    "xpq": _build_vehicle_type_options(df_xpq),
}


def _build_vehicle_seat_options(dff: pd.DataFrame):
    if dff is None or dff.empty:
        return []
    if "so_cho_loc" in dff.columns:
        seat_series = pd.to_numeric(dff["so_cho_loc"], errors="coerce").fillna(0).round().astype(int)
    elif "so_cho_binh_quan_xe" in dff.columns:
        seat_series = pd.to_numeric(dff["so_cho_binh_quan_xe"], errors="coerce").fillna(0).round().astype(int)
    else:
        return []
    temp = dff.copy()
    temp["so_cho_loc"] = seat_series
    temp = temp[temp["so_cho_loc"] > 0].copy()
    if temp.empty:
        return []
    metric_col = "so_luong_xe" if "so_luong_xe" in temp.columns else ("tong_doanh_thu" if "tong_doanh_thu" in temp.columns else None)
    if metric_col:
        order = temp.groupby("so_cho_loc", as_index=False)[metric_col].sum().sort_values(["so_cho_loc"], ascending=[True])["so_cho_loc"].astype(int).tolist()
    else:
        order = sorted(temp["so_cho_loc"].dropna().astype(int).unique().tolist())
    return [{"label": f"{int(x)} chỗ", "value": int(x)} for x in order if int(x) > 0]


VEHICLE_SEAT_OPTIONS = {
    "xdt": _build_vehicle_seat_options(df_xdt),
    "xpq": _build_vehicle_seat_options(df_xpq),
}


def _refresh_lazy_menu_bindings(prefixes=None) -> None:
    prefixes = list(prefixes or [])
    try:
        if not prefixes:
            prefixes = list(DASH_PREFIXES)
    except Exception:
        prefixes = list(prefixes or [])

    for prefix in prefixes:
        try:
            df_name = f"df_{prefix}"
            if "MENU_CONFIG" in globals() and prefix in MENU_CONFIG and df_name in globals():
                MENU_CONFIG[prefix]["df"] = globals()[df_name]
            if "DATAFRAME_BY_PREFIX" in globals() and df_name in globals():
                DATAFRAME_BY_PREFIX[prefix] = globals()[df_name]
        except Exception:
            pass

    for prefix in [p for p in prefixes if p in {"xdt", "xpq"}]:
        try:
            dff = globals().get(f"df_{prefix}")
            FLEET_ACTIVITY_BRIDGE[prefix] = _fleet_is_activity_bridge_df(dff)
            FLEET_BRIDGE_METRIC_KIND[prefix] = _fleet_bridge_metric_kind(dff)
            VEHICLE_TYPE_OPTIONS[prefix] = _build_vehicle_type_options(dff)
            VEHICLE_SEAT_OPTIONS[prefix] = _build_vehicle_seat_options(dff)
            if "MENU_CONFIG" in globals() and prefix in MENU_CONFIG:
                MENU_CONFIG[prefix]["metric_label"] = _fleet_metric_label(prefix)
                MENU_CONFIG[prefix]["secondary_col"] = "tong_doanh_thu" if FLEET_ACTIVITY_BRIDGE.get(prefix) else "so_bien_kiem_soat"
                MENU_CONFIG[prefix]["secondary_label"] = "Doanh thu phương tiện" if FLEET_ACTIVITY_BRIDGE.get(prefix) else "Khu vực có xe"
                MENU_CONFIG[prefix]["avg_label"] = "Nhóm phương tiện hoạt động" if FLEET_ACTIVITY_BRIDGE.get(prefix) else "Loại xe hoạt động"
                MENU_CONFIG[prefix]["avg_divisor_label"] = _fleet_unit_label(prefix)
                MENU_CONFIG[prefix]["avg_numerator_col"] = "tong_doanh_thu" if FLEET_ACTIVITY_BRIDGE.get(prefix) else "so_luong_xe"
                MENU_CONFIG[prefix]["avg_denominator_col"] = "so_luong_xe"
                MENU_CONFIG[prefix]["fleet_unit"] = _fleet_unit_label(prefix)
        except Exception:
            pass

    try:
        HR_DEPT_OPTIONS["emp"] = [{"label": x, "value": x} for x in sorted(df_emp.get("bo_phan", pd.Series(dtype=str)).astype(str).dropna().unique().tolist()) if str(x).strip()]
        HR_DEPT_OPTIONS["drv"] = [{"label": x, "value": x} for x in sorted(df_drv.get("bo_phan", pd.Series(dtype=str)).astype(str).dropna().unique().tolist()) if str(x).strip()]
    except Exception:
        pass


def ensure_daily_data_loaded(log: bool = True) -> None:
    if not DASH_BOOT_LAZY_DATA or _BOOT_DATA_LOADED.get("daily"):
        return
    if "daily" in _BOOT_DATA_LOADING:
        return
    _BOOT_DATA_LOADING.add("daily")
    try:
        _assign_loaded_frames(
            _load_daily_boot_frames(log=log),
            ["df_daily_checker", "df_daily_lh_checker", "df_daily_hinhthuc_checker", "df_daily_lh_hinhthuc_checker", "df_daily_luong_checker", "df_daily_socho_checker", "df_daily_taixe_checker", "df_daily_taixe_lh_checker", "df_daily_taixe_hinhthuc_checker", "df_daily_taixe_lh_hinhthuc_checker", "df_daily_taixe_luong_checker", "df_daily_taixe_socho_checker", "df_daily_raw_checker"]
        )
        _BOOT_DATA_LOADED["daily"] = True
    finally:
        _BOOT_DATA_LOADING.discard("daily")


def ensure_menu_data_loaded(prefix: str, log: bool = True) -> None:
    prefix = str(prefix or "")
    if not DASH_BOOT_LAZY_DATA:
        return
    if prefix in {"dt", "lh", "hd", "home"}:
        return

    group = None
    frame_loader = None
    cutoff_names = None
    refresh_prefixes = []

    if prefix == "daily":
        ensure_daily_data_loaded(log=log)
        return
    if prefix in {"emp", "drv"}:
        group = "hr"
        frame_loader = _load_hr_boot_frames
        cutoff_names = ["df_emp", "df_drv"]
        refresh_prefixes = ["emp", "drv"]
    elif prefix in {"mkt", "bb"}:
        group = "biz"
        frame_loader = _load_biz_boot_frames
        cutoff_names = ["df_mkt", "df_bb"]
        refresh_prefixes = ["mkt", "bb"]
    elif prefix in {"xdt", "xpq"}:
        group = "fleet"
        frame_loader = _load_fleet_boot_frames
        cutoff_names = None
        refresh_prefixes = ["xdt", "xpq"]

    if not group or _BOOT_DATA_LOADED.get(group):
        return
    if group in _BOOT_DATA_LOADING:
        return
    _BOOT_DATA_LOADING.add(group)
    try:
        _assign_loaded_frames(frame_loader(log=log), cutoff_names)
        _BOOT_DATA_LOADED[group] = True
        _refresh_lazy_menu_bindings(refresh_prefixes)
    finally:
        _BOOT_DATA_LOADING.discard(group)


def ensure_all_lazy_data_loaded(log: bool = True) -> None:
    ensure_daily_data_loaded(log=log)
    for _prefix in ["emp", "mkt", "xdt"]:
        ensure_menu_data_loaded(_prefix, log=log)

DASH_PREFIXES = ["dt", "lh", "hd", "emp", "drv", "mkt", "bb", "xdt", "xpq"]
DASH_DATASETS = [df_dt, df_lh, df_hd, df_emp, df_drv, df_mkt, df_bb, df_xdt, df_xpq, df_daily_checker, df_daily_lh_checker, df_daily_hinhthuc_checker, df_daily_luong_checker, df_daily_socho_checker, df_daily_taixe_checker, df_daily_taixe_lh_checker, df_daily_taixe_hinhthuc_checker, df_daily_taixe_luong_checker, df_daily_taixe_socho_checker, df_daily_raw_checker]

_all_months = pd.concat([dff["thang_nam_vn"] for dff in DASH_DATASETS], ignore_index=True)
_all_months = pd.to_datetime(_all_months, errors="coerce")
MONTH_OPTIONS_ALL = (
    _all_months.dropna()
              .drop_duplicates()
              .sort_values()
              .dt.strftime("%m/%Y")
              .tolist()
)

_all_years = pd.concat([dff["nam"] for dff in DASH_DATASETS], ignore_index=True)
YEAR_OPTIONS_ALL = sorted(_all_years.dropna().astype(int).drop_duplicates().tolist())
CURRENT_VN_YEAR = int(pd.Timestamp.now(tz=VN_TZ).year)
DEFAULT_YEAR = (
    CURRENT_VN_YEAR
    if CURRENT_VN_YEAR in YEAR_OPTIONS_ALL
    else (YEAR_OPTIONS_ALL[-1] if YEAR_OPTIONS_ALL else CURRENT_VN_YEAR)
)

_all_month_df = pd.DataFrame({"thang_nam_vn": _all_months.dropna()})
_all_month_df["nam"] = _all_month_df["thang_nam_vn"].dt.year
_all_month_df["thang_label"] = _all_month_df["thang_nam_vn"].dt.strftime("%m/%Y")
MONTH_OPTIONS_BY_YEAR = {
    int(y): _all_month_df[_all_month_df["nam"] == y]["thang_nam_vn"]
                .drop_duplicates()
                .sort_values()
                .dt.strftime("%m/%Y")
                .tolist()
    for y in YEAR_OPTIONS_ALL
}

LH_COL_RAW = find_col(df_lh, [
    "loaihinh_hoptac",
    "loai_hinh", "loại_hình", "loaihinh", "loai hinh", "type", "loai"
])

HD_COL_RAW = find_col(df_hd, [
    "loai_hopdong",
    "loai_hop_dong", "loại_hợp_đồng", "loai hop dong",
    "loaihd", "loai_hd", "phan_loai", "nhom_hop_dong"
])

if LH_COL_RAW and LH_COL_RAW in df_lh.columns:
    df_lh["loai_hinh_std"] = map_to_canon(df_lh[LH_COL_RAW], LH_MAP)
else:
    df_lh["loai_hinh_std"] = "Khác"

if HD_COL_RAW and HD_COL_RAW in df_hd.columns:
    df_hd["loai_hop_dong_std"] = map_to_canon(df_hd[HD_COL_RAW], HD_MAP)
else:
    df_hd["loai_hop_dong_std"] = "Khác"

LH_COL = "loai_hinh_std"
HD_COL = "loai_hop_dong_std"

LH_OPTIONS = [{"label": x, "value": x} for x in (LH_CANON + ["Khác"])]
HD_OPTIONS = [{"label": x, "value": x} for x in (HD_CANON + ["Khác"])]

DARK_BG = "#1e1e2f"
LIGHT_BG = "#ffffff"

REGION_PALETTE = (
    px.colors.qualitative.Bold
    + px.colors.qualitative.D3
    + px.colors.qualitative.Dark24
    + px.colors.qualitative.Alphabet
)

ALL_REGIONS = sorted(
    set().union(*[
        set(dff.get("khu_vuc", pd.Series(dtype=str)).astype(str).dropna().unique().tolist())
        for dff in DASH_DATASETS
    ])
)

REGION_COLOR_MAP = {r: REGION_PALETTE[i % len(REGION_PALETTE)] for i, r in enumerate(ALL_REGIONS)}
REGION_COLOR_MAP["Khác"] = "#9aa0a6"

def get_scoped_all_regions() -> list[str]:
    scope = current_user_region_scope()
    if scope is None:
        return ALL_REGIONS.copy()
    scope_set = {str(x) for x in scope}
    return [r for r in ALL_REGIONS if str(r) in scope_set]

def get_scoped_regions_from_df(dff: pd.DataFrame) -> list[str]:
    scoped = apply_region_scope_to_df(dff)
    if scoped is None or scoped.empty or "khu_vuc" not in scoped.columns:
        return []
    return sorted(scoped["khu_vuc"].astype(str).dropna().unique().tolist())

def get_scoped_menu_df(prefix: str) -> pd.DataFrame:
    ensure_menu_data_loaded(prefix)
    cfg = get_menu_config(prefix)
    return apply_region_scope_to_df(cfg["df"])

def get_scoped_vehicle_type_options(prefix: str):
    return _build_vehicle_type_options(get_scoped_menu_df(prefix))

def get_scoped_vehicle_seat_options(prefix: str):
    return _build_vehicle_seat_options(get_scoped_menu_df(prefix))

def get_scoped_hr_dept_options(prefix: str):
    dff = get_scoped_menu_df(prefix)
    if dff is None or dff.empty or "bo_phan" not in dff.columns:
        return []
    vals = sorted(dff["bo_phan"].astype(str).dropna().unique().tolist())
    return [{"label": x, "value": x} for x in vals if str(x).strip()]

HR_MENU_PREFIXES = ["emp", "drv"]
FLEET_MENU_PREFIXES = ["xdt", "xpq"]

def _is_fleet_menu(prefix) -> bool:
    try:
        return str(prefix) in FLEET_MENU_PREFIXES
    except Exception:
        return False

def _resolve_year_filter_for_menu(menu: str, filt: dict | None = None, fallback_year=None):
    # Phương tiện không có UI lọc năm, nên không tự áp DEFAULT_YEAR cho xdt/xpq.
    if _is_fleet_menu(menu):
        return None
    filt = filt or {}
    if "year" in filt:
        return filt.get("year")
    return fallback_year

HR_DEPT_OPTIONS = {
    "emp": [{"label": x, "value": x} for x in sorted(df_emp.get("bo_phan", pd.Series(dtype=str)).astype(str).dropna().unique().tolist()) if str(x).strip()],
    "drv": [{"label": x, "value": x} for x in sorted(df_drv.get("bo_phan", pd.Series(dtype=str)).astype(str).dropna().unique().tolist()) if str(x).strip()],
}


def _swatch(color: str):
    return html.Span(
        style={
            "display": "inline-block",
            "width": "10px",
            "height": "10px",
            "borderRadius": "3px",
            "backgroundColor": color,
            "marginRight": "6px",
            "verticalAlign": "middle",
        }
    )

def _ellipsis_div(children):
    return html.Div(
        children,
        style={
            "fontSize": "12px",
            "opacity": 0.92,
            "whiteSpace": "nowrap",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
            "lineHeight": "1.25",
        },
    )

def region_payload_value(dff: pd.DataFrame, metric_col: str, selected_regions=None, max_items=None):
    if dff is None or dff.empty or "khu_vuc" not in dff.columns or metric_col not in dff.columns:
        return []
    tmp = dff.copy()
    if selected_regions:
        sel = [str(x) for x in (selected_regions if isinstance(selected_regions, list) else [selected_regions])]
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(sel)]
    if tmp.empty:
        return []
    g = tmp.groupby("khu_vuc", as_index=False)[metric_col].sum().sort_values(metric_col, ascending=False)
    if max_items is not None and int(max_items) > 0:
        g = g.head(int(max_items))
    total = float(g[metric_col].sum()) if not g.empty else 0.0
    rows = []
    for _, r in g.iterrows():
        name = str(r["khu_vuc"])
        val = float(r[metric_col]) if r[metric_col] is not None else 0.0
        pct = (val / total * 100.0) if total > 0 else 0.0
        rows.append({
            "khu_vuc": name,
            "value": val,
            "value_fmt": fmt_vn(val),
            "pct": pct,
            "color": REGION_COLOR_MAP.get(name, "#888")
        })
    return rows

def region_payload_avg_revenue_per_trip(dff: pd.DataFrame, revenue_col: str, selected_regions=None, max_items=None):
    if dff is None or dff.empty or "khu_vuc" not in dff.columns:
        return []
    if revenue_col not in dff.columns or "tong_so_cuoc" not in dff.columns:
        return []
    tmp = dff.copy()
    if selected_regions:
        sel = [str(x) for x in (selected_regions if isinstance(selected_regions, list) else [selected_regions])]
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(sel)]
    if tmp.empty:
        return []
    g = tmp.groupby("khu_vuc", as_index=False).agg({revenue_col: "sum", "tong_so_cuoc": "sum"})
    g["avg"] = g[revenue_col] / g["tong_so_cuoc"].replace(0, 1)
    g = g.sort_values("avg", ascending=False)
    if max_items is not None and int(max_items) > 0:
        g = g.head(int(max_items))
    rows = []
    for _, r in g.iterrows():
        name = str(r["khu_vuc"])
        avg = float(r["avg"]) if r["avg"] is not None else 0.0
        rows.append({
            "khu_vuc": name,
            "avg": avg,
            "avg_fmt": fmt_vn(avg),
            "color": REGION_COLOR_MAP.get(name, "#888")
        })
    return rows

def region_payload_avg_trips_per_month(dff: pd.DataFrame, selected_regions=None, max_items=None):
    if dff is None or dff.empty or "khu_vuc" not in dff.columns:
        return []
    if "tong_so_cuoc" not in dff.columns:
        return []
    tmp = dff.copy()
    if selected_regions:
        sel = [str(x) for x in (selected_regions if isinstance(selected_regions, list) else [selected_regions])]
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(sel)]
    if tmp.empty:
        return []
    months_n = int(tmp["thang_label"].nunique()) if "thang_label" in tmp.columns else 1
    months_n = max(months_n, 1)
    g = tmp.groupby("khu_vuc", as_index=False)["tong_so_cuoc"].sum()
    g["avg"] = g["tong_so_cuoc"] / months_n
    g = g.sort_values("avg", ascending=False)
    if max_items is not None and int(max_items) > 0:
        g = g.head(int(max_items))
    rows = []
    for _, r in g.iterrows():
        name = str(r["khu_vuc"])
        avg = float(r["avg"]) if r["avg"] is not None else 0.0
        rows.append({
            "khu_vuc": name,
            "avg": avg,
            "avg_fmt": fmt_vn(avg),
            "color": REGION_COLOR_MAP.get(name, "#888")
        })
    return rows

def region_payload_avg_metric_per_month(dff: pd.DataFrame, metric_col: str, selected_regions=None, max_items=None):
    if dff is None or dff.empty or "khu_vuc" not in dff.columns or metric_col not in dff.columns:
        return []
    tmp = dff.copy()
    if selected_regions:
        sel = [str(x) for x in (selected_regions if isinstance(selected_regions, list) else [selected_regions])]
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(sel)]
    if tmp.empty:
        return []
    months_n = int(tmp["thang_label"].nunique()) if "thang_label" in tmp.columns else 1
    months_n = max(months_n, 1)
    g = tmp.groupby("khu_vuc", as_index=False)[metric_col].sum()
    g["avg"] = g[metric_col] / months_n
    g = g.sort_values("avg", ascending=False)
    if max_items is not None and int(max_items) > 0:
        g = g.head(int(max_items))
    rows = []
    for _, r in g.iterrows():
        name = str(r["khu_vuc"])
        avg = float(r["avg"]) if r["avg"] is not None else 0.0
        rows.append({
            "khu_vuc": name,
            "avg": avg,
            "avg_fmt": fmt_vn(avg),
            "color": REGION_COLOR_MAP.get(name, "#888")
        })
    return rows

def region_payload_avg_ratio(dff: pd.DataFrame, numerator_col: str, denominator_col: str, selected_regions=None, max_items=None):
    if dff is None or dff.empty or "khu_vuc" not in dff.columns:
        return []
    if numerator_col not in dff.columns or denominator_col not in dff.columns:
        return []
    tmp = dff.copy()
    if selected_regions:
        sel = [str(x) for x in (selected_regions if isinstance(selected_regions, list) else [selected_regions])]
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(sel)]
    if tmp.empty:
        return []
    g = tmp.groupby("khu_vuc", as_index=False).agg({numerator_col: "sum", denominator_col: "sum"})
    g["avg"] = g[numerator_col] / g[denominator_col].replace(0, 1)
    g = g.sort_values("avg", ascending=False)
    if max_items is not None and int(max_items) > 0:
        g = g.head(int(max_items))
    rows = []
    for _, r in g.iterrows():
        name = str(r["khu_vuc"])
        avg = float(r["avg"]) if r["avg"] is not None else 0.0
        rows.append({
            "khu_vuc": name,
            "avg": avg,
            "avg_fmt": fmt_vn(avg),
            "color": REGION_COLOR_MAP.get(name, "#888")
        })
    return rows

def region_value_lines_from_payload(payload, max_lines=6, value_key="value_fmt", pct_key="pct"):
    if not payload:
        return []
    lines = []
    for r in payload[:max_lines]:
        name = r.get("khu_vuc", "")
        color = r.get("color", "#888")
        val = r.get(value_key, "0")
        pct = r.get(pct_key, None)
        lines.append(
            _ellipsis_div([
                _swatch(color),
                f"{name}: {val}",
                html.Span(f" ({pct:.1f}%)", style={"opacity": 0.75}) if pct is not None else None
            ])
        )
    return lines

def kpi_content(main_text: str, subtitle_text: str = "", extra_lines=None):
    extra_lines = extra_lines or []
    return html.Div([
        html.Div(main_text, style={"fontSize": "28px", "fontWeight": "800", "lineHeight": "1.1", "color": TEXT_LIGHT_UI}),
        html.Div(subtitle_text, style={"fontSize": "12px", "opacity": 0.85, "marginTop": "4px", "fontWeight": "600", "color": MUTED_LIGHT_UI}) if subtitle_text else None,
        html.Div(extra_lines, style={"marginTop": "8px"}) if extra_lines else None
    ])


DROPDOWN_FIX_CSS = """
.Select-menu-outer .Select-option,
.Select-menu-outer .VirtualizedSelectOption,
.VirtualizedSelectOption {
  color: #000000 !important;
  opacity: 1 !important;
}
.Select-option.is-focused,
.VirtualizedSelectFocusedOption { color: #000000 !important; }
.Select-option.is-selected,
.VirtualizedSelectSelectedOption { color: #000000 !important; }
.Select-menu-outer .Select-input > input { color: #000000 !important; opacity: 1 !important; }
"""

PAGINATION_PRO_CSS = """
.page-nav-btn{
  position:fixed !important;
  top:50% !important;
  transform:translateY(-50%) !important;
  z-index:9999 !important;
  width:48px;
  height:48px;
  padding:0 !important;
  border-radius:999px;
  display:flex !important;
  align-items:center !important;
  justify-content:center !important;
  background:rgba(20,20,35,0.16) !important;
  border:1px solid rgba(170,170,220,0.20) !important;
  backdrop-filter:blur(14px);
  -webkit-backdrop-filter:blur(14px);
  box-shadow:
    0 10px 26px rgba(0,0,0,0.26),
    0 0 0 rgba(90,80,255,0);
  color:rgba(255,255,255,0.55) !important;
  font-weight:300 !important;
  font-size:28px !important;
  line-height:1 !important;
  opacity:0.44;
  cursor:pointer;
  transition:
    opacity 180ms ease,
    background 180ms ease,
    border-color 180ms ease,
    box-shadow 220ms ease,
    color 180ms ease,
    transform 180ms ease;
  user-select:none;
}
.page-nav-btn:hover{
  opacity:0.96;
  background:rgba(20,20,35,0.46) !important;
  border-color:rgba(150,140,255,0.55) !important;
  color:rgba(255,255,255,0.96) !important;
  box-shadow:
    0 14px 34px rgba(0,0,0,0.40),
    0 0 32px rgba(90,80,255,0.20);
  transform:translateY(-50%) scale(1.04) !important;
}
.page-nav-btn:active{
  transform:translateY(-50%) scale(0.98) !important;
  opacity:0.92;
}
.page-nav-btn:focus{
  outline:none !important;
  box-shadow:
    0 14px 34px rgba(0,0,0,0.40),
    0 0 0 3px rgba(120,120,255,0.18),
    0 0 34px rgba(90,80,255,0.20);
}
.page-nav-left{ left:16px !important; }
.page-nav-right{ right:16px !important; }
@media (max-width: 576px){
  .page-nav-btn{
    width:44px;
    height:44px;
    font-size:26px !important;
  }
  .page-nav-left{ left:10px !important; }
  .page-nav-right{ right:10px !important; }
}
"""

AI_CHAT_CSS = """
.ai-panel-intro{
  background: linear-gradient(135deg, #0f172a 0%, #14532d 55%, #16a34a 100%);
  border-radius: 24px;
  padding: 18px 18px 16px;
  color: #ffffff;
  box-shadow: 0 22px 45px rgba(15,23,42,0.18);
  position: relative;
  overflow: hidden;
}
.ai-panel-intro::after{
  content:"";
  position:absolute;
  right:-32px;
  top:-32px;
  width:140px;
  height:140px;
  border-radius:50%;
  background: rgba(255,255,255,0.08);
}
.ai-panel-kicker{
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 1px;
  text-transform: uppercase;
  opacity: 0.92;
}
.ai-panel-title{
  font-size: 22px;
  line-height: 1.15;
  font-weight: 900;
  margin-top: 6px;
}
.ai-panel-subtitle{
  font-size: 13px;
  line-height: 1.55;
  opacity: 0.92;
  margin-top: 8px;
  max-width: 96%;
}
.ai-scope-row{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top: 12px;
}
.ai-scope-pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
  border:1px solid rgba(255,255,255,0.20);
  background: rgba(255,255,255,0.12);
  color:#ffffff;
}
.ai-compose-shell{
  margin-top: 14px;
  background: linear-gradient(180deg,#ffffff 0%, #f8fbff 100%);
  border: 1px solid #e3ebf3;
  border-radius: 24px;
  padding: 14px 14px 16px;
  box-shadow: 0 18px 36px rgba(15,23,42,0.08);
}
.ai-compose-head{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}
.ai-compose-title{
  font-size: 13px;
  font-weight: 900;
  letter-spacing: .6px;
  color: #0f172a;
  text-transform: uppercase;
}
.ai-compose-caption{
  font-size: 12px;
  color: #64748b;
  margin-top: 3px;
  line-height: 1.45;
}
.ai-compose-badge{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:8px 10px;
  border-radius:999px;
  border:1px solid #d1fae5;
  background:#ecfdf5;
  color:#166534;
  font-size:11px;
  font-weight:900;
  white-space:nowrap;
}
#ai-input{
  min-height: 118px !important;
  resize: vertical;
  background: linear-gradient(180deg,#ffffff 0%, #fbfdff 100%) !important;
  color: #0f172a !important;
  border: 1.5px solid #dce7f3 !important;
  border-radius: 20px !important;
  box-shadow: inset 0 1px 2px rgba(15,23,42,0.03), 0 8px 18px rgba(15,23,42,0.04) !important;
  padding: 14px 16px !important;
  font-size: 14px !important;
  line-height: 1.6 !important;
}
#ai-input:focus{
  border-color: #22c55e !important;
  box-shadow: 0 0 0 4px rgba(34,197,94,0.10), 0 14px 28px rgba(15,23,42,0.08) !important;
  outline: none !important;
}
.ai-action-btn{
  border-radius: 16px !important;
  padding: 11px 14px !important;
  font-weight: 900 !important;
  box-shadow: 0 12px 26px rgba(15,23,42,0.08);
}
.ai-send-btn{
  background: linear-gradient(135deg,#16a34a 0%, #15803d 100%) !important;
  border: 1px solid #15803d !important;
}
.ai-send-btn:hover{
  transform: translateY(-1px);
  box-shadow: 0 16px 30px rgba(22,163,74,0.18);
}
.ai-clear-btn{
  background: #ffffff !important;
  color: #334155 !important;
  border: 1px solid #d9e3ef !important;
}
.ai-clear-btn:hover{
  border-color: #cbd5e1 !important;
  background: #f8fafc !important;
}
.ai-suggestion-shell{
  margin-top: 14px;
  background:#ffffff;
  border:1px solid #e7eef6;
  border-radius:24px;
  padding:14px 14px 12px;
  box-shadow:0 14px 30px rgba(15,23,42,0.06);
}
.ai-suggestion-title{
  font-size:12px;
  font-weight:900;
  color:#0f172a;
  letter-spacing:.6px;
  text-transform:uppercase;
  margin-bottom:8px;
}
.ai-wrap{
  margin-top: 4px;
  display:flex;
  flex-wrap:wrap;
  gap:8px;
}
.ai-chip{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:999px;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
  border:1px solid #d9e7da;
  background:linear-gradient(180deg,#ffffff 0%, #f5fbf7 100%);
  color:#166534;
  transition: all .18s ease;
  box-shadow:0 8px 16px rgba(15,23,42,0.04);
}
.ai-chip:hover{
  transform: translateY(-1px);
  border-color:#22c55e;
  box-shadow:0 12px 22px rgba(34,197,94,0.10);
}
.ai-thread-note{
  margin-top: 14px;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 800;
  color: #64748b;
}
.ai-output-shell{
  margin-top: 10px;
  background: linear-gradient(180deg,#f8fbff 0%, #ffffff 100%);
  border: 1px solid #e4edf5;
  border-radius: 26px;
  padding: 14px;
  min-height: 340px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), 0 18px 35px rgba(15,23,42,0.07);
}
.ai-thread{
  display:flex;
  flex-direction:column;
  gap:14px;
}
.ai-row{
  display:flex;
  gap:10px;
  align-items:flex-end;
}
.ai-row.user{
  flex-direction:row-reverse;
}
.ai-avatar{
  width:38px;
  height:38px;
  border-radius:14px;
  display:flex;
  align-items:center;
  justify-content:center;
  flex:0 0 38px;
  box-shadow:0 12px 22px rgba(15,23,42,0.14);
}
.ai-row.user .ai-avatar{
  background: linear-gradient(135deg,#0f172a 0%, #334155 100%);
}
.ai-row.bot .ai-avatar{
  background: linear-gradient(135deg,#16a34a 0%, #0f766e 100%);
}
.ai-bubble{
  max-width: calc(100% - 52px);
  padding: 14px 16px;
  border-radius: 20px;
  box-shadow: 0 18px 32px rgba(15,23,42,0.08);
}
.ai-row.user .ai-bubble{
  background: linear-gradient(135deg,#0f172a 0%, #1e293b 100%);
  color:#ffffff;
  border:1px solid rgba(15,23,42,0.06);
  border-bottom-right-radius:8px;
}
.ai-row.bot .ai-bubble{
  background:#ffffff;
  color:#0f172a;
  border:1px solid #e4edf5;
  border-bottom-left-radius:8px;
}
.ai-bubble-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}
.ai-role{
  font-size:12px;
  font-weight:900;
  text-transform:uppercase;
  letter-spacing:.7px;
}
.ai-row.user .ai-role{ color: rgba(255,255,255,0.9); }
.ai-row.bot .ai-role{ color: #166534; }
.ai-time{
  font-size:11px;
  font-weight:800;
  opacity:0.72;
  white-space:nowrap;
}
.ai-bubble-body{
  font-size:13px;
  line-height:1.62;
}
.ai-bubble-body p{ margin-bottom: .55rem; }
.ai-bubble-body p:last-child{ margin-bottom: 0; }
.ai-bubble-body ul,
.ai-bubble-body ol{
  padding-left: 1.15rem;
  margin-bottom: .6rem;
}
.ai-bubble-body li{ margin-bottom: .2rem; }
.ai-bubble-body code{
  background:#f1f5f9;
  color:#0f172a;
  border-radius:8px;
  padding:2px 6px;
  font-size:12px;
}
.ai-bubble-body strong{ font-weight: 900; }
.ai-row.user .ai-bubble-body code{
  background: rgba(255,255,255,0.14);
  color:#ffffff;
}
.ai-meta-row{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  margin-top:10px;
}
.ai-mini-badge{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
}
.ai-mini-badge.accent{
  background:#dcfce7;
  color:#166534;
  border:1px solid #bbf7d0;
}
.ai-mini-badge.soft{
  background:#f8fafc;
  color:#475569;
  border:1px solid #e2e8f0;
}
.ai-empty-state{
  min-height: 300px;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  text-align:center;
  padding: 18px;
}
.ai-empty-icon{
  width:58px;
  height:58px;
  border-radius:20px;
  display:flex;
  align-items:center;
  justify-content:center;
  background:linear-gradient(135deg,#16a34a 0%, #0f766e 100%);
  color:#ffffff;
  box-shadow:0 16px 28px rgba(22,163,74,0.18);
  margin-bottom:12px;
}
.ai-empty-title{
  font-size:16px;
  font-weight:900;
  color:#0f172a;
}
.ai-empty-text{
  font-size:13px;
  color:#64748b;
  line-height:1.6;
  max-width:280px;
  margin-top:6px;
}
@media (max-width: 576px){
  .ai-bubble{ max-width: calc(100% - 46px); }
  .ai-output-shell{ min-height: 280px; }
}
"""

PREMIUM_DATA_STATUS_CSS = """
.data-status-card{
  background: linear-gradient(135deg, rgba(15,23,42,0.98) 0%, rgba(20,83,45,0.97) 58%, rgba(22,163,74,0.96) 100%);
  border: 1px solid rgba(34,197,94,0.22) !important;
  border-radius: 26px !important;
  overflow: hidden;
  position: relative;
  box-shadow: 0 22px 50px rgba(15,23,42,0.18), inset 0 1px 0 rgba(255,255,255,0.05);
}
.data-status-card::after{
  content:"";
  position:absolute;
  right:-34px;
  top:-34px;
  width:160px;
  height:160px;
  border-radius:50%;
  background: rgba(255,255,255,0.08);
}
.data-status-inner{
  position:relative;
  z-index:1;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
  flex-wrap:wrap;
}
.data-status-kicker{
  font-size:11px;
  font-weight:900;
  letter-spacing:1px;
  color:rgba(255,255,255,0.78);
  text-transform:uppercase;
  margin-bottom:10px;
}
.data-status-pill-row{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-bottom:10px;
}
.data-status-pill{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:7px 11px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
  color:#ffffff;
  background:rgba(255,255,255,0.12);
  border:1px solid rgba(255,255,255,0.18);
  white-space:nowrap;
}
.data-status-pill.soft{
  background:rgba(255,255,255,0.08);
}
.data-status-main{
  font-size:28px;
  font-weight:900;
  line-height:1.08;
  letter-spacing:.2px;
  color:#ffffff;
}
.data-status-caption{
  font-size:13px;
  line-height:1.6;
  color:rgba(255,255,255,0.86);
  margin-top:8px;
  max-width:780px;
}
.data-status-cta{
  border-radius:18px !important;
  padding:12px 16px !important;
  font-weight:900 !important;
  border:1px solid rgba(255,255,255,0.18) !important;
  background:rgba(255,255,255,0.14) !important;
  color:#ffffff !important;
  backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);
  box-shadow:0 18px 34px rgba(15,23,42,0.16);
}
.data-status-cta:hover{
  transform:translateY(-1px);
  background:rgba(255,255,255,0.20) !important;
  color:#ffffff !important;
}
@media (max-width: 768px){
  .data-status-main{ font-size:22px; }
  .data-status-cta{ width:100%; justify-content:center; }
}
"""

AI_LAUNCHER_CSS = """
.ai-launcher-btn{
  position:fixed !important;
  right:18px !important;
  bottom:88px !important;
  z-index:1039 !important;
  display:inline-flex !important;
  align-items:center !important;
  gap:12px !important;
  padding:8px 16px 8px 8px !important;
  border-radius:999px !important;
  border:1px solid rgba(34,197,94,0.26) !important;
  background:linear-gradient(135deg,#0f172a 0%, #14532d 58%, #16a34a 100%) !important;
  color:#ffffff !important;
  box-shadow:0 18px 38px rgba(15,23,42,0.24), inset 0 1px 0 rgba(255,255,255,0.05);
  transform:translateZ(0);
  overflow:hidden;
}
.ai-launcher-btn::after{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(135deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.00) 48%, rgba(255,255,255,0.04) 100%);
  pointer-events:none;
}
.ai-launcher-btn:hover{
  transform:translateY(-2px) !important;
  color:#ffffff !important;
  box-shadow:0 22px 42px rgba(15,23,42,0.30), 0 0 30px rgba(34,197,94,0.18);
}
.ai-launcher-btn:focus,
.ai-launcher-btn:active{
  color:#ffffff !important;
  box-shadow:0 22px 42px rgba(15,23,42,0.30), 0 0 0 3px rgba(34,197,94,0.18) !important;
}
.ai-launcher-orb{
  width:48px;
  height:48px;
  border-radius:50%;
  display:flex;
  align-items:center;
  justify-content:center;
  background:rgba(255,255,255,0.14);
  border:1px solid rgba(255,255,255,0.18);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.08);
  position:relative;
  z-index:1;
}
.ai-launcher-copy{
  display:flex;
  flex-direction:column;
  align-items:flex-start;
  line-height:1.08;
  position:relative;
  z-index:1;
}
.ai-launcher-title{
  font-size:13px;
  font-weight:900;
  color:#ffffff;
  letter-spacing:.2px;
}
.ai-launcher-sub{
  font-size:11px;
  color:rgba(255,255,255,0.82);
  margin-top:4px;
  white-space:nowrap;
}
.ai-premium-offcanvas.offcanvas-end{
  box-shadow:-22px 0 48px rgba(15,23,42,0.18);
}
.ai-premium-offcanvas .offcanvas-header{
  background:linear-gradient(135deg,#0f172a 0%, #14532d 58%, #16a34a 100%);
  color:#ffffff;
  border-bottom:1px solid rgba(255,255,255,0.08);
}
.ai-premium-offcanvas .offcanvas-title{
  color:#ffffff !important;
}
.ai-premium-offcanvas .btn-close{
  filter:invert(1) grayscale(100%) brightness(200%);
  opacity:.95;
}
.ai-premium-offcanvas .offcanvas-body{
  background:linear-gradient(180deg,#f7fbff 0%, #ecfdf5 100%);
  padding:18px;
}
@media (max-width: 576px){
  .ai-launcher-btn{
    right:12px !important;
    bottom:84px !important;
    width:60px;
    height:60px;
    padding:6px !important;
    justify-content:center;
  }
  .ai-launcher-copy{ display:none; }
  .ai-launcher-orb{ width:48px; height:48px; }
}
"""

PREMIUM_LOADING_CSS = """
.page-content-shell{
  position:relative;
  min-height:56vh;
}
.page-loading-shell{
  padding-top:4px;
}
.page-loading-hero{
  position:relative;
  overflow:hidden;
  border-radius:28px;
  padding:22px 24px;
  background:linear-gradient(135deg,#0f172a 0%, #14532d 58%, #16a34a 100%);
  box-shadow:0 24px 54px rgba(15,23,42,0.18);
  color:#ffffff;
  margin-bottom:16px;
}
.page-loading-hero::after{
  content:"";
  position:absolute;
  top:-42px;
  right:-42px;
  width:180px;
  height:180px;
  border-radius:50%;
  background:rgba(255,255,255,0.08);
}
.page-loading-kicker{
  position:relative;
  z-index:1;
  font-size:11px;
  font-weight:900;
  letter-spacing:1px;
  text-transform:uppercase;
  opacity:0.88;
}
.page-loading-title{
  position:relative;
  z-index:1;
  font-size:28px;
  font-weight:900;
  line-height:1.08;
  margin-top:8px;
  max-width:720px;
}
.page-loading-subtitle{
  position:relative;
  z-index:1;
  font-size:13px;
  line-height:1.6;
  opacity:0.92;
  margin-top:10px;
  max-width:760px;
}
.page-loading-pill-row{
  position:relative;
  z-index:1;
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:14px;
}
.page-loading-pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
  color:#ffffff;
  background:rgba(255,255,255,0.12);
  border:1px solid rgba(255,255,255,0.18);
}
.page-loading-skeleton-card{
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%);
  border:1px solid #e3ebf3;
  border-radius:22px;
  box-shadow:0 18px 36px rgba(15,23,42,0.08);
  padding:18px;
  min-height:148px;
}
.page-loading-skeleton-title{
  font-size:12px;
  font-weight:900;
  letter-spacing:.6px;
  text-transform:uppercase;
  color:#64748b;
  margin-bottom:14px;
}
.page-loading-chart-shell{
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%);
  border:1px solid #e3ebf3;
  border-radius:22px;
  box-shadow:0 18px 36px rgba(15,23,42,0.08);
  padding:18px;
  min-height:256px;
}
.page-loading-skeleton,
.page-loading-skeleton-bar,
.page-loading-skeleton-dot{
  position:relative;
  overflow:hidden;
  background:linear-gradient(90deg, #e9eef5 8%, #f7fbff 28%, #e9eef5 48%);
  background-size:220% 100%;
  animation:premiumPageShimmer 1.55s linear infinite;
}
.page-loading-skeleton{
  height:14px;
  border-radius:999px;
  margin-bottom:10px;
}
.page-loading-skeleton.sm{ width:34%; }
.page-loading-skeleton.md{ width:58%; }
.page-loading-skeleton.lg{ width:78%; }
.page-loading-skeleton.full{ width:100%; }
.page-loading-skeleton:last-child{ margin-bottom:0; }
.page-loading-skeleton-bar{
  height:178px;
  border-radius:18px;
}
.page-loading-chart-mini{
  display:flex;
  align-items:flex-end;
  gap:10px;
  height:170px;
  margin-top:10px;
}
.page-loading-chart-mini .bar{
  flex:1 1 0;
  border-radius:14px 14px 6px 6px;
  min-width:0;
}
.page-loading-chart-mini .bar.h1{ height:34%; }
.page-loading-chart-mini .bar.h2{ height:58%; }
.page-loading-chart-mini .bar.h3{ height:82%; }
.page-loading-chart-mini .bar.h4{ height:46%; }
.page-loading-chart-mini .bar.h5{ height:68%; }
.page-loading-chart-mini .bar.h6{ height:91%; }
.page-loading-chart-mini .bar.h7{ height:53%; }
.page-loading-chart-mini .bar.h8{ height:73%; }
._dash-loading-callback{
  position:fixed !important;
  top:12px !important;
  left:50% !important;
  transform:translateX(-50%) !important;
  width:min(760px, calc(100vw - 20px)) !important;
  min-height:82px !important;
  padding:14px 18px 18px !important;
  border-radius:24px !important;
  background:linear-gradient(135deg, rgba(15,23,42,0.98) 0%, rgba(20,83,45,0.97) 58%, rgba(22,163,74,0.96) 100%) !important;
  border:1px solid rgba(255,255,255,0.14) !important;
  box-shadow:0 26px 60px rgba(15,23,42,0.28), 0 0 0 1px rgba(34,197,94,0.18) inset !important;
  backdrop-filter:blur(18px);
  -webkit-backdrop-filter:blur(18px);
  z-index:2147483200 !important;
  color:transparent !important;
  font-size:0 !important;
  overflow:hidden !important;
  pointer-events:none !important;
}
._dash-loading-callback::before{
  content:"Đang truy xuất phân tích dữ liệu, vui lòng chờ !\\AKPI";
  white-space:pre-line;
  display:block;
  color:#ffffff;
  font-size:13px;
  font-weight:900;
  line-height:1.5;
  letter-spacing:.2px;
  padding-right:120px;
}
._dash-loading-callback::after{
  content:"";
  position:absolute;
  left:18px;
  right:18px;
  bottom:14px;
  height:8px;
  border-radius:999px;
  background-image:linear-gradient(
    90deg,
    rgba(255,255,255,0.12) 0%,
    rgba(255,255,255,0.18) 15%,
    rgba(134,239,172,0.95) 48%,
    rgba(255,255,255,0.18) 82%,
    rgba(255,255,255,0.12) 100%
  );
  background-size:220% 100%;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,0.08);
  animation:premiumTopLoader 1.25s linear infinite;
}
@keyframes premiumTopLoader{
  0%{ background-position:200% 0; }
  100%{ background-position:-40% 0; }
}
@keyframes premiumPageShimmer{
  0%{ background-position:200% 0; }
  100%{ background-position:-60% 0; }
}
@media (max-width: 768px){
  .page-loading-hero{
    padding:18px 18px 20px;
    border-radius:24px;
  }
  .page-loading-title{
    font-size:22px;
  }
  ._dash-loading-callback{
    top:10px !important;
    width:calc(100vw - 16px) !important;
    min-height:74px !important;
    padding:12px 14px 16px !important;
    border-radius:20px !important;
  }
  ._dash-loading-callback::before{
    font-size:12px;
    padding-right:0;
  }
}
"""

GREEN_UI_CSS = """
.dash-graph{
  background: #ffffff;
  border: 1.5px solid #22c55e !important;
  border-radius: 18px;
  padding: 6px;
  box-shadow: 0 8px 20px rgba(34,197,94,0.12);
}
.dash-graph .js-plotly-plot,
.dash-graph .plot-container,
.dash-graph .svg-container{
  border-radius: 12px !important;
  overflow: visible !important;
}
.dash-graph .main-svg{
  border-radius: 12px !important;
}
#zoom-graph{
  border: 1.5px solid #22c55e !important;
  border-radius: 16px;
  box-shadow: 0 8px 20px rgba(34,197,94,0.12);
  background: #fff;
}
.Select-control,
.Select-menu-outer{
  border-color: #22c55e !important;
}
.Select-control{
  box-shadow: none !important;
}
.Select.is-focused > .Select-control,
.is-focused:not(.is-open) > .Select-control{
  border-color: #16a34a !important;
  box-shadow: 0 0 0 2px rgba(34,197,94,0.15) !important;
}
.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table{
  border: 1px solid #dfe5ef;
}
"""

EXECUTIVE_UI_CSS = """
.exec-header-card{
  background: linear-gradient(135deg, #0f172a 0%, #14532d 55%, #16a34a 100%);
  color:#ffffff;
  border-radius:28px;
  padding:24px 28px;
  box-shadow:0 28px 60px rgba(15,23,42,0.18);
  position:relative;
  overflow:hidden;
  margin-bottom:16px;
}
.exec-header-card::after{
  content:"";
  position:absolute;
  top:-40px;
  right:-40px;
  width:180px;
  height:180px;
  border-radius:50%;
  background:rgba(255,255,255,0.08);
}
.exec-title{
  font-size:32px;
  font-weight:900;
  line-height:1.08;
  letter-spacing:0.2px;
}
.exec-subtitle{
  margin-top:8px;
  opacity:0.9;
  font-size:14px;
  max-width:760px;
}
.exec-chip-row{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  justify-content:flex-end;
}
.exec-chip{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:10px 14px;
  border-radius:999px;
  font-size:12px;
  font-weight:800;
  background:rgba(255,255,255,0.12);
  border:1px solid rgba(255,255,255,0.18);
  color:#ffffff;
  white-space:nowrap;
}
.quick-nav-btn{
  border-radius:18px !important;
  padding:14px 16px !important;
  font-weight:800 !important;
  border:1px solid #e2e8f0 !important;
  background:#ffffff !important;
  color:#0f172a !important;
  box-shadow:0 10px 24px rgba(15,23,42,0.06);
}
.quick-nav-btn:hover{
  transform:translateY(-1px);
  box-shadow:0 14px 30px rgba(15,23,42,0.10);
  border-color:#22c55e !important;
}
.executive-kpi-card,
.executive-table-card{
  border:1px solid #e5edf5 !important;
  border-radius:22px !important;
  box-shadow:0 16px 38px rgba(15,23,42,0.07) !important;
  overflow:hidden;
  background:#ffffff !important;
}
.executive-graph-card{
  border:1px solid #e5edf5 !important;
  border-radius:22px !important;
  box-shadow:0 16px 38px rgba(15,23,42,0.07) !important;
  overflow:visible !important;
  background:#ffffff !important;
}
.executive-graph-card .card-body,
.executive-graph-card .dash-graph{
  overflow: visible !important;
}
.kpi-top-accent{
  height:5px;
  background:linear-gradient(90deg,#16a34a 0%, #22c55e 60%, #86efac 100%);
}
.section-eyebrow{
  display:inline-block;
  padding:6px 12px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
  letter-spacing:.6px;
  color:#166534;
  background:#dcfce7;
  border:1px solid #bbf7d0;
  margin-bottom:10px;
  text-transform:uppercase;
}
.kpi-card-title{
  font-size:12px;
  font-weight:900;
  letter-spacing:.6px;
  color:#64748b;
  text-transform:uppercase;
}
.kpi-delta-pill{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:999px;
  font-size:12px;
  font-weight:900;
}
.kpi-delta-pill.positive{
  color:#166534;
  background:#dcfce7;
}
.kpi-delta-pill.negative{
  color:#b91c1c;
  background:#fee2e2;
}
.kpi-delta-pill.neutral{
  color:#475569;
  background:#f1f5f9;
}
.summary-pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:999px;
  background:#ffffff;
  border:1px solid #e2e8f0;
  font-size:12px;
  font-weight:800;
  color:#334155;
  box-shadow:0 10px 18px rgba(15,23,42,0.05);
}
.home-mini-note{
  font-size:12px;
  color:#64748b;
  font-weight:700;
}
@media (max-width: 768px){
  .exec-title{ font-size:26px; }
  .exec-chip-row{ justify-content:flex-start; margin-top:14px; }
}
"""

def dropdown_style(theme: str):
    if theme == "light":
        return {
            "backgroundColor": "transparent",
            "color": "#0f172a",
            "border": "none",
            "fontSize": "15px",
            "fontWeight": "700",
        }
    return {
        "backgroundColor": "transparent",
        "color": "white",
        "border": "none",
        "fontSize": "15px",
        "fontWeight": "700",
    }

def dropdown_container_style(theme: str):
    if theme == "light":
        return {
            "background": "linear-gradient(180deg,#ffffff 0%, #f8fbff 100%)",
            "padding": "14px 14px 12px",
            "borderRadius": "24px",
            "border": "1px solid #e3ebf3",
            "boxShadow": "0 20px 42px rgba(15,23,42,0.08)",
            "minHeight": "110px",
        }
    return {
        "backgroundColor": "#0f1020",
        "padding": "14px 14px 12px",
        "borderRadius": "24px",
        "border": "1px solid #2b2b47",
        "boxShadow": "0 14px 28px rgba(90,80,255,0.12)",
        "minHeight": "110px",
    }

def filter_label_style(theme: str):
    return {
        "fontWeight": "700",
        "letterSpacing": "0.35px",
        "opacity": 0.96,
        "marginBottom": "8px",
        "fontSize": "11px",
        "textTransform": "uppercase",
        "color": GREEN_PRIMARY if theme == "light" else "white"
    }

def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    try:
        c = str(hex_color).strip().lstrip("#")
        if len(c) == 3:
            c = "".join([ch * 2 for ch in c])
        if len(c) != 6:
            raise ValueError("invalid hex")
        r = int(c[0:2], 16)
        g = int(c[2:4], 16)
        b = int(c[4:6], 16)
        a = max(0.0, min(1.0, float(alpha)))
        return f"rgba({r},{g},{b},{a})"
    except Exception:
        a = max(0.0, min(1.0, float(alpha))) if alpha is not None else 1.0
        return f"rgba(22,163,74,{a})"

def _chart_title_escape(value) -> str:
    s = "" if value is None else str(value)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))

def _premium_chart_title_parts(title: str) -> tuple[str, str]:
    raw = "" if title is None else str(title)
    raw = re.sub(r"(?i)<br\s*/?>", "<br>", raw).strip()
    raw = re.sub(r"(?i)</?b>", "", raw)
    raw = re.sub(r"(?i)</?sup>", "", raw)
    parts = [p.strip() for p in raw.split("<br>") if str(p).strip()]
    if not parts:
        return "", ""
    main = parts[0]
    subtitle_parts = parts[1:]
    if not subtitle_parts and " • " in main:
        p2 = [p.strip() for p in main.split(" • ") if p.strip()]
        if len(p2) >= 2:
            main = p2[0]
            subtitle_parts = p2[1:]
    elif " • " in main and len(main) > 62:
        p2 = [p.strip() for p in main.split(" • ") if p.strip()]
        if len(p2) >= 2:
            main = p2[0]
            subtitle_parts = p2[1:] + subtitle_parts
    subtitle = " • ".join(subtitle_parts)
    return main, subtitle

def _premium_chart_title_text(title: str, theme: str = "light") -> str:
    main, subtitle = _premium_chart_title_parts(title)
    if not main and not subtitle:
        return ""
    main_color = "#0f172a" if theme == "light" else "#f8fafc"
    sub_color = "#64748b" if theme == "light" else "#cbd5e1"
    accent_color = "#16a34a" if theme == "light" else "#86efac"
    main_html = _chart_title_escape(main)
    sub_html = _chart_title_escape(subtitle)
    main_line = (
        f"<span style='font-size:16px;font-weight:800;color:{main_color};letter-spacing:-0.18px;line-height:1.2'>"
        f"<span style='color:{accent_color};font-size:11px;vertical-align:middle'>●</span> {main_html}</span>"
    )
    if sub_html:
        return (
            main_line
            + f"<br><span style='font-size:11.5px;font-weight:500;color:{sub_color};letter-spacing:0px;line-height:1.35'>"
            + sub_html
            + "</span>"
        )
    return main_line

def _premium_chart_title_dict(title: str, theme: str = "light") -> dict:
    fg = "#0f172a" if theme == "light" else "#f8fafc"
    return dict(
        text=_premium_chart_title_text(title, theme=theme),
        x=0.022,
        xanchor="left",
        y=0.968,
        yanchor="top",
        pad=dict(t=14, b=16),
        font=dict(family=FONT_UI_FAMILY, size=15, color=fg),
    )

def _chart_title_margin(title: str, base_top: int = 120, min_top: int = 170, extra_per_line: int = 30) -> int:
    main, subtitle = _premium_chart_title_parts(title)
    line_units = 1.0 + (1.0 if subtitle else 0.0)
    if len(main) > 58:
        line_units += 0.35
    if len(subtitle) > 72:
        line_units += 0.35
    return int(max(min_top, int(base_top) + max(0.0, line_units - 1.0) * int(extra_per_line)))


def apply_time_axis(fig):
    fig.update_xaxes(
        tickformat="%m/%Y",
        dtick="M1",
        ticklabelmode="period",
        tickangle=0,
        showgrid=True,
        automargin=True
    )
    for tr in fig.data:
        t = getattr(tr, "type", "")
        if t in (None, "scatter"):
            try:
                tr.update(xperiod="M1", xperiodalignment="middle")
            except Exception:
                pass
        if t == "bar":
            tr.update(xperiod="M1", xperiodalignment="middle")
    return fig

def apply_theme(fig, theme, use_time_axis: bool = True):
    if use_time_axis:
        fig = apply_time_axis(fig)
    base_font_color = "#f8fafc" if theme == "dark" else "#0f172a"

    fig.update_layout(
        legend_itemclick="toggleothers",
        legend_itemdoubleclick="toggle",
        font=dict(
            family=FONT_UI_FAMILY,
            size=14,
            color=base_font_color
        )
    )

    if theme == "dark":
        fig.update_layout(
            plot_bgcolor=DARK_BG,
            paper_bgcolor=DARK_BG,
            xaxis=dict(gridcolor="#333"),
            yaxis=dict(gridcolor="#333"),
            legend_title_text="",
            hovermode="x unified"
        )
    else:
        fig.update_layout(
            plot_bgcolor=LIGHT_BG,
            paper_bgcolor=LIGHT_BG,
            xaxis=dict(
                gridcolor="#e5e7eb",
                showline=True,
                linecolor=GREEN_BORDER,
                linewidth=1,
                mirror=False
            ),
            yaxis=dict(
                gridcolor="#e5e7eb",
                showline=True,
                linecolor=GREEN_BORDER,
                linewidth=1,
                mirror=False
            ),
            legend_title_text="",
            hovermode="x unified"
        )
    return fig

def apply_exec_layout(fig, theme="light", title=None, top=120, x_title=None, y_title=None):
    bg = LIGHT_BG if theme == "light" else DARK_BG
    fg = "#0f172a" if theme == "light" else "#f8fafc"
    grid = "#e5e7eb" if theme == "light" else "#333"
    axis_line = GREEN_BORDER if theme == "light" else "#64748b"
    title_text = title or ""
    top2 = _chart_title_margin(title_text, base_top=top, min_top=178, extra_per_line=34)

    fig.update_layout(
        plot_bgcolor=bg,
        paper_bgcolor=bg,
        font=dict(
            family=FONT_UI_FAMILY,
            size=13,
            color=fg
        ),
        hovermode="closest",
        legend_title_text="",
        margin=dict(l=22, r=18, t=top2, b=24),
        title=_premium_chart_title_dict(title_text, theme=theme),
        title_automargin=True,
        hoverlabel=dict(
            bgcolor="#ffffff" if theme == "light" else "#111827",
            bordercolor="#dbe7f3" if theme == "light" else "#334155",
            font=dict(family=FONT_UI_FAMILY, size=12, color="#0f172a" if theme == "light" else "#f8fafc")
        )
    )

    fig.update_xaxes(
        showgrid=True,
        gridcolor=grid,
        showline=True,
        linecolor=axis_line,
        linewidth=1,
        automargin=True,
        title_font=dict(size=12, family=FONT_UI_FAMILY),
        tickfont=dict(size=11, family=FONT_UI_FAMILY)
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=grid,
        showline=True,
        linecolor=axis_line,
        linewidth=1,
        automargin=True,
        title_font=dict(size=12, family=FONT_UI_FAMILY),
        tickfont=dict(size=11, family=FONT_UI_FAMILY)
    )

    if x_title:
        try:
            fig.update_xaxes(title_text=x_title)
        except Exception:
            pass

    if y_title:
        try:
            fig.update_yaxes(title_text=y_title)
        except Exception:
            pass

    return fig

def apply_chart_title(fig, title: str, top: int = 120, y_title: str = None, theme: str = "light"):
    top2 = _chart_title_margin(title, base_top=top, min_top=190, extra_per_line=34)
    fig.update_layout(
        title=_premium_chart_title_dict(title, theme=theme),
        margin=dict(l=22, r=16, t=top2, b=20),
        title_automargin=True,
        hoverlabel=dict(
            bgcolor="#ffffff" if theme == "light" else "#111827",
            bordercolor="#dbe7f3" if theme == "light" else "#334155",
            font=dict(family=FONT_UI_FAMILY, size=12, color="#0f172a" if theme == "light" else "#f8fafc")
        ),
        font=dict(family=FONT_UI_FAMILY, size=13, color="#0f172a" if theme == "light" else "#f8fafc")
    )
    try:
        fig.update_xaxes(title_text="Tháng", automargin=True, title_font=dict(size=12, family=FONT_UI_FAMILY), tickfont=dict(size=11, family=FONT_UI_FAMILY))
    except Exception:
        pass
    if y_title:
        try:
            fig.update_yaxes(title_text=y_title, automargin=True, title_font=dict(size=12, family=FONT_UI_FAMILY), tickfont=dict(size=11, family=FONT_UI_FAMILY))
        except Exception:
            pass
    return fig

def _add_line_point_labels(fig, show_all_if_points_le=10):
    try:
        for tr in fig.data:
            t = getattr(tr, "type", "")
            if t not in (None, "scatter"):
                continue
            ys = getattr(tr, "y", None)
            if ys is None:
                continue
            n = len(ys) if hasattr(ys, "__len__") else 0
            if n <= 0:
                continue
            text_vals = [""] * n
            if n <= show_all_if_points_le:
                for i, y in enumerate(ys):
                    text_vals[i] = fmt_vn(y)
            else:
                try:
                    text_vals[-1] = fmt_vn(ys[-1])
                except Exception:
                    pass
            tr.update(
                mode="lines+markers+text",
                text=text_vals,
                textposition="top center",
                textfont=dict(size=10),
                cliponaxis=False,
            )
        m = fig.layout.margin if getattr(fig.layout, "margin", None) else None
        if m:
            fig.update_layout(
                margin=dict(
                    l=m.l or 16,
                    r=m.r or 16,
                    t=max(m.t or 190, 220),
                    b=m.b or 16
                )
            )
    except Exception:
        pass
    return fig

def enhance_p1_chart2_total_line(fig, g: pd.DataFrame, x_col: str, y_col: str, metric_label: str, theme: str = "light"):
    try:
        if fig is None or g is None or g.empty:
            return fig
        if x_col not in g.columns or y_col not in g.columns:
            return fig
        gg = g[[x_col, y_col]].copy().sort_values(x_col).reset_index(drop=True)
        gg["val_fmt_local"] = gg[y_col].apply(fmt_vn)
        gg["mom_abs"] = gg[y_col].diff()
        gg["mom_pct"] = gg[y_col].pct_change() * 100

        def _fmt_diff(v):
            if pd.isna(v):
                return "N/A"
            sign = "+" if float(v) > 0 else ""
            return f"{sign}{fmt_vn(v)}"

        def _fmt_pct(v):
            if pd.isna(v):
                return "N/A"
            sign = "+" if float(v) > 0 else ""
            return f"{sign}{float(v):.1f}%"

        gg["mom_abs_fmt"] = gg["mom_abs"].apply(_fmt_diff)
        gg["mom_pct_fmt"] = gg["mom_pct"].apply(_fmt_pct)

        if len(fig.data) > 0:
            tr = fig.data[0]
            tr.update(
                fill="tozeroy",
                fillcolor=_hex_to_rgba(GREEN_PRIMARY, 0.08),
                line=dict(width=3.5, shape="spline"),
                marker=dict(size=8, line=dict(width=1.5, color="#ffffff")),
                customdata=gg[["val_fmt_local", "mom_abs_fmt", "mom_pct_fmt"]].to_numpy(),
                hovertemplate=(
                    "Tháng: %{x|%m/%Y}<br>"
                    + f"{metric_label}: "
                    + "%{customdata[0]}<br>"
                    + "MoM: %{customdata[1]}<br>"
                    + "MoM (%): %{customdata[2]}"
                    + "<extra></extra>"
                )
            )

        avg_val = float(gg[y_col].mean()) if len(gg) else 0.0
        q25 = float(gg[y_col].quantile(0.25)) if len(gg) else 0.0
        q75 = float(gg[y_col].quantile(0.75)) if len(gg) else 0.0

        try:
            if len(gg) >= 4 and q75 >= q25:
                fig.add_hrect(
                    y0=q25, y1=q75,
                    fillcolor=_hex_to_rgba(GREEN_PRIMARY, 0.05),
                    line_width=0,
                    annotation_text="Vùng 25%-75%",
                    annotation_position="top left",
                    annotation_font_size=10
                )
        except Exception:
            pass

        try:
            fig.add_hline(
                y=avg_val,
                line_dash="dash",
                line_width=1.5,
                line_color="#94a3b8",
                annotation_text=f"TB: {fmt_vn(avg_val)}",
                annotation_position="top right",
                annotation_font_size=11
            )
        except Exception:
            pass

        if len(gg) >= 3:
            gg["ma3"] = gg[y_col].rolling(3, min_periods=1).mean()
            fig.add_scatter(
                x=gg[x_col],
                y=gg["ma3"],
                mode="lines",
                name="MA(3)",
                line=dict(width=2, dash="dot", color="#64748b"),
                hovertemplate="Tháng: %{x|%m/%Y}<br>MA(3): %{y:,.0f}<extra></extra>"
            )

        if len(gg) >= 2:
            i_max = int(gg[y_col].idxmax())
            i_min = int(gg[y_col].idxmin())
            rmax = gg.loc[i_max]
            rmin = gg.loc[i_min]
            ann_bg = _hex_to_rgba("#ffffff", 0.95) if theme == "light" else _hex_to_rgba("#111827", 0.92)

            fig.add_annotation(
                x=rmax[x_col], y=rmax[y_col],
                text=f"Đỉnh: {fmt_vn(rmax[y_col])}",
                showarrow=True, arrowhead=2, ax=0, ay=-34,
                bgcolor=ann_bg,
                bordercolor=GREEN_BORDER, borderwidth=1
            )
            fig.add_annotation(
                x=rmin[x_col], y=rmin[y_col],
                text=f"Đáy: {fmt_vn(rmin[y_col])}",
                showarrow=True, arrowhead=2, ax=0, ay=34,
                bgcolor=ann_bg,
                bordercolor="#cbd5e1", borderwidth=1
            )

        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot", spikethickness=1)
        fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot", spikethickness=1)
        fig.update_layout(
            hovermode="x unified",
            hoverlabel=dict(font_size=12),
            legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0)
        )
    except Exception:
        return fig
    return fig

def enhance_p1_chart3_monthly_bar(fig, g: pd.DataFrame, x_col: str, y_col: str, metric_label: str, theme: str = "light"):
    try:
        if fig is None or g is None or g.empty:
            return fig
        if x_col not in g.columns or y_col not in g.columns:
            return fig

        gg = g[[x_col, y_col]].copy().sort_values(x_col).reset_index(drop=True)
        gg["val_fmt_local"] = gg[y_col].apply(fmt_vn)
        total_val = float(gg[y_col].sum()) if len(gg) else 0.0
        avg_val = float(gg[y_col].mean()) if len(gg) else 0.0
        gg["share_pct"] = (gg[y_col] / total_val * 100.0) if total_val > 0 else 0.0
        gg["delta_vs_avg"] = gg[y_col] - avg_val
        gg["rank_desc"] = gg[y_col].rank(method="min", ascending=False).astype(int)

        def _fmt_signed(v):
            if pd.isna(v):
                return "0"
            sign = "+" if float(v) > 0 else ""
            return f"{sign}{fmt_vn(v)}"

        gg["share_pct_fmt"] = gg["share_pct"].apply(lambda x: f"{float(x):.1f}%")
        gg["delta_vs_avg_fmt"] = gg["delta_vs_avg"].apply(_fmt_signed)
        gg["rank_fmt"] = gg["rank_desc"].apply(lambda x: f"#{int(x)}")

        i_max = int(gg[y_col].idxmax()) if len(gg) else -1
        i_min = int(gg[y_col].idxmin()) if len(gg) else -1

        colors = []
        line_colors = []
        for i, row in gg.iterrows():
            v = float(row[y_col])
            if i == i_max:
                colors.append("#15803d")
                line_colors.append("#14532d")
            elif i == i_min:
                colors.append("#86efac")
                line_colors.append("#4ade80")
            elif v >= avg_val:
                colors.append("#22c55e")
                line_colors.append("#16a34a")
            else:
                colors.append("#bbf7d0")
                line_colors.append("#86efac")

        text_vals = [""] * len(gg)
        if len(gg) <= 8:
            text_vals = gg["val_fmt_local"].tolist()
        elif len(gg) > 0:
            text_vals[i_max] = gg.loc[i_max, "val_fmt_local"]
            text_vals[i_min] = gg.loc[i_min, "val_fmt_local"]
            text_vals[len(gg) - 1] = gg.loc[len(gg) - 1, "val_fmt_local"]
            if len(gg) >= 2:
                text_vals[0] = gg.loc[0, "val_fmt_local"]

        if len(fig.data) > 0:
            tr = fig.data[0]
            tr.update(
                marker=dict(
                    color=colors,
                    line=dict(color=line_colors, width=1.2)
                ),
                customdata=gg[["val_fmt_local", "share_pct_fmt", "delta_vs_avg_fmt", "rank_fmt"]].to_numpy(),
                hovertemplate=(
                    "Tháng: %{x|%m/%Y}<br>"
                    + f"{metric_label}: "
                    + "%{customdata[0]}<br>"
                    + "Tỷ trọng: %{customdata[1]}<br>"
                    + "So với TB: %{customdata[2]}<br>"
                    + "Xếp hạng tháng: %{customdata[3]}"
                    + "<extra></extra>"
                ),
                text=text_vals,
                textposition="outside",
                cliponaxis=False,
                textfont=dict(size=10, color="#111827" if theme == "light" else "white")
            )

        try:
            fig.add_hline(
                y=avg_val,
                line_dash="dash",
                line_width=1.5,
                line_color="#64748b",
                annotation_text=f"TB: {fmt_vn(avg_val)}",
                annotation_position="top right",
                annotation_font_size=11
            )
        except Exception:
            pass

        trend_color = "#0f172a" if theme == "light" else "#e2e8f0"
        fig.add_scatter(
            x=gg[x_col],
            y=gg[y_col],
            mode="lines+markers",
            name="Xu hướng",
            line=dict(width=2.2, color=trend_color),
            marker=dict(size=6, color=trend_color),
            opacity=0.68,
            hovertemplate="Tháng: %{x|%m/%Y}<br>Xu hướng: %{y:,.0f}<extra></extra>"
        )

        ann_bg = _hex_to_rgba("#ffffff", 0.95) if theme == "light" else _hex_to_rgba("#111827", 0.92)

        if len(gg) >= 2:
            fig.add_annotation(
                x=gg.loc[i_max, x_col], y=gg.loc[i_max, y_col],
                text="Đỉnh",
                showarrow=True, arrowhead=2, ax=0, ay=-28,
                bgcolor=ann_bg,
                bordercolor=GREEN_BORDER, borderwidth=1
            )
            fig.add_annotation(
                x=gg.loc[i_min, x_col], y=gg.loc[i_min, y_col],
                text="Đáy",
                showarrow=True, arrowhead=2, ax=0, ay=28,
                bgcolor=ann_bg,
                bordercolor="#cbd5e1", borderwidth=1
            )

        top3 = gg.sort_values(y_col, ascending=False).head(3).reset_index(drop=True)
        for j, (_, rr) in enumerate(top3.iterrows(), start=1):
            try:
                badge = f"TOP {j}"
                fig.add_annotation(
                    x=rr[x_col],
                    y=rr[y_col],
                    text=badge,
                    showarrow=False,
                    yshift=30 + (j - 1) * 14,
                    font=dict(size=10, color="#ffffff"),
                    bgcolor="#166534" if j == 1 else ("#16a34a" if j == 2 else "#22c55e"),
                    bordercolor="#14532d",
                    borderwidth=1,
                    borderpad=3
                )
            except Exception:
                pass

        fig.update_layout(
            bargap=0.22,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0)
        )

        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot", spikethickness=1)
        fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot", spikethickness=1, zeroline=True, zerolinewidth=1)

        m = fig.layout.margin if getattr(fig.layout, "margin", None) else None
        if m:
            fig.update_layout(margin=dict(l=(m.l or 16), r=(m.r or 16), t=max((m.t or 210), 260), b=(m.b or 16)))

    except Exception:
        return fig
    return fig

def top_n_keep_other(df: pd.DataFrame, cat_col: str, val_col: str, n: int = 8, other_label: str = "Khác", keep_cats=None):
    if cat_col not in df.columns or val_col not in df.columns or df.empty:
        return df.copy(), cat_col
    tmp = df.copy()
    tmp[cat_col] = tmp[cat_col].astype(str)
    new_col = f"{cat_col}__show"
    if n is None or (isinstance(n, (int, float)) and int(n) <= 0):
        tmp[new_col] = tmp[cat_col]
        return tmp, new_col
    keep_cats = keep_cats or []
    keep_cats = [str(x) for x in keep_cats if x is not None]
    top_cats = (
        tmp.groupby(cat_col, as_index=False)[val_col].sum()
           .sort_values(val_col, ascending=False)
           .head(n)[cat_col]
           .tolist()
    )
    for k in keep_cats:
        if k in tmp[cat_col].unique().tolist() and k not in top_cats:
            top_cats.append(k)
    tmp[new_col] = tmp[cat_col].where(tmp[cat_col].isin(top_cats), other_label)
    return tmp, new_col

def make_vn_donut(df: pd.DataFrame, names: str, values: str, title: str, max_slices: int | None = 8, color_map=None, theme: str = "light"):
    dff = df.copy()
    if dff.empty:
        fig = px.pie(dff, names=names, values=values, hole=0.45)
        fig = apply_exec_layout(fig, theme=theme, title=title, top=130)
        return fig
    dff[names] = dff[names].astype(str)
    g = dff.groupby(names, as_index=False)[values].sum().sort_values(values, ascending=False)
    if max_slices is not None and int(max_slices) > 0 and len(g) > int(max_slices):
        top = g.head(int(max_slices)).copy()
        other = pd.DataFrame({names: ["Khác"], values: [g.iloc[int(max_slices):][values].sum()]})
        g = pd.concat([top, other], ignore_index=True)
    g["val_fmt"] = g[values].apply(fmt_vn)
    kwargs = dict(names=names, values=values, hole=0.52, hover_data={"val_fmt": True, values: False})
    if color_map is not None:
        kwargs["color_discrete_map"] = color_map
    fig = px.pie(g, **kwargs)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig = apply_exec_layout(fig, theme=theme, title=title, top=135)
    return fig

def empty_figure(message: str = "Không có dữ liệu", theme: str = "light"):
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=15, color="#64748b" if theme == "light" else "white")
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        plot_bgcolor=LIGHT_BG if theme == "light" else DARK_BG,
        paper_bgcolor=LIGHT_BG if theme == "light" else DARK_BG,
        margin=dict(l=10, r=10, t=40, b=10)
    )
    return fig


def _zoom_graph_hidden_style() -> dict:
    """Keep zoom Graph mounted but visually hidden to avoid Plotly.react/_doPlot warnings."""
    return {
        "visibility": "hidden",
        "height": "1px",
        "minHeight": "1px",
        "maxHeight": "1px",
        "overflow": "hidden",
        "pointerEvents": "none",
    }


def _zoom_graph_visible_style() -> dict:
    return {
        "display": "block",
        "visibility": "visible",
        "height": "82vh",
        "pointerEvents": "auto",
    }

def card_top_accent():
    return html.Div(className="kpi-top-accent", style={"borderTopLeftRadius": "22px", "borderTopRightRadius": "22px"})

def executive_header(title: str, subtitle: str = "", right_children=None):
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div(title, className="exec-title"),
                            html.Div(subtitle, className="exec-subtitle") if subtitle else None,
                        ],
                        md=8
                    ),
                    dbc.Col(
                        html.Div(right_children, className="exec-chip-row") if right_children is not None else html.Div(),
                        md=4
                    )
                ],
                className="align-items-center g-3"
            )
        ],
        className="exec-header-card"
    )

def summary_pill(text, icon=None):
    return html.Span(
        [icon, html.Span(text, className="ms-1") if icon is not None else html.Span(text)],
        className="summary-pill"
    )

def make_kpi_card(title, body_id, target, icon=None, min_height="220px"):
    title_row = html.Div(
        [
            html.Div(
                [
                    icon if icon is not None else fa_icon("fa-chart-column", 16, GREEN_PRIMARY),
                    html.Span(title, className="ms-2")
                ],
                className="d-flex align-items-center"
            )
        ],
        className="kpi-card-title mb-2"
    )
    return html.Div(
        dbc.Card(
            [
                card_top_accent(),
                dbc.CardBody(
                    [
                        title_row,
                        html.Div(id=body_id)
                    ],
                    style={"padding": "18px 20px"}
                )
            ],
            className="executive-kpi-card",
            style={"minHeight": min_height}
        ),
        id=_zoomable_wrap("kpi", target),
        n_clicks=0,
        style={"cursor": "pointer"}
    )

def make_graph_card(graph_id, target, height="390px"):
    return html.Div(
        dbc.Card(
            [
                card_top_accent(),
                dbc.CardBody(
                    [
                        dcc.Graph(
                            id=graph_id,
                            config=_graph_config(),
                            style={"height": height}
                        )
                    ],
                    style={"padding": "16px 16px 20px", "overflow": "visible"}
                )
            ],
            className="executive-graph-card"
        ),
        id=_zoomable_wrap("fig", target),
        n_clicks=0,
        style={"cursor": "zoom-in"}
    )

def make_table_card(title, subtitle, table_component):
    return dbc.Card(
        [
            card_top_accent(),
            dbc.CardBody(
                [
                    html.Div("Bảng dữ liệu", className="section-eyebrow"),
                    html.Div(title, style={"fontSize": "24px", "fontWeight": "800", "color": TEXT_LIGHT_UI}),
                    html.Div(subtitle, className="home-mini-note mb-3"),
                    table_component
                ],
                style={"padding": "18px 20px"}
            )
        ],
        className="executive-table-card"
    )

def home_kpi_markup(main_text, subtitle_text="", delta_text=None, delta_class="neutral", extra_lines=None):
    extra_lines = extra_lines or []
    return html.Div(
        [
            html.Div(main_text, style={"fontSize": "30px", "fontWeight": "800", "lineHeight": "1.08", "color": TEXT_LIGHT_UI}),
            html.Div(subtitle_text, style={"fontSize": "12px", "fontWeight": "600", "color": MUTED_LIGHT_UI, "marginTop": "6px"}) if subtitle_text else None,
            html.Span(delta_text, className=f"kpi-delta-pill {delta_class}", style={"marginTop": "10px", "display": "inline-flex"}) if delta_text else None,
            html.Div(extra_lines, style={"marginTop": "10px"}) if extra_lines else None
        ]
    )

def safe_number(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def signed_pct_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "0.0%"
    sign = "+" if float(v) > 0 else ""
    return f"{sign}{float(v):.1f}%"

def signed_diff_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "0"
    sign = "+" if float(v) > 0 else ""
    return f"{sign}{fmt_vn(v)}"

def json_safe(obj):
    if isinstance(obj, pd.DataFrame):
        return json_safe(obj.to_dict("records"))
    if isinstance(obj, pd.Series):
        return json_safe(obj.to_dict())
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        if math.isnan(float(obj)):
            return None
        return float(obj)
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(x) for x in obj]
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass
    return obj

def enhance_zoom_figure(fig_dict):
    f = copy.deepcopy(fig_dict) if fig_dict is not None else None
    if not f:
        return f
    layout = f.get("layout", {}) if isinstance(f, dict) else {}
    if isinstance(layout, dict):
        layout["height"] = 860
        layout.setdefault("margin", {})
        layout["margin"].update({"l": 40, "r": 20, "t": max(layout.get("margin", {}).get("t", 190), 240), "b": 55})

        layout.setdefault("font", {})
        layout["font"]["size"] = max(int(layout["font"].get("size", 14)), 15)

        layout.setdefault("hoverlabel", {})
        layout["hoverlabel"].setdefault("font", {})
        layout["hoverlabel"]["font"]["size"] = max(int(layout["hoverlabel"]["font"].get("size", 14)), 15)

        if "title" in layout and isinstance(layout["title"], dict):
            layout["title"].setdefault("font", {})
            layout["title"]["font"]["size"] = max(int(layout["title"].get("font", {}).get("size", 18)), 24)
            layout["title"]["x"] = 0.5

        layout.setdefault("legend", {})
        if isinstance(layout["legend"], dict):
            layout["legend"].setdefault("font", {})
            layout["legend"]["font"]["size"] = max(int(layout["legend"].get("font", {}).get("size", 12)), 14)

        for ax in ["xaxis", "yaxis", "yaxis2"]:
            if ax in layout and isinstance(layout[ax], dict):
                layout[ax].setdefault("tickfont", {})
                layout[ax]["tickfont"]["size"] = max(int(layout[ax]["tickfont"].get("size", 12)), 13)
                layout[ax].setdefault("title", {})
                if isinstance(layout[ax]["title"], dict):
                    layout[ax]["title"].setdefault("font", {})
                    layout[ax]["title"]["font"]["size"] = max(int(layout[ax]["title"].get("font", {}).get("size", 12)), 15)

        f["layout"] = layout

    data = f.get("data", []) if isinstance(f, dict) else []
    if isinstance(data, list):
        for tr in data:
            if not isinstance(tr, dict):
                continue
            t = tr.get("type", None)
            if t in (None, "scatter"):
                tr.setdefault("line", {})
                if isinstance(tr["line"], dict):
                    tr["line"]["width"] = max(int(tr["line"].get("width", 3)), 4)
                tr.setdefault("marker", {})
                if isinstance(tr["marker"], dict):
                    tr["marker"]["size"] = max(int(tr["marker"].get("size", 7)), 9)
            if t == "bar":
                tr.setdefault("textfont", {})
                if isinstance(tr["textfont"], dict):
                    tr["textfont"]["size"] = max(int(tr["textfont"].get("size", 12)), 14)
            if t == "pie":
                tr.setdefault("textfont", {})
                if isinstance(tr["textfont"], dict):
                    tr["textfont"]["size"] = max(int(tr["textfont"].get("size", 12)), 14)
    return f

def _limit_store_rows(rows, max_rows: int):
    if rows is None:
        return [], False, 0
    if isinstance(rows, pd.DataFrame):
        total = len(rows)
        if max_rows and total > max_rows:
            return rows.head(max_rows).to_dict("records"), True, total
        return rows.to_dict("records"), False, total
    if isinstance(rows, (list, tuple)):
        total = len(rows)
        if max_rows and total > max_rows:
            return list(rows[:max_rows]), True, total
        return list(rows), False, total
    return rows, False, 0

def _compact_zoom_figure_dict(fig_dict):
    """Reduce dcc.Store payload for zoom figures without changing the visible chart."""
    if not DASH_ZOOM_COMPACT_FIGURE or not isinstance(fig_dict, dict):
        return fig_dict
    try:
        f = copy.deepcopy(fig_dict)
        layout = f.get("layout")
        if isinstance(layout, dict):
            # Plotly templates are often the largest part of a figure dict and are not
            # needed for an already styled dashboard figure.
            layout.pop("template", None)
            for volatile_key in ["uirevision", "selectionrevision", "editrevision"]:
                if volatile_key in layout and layout.get(volatile_key) in [None, ""]:
                    layout.pop(volatile_key, None)
        data = f.get("data")
        if isinstance(data, list):
            for tr in data:
                if not isinstance(tr, dict):
                    continue
                # These fields are useful while constructing charts but expensive to
                # keep inside every zoom-store. They do not affect the enlarged view.
                for key in [
                    "customdata", "custom_data", "ids", "id", "meta",
                    "selectedpoints", "selected", "unselected", "transforms",
                ]:
                    tr.pop(key, None)
                # Very long hovertemplates also add payload. Keep normal hover text,
                # but drop generated templates for compact serverless payloads.
                if isinstance(tr.get("hovertemplate"), str) and len(tr.get("hovertemplate", "")) > 240:
                    tr.pop("hovertemplate", None)
        return f
    except Exception:
        return fig_dict


def _zoom_trace_names_from_fig(fig_dict):
    try:
        data = fig_dict.get("data", []) if isinstance(fig_dict, dict) else []
        if not isinstance(data, list):
            return []
        return [str(tr.get("name", "")).strip() if isinstance(tr, dict) and tr.get("name", None) not in [None, ""] else None for tr in data]
    except Exception:
        return []


def _zoom_cache_fingerprint(value, max_chars: int = 12000):
    try:
        raw = json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(value)
    if len(raw) > max_chars:
        raw = raw[:max_chars] + raw[-1024:]
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


ZOOM_OPEN_RENDER_CACHE = {}
ZOOM_DRILL_RENDER_CACHE = {}


def _zoom_open_cache_get(key):
    return ZOOM_OPEN_RENDER_CACHE.get(key)


def _zoom_open_cache_set(key, value):
    try:
        if len(ZOOM_OPEN_RENDER_CACHE) > DASH_ZOOM_OPEN_CACHE_MAX:
            ZOOM_OPEN_RENDER_CACHE.clear()
        ZOOM_OPEN_RENDER_CACHE[key] = value
    except Exception:
        pass
    return value


def _zoom_drill_cache_get(key):
    return ZOOM_DRILL_RENDER_CACHE.get(key)


def _zoom_drill_cache_set(key, value):
    try:
        if len(ZOOM_DRILL_RENDER_CACHE) > DASH_ZOOM_DRILL_CACHE_MAX:
            ZOOM_DRILL_RENDER_CACHE.clear()
        ZOOM_DRILL_RENDER_CACHE[key] = value
    except Exception:
        pass
    return value


def _zoom_open_cache_key(target, store, theme):
    """Fast cache key for zoom-open without serializing the entire Plotly figure."""
    try:
        store = store or {}
        meta = store.get("meta", {}) if isinstance(store, dict) else {}
        rows = store.get("rows", []) if isinstance(store, dict) else []
        fig = store.get("figure", {}) if isinstance(store, dict) else {}
        data = fig.get("data", []) if isinstance(fig, dict) else []
        layout = fig.get("layout", {}) if isinstance(fig, dict) else {}
        title_obj = layout.get("title", {}) if isinstance(layout, dict) else {}
        if isinstance(title_obj, dict):
            title_text = title_obj.get("text", "")
        else:
            title_text = str(title_obj or "")
        fig_sig = {
            "kind": store.get("kind") if isinstance(store, dict) else None,
            "data_n": len(data) if isinstance(data, list) else 0,
            "title": title_text,
            "trace_names": meta.get("trace_names", []),
            "figure_included": meta.get("figure_included"),
            "figure_compacted": meta.get("figure_compacted"),
        }
        return (
            str(target),
            str(theme or "light"),
            _zoom_cache_fingerprint(meta, max_chars=5000),
            len(rows) if isinstance(rows, list) else 0,
            _zoom_cache_fingerprint(rows, max_chars=9000),
            _zoom_cache_fingerprint(fig_sig, max_chars=3000),
        )
    except Exception:
        return (str(target), str(theme or "light"), str(time.time()))


def _zoom_drill_cache_key(target, store, clickData, theme):
    meta = (store or {}).get("meta", {}) if isinstance(store, dict) else {}
    rows = (store or {}).get("rows", []) if isinstance(store, dict) else []
    pt = ((clickData or {}).get("points") or [{}])[0]
    point_key = {k: pt.get(k) for k in ["x", "y", "label", "text", "curveNumber", "pointNumber", "pointIndex"]}
    return (
        str(target),
        str(theme or "light"),
        _zoom_cache_fingerprint(meta, max_chars=4000),
        len(rows) if isinstance(rows, list) else 0,
        _zoom_cache_fingerprint(rows, max_chars=10000),
        _zoom_cache_fingerprint(point_key, max_chars=2000),
    )


def pack_fig_store(fig, rows=None, meta=None):
    fig_dict = {}
    include_figure = bool(DASH_ZOOM_STORE_INCLUDE_FIGURE or DASH_ZOOM_FORCE_FIGURE_FOR_CHARTS)
    if include_figure:
        try:
            fig_dict = fig.to_dict()
        except Exception:
            fig_dict = fig
    trace_names = _zoom_trace_names_from_fig(fig_dict)
    fig_dict = _compact_zoom_figure_dict(fig_dict)
    limited_rows, truncated, total_rows = _limit_store_rows(rows or [], DASH_FIGURE_STORE_MAX_ROWS)
    meta_out = dict(meta or {})
    meta_out["figure_included"] = bool(include_figure)
    meta_out["figure_compacted"] = bool(include_figure and DASH_ZOOM_COMPACT_FIGURE)
    meta_out["trace_names"] = trace_names
    meta_out["zoom_first"] = True
    if truncated:
        meta_out["rows_truncated"] = True
        meta_out["rows_total"] = total_rows
        meta_out["rows_limit"] = DASH_FIGURE_STORE_MAX_ROWS
    return {"kind": "fig", "figure": fig_dict, "rows": json_safe(limited_rows), "meta": json_safe(meta_out)}


def pack_daily_fig_store(fig, rows=None, meta=None):
    """Daily-only zoom store: keep rows/meta but do not duplicate chart figures in dcc.Store.

    The visible dcc.Graph already receives the full Plotly figure. A clientside zoom
    selector injects that graph figure only when the user actually opens zoom. This
    removes 5 duplicated figure JSON payloads from the main Daily callback response.
    """
    if not DASH_DAILY_LAZY_ZOOM_FIGURES:
        return pack_fig_store(fig, rows=rows, meta=meta)
    limited_rows, truncated, total_rows = _limit_store_rows(rows or [], DASH_FIGURE_STORE_MAX_ROWS)
    meta_out = dict(meta or {})
    meta_out["figure_included"] = False
    meta_out["figure_lazy_from_graph"] = True
    meta_out["figure_compacted"] = False
    meta_out["zoom_first"] = True
    try:
        meta_out["trace_names"] = [str(getattr(tr, "name", "") or "") for tr in getattr(fig, "data", [])]
    except Exception:
        meta_out["trace_names"] = []
    if truncated:
        meta_out["rows_truncated"] = True
        meta_out["rows_total"] = total_rows
        meta_out["rows_limit"] = DASH_FIGURE_STORE_MAX_ROWS
    return {"kind": "fig", "figure": {}, "rows": json_safe(limited_rows), "meta": json_safe(meta_out)}

def pack_home_fig_store(fig, rows=None, meta=None):
    """Home-only zoom store: keep rows/meta but do not duplicate chart figures in dcc.Store."""
    if not DASH_HOME_LAZY_ZOOM_FIGURES:
        return pack_fig_store(fig, rows=rows, meta=meta)
    limited_rows, truncated, total_rows = _limit_store_rows(rows or [], DASH_FIGURE_STORE_MAX_ROWS)
    meta_out = dict(meta or {})
    meta_out["figure_included"] = False
    meta_out["figure_lazy_from_graph"] = True
    meta_out["figure_compacted"] = False
    meta_out["zoom_first"] = True
    try:
        meta_out["trace_names"] = [str(getattr(tr, "name", "") or "") for tr in getattr(fig, "data", [])]
    except Exception:
        meta_out["trace_names"] = []
    if truncated:
        meta_out["rows_truncated"] = True
        meta_out["rows_total"] = total_rows
        meta_out["rows_limit"] = DASH_FIGURE_STORE_MAX_ROWS
    return {"kind": "fig", "figure": {}, "rows": json_safe(limited_rows), "meta": json_safe(meta_out)}


def _kpi_store_effective_row_limit(rows=None, configured_limit=None) -> int:
    """Return a safe KPI store row limit.

    KPI zoom tables are small summary tables. On Vercel, an environment variable
    such as DASH_KPI_STORE_MAX_ROWS may be set too low and can truncate Daily KPI
    detail rows to only 1 branch. Keep all small KPI tables intact while still
    capping unexpectedly large stores.
    """
    try:
        configured = int(configured_limit if configured_limit is not None else DASH_KPI_STORE_MAX_ROWS)
    except Exception:
        configured = 0
    try:
        if rows is None:
            total = 0
        elif isinstance(rows, pd.DataFrame):
            total = len(rows)
        elif isinstance(rows, (list, tuple)):
            total = len(rows)
        else:
            total = 0
    except Exception:
        total = 0

    # Daily KPI details need 9 regions. Use 12 as a safe floor and preserve all
    # small summary tables so production env overrides cannot hide branches.
    safe_floor = 12
    small_table_limit = 24
    if total and total <= small_table_limit:
        return max(configured, total, safe_floor)
    return max(configured, safe_floor)


def pack_kpi_store(title, main, subtitle, rows=None, kind="kpi"):
    row_limit = _kpi_store_effective_row_limit(rows, DASH_KPI_STORE_MAX_ROWS)
    limited_rows, truncated, total_rows = _limit_store_rows(rows or [], row_limit)
    payload = {"kind": kind, "title": title, "main": main, "subtitle": subtitle, "rows": json_safe(limited_rows)}
    meta = {"rows_limit_effective": row_limit, "rows_limit_env": int(DASH_KPI_STORE_MAX_ROWS)}
    if truncated:
        meta.update({"rows_truncated": True, "rows_total": total_rows, "rows_limit": row_limit})
    payload["meta"] = meta
    return payload

def safe_month_label(x):
    try:
        return pd.to_datetime(x).strftime("%m/%Y")
    except Exception:
        return str(x)

def _get_store_for_target(target: str, all_store_data: list):
    for k, v in ctx.states.items():
        if k.endswith(".data") and f'"target":"{target}"' in k:
            return v
    return None


def _zoom_table_styles(theme: str, dense: bool = False):
    if theme == "light":
        style_header = {
            "backgroundColor": "#f2f4f7",
            "color": "#111827",
            "fontWeight": "900",
            "textAlign": "center",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.25",
            "padding": "10px 8px",
            "border": "1px solid #d9e3ef",
        }
        style_cell = {
            "backgroundColor": "#ffffff",
            "color": "#111827",
            "textAlign": "center",
            "padding": "8px",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.25",
            "border": "1px solid #e5edf5",
            "minWidth": "86px" if dense else "96px",
            "width": "86px" if dense else "96px",
            "maxWidth": "150px" if dense else "170px",
        }
    else:
        style_header = {
            "backgroundColor": "#222",
            "color": "white",
            "fontWeight": "900",
            "textAlign": "center",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.25",
            "padding": "10px 8px",
            "border": "1px solid #3b3b57",
        }
        style_cell = {
            "backgroundColor": DARK_BG,
            "color": "white",
            "textAlign": "center",
            "padding": "8px",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.25",
            "border": "1px solid #3b3b57",
            "minWidth": "86px" if dense else "96px",
            "width": "86px" if dense else "96px",
            "maxWidth": "150px" if dense else "170px",
        }

    style_table = {
        "width": "100%",
        "minWidth": "100%",
        "maxWidth": "100%",
        "overflowX": "auto",
        "overflowY": "hidden",
        "borderRadius": "14px",
    }
    wrapper_style = {
        "width": "100%",
        "maxWidth": "100%",
        "overflowX": "auto",
        "overflowY": "hidden",
        "paddingBottom": "4px",
    }
    return style_header, style_cell, style_table, wrapper_style


# =========================================================
# ZOOM / DRILL-DOWN PRESENTATION CONTRACT
# =========================================================
# Những helper này chỉ chuẩn hoá hiển thị trong modal phóng to và bảng drill-down.
# Không thay đổi dữ liệu nguồn, không thay đổi layout/menu/filter, không cache callback output.
ZOOM_DETAIL_COLUMN_LABELS = {
    "ngay_du_lieu": "Ngày dữ liệu",
    "ngay_label": "Ngày",
    "thang": "Tháng",
    "thang_nam": "Tháng",
    "thang_nam_vn": "Tháng dữ liệu",
    "thang_label": "Tháng",
    "nam": "Năm",
    "khu_vuc": "Khu vực",
    "label": "Nhóm dữ liệu",
    "daily_lh_label": "Loại hình",
    "loai_hinh_std": "Loại hình hợp tác",
    "loaihinh_hoptac": "Loại hình hợp tác",
    "loai_hinh": "Loại hình",
    "loai_hop_dong_std": "Loại hợp đồng",
    "loai_hopdong": "Loại hợp đồng",
    "loai_hop_dong": "Loại hợp đồng",
    "metric_label": "Chỉ tiêu",
    "metric_key": "Mã chỉ tiêu",
    "zoom_click_metric_label": "Chỉ tiêu",
    "zoom_click_value_fmt": "Giá trị",
    "metric_fmt": "Giá trị",
    "value_fmt": "Giá trị",
    "val_fmt": "Giá trị",
    "rev_fmt": "Doanh thu",
    "trip_fmt": "Số cuốc",
    "avg_fmt": "Bình quân",
    "avg_per_trip_fmt": "Doanh thu bình quân / cuốc",
    "avg_per_trip": "Doanh thu bình quân / cuốc",
    "avg_per_vehicle_day_fmt": "Doanh thu bình quân / xe kinh doanh-ngày",
    "vehicle_day_fmt": "Lượt xe kinh doanh-ngày",
    "active_vehicle_fmt": "Xe hoạt động",
    "active_driver_fmt": "Tài xế",
    "rev_ma7_fmt": "Doanh thu TB 7 ngày",
    "pct": "Tỷ trọng",
    "pct_fmt": "Tỷ trọng",
    "ty_trong_fmt": "Tỷ trọng",
    "pct_segment_fmt": "Đóng góp nhóm",
    "count_fmt": "Số lượng",
    "bks_fmt": "Biển kiểm soát",
    "xe_fmt": "Số xe",
    "so_luong_xe": "Số lượng xe",
    "so_bien_kiem_soat": "Số biển kiểm soát",
    "so_so_tai": "Số sổ tài",
    "tong_so_cho": "Tổng số chỗ",
    "so_cho_binh_quan_xe": "Số chỗ bình quân / xe",
    "so_cho_loc": "Số chỗ",
    "nhan_so_cho": "Nhãn số chỗ",
    "loai_xe": "Loại xe",
    "nhom_nhien_lieu": "Nhóm nhiên liệu",
    "tong_doanh_thu": "Tổng doanh thu",
    "tong_so_cuoc": "Tổng số cuốc",
    "gia_tri": "Giá trị",
    "tong_phai_chi": "Tổng phải chi",
    "so_diem_tiep_thi": "Số điểm tiếp thị",
    "chi_phi_binh_quan_moi_diem": "Chi phí bình quân / điểm",
    "so_ho_so_hoa_hong": "Số hồ sơ hoa hồng",
    "tong_da_chi_du": "Tổng đã chi đủ",
    "tong_chua_chi_du": "Tổng chưa chi đủ",
    "tong_khong_chi": "Tổng không chi",
    "so_ho_so_da_chi_du": "Hồ sơ đã chi đủ",
    "so_ho_so_chua_chi_du": "Hồ sơ chưa chi đủ",
    "so_ho_so_khong_chi": "Hồ sơ không chi",
    "chi_phi_binh_quan_moi_ho_so": "Chi phí bình quân / hồ sơ",
    "so_diem_moi_ky_hd": "Điểm mới / kỳ HĐ",
    "so_loai_hinh_kd": "Số loại hình KD",
    "tong_tien_de_xuat": "Tổng tiền đề xuất",
    "so_tien_thu_duoc": "Số tiền đã xử lý",
    "so_tien_da_xu_ly": "Số tiền đã xử lý",
    "so_tien_con_no": "Số tiền chênh lệch",
    "so_bien_ban": "Số biên bản",
    "so_bien_ban_da_xu_ly": "Biên bản đã xử lý",
    "so_bien_ban_thu_hoan_tat": "Biên bản thu hoàn tất",
    "bo_phan": "Bộ phận",
    "so_luong_nhan_su": "Số lượng nhân sự",
    "so_luong_nhan_su_fmt": "Số lượng nhân sự",
    "so_vao_lam": "Vào làm",
    "so_vao_lam_fmt": "Vào làm",
    "so_nghi_viec": "Nghỉ việc",
    "so_nghi_viec_fmt": "Nghỉ việc",
    "net_flow": "Biến động thuần",
    "join_fmt": "Vào làm",
    "leave_fmt": "Nghỉ việc",
    "net_fmt": "Biến động thuần",
    "headcount_dau_ky": "Nhân sự đầu kỳ",
    "headcount_dau_ky_fmt": "Nhân sự đầu kỳ",
    "so_giu_on_dinh": "Giữ ổn định",
    "so_giu_on_dinh_fmt": "Giữ ổn định",
    "bien_dong_thuan": "Biến động thuần",
    "bien_dong_thuan_fmt": "Biến động thuần",
    "so_duoi_1_nam": "Dưới 1 năm",
    "so_duoi_1_nam_fmt": "Dưới 1 năm",
    "so_tu_1_den_3_nam": "Từ 1 đến 3 năm",
    "so_tu_1_den_3_nam_fmt": "Từ 1 đến 3 năm",
    "so_tren_3_nam": "Trên 3 năm",
    "so_tren_3_nam_fmt": "Trên 3 năm",
    "ty_le_tang": "Tỷ lệ tăng",
    "ty_le_tang_fmt": "Tỷ lệ tăng",
    "ty_le_giam": "Tỷ lệ giảm",
    "ty_le_giam_fmt": "Tỷ lệ giảm",
    "ty_le_giu_chan": "Tỷ lệ giữ chân",
    "ty_le_giu_chan_fmt": "Tỷ lệ giữ chân",
    "tang_fmt": "Tỷ lệ tăng",
    "giam_fmt": "Tỷ lệ giảm",
    "giu_fmt": "Tỷ lệ giữ chân",
    "nhom_vong_doi": "Nhóm vòng đời",
    "du_lieu_nguon": "Nguồn dữ liệu",
    "ghi_chu_nguon": "Ghi chú nguồn",
    "fleet_bridge_metric": "Chỉ tiêu đội xe",
}

ZOOM_DETAIL_CONTEXT_ORDER = [
    "ngay_label", "thang_label", "thang", "nam", "khu_vuc", "label", "daily_lh_label",
    "loai_hinh_std", "loaihinh_hoptac", "loai_hinh", "loai_hop_dong_std", "loai_hopdong", "loai_hop_dong",
    "metric_label", "loai_xe", "nhom_nhien_lieu", "nhom_vong_doi", "bo_phan",
]
ZOOM_DETAIL_VALUE_ORDER = [
    "metric_fmt", "value_fmt", "val_fmt", "rev_fmt", "trip_fmt", "avg_per_trip_fmt", "avg_per_vehicle_day_fmt", "vehicle_day_fmt", "rev_ma7_fmt",
    "avg_fmt", "pct_fmt", "ty_trong_fmt", "pct_segment_fmt", "count_fmt", "xe_fmt", "bks_fmt",
    "join_fmt", "leave_fmt", "net_fmt", "tang_fmt", "giam_fmt", "giu_fmt",
    "tong_doanh_thu", "tong_so_cuoc", "gia_tri", "so_luong_xe", "so_bien_kiem_soat", "so_so_tai", "tong_so_cho",
    "tong_phai_chi", "so_diem_tiep_thi", "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no",
    "so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
    "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "net_flow", "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
    "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "ty_le_tang", "ty_le_giam", "ty_le_giu_chan",
]
ZOOM_DETAIL_INTERNAL_SKIP = {
    "thang_nam_vn", "thang_nam", "ngay_du_lieu", "metric", "metric_key", "pct", "avg_per_trip",
    # Plotly/frontend/dev-only fields must never be exposed as business columns.
    "color", "colour", "value", "values", "x", "y", "z", "text", "hovertext", "hoverinfo",
    "customdata", "custom_data", "curveNumber", "pointNumber", "pointIndex", "pointNumbers",
    "bbox", "marker", "marker_color", "line_color", "legendgroup", "ids", "id", "index",
}


def _zoom_metric_label(meta: dict | None, default: str = "Giá trị") -> str:
    try:
        value = (meta or {}).get("metric_label") or default
        value = re.sub(r"<br\s*/?>", " • ", str(value), flags=re.I)
        value = re.sub(r"\s+", " ", value).strip()
        return value or default
    except Exception:
        return default


def _zoom_vn_label(col, metric_label: str | None = None) -> str:
    col = str(col)
    metric_label = metric_label or "Giá trị"
    if col in {"metric_fmt", "value_fmt", "val_fmt"}:
        return metric_label
    if col in ZOOM_DETAIL_COLUMN_LABELS:
        return ZOOM_DETAIL_COLUMN_LABELS[col]
    base = col
    for suffix in ["_fmt", "_std"]:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    if base in ZOOM_DETAIL_COLUMN_LABELS:
        return ZOOM_DETAIL_COLUMN_LABELS[base]
    replacements = {
        "ngay": "Ngày", "thang": "Tháng", "nam": "Năm", "khu": "Khu", "vuc": "vực",
        "tong": "Tổng", "doanh": "doanh", "thu": "thu", "cuoc": "cuốc",
        "so": "Số", "luong": "lượng", "nhan": "nhân", "su": "sự",
        "tai": "tài", "xe": "xe", "hop": "hợp", "dong": "đồng",
        "loai": "loại", "hinh": "hình", "chi": "chi", "phi": "phí",
        "binh": "bình", "quan": "quân", "diem": "điểm", "tiep": "tiếp", "thi": "thị",
        "tien": "tiền", "de": "đề", "xuat": "xuất", "xu": "xử", "ly": "lý",
        "con": "còn", "no": "nợ", "bien": "biên", "ban": "bản",
        "phan": "phân", "quyen": "quyền", "truc": "trực", "thuoc": "thuộc",
        "nhien": "nhiên", "lieu": "liệu", "kiem": "kiểm", "soat": "soát",
        "giu": "giữ", "chan": "chân", "tang": "tăng", "giam": "giảm",
        "duoi": "dưới", "tren": "trên", "tu": "từ", "den": "đến",
        "ty": "Tỷ", "trong": "trọng", "gia": "giá", "tri": "trị", "ma7": "TB 7 ngày",
        "rev": "Doanh thu", "trip": "Số cuốc", "avg": "Bình quân", "pct": "Tỷ trọng",
        "bks": "Biển kiểm soát", "fmt": "", "std": "",
    }
    parts = [p for p in re.split(r"_+", base) if p]
    label = " ".join(replacements.get(p, p) for p in parts).strip()
    return label[:1].upper() + label[1:] if label else col


def _zoom_format_raw_value(col: str, value):
    if value is None:
        return ""
    try:
        if isinstance(value, float) and pd.isna(value):
            return ""
        if isinstance(value, (pd.Timestamp, datetime)):
            return pd.Timestamp(value).strftime("%d/%m/%Y")
        col_l = str(col).lower()
        if col_l.endswith("_fmt") or isinstance(value, str):
            return value
        if "ty_le" in col_l or "pct" in col_l or "ty_trong" in col_l:
            return fmt_pct(value, 1)
        if any(k in col_l for k in ["doanh_thu", "tong", "so_", "gia_tri", "cuoc", "luong", "tien", "xe", "ban", "chi_phi"]):
            return fmt_vn(value)
    except Exception:
        pass
    return value


def _zoom_safe_day_label(x):
    try:
        ts = pd.to_datetime(x, errors="coerce")
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts).strftime("%d/%m/%Y")
    except Exception:
        return None


def _zoom_safe_month_label(x):
    try:
        ts = pd.to_datetime(x, errors="coerce")
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts).strftime("%m/%Y")
    except Exception:
        return None


def _zoom_filter_eq(df: pd.DataFrame, col: str, value) -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns or value in [None, ""]:
        return df
    try:
        value_s = str(value)
        tmp = df[df[col].astype(str) == value_s]
        if not tmp.empty:
            return tmp
        # So sánh dạng đã chuẩn hoá để bắt tiếng Việt/dấu cách khác nhau.
        nv = norm_text(value_s)
        tmp = df[df[col].astype(str).map(norm_text) == nv]
        if not tmp.empty:
            return tmp
    except Exception:
        return df
    return df


def _zoom_trace_name_from_point(fig: dict, pt: dict, meta: dict | None = None):
    try:
        curve = pt.get("curveNumber", None)
        if curve is not None and isinstance(fig.get("data", []), list) and int(curve) < len(fig["data"]):
            name = fig["data"][int(curve)].get("name", None)
            if name not in [None, ""]:
                return str(name).strip()
        trace_names = (meta or {}).get("trace_names", [])
        if curve is not None and isinstance(trace_names, list) and int(curve) < len(trace_names):
            name = trace_names[int(curve)]
            return str(name).strip() if name not in [None, ""] else None
    except Exception:
        return None
    return None


def _zoom_filter_rows_for_point(df: pd.DataFrame, meta: dict, fig: dict, pt: dict):
    """Filter drill rows by the clicked point while keeping chart/card logic unchanged."""
    if df is None or df.empty:
        return df, []
    meta = meta or {}
    pt = pt or {}
    out = df.copy()
    subtitles = []
    x = pt.get("x", None)
    y = pt.get("y", None)
    label = pt.get("label", None)
    text = pt.get("text", None)
    trace_name = _zoom_trace_name_from_point(fig or {}, pt, meta)
    series_field = str(meta.get("series_field") or meta.get("series_key") or "").strip()

    day_label = _zoom_safe_day_label(x)
    month_label = _zoom_safe_month_label(x)
    x_text = str(x).strip() if x not in [None, ""] else None
    y_text = str(y).strip() if y not in [None, ""] else None
    label_text = str(label).strip() if label not in [None, ""] else None
    text_value = str(text).strip() if text not in [None, ""] else None

    if "ngay_label" in out.columns and day_label:
        before = len(out)
        out2 = _zoom_filter_eq(out, "ngay_label", day_label)
        if len(out2) < before or not out2.empty:
            out = out2
            subtitles.append(f"Ngày: {day_label}")
    elif "thang_label" in out.columns and month_label:
        before = len(out)
        out2 = _zoom_filter_eq(out, "thang_label", month_label)
        if len(out2) < before or not out2.empty:
            out = out2
            subtitles.append(f"Tháng: {month_label}")
    elif "thang" in out.columns:
        candidate = label_text or x_text or month_label
        out2 = _zoom_filter_eq(out, "thang", candidate)
        if not out2.empty and len(out2) <= len(out):
            out = out2
            if candidate:
                subtitles.append(f"Tháng: {candidate}")

    # Với line/bar multi-series: trace name là khu vực/chỉ tiêu/nhóm.
    if series_field and trace_name and series_field in out.columns:
        out2 = _zoom_filter_eq(out, series_field, trace_name)
        if not out2.empty:
            out = out2
            subtitles.append(f"Nhóm: {trace_name}")

    # Với pie/donut: click label thường là tên khu vực/nhóm, không phải tháng.
    candidate_values = [label_text, text_value, y_text, x_text, trace_name]
    candidate_cols = []
    if series_field and series_field in out.columns:
        candidate_cols.append(series_field)
    candidate_cols += [
        "khu_vuc", "label", "daily_lh_label", "loai_hinh_std", "loaihinh_hoptac", "loai_hop_dong_std",
        "loai_hopdong", "loai_xe", "nhom_nhien_lieu", "nhom_vong_doi", "metric_label", "bo_phan",
    ]
    for candidate in candidate_values:
        if not candidate:
            continue
        # Tránh lấy ngày ISO làm category nếu đã lọc ngày/tháng ở trên.
        if _zoom_safe_day_label(candidate) and ("ngay_label" in df.columns or "thang_label" in df.columns):
            continue
        for col in candidate_cols:
            if col in out.columns:
                out2 = _zoom_filter_eq(out, col, candidate)
                if not out2.empty and len(out2) <= len(out):
                    out = out2
                    label_name = _zoom_vn_label(col, _zoom_metric_label(meta))
                    subtitles.append(f"{label_name}: {candidate}")
                    return out, list(dict.fromkeys(subtitles))
    return out, list(dict.fromkeys(subtitles))


def _zoom_prepare_detail_df(df: pd.DataFrame, meta: dict | None = None, pt: dict | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    meta = meta or {}
    metric_label = _zoom_metric_label(meta)

    # Không để lộ các field kỹ thuật của Plotly/frontend trong bảng nghiệp vụ.
    technical_cols = [c for c in out.columns if str(c) in ZOOM_DETAIL_INTERNAL_SKIP or str(c).lower() in ZOOM_DETAIL_INTERNAL_SKIP]
    if technical_cols:
        # Nếu store chỉ có cột 'value' là giá trị nghiệp vụ, chuyển sang cột formatted trước khi bỏ raw field.
        for raw_value_col in ["metric", "value", "values", "y"]:
            if raw_value_col in out.columns and not any(c in out.columns for c in ["metric_fmt", "value_fmt", "val_fmt", "rev_fmt"]):
                out["zoom_click_metric_label"] = metric_label
                out["zoom_click_value_fmt"] = out[raw_value_col].map(lambda v: fmt_pct(v, 1) if ("tỷ" in metric_label.lower() or "%" in metric_label) else fmt_vn(v))
                break
        out = out.drop(columns=[c for c in technical_cols if c in out.columns], errors="ignore")

    # Nếu store chỉ có ngữ cảnh mà thiếu giá trị, bổ sung giá trị của điểm click để bảng vẫn có ý nghĩa.
    value_cols = [c for c in out.columns if c in ZOOM_DETAIL_VALUE_ORDER or str(c).endswith("_fmt")]
    if not value_cols and pt:
        y = pt.get("y", pt.get("value", None))
        if y not in [None, ""]:
            out["zoom_click_metric_label"] = metric_label
            out["zoom_click_value_fmt"] = fmt_vn(y) if not ("tỷ" in metric_label.lower() or "%" in metric_label) else fmt_pct(y, 1)
    return out


def _zoom_order_detail_columns(df: pd.DataFrame, meta: dict | None = None, max_cols: int = 12):
    if df is None or df.empty:
        return []
    meta = meta or {}
    metric_label = _zoom_metric_label(meta)
    columns = list(df.columns)
    ordered = []
    for c in ZOOM_DETAIL_CONTEXT_ORDER + ZOOM_DETAIL_VALUE_ORDER + ["zoom_click_metric_label", "zoom_click_value_fmt"]:
        if c in columns and c not in ordered:
            ordered.append(c)
    # Thêm các cột còn lại nhưng bỏ cột kỹ thuật/raw trùng thông tin nếu đã có cột formatted.
    for c in columns:
        if c in ordered or c in ZOOM_DETAIL_INTERNAL_SKIP or str(c).lower() in ZOOM_DETAIL_INTERNAL_SKIP:
            continue
        if c == "tong_doanh_thu" and any(x in columns for x in ["rev_fmt", "metric_fmt", "val_fmt"]):
            continue
        if c == "tong_so_cuoc" and "trip_fmt" in columns:
            continue
        if c == "gia_tri" and any(x in columns for x in ["metric_fmt", "val_fmt"]):
            continue
        ordered.append(c)
    if len(ordered) == 1 and len(columns) > 1:
        for c in columns:
            if c not in ordered and c not in ZOOM_DETAIL_INTERNAL_SKIP:
                ordered.append(c)
            if len(ordered) >= 4:
                break
    return ordered[:max_cols]


def _zoom_columns_data(df: pd.DataFrame, meta: dict | None = None, max_cols: int = 12):
    if df is None or df.empty:
        return [], []
    meta = meta or {}
    metric_label = _zoom_metric_label(meta)
    use_cols = _zoom_order_detail_columns(df, meta, max_cols=max_cols)
    if not use_cols:
        use_cols = list(df.columns[:max_cols])
    display_df = df[use_cols].copy()
    for c in use_cols:
        display_df[c] = display_df[c].map(lambda v, col=c: _zoom_format_raw_value(col, v))
    columns = [{"name": _zoom_vn_label(c, metric_label), "id": c} for c in use_cols]
    return columns, display_df.to_dict("records")


def _zoom_detail_card(df: pd.DataFrame, meta: dict | None, theme: str, title: str, subtitle_parts=None, dense: bool = True):
    meta = meta or {}
    subtitle_parts = [str(x) for x in (subtitle_parts or []) if str(x).strip()]
    columns, data = _zoom_columns_data(df, meta, max_cols=12)
    style_header, style_cell, style_table, wrapper_style = _zoom_table_styles(theme, dense=dense)
    body_children = [
        html.Div(title, style={"fontSize":"15px","fontWeight":"900"}),
    ]
    if subtitle_parts:
        body_children.append(html.Div(" • ".join(list(dict.fromkeys(subtitle_parts))), style={"opacity":0.85,"marginBottom":"8px","fontWeight":"700"}))
    if columns:
        body_children.append(html.Div(
            dash_table.DataTable(
                columns=columns,
                data=data,
                page_size=14,
                style_cell=style_cell,
                style_header=style_header,
                style_table=style_table,
            ),
            style=wrapper_style,
        ))
    else:
        body_children.append(html.Div("Không có dữ liệu chi tiết phù hợp.", style={"opacity":0.8, "fontWeight":"700"}))
    return dbc.Card(
        dbc.CardBody(body_children, style={"width": "100%", "maxWidth": "100%", "overflowX": "hidden"}),
        style={"border": f"1.5px solid {GREEN_BORDER}", "boxShadow": f"0 8px 18px {GREEN_SHADOW}", "width": "100%", "maxWidth": "100%", "overflow": "hidden"}
    )


COMMON_FILTER_CACHE = {}

def apply_common_filters(dff: pd.DataFrame, year_val=None, months=None, dims=None, real_cutoff: bool = True):
    months_key = _stable_list_key(months)
    dims_key = _stable_list_key(dims)
    scope_key = _region_scope_cache_key(current_user_region_scope())
    cache_key = (_df_cache_signature(dff), str(year_val), months_key, dims_key, bool(real_cutoff), scope_key)
    if DASH_GLOBAL_FILTER_CACHE:
        cached = COMMON_FILTER_CACHE.get(cache_key)
        if isinstance(cached, pd.DataFrame):
            return _return_df_cached(cached)

    out = apply_region_scope_to_df(dff)
    if real_cutoff:
        out = _apply_real_data_cutoff(out)
    if year_val is not None and "nam" in out.columns:
        out = out[out["nam"] == int(year_val)]
    if months_key and "thang_label" in out.columns:
        out = out[out["thang_label"].astype(str).isin(months_key)]
    if dims_key and "khu_vuc" in out.columns:
        requested_dims = filter_regions_for_current_user(list(dims_key))
        if requested_dims:
            out = out[out["khu_vuc"].astype(str).isin([str(x) for x in requested_dims])]
        else:
            out = out.iloc[0:0]

    out_cached = out.copy(deep=False)
    if DASH_GLOBAL_FILTER_CACHE:
        if len(COMMON_FILTER_CACHE) > DASH_GLOBAL_FILTER_CACHE_MAX:
            COMMON_FILTER_CACHE.clear()
        COMMON_FILTER_CACHE[cache_key] = out_cached
    return _return_df_cached(out_cached)

def _make_summary_for_export(dff: pd.DataFrame, menu: str) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame()
    time_col = "thang_nam_vn" if "thang_nam_vn" in dff.columns else None
    group_cols = []
    if time_col:
        group_cols.append(time_col)
    elif "thang_label" in dff.columns:
        group_cols.append("thang_label")
    if "khu_vuc" in dff.columns:
        group_cols.append("khu_vuc")
    agg = {}
    if menu in ["dt", "lh", "home"]:
        if "tong_doanh_thu" in dff.columns:
            agg["tong_doanh_thu"] = "sum"
        if "tong_so_cuoc" in dff.columns:
            agg["tong_so_cuoc"] = "sum"
    else:
        if "tong_so_cuoc" in dff.columns:
            agg["tong_so_cuoc"] = "sum"
        if "tong_doanh_thu" in dff.columns:
            agg["tong_doanh_thu"] = "sum"
    if not group_cols or not agg:
        return pd.DataFrame()
    g = dff.groupby(group_cols, as_index=False).agg(agg)
    if time_col and time_col in g.columns:
        g = g.sort_values(time_col)
        g["thang_label"] = pd.to_datetime(g[time_col], errors="coerce").dt.strftime("%m/%Y")
    return g

def _apply_export_filters(menu: str, page: int, filt: dict) -> pd.DataFrame:
    ensure_menu_data_loaded(menu)
    if menu not in DATAFRAME_BY_PREFIX:
        return pd.DataFrame()
    base = DATAFRAME_BY_PREFIX[menu].copy()
    key = menu

    filt = filt or {}
    months = (filt or {}).get("months", []) or []
    dims = (filt or {}).get("dims", []) or []
    type_filter = (filt or {}).get("type_filter", []) or []
    business_filter = (filt or {}).get("business_filter", []) or []
    seat_filter = (filt or {}).get("seat_filter", []) or []
    if _is_fleet_menu(menu):
        year_val = None
        months = []
    else:
        year_val = _resolve_year_filter_for_menu(menu, filt, DEFAULT_YEAR)

    if key == "lh" and _normalize_multi_value(business_filter):
        business_base = _lh_business_monthly_source_df()
        if isinstance(business_base, pd.DataFrame) and not business_base.empty:
            base = business_base
    dff = apply_common_filters(base, year_val=year_val, months=months, dims=dims if page == 2 else None, real_cutoff=not _is_fleet_menu(menu))
    if _is_fleet_menu(menu):
        dff = _latest_fleet_snapshot_df(dff)
    if key == "lh" and type_filter and LH_COL in dff.columns:
        dff = dff[dff[LH_COL].astype(str).isin(type_filter)]
    if key == "lh" and business_filter:
        dff = _apply_lh_business_filter_frame(dff, business_filter)
    if key == "hd" and type_filter and HD_COL in dff.columns:
        dff = dff[dff[HD_COL].astype(str).isin(type_filter)]
    if key in ["xdt", "xpq"] and type_filter and "loai_xe" in dff.columns:
        dff = dff[dff["loai_xe"].astype(str).isin(type_filter)]
    if key in ["xdt", "xpq"] and seat_filter:
        try:
            seat_vals = sorted({int(float(x)) for x in seat_filter if str(x) not in ["", "None"]})
        except Exception:
            seat_vals = []
        if seat_vals:
            if "so_cho_loc" in dff.columns:
                seat_series = pd.to_numeric(dff["so_cho_loc"], errors="coerce").fillna(0).round().astype(int)
            elif "so_cho_binh_quan_xe" in dff.columns:
                seat_series = pd.to_numeric(dff["so_cho_binh_quan_xe"], errors="coerce").fillna(0).round().astype(int)
            else:
                seat_series = pd.Series([0] * len(dff), index=dff.index)
            dff = dff[seat_series.isin(seat_vals)]
    return dff.copy()


FA_CDN = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"

server = Flask(__name__)
server.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key-before-production")
server.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
if _env_flag("SESSION_COOKIE_SECURE", False):
    server.config["SESSION_COOKIE_SECURE"] = True

@server.after_request
def add_fast_cache_headers(response):
    try:
        path = request.path or ""
        if path.startswith("/assets/") or path == "/company-logo":
            response.headers.setdefault("Cache-Control", "public, max-age=86400, immutable")
    except Exception:
        pass
    return response

@server.get("/healthz")
def healthz():
    return ("ok", 200)

@server.get("/company-logo")
def company_logo():
    try:
        if LOGO_PATH is not None and LOGO_PATH.exists():
            mime = "image/png" if LOGO_PATH.suffix.lower() == ".png" else "image/jpeg"
            return send_file(LOGO_PATH, mimetype=mime, max_age=86400, conditional=True)
    except Exception:
        pass
    return ("", 404)


def _run_warm_preload(preload: str, deep: bool = False) -> str:
    """Shared warm/preload logic used by token endpoint and authenticated browser ping."""
    mode = str(preload or "").strip().lower()
    if deep or mode in {"all", "full"}:
        if not DASH_WARM_ALLOW_DEEP_PRELOAD:
            # Guard production warm pings from accidentally loading every lazy dataset.
            # Set DASH_WARM_ALLOW_DEEP_PRELOAD=1 only for a deliberate one-off preload.
            return "light_guarded"
        ensure_all_lazy_data_loaded(log=True)
        return "all"
    if mode in {"interactive", "ui", "first-click", "first_click"}:
        ensure_daily_data_loaded(log=True)
        for _menu_key in ["emp", "mkt", "xdt"]:
            ensure_menu_data_loaded(_menu_key, log=True)
        return "interactive"
    if mode in {"daily", "ngay"}:
        ensure_daily_data_loaded(log=True)
        return "daily"
    if mode in {"hr", "nhansu", "nhan-su"}:
        ensure_menu_data_loaded("emp", log=True)
        return "hr"
    if mode in {"biz", "business", "kinhdoanh", "kinh-doanh"}:
        ensure_menu_data_loaded("mkt", log=True)
        return "biz"
    if mode in {"fleet", "phuongtien", "phuong-tien"}:
        ensure_menu_data_loaded("xdt", log=True)
        return "fleet"
    return "light"


@server.route("/_warm", methods=["GET", "HEAD"])
def warm_endpoint():
    """
    Lightweight warm endpoint for Vercel/UptimeRobot.
    Chỉ chạm nhẹ vào dữ liệu đã load sẵn, không dựng chart, không chạy callback,
    không thay đổi session/filter/UI/logic dashboard.
    """
    token = str(os.getenv("DASH_WARM_TOKEN", "")).strip()
    if token:
        incoming = str(request.args.get("token", "")).strip()
        if not hmac.compare_digest(incoming, token):
            return {"ok": False, "error": "forbidden"}, 403

    if request.method == "HEAD":
        return "", 200, {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
        }

    preload = str(request.args.get("preload", "") or request.args.get("mode", "")).strip().lower()
    deep = str(request.args.get("deep", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
    preload_done = _run_warm_preload(preload, deep=deep)

    started = time.perf_counter()
    touched = {}
    include_touch_sums = DASH_WARM_INCLUDE_TOUCH_SUMS or str(request.args.get("debug", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _touch_df(name):
        obj = globals().get(name)
        if not isinstance(obj, pd.DataFrame):
            return
        info = {
            "rows": int(len(obj)),
            "cols": int(len(obj.columns)),
        }
        if include_touch_sums:
            for col in [
                "tong_doanh_thu",
                "tong_so_cuoc",
                "so_tien_thu_duoc",
                "tong_tien_de_xuat",
                "so_tien_da_xu_ly",
                "so_tien_con_no",
                "so_luong_xe",
                "so_luong_nhan_su",
            ]:
                if col in obj.columns:
                    try:
                        info[col] = float(pd.to_numeric(obj[col], errors="coerce").fillna(0).sum())
                    except Exception:
                        pass
        touched[name] = info

    for name in [
        "df_dt",
        "df_lh",
        "df_hd",
        "df_daily_checker",
        "df_daily_lh_checker",
        "df_daily_hinhthuc_checker",
        "df_daily_luong_checker",
        "df_daily_socho_checker",
        "df_daily_taixe_checker",
        "df_daily_taixe_lh_checker",
        "df_daily_taixe_hinhthuc_checker",
        "df_daily_taixe_luong_checker",
        "df_daily_taixe_socho_checker",
        "df_daily_raw_checker",
        "df_emp",
        "df_drv",
        "df_mkt",
        "df_bb",
        "df_xdt",
        "df_xpq",
    ]:
        _touch_df(name)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": True,
        "mode": "light",
        "elapsed_ms": elapsed_ms,
        "preload_done": preload_done,
        "touched_count": len(touched),
        "touched": touched,
        "perf": {
            "serverless_fast_preset": bool(DASH_SERVERLESS_FAST_PRESET),
            "prefer_cache": bool(DASH_PREFER_PARQUET_CACHE),
            "cache_dir": str(DASH_CACHE_DIR),
            "zoom_store_max_rows": int(DASH_ZOOM_STORE_MAX_ROWS),
            "figure_store_max_rows": int(DASH_FIGURE_STORE_MAX_ROWS),
            "kpi_store_max_rows": int(DASH_KPI_STORE_MAX_ROWS),
        },
    }, 200, {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
    }


@server.get("/_warm_user")
def warm_user_endpoint():
    """Authenticated browser-side warm ping; no public token is exposed to JS."""
    started = time.perf_counter()
    preload = str(request.args.get("preload", DASH_CLIENT_PRELOAD_MODE) or DASH_CLIENT_PRELOAD_MODE).strip().lower()
    deep = str(request.args.get("deep", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
    preload_done = _run_warm_preload(preload, deep=deep)
    return {
        "ok": True,
        "preload_done": preload_done,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }, 200, {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
    }

@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = str(request.form.get("username", "")).strip()
        password = request.form.get("password", "")
        users = load_auth_user_store()
        user_record = users.get(username)
        if user_record and _verify_password(user_record, password):
            session["dash_auth_user"] = {
                "username": user_record["username"],
                "display_name": user_record.get("display_name") or user_record["username"],
                "role": user_record.get("role", "region"),
                "regions": user_record.get("regions", []),
            }
            # V2: sau khi đăng nhập, mọi tài khoản luôn vào Home trước.
            return redirect("/")
        error_msg = "Sai tài khoản hoặc mật khẩu."
    else:
        error_msg = None
        current = current_auth_user()
        if current:
            return redirect("/")

    next_path = request.args.get("next") or request.form.get("next") or "/"
    if not _is_safe_next_path(next_path):
        next_path = "/"
    return render_template_string(
        LOGIN_PAGE_TEMPLATE,
        app_title="Nam Thang Group Dashboard",
        logo_src=COMPANY_LOGO_SRC,
        error=error_msg,
        next_path=next_path,
        default_hint=_auth_store_source() == "default",
    )

@server.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@server.before_request
def protect_dash_routes():
    path = request.path or "/"
    if path in {"/login", "/logout", "/healthz", "/_warm"}:
        return None
    if path.startswith("/assets/") or path == "/favicon.ico":
        return None
    if request.endpoint == "static":
        return None
    if current_auth_user():
        return None
    next_path = request.full_path if request.query_string else request.path
    if next_path.endswith("?"):
        next_path = next_path[:-1]
    return redirect(url_for("login", next=next_path))

app = Dash(__name__, server=server, external_stylesheets=[dbc.themes.FLATLY, FA_CDN], suppress_callback_exceptions=True, serve_locally=False)

def fa_icon(name: str, size: int = 18, color: str = "currentColor", extra_class: str = ""):
    return html.I(
        className=f"fa-solid {name} {extra_class}",
        style={"fontSize": f"{size}px", "color": color, "lineHeight": "1", "display": "inline-block"}
    )

ICON_MENU   = fa_icon("fa-bars", 18)
ICON_THEME  = fa_icon("fa-circle-half-stroke", 18)
ICON_BOT    = fa_icon("fa-robot", 18)
ICON_DL     = fa_icon("fa-download", 18)
ICON_SEND   = fa_icon("fa-paper-plane", 18)
ICON_TRASH  = fa_icon("fa-trash", 18)
ICON_CHEV_L = fa_icon("fa-chevron-left", 22)
ICON_CHEV_R = fa_icon("fa-chevron-right", 22)
ICON_CHART  = fa_icon("fa-chart-line", 16)
ICON_HOME   = fa_icon("fa-house", 16)
ICON_MONEY  = fa_icon("fa-sack-dollar", 16, GREEN_PRIMARY)
ICON_ROUTE  = fa_icon("fa-route", 16, GREEN_PRIMARY)
ICON_AVG    = fa_icon("fa-chart-pie", 16, GREEN_PRIMARY)
ICON_REGION = fa_icon("fa-map-location-dot", 16, GREEN_PRIMARY)
ICON_EMP    = fa_icon("fa-users", 16, GREEN_PRIMARY)
ICON_DRV    = fa_icon("fa-id-badge", 16, GREEN_PRIMARY)
ICON_MKT    = fa_icon("fa-bullseye", 16, GREEN_PRIMARY)
ICON_BB     = fa_icon("fa-file-lines", 16, GREEN_PRIMARY)
ICON_XDT    = fa_icon("fa-bus-simple", 16, GREEN_PRIMARY)
ICON_XPQ    = fa_icon("fa-car-side", 16, GREEN_PRIMARY)

MENU_TREE_CSS = """
.menu-group-card{
  background:#ffffff;
  border:1px solid #dfe5ef;
  border-radius:20px;
  padding:14px 14px 10px 14px;
  box-shadow:0 14px 28px rgba(15,23,42,0.06);
}
.menu-group-head{
  display:flex;
  align-items:center;
  gap:10px;
  margin-bottom:10px;
}
.menu-group-icon{
  width:36px;
  height:36px;
  border-radius:12px;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#ffffff;
  font-size:14px;
  box-shadow:0 10px 18px rgba(15,23,42,0.12);
}
.menu-group-title{
  font-size:14px;
  font-weight:900;
  color:#0f172a;
  line-height:1.15;
}
.menu-group-subtitle{
  font-size:11px;
  color:#64748b;
  font-weight:700;
  margin-top:2px;
}
.menu-tree-btn{
  border-radius:16px !important;
  border:1px solid #e2e8f0 !important;
  background:#f8fafc !important;
  color:#0f172a !important;
  text-align:left !important;
  padding:10px 12px !important;
  font-weight:800 !important;
  box-shadow:none !important;
}
.menu-tree-btn:hover{
  background:#f0fdf4 !important;
  border-color:#22c55e !important;
  transform:translateY(-1px);
}
.menu-tree-btn .small-caption{
  display:block;
  font-size:11px;
  opacity:0.72;
  font-weight:700;
  margin-top:2px;
}
.home-nav-grid .quick-nav-btn{
  min-height:74px;
}
.home-nav-grid .quick-nav-btn .nav-title{
  font-weight:900;
  color:#0f172a;
  display:block;
}
.home-nav-grid .quick-nav-btn .nav-subtitle{
  display:block;
  font-size:11px;
  color:#64748b;
  font-weight:700;
}
"""

PREMIUM_FILTER_NAV_CSS = """
.executive-filter-panel{
  position:relative;
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%);
  border:1px solid #e3ebf3 !important;
  border-radius:26px !important;
  box-shadow:0 22px 48px rgba(15,23,42,0.08) !important;
  overflow:hidden;
}
.executive-filter-panel::before{
  content:"";
  position:absolute;
  left:0;
  right:0;
  top:0;
  height:4px;
  background:linear-gradient(90deg,#16a34a 0%, #14b8a6 32%, #f59e0b 68%, #6366f1 100%);
}
.filter-panel-title{
  font-size:15px;
  font-weight:900;
  color:#0f172a;
  letter-spacing:.2px;
}
.filter-panel-subtitle{
  font-size:12px;
  color:#64748b;
  font-weight:700;
  margin-top:4px;
  line-height:1.45;
}
.filter-panel-chip-row{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  justify-content:flex-end;
}
.filter-panel-chip{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:9px 12px;
  border-radius:999px;
  background:#ffffff;
  border:1px solid #e2e8f0;
  box-shadow:0 10px 20px rgba(15,23,42,0.05);
  font-size:12px;
  font-weight:800;
  color:#334155;
  white-space:nowrap;
}
.exec-filter-shell{
  position:relative;
  min-height:110px;
}
.exec-filter-shell::after{
  content:"";
  position:absolute;
  top:14px;
  right:14px;
  width:62px;
  height:62px;
  border-radius:18px;
  background:radial-gradient(circle at center, rgba(34,197,94,0.10), rgba(34,197,94,0.03) 58%, transparent 70%);
  pointer-events:none;
}
.exec-filter-header{
  display:flex;
  align-items:flex-start;
  gap:12px;
  margin-bottom:12px;
}
.exec-filter-badge{
  width:36px;
  height:36px;
  border-radius:14px;
  display:flex;
  align-items:center;
  justify-content:center;
  background:linear-gradient(135deg,#16a34a,#22c55e);
  box-shadow:0 12px 22px rgba(34,197,94,0.22);
  flex:0 0 auto;
}
.exec-filter-title{
  font-size:12px;
  font-weight:900;
  letter-spacing:.7px;
  color:#0f172a;
  text-transform:uppercase;
  line-height:1.1;
}
.exec-filter-helper{
  font-size:12px;
  color:#64748b;
  font-weight:700;
  margin-top:4px;
  line-height:1.3;
}
.exec-filter-dropdown-wrap{
  position:relative;
  z-index:2;
}
.executive-dropdown .Select-control,
.exec-filter-shell .Select-control{
  min-height:54px !important;
  border-radius:18px !important;
  border:1px solid #dce7ef !important;
  background:linear-gradient(180deg,#ffffff 0%, #f8fafc 100%) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.88), 0 8px 16px rgba(15,23,42,0.04) !important;
}
.executive-dropdown .Select-placeholder,
.exec-filter-shell .Select-placeholder{
  color:#94a3b8 !important;
  font-weight:700 !important;
}
.executive-dropdown .Select--single > .Select-control .Select-value,
.exec-filter-shell .Select--single > .Select-control .Select-value{
  line-height:52px !important;
}
.executive-dropdown .Select-value-label,
.exec-filter-shell .Select-value-label,
.executive-dropdown .Select-input > input,
.exec-filter-shell .Select-input > input{
  color:#0f172a !important;
  font-weight:800 !important;
}
.executive-dropdown .Select-arrow,
.exec-filter-shell .Select-arrow{
  border-top-color:#64748b !important;
}
.executive-dropdown .Select-clear,
.exec-filter-shell .Select-clear{
  color:#94a3b8 !important;
}
.executive-dropdown .Select.is-focused > .Select-control,
.executive-dropdown .is-focused:not(.is-open) > .Select-control,
.exec-filter-shell .Select.is-focused > .Select-control,
.exec-filter-shell .is-focused:not(.is-open) > .Select-control{
  border-color:#22c55e !important;
  background:#ffffff !important;
  box-shadow:0 0 0 4px rgba(34,197,94,0.12), 0 10px 20px rgba(15,23,42,0.06) !important;
}
.executive-dropdown .Select-menu-outer,
.exec-filter-shell .Select-menu-outer{
  border:1px solid #dce7ef !important;
  border-radius:16px !important;
  box-shadow:0 18px 32px rgba(15,23,42,0.10) !important;
}
.executive-dropdown .Select--multi .Select-value,
.exec-filter-shell .Select--multi .Select-value{
  background:#ecfdf3 !important;
  border:1px solid #bbf7d0 !important;
  color:#166534 !important;
  border-radius:999px !important;
  font-weight:800 !important;
}
.home-nav-card-btn{
  padding:0 !important;
  border:none !important;
  background:transparent !important;
  box-shadow:none !important;
}
.home-nav-card-inner{
  position:relative;
  min-height:146px;
  padding:18px 18px 16px 18px;
  border-radius:24px;
  border:1px solid #e3ebf3;
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%);
  box-shadow:0 20px 42px rgba(15,23,42,0.08);
  overflow:hidden;
  transition:transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
  text-align:left;
}
.home-nav-card-inner::before{
  content:"";
  position:absolute;
  left:0;
  right:0;
  top:0;
  height:4px;
  background:var(--nav-accent, #22c55e);
}
.home-nav-card-inner::after{
  content:"";
  position:absolute;
  right:-20px;
  top:-20px;
  width:110px;
  height:110px;
  border-radius:28px;
  background:radial-gradient(circle at center, var(--nav-accent-soft-strong, rgba(34,197,94,0.18)) 0%, transparent 68%);
}
.home-nav-card-btn:hover .home-nav-card-inner{
  transform:translateY(-3px);
  border-color:var(--nav-accent, #22c55e);
  box-shadow:0 24px 52px rgba(15,23,42,0.12);
}
.home-nav-card-btn:focus .home-nav-card-inner,
.home-nav-card-btn:active .home-nav-card-inner{
  transform:translateY(-2px);
  box-shadow:0 0 0 4px var(--nav-accent-soft, rgba(34,197,94,0.14)), 0 24px 52px rgba(15,23,42,0.12);
}
.home-nav-badges{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-bottom:14px;
  padding-right:62px;
}
.home-nav-code,
.home-nav-group{
  display:inline-flex;
  align-items:center;
  padding:7px 11px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
  line-height:1;
}
.home-nav-code{
  background:var(--nav-accent-soft, rgba(34,197,94,0.14));
  color:var(--nav-accent-dark, #166534);
  border:1px solid transparent;
}
.home-nav-group{
  background:#ffffff;
  border:1px solid #e2e8f0;
  color:#475569;
}
.home-nav-icon{
  position:absolute;
  top:18px;
  right:18px;
  width:44px;
  height:44px;
  border-radius:16px;
  display:flex;
  align-items:center;
  justify-content:center;
  background:var(--nav-accent-soft, rgba(34,197,94,0.14));
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.82);
}
.home-nav-icon i{
  color:var(--nav-accent, #22c55e) !important;
  font-size:18px !important;
}
.home-nav-title{
  font-size:19px;
  font-weight:900;
  color:#0f172a;
  line-height:1.14;
  padding-right:62px;
}
.home-nav-subtitle{
  display:block;
  margin-top:8px;
  font-size:12px;
  color:#64748b;
  font-weight:700;
  line-height:1.4;
  min-height:34px;
}
.home-nav-footer{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:14px;
}
.home-nav-meta-pill{
  display:inline-flex;
  align-items:center;
  padding:7px 10px;
  border-radius:999px;
  background:#f8fafc;
  border:1px solid #e2e8f0;
  color:#475569;
  font-size:11px;
  font-weight:800;
}
@media (max-width: 991px){
  .filter-panel-chip-row{ justify-content:flex-start; }
}
@media (max-width: 768px){
  .home-nav-card-inner{ min-height:132px; }
  .home-nav-title{ font-size:17px; }
  .exec-filter-shell{ min-height:auto; }
}
"""

NEXT_LEVEL_HOME_UI_CSS = """
.executive-home-nav-panel,
.executive-control-dock{
  overflow:hidden;
}
.executive-home-nav-panel .card-body,
.executive-control-dock .card-body{
  padding:22px 22px 22px 22px;
}
.executive-home-nav-panel{
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%) !important;
}
.executive-home-nav-panel::after,
.executive-control-dock::after{
  content:"";
  position:absolute;
  right:18px;
  top:14px;
  width:150px;
  height:150px;
  border-radius:50%;
  background:radial-gradient(circle at center, rgba(15,118,110,0.06) 0%, rgba(34,197,94,0.03) 42%, transparent 72%);
  pointer-events:none;
}
.executive-home-nav-panel .filter-panel-title,
.executive-control-dock .filter-panel-title{
  font-size:16px;
  letter-spacing:.15px;
}
.executive-home-nav-panel .filter-panel-subtitle,
.executive-control-dock .filter-panel-subtitle{
  font-size:12px;
  line-height:1.5;
}
.home-nav-super-grid{
  position:relative;
  z-index:2;
}
.home-nav-group-shell{
  position:relative;
  height:100%;
  padding:18px;
  border-radius:28px;
  border:1px solid #e4ebf3;
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%);
  box-shadow:0 20px 46px rgba(15,23,42,0.08);
  overflow:hidden;
}
.home-nav-group-shell::before{
  content:"";
  position:absolute;
  left:0;
  top:0;
  bottom:0;
  width:4px;
  border-radius:28px 0 0 28px;
  background:var(--group-accent, #22c55e);
}
.home-nav-group-shell::after{
  content:"";
  position:absolute;
  top:-36px;
  right:-24px;
  width:170px;
  height:170px;
  border-radius:50%;
  background:radial-gradient(circle at center, var(--group-accent-soft-strong, rgba(34,197,94,0.22)) 0%, transparent 70%);
  pointer-events:none;
}
.home-nav-group-head{
  position:relative;
  display:flex;
  align-items:flex-start;
  gap:12px;
  margin-bottom:16px;
  padding-right:104px;
}
.home-nav-group-icon-shell{
  width:44px;
  height:44px;
  border-radius:16px;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#ffffff;
  box-shadow:0 14px 28px rgba(15,23,42,0.14);
  flex:0 0 auto;
}
.home-nav-group-title{
  font-size:16px;
  font-weight:900;
  color:#0f172a;
  line-height:1.15;
  letter-spacing:.1px;
}
.home-nav-group-subtitle{
  font-size:12px;
  color:#64748b;
  font-weight:700;
  line-height:1.4;
  margin-top:4px;
}
.home-nav-group-badge-stack{
  position:absolute;
  top:0;
  right:0;
  display:flex;
  flex-direction:column;
  align-items:flex-end;
  gap:7px;
}
.home-nav-group-badge,
.home-nav-group-meta{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:8px 12px;
  border-radius:999px;
  font-size:11px;
  font-weight:900;
  line-height:1;
  white-space:nowrap;
}
.home-nav-group-badge{
  background:var(--group-accent-soft, rgba(34,197,94,0.14));
  color:var(--group-accent-dark, #166534);
  border:1px solid rgba(255,255,255,0.6);
}
.home-nav-group-meta{
  background:#ffffff;
  color:#475569;
  border:1px solid #e2e8f0;
  box-shadow:0 8px 18px rgba(15,23,42,0.05);
}
.home-nav-card-inner{
  min-height:172px;
  padding:18px 18px 16px 18px;
  border-radius:24px;
  border:1px solid #e7eef5;
  background:linear-gradient(180deg,#ffffff 0%, #fbfdff 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.92), 0 14px 30px rgba(15,23,42,0.05);
  overflow:hidden;
}
.home-nav-card-inner::before{
  height:3px;
}
.home-nav-card-inner::after{
  top:-28px;
  right:-20px;
  width:126px;
  height:126px;
  border-radius:42px;
  background:radial-gradient(circle at center, var(--nav-accent-soft-strong, rgba(34,197,94,0.22)) 0%, transparent 70%);
}
.home-nav-card-btn:hover .home-nav-card-inner{
  transform:translateY(-4px);
  box-shadow:0 22px 42px rgba(15,23,42,0.10);
}
.home-nav-badges{
  margin-bottom:12px;
  padding-right:56px;
}
.home-nav-code,
.home-nav-group{
  padding:6px 10px;
  font-size:10px;
  letter-spacing:.35px;
}
.home-nav-group{
  background:rgba(255,255,255,0.94);
  backdrop-filter:blur(8px);
}
.home-nav-icon{
  top:18px;
  right:18px;
  width:46px;
  height:46px;
  border-radius:16px;
  background:linear-gradient(135deg, rgba(255,255,255,0.98) 0%, var(--nav-accent-soft, rgba(34,197,94,0.14)) 100%);
  border:1px solid rgba(255,255,255,0.92);
  box-shadow:0 12px 22px rgba(15,23,42,0.08);
}
.home-nav-icon i{
  font-size:18px !important;
}
.home-nav-title{
  font-size:18px;
  padding-right:58px;
}
.home-nav-subtitle{
  min-height:38px;
  margin-top:8px;
  font-size:12px;
  line-height:1.45;
}
.home-nav-footer{
  gap:6px;
  margin-top:13px;
}
.home-nav-meta-pill{
  background:#f8fafc;
  border:1px solid #e2e8f0;
  color:#475569;
  font-size:10px;
}
.home-nav-cta{
  margin-top:14px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:10px 12px;
  border-radius:14px;
  border:1px solid rgba(226,232,240,0.92);
  background:linear-gradient(90deg, var(--nav-accent-soft, rgba(34,197,94,0.14)) 0%, rgba(255,255,255,0.98) 86%);
  font-size:12px;
  font-weight:900;
  color:var(--nav-accent-dark, #166534);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.75);
  transition:transform 180ms ease, box-shadow 180ms ease;
}
.home-nav-card-btn:hover .home-nav-cta{
  transform:translateX(2px);
  box-shadow:0 10px 20px rgba(15,23,42,0.06);
}
.home-nav-cta i{
  color:var(--nav-accent, #22c55e) !important;
}
.executive-control-dock{
  background:linear-gradient(180deg,#ffffff 0%, #f8fbff 100%) !important;
}
.exec-filter-shell{
  position:relative;
  min-height:128px !important;
  padding:16px 16px 14px !important;
  border-radius:26px !important;
  border:1px solid #dfe8f0 !important;
  background:linear-gradient(180deg,#ffffff 0%, #fbfdff 100%) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.95), 0 22px 42px rgba(15,23,42,0.07) !important;
  overflow:hidden;
}
.exec-filter-shell::before{
  content:"";
  position:absolute;
  left:0;
  top:0;
  bottom:0;
  width:4px;
  background:linear-gradient(180deg,#16a34a 0%, #22c55e 100%);
  border-radius:26px 0 0 26px;
}
.exec-filter-shell::after{
  top:16px;
  right:16px;
  width:76px;
  height:76px;
  border-radius:24px;
  background:radial-gradient(circle at center, rgba(34,197,94,0.10), rgba(20,184,166,0.04) 58%, transparent 72%);
}
.exec-filter-header{
  align-items:flex-start;
  justify-content:space-between;
  gap:12px;
  margin-bottom:14px;
}
.exec-filter-header-main{
  display:flex;
  align-items:flex-start;
  gap:12px;
  min-width:0;
  flex:1 1 auto;
}
.exec-filter-live-tag{
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:7px 10px;
  border-radius:999px;
  background:#f0fdf4;
  border:1px solid #bbf7d0;
  color:#166534;
  font-size:10px;
  font-weight:900;
  line-height:1;
  white-space:nowrap;
  box-shadow:0 8px 18px rgba(34,197,94,0.10);
  flex:0 0 auto;
}
.exec-filter-live-dot{
  width:7px;
  height:7px;
  border-radius:50%;
  background:#22c55e;
  box-shadow:0 0 0 4px rgba(34,197,94,0.12);
}
.exec-filter-title{
  font-size:11px;
  letter-spacing:.9px;
}
.exec-filter-helper{
  font-size:12px;
  line-height:1.35;
  margin-top:5px;
}
.exec-filter-dropdown-wrap{
  position:relative;
  z-index:2;
}
.executive-dropdown .Select-control,
.exec-filter-shell .Select-control{
  min-height:58px !important;
  border-radius:18px !important;
  border:1px solid #dce7ef !important;
  background:linear-gradient(180deg,#ffffff 0%, #f8fafc 100%) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.90), 0 10px 18px rgba(15,23,42,0.04) !important;
}
.executive-dropdown .Select--single > .Select-control .Select-value,
.exec-filter-shell .Select--single > .Select-control .Select-value{
  line-height:56px !important;
}
.executive-dropdown .Select-menu-outer,
.exec-filter-shell .Select-menu-outer{
  margin-top:8px !important;
  border:1px solid #dce7ef !important;
  border-radius:18px !important;
  box-shadow:0 18px 32px rgba(15,23,42,0.12) !important;
  overflow:hidden !important;
}
.executive-dropdown .Select--multi .Select-value,
.exec-filter-shell .Select--multi .Select-value{
  padding:2px 8px !important;
  background:#ecfdf3 !important;
  border:1px solid #bbf7d0 !important;
  color:#166534 !important;
  border-radius:999px !important;
  font-weight:800 !important;
}
.executive-dropdown .Select-arrow,
.exec-filter-shell .Select-arrow{
  border-top-color:#64748b !important;
  border-width:6px 6px 2.5px !important;
}
.executive-dropdown .Select-placeholder,
.exec-filter-shell .Select-placeholder{
  color:#94a3b8 !important;
  font-weight:700 !important;
}
.executive-dropdown .Select.is-focused > .Select-control,
.executive-dropdown .is-focused:not(.is-open) > .Select-control,
.exec-filter-shell .Select.is-focused > .Select-control,
.exec-filter-shell .is-focused:not(.is-open) > .Select-control{
  border-color:#22c55e !important;
  background:#ffffff !important;
  box-shadow:0 0 0 4px rgba(34,197,94,0.12), 0 12px 22px rgba(15,23,42,0.06) !important;
}
@media (max-width: 1199px){
  .home-nav-group-head{ padding-right:0; }
  .home-nav-group-badge-stack{ position:static; align-items:flex-start; flex-direction:row; flex-wrap:wrap; margin-top:10px; }
}
@media (max-width: 991px){
  .executive-home-nav-panel .card-body,
  .executive-control-dock .card-body{ padding:18px 18px 18px 18px; }
}
@media (max-width: 768px){
  .home-nav-group-shell{ padding:16px; }
  .home-nav-card-inner{ min-height:160px; }
  .home-nav-title{ font-size:17px; }
  .exec-filter-live-tag{ padding:6px 9px; }
}
"""

MENU_GROUPS = [
    {
        "key": "rev",
        "code": "1",
        "label": "Doanh thu tập đoàn",
        "subtitle": "Khối doanh thu lõi của tập đoàn",
        "icon": "fa-sack-dollar",
        "color": "linear-gradient(135deg,#16a34a,#22c55e)",
        "menus": ["dt", "lh", "hd"],
    },
    {
        "key": "hr",
        "code": "2",
        "label": "Nhân sự",
        "subtitle": "Quản trị lực lượng vận hành",
        "icon": "fa-users",
        "color": "linear-gradient(135deg,#0f766e,#14b8a6)",
        "menus": ["emp", "drv"],
    },
    {
        "key": "biz",
        "code": "3",
        "label": "Kinh doanh",
        "subtitle": "Theo dõi hoạt động khai thác thị trường",
        "icon": "fa-bullseye",
        "color": "linear-gradient(135deg,#d97706,#f59e0b)",
        "menus": ["mkt", "bb"],
    },
    {
        "key": "fleet",
        "code": "4",
        "label": "Phương tiện",
        "subtitle": "Theo dõi tài sản và năng lực xe",
        "icon": "fa-bus-simple",
        "color": "linear-gradient(135deg,#4338ca,#6366f1)",
        "menus": ["xdt", "xpq"],
    },
]

GROUP_VISUALS = {
    "rev": {"accent": "#16a34a", "soft": "rgba(34,197,94,0.14)", "soft2": "rgba(34,197,94,0.24)", "dark": "#166534"},
    "hr": {"accent": "#0f766e", "soft": "rgba(20,184,166,0.14)", "soft2": "rgba(20,184,166,0.24)", "dark": "#115e59"},
    "biz": {"accent": "#d97706", "soft": "rgba(245,158,11,0.14)", "soft2": "rgba(245,158,11,0.24)", "dark": "#b45309"},
    "fleet": {"accent": "#4f46e5", "soft": "rgba(99,102,241,0.14)", "soft2": "rgba(99,102,241,0.24)", "dark": "#3730a3"},
}

def get_group_config(group_key: str) -> dict:
    for g in MENU_GROUPS:
        if g.get("key") == group_key:
            return g
    return MENU_GROUPS[0]

MENU_CONFIG = {
    "dt": {
        "code": "1.1",
        "group": "rev",
        "menu_label": "Doanh thu",
        "menu_caption": "Revenue dashboard",
        "page1_title": "DOANH THU – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH DOANH THU THEO KHU VỰC",
        "df": df_dt,
        "value_col": "tong_doanh_thu",
        "metric_label": "Doanh thu",
        "secondary_col": "tong_so_cuoc",
        "secondary_label": "Số cuốc",
        "avg_label": "Doanh thu / cuốc",
        "avg_mode": "per_secondary",
        "avg_divisor_label": "cuốc",
        "icon": ICON_MONEY,
        "type_filter_kind": None,
        "dataset_keywords": ["doanh thu", "revenue"],
    },
    "lh": {
        "code": "1.2",
        "group": "rev",
        "menu_label": "Loại hình",
        "menu_caption": "Model mix dashboard",
        "page1_title": "DOANH THU LOẠI HÌNH – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH LOẠI HÌNH THEO KHU VỰC",
        "df": df_lh,
        "value_col": "tong_doanh_thu",
        "metric_label": "Doanh thu",
        "secondary_col": "tong_so_cuoc",
        "secondary_label": "Số cuốc",
        "avg_label": "Doanh thu / cuốc",
        "avg_mode": "per_secondary",
        "avg_divisor_label": "cuốc",
        "icon": fa_icon("fa-bus", 16, GREEN_PRIMARY),
        "type_filter_kind": "lh",
        "dataset_keywords": ["loai hinh", "loại hình"],
    },
    "hd": {
        "code": "1.3",
        "group": "rev",
        "menu_label": "Hợp đồng",
        "menu_caption": "Contract dashboard",
        "page1_title": "HỢP ĐỒNG – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH HỢP ĐỒNG THEO KHU VỰC",
        "df": df_hd,
        "value_col": "tong_so_cuoc",
        "metric_label": "Số cuốc",
        "secondary_col": "tong_doanh_thu",
        "secondary_label": "Doanh thu HĐ",
        "avg_label": "Cuốc / tháng",
        "avg_mode": "per_month",
        "avg_divisor_label": "tháng",
        "icon": fa_icon("fa-file-signature", 16, GREEN_PRIMARY),
        "type_filter_kind": "hd",
        "dataset_keywords": ["hop dong", "hợp đồng", "so cuoc", "số cuốc"],
    },
    "emp": {
        "code": "2.1",
        "group": "hr",
        "menu_label": "Quản lý nhân viên",
        "menu_caption": "Employee management",
        "page1_title": "QUẢN LÝ NHÂN VIÊN – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH NHÂN VIÊN THEO KHU VỰC",
        "df": df_emp,
        "value_col": "so_luong_nhan_su",
        "metric_label": "Số lượng nhân sự",
        "secondary_col": "so_vao_lam",
        "secondary_label": "Nhân sự vào làm",
        "avg_label": "Nhân sự nghỉ việc",
        "avg_mode": "per_month",
        "avg_divisor_label": "tháng",
        "icon": ICON_EMP,
        "type_filter_kind": None,
        "dataset_keywords": ["nhan vien", "nhân viên", "quan ly nhan vien", "so luong nhan vien", "số lượng nhân viên", "bo phan", "vong doi"],
    },
    "drv": {
        "code": "2.2",
        "group": "hr",
        "menu_label": "Quản lý tài xế",
        "menu_caption": "Driver management",
        "page1_title": "QUẢN LÝ TÀI XẾ – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH TÀI XẾ THEO KHU VỰC",
        "df": df_drv,
        "value_col": "so_luong_nhan_su",
        "metric_label": "Số lượng tài xế",
        "secondary_col": "so_vao_lam",
        "secondary_label": "Tài xế vào làm",
        "avg_label": "Tài xế nghỉ việc",
        "avg_mode": "per_month",
        "avg_divisor_label": "tháng",
        "icon": ICON_DRV,
        "type_filter_kind": None,
        "dataset_keywords": ["tai xe", "tài xế", "quan ly tai xe", "so luong tai xe", "số lượng tài xế", "giu chan", "vong doi"],
    },
    "mkt": {
        "code": "3.1",
        "group": "biz",
        "menu_label": "Điểm tiếp thị",
        "menu_caption": "Marketing points",
        "page1_title": "ĐIỂM TIẾP THỊ – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH ĐIỂM TIẾP THỊ THEO KHU VỰC",
        "df": df_mkt,
        "value_col": "tong_doanh_thu",
        "metric_label": "Số tiền phải chi",
        "secondary_col": "tong_so_cuoc",
        "secondary_label": "Số điểm tiếp thị",
        "avg_label": "Chi phí / điểm tiếp thị",
        "avg_mode": "per_secondary",
        "avg_divisor_label": "điểm",
        "icon": ICON_MKT,
        "type_filter_kind": None,
        "dataset_keywords": ["diem tiep thi", "điểm tiếp thị", "tiep thi", "so tien phai chi", "số tiền phải chi", "so diem tiep thi", "số điểm tiếp thị"],
    },
    "bb": {
        "code": "3.2",
        "group": "biz",
        "menu_label": "Biên bản",
        "menu_caption": "Minutes & documents",
        "page1_title": "BIÊN BẢN – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH BIÊN BẢN THEO KHU VỰC",
        "df": df_bb,
        "value_col": "so_tien_thu_duoc",
        "metric_label": "Số tiền đã xử lý",
        "secondary_col": "so_tien_da_xu_ly",
        "secondary_label": "Số tiền biên bản ghi nhận",
        "avg_label": "Số tiền chênh lệch",
        "avg_mode": "per_secondary",
        "avg_divisor_label": "biên bản",
        "icon": ICON_BB,
        "type_filter_kind": None,
        "dataset_keywords": ["bien ban", "biên bản", "thu duoc", "đã xử lý", "con no", "chênh lệch", "da xu ly", "đã xử lý", "thu hoi"],
    },
    "xdt": {
        "code": "4.1",
        "group": "fleet",
        "menu_label": "Xe trực thuộc",
        "menu_caption": "Owned fleet",
        "page1_title": "XE TRỰC THUỘC – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH XE TRỰC THUỘC THEO KHU VỰC",
        "df": df_xdt,
        "value_col": "so_luong_xe",
        "metric_label": _fleet_metric_label("xdt"),
        "secondary_col": "tong_doanh_thu" if FLEET_ACTIVITY_BRIDGE.get("xdt") else "so_bien_kiem_soat",
        "secondary_label": "Doanh thu phương tiện" if FLEET_ACTIVITY_BRIDGE.get("xdt") else "Khu vực có xe",
        "avg_label": "Nhóm phương tiện hoạt động" if FLEET_ACTIVITY_BRIDGE.get("xdt") else "Loại xe hoạt động",
        "avg_mode": "per_secondary",
        "avg_divisor_label": _fleet_unit_label("xdt"),
        "avg_numerator_col": "tong_doanh_thu" if FLEET_ACTIVITY_BRIDGE.get("xdt") else "so_luong_xe",
        "avg_denominator_col": "so_luong_xe",
        "fleet_unit": _fleet_unit_label("xdt"),
        "icon": ICON_XDT,
        "type_filter_kind": "fleet",
        "dataset_keywords": ["xe truc thuoc", "xe trực thuộc", "xe dien", "xe điện", "loai xe"],
    },
    "xpq": {
        "code": "4.2",
        "group": "fleet",
        "menu_label": "Xe phân quyền",
        "menu_caption": "Delegated fleet",
        "page1_title": "XE PHÂN QUYỀN – TỔNG TẬP ĐOÀN",
        "page2_title": "PHÂN TÍCH XE PHÂN QUYỀN THEO KHU VỰC",
        "df": df_xpq,
        "value_col": "so_luong_xe",
        "metric_label": _fleet_metric_label("xpq"),
        "secondary_col": "tong_doanh_thu" if FLEET_ACTIVITY_BRIDGE.get("xpq") else "so_bien_kiem_soat",
        "secondary_label": "Doanh thu phương tiện" if FLEET_ACTIVITY_BRIDGE.get("xpq") else "Khu vực có xe",
        "avg_label": "Nhóm phương tiện hoạt động" if FLEET_ACTIVITY_BRIDGE.get("xpq") else "Loại xe hoạt động",
        "avg_mode": "per_secondary",
        "avg_divisor_label": _fleet_unit_label("xpq"),
        "avg_numerator_col": "tong_doanh_thu" if FLEET_ACTIVITY_BRIDGE.get("xpq") else "so_luong_xe",
        "avg_denominator_col": "so_luong_xe",
        "fleet_unit": _fleet_unit_label("xpq"),
        "icon": ICON_XPQ,
        "type_filter_kind": "fleet",
        "dataset_keywords": ["xe phan quyen", "xe phân quyền", "xe xang", "xe xăng", "loai xe"],
    },
}

HOME_NAV_ORDER = ["dt", "lh", "hd", "emp", "drv", "mkt", "bb", "xdt", "xpq"]
DATAFRAME_BY_PREFIX = {k: MENU_CONFIG[k]["df"] for k in DASH_PREFIXES}

def get_menu_config(prefix: str) -> dict:
    return MENU_CONFIG.get(prefix, MENU_CONFIG["dt"])

def make_menu_nav_button(prefix: str, source: str = "sidebar"):
    cfg = get_menu_config(prefix)
    if source == "home":
        visual = GROUP_VISUALS.get(cfg.get("group"), GROUP_VISUALS["rev"])
        quick_desc_map = {
            "dt": "Theo dõi doanh thu toàn tập đoàn",
            "lh": "Theo dõi cơ cấu loại hình khai thác",
            "hd": "Theo dõi nhóm hợp đồng vận hành",
            "emp": "Quản trị lực lượng nhân viên",
            "drv": "Quản trị đội ngũ tài xế",
            "mkt": "Theo dõi chi phí phải chi và độ phủ điểm tiếp thị theo khu vực",
            "bb": "Theo dõi biên bản và chứng từ hiện trường",
            "xdt": "Theo dõi xe trực thuộc và năng lực vận hành",
            "xpq": "Theo dõi xe phân quyền và hiệu suất khai thác",
        }
        desc = quick_desc_map.get(prefix, cfg.get("menu_caption", ""))
        return dbc.Button(
            html.Div([
                html.Div([
                    html.Span(cfg["code"], className="home-nav-code"),
                    html.Span("2 tầng phân tích", className="home-nav-group"),
                ], className="home-nav-badges"),
                html.Div(cfg["icon"], className="home-nav-icon"),
                html.Div(cfg["menu_label"], className="home-nav-title"),
                html.Div(desc, className="home-nav-subtitle"),
                html.Div([
                    html.Span("P1 • Tập đoàn", className="home-nav-meta-pill"),
                    html.Span("P2 • Khu vực", className="home-nav-meta-pill"),
                ], className="home-nav-footer"),
                html.Div([
                    html.Span("Mở dashboard"),
                    fa_icon("fa-arrow-right", 10, "currentColor")
                ], className="home-nav-cta"),
            ], className="home-nav-card-inner"),
            id={"type": "menu-nav", "menu": prefix, "source": source},
            n_clicks=0,
            className="home-nav-card-btn w-100",
            color="light",
            style={
                "--nav-accent": visual["accent"],
                "--nav-accent-soft": visual["soft"],
                "--nav-accent-soft-strong": visual["soft2"],
                "--nav-accent-dark": visual["dark"],
            },
        )

    body = [
        html.Div(cfg["icon"], className="me-2"),
        html.Div([
            html.Span(f'{cfg["code"]} {cfg["menu_label"]}'),
            html.Span(cfg.get("menu_caption", ""), className="small-caption")
        ], className="flex-grow-1 text-start"),
    ]
    return dbc.Button(
        body,
        id={"type": "menu-nav", "menu": prefix, "source": source},
        n_clicks=0,
        className="menu-tree-btn w-100 mb-2",
        color="light"
    )


def build_sidebar_menu_section(group_cfg: dict):
    return html.Div([
        html.Div([
            html.Div(fa_icon(group_cfg["icon"], 14, "#ffffff"), className="menu-group-icon", style={"background": group_cfg["color"]}),
            html.Div([
                html.Div(f'{group_cfg["code"]}. {group_cfg["label"]}'.upper(), className="menu-group-title"),
                html.Div(group_cfg["subtitle"], className="menu-group-subtitle"),
            ], className="flex-grow-1"),
        ], className="menu-group-head"),
        html.Div([make_menu_nav_button(prefix, source="sidebar") for prefix in group_cfg["menus"]])
    ], className="menu-group-card mb-3")


def build_home_nav_group(group_cfg: dict):
    visual = GROUP_VISUALS.get(group_cfg.get("key"), GROUP_VISUALS["rev"])
    menu_count = len(group_cfg.get("menus", []))
    width_lg = 4 if menu_count >= 3 else 6
    width_md = 6
    buttons = [
        dbc.Col(
            make_menu_nav_button(prefix, source="home"),
            lg=width_lg,
            md=width_md,
            sm=12,
        )
        for prefix in group_cfg.get("menus", [])
    ]
    return html.Div([
        html.Div([
            html.Div(fa_icon(group_cfg["icon"], 16, "#ffffff"), className="home-nav-group-icon-shell", style={"background": group_cfg["color"]}),
            html.Div([
                html.Div(f'{group_cfg["code"]}. {group_cfg["label"]}', className="home-nav-group-title"),
                html.Div(group_cfg["subtitle"], className="home-nav-group-subtitle"),
            ], className="flex-grow-1"),
            html.Div([
                html.Span(f"{menu_count} dashboard", className="home-nav-group-badge"),
                html.Span("Page 1 + Page 2", className="home-nav-group-meta"),
            ], className="home-nav-group-badge-stack"),
        ], className="home-nav-group-head"),
        dbc.Row(buttons, className="g-3")
    ], className="home-nav-group-shell", style={
        "--group-accent": visual["accent"],
        "--group-accent-soft": visual["soft"],
        "--group-accent-soft-strong": visual["soft2"],
        "--group-accent-dark": visual["dark"],
    })


def build_home_quick_nav():
    return dbc.Row([
        dbc.Col(build_home_nav_group(group_cfg), xl=6, lg=12, md=12)
        for group_cfg in MENU_GROUPS
    ], className="g-3 home-nav-super-grid")


def filter_panel_chip(text: str, icon=None):
    return html.Div([
        icon if icon is not None else None,
        html.Span(text),
    ], className="filter-panel-chip")


def executive_section_panel(title: str, subtitle: str, body, right_children=None, class_name: str = "mb-3"):
    right_children = right_children or []
    if not isinstance(right_children, list):
        right_children = [right_children]
    header_cols = [
        dbc.Col([
            html.Div(title, className="filter-panel-title"),
            html.Div(subtitle, className="filter-panel-subtitle"),
        ], lg=7, md=12)
    ]
    if right_children:
        header_cols.append(
            dbc.Col(html.Div(right_children, className="filter-panel-chip-row"), lg=5, md=12)
        )
    return dbc.Card(
        dbc.CardBody([
            dbc.Row(header_cols, className="align-items-center g-3 mb-3"),
            body,
        ]),
        className=f"executive-filter-panel {class_name}"
    )


def exec_dropdown(**kwargs):
    existing_class = str(kwargs.pop("className", "") or "").strip()
    kwargs["className"] = f"{existing_class} executive-dropdown".strip()
    kwargs.setdefault("style", dropdown_style("light"))
    return dcc.Dropdown(**kwargs)


def make_filter_col(label: str, dropdown_component, wrap_id: str, md: int, icon_name: str, helper_text: str):
    return dbc.Col(
        html.Div([
            html.Div([
                html.Div([
                    html.Div(fa_icon(icon_name, 13, "#ffffff"), className="exec-filter-badge"),
                    html.Div([
                        html.Div(label, className="exec-filter-title"),
                        html.Div(helper_text, className="exec-filter-helper"),
                    ], className="flex-grow-1"),
                ], className="exec-filter-header-main"),
                html.Div([
                    html.Span(className="exec-filter-live-dot"),
                    html.Span("Smart filter"),
                ], className="exec-filter-live-tag"),
            ], className="exec-filter-header"),
            html.Div(dropdown_component, className="exec-filter-dropdown-wrap"),
        ], id={"type":"filter-wrap","id":wrap_id}, className="exec-filter-shell", style=dropdown_container_style("light")),
        md=md
    )


def _build_type_filter(prefix: str, page_key: str):
    cfg = get_menu_config(prefix)
    kind = cfg.get("type_filter_kind")
    if prefix in HR_MENU_PREFIXES:
        dept_options = get_scoped_hr_dept_options(prefix)
        if page_key == "p1":
            return make_filter_col(
                "Bộ phận",
                exec_dropdown(
                    id=f"{prefix}-dept",
                    options=dept_options,
                    multi=True,
                    placeholder="Chọn bộ phận nhân sự",
                    clearable=True,
                ),
                f"{prefix}-dept-wrap",
                3,
                "fa-building-user",
                "Lọc theo đơn vị / bộ phận",
            )
        return make_filter_col(
            "Bộ phận",
            exec_dropdown(
                id=f"{prefix}-dept-p2",
                options=dept_options,
                multi=True,
                placeholder="Chọn bộ phận nhân sự",
                clearable=True,
            ),
            f"{prefix}-dept-p2-wrap",
            2,
            "fa-building-user",
            "Khoanh vùng theo bộ phận",
        )
    if page_key == "p1":
        if kind == "lh":
            return make_filter_col(
                "Loại hình",
                exec_dropdown(
                    id="lh-type-p1",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Chọn mô hình vận hành",
                    clearable=True,
                ),
                "lh-type-p1-wrap",
                4,
                "fa-layer-group",
                "Phân nhóm theo mô hình khai thác",
            )
        if kind == "hd":
            return make_filter_col(
                "Loại hợp đồng",
                exec_dropdown(
                    id="hd-type-p1",
                    options=HD_OPTIONS,
                    multi=True,
                    placeholder="Chọn loại hợp đồng",
                    clearable=True,
                ),
                "hd-type-p1-wrap",
                4,
                "fa-file-signature",
                "Phân nhóm hợp đồng vận hành",
            )
        if kind == "fleet":
            return make_filter_col(
                "Loại xe",
                exec_dropdown(
                    id=f"{prefix}-type-p1",
                    options=get_scoped_vehicle_type_options(prefix),
                    multi=True,
                    placeholder="Chọn dòng xe",
                    clearable=True,
                ),
                f"{prefix}-type-p1-wrap",
                6,
                "fa-car-side",
                "Phân nhóm đội xe theo dòng xe",
            )
        return dbc.Col(html.Div(), md=4)

    if kind == "lh":
        return make_filter_col(
            "Loại hình",
            exec_dropdown(
                id="lh-type-p2",
                options=LH_OPTIONS,
                multi=True,
                placeholder="Chọn mô hình vận hành",
                clearable=True,
            ),
            "lh-type-p2-wrap",
            4,
            "fa-layer-group",
            "Khoanh vùng mô hình tại khu vực",
        )
    if kind == "hd":
        return make_filter_col(
            "Loại hợp đồng",
            exec_dropdown(
                id="hd-type-p2",
                options=HD_OPTIONS,
                multi=True,
                placeholder="Chọn loại hợp đồng",
                clearable=True,
            ),
            "hd-type-p2-wrap",
            2,
            "fa-file-signature",
            "Khoanh vùng nhóm hợp đồng",
        )
    if kind == "fleet":
        return make_filter_col(
            "Loại xe",
            exec_dropdown(
                id=f"{prefix}-type-p2",
                options=VEHICLE_TYPE_OPTIONS.get(prefix, []),
                multi=True,
                placeholder="Chọn dòng xe",
                clearable=True,
            ),
            f"{prefix}-type-p2-wrap",
            6,
            "fa-car-side",
            "Khoanh vùng nhóm xe theo dòng xe",
        )
    return dbc.Col(html.Div(), md=2)


def _build_lh_business_filter(page_key: str):
    suffix = "p1" if str(page_key) == "p1" else "p2"
    return make_filter_col(
        "Hình thức KD",
        exec_dropdown(
            id=f"lh-business-type-{suffix}",
            options=_daily_business_type_options(),
            multi=True,
            placeholder="Chọn điện/khoán/xăng",
            clearable=True,
        ),
        f"lh-business-type-{suffix}-wrap",
        4 if suffix == "p1" else 3,
        "fa-charging-station",
        "Điện ăn chia / khoán điện / khoán xăng",
    )


def _build_fleet_seat_filter(prefix: str, page_key: str):
    dropdown_id = f"{prefix}-seat-p1" if page_key == "p1" else f"{prefix}-seat-p2"
    wrap_id = f"{prefix}-seat-p1-wrap" if page_key == "p1" else f"{prefix}-seat-p2-wrap"
    helper_text = "Lọc snapshot theo số chỗ mỗi xe" if page_key == "p1" else "Khoanh vùng đội xe theo số chỗ"
    return make_filter_col(
        "Số chỗ",
        exec_dropdown(
            id=dropdown_id,
            options=get_scoped_vehicle_seat_options(prefix),
            multi=True,
            placeholder="Chọn số chỗ",
            clearable=True,
        ),
        wrap_id,
        6 if page_key == "p1" else 4,
        "fa-chair",
        helper_text,
    )


def home_page():
    hero = executive_header(
        "NAM THANG GROUP • TỔNG QUAN",
        "Trang tổng quan dashboard. Menu phân cấp theo cụm nghiệp vụ: Doanh thu, Nhân sự, Kinh doanh và Phương tiện.",
        right_children=html.Div(id="home-summary", className="exec-chip-row")
    )

    quick_nav = executive_section_panel(
        "Bản đồ điều hành theo cụm nghiệp vụ",
        "Dashboard 4 khối điều hành. Mỗi tiêu chuẩn đều giữ 2 page để theo dõi tổng tập đoàn và phân tích sâu vào khu vực.",
        build_home_quick_nav(),
        right_children=[
            filter_panel_chip("4 khối nghiệp vụ", fa_icon("fa-sitemap", 12, GREEN_PRIMARY)),
            filter_panel_chip("9 dashboard chuyên trách", fa_icon("fa-table-cells-large", 12, GREEN_PRIMARY)),
            filter_panel_chip("2 page / module", fa_icon("fa-layer-group", 12, GREEN_PRIMARY)),
        ],
        class_name="mb-3 executive-home-nav-panel"
    )

    filter_row = dbc.Row(
        [
            make_filter_col(
                "Năm",
                exec_dropdown(
                    id="home-year",
                    options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                    value=DEFAULT_YEAR,
                    multi=False,
                    placeholder="Chọn niên độ báo cáo",
                    clearable=True,
                ),
                "home-year-wrap",
                3,
                "fa-calendar-days",
                "Niên độ điều hành",
            ),
            make_filter_col(
                "Tháng",
                exec_dropdown(
                    id="home-month",
                    options=[{"label": m, "value": m} for m in MONTH_OPTIONS_BY_YEAR.get(DEFAULT_YEAR, MONTH_OPTIONS_ALL)],
                    value=[],
                    multi=True,
                    placeholder="Chọn một hoặc nhiều tháng",
                    clearable=True,
                ),
                "home-month-wrap",
                5,
                "fa-calendar",
                "Lọc theo chu kỳ báo cáo",
            ),
            make_filter_col(
                "Khu vực",
                exec_dropdown(
                    id="home-region",
                    options=[{"label": x, "value": x} for x in get_scoped_all_regions()],
                    value=[],
                    multi=True,
                    placeholder="Tất cả khu vực",
                    clearable=True,
                ),
                "home-region-wrap",
                4,
                "fa-map-location-dot",
                "Khoanh vùng điều hành",
            ),
        ],
        className="g-3"
    )
    filters = executive_section_panel(
        "Bộ lọc phân cấp",
        "Bộ lọc phân cấp: đồng bộ cho toàn bộ KPI, biểu đồ và bảng phân tích.",
        filter_row,
        right_children=[
            filter_panel_chip("Kiểm soát phạm vi", fa_icon("fa-crosshairs", 12, GREEN_PRIMARY)),
            filter_panel_chip("Đồng bộ toàn trang", fa_icon("fa-arrows-rotate", 12, GREEN_PRIMARY)),
            filter_panel_chip("Xác nhận đa nhiệm linh hoạt", fa_icon("fa-sliders", 12, GREEN_PRIMARY)),
        ],
        class_name="mb-3 executive-control-dock"
    )

    kpis = dbc.Row(
        [
            dbc.Col(make_kpi_card("Tổng doanh thu", "home-kpi1", "home-kpi1", ICON_MONEY, min_height="230px"), md=3),
            dbc.Col(make_kpi_card("Tổng số cuốc", "home-kpi2", "home-kpi2", ICON_ROUTE, min_height="230px"), md=3),
            dbc.Col(make_kpi_card("Doanh thu TB / cuốc", "home-kpi3", "home-kpi3", ICON_AVG, min_height="230px"), md=3),
            dbc.Col(make_kpi_card("Khu vực hoạt động", "home-kpi4", "home-kpi4", ICON_REGION, min_height="230px"), md=3),
        ],
        className="g-3 mb-3"
    )

    charts1 = dbc.Row(
        [
            dbc.Col(make_graph_card("home-main", "home-main", height="420px"), md=8),
            dbc.Col(make_graph_card("home-region-donut", "home-region-donut", height="420px"), md=4),
        ],
        className="g-3 mb-3"
    )

    charts2 = dbc.Row(
        [
            dbc.Col(make_graph_card("home-region-bar", "home-region-bar", height="380px"), md=4),
            dbc.Col(make_graph_card("home-lh-donut", "home-lh-donut", height="380px"), md=4),
            dbc.Col(make_graph_card("home-hd-bar", "home-hd-bar", height="380px"), md=4),
        ],
        className="g-3 mb-3"
    )

    table = dbc.Row([
        dbc.Col(
            make_table_card(
                "Bảng chi tiết • đa biến",
                "Tổng hợp nhanh theo tháng để ban lãnh đạo theo dõi doanh thu, số cuốc, hiệu suất và khu vực dẫn đầu.",
                dash_table.DataTable(
                    id="home-table",
                    columns=[
                        {"name": "Tháng", "id": "thang_label"},
                        {"name": "Doanh thu", "id": "tong_doanh_thu_fmt"},
                        {"name": "Số cuốc", "id": "tong_so_cuoc_fmt"},
                        {"name": "TB/cuốc", "id": "avg_per_trip_fmt"},
                        {"name": "Khu vực dẫn đầu", "id": "top_region"},
                    ],
                    page_size=12,
                    sort_action="native",
                    filter_action="none",
                    cell_selectable=True,
                    fixed_rows={"headers": True},
                    style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "560px", "borderRadius": "18px", "border": "1px solid #dbe7f3"},
                    style_header={"backgroundColor": "#0f172a", "color": "#ffffff", "fontWeight": "700", "textAlign": "center", "padding": "12px 10px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.25", "fontSize": "12px"},
                    style_cell={"backgroundColor": "#ffffff", "color": "#0f172a", "textAlign": "center", "padding": "11px 10px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.35", "fontSize": "12.5px", "fontWeight": "500", "border": "1px solid #e5edf5"},
                    style_data_conditional=[
                        {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
                        {"if": {"state": "active"}, "backgroundColor": "#ecfdf5", "border": "1px solid #22c55e"},
                        {"if": {"state": "selected"}, "backgroundColor": "#dcfce7", "border": "1px solid #22c55e"},
                    ],
                )
            ),
            md=12
        )
    ])


    return dbc.Container(fluid=True, children=[hero, quick_nav, filters, kpis, charts1, charts2, table])


DAILY_DATE_COL_CANDIDATES = [
    "ngay_du_lieu", "ngày dữ liệu", "ngay du lieu", "ngay", "ngày", "date",
    "report_date", "report date", "ngay_bao_cao", "ngày báo cáo", "ngay bao cao",
    "ngay_chay", "ngày chạy", "ngay chay", "ngay_tao", "ngày tạo", "ngay tao",
    "ngay_cap_nhat", "ngày cập nhật", "ngay cap nhat", "ngay_nhap", "ngày nhập", "ngay nhap",
    "ngay_ghi_nhan", "ngày ghi nhận", "ngay ghi nhan", "ngay_kiem_ke", "ngày kiểm kê", "ngay kiem ke",
    "ngay_trang_thai", "ngày trạng thái", "ngay trang thai", "snapshot_date", "snapshot date",
    "fleet_date", "vehicle_date", "as_of_date", "as of date", "effective_date", "effective date",
    "created_at", "createdat", "updated_at", "updatedat", "timestamp",
]


def _find_daily_date_col(dff: pd.DataFrame) -> str | None:
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return None
    candidate_norm = {norm_text(x) for x in DAILY_DATE_COL_CANDIDATES}
    for col in dff.columns:
        if norm_text(col) in candidate_norm:
            try:
                parsed = pd.to_datetime(dff[col], errors="coerce")
                if parsed.notna().sum() > 0:
                    return col
            except Exception:
                continue
    return None


def _coerce_daily_date_series(dff: pd.DataFrame) -> pd.Series:
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return pd.Series(dtype="datetime64[ns]")
    col = _find_daily_date_col(dff)
    if col:
        s = pd.to_datetime(dff[col], errors="coerce")
    elif "thang_nam_vn" in dff.columns:
        s = pd.to_datetime(dff["thang_nam_vn"], errors="coerce")
    elif "thang_nam" in dff.columns:
        s = pd.to_datetime(dff["thang_nam"], errors="coerce")
    else:
        s = pd.Series([pd.NaT] * len(dff), index=dff.index)
    try:
        if getattr(s.dt, "tz", None) is not None:
            s = s.dt.tz_convert(VN_TZ).dt.tz_localize(None)
    except Exception:
        pass
    return pd.to_datetime(s, errors="coerce").dt.normalize()


def _prepare_daily_frame(source_df: pd.DataFrame, source_label: str = "Doanh thu") -> pd.DataFrame:
    if source_df is None or not isinstance(source_df, pd.DataFrame) or source_df.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "ngay_label", "thang_label", "nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc", "nguon_du_lieu"])
    dff = source_df.copy()
    dff["ngay_du_lieu"] = _coerce_daily_date_series(dff)
    dff = dff[dff["ngay_du_lieu"].notna()].copy()
    if dff.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "ngay_label", "thang_label", "nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc", "nguon_du_lieu"])
    if "khu_vuc" not in dff.columns:
        dff["khu_vuc"] = "Tổng hợp"
    dff["khu_vuc"] = dff["khu_vuc"].fillna("Tổng hợp").astype(str).str.strip()
    dff.loc[dff["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"

    numeric_cols = [
        "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach",
        "so_xe", "so_tai_xe", "km_rong",
        "doanh_thu_moi_km_vd", "doanh_thu_moi_km_khach",
    ]
    for c in numeric_cols:
        if c in dff.columns:
            dff[c] = pd.to_numeric(dff[c], errors="coerce").fillna(0)
    if "tong_doanh_thu" not in dff.columns:
        dff["tong_doanh_thu"] = 0
    if "tong_so_cuoc" not in dff.columns:
        dff["tong_so_cuoc"] = 0
    dff["ngay_label"] = dff["ngay_du_lieu"].dt.strftime("%d/%m/%Y")
    if "thang_label" not in dff.columns:
        dff["thang_label"] = dff["ngay_du_lieu"].dt.strftime("%m/%Y")
    if "nam" not in dff.columns:
        dff["nam"] = dff["ngay_du_lieu"].dt.year
    dff["nguon_du_lieu"] = source_label
    return dff


DAILY_FILTER_CACHE = {}
DAILY_FILTER_CACHE_MAX = 220
DAILY_SOURCE_PREP_CACHE = {}
DAILY_SOURCE_PREP_CACHE_MAX = 48
DAILY_DRIVER_SOURCE_CACHE = {}
DAILY_DRIVER_SOURCE_CACHE_MAX = 120
DAILY_LATEST_OUTPUT_CACHE = {}
DAILY_LATEST_OUTPUT_CACHE_MAX = int(os.getenv("DASH_DAILY_OUTPUT_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
DAILY_TABLE_FRAME_CACHE = {}
DAILY_TABLE_FRAME_CACHE_MAX = int(os.getenv("DASH_DAILY_TABLE_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
DAILY_DATE_BOUNDS_CACHE = {"key": None, "value": None}
DAILY_FLEET_AVAILABLE_CACHE = {}
DAILY_FLEET_AVAILABLE_CACHE_MAX = int(os.getenv("DASH_DAILY_FLEET_AVAILABLE_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
DAILY_DRIVER_OPTIONS_CACHE = {"key": None, "value": None}
DAILY_OPERATING_COUNTS_CACHE = {}
DAILY_OPERATING_COUNTS_CACHE_MAX = int(os.getenv("DASH_DAILY_OPERATING_COUNTS_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
DAILY_AVAILABLE_SUMMARY_CACHE = {}
DAILY_AVAILABLE_SUMMARY_CACHE_MAX = int(os.getenv("DASH_DAILY_AVAILABLE_SUMMARY_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
DAILY_VEHICLE_KPI_PAYLOAD_CACHE = {}
DAILY_VEHICLE_KPI_PAYLOAD_CACHE_MAX = int(os.getenv("DASH_DAILY_VEHICLE_KPI_PAYLOAD_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))
# Daily menu responsive mode: reuse already-filtered daily frames to build all
# KPI payloads/charts/table from the same grouped views. This avoids repeating
# region/day groupby work every time the date filter changes.
DASH_DAILY_RESPONSIVE_CACHE = str(os.getenv("DASH_DAILY_RESPONSIVE_CACHE", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
DAILY_AGG_VIEW_CACHE = {}
DAILY_AGG_VIEW_CACHE_MAX = int(os.getenv("DASH_DAILY_AGG_VIEW_CACHE_MAX", "160" if DASH_SERVERLESS_FAST_PRESET else "256"))


def _normalize_multi_value(values) -> list[str]:
    values = values if isinstance(values, list) else ([values] if values else [])
    return [str(x).strip() for x in values if str(x).strip()]


def _daily_filter_cache_scope_key():
    try:
        scope = current_user_region_scope()
        if scope is None:
            return "__all__"
        return tuple(sorted(str(x) for x in scope))
    except Exception:
        return "__na__"


def _daily_output_cache_key(start_date, end_date, regions, drivers, vehicle_types, business_types, seat_filter, theme, source_dt, source_lh, source_hd, source_cross=None):
    return (
        str(start_date or ""),
        str(end_date or ""),
        tuple(sorted(_normalize_multi_value(regions))),
        tuple(sorted(_normalize_multi_value(drivers))),
        tuple(sorted(_normalize_multi_value(vehicle_types))),
        tuple(sorted(_normalize_multi_value(business_types))),
        tuple(sorted(_normalize_multi_value(seat_filter))),
        str(theme or "light"),
        _daily_filter_cache_scope_key(),
        _df_cache_signature(source_dt),
        _df_cache_signature(source_lh),
        _df_cache_signature(source_hd),
        _df_cache_signature(source_cross) if isinstance(source_cross, pd.DataFrame) else None,
        bool(DASH_ZOOM_STORE_INCLUDE_FIGURE),
        bool(DASH_ZOOM_FORCE_FIGURE_FOR_CHARTS),
        int(DASH_FIGURE_STORE_MAX_ROWS),
        int(DASH_DAILY_TABLE_MAX_ROWS),
        int(_kpi_store_effective_row_limit([{}] * len(DAILY_REGION_DETAIL_ORDER), DASH_KPI_STORE_MAX_ROWS)) if "DAILY_REGION_DETAIL_ORDER" in globals() else max(int(DASH_KPI_STORE_MAX_ROWS), 12),
        str(DASH_DATA_VERSION),
        "kpi-safe-region-rows-v3-business-filter-table-limit",
    )


def _daily_output_cache_get(cache_key):
    cached = DAILY_LATEST_OUTPUT_CACHE.get(cache_key)
    return cached if cached is not None else None


def _daily_output_cache_set(cache_key, value):
    try:
        if len(DAILY_LATEST_OUTPUT_CACHE) > DAILY_LATEST_OUTPUT_CACHE_MAX:
            DAILY_LATEST_OUTPUT_CACHE.clear()
        DAILY_LATEST_OUTPUT_CACHE[cache_key] = value
    except Exception:
        pass
    return value


def _prepared_daily_source_cached(source_df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    if source_df is None or not isinstance(source_df, pd.DataFrame):
        return _prepare_daily_frame(source_df, source_label=source_label)
    cache_key = (id(source_df), len(source_df), tuple(map(str, source_df.columns)), source_label)
    cached = DAILY_SOURCE_PREP_CACHE.get(cache_key)
    if isinstance(cached, pd.DataFrame):
        return _return_df_cached(cached)
    out = _prepare_daily_frame(source_df, source_label=source_label)
    out = _apply_real_data_cutoff(out, day_col="ngay_du_lieu")
    if len(DAILY_SOURCE_PREP_CACHE) > DAILY_SOURCE_PREP_CACHE_MAX:
        DAILY_SOURCE_PREP_CACHE.clear()
    DAILY_SOURCE_PREP_CACHE[cache_key] = out.copy(deep=False)
    return _return_df_cached(out)


def _filter_daily_frame(source_df: pd.DataFrame, start_date=None, end_date=None, regions=None, source_label: str = "Doanh thu", drivers=None) -> pd.DataFrame:
    regions_norm = _normalize_multi_value(regions)
    drivers_norm = _normalize_multi_value(drivers)
    cache_key = (
        id(source_df), len(source_df) if isinstance(source_df, pd.DataFrame) else 0,
        tuple(map(str, source_df.columns)) if isinstance(source_df, pd.DataFrame) else (),
        str(start_date or ""), str(end_date or ""), tuple(sorted(regions_norm)),
        tuple(sorted(drivers_norm)), source_label, _daily_filter_cache_scope_key(),
    )
    cached = DAILY_FILTER_CACHE.get(cache_key)
    if isinstance(cached, pd.DataFrame):
        return _return_df_cached(cached)

    dff = _prepared_daily_source_cached(source_df, source_label=source_label)
    dff = apply_region_scope_to_df(dff)
    if regions_norm and "khu_vuc" in dff.columns:
        dff = dff[dff["khu_vuc"].astype(str).isin(regions_norm)]
    if drivers_norm and "ho_ten" in dff.columns:
        dff = dff[dff["ho_ten"].fillna("").astype(str).str.strip().isin(drivers_norm)]
    try:
        if start_date:
            start_ts = pd.to_datetime(start_date, errors="coerce").normalize()
            if not pd.isna(start_ts):
                dff = dff[dff["ngay_du_lieu"] >= start_ts]
        if end_date:
            end_ts = pd.to_datetime(end_date, errors="coerce").normalize()
            if not pd.isna(end_ts):
                dff = dff[dff["ngay_du_lieu"] <= end_ts]
    except Exception:
        pass

    # Daily business rule: all revenue/trip/KM/vehicle metrics exclude Khoan dien
    # outside Phu Quoc. This app-side guard also protects old cache files that
    # may still contain those rows before refresh_data.py is rerun.
    dff = _daily_filter_khoan_dien_outside_phu_quoc(dff)

    out = dff.copy(deep=False)
    if len(DAILY_FILTER_CACHE) > DAILY_FILTER_CACHE_MAX:
        DAILY_FILTER_CACHE.clear()
    DAILY_FILTER_CACHE[cache_key] = out.copy(deep=False)
    return _return_df_cached(out)


def _daily_numeric_series(dff: pd.DataFrame, col: str, default=0) -> pd.Series:
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return pd.Series(dtype="float64")
    if col not in dff.columns:
        return pd.Series([default] * len(dff), index=dff.index, dtype="float64")
    return pd.to_numeric(dff[col], errors="coerce").fillna(default)


def _daily_filtered_agg_view(dff_dt: pd.DataFrame) -> dict:
    """Build and cache all lightweight grouped views used by the Daily callback.

    The callback used to group the same filtered daily data several times for KPI
    payloads, charts and the detail table. This helper computes those grouped
    views once per filtered frame and reuses them across the whole response.
    """
    empty_region = pd.DataFrame(columns=[
        "khu_vuc", "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh",
        "sokm_cokhach", "so_xe", "so_tai_xe", "avg_per_trip",
        "avg_per_vehicle_day", "rev_fmt", "trip_fmt", "avg_per_trip_fmt",
        "so_xe_fmt", "vehicle_day_fmt", "avg_per_vehicle_day_fmt",
        "km_co_khach_ratio", "km_co_khach_ratio_fmt",
    ])
    empty_day = pd.DataFrame(columns=[
        "ngay_du_lieu", "ngay_label", "tong_doanh_thu", "tong_so_cuoc",
        "rev_fmt", "trip_fmt", "avg_per_trip", "avg_per_trip_fmt",
        "rev_ma7", "rev_ma7_fmt",
    ])
    empty_table = pd.DataFrame(columns=[
        "ngay_label", "thang_label", "khu_vuc", "tong_doanh_thu_fmt",
        "tong_so_cuoc_fmt", "avg_per_trip_fmt", "so_xe_fmt",
        "avg_per_vehicle_day_fmt", "so_tai_xe_fmt", "sokm_vandoanh_fmt",
        "sokm_cokhach_fmt", "km_co_khach_ratio_fmt",
    ])
    if dff_dt is None or not isinstance(dff_dt, pd.DataFrame) or dff_dt.empty:
        return {"region": empty_region, "day": empty_day, "table": empty_table}

    cache_key = (_df_cache_signature(dff_dt), _daily_filter_cache_scope_key(), "daily_agg_view_v3")
    if DASH_DAILY_RESPONSIVE_CACHE:
        cached = DAILY_AGG_VIEW_CACHE.get(cache_key)
        if isinstance(cached, dict):
            return {
                "region": _return_df_cached(cached.get("region", empty_region)),
                "day": _return_df_cached(cached.get("day", empty_day)),
                "table": _return_df_cached(cached.get("table", empty_table)),
            }

    tmp = dff_dt.copy(deep=False)
    if "khu_vuc" not in tmp.columns:
        tmp = tmp.copy()
        tmp["khu_vuc"] = "Tổng hợp"
    tmp["khu_vuc"] = tmp["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")
    if "ngay_du_lieu" not in tmp.columns:
        tmp = tmp.copy()
        tmp["ngay_du_lieu"] = _coerce_daily_date_series(tmp)
    tmp = tmp[tmp["ngay_du_lieu"].notna()].copy(deep=False)
    if tmp.empty:
        return {"region": empty_region, "day": empty_day, "table": empty_table}

    for col in ["tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe"]:
        if col not in tmp.columns:
            tmp[col] = 0
        tmp[col] = pd.to_numeric(tmp[col], errors="coerce").fillna(0)
    if "ngay_label" not in tmp.columns:
        tmp["ngay_label"] = pd.to_datetime(tmp["ngay_du_lieu"], errors="coerce").dt.strftime("%d/%m/%Y")
    if "thang_label" not in tmp.columns:
        tmp["thang_label"] = pd.to_datetime(tmp["ngay_du_lieu"], errors="coerce").dt.strftime("%m/%Y")

    region_g = tmp.groupby("khu_vuc", as_index=False).agg(
        tong_doanh_thu=("tong_doanh_thu", "sum"),
        tong_so_cuoc=("tong_so_cuoc", "sum"),
        sokm_vandoanh=("sokm_vandoanh", "sum"),
        sokm_cokhach=("sokm_cokhach", "sum"),
        so_xe=("so_xe", "sum"),
        so_tai_xe=("so_tai_xe", "sum"),
    ).sort_values("tong_doanh_thu", ascending=False).reset_index(drop=True)
    region_g["avg_per_trip"] = np.where(region_g["tong_so_cuoc"] > 0, region_g["tong_doanh_thu"] / region_g["tong_so_cuoc"].replace(0, 1), 0)
    region_g["avg_per_vehicle_day"] = np.where(region_g["so_xe"] > 0, region_g["tong_doanh_thu"] / region_g["so_xe"].replace(0, 1), 0)
    region_g["km_co_khach_ratio"] = np.where(region_g["sokm_vandoanh"] > 0, region_g["sokm_cokhach"] / region_g["sokm_vandoanh"].replace(0, 1) * 100, 0)
    region_g["rev_fmt"] = region_g["tong_doanh_thu"].apply(fmt_vn)
    region_g["trip_fmt"] = region_g["tong_so_cuoc"].apply(fmt_vn)
    region_g["avg_per_trip_fmt"] = region_g["avg_per_trip"].apply(fmt_vn)
    region_g["so_xe_fmt"] = region_g["so_xe"].apply(fmt_vn)
    region_g["vehicle_day_fmt"] = region_g["so_xe"].apply(fmt_vn)
    region_g["avg_per_vehicle_day_fmt"] = region_g["avg_per_vehicle_day"].apply(fmt_vn)
    region_g["km_co_khach_ratio_fmt"] = region_g["km_co_khach_ratio"].apply(lambda x: fmt_pct(x, 1))

    day_g = tmp.groupby("ngay_du_lieu", as_index=False).agg(
        tong_doanh_thu=("tong_doanh_thu", "sum"),
        tong_so_cuoc=("tong_so_cuoc", "sum"),
    ).sort_values("ngay_du_lieu").reset_index(drop=True)
    day_g["ngay_label"] = pd.to_datetime(day_g["ngay_du_lieu"], errors="coerce").dt.strftime("%d/%m/%Y")
    day_g["rev_fmt"] = day_g["tong_doanh_thu"].apply(fmt_vn)
    day_g["trip_fmt"] = day_g["tong_so_cuoc"].apply(fmt_vn)
    day_g["avg_per_trip"] = np.where(day_g["tong_so_cuoc"] > 0, day_g["tong_doanh_thu"] / day_g["tong_so_cuoc"].replace(0, 1), 0)
    day_g["avg_per_trip_fmt"] = day_g["avg_per_trip"].apply(fmt_vn)
    day_g["rev_ma7"] = day_g["tong_doanh_thu"].rolling(window=7, min_periods=1).mean()
    day_g["rev_ma7_fmt"] = day_g["rev_ma7"].apply(fmt_vn)

    table_g = tmp.groupby(["ngay_du_lieu", "ngay_label", "thang_label", "khu_vuc"], as_index=False).agg(
        tong_doanh_thu=("tong_doanh_thu", "sum"),
        tong_so_cuoc=("tong_so_cuoc", "sum"),
        sokm_vandoanh=("sokm_vandoanh", "sum"),
        sokm_cokhach=("sokm_cokhach", "sum"),
        so_xe=("so_xe", "sum"),
        so_tai_xe=("so_tai_xe", "sum"),
    ).sort_values(["ngay_du_lieu", "tong_doanh_thu"], ascending=[False, False]).reset_index(drop=True)
    table_g["avg_per_trip"] = np.where(table_g["tong_so_cuoc"] > 0, table_g["tong_doanh_thu"] / table_g["tong_so_cuoc"].replace(0, 1), 0)
    table_g["avg_per_vehicle_day"] = np.where(table_g["so_xe"] > 0, table_g["tong_doanh_thu"] / table_g["so_xe"].replace(0, 1), 0)
    table_g["km_co_khach_ratio"] = np.where(table_g["sokm_vandoanh"] > 0, table_g["sokm_cokhach"] / table_g["sokm_vandoanh"].replace(0, 1) * 100, 0)
    table_g["tong_doanh_thu_fmt"] = table_g["tong_doanh_thu"].apply(fmt_vn)
    table_g["tong_so_cuoc_fmt"] = table_g["tong_so_cuoc"].apply(fmt_vn)
    table_g["avg_per_trip_fmt"] = table_g["avg_per_trip"].apply(fmt_vn)
    table_g["so_xe_fmt"] = table_g["so_xe"].apply(fmt_vn)
    table_g["avg_per_vehicle_day_fmt"] = table_g["avg_per_vehicle_day"].apply(fmt_vn)
    table_g["so_tai_xe_fmt"] = table_g["so_tai_xe"].apply(fmt_vn)
    table_g["sokm_vandoanh_fmt"] = table_g["sokm_vandoanh"].apply(fmt_vn)
    table_g["sokm_cokhach_fmt"] = table_g["sokm_cokhach"].apply(fmt_vn)
    table_g["km_co_khach_ratio_fmt"] = table_g["km_co_khach_ratio"].apply(lambda x: fmt_pct(x, 1))
    table_cols = [
        "ngay_label", "thang_label", "khu_vuc", "tong_doanh_thu_fmt",
        "tong_so_cuoc_fmt", "avg_per_trip_fmt", "so_xe_fmt",
        "avg_per_vehicle_day_fmt", "so_tai_xe_fmt", "sokm_vandoanh_fmt",
        "sokm_cokhach_fmt", "km_co_khach_ratio_fmt",
    ]
    table_out = table_g[table_cols].copy()

    result = {"region": region_g, "day": day_g, "table": table_out}
    if DASH_DAILY_RESPONSIVE_CACHE:
        try:
            if len(DAILY_AGG_VIEW_CACHE) > DAILY_AGG_VIEW_CACHE_MAX:
                DAILY_AGG_VIEW_CACHE.clear()
            DAILY_AGG_VIEW_CACHE[cache_key] = {k: v.copy(deep=False) for k, v in result.items()}
        except Exception:
            pass
    return {k: _return_df_cached(v) for k, v in result.items()}


def _daily_payload_from_region_view(region_g: pd.DataFrame, metric_col: str, selected_regions=None):
    if region_g is None or not isinstance(region_g, pd.DataFrame) or region_g.empty or metric_col not in region_g.columns:
        return []
    tmp = region_g.copy(deep=False)
    selected = _normalize_multi_value(selected_regions)
    if selected and "khu_vuc" in tmp.columns:
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(selected)]
    tmp = tmp.sort_values(metric_col, ascending=False)
    total = float(pd.to_numeric(tmp[metric_col], errors="coerce").fillna(0).sum()) if not tmp.empty else 0.0
    out = []
    for _, r in tmp.iterrows():
        name = str(r.get("khu_vuc", ""))
        val = float(r.get(metric_col, 0) or 0)
        out.append({
            "khu_vuc": name,
            "value": val,
            "value_fmt": fmt_vn(val),
            "pct": (val / total * 100.0) if total > 0 else 0.0,
            "color": REGION_COLOR_MAP.get(name, "#888"),
        })
    return out


def _daily_avg_payload_from_region_view(region_g: pd.DataFrame, selected_regions=None):
    if region_g is None or not isinstance(region_g, pd.DataFrame) or region_g.empty:
        return []
    tmp = region_g.copy(deep=False)
    selected = _normalize_multi_value(selected_regions)
    if selected and "khu_vuc" in tmp.columns:
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(selected)]
    if "avg_per_trip" not in tmp.columns:
        tmp = tmp.copy()
        tmp["avg_per_trip"] = np.where(pd.to_numeric(tmp.get("tong_so_cuoc", 0), errors="coerce").fillna(0) > 0, pd.to_numeric(tmp.get("tong_doanh_thu", 0), errors="coerce").fillna(0) / pd.to_numeric(tmp.get("tong_so_cuoc", 0), errors="coerce").fillna(0).replace(0, 1), 0)
    tmp = tmp.sort_values("avg_per_trip", ascending=False)
    return [{
        "khu_vuc": str(r.get("khu_vuc", "")),
        "avg": float(r.get("avg_per_trip", 0) or 0),
        "avg_fmt": fmt_vn(r.get("avg_per_trip", 0)),
        "color": REGION_COLOR_MAP.get(str(r.get("khu_vuc", "")), "#888"),
    } for _, r in tmp.iterrows()]

def _daily_primary_source_df() -> pd.DataFrame:
    ensure_daily_data_loaded()
    return df_daily_checker if isinstance(df_daily_checker, pd.DataFrame) and not df_daily_checker.empty else df_dt


def _daily_lh_source_df() -> pd.DataFrame:
    ensure_daily_data_loaded()
    if isinstance(df_daily_lh_checker, pd.DataFrame) and not df_daily_lh_checker.empty:
        return df_daily_lh_checker
    return df_lh


def _daily_mix_source_df() -> pd.DataFrame:
    ensure_daily_data_loaded()
    if isinstance(df_daily_hinhthuc_checker, pd.DataFrame) and not df_daily_hinhthuc_checker.empty:
        return df_daily_hinhthuc_checker
    if isinstance(df_daily_luong_checker, pd.DataFrame) and not df_daily_luong_checker.empty:
        return df_daily_luong_checker
    return df_hd


def _daily_source_label() -> str:
    ensure_daily_data_loaded()
    if isinstance(df_daily_checker, pd.DataFrame) and not df_daily_checker.empty:
        return "SQL Doanh thu theo ngày"
    return "Dữ liệu tổng hợp hiện có"

def _daily_driver_options():
    ensure_daily_data_loaded()
    source = df_daily_taixe_checker if isinstance(df_daily_taixe_checker, pd.DataFrame) and not df_daily_taixe_checker.empty else df_daily_raw_checker
    cache_key = (_df_cache_signature(source), _daily_filter_cache_scope_key())
    if DAILY_DRIVER_OPTIONS_CACHE.get("key") == cache_key:
        return DAILY_DRIVER_OPTIONS_CACHE.get("value", [])
    if source is None or not isinstance(source, pd.DataFrame) or source.empty or "ho_ten" not in source.columns:
        value = []
    else:
        scoped = apply_region_scope_to_df(source)
        names = scoped["ho_ten"].fillna("").astype(str).str.strip()
        names = sorted([x for x in names.unique().tolist() if x])
        value = [{"label": x, "value": x} for x in names]
    DAILY_DRIVER_OPTIONS_CACHE["key"] = cache_key
    DAILY_DRIVER_OPTIONS_CACHE["value"] = value
    return value



DAILY_VEHICLE_TYPE_CANON = ["Xe Công ty", "Xe thương quyền trả góp", "Xe thương quyền hợp tác"]


def _daily_vehicle_type_options():
    return [{"label": x, "value": x} for x in DAILY_VEHICLE_TYPE_CANON]


DAILY_BUSINESS_TYPE_CANON = ["Taxi điện", "Điện ăn chia", "Khoán điện", "Khoán xăng", "Khoán online", "Xăng ăn chia"]
DAILY_BUSINESS_TYPE_FILTER_DEFAULT = ["Điện ăn chia", "Khoán điện", "Khoán xăng", "Khoán online", "Xăng ăn chia"]
DAILY_BUSINESS_TYPE_MAP = {
    "taxi dien": "Taxi điện",
    "dien an chia": "Điện ăn chia",
    "dien an chia ngay": "Điện ăn chia",
    "khoan dien": "Khoán điện",
    "khoang dien": "Khoán điện",
    "khoan dien ngay": "Khoán điện",
    "khoan xang": "Khoán xăng",
    "khoang xang": "Khoán xăng",
    "khoan online": "Khoán online",
    "xang an chia": "Xăng ăn chia",
}
DAILY_BUSINESS_TYPE_MAP_NORM = {norm_text(k): v for k, v in DAILY_BUSINESS_TYPE_MAP.items()}


def _daily_business_type_options():
    return [{"label": x, "value": x} for x in DAILY_BUSINESS_TYPE_CANON]


def _daily_business_type_col(dff: pd.DataFrame):
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return None
    return find_col_fuzzy(dff, [
        "hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh",
        "hinh_thuc_kd", "hinh thuc kd", "kenh_kinh_doanh", "hinhthuc", "business_type",
    ])


def _daily_business_type_label_series(dff: pd.DataFrame, col: str) -> pd.Series:
    if dff is None or not isinstance(dff, pd.DataFrame) or col not in dff.columns:
        return pd.Series([], dtype="object")
    raw = dff[col].fillna("Chưa rõ hình thức").astype(str).str.strip()
    key = raw.map(norm_text)
    mapped = key.map(DAILY_BUSINESS_TYPE_MAP_NORM)
    missing = mapped.isna()
    if missing.any():
        kk = key[missing]
        mapped.loc[missing & kk.str.contains("taxi dien", na=False)] = "Taxi điện"
        mapped.loc[missing & kk.str.contains("dien an chia", na=False)] = "Điện ăn chia"
        mapped.loc[missing & (kk.str.contains("khoan dien", na=False) | kk.str.contains("khoang dien", na=False))] = "Khoán điện"
        mapped.loc[missing & (kk.str.contains("khoan xang", na=False) | kk.str.contains("khoang xang", na=False))] = "Khoán xăng"
        mapped.loc[missing & kk.str.contains("khoan online", na=False)] = "Khoán online"
        mapped.loc[missing & kk.str.contains("xang an chia", na=False)] = "Xăng ăn chia"
    return mapped.fillna(raw.where(raw.ne(""), "Chưa rõ hình thức")).astype(str).str.strip()


def _filter_daily_business_type_frame(dff: pd.DataFrame, business_types=None) -> pd.DataFrame:
    selected = _normalize_multi_value(business_types)
    if dff is None or not isinstance(dff, pd.DataFrame):
        return pd.DataFrame()
    if not selected:
        return _return_df_cached(dff)
    if dff.empty:
        return dff.copy()
    col = _daily_business_type_col(dff)
    if col is None or col not in dff.columns:
        return dff.iloc[0:0].copy()
    labels = _daily_business_type_label_series(dff, col)
    mask = labels.isin(set(selected))
    out = dff.loc[mask].copy()
    if "hinhthuc_kinhdoanh" not in out.columns:
        out["hinhthuc_kinhdoanh"] = labels.loc[out.index].values if len(out) else []
    else:
        out["hinhthuc_kinhdoanh"] = labels.loc[out.index].values if len(out) else []
    return out


def _daily_frame_has_business_type(dff: pd.DataFrame) -> bool:
    col = _daily_business_type_col(dff)
    return bool(col is not None and isinstance(dff, pd.DataFrame) and col in dff.columns)


def _daily_metric_frame_from_business_type(dff_ht: pd.DataFrame) -> pd.DataFrame:
    """Use the already-filtered daily business-type frame as primary metrics."""
    return _daily_metric_frame_from_lh(dff_ht)


def _daily_cross_source_df(drivers=None) -> pd.DataFrame:
    drivers_norm = _normalize_multi_value(drivers)
    if drivers_norm:
        _ensure_daily_driver_detail_loaded()
        if isinstance(df_daily_taixe_lh_hinhthuc_checker, pd.DataFrame) and not df_daily_taixe_lh_hinhthuc_checker.empty:
            return df_daily_taixe_lh_hinhthuc_checker
    if isinstance(df_daily_lh_hinhthuc_checker, pd.DataFrame) and not df_daily_lh_hinhthuc_checker.empty:
        return df_daily_lh_hinhthuc_checker
    if isinstance(df_daily_raw_checker, pd.DataFrame) and not df_daily_raw_checker.empty:
        return df_daily_raw_checker
    return pd.DataFrame()


def _daily_vehicle_type_col(dff: pd.DataFrame):
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return None
    return find_col_fuzzy(dff, [
        "loai_hinh_std", "loaihinh_hoptac", "loai_hinh_hop_tac", "loại hình hợp tác",
        "loai hinh hop tac", "loai_hinh", "loại hình", "loaihinh", "loai hinh",
        "phan_loai_xe", "phân loại xe", "nhom_xe", "nhóm xe", "type", "loai",
    ])


def _daily_vehicle_type_label_series(dff: pd.DataFrame, col: str) -> pd.Series:
    if dff is None or not isinstance(dff, pd.DataFrame) or col not in dff.columns:
        return pd.Series([], dtype="object")
    if str(col) == "loai_hinh_std":
        return dff[col].fillna("Khác").astype(str).str.strip()
    return map_to_canon(dff[col], LH_MAP).fillna("Khác").astype(str).str.strip()


def _filter_daily_vehicle_type_frame(dff: pd.DataFrame, vehicle_types=None) -> pd.DataFrame:
    selected = _normalize_multi_value(vehicle_types)
    if dff is None or not isinstance(dff, pd.DataFrame):
        return pd.DataFrame()
    if not selected:
        return _return_df_cached(dff)
    if dff.empty:
        return dff.copy()
    col = _daily_vehicle_type_col(dff)
    if col is None or col not in dff.columns:
        return dff.iloc[0:0].copy()
    labels = _daily_vehicle_type_label_series(dff, col)
    mask = labels.isin(set(selected))
    out = dff.loc[mask].copy()
    if "loai_hinh_std" not in out.columns:
        out["loai_hinh_std"] = labels.loc[out.index].values if len(out) else []
    return out


def _daily_frame_has_vehicle_type(dff: pd.DataFrame) -> bool:
    col = _daily_vehicle_type_col(dff)
    return bool(col is not None and isinstance(dff, pd.DataFrame) and col in dff.columns)


def _daily_compact_norm(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm_text(value))


def _daily_is_phu_quoc_series(series_like) -> pd.Series:
    try:
        return pd.Series(series_like).map(lambda x: _daily_compact_norm(x) in {"phuquoc", "pq"}).fillna(False).astype(bool)
    except Exception:
        return pd.Series(False, index=getattr(series_like, "index", None))


def _daily_is_khoan_dien_series(series_like) -> pd.Series:
    try:
        s = pd.Series(series_like).map(norm_text)
        return s.str.contains("khoan dien", regex=False, na=False) | s.str.contains("khoang dien", regex=False, na=False)
    except Exception:
        return pd.Series(False, index=getattr(series_like, "index", None))


def _daily_filter_khoan_dien_outside_phu_quoc(dff: pd.DataFrame) -> pd.DataFrame:
    """Exclude Khoan dien outside Phu Quoc for all Daily-menu metrics and denominators.

    Phu Quoc is the only exception where Khoan dien remains valid for Daily analysis.
    """
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return dff.copy() if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    hinhthuc_col = find_col_fuzzy(dff, [
        "hinhthuc_kinhdoanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh",
        "hinh_thuc_kd", "hinh thuc kd", "kenh_kinh_doanh", "hinhthuc"
    ])
    region_col = find_col_fuzzy(dff, ["khu_vuc", "khu vực", "khu vuc", "region", "kv", "area"])
    if hinhthuc_col is None or hinhthuc_col not in dff.columns or region_col is None or region_col not in dff.columns:
        return dff.copy(deep=False)
    is_khoan = _daily_is_khoan_dien_series(dff[hinhthuc_col])
    is_pq = _daily_is_phu_quoc_series(dff[region_col])
    try:
        return dff.loc[~(is_khoan & ~is_pq)].copy()
    except Exception:
        return dff.copy(deep=False)


DAILY_SEAT_CANON = [5, 7]


def _daily_seat_options():
    return [{"label": f"{x} chỗ", "value": str(x)} for x in DAILY_SEAT_CANON]


def _normalize_daily_seat_values(values) -> list[int]:
    raw = _normalize_multi_value(values)
    out = []
    for item in raw:
        try:
            m = re.search(r"(\d+)", str(item))
            if m:
                out.append(int(m.group(1)))
        except Exception:
            continue
    return [x for x in sorted(set(out)) if x in set(DAILY_SEAT_CANON)]


def _daily_seat_col(dff: pd.DataFrame):
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return None
    return find_col_fuzzy(dff, [
        "so_cho_num", "so_cho", "số chỗ", "so cho", "socho", "seat", "seats",
        "seat_count", "suc_chua", "sức chứa", "cho_ngoi", "chỗ ngồi",
        "so_cho_loc", "nhan_so_cho", "nhãn số chỗ",
    ])


def _daily_seat_series(dff: pd.DataFrame, col: str) -> pd.Series:
    if dff is None or not isinstance(dff, pd.DataFrame) or col not in dff.columns:
        return pd.Series([], dtype="float")
    raw = dff[col]
    numeric = pd.to_numeric(raw, errors="coerce")
    if numeric.notna().sum() >= max(1, int(len(raw) * 0.65)):
        return numeric.fillna(0).round().astype(int)
    return pd.to_numeric(raw.astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(0).round().astype(int)


def _daily_frame_has_seat(dff: pd.DataFrame) -> bool:
    col = _daily_seat_col(dff)
    return bool(col is not None and isinstance(dff, pd.DataFrame) and col in dff.columns)


def _filter_daily_seat_frame(dff: pd.DataFrame, seat_filter=None) -> pd.DataFrame:
    seats = _normalize_daily_seat_values(seat_filter)
    if dff is None or not isinstance(dff, pd.DataFrame):
        return pd.DataFrame()
    if not seats:
        return _return_df_cached(dff)
    if dff.empty:
        return dff.copy()
    col = _daily_seat_col(dff)
    if col is None or col not in dff.columns:
        return dff.iloc[0:0].copy()
    seat_series = _daily_seat_series(dff, col)
    out = dff.loc[seat_series.isin(seats)].copy()
    if "so_cho_num" not in out.columns:
        out["so_cho_num"] = seat_series.loc[out.index].values if len(out) else []
    if "so_cho" not in out.columns:
        out["so_cho"] = out["so_cho_num"].astype(str) + " chỗ" if "so_cho_num" in out.columns else ""
    return out


def _daily_metric_frame_from_lh(dff_lh: pd.DataFrame) -> pd.DataFrame:
    """Use the already-filtered daily LH frame as the primary daily metric frame when filtering by vehicle type."""
    if dff_lh is None or not isinstance(dff_lh, pd.DataFrame) or dff_lh.empty:
        return pd.DataFrame()
    out = dff_lh.copy()
    if "ngay_du_lieu" not in out.columns:
        try:
            out["ngay_du_lieu"] = _coerce_daily_date_series(out)
        except Exception:
            out["ngay_du_lieu"] = pd.NaT
    out["ngay_du_lieu"] = pd.to_datetime(out["ngay_du_lieu"], errors="coerce").dt.normalize()
    out = out[out["ngay_du_lieu"].notna()].copy()
    if out.empty:
        return out
    if "ngay_label" not in out.columns:
        out["ngay_label"] = out["ngay_du_lieu"].dt.strftime("%d/%m/%Y")
    if "thang_label" not in out.columns:
        out["thang_label"] = out["ngay_du_lieu"].dt.strftime("%m/%Y")
    if "nam" not in out.columns:
        out["nam"] = out["ngay_du_lieu"].dt.year
    if "khu_vuc" not in out.columns:
        out["khu_vuc"] = "Tổng hợp"
    for c in ["tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe"]:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    return out


def _daily_vehicle_type_to_fleet_prefixes(vehicle_types=None) -> list[str]:
    selected = set(_normalize_multi_value(vehicle_types))
    if not selected:
        return ["xdt", "xpq"]
    out = []
    if "Xe Công ty" in selected:
        out.append("xdt")
    if {"Xe thương quyền trả góp", "Xe thương quyền hợp tác"}.intersection(selected):
        out.append("xpq")
    return list(dict.fromkeys(out))


def _filter_fleet_frame_by_daily_vehicle_type(dff: pd.DataFrame, prefix: str, vehicle_types=None) -> pd.DataFrame:
    """Filter daily fleet snapshot rows by XDT/XPQ and optional daily vehicle type.

    Important for generic XeDangCo_KV_Ngay sheets: when no vehicle-type filter is selected,
    still split rows by fleet_prefix/loai_hinh so xdt and xpq are not double-counted.
    If a source has no type/prefix column, assume it is already prefix-specific and keep it.
    """
    selected = set(_normalize_multi_value(vehicle_types))
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return pd.DataFrame()
    prefix = str(prefix or "")
    if prefix not in {"xdt", "xpq"}:
        return dff.iloc[0:0].copy()

    base_mask = None
    prefix_col = find_col_fuzzy(dff, ["fleet_prefix", "prefix", "nhom_fleet", "nhóm fleet"])
    if prefix_col is not None and prefix_col in dff.columns:
        prefix_series = dff[prefix_col].fillna("").astype(str).map(lambda x: re.sub(r"[^a-z0-9]+", "", norm_text(x)))
        base_mask = prefix_series.eq(prefix)
    else:
        type_col = _daily_vehicle_type_col(dff)
        if type_col is not None and type_col in dff.columns:
            labels = _daily_vehicle_type_label_series(dff, type_col)
            if prefix == "xdt":
                base_mask = labels.eq("Xe Công ty")
            else:
                base_mask = labels.isin({"Xe thương quyền trả góp", "Xe thương quyền hợp tác"})

    if base_mask is not None:
        dff = dff.loc[base_mask].copy()
    else:
        # No prefix/type metadata found: keep as-is because this is likely a dedicated prefix sheet.
        dff = _return_df_cached(dff)

    if dff.empty:
        return dff.copy()
    if not selected:
        return _return_df_cached(dff)

    if prefix == "xdt":
        return _return_df_cached(dff) if "Xe Công ty" in selected else dff.iloc[0:0].copy()

    tq_selected = selected.intersection({"Xe thương quyền trả góp", "Xe thương quyền hợp tác"})
    if not tq_selected:
        return dff.iloc[0:0].copy()

    type_col = _daily_vehicle_type_col(dff)
    if type_col is not None and type_col in dff.columns:
        labels = _daily_vehicle_type_label_series(dff, type_col)
        filtered = dff.loc[labels.isin(tq_selected)].copy()
        if not filtered.empty:
            return filtered

    if len(tq_selected) >= 2:
        return _return_df_cached(dff)

    # Try to split XPQ into trả góp/hợp tác only when the fleet sheet has a real text column
    # containing those words. If it cannot be split safely, keep all XPQ instead of returning 0.
    target = next(iter(tq_selected))
    pattern = r"tra\s*gop|tra\s+gop" if "trả góp" in target.lower() else r"hop\s*tac|hop\s+tc|hop\s+dong\s+hop\s+tac"
    text_cols = []
    for cand in ["loai_xe", "loai_hinh", "loaihinh_hoptac", "nhom_nhien_lieu", "du_lieu_nguon", "ghi_chu_nguon"]:
        if cand in dff.columns:
            text_cols.append(cand)
    if not text_cols:
        for col in dff.columns:
            try:
                if pd.api.types.is_object_dtype(dff[col]) or pd.api.types.is_string_dtype(dff[col]):
                    text_cols.append(col)
            except Exception:
                continue
    if not text_cols:
        return _return_df_cached(dff)
    try:
        joined = dff[text_cols].fillna("").astype(str).agg(" ".join, axis=1).map(norm_text)
        mask = joined.str.contains(pattern, regex=True, na=False)
        if bool(mask.any()):
            return dff.loc[mask].copy()
    except Exception:
        pass
    return _return_df_cached(dff)


def _daily_fleet_strict_day_series(dff: pd.DataFrame) -> pd.Series:
    """Return only real daily snapshot dates from fleet data; never fall back to month columns."""
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return pd.Series(dtype="datetime64[ns]")
    col = _find_daily_date_col(dff)
    if col is None or col not in dff.columns:
        return pd.Series([pd.NaT] * len(dff), index=dff.index)
    s = pd.to_datetime(dff[col], errors="coerce")
    try:
        if getattr(s.dt, "tz", None) is not None:
            s = s.dt.tz_convert(VN_TZ).dt.tz_localize(None)
    except Exception:
        pass
    return pd.to_datetime(s, errors="coerce").dt.normalize()


def _daily_fleet_vf3_mask(dff: pd.DataFrame) -> pd.Series:
    """Detect VF3 service vehicles so they are excluded from xe đang có."""
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return pd.Series(False, index=getattr(dff, "index", None))
    text_cols = []
    preferred = [
        "loai_xe", "loại xe", "loai xe", "dong_xe", "dòng xe", "dong xe", "model",
        "vehicle_model", "nhan_hieu", "nhãn hiệu", "nhan hieu", "hang_xe", "hãng xe",
        "hang xe", "ten_loai_xe", "tên loại xe", "ten loai xe", "ghi_chu", "ghi chú",
        "muc_dich_su_dung", "mục đích sử dụng", "nhom_xe", "nhóm xe",
    ]
    for cand in preferred:
        col = find_col_fuzzy(dff, [cand])
        if col is not None and col in dff.columns and col not in text_cols:
            text_cols.append(col)
    if not text_cols:
        for col in dff.columns:
            try:
                if pd.api.types.is_object_dtype(dff[col]) or pd.api.types.is_string_dtype(dff[col]):
                    text_cols.append(col)
            except Exception:
                continue
    if not text_cols:
        return pd.Series(False, index=dff.index)
    try:
        joined = dff[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
        compact = joined.map(lambda x: re.sub(r"[^a-z0-9]+", "", norm_text(x)))
        return compact.str.contains("vf3", na=False)
    except Exception:
        return pd.Series(False, index=dff.index)


def _daily_fleet_vehicle_count_frame(raw_df: pd.DataFrame, prefix: str, vehicle_types=None, seat_filter=None) -> pd.DataFrame:
    """Daily xe đang có by date/region from real fleet snapshot rows.

    Requirements:
    - Use only rows with a real daily date column.
    - Include inactive/parked vehicles because this is fleet availability, not revenue activity.
    - Exclude VF3 service vehicles.
    - Do not estimate missing days from month-end/latest snapshots.
    """
    if raw_df is None or not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])
    dff = raw_df.copy()
    dff = _filter_fleet_frame_by_daily_vehicle_type(dff, prefix, vehicle_types)
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])

    dff["ngay_du_lieu"] = _daily_fleet_strict_day_series(dff)
    dff = dff[dff["ngay_du_lieu"].notna()].copy()
    if dff.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])

    # App-side safety: old cache files may still include Khoan dien outside Phu Quoc.
    # Keep Khoan dien only for Phu Quoc; exclude it elsewhere from xe dang co denominator.
    dff = _daily_filter_khoan_dien_outside_phu_quoc(dff)
    if dff.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])

    vf3_mask = _daily_fleet_vf3_mask(dff)
    try:
        dff = dff.loc[~vf3_mask].copy()
    except Exception:
        pass
    if dff.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])

    region_col = find_col_fuzzy(dff, [
        "khu_vuc", "khu vực", "khu vuc", "region", "kv", "area", "ten_khu_vuc", "tên khu vực",
        "chi_nhanh", "chi nhánh", "chi nhanh", "don_vi", "đơn vị", "don vi", "tram", "trạm",
    ])
    if region_col is None or region_col not in dff.columns:
        dff["khu_vuc"] = "Tổng hợp"
    elif region_col != "khu_vuc":
        dff["khu_vuc"] = dff[region_col]
    dff["khu_vuc"] = dff["khu_vuc"].apply(canon_region_name).fillna("Tổng hợp")
    dff = apply_region_scope_to_df(dff)
    if dff is None or dff.empty:
        return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])

    plate_col = find_col_fuzzy(dff, [
        "bien_kiem_soat", "biển kiểm soát", "bien kiem soat", "bien_so", "biển số",
        "bks", "license_plate", "plate", "so_tai", "số tài", "ma_tai", "mã tài",
        "vehicle_no", "taxi_no",
    ])
    count_col = find_col_fuzzy(dff, [
        "so_luong_xe", "số lượng xe", "so luong xe", "so_xe", "số xe", "so xe",
        "tong_so_xe", "tổng số xe", "tong xe", "so_luong", "số lượng", "quantity", "count", "sl",
    ])

    if plate_col is not None and plate_col in dff.columns:
        tmp = dff[["ngay_du_lieu", "khu_vuc", plate_col]].copy()
        tmp[plate_col] = tmp[plate_col].fillna("").astype(str).str.strip()
        tmp = tmp[tmp[plate_col].ne("")].copy()
        if tmp.empty:
            return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])
        out = tmp.groupby(["ngay_du_lieu", "khu_vuc"], as_index=False).agg(xe_dang_co=(plate_col, "nunique"))
    elif count_col is not None and count_col in dff.columns:
        tmp = dff[["ngay_du_lieu", "khu_vuc", count_col]].copy()
        tmp["_count"] = pd.to_numeric(tmp[count_col], errors="coerce").fillna(0)
        tmp = tmp[tmp["_count"] > 0].copy()
        if tmp.empty:
            return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])
        out = tmp.groupby(["ngay_du_lieu", "khu_vuc"], as_index=False).agg(xe_dang_co=("_count", "sum"))
    else:
        tmp = dff[["ngay_du_lieu", "khu_vuc"]].copy()
        out = tmp.groupby(["ngay_du_lieu", "khu_vuc"], as_index=False).size().rename(columns={"size": "xe_dang_co"})

    out["xe_dang_co"] = pd.to_numeric(out["xe_dang_co"], errors="coerce").fillna(0)
    out = out[out["xe_dang_co"] > 0].copy()
    return out[["ngay_du_lieu", "khu_vuc", "xe_dang_co"]]


DAILY_FLEET_SNAPSHOT_SHEET_CANDIDATES = {
    "xdt": [
        "PhuongTien_XeTrucThuoc_KV_Ngay", "XeTrucThuoc_KV_Ngay", "XeTrucThuoc_Ngay_KV",
        "PhuongTien_XeTrucThuoc_Ngay", "XeDangCo_XeTrucThuoc_KV_Ngay",
        "DanhSachXeTrucThuoc_KV_Ngay", "DanhSachXeTrucThuoc_Ngay", "XDT_KV_Ngay", "XeDT_KV_Ngay",
    ],
    "xpq": [
        "PhuongTien_XePhanQuyen_KV_Ngay", "XePhanQuyen_KV_Ngay", "XePhanQuyen_Ngay_KV",
        "PhuongTien_XePhanQuyen_Ngay", "XeDangCo_XePhanQuyen_KV_Ngay",
        "DanhSachXePhanQuyen_KV_Ngay", "DanhSachXePhanQuyen_Ngay", "XPQ_KV_Ngay", "XePQ_KV_Ngay",
    ],
    "generic": [
        "PhuongTien_KV_Ngay", "PhuongTien_Ngay_KhuVuc", "PhuongTien_Ngay",
        "Xe_KV_Ngay", "Xe_Ngay_KhuVuc", "Xe_Ngay",
        "DanhSachXe_KV_Ngay", "DanhSachXe_Ngay", "XeDangCo_KV_Ngay", "XeDangCo_Ngay",
        "DailyFleetSnapshot", "Fleet_Daily", "Fleet_KV_Ngay", "Vehicle_Daily",
    ],
}


def _lh_business_monthly_source_df() -> pd.DataFrame:
    """Monthly LH x business-type source built from Daily cross aggregates when available."""
    try:
        ensure_daily_data_loaded(log=False)
    except Exception:
        pass
    src = _first_non_empty_df(df_daily_lh_hinhthuc_checker, df_daily_raw_checker)
    if src is None or not isinstance(src, pd.DataFrame) or src.empty:
        return pd.DataFrame()
    work = _daily_metric_frame_from_lh(src)
    if work.empty:
        return work
    lh_col = _daily_vehicle_type_col(work)
    ht_col = _daily_business_type_col(work)
    if lh_col is None or ht_col is None or lh_col not in work.columns or ht_col not in work.columns:
        return pd.DataFrame()
    work = work.copy()
    work["loai_hinh_std"] = _daily_vehicle_type_label_series(work, lh_col)
    work["hinhthuc_kinhdoanh"] = _daily_business_type_label_series(work, ht_col)
    if "thang_nam_vn" not in work.columns:
        if "ngay_du_lieu" in work.columns:
            work["thang_nam_vn"] = pd.to_datetime(work["ngay_du_lieu"], errors="coerce").dt.to_period("M").dt.to_timestamp()
        elif "thang_nam" in work.columns:
            work["thang_nam_vn"] = pd.to_datetime(work["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    work["thang_nam_vn"] = pd.to_datetime(work["thang_nam_vn"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    work = work[work["thang_nam_vn"].notna()].copy()
    if work.empty:
        return work
    work["thang_nam"] = work["thang_nam_vn"]
    work["thang_label"] = work["thang_nam_vn"].dt.strftime("%m/%Y")
    work["nam"] = work["thang_nam_vn"].dt.year
    if "khu_vuc" not in work.columns:
        work["khu_vuc"] = "Tổng hợp"
    num_cols = [c for c in ["tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe"] if c in work.columns]
    for c in num_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)
    group_cols = ["thang_nam", "thang_nam_vn", "thang_label", "nam", "khu_vuc", "loai_hinh_std", "hinhthuc_kinhdoanh"]
    agg = {c: "sum" for c in num_cols}
    if not agg:
        work["tong_doanh_thu"] = 0
        agg = {"tong_doanh_thu": "sum"}
    out = work.groupby(group_cols, as_index=False, dropna=False).agg(agg)
    if "tong_so_cuoc" not in out.columns:
        out["tong_so_cuoc"] = 0
    return _apply_real_data_cutoff(out).reset_index(drop=True)


def _apply_lh_business_filter_frame(dff: pd.DataFrame, business_filter=None) -> pd.DataFrame:
    selected = _normalize_multi_value(business_filter)
    if not selected:
        return dff
    return _filter_daily_business_type_frame(dff, selected)


def _read_daily_fleet_snapshot_source(prefix: str):
    """Prefer explicit daily fleet snapshot sheets before falling back to the menu fleet source."""
    prefix = str(prefix or "")
    candidates = list(DAILY_FLEET_SNAPSHOT_SHEET_CANDIDATES.get(prefix, []))
    candidates.extend(DAILY_FLEET_SNAPSHOT_SHEET_CANDIDATES.get("generic", []))
    try:
        raw = _read_optional_sheet(candidates, menu_key=None)
        if isinstance(raw, pd.DataFrame) and not raw.empty:
            return raw
    except Exception:
        pass
    try:
        return _read_vehicle_source_sheet(prefix)
    except Exception:
        return globals().get(f"df_{prefix}")


def _daily_fleet_available_daily(vehicle_types=None, seat_filter=None) -> pd.DataFrame:
    """Disabled for Daily menu; kept as a no-op compatibility helper."""
    return pd.DataFrame(columns=["ngay_du_lieu", "khu_vuc", "xe_dang_co"])


def _daily_available_vehicle_summary(metric_frame: pd.DataFrame, vehicle_types=None, seat_filter=None, start_date=None, end_date=None, regions=None) -> dict:
    """Disabled for Daily menu; kept as a no-op compatibility helper."""
    return {"total_available_vehicle_days": 0.0, "rows": [], "source": "disabled"}


def _daily_vehicle_kpi_payload(start_date=None, end_date=None, regions=None, drivers=None, vehicle_types=None, business_types=None, seat_filter=None, metric_frame=None, max_items: int = 8, available_summary=None):
    """Rows for the Xe hoạt động zoom table.

    Lean Daily version: only active vehicles, vehicle-days and DT/xe KD-ngày.
    It intentionally does not calculate the removed total-fleet denominator, so this
    callback stays on the already-aggregated Daily revenue/activity sheets.
    """
    selected_types = _normalize_multi_value(vehicle_types)
    selected_business = _normalize_multi_value(business_types)
    if (selected_types or selected_business) and (_normalize_multi_value(drivers) or DASH_DAILY_LAZY_DRIVER_DETAIL):
        _ensure_daily_driver_detail_loaded()
    metric_frame = metric_frame if isinstance(metric_frame, pd.DataFrame) else pd.DataFrame()
    cache_key = (
        str(start_date or ""), str(end_date or ""),
        tuple(sorted(_normalize_multi_value(regions))),
        tuple(sorted(_normalize_multi_value(drivers))),
        tuple(sorted(selected_types)),
        tuple(sorted(selected_business)),
        _df_cache_signature(metric_frame),
        _daily_filter_cache_scope_key(),
        "lean_vehicle_payload_v2",
    )
    cached = DAILY_VEHICLE_KPI_PAYLOAD_CACHE.get(cache_key)
    if isinstance(cached, list):
        return [dict(x) for x in cached]

    op_source = _first_non_empty_df(
        df_daily_taixe_lh_hinhthuc_checker if (selected_types and selected_business) else pd.DataFrame(),
        df_daily_taixe_lh_checker if selected_types else pd.DataFrame(),
        df_daily_taixe_hinhthuc_checker if selected_business else pd.DataFrame(),
        df_daily_taixe_checker,
        df_daily_raw_checker,
    )
    op = pd.DataFrame()
    if isinstance(op_source, pd.DataFrame) and not op_source.empty:
        op = _filter_daily_frame(op_source, start_date, end_date, regions, source_label="Tài xế ngày", drivers=drivers)
        if selected_types:
            op = _filter_daily_vehicle_type_frame(op, selected_types)
        if selected_business:
            op = _filter_daily_business_type_frame(op, selected_business)
        op = _daily_filter_khoan_dien_outside_phu_quoc(op)
        if seat_filter:
            op = _filter_daily_seat_frame(op, seat_filter)

    revenue_by_region = pd.DataFrame(columns=["khu_vuc", "tong_doanh_thu", "vehicle_day"])
    if isinstance(metric_frame, pd.DataFrame) and not metric_frame.empty and "khu_vuc" in metric_frame.columns:
        tmp = metric_frame.copy()
        if "tong_doanh_thu" not in tmp.columns:
            tmp["tong_doanh_thu"] = 0
        if "so_xe" not in tmp.columns:
            tmp["so_xe"] = 0
        tmp["khu_vuc"] = tmp["khu_vuc"].apply(canon_region_name)
        tmp["tong_doanh_thu"] = pd.to_numeric(tmp["tong_doanh_thu"], errors="coerce").fillna(0)
        tmp["so_xe"] = pd.to_numeric(tmp["so_xe"], errors="coerce").fillna(0)
        revenue_by_region = tmp.groupby("khu_vuc", as_index=False).agg(
            tong_doanh_thu=("tong_doanh_thu", "sum"),
            vehicle_day=("so_xe", "sum"),
        )

    active_by_region = pd.DataFrame()
    if isinstance(op, pd.DataFrame) and not op.empty and "khu_vuc" in op.columns:
        op = op.copy()
        op["khu_vuc"] = op["khu_vuc"].apply(canon_region_name)
        def _nunique_clean(series):
            return series.fillna("").astype(str).str.strip().replace({"": pd.NA}).dropna().nunique()
        agg = {}
        if "bks" in op.columns:
            agg["active_vehicle"] = ("bks", _nunique_clean)
        elif "so_xe" in op.columns:
            op["_so_xe_num"] = pd.to_numeric(op["so_xe"], errors="coerce").fillna(0)
            agg["active_vehicle"] = ("_so_xe_num", "sum")
        if "ho_ten" in op.columns:
            agg["active_driver"] = ("ho_ten", _nunique_clean)
        elif "so_tai_xe" in op.columns:
            op["_so_tai_xe_num"] = pd.to_numeric(op["so_tai_xe"], errors="coerce").fillna(0)
            agg["active_driver"] = ("_so_tai_xe_num", "sum")
        if agg:
            active_by_region = op.groupby("khu_vuc", as_index=False).agg(**agg)

    if active_by_region.empty and not revenue_by_region.empty:
        active_by_region = revenue_by_region[["khu_vuc", "vehicle_day"]].copy()
        active_by_region["active_vehicle"] = active_by_region["vehicle_day"]
        active_by_region["active_driver"] = 0
        active_by_region = active_by_region.drop(columns=["vehicle_day"], errors="ignore")

    if active_by_region.empty and revenue_by_region.empty:
        return []

    g = active_by_region.merge(revenue_by_region, on="khu_vuc", how="outer").fillna(0)
    for c in ["active_vehicle", "active_driver", "tong_doanh_thu", "vehicle_day"]:
        if c not in g.columns:
            g[c] = 0
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0)
    g["avg_per_vehicle_day"] = np.where(g["vehicle_day"] > 0, g["tong_doanh_thu"] / g["vehicle_day"].replace(0, 1), 0)
    g = g.sort_values("active_vehicle", ascending=False)
    if max_items:
        g = g.head(int(max_items))
    total_active = float(g["active_vehicle"].sum()) if not g.empty else 0.0
    rows = []
    for _, r in g.iterrows():
        active = float(r.get("active_vehicle", 0) or 0)
        rows.append({
            "khu_vuc": str(r.get("khu_vuc", "")),
            "metric_fmt": fmt_vn(active),
            "vehicle_day_fmt": fmt_vn(r.get("vehicle_day", 0)),
            "avg_per_vehicle_day_fmt": fmt_vn(r.get("avg_per_vehicle_day", 0)),
            "pct": (active / total_active * 100.0) if total_active > 0 else 0.0,
            "pct_fmt": fmt_pct((active / total_active * 100.0) if total_active > 0 else 0.0, 1),
            "color": REGION_COLOR_MAP.get(str(r.get("khu_vuc", "")), "#888"),
        })
    try:
        if len(DAILY_VEHICLE_KPI_PAYLOAD_CACHE) > DAILY_VEHICLE_KPI_PAYLOAD_CACHE_MAX:
            DAILY_VEHICLE_KPI_PAYLOAD_CACHE.clear()
        DAILY_VEHICLE_KPI_PAYLOAD_CACHE[cache_key] = [dict(x) for x in rows]
    except Exception:
        pass
    return rows


DAILY_REGION_DETAIL_ORDER = [
    "An Giang", "Bạc Liêu", "Cà Mau", "Cần Thơ", "Hậu Giang",
    "Phú Quốc", "Rạch Giá", "Sóc Trăng", "Vĩnh Long",
]


def _daily_detail_regions(selected_regions=None) -> list[str]:
    """Region order for Daily KPI detail tables.

    When no region filter is selected, show all 9 operating regions so every Daily
    KPI card detail is comparable across branches, including zero-value regions.
    When a region filter is selected, respect that explicit filter.
    """
    selected = _normalize_multi_value(selected_regions)
    if selected:
        return [str(canon_region_name(x) or x) for x in selected]
    try:
        scope = current_user_region_scope()
        if scope is not None:
            scope_set = {str(x) for x in _normalize_region_list(scope)}
            return [r for r in DAILY_REGION_DETAIL_ORDER if str(r) in scope_set]
    except Exception:
        pass
    return DAILY_REGION_DETAIL_ORDER.copy()


def _daily_region_order_index(region_name: str) -> int:
    try:
        return DAILY_REGION_DETAIL_ORDER.index(str(region_name))
    except Exception:
        return 999


def _sort_daily_detail_rows(rows, numeric_key: str, descending: bool = True):
    out = [] if rows is None else [dict(r) for r in rows]
    def _num(row):
        try:
            return float(row.get(numeric_key, 0) or 0)
        except Exception:
            return 0.0
    return sorted(out, key=lambda r: (-_num(r) if descending else _num(r), _daily_region_order_index(r.get("khu_vuc", "")), str(r.get("khu_vuc", ""))))


def _complete_daily_value_payload(rows, selected_regions=None, value_key="value", fmt_key="value_fmt", pct_key="pct"):
    base_rows = [] if rows is None else [dict(r) for r in rows]
    order = _daily_detail_regions(selected_regions)
    by_region = {}
    for row in base_rows:
        region = str(canon_region_name(row.get("khu_vuc")) or row.get("khu_vuc") or "").strip()
        if not region:
            continue
        row["khu_vuc"] = region
        by_region[region] = row
    for region in order:
        if region not in by_region:
            by_region[region] = {
                "khu_vuc": region,
                value_key: 0.0,
                fmt_key: fmt_vn(0),
                "color": REGION_COLOR_MAP.get(region, "#888"),
            }
    total = 0.0
    for row in by_region.values():
        try:
            total += float(row.get(value_key, 0) or 0)
        except Exception:
            pass
    out = []
    for region in order:
        row = by_region.get(region, {"khu_vuc": region})
        try:
            val = float(row.get(value_key, 0) or 0)
        except Exception:
            val = 0.0
        row[value_key] = val
        row[fmt_key] = row.get(fmt_key) or fmt_vn(val)
        if pct_key:
            pct = (val / total * 100.0) if total > 0 else 0.0
            row[pct_key] = pct
            row["pct_fmt"] = fmt_pct(pct, 1)
        row["color"] = row.get("color") or REGION_COLOR_MAP.get(region, "#888")
        out.append(row)
    return _sort_daily_detail_rows(out, value_key, descending=True)


def _complete_daily_avg_payload(rows, selected_regions=None):
    base_rows = [] if rows is None else [dict(r) for r in rows]
    order = _daily_detail_regions(selected_regions)
    by_region = {}
    for row in base_rows:
        region = str(canon_region_name(row.get("khu_vuc")) or row.get("khu_vuc") or "").strip()
        if not region:
            continue
        row["khu_vuc"] = region
        by_region[region] = row
    out = []
    for region in order:
        row = by_region.get(region, {"khu_vuc": region})
        try:
            avg = float(row.get("avg", 0) or 0)
        except Exception:
            avg = 0.0
        row["avg"] = avg
        row["avg_fmt"] = row.get("avg_fmt") or fmt_vn(avg)
        row["color"] = row.get("color") or REGION_COLOR_MAP.get(region, "#888")
        out.append(row)
    return _sort_daily_detail_rows(out, "avg", descending=True)


def _complete_daily_vehicle_payload(rows, selected_regions=None):
    base_rows = [] if rows is None else [dict(r) for r in rows]
    order = _daily_detail_regions(selected_regions)
    by_region = {}
    for row in base_rows:
        region = str(canon_region_name(row.get("khu_vuc")) or row.get("khu_vuc") or "").strip()
        if not region:
            continue
        row["khu_vuc"] = region
        by_region[region] = row
    for region in order:
        if region not in by_region:
            by_region[region] = {
                "khu_vuc": region,
                "metric_fmt": fmt_vn(0),
                "vehicle_day_fmt": fmt_vn(0),
                "avg_per_vehicle_day_fmt": fmt_vn(0),
                "pct": 0.0,
                "pct_fmt": fmt_pct(0, 1),
                "color": REGION_COLOR_MAP.get(region, "#888"),
            }
    # Recompute percentage from the displayed active-vehicle metric where possible.
    def _parse_fmt_number(value):
        try:
            return float(str(value).replace(".", "").replace(",", "."))
        except Exception:
            return 0.0
    total_active = sum(_parse_fmt_number(by_region.get(region, {}).get("metric_fmt", 0)) for region in order)
    out = []
    for region in order:
        row = by_region.get(region, {"khu_vuc": region})
        for key in ["metric_fmt", "vehicle_day_fmt", "avg_per_vehicle_day_fmt"]:
            row[key] = row.get(key) or fmt_vn(0)
        active = _parse_fmt_number(row.get("metric_fmt", 0))
        pct = (active / total_active * 100.0) if total_active > 0 else 0.0
        row["pct"] = pct
        row["pct_fmt"] = fmt_pct(pct, 1)
        row["color"] = row.get("color") or REGION_COLOR_MAP.get(region, "#888")
        row["_active_numeric"] = active
        out.append(row)
    out = _sort_daily_detail_rows(out, "_active_numeric", descending=True)
    for row in out:
        try:
            row.pop("_active_numeric", None)
        except Exception:
            pass
    return out


def _daily_default_start_date(min_d, max_d):
    try:
        if max_d is None or pd.isna(max_d):
            return min_d
        start = pd.Timestamp(max_d).normalize() - pd.Timedelta(days=29)
        if min_d is not None and not pd.isna(min_d):
            start = max(start, pd.Timestamp(min_d).normalize())
        return start
    except Exception:
        return min_d


def _first_non_empty_df(*frames):
    for frame in frames:
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame
    return pd.DataFrame()


def _ensure_daily_driver_detail_loaded():
    """Load driver-specific Daily breakdown sheets only when a driver filter is used."""
    global DAILY_DRIVER_DETAIL_LOADED, df_daily_taixe_lh_checker, df_daily_taixe_hinhthuc_checker, df_daily_taixe_lh_hinhthuc_checker, df_daily_taixe_luong_checker
    if not DASH_DAILY_LAZY_DRIVER_DETAIL or DAILY_DRIVER_DETAIL_LOADED:
        return
    started = time.perf_counter()
    try:
        df_daily_taixe_lh_checker = _df_reset_in_place(
            df_daily_taixe_lh_checker,
            _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_LH_SHEET_CANDIDATES),
        )
        df_daily_taixe_hinhthuc_checker = _df_reset_in_place(
            df_daily_taixe_hinhthuc_checker,
            _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_HINHTHUC_SHEET_CANDIDATES),
        )
        df_daily_taixe_lh_hinhthuc_checker = _df_reset_in_place(
            df_daily_taixe_lh_hinhthuc_checker,
            _read_daily_checker_multi_category_df(
                DAILY_CHECKER_TAIXE_LH_HINHTHUC_SHEET_CANDIDATES,
                category_specs=[
                    ("loaihinh_hoptac", ["loaihinh_hoptac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình"]),
                    ("hinhthuc_kinhdoanh", ["hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh"]),
                ],
                source_label="Tài xế + loại hình + hình thức ngày checker",
            ),
        )
        df_daily_taixe_luong_checker = _df_reset_in_place(
            df_daily_taixe_luong_checker,
            _read_daily_driver_grouped_df(DAILY_CHECKER_TAIXE_LUONG_SHEET_CANDIDATES),
        )
    finally:
        DAILY_DRIVER_DETAIL_LOADED = True
        try:
            DAILY_DRIVER_SOURCE_CACHE.clear()
            DAILY_FILTER_CACHE.clear()
            DAILY_LATEST_OUTPUT_CACHE.clear()
        except Exception:
            pass
        if DASH_LOG_CALLBACK_TIMING or DASH_LOG_BOOT_TIMING:
            _perf_log("daily_driver_detail_lazy_load", started)


def _daily_sources_for_driver_filter(drivers=None):
    ensure_daily_data_loaded()
    drivers_norm = _normalize_multi_value(drivers)
    if drivers_norm:
        _ensure_daily_driver_detail_loaded()
        driver_key = (
            tuple(sorted(drivers_norm)),
            _daily_filter_cache_scope_key(),
            _df_cache_signature(df_daily_taixe_checker),
            _df_cache_signature(df_daily_taixe_lh_checker),
            _df_cache_signature(df_daily_taixe_hinhthuc_checker),
            _df_cache_signature(df_daily_taixe_lh_hinhthuc_checker),
            _df_cache_signature(df_daily_taixe_luong_checker),
        )
        cached = DAILY_DRIVER_SOURCE_CACHE.get(driver_key)
        if cached is not None:
            return cached

        source_dt = _first_non_empty_df(df_daily_taixe_checker, df_daily_raw_checker)
        source_lh = _first_non_empty_df(df_daily_taixe_lh_checker, df_daily_lh_checker, df_daily_raw_checker)
        source_mix = _first_non_empty_df(
            df_daily_taixe_hinhthuc_checker,
            df_daily_taixe_luong_checker,
            df_daily_hinhthuc_checker,
            df_daily_luong_checker,
            df_daily_raw_checker,
        )
        result = (source_dt, source_lh, source_mix)
        if len(DAILY_DRIVER_SOURCE_CACHE) > DAILY_DRIVER_SOURCE_CACHE_MAX:
            DAILY_DRIVER_SOURCE_CACHE.clear()
        DAILY_DRIVER_SOURCE_CACHE[driver_key] = result
        return result
    return _daily_primary_source_df(), _daily_lh_source_df(), _daily_mix_source_df()


def _daily_unique_operating_counts(start_date=None, end_date=None, regions=None, drivers=None, vehicle_types=None, business_types=None, seat_filter=None):
    ensure_daily_data_loaded()
    selected_types = _normalize_multi_value(vehicle_types)
    selected_business = _normalize_multi_value(business_types)
    if (selected_types or selected_business) and (_normalize_multi_value(drivers) or DASH_DAILY_LAZY_DRIVER_DETAIL):
        _ensure_daily_driver_detail_loaded()
    source = _first_non_empty_df(
        df_daily_taixe_lh_hinhthuc_checker if (selected_types and selected_business) else pd.DataFrame(),
        df_daily_taixe_lh_checker if selected_types else pd.DataFrame(),
        df_daily_taixe_hinhthuc_checker if selected_business else pd.DataFrame(),
        df_daily_taixe_checker,
        df_daily_raw_checker,
    )
    cache_key = (
        str(start_date or ""), str(end_date or ""),
        tuple(sorted(_normalize_multi_value(regions))),
        tuple(sorted(_normalize_multi_value(drivers))),
        tuple(sorted(selected_types)),
        tuple(sorted(selected_business)),
        _df_cache_signature(source),
        _daily_filter_cache_scope_key(),
    )
    cached = DAILY_OPERATING_COUNTS_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)
    if source is None or not isinstance(source, pd.DataFrame) or source.empty:
        return None
    dff = _filter_daily_frame(source, start_date, end_date, regions, source_label="Tài xế ngày", drivers=drivers)
    if selected_types:
        dff = _filter_daily_vehicle_type_frame(dff, selected_types)
    if selected_business:
        dff = _filter_daily_business_type_frame(dff, selected_business)
    dff = _daily_filter_khoan_dien_outside_phu_quoc(dff)
    if seat_filter:
        dff = _filter_daily_seat_frame(dff, seat_filter)
    if dff.empty:
        result = {"vehicles": 0, "drivers": 0, "regions": 0}
        try:
            if len(DAILY_OPERATING_COUNTS_CACHE) > DAILY_OPERATING_COUNTS_CACHE_MAX:
                DAILY_OPERATING_COUNTS_CACHE.clear()
            DAILY_OPERATING_COUNTS_CACHE[cache_key] = dict(result)
        except Exception:
            pass
        return result
    def _nunique(col):
        if col not in dff.columns:
            return 0
        return int(dff[col].fillna("").astype(str).str.strip().replace({"": pd.NA}).dropna().nunique())
    result = {
        "vehicles": _nunique("bks"),
        "drivers": _nunique("ho_ten"),
        "regions": _nunique("khu_vuc"),
    }
    try:
        if len(DAILY_OPERATING_COUNTS_CACHE) > DAILY_OPERATING_COUNTS_CACHE_MAX:
            DAILY_OPERATING_COUNTS_CACHE.clear()
        DAILY_OPERATING_COUNTS_CACHE[cache_key] = dict(result)
    except Exception:
        pass
    return result


def _daily_top_driver_frame(start_date=None, end_date=None, regions=None, drivers=None, limit: int = 10):
    ensure_daily_data_loaded()
    source = _first_non_empty_df(df_daily_taixe_checker, df_daily_raw_checker)
    if source is None or not isinstance(source, pd.DataFrame) or source.empty:
        return pd.DataFrame()
    dff = _filter_daily_frame(source, start_date, end_date, regions, source_label="Tài xế ngày", drivers=drivers)
    if dff.empty or "ho_ten" not in dff.columns:
        return pd.DataFrame()
    top = dff.groupby("ho_ten", as_index=False).agg(
        tong_doanh_thu=("tong_doanh_thu", "sum"),
        tong_so_cuoc=("tong_so_cuoc", "sum"),
        sokm_vandoanh=("sokm_vandoanh", "sum") if "sokm_vandoanh" in dff.columns else ("tong_so_cuoc", "sum"),
    ).sort_values("tong_doanh_thu", ascending=False).head(limit)
    top["rev_fmt"] = top["tong_doanh_thu"].apply(fmt_vn)
    top["trip_fmt"] = top["tong_so_cuoc"].apply(fmt_vn)
    return top



def _daily_date_bounds():
    ensure_daily_data_loaded()
    frames = [_daily_primary_source_df(), _daily_lh_source_df(), _daily_mix_source_df(), df_daily_taixe_checker]
    cache_key = tuple(_df_cache_signature(f) for f in frames) + (_daily_filter_cache_scope_key(), str(_current_vn_day_start()))
    if DAILY_DATE_BOUNDS_CACHE.get("key") == cache_key:
        return DAILY_DATE_BOUNDS_CACHE.get("value", (None, None))
    dates = []
    cutoff_day = _current_vn_day_start()
    for dff in frames:
        try:
            s = _coerce_daily_date_series(dff).dropna()
            if not s.empty:
                s = s[s <= cutoff_day]
                if not s.empty:
                    dates.extend(s.tolist())
        except Exception:
            continue
    if not dates:
        value = (None, None)
    else:
        mn = pd.Timestamp(min(dates)).normalize()
        mx = min(pd.Timestamp(max(dates)).normalize(), cutoff_day)
        value = (mn, mx)
    DAILY_DATE_BOUNDS_CACHE["key"] = cache_key
    DAILY_DATE_BOUNDS_CACHE["value"] = value
    return value


def _date_iso(ts):
    try:
        if ts is None or pd.isna(ts):
            return None
        return pd.Timestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return None


def _format_date_range_text(start_date, end_date):
    try:
        if start_date and end_date:
            s0 = pd.to_datetime(start_date).strftime("%d/%m/%Y")
            s1 = pd.to_datetime(end_date).strftime("%d/%m/%Y")
            return s0 if s0 == s1 else f"{s0} - {s1}"
        if start_date:
            return "Từ " + pd.to_datetime(start_date).strftime("%d/%m/%Y")
        if end_date:
            return "Đến " + pd.to_datetime(end_date).strftime("%d/%m/%Y")
    except Exception:
        pass
    return "Tất cả ngày"


def _daily_table_columns():
    return [
        {"name": "Ngày dữ liệu", "id": "ngay_label"},
        {"name": "Kỳ dữ liệu", "id": "thang_label"},
        {"name": "Khu vực", "id": "khu_vuc"},
        {"name": "Doanh thu", "id": "tong_doanh_thu_fmt"},
        {"name": "Số cuốc", "id": "tong_so_cuoc_fmt"},
        {"name": "TB / cuốc", "id": "avg_per_trip_fmt"},
        {"name": "Xe hoạt động", "id": "so_xe_fmt"},
        {"name": "TB / xe-ngày", "id": "avg_per_vehicle_day_fmt"},
        {"name": "Tài xế", "id": "so_tai_xe_fmt"},
        {"name": "KM vận doanh", "id": "sokm_vandoanh_fmt"},
        {"name": "KM có khách", "id": "sokm_cokhach_fmt"},
        {"name": "Tỷ lệ KM khách", "id": "km_co_khach_ratio_fmt"},
    ]


def _daily_table_frame(dff: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "ngay_du_lieu", "ngay_label", "thang_label", "khu_vuc",
        "tong_doanh_thu", "tong_so_cuoc", "sokm_vandoanh", "sokm_cokhach",
        "so_xe", "so_tai_xe",
    ]
    cache_key = None
    if dff is None or dff.empty:
        out = pd.DataFrame(columns=cols)
    else:
        cache_key = (_df_cache_signature(dff), _daily_filter_cache_scope_key())
        cached = DAILY_TABLE_FRAME_CACHE.get(cache_key)
        if isinstance(cached, pd.DataFrame):
            return _return_df_cached(cached)
        temp = dff.copy()
        for c in ["sokm_vandoanh", "sokm_cokhach"]:
            if c not in temp.columns:
                temp[c] = 0
            temp[c] = pd.to_numeric(temp[c], errors="coerce").fillna(0)

        def _nunique_clean(series):
            return series.fillna("").astype(str).str.strip().replace({"": pd.NA}).dropna().nunique()

        if "so_xe" in temp.columns:
            temp["so_xe_metric"] = pd.to_numeric(temp["so_xe"], errors="coerce").fillna(0)
            xe_agg = ("so_xe_metric", "sum")
        elif "bks" in temp.columns:
            xe_agg = ("bks", _nunique_clean)
        else:
            temp["so_xe_metric"] = 0
            xe_agg = ("so_xe_metric", "sum")

        if "so_tai_xe" in temp.columns:
            temp["so_tai_xe_metric"] = pd.to_numeric(temp["so_tai_xe"], errors="coerce").fillna(0)
            driver_agg = ("so_tai_xe_metric", "sum")
        elif "ho_ten" in temp.columns:
            driver_agg = ("ho_ten", _nunique_clean)
        else:
            temp["so_tai_xe_metric"] = 0
            driver_agg = ("so_tai_xe_metric", "sum")

        out = temp.groupby(["ngay_du_lieu", "ngay_label", "thang_label", "khu_vuc"], as_index=False).agg(
            tong_doanh_thu=("tong_doanh_thu", "sum"),
            tong_so_cuoc=("tong_so_cuoc", "sum"),
            sokm_vandoanh=("sokm_vandoanh", "sum"),
            sokm_cokhach=("sokm_cokhach", "sum"),
            so_xe=xe_agg,
            so_tai_xe=driver_agg,
        ).sort_values(["ngay_du_lieu", "tong_doanh_thu"], ascending=[False, False])
    out["tong_doanh_thu_fmt"] = pd.to_numeric(out.get("tong_doanh_thu", 0), errors="coerce").fillna(0).apply(fmt_vn)
    out["tong_so_cuoc_fmt"] = pd.to_numeric(out.get("tong_so_cuoc", 0), errors="coerce").fillna(0).apply(fmt_vn)
    out["avg_per_trip"] = np.where(
        pd.to_numeric(out.get("tong_so_cuoc", 0), errors="coerce").fillna(0) > 0,
        pd.to_numeric(out.get("tong_doanh_thu", 0), errors="coerce").fillna(0) / pd.to_numeric(out.get("tong_so_cuoc", 0), errors="coerce").fillna(0).replace(0, 1),
        0,
    )
    out["avg_per_trip_fmt"] = pd.to_numeric(out["avg_per_trip"], errors="coerce").fillna(0).apply(fmt_vn)
    _daily_table_vehicle_days = pd.to_numeric(out["so_xe"], errors="coerce").fillna(0) if "so_xe" in out.columns else pd.Series(0, index=out.index)
    _daily_table_revenue = pd.to_numeric(out["tong_doanh_thu"], errors="coerce").fillna(0) if "tong_doanh_thu" in out.columns else pd.Series(0, index=out.index)
    out["avg_per_vehicle_day"] = np.where(_daily_table_vehicle_days > 0, _daily_table_revenue / _daily_table_vehicle_days.replace(0, 1), 0)
    out["avg_per_vehicle_day_fmt"] = pd.to_numeric(out["avg_per_vehicle_day"], errors="coerce").fillna(0).apply(fmt_vn)
    out["so_xe_fmt"] = pd.to_numeric(out.get("so_xe", 0), errors="coerce").fillna(0).apply(fmt_vn)
    out["so_tai_xe_fmt"] = pd.to_numeric(out.get("so_tai_xe", 0), errors="coerce").fillna(0).apply(fmt_vn)
    out["sokm_vandoanh_fmt"] = pd.to_numeric(out.get("sokm_vandoanh", 0), errors="coerce").fillna(0).apply(fmt_vn)
    out["sokm_cokhach_fmt"] = pd.to_numeric(out.get("sokm_cokhach", 0), errors="coerce").fillna(0).apply(fmt_vn)
    out["km_co_khach_ratio"] = np.where(
        pd.to_numeric(out.get("sokm_vandoanh", 0), errors="coerce").fillna(0) > 0,
        pd.to_numeric(out.get("sokm_cokhach", 0), errors="coerce").fillna(0) / pd.to_numeric(out.get("sokm_vandoanh", 0), errors="coerce").fillna(0).replace(0, 1) * 100,
        0,
    )
    out["km_co_khach_ratio_fmt"] = pd.to_numeric(out["km_co_khach_ratio"], errors="coerce").fillna(0).apply(lambda x: fmt_pct(x, 1))
    result = out[["ngay_label", "thang_label", "khu_vuc", "tong_doanh_thu_fmt", "tong_so_cuoc_fmt", "avg_per_trip_fmt", "so_xe_fmt", "avg_per_vehicle_day_fmt", "so_tai_xe_fmt", "sokm_vandoanh_fmt", "sokm_cokhach_fmt", "km_co_khach_ratio_fmt"]].copy()
    if cache_key is not None:
        if len(DAILY_TABLE_FRAME_CACHE) > DAILY_TABLE_FRAME_CACHE_MAX:
            DAILY_TABLE_FRAME_CACHE.clear()
        DAILY_TABLE_FRAME_CACHE[cache_key] = result.copy(deep=False)
    return _return_df_cached(result)


def daily_latest_page():
    ensure_daily_data_loaded()
    min_d, max_d = _daily_date_bounds()
    latest_iso = _date_iso(max_d)
    min_iso = _date_iso(min_d)
    default_start_iso = _date_iso(_daily_default_start_date(min_d, max_d))
    hero = executive_header(
        "DOANH THU CẬP NHẬT THEO NGÀY",
        "Theo dõi dữ liệu ngày: doanh thu, số cuốc, xe/tài xế hoạt động, KM vận doanh và KM có khách theo khu vực.",
        right_children=html.Div(id="daily-summary", className="exec-chip-row")
    )

    date_picker = html.Div(
        dcc.DatePickerRange(
            id="daily-date-range",
            start_date=default_start_iso,
            end_date=latest_iso,
            min_date_allowed=min_iso,
            max_date_allowed=latest_iso,
            display_format="DD/MM/YYYY",
            minimum_nights=0,
            clearable=False,
            updatemode="bothdates",
            className="executive-date-picker",
        ),
        className="executive-date-picker"
    )

    filter_row = dbc.Row([
        make_filter_col(
            "Ngày dữ liệu",
            date_picker,
            "daily-date-wrap",
            3,
            "fa-calendar-day",
            "Mặc định mở 30 ngày gần nhất",
        ),
        make_filter_col(
            "Khu vực",
            exec_dropdown(
                id="daily-region",
                options=[{"label": x, "value": x} for x in get_scoped_all_regions()],
                value=[],
                multi=True,
                placeholder="Tất cả khu vực",
                clearable=True,
            ),
            "daily-region-wrap",
            3,
            "fa-map-location-dot",
            "Khoanh vùng doanh thu ngày",
        ),
        make_filter_col(
            "Phân loại xe",
            exec_dropdown(
                id="daily-vehicle-type",
                options=_daily_vehicle_type_options(),
                value=[],
                multi=True,
                placeholder="Tất cả phân loại xe",
                clearable=True,
            ),
            "daily-vehicle-type-wrap",
            3,
            "fa-car-side",
            "Lọc Xe Công ty / thương quyền",
        ),
        make_filter_col(
            "Hình thức KD",
            exec_dropdown(
                id="daily-business-type",
                options=_daily_business_type_options(),
                value=[],
                multi=True,
                placeholder="Tất cả hình thức",
                clearable=True,
            ),
            "daily-business-type-wrap",
            3,
            "fa-charging-station",
            "Điện ăn chia / khoán điện / khoán xăng",
        ),
        make_filter_col(
            "Tài xế",
            exec_dropdown(
                id="daily-driver",
                options=_daily_driver_options(),
                value=[],
                multi=True,
                placeholder="Tất cả tài xế",
                clearable=True,
            ),
            "daily-driver-wrap",
            3,
            "fa-id-card",
            "Lọc riêng theo từng tài xế",
        ),
    ], className="g-3")

    filters = executive_section_panel(
        "Bộ lọc doanh thu ngày",
        "Mặc định mở 30 ngày gần nhất. Bộ lọc riêng của từng tài xế.",
        filter_row,
        right_children=[
            filter_panel_chip("Lọc theo ngày", fa_icon("fa-calendar-day", 12, GREEN_PRIMARY)),
            filter_panel_chip("30 ngày gần nhất", fa_icon("fa-bolt", 12, GREEN_PRIMARY)),
            filter_panel_chip("Lọc phân loại xe", fa_icon("fa-car-side", 12, GREEN_PRIMARY)),
            filter_panel_chip("Lọc theo tài xế", fa_icon("fa-id-card", 12, GREEN_PRIMARY)),
        ],
        class_name="mb-3 executive-control-dock"
    )

    kpis = dbc.Row([
        dbc.Col(make_kpi_card("Doanh thu theo ngày", "daily-kpi1", "daily-kpi1", ICON_MONEY, min_height="230px"), md=3),
        dbc.Col(make_kpi_card("Số cuốc theo ngày", "daily-kpi2", "daily-kpi2", ICON_ROUTE, min_height="230px"), md=3),
        dbc.Col(make_kpi_card("TB / cuốc", "daily-kpi3", "daily-kpi3", ICON_AVG, min_height="230px"), md=3),
        dbc.Col(make_kpi_card("Xe hoạt động", "daily-kpi4", "daily-kpi4", ICON_REGION, min_height="230px"), md=3),
    ], className="g-3 mb-3")

    charts1 = dbc.Row([
        dbc.Col(make_graph_card("daily-main", "daily-main", height="420px"), md=8),
        dbc.Col(make_graph_card("daily-region-donut", "daily-region-donut", height="420px"), md=4),
    ], className="g-3 mb-3")

    charts2 = dbc.Row([
        dbc.Col(make_graph_card("daily-region-bar", "daily-region-bar", height="380px"), md=4),
        dbc.Col(make_graph_card("daily-lh-donut", "daily-lh-donut", height="380px"), md=4),
        dbc.Col(make_graph_card("daily-hd-bar", "daily-hd-bar", height="380px"), md=4),
    ], className="g-3 mb-3")

    table = dbc.Row([
        dbc.Col(
            make_table_card(
                "Bảng chi tiết • doanh thu ngày checker",
                "Tổng hợp theo ngày/khu vực: doanh thu, số cuốc, xe/tài xế hoạt động, KM vận doanh, KM có khách và hiệu suất KM.",
                dash_table.DataTable(
                    id="daily-table",
                    columns=_daily_table_columns(),
                    page_size=12,
                    sort_action="native",
                    filter_action="none",
                    cell_selectable=True,
                    fixed_rows={"headers": True},
                    style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "560px", "borderRadius": "18px", "border": "1px solid #dbe7f3"},
                    style_header={"backgroundColor": "#0f172a", "color": "#ffffff", "fontWeight": "700", "textAlign": "center", "padding": "12px 10px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.25", "fontSize": "12px"},
                    style_cell={"backgroundColor": "#ffffff", "color": "#0f172a", "textAlign": "center", "padding": "11px 10px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.35", "fontSize": "12.5px", "fontWeight": "500", "border": "1px solid #e5edf5"},
                    style_data_conditional=[
                        {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
                        {"if": {"state": "active"}, "backgroundColor": "#ecfdf5", "border": "1px solid #22c55e"},
                        {"if": {"state": "selected"}, "backgroundColor": "#dcfce7", "border": "1px solid #22c55e"},
                    ],
                )
            ),
            md=12
        )
    ])

    return dbc.Container(fluid=True, children=[hero, filters, kpis, charts1, charts2, table])


def _detail_table_columns(prefix: str):
    cfg = get_menu_config(prefix)
    df_src = cfg.get("df", pd.DataFrame()) if isinstance(cfg, dict) else pd.DataFrame()
    available = set(df_src.columns) if isinstance(df_src, pd.DataFrame) else set()

    label_map = {
        "thang_nam": "Tháng",
        "thang_nam_vn": "Tháng dữ liệu",
        "thang_label": "Tháng",
        "nam": "Năm",
        "khu_vuc": "Khu vực",
        "tong_doanh_thu": "Tổng doanh thu",
        "tong_so_cuoc": "Tổng số cuốc",
        "avg_per_trip": "TB / cuốc",
        "avg_per_trip_fmt": "TB / cuốc",
        "top_region": "Khu vực dẫn đầu",
        "loai_hinh_std": "Loại hình hợp tác",
        "loaihinh_hoptac": "Loại hình hợp tác",
        "loai_hinh": "Loại hình",
        "loai_hop_dong_std": "Loại hợp đồng",
        "loai_hopdong": "Loại hợp đồng",
        "loai_hop_dong": "Loại hợp đồng",
        "bo_phan": "Bộ phận",
        "so_luong_nhan_su": "Số lượng nhân sự",
        "so_vao_lam": "Vào làm",
        "so_nghi_viec": "Nghỉ việc",
        "net_flow": "Biến động thuần",
        "so_duoi_1_nam": "Dưới 1 năm",
        "so_tu_1_den_3_nam": "Từ 1 đến 3 năm",
        "so_tren_3_nam": "Trên 3 năm",
        "headcount_dau_ky": "Nhân sự đầu kỳ",
        "so_giu_on_dinh": "Giữ ổn định",
        "bien_dong_thuan": "Biến động thuần",
        "ty_le_tang": "Tỷ lệ tăng",
        "ty_le_giam": "Tỷ lệ giảm",
        "ty_le_giu_chan": "Tỷ lệ giữ chân",
        "chi_phi": "Chi phí",
        "tong_phai_chi": "Tổng phải chi",
        "so_diem_tiep_thi": "Số điểm tiếp thị",
        "chi_phi_binh_quan_moi_diem": "Chi phí bình quân / điểm",
        "so_ho_so_hoa_hong": "Số hồ sơ hoa hồng",
        "tong_da_chi_du": "Tổng đã chi đủ",
        "tong_chua_chi_du": "Tổng chưa chi đủ",
        "tong_khong_chi": "Tổng không chi",
        "so_ho_so_da_chi_du": "Hồ sơ đã chi đủ",
        "so_ho_so_chua_chi_du": "Hồ sơ chưa chi đủ",
        "so_ho_so_khong_chi": "Hồ sơ không chi",
        "chi_phi_binh_quan_moi_ho_so": "Chi phí bình quân / hồ sơ",
        "so_diem_moi_ky_hd": "Điểm mới / kỳ HĐ",
        "so_loai_hinh_kd": "Số loại hình KD",
        "tong_tien_de_xuat": "Tổng tiền đề xuất",
        "so_tien_thu_duoc": "Số tiền đã xử lý",
        "so_tien_da_xu_ly": "Số tiền biên bản ghi nhận",
        "so_tien_con_no": "Số tiền chênh lệch",
        "so_bien_ban": "Số biên bản",
        "so_bien_ban_da_xu_ly": "Biên bản đã xử lý",
        "so_bien_ban_thu_hoan_tat": "Biên bản thu hoàn tất",
        "loai_xe": "Loại xe",
        "nhom_nhien_lieu": "Nhóm nhiên liệu",
        "so_luong_xe": "Số lượng xe",
        "tong_so_cho": "Tổng số chỗ",
        "so_cho_binh_quan_xe": "Số chỗ bình quân / xe",
        "so_cho_loc": "Số chỗ",
        "nhan_so_cho": "Nhãn số chỗ",
        "so_bien_kiem_soat": "Số biển kiểm soát",
        "so_so_tai": "Số sổ tài",
        "metric_fmt": "Giá trị",
        "label": "Nhãn",
        "pct": "Tỷ trọng",
        "pct_fmt": "Tỷ trọng",
        "value_fmt": "Giá trị",
    }

    def _vn_label(col):
        col = str(col)
        if col in label_map:
            return label_map[col]
        cleaned = col.replace("_fmt", "").replace("_std", "")
        words = cleaned.split("_")
        replacements = {
            "thang": "Tháng", "nam": "Năm", "khu": "Khu", "vuc": "vực",
            "tong": "Tổng", "doanh": "doanh", "thu": "thu", "cuoc": "cuốc",
            "so": "Số", "luong": "lượng", "nhan": "nhân", "su": "sự",
            "tai": "tài", "xe": "xe", "hop": "hợp", "dong": "đồng",
            "loai": "loại", "hinh": "hình", "chi": "chi", "phi": "phí",
            "binh": "bình", "quan": "quân", "diem": "điểm", "tiep": "tiếp", "thi": "thị",
            "tien": "tiền", "de": "đề", "xuat": "xuất", "xu": "xử", "ly": "lý",
            "con": "còn", "no": "nợ", "bien": "biên", "ban": "bản",
            "phan": "phân", "quyen": "quyền", "truc": "trực", "thuoc": "thuộc",
            "nhien": "nhiên", "lieu": "liệu", "kiem": "kiểm", "soat": "soát",
            "giu": "giữ", "chan": "chân", "tang": "tăng", "giam": "giảm",
            "duoi": "dưới", "tren": "trên", "tu": "từ", "den": "đến",
        }
        return " ".join(replacements.get(w, w) for w in words).strip().capitalize()

    def _cols(preferred):
        return [{"name": _vn_label(col), "id": col} for col in preferred if col in available]

    common = ["thang_label", "nam", "khu_vuc"]
    if prefix == "dt":
        cols = _cols(common + ["tong_doanh_thu", "tong_so_cuoc"])
        if cols:
            return cols
    if prefix == "lh":
        cols = _cols(common + ["loai_hinh_std", "loaihinh_hoptac", "tong_doanh_thu", "tong_so_cuoc"])
        if cols:
            return cols
    if prefix == "hd":
        cols = _cols(common + ["loai_hop_dong_std", "loai_hopdong", "tong_doanh_thu", "tong_so_cuoc"])
        if cols:
            return cols
    if prefix in HR_MENU_PREFIXES:
        preferred = [
            "thang_nam", "khu_vuc", "bo_phan",
            "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "net_flow",
            "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam",
            "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
            "ty_le_tang", "ty_le_giam", "ty_le_giu_chan",
        ]
        cols = [{"name": _vn_label(col), "id": col} for col in preferred if (col in available or col == "net_flow")]
        if cols:
            return cols
    if prefix == "mkt":
        preferred = [
            "thang_label", "nam", "khu_vuc", "tong_phai_chi", "so_diem_tiep_thi",
            "chi_phi_binh_quan_moi_diem", "so_ho_so_hoa_hong",
            "tong_da_chi_du", "tong_chua_chi_du", "tong_khong_chi",
            "so_ho_so_da_chi_du", "so_ho_so_chua_chi_du", "so_ho_so_khong_chi",
            "chi_phi_binh_quan_moi_ho_so", "so_diem_moi_ky_hd", "so_loai_hinh_kd",
        ]
        cols = _cols(preferred)
        if cols:
            return cols
    if prefix == "bb":
        preferred = [
            "thang_nam", "khu_vuc", "so_bien_ban",
            "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
            "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no",
        ]
        cols = _cols(preferred)
        if cols:
            return cols
    if prefix in {"xdt", "xpq"}:
        preferred = [
            "khu_vuc", "loai_xe", "nhom_nhien_lieu", "so_luong_xe",
            "so_bien_kiem_soat", "so_so_tai",
        ]
        cols = _cols(preferred)
        if cols:
            return cols

    fallback = []
    for col in (list(df_src.columns) if isinstance(df_src, pd.DataFrame) else []):
        if str(col) == "metric":
            continue
        fallback.append({"name": _vn_label(col), "id": col})
        if len(fallback) >= 14:
            break
    return fallback


def _detail_table_props(prefix: str):
    cols = _detail_table_columns(prefix)
    text_cols = {
        "khu_vuc", "loai_xe", "nhom_nhien_lieu", "bo_phan", "loai_hinh_std",
        "loaihinh_hoptac", "loai_hop_dong_std", "loai_hopdong", "top_region",
    }
    wide_cols = {
        "khu_vuc", "bo_phan", "loai_xe", "loai_hinh_std", "loaihinh_hoptac",
        "loai_hop_dong_std", "loai_hopdong", "top_region",
    }
    money_cols = {
        "tong_doanh_thu", "tong_phai_chi", "chi_phi_binh_quan_moi_diem",
        "tong_da_chi_du", "tong_chua_chi_du", "tong_khong_chi",
        "chi_phi_binh_quan_moi_ho_so", "tong_tien_de_xuat",
        "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no",
    }

    style_cell_conditional = []
    for col in [c["id"] for c in cols if c.get("id") in text_cols]:
        style_cell_conditional.append({
            "if": {"column_id": col},
            "textAlign": "left",
            "minWidth": "170px" if col in wide_cols else "130px",
            "width": "190px" if col in wide_cols else "140px",
            "maxWidth": "260px" if col in wide_cols else "190px",
        })
    for col in [c["id"] for c in cols if c.get("id") in money_cols]:
        style_cell_conditional.append({
            "if": {"column_id": col},
            "textAlign": "right",
            "minWidth": "138px",
            "width": "150px",
            "maxWidth": "180px",
            "fontVariantNumeric": "tabular-nums",
        })
    for col in [c["id"] for c in cols if c.get("id") in {"thang_nam", "thang_label", "nam"}]:
        style_cell_conditional.append({
            "if": {"column_id": col},
            "minWidth": "92px",
            "width": "104px",
            "maxWidth": "118px",
            "fontWeight": "800",
        })

    tooltip_header = {c["id"]: c["name"] for c in cols}
    return {
        "columns": cols,
        "tooltip_header": tooltip_header,
        "tooltip_delay": 0,
        "tooltip_duration": None,
        "sort_action": "native",
        "filter_action": "none",
        "cell_selectable": True,
        "fixed_rows": {"headers": True},
        "style_table": {
            "overflowX": "auto",
            "overflowY": "auto",
            "maxWidth": "100%",
            "minWidth": "100%",
            "maxHeight": "560px",
            "borderRadius": "18px",
            "border": "1px solid #dbe7f3",
            "boxShadow": "0 16px 34px rgba(15,23,42,0.07)",
        },
        "style_cell_conditional": style_cell_conditional,
        "style_data_conditional": [
            {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
            {"if": {"state": "selected"}, "backgroundColor": "#dcfce7", "border": "1px solid #22c55e"},
            {"if": {"state": "active"}, "backgroundColor": "#ecfdf5", "border": "1px solid #22c55e"},
        ],
        "css": [
            {"selector": ".dash-spreadsheet-container", "rule": "border-radius:18px; overflow:hidden;"},
            {"selector": ".dash-spreadsheet-inner table", "rule": "border-collapse:separate !important; border-spacing:0;"},
            {"selector": "th", "rule": "letter-spacing:.2px;"},
            {"selector": "td", "rule": "transition: background-color .16s ease;"},
        ],
    }


def _detail_table_theme_styles(theme: str, prefix: str):
    if theme == "light":
        style_cell = {
            "backgroundColor": "#ffffff",
            "color": "#0f172a",
            "textAlign": "center",
            "padding": "11px 10px",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.35",
            "fontSize": "12.5px",
            "fontWeight": "500",
            "fontFamily": FONT_UI_FAMILY,
            "border": "1px solid #e5edf5",
            "minWidth": "108px",
            "width": "124px",
            "maxWidth": "210px",
        }
        style_header = {
            "backgroundColor": "#0f172a",
            "color": "#ffffff",
            "fontWeight": "700",
            "textAlign": "center",
            "padding": "12px 10px",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.25",
            "fontSize": "12px",
            "fontFamily": FONT_UI_FAMILY,
            "border": "1px solid #1e293b",
            "position": "sticky",
            "top": 0,
            "zIndex": 2,
        }
    else:
        style_cell = {
            "backgroundColor": DARK_BG,
            "color": "white",
            "textAlign": "center",
            "padding": "11px 10px",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.35",
            "fontSize": "12.5px",
            "fontWeight": "500",
            "fontFamily": FONT_UI_FAMILY,
            "border": "1px solid #334155",
            "minWidth": "108px",
            "width": "124px",
            "maxWidth": "210px",
        }
        style_header = {
            "backgroundColor": "#020617",
            "color": "white",
            "fontWeight": "700",
            "textAlign": "center",
            "padding": "12px 10px",
            "whiteSpace": "normal",
            "height": "auto",
            "lineHeight": "1.25",
            "fontSize": "12px",
            "fontFamily": FONT_UI_FAMILY,
            "border": "1px solid #334155",
            "position": "sticky",
            "top": 0,
            "zIndex": 2,
        }
    return style_cell, style_header


def _fleet_filter_text(dims=None, type_filter=None, seat_filter=None):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    type_filter = type_filter if isinstance(type_filter, list) else ([type_filter] if type_filter else [])
    seat_filter = seat_filter if isinstance(seat_filter, list) else ([seat_filter] if seat_filter else [])
    dims_show = ", ".join([str(x) for x in dims[:3]]) if dims else ("Phạm vi tài khoản" if current_user_region_scope() is not None else "Toàn bộ khu vực")
    if dims and len(dims) > 3:
        dims_show = f"{len(dims)} khu vực đã chọn"
    tf_txt = f" • Lọc loại xe: {', '.join(type_filter)}" if type_filter else ""
    if seat_filter:
        seat_labels = [f"{int(float(x))} chỗ" for x in seat_filter if str(x) not in ["", "None"]]
        if seat_labels:
            tf_txt += f" • Số chỗ: {', '.join(seat_labels)}"
    return dims_show, tf_txt


def _latest_fleet_snapshot_df(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return dff.copy() if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if "thang_nam_vn" not in dff.columns:
        return dff.copy()
    months = _coerce_month_start(dff["thang_nam_vn"])
    valid_months = months.dropna()
    if valid_months.empty:
        return dff.copy()
    latest_month = valid_months.max()
    out = dff.loc[months == latest_month].copy()
    return out if not out.empty else dff.copy()


def _fleet_snapshot_period_text(dff: pd.DataFrame) -> str:
    try:
        if dff is None or dff.empty or "thang_nam_vn" not in dff.columns:
            return "Snapshot hiện tại"
        months = _coerce_month_start(dff["thang_nam_vn"]).dropna()
        if months.empty:
            return "Snapshot hiện tại"
        return f"Snapshot kỳ {pd.Timestamp(months.max()).strftime('%m/%Y')}"
    except Exception:
        return "Snapshot hiện tại"


def _fleet_table_frame(dff: pd.DataFrame) -> pd.DataFrame:
    cols = ["khu_vuc", "loai_xe", "nhom_nhien_lieu", "so_luong_xe", "so_bien_kiem_soat", "so_so_tai"]
    if dff is None or dff.empty:
        return pd.DataFrame(columns=cols)
    out = dff.groupby([c for c in ["khu_vuc", "loai_xe", "nhom_nhien_lieu"] if c in dff.columns], as_index=False).agg(
        so_luong_xe=("so_luong_xe", "sum"),
        so_bien_kiem_soat=("so_bien_kiem_soat", "sum"),
        so_so_tai=("so_so_tai", "sum"),
    )
    out = out.sort_values([c for c in ["khu_vuc", "so_luong_xe", "so_bien_kiem_soat"] if c in out.columns], ascending=[True, False, False][:len([c for c in ["khu_vuc", "so_luong_xe", "so_bien_kiem_soat"] if c in out.columns])]).reset_index(drop=True)
    return out[[c for c in cols if c in out.columns]].copy()


def _fleet_region_snapshot(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame(columns=["khu_vuc", "so_luong_xe", "so_bien_kiem_soat", "so_so_tai", "so_loai_xe", "ty_trong_xe", "xe_fmt", "bks_fmt", "so_tai_fmt", "ty_trong_fmt"])
    g = dff.groupby("khu_vuc", as_index=False).agg(
        so_luong_xe=("so_luong_xe", "sum"),
        so_bien_kiem_soat=("so_bien_kiem_soat", "sum"),
        so_so_tai=("so_so_tai", "sum"),
        so_loai_xe=("loai_xe", "nunique"),
    ).sort_values(["so_luong_xe", "so_loai_xe"], ascending=[False, False]).reset_index(drop=True)
    total = float(pd.to_numeric(g["so_luong_xe"], errors="coerce").fillna(0).sum())
    g["ty_trong_xe"] = np.where(total > 0, g["so_luong_xe"] / total * 100.0, 0.0)
    g["xe_fmt"] = g["so_luong_xe"].apply(fmt_vn)
    g["bks_fmt"] = g["so_bien_kiem_soat"].apply(fmt_vn)
    g["so_tai_fmt"] = g["so_so_tai"].apply(fmt_vn)
    g["ty_trong_fmt"] = g["ty_trong_xe"].apply(lambda x: fmt_pct(x, 1))
    return g


def _fleet_type_snapshot(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame(columns=["loai_xe", "so_luong_xe", "so_bien_kiem_soat", "so_so_tai", "so_khu_vuc", "ty_trong_xe", "xe_fmt", "bks_fmt", "so_tai_fmt", "ty_trong_fmt"])
    g = dff.groupby("loai_xe", as_index=False).agg(
        so_luong_xe=("so_luong_xe", "sum"),
        so_bien_kiem_soat=("so_bien_kiem_soat", "sum"),
        so_so_tai=("so_so_tai", "sum"),
        so_khu_vuc=("khu_vuc", "nunique"),
    ).sort_values(["so_luong_xe", "so_khu_vuc"], ascending=[False, False]).reset_index(drop=True)
    total = float(pd.to_numeric(g["so_luong_xe"], errors="coerce").fillna(0).sum())
    g["ty_trong_xe"] = np.where(total > 0, g["so_luong_xe"] / total * 100.0, 0.0)
    g["xe_fmt"] = g["so_luong_xe"].apply(fmt_vn)
    g["bks_fmt"] = g["so_bien_kiem_soat"].apply(fmt_vn)
    g["so_tai_fmt"] = g["so_so_tai"].apply(fmt_vn)
    g["ty_trong_fmt"] = g["ty_trong_xe"].apply(lambda x: fmt_pct(x, 1))
    return g


def _fleet_region_type_snapshot(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame(columns=["khu_vuc", "loai_xe", "so_luong_xe", "xe_fmt"])
    g = dff.groupby([c for c in ["khu_vuc", "loai_xe"] if c in dff.columns], as_index=False).agg(
        so_luong_xe=("so_luong_xe", "sum"),
        so_bien_kiem_soat=("so_bien_kiem_soat", "sum"),
        so_so_tai=("so_so_tai", "sum"),
    ).sort_values("so_luong_xe", ascending=False).reset_index(drop=True)
    g["xe_fmt"] = g["so_luong_xe"].apply(fmt_vn)
    return g


def _fleet_kpi_lines_region(region_df: pd.DataFrame, max_lines: int = 4, unit: str = "xe"):
    if region_df is None or region_df.empty:
        return []
    lines = []
    for _, r in region_df.head(max_lines).iterrows():
        color = REGION_COLOR_MAP.get(str(r.get("khu_vuc", "Khác")), "#888")
        lines.append(_ellipsis_div([
            _swatch(color),
            f"{r.get('khu_vuc', '')}: {r.get('xe_fmt', '0')} {unit}",
            html.Span(f" • {r.get('ty_trong_fmt', '0%')}", style={"opacity": 0.75}),
        ]))
    return lines


def _fleet_kpi_lines_type(type_df: pd.DataFrame, max_lines: int = 4, unit: str = "xe"):
    if type_df is None or type_df.empty:
        return []
    lines = []
    palette = px.colors.qualitative.Set2 + px.colors.qualitative.Bold
    for i, (_, r) in enumerate(type_df.head(max_lines).iterrows()):
        color = palette[i % len(palette)]
        lines.append(_ellipsis_div([
            _swatch(color),
            f"{r.get('loai_xe', '')}: {r.get('xe_fmt', '0')} {unit}",
            html.Span(f" • {r.get('ty_trong_fmt', '0%')}", style={"opacity": 0.75}),
        ]))
    return lines


def page_1(prefix, title=None):
    ensure_menu_data_loaded(prefix)
    cfg = get_menu_config(prefix)
    title = title or cfg["page1_title"]
    if prefix in FLEET_MENU_PREFIXES:
        filter_row = dbc.Row([
            _build_type_filter(prefix, "p1"),
            _build_fleet_seat_filter(prefix, "p1"),
        ], className="g-3")
    elif prefix in HR_MENU_PREFIXES:
        filter_row = dbc.Row([
            make_filter_col(
                "Năm",
                exec_dropdown(
                    id=f"{prefix}-year",
                    options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                    value=DEFAULT_YEAR,
                    multi=False,
                    placeholder="Chọn niên độ báo cáo",
                    clearable=True,
                ),
                f"{prefix}-year-wrap",
                3,
                "fa-calendar-days",
                "Niên độ tổng hợp toàn tập đoàn",
            ),
            make_filter_col(
                "Tháng",
                exec_dropdown(
                    id=f"{prefix}-month",
                    options=[{"label": m, "value": m} for m in MONTH_OPTIONS_BY_YEAR.get(DEFAULT_YEAR, MONTH_OPTIONS_ALL)],
                    multi=True,
                    placeholder="Chọn một hoặc nhiều tháng",
                    clearable=True,
                ),
                f"{prefix}-month-wrap",
                3,
                "fa-calendar",
                "Khoảng thời gian cần theo dõi",
            ),
            make_filter_col(
                "Khu vực",
                exec_dropdown(
                    id=f"{prefix}-region",
                    options=[{"label": x, "value": x} for x in get_scoped_regions_from_df(cfg["df"])],
                    multi=True,
                    placeholder="Chọn khu vực cần phân tích",
                    clearable=True,
                ),
                f"{prefix}-region-wrap",
                3,
                "fa-map-location-dot",
                "Lọc riêng theo khu vực",
            ),
            _build_type_filter(prefix, "p1"),
        ], className="g-3")
    else:
        filter_row = dbc.Row([
            make_filter_col(
                "Năm",
                exec_dropdown(
                    id=f"{prefix}-year",
                    options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                    value=DEFAULT_YEAR,
                    multi=False,
                    placeholder="Chọn niên độ báo cáo",
                    clearable=True,
                ),
                f"{prefix}-year-wrap",
                3,
                "fa-calendar-days",
                "Niên độ tổng hợp toàn tập đoàn",
            ),
            make_filter_col(
                "Tháng",
                exec_dropdown(
                    id=f"{prefix}-month",
                    options=[{"label": m, "value": m} for m in MONTH_OPTIONS_BY_YEAR.get(DEFAULT_YEAR, MONTH_OPTIONS_ALL)],
                    multi=True,
                    placeholder="Chọn một hoặc nhiều tháng",
                    clearable=True,
                ),
                f"{prefix}-month-wrap",
                5,
                "fa-calendar",
                "Khoảng thời gian cần theo dõi",
            ),
            _build_type_filter(prefix, "p1"),
            *([_build_lh_business_filter("p1")] if prefix == "lh" else []),
        ], className="g-3")

    filters_panel = executive_section_panel(
        "Điều kiện lọc trang 1",
        f"Chế độ tổng hợp toàn tập đoàn cho menu {cfg['menu_label']}. Bộ lọc phân cấp, đồng bộ tức thời với KPI và biểu đồ.",
        filter_row,
        right_children=[
            filter_panel_chip("Page 1 • Tổng quan", fa_icon("fa-gauge-high", 12, GREEN_PRIMARY)),
            filter_panel_chip("Zoom / export sẵn sàng", fa_icon("fa-magnifying-glass-chart", 12, GREEN_PRIMARY)),
        ],
        class_name="mb-3 executive-control-dock"
    )

    return dbc.Container(fluid=True, children=[
        page_title_block(title, f"Trang tổng hợp toàn tập đoàn cho menu {cfg['menu_label']} với KPI, xu hướng, cơ cấu và khả năng zoom chi tiết từng biểu đồ."),
        filters_panel,
        dbc.Row([
            dbc.Col(make_kpi_card(f"Tổng {cfg['metric_label']}", f"{prefix}-p1-kpi1", f"{prefix}-p1-kpi1", cfg["icon"]), md=4),
            dbc.Col(make_kpi_card(cfg["secondary_label"], f"{prefix}-p1-kpi2", f"{prefix}-p1-kpi2", ICON_ROUTE), md=4),
            dbc.Col(make_kpi_card(cfg["avg_label"], f"{prefix}-p1-kpi3", f"{prefix}-p1-kpi3", ICON_AVG), md=4),
        ], className="mb-3 g-3"),
        dbc.Row([
            dbc.Col(make_graph_card(f"{prefix}-p1-line-kv", f"{prefix}-p1-line-kv", height="430px"), md=12),
        ], className="mb-3 g-3"),
        dbc.Row([
            dbc.Col(make_graph_card(f"{prefix}-p1-line", f"{prefix}-p1-line", height="390px"), md=6),
            dbc.Col(make_graph_card(f"{prefix}-p1-bar", f"{prefix}-p1-bar", height="390px"), md=6),
        ], className="mb-3 g-3"),
        dbc.Row([
            dbc.Col(make_graph_card(f"{prefix}-p1-pie", f"{prefix}-p1-pie", height="390px"), md=6),
        ], className="mb-3 g-3"),
    ])


def page_2(prefix, title=None, df=None, dim="khu_vuc"):
    ensure_menu_data_loaded(prefix)
    cfg = get_menu_config(prefix)
    df = apply_region_scope_to_df(df if df is not None else cfg["df"])
    title = title or cfg["page2_title"]
    dim_values = sorted(df[dim].astype(str).dropna().unique().tolist()) if dim in df.columns else []

    if prefix in FLEET_MENU_PREFIXES:
        filter_row = dbc.Row([
            make_filter_col(
                "Khu vực",
                exec_dropdown(
                    id=f"{prefix}-dim",
                    options=[{"label": x, "value": x} for x in dim_values],
                    value=dim_values[:1],
                    multi=True,
                    placeholder="Chọn khu vực theo dõi",
                    clearable=True,
                ),
                f"{prefix}-dim-wrap",
                4,
                "fa-map-location-dot",
                "Khoanh vùng phân tích địa bàn",
            ),
            _build_type_filter(prefix, "p2"),
            _build_fleet_seat_filter(prefix, "p2"),
        ], className="g-3")
    elif prefix in HR_MENU_PREFIXES:
        filter_row = dbc.Row([
            make_filter_col(
                "Năm",
                exec_dropdown(
                    id=f"{prefix}-year-p2",
                    options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                    value=DEFAULT_YEAR,
                    multi=False,
                    placeholder="Chọn niên độ báo cáo",
                    clearable=True,
                ),
                f"{prefix}-year-p2-wrap",
                3,
                "fa-calendar-days",
                "Niên độ của khu vực đang xem",
            ),
            make_filter_col(
                "Tháng",
                exec_dropdown(
                    id=f"{prefix}-month-p2",
                    options=[{"label": m, "value": m} for m in MONTH_OPTIONS_BY_YEAR.get(DEFAULT_YEAR, MONTH_OPTIONS_ALL)],
                    multi=True,
                    placeholder="Chọn một hoặc nhiều tháng",
                    clearable=True,
                ),
                f"{prefix}-month-p2-wrap",
                3,
                "fa-calendar",
                "Chu kỳ cần so sánh chi tiết",
            ),
            make_filter_col(
                "Khu vực",
                exec_dropdown(
                    id=f"{prefix}-dim",
                    options=[{"label": x, "value": x} for x in dim_values],
                    value=None,
                    multi=True,
                    placeholder="Chọn khu vực theo dõi",
                    clearable=True,
                ),
                f"{prefix}-dim-wrap",
                4,
                "fa-map-location-dot",
                "Khoanh vùng phân tích địa bàn",
            ),
            _build_type_filter(prefix, "p2"),
        ], className="g-3")
    else:
        filter_row = dbc.Row([
            make_filter_col(
                "Khu vực",
                exec_dropdown(
                    id=f"{prefix}-dim",
                    options=[{"label": x, "value": x} for x in dim_values],
                    value=dim_values[:1],
                    multi=True,
                    placeholder="Chọn khu vực theo dõi",
                    clearable=True,
                ),
                f"{prefix}-dim-wrap",
                3,
                "fa-map-location-dot",
                "Khoanh vùng phân tích địa bàn",
            ),
            make_filter_col(
                "Năm",
                exec_dropdown(
                    id=f"{prefix}-year-p2",
                    options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                    value=DEFAULT_YEAR,
                    multi=False,
                    placeholder="Chọn niên độ báo cáo",
                    clearable=True,
                ),
                f"{prefix}-year-p2-wrap",
                3,
                "fa-calendar-days",
                "Niên độ của khu vực đang xem",
            ),
            make_filter_col(
                "Tháng",
                exec_dropdown(
                    id=f"{prefix}-month-p2",
                    options=[{"label": m, "value": m} for m in MONTH_OPTIONS_BY_YEAR.get(DEFAULT_YEAR, MONTH_OPTIONS_ALL)],
                    multi=True,
                    placeholder="Chọn một hoặc nhiều tháng",
                    clearable=True,
                ),
                f"{prefix}-month-p2-wrap",
                4,
                "fa-calendar",
                "Chu kỳ cần so sánh chi tiết",
            ),
            _build_type_filter(prefix, "p2"),
            *([_build_lh_business_filter("p2")] if prefix == "lh" else []),
        ], className="g-3")

    filters_panel = executive_section_panel(
        "Điều kiện lọc trang 2",
        f"Phân tích theo khu vực cho menu {cfg['menu_label']}. Dùng bộ lọc để so sánh địa bàn, kỳ báo cáo và nhóm nghiệp vụ trên cùng một layout executive.",
        filter_row,
        right_children=[
            filter_panel_chip("Page 2 • Khu vực", fa_icon("fa-map", 12, GREEN_PRIMARY)),
            filter_panel_chip("So sánh đa tầng", fa_icon("fa-code-compare", 12, GREEN_PRIMARY)),
        ],
        class_name="mb-3 executive-control-dock"
    )

    return dbc.Container(fluid=True, children=[
        page_title_block(title, f"Phân tích theo khu vực cho menu {cfg['menu_label']} với khả năng so sánh, lọc chi tiết và xem bảng dữ liệu ngay trong dashboard."),
        html.Div(id=f"{prefix}-insight", className="text-center mb-3", style={"fontSize":"18px","fontWeight":"bold", "color": TEXT_LIGHT_UI}),
        filters_panel,
        dbc.Row([
            dbc.Col(make_kpi_card(f"Tổng {cfg['metric_label']}", f"{prefix}-kpi1", f"{prefix}-kpi1", cfg["icon"]), md=4),
            dbc.Col(make_kpi_card(cfg["secondary_label"], f"{prefix}-kpi2", f"{prefix}-kpi2", ICON_ROUTE), md=4),
            dbc.Col(make_kpi_card(cfg["avg_label"], f"{prefix}-kpi3", f"{prefix}-kpi3", ICON_AVG), md=4),
        ], className="mb-3 g-3"),
        dbc.Row([
            dbc.Col(make_graph_card(f"{prefix}-p2-line", f"{prefix}-p2-line", height="390px"), md=6),
            dbc.Col(make_graph_card(f"{prefix}-p2-bar", f"{prefix}-p2-bar", height="390px"), md=6),
        ], className="mb-3 g-3"),
        dbc.Row([
            dbc.Col(make_graph_card(f"{prefix}-p2-pie", f"{prefix}-p2-pie", height="390px"), md=6),
        ], className="mb-3 g-3"),
        dbc.Row([
            dbc.Col(
                make_table_card(
                    "Dữ liệu chi tiết",
                    "Bảng dữ liệu sau lọc để đối chiếu nhanh với biểu đồ.",
                    dash_table.DataTable(
                        id=f"{prefix}-table",
                        page_action=("none" if prefix in ["lh", "hd"] else "native"),
                        page_size=12,
                        style_header=_detail_table_theme_styles("light", prefix)[1],
                        style_cell=_detail_table_theme_styles("light", prefix)[0],
                        **_detail_table_props(prefix)
                    )
                ),
                md=12
            )
        ])
    ])

def ai_badge(text: str, variant: str = "soft"):
    return html.Span(text, className=f"ai-mini-badge {variant}")


def ai_empty_state(title: str = "AI Copilot sẵn sàng", subtitle: str = "Hãy nhập câu hỏi hoặc chọn một gợi ý nhanh ở phía trên. AI trả lời độc lập, không bám theo page hoặc bộ lọc hiện tại."):
    return html.Div(
        [
            html.Div(fa_icon("fa-robot", 22, "#ffffff"), className="ai-empty-icon"),
            html.Div(title, className="ai-empty-title"),
            html.Div(subtitle, className="ai-empty-text"),
        ],
        className="ai-empty-state"
    )


def _ai_menu_label(menu: str) -> str:
    if menu == "home":
        return "Home overview"
    try:
        return get_menu_config(menu).get("menu_label", str(menu).upper())
    except Exception:
        return str(menu).upper()


def ai_context_tags(context: dict | None):
    context = context or {}
    filters = context.get("filters") or {}
    menu = context.get("menu")
    page = context.get("page")
    tags = []
    if menu:
        tags.append(_ai_menu_label(menu))
    if menu == "home":
        tags.append("Landing page")
    elif page in [1, 2]:
        tags.append(f"Page {page}")

    year_val = filters.get("year") or filters.get("year_p2")
    if year_val is not None and str(year_val) != "":
        tags.append(f"Năm {year_val}")

    months = filters.get("months") or filters.get("months_p2") or []
    if isinstance(months, str):
        months = [months]
    if months:
        tags.append(months[0] if len(months) == 1 else f"{len(months)} tháng")

    dims = filters.get("dims") or filters.get("dim") or []
    if isinstance(dims, str):
        dims = [dims]
    if dims:
        tags.append(dims[0] if len(dims) == 1 else f"{len(dims)} khu vực")

    type_filter = filters.get("type_filter") or filters.get("type") or []
    if isinstance(type_filter, str):
        type_filter = [type_filter]
    if type_filter:
        tags.append(type_filter[0] if len(type_filter) == 1 else f"{len(type_filter)} nhóm lọc")

    seat_filter = filters.get("seat_filter") or []
    if isinstance(seat_filter, (str, int, float)):
        seat_filter = [seat_filter]
    if seat_filter:
        seat_first = seat_filter[0]
        try:
            tags.append(f"{int(float(seat_first))} chỗ" if len(seat_filter) == 1 else f"{len(seat_filter)} mức chỗ")
        except Exception:
            tags.append("Lọc số chỗ")

    return tags[:5]


def format_ai_time(ts: str | None) -> str:
    try:
        return pd.to_datetime(ts).strftime("%H:%M")
    except Exception:
        return ""


def render_ai_thread(history):
    history = history or []
    if not history:
        return ai_empty_state()

    bubbles = []
    recent_history = list(history[-6:])[::-1]
    for idx, item in enumerate(recent_history):
        ts_text = format_ai_time(item.get("ts"))
        source = item.get("source", "typed")
        question = item.get("q", "")
        answer = item.get("a", "")
        context_tags_list = item.get("context_tags") or []

        user_meta = []
        if source == "chip":
            user_meta.append(ai_badge("Quick prompt", "accent"))
        elif source == "batch":
            user_meta.append(ai_badge("Batch question", "accent"))
        else:
            user_meta.append(ai_badge("Manual input", "soft"))

        bubbles.append(
            html.Div(
                [
                    html.Div(fa_icon("fa-user", 15, "#ffffff"), className="ai-avatar"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Bạn", className="ai-role"),
                                    html.Span(ts_text, className="ai-time"),
                                ],
                                className="ai-bubble-head"
                            ),
                            html.Div(question, className="ai-bubble-body"),
                            html.Div(user_meta, className="ai-meta-row"),
                        ],
                        className="ai-bubble"
                    )
                ],
                className="ai-row user"
            )
        )

        bot_badges = [ai_badge("Mới nhất" if idx == 0 else "Đã phân tích", "accent")]
        for tag in context_tags_list:
            bot_badges.append(ai_badge(tag, "soft"))

        bubbles.append(
            html.Div(
                [
                    html.Div(fa_icon("fa-sparkles", 15, "#ffffff"), className="ai-avatar"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("AI Copilot", className="ai-role"),
                                    html.Span(ts_text, className="ai-time"),
                                ],
                                className="ai-bubble-head"
                            ),
                            dcc.Markdown(answer, link_target="_blank", className="ai-bubble-body"),
                            html.Div(bot_badges, className="ai-meta-row"),
                        ],
                        className="ai-bubble"
                    )
                ],
                className=("ai-row bot latest" if idx == 0 else "ai-row bot")
            )
        )

    return html.Div(bubbles, className="ai-thread")


AI_SUGGESTIONS_V3 = [
    "Cà Mau tháng nào có doanh thu cao nhất năm 2025",
    "Top 3 tháng doanh thu cao nhất của Cà Mau năm 2025",
    "Doanh thu tháng gần nhất",
    "Doanh thu tháng gần nhất so với tháng liền trước (MoM)",
    "Doanh thu tháng gần nhất so với cùng kỳ năm trước (YoY)",
    "Doanh thu quý 1/2025",
    "Doanh thu quý 1/2025 so với cùng kỳ năm trước",
    "Doanh thu 6 tháng đầu năm 2025",
    "Tháng 3/2025 khu vực nào có doanh thu cao nhất",
    "So sánh doanh thu của Rạch Giá và An Giang trong tháng 1 2025 và tháng 10 2025",
    "Số lượng nhân sự tháng gần nhất",
    "Số tài xế theo khu vực năm 2025",
    "Doanh thu xe phân quyền quý 1/2025",
]

UI_HOTFIX_DROPDOWN_FONT_CSS = """
/* ===== HOTFIX: dropdown overlay + font-weight normalize (light touch) ===== */
.executive-filter-panel,
.executive-control-dock,
.executive-filter-panel .card-body,
.executive-control-dock .card-body,
.executive-graph-card,
.executive-kpi-card,
.executive-table-card,
.exec-filter-shell,
.exec-filter-dropdown-wrap{
  overflow: visible !important;
}

.exec-filter-shell{
  position: relative;
  z-index: 20;
}
.exec-filter-shell:focus-within{
  z-index: 9990 !important;
}
.exec-filter-dropdown-wrap{
  position: relative;
  z-index: 9991 !important;
}

.executive-dropdown,
.executive-dropdown .Select,
.executive-dropdown .Select-control,
.executive-dropdown .Select-menu-outer,
.exec-filter-shell .Select,
.exec-filter-shell .Select-control,
.exec-filter-shell .Select-menu-outer,
.Select-menu-outer{
  overflow: visible !important;
}

.executive-dropdown .Select-menu-outer,
.exec-filter-shell .Select-menu-outer,
.Select-menu-outer{
  z-index: 99999 !important;
  max-height: 320px !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
}

.executive-dropdown .Select-menu,
.exec-filter-shell .Select-menu,
.Select-menu{
  max-height: 318px !important;
}

.executive-dropdown .Select-option,
.exec-filter-shell .Select-option,
.executive-dropdown .VirtualizedSelectOption,
.exec-filter-shell .VirtualizedSelectOption{
  font-weight: 600 !important;
}

.exec-title,
.ai-panel-title,
.ai-empty-title,
.menu-group-title,
.kpi-card-title,
.filter-panel-title,
.exec-filter-title,
.home-nav-title,
.home-nav-group-title{
  font-weight: 800 !important;
}

.executive-dropdown .Select-value-label,
.exec-filter-shell .Select-value-label,
.executive-dropdown .Select-input > input,
.exec-filter-shell .Select-input > input{
  font-weight: 700 !important;
}
"""

TYPOGRAPHY_UNIFY_CSS = """
/* ===== HOTFIX: unify font family + normalize font weight ===== */
:root{
  --ui-font: "DejaVu Sans", Arial, "Helvetica Neue", Helvetica, sans-serif;
}

/* giữ icon Font Awesome không bị vỡ */
.fa,
.fas,
.fa-solid,
i.fa-solid,
i[class^="fa-"],
i[class*=" fa-"]{
  font-family: "Font Awesome 6 Free" !important;
  font-weight: 900 !important;
}

/* ép toàn bộ text dùng cùng 1 font để tránh fallback làm chữ đậm nhạt lẫn nhau */
html,
body,
#react-entry-point,
#_dash-app-content,
h1, h2, h3, h4, h5, h6,
div,
span,
p,
a,
button,
input,
textarea,
label,
small,
strong,
b,
li,
ul,
ol,
table,
thead,
tbody,
tr,
th,
td,
.offcanvas-title,
.card-title,
.card-text,
.modal-title,
.Select-placeholder,
.Select-value-label,
.Select-input > input,
.Select-option,
.VirtualizedSelectOption,
.dash-table-container,
.dash-spreadsheet-container,
.dash-spreadsheet-inner table{
  font-family: var(--ui-font) !important;
  font-synthesis: none !important;
  -webkit-font-smoothing: antialiased !important;
  -moz-osx-font-smoothing: grayscale !important;
  text-rendering: optimizeLegibility !important;
}

body{
  font-weight: 500 !important;
}

/* title */
#top-title,
.exec-title,
.ai-panel-title,
.ai-empty-title,
.menu-group-title,
.filter-panel-title,
.exec-filter-title,
.home-nav-title,
.home-nav-group-title,
.kpi-card-title,
.section-eyebrow,
.exec-chip,
.filter-panel-chip,
.summary-pill,
.offcanvas-title{
  font-weight: 700 !important;
  letter-spacing: 0 !important;
}

/* button / chip / CTA */
.ai-compose-title,
.ai-suggestion-title,
.ai-role,
.ai-mini-badge,
.ai-chip,
.quick-nav-btn,
.menu-tree-btn,
.home-nav-cta,
.home-nav-meta-pill,
.home-nav-code,
.home-nav-group,
.exec-filter-live-tag,
.kpi-delta-pill,
.btn{
  font-weight: 600 !important;
}

/* subtitle / body / caption */
.exec-subtitle,
.menu-group-subtitle,
.filter-panel-subtitle,
.exec-filter-helper,
.home-nav-subtitle,
.home-nav-group-subtitle,
.home-mini-note,
.ai-compose-caption,
.ai-panel-subtitle,
.ai-empty-text,
.ai-bubble-body,
.ai-thread-note,
.executive-dropdown .Select-value-label,
.exec-filter-shell .Select-value-label,
.executive-dropdown .Select-input > input,
.exec-filter-shell .Select-input > input,
.executive-dropdown .Select-option,
.exec-filter-shell .Select-option,
.executive-dropdown .VirtualizedSelectOption,
.exec-filter-shell .VirtualizedSelectOption,
.Select-placeholder,
.Select-option,
.VirtualizedSelectOption,
.card,
.card-body,
.card-text,
td,
th{
  font-weight: 500 !important;
  letter-spacing: 0 !important;
}

strong,
b{
  font-weight: 600 !important;
}

/* sidebar/menu riêng */
.offcanvas,
.offcanvas-body,
.offcanvas .btn,
.offcanvas .card,
.offcanvas .card-body,
.offcanvas .menu-group-title,
.offcanvas .menu-group-subtitle,
.offcanvas .menu-tree-btn,
.offcanvas .small-caption{
  font-family: var(--ui-font) !important;
}

.offcanvas .menu-group-title,
.offcanvas .menu-tree-btn,
.offcanvas .btn{
  font-weight: 600 !important;
}

.offcanvas .menu-group-subtitle,
.offcanvas .small-caption{
  font-weight: 500 !important;
}

/* Plotly text */
.js-plotly-plot .plotly text,
.js-plotly-plot .gtitle,
.js-plotly-plot .xtitle,
.js-plotly-plot .ytitle,
.js-plotly-plot .legend text,
.main-svg text{
  font-family: var(--ui-font) !important;
  font-weight: 500 !important;
}
"""


PREMIUM_DETAIL_TABLE_CSS = """
.executive-table-card{
  background: linear-gradient(180deg,#ffffff 0%,#f8fbff 100%) !important;
  border: 1px solid #dbe7f3 !important;
  border-radius: 26px !important;
  box-shadow: 0 22px 46px rgba(15,23,42,0.08) !important;
}
.executive-table-card .dash-table-container{
  border-radius: 18px;
  overflow: hidden;
}
.executive-table-card .dash-spreadsheet-container,
.executive-table-card .dash-spreadsheet-inner{
  border-radius: 18px !important;
  overflow: hidden !important;
}
.executive-table-card .dash-filter input{
  border-radius: 10px !important;
  border: 1px solid #cbd5e1 !important;
  padding: 6px 8px !important;
  font-weight: 700 !important;
  color: #0f172a !important;
  background: #ffffff !important;
}
.executive-table-card th{
  box-shadow: inset 0 -3px 0 rgba(34,197,94,0.85);
}
.executive-table-card td{
  vertical-align: middle !important;
}
.executive-table-card .dash-cell-value{
  line-height: 1.35 !important;
}
.executive-table-card .previous-next-container button,
.executive-table-card .page-number{
  border-radius: 12px !important;
  font-weight: 800 !important;
}
"""

AI_COPILOT_PRO_DOCK_CSS = """
.ai-answer-dock{
  margin-top: 14px;
  position: sticky;
  top: 0;
  z-index: 5;
  background: linear-gradient(180deg,rgba(247,251,255,0.98) 0%, rgba(247,251,255,0.94) 100%);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid #dbeafe;
  border-radius: 26px;
  padding: 12px;
  box-shadow: 0 18px 36px rgba(15,23,42,0.10);
}
.ai-answer-dock-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:8px;
}
.ai-answer-title{
  display:flex;
  align-items:center;
  gap:8px;
  font-size:12px;
  font-weight:900;
  letter-spacing:.5px;
  color:#0f172a;
  text-transform:uppercase;
}
.ai-answer-live{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:999px;
  background:#dcfce7;
  color:#166534;
  border:1px solid #bbf7d0;
  font-size:11px;
  font-weight:900;
  white-space:nowrap;
}
.ai-output-shell{
  margin-top: 0 !important;
  min-height: 260px !important;
  max-height: 42vh;
  overflow-y: auto;
  scroll-behavior: smooth;
  border-radius: 22px !important;
}
.ai-output-shell::-webkit-scrollbar{ width: 8px; }
.ai-output-shell::-webkit-scrollbar-thumb{
  background: rgba(22,163,74,0.42);
  border-radius: 999px;
}
.ai-row.bot.latest .ai-bubble{
  border-color:#22c55e;
  box-shadow:0 20px 40px rgba(34,197,94,0.12), 0 0 0 1px rgba(34,197,94,0.12) inset;
}
.ai-row.bot.latest .ai-role::after{
  content:"MỚI NHẤT";
  margin-left:8px;
  padding:3px 7px;
  border-radius:999px;
  background:#dcfce7;
  color:#166534;
  font-size:9px;
  font-weight:900;
  vertical-align:middle;
}
@media (max-width: 576px){
  .ai-answer-dock{ position: relative; top:auto; }
  .ai-output-shell{ max-height: 48vh; }
}
"""

DEVELOPER_CREDIT_CSS = """
.developer-credit-card{
  position: relative;
  overflow: hidden;
  margin-top: 18px;
  text-align: center;
  padding: 14px 14px 13px;
  border-radius: 22px;
  border: 1px solid rgba(34,197,94,0.24);
  background: linear-gradient(145deg,#ffffff 0%, #f0fdf4 52%, #ecfdf5 100%);
  box-shadow: 0 18px 34px rgba(15,23,42,0.10), inset 0 1px 0 rgba(255,255,255,0.95);
  flex-shrink: 0;
}
.developer-credit-card::before{
  content:"";
  position:absolute;
  inset:0 0 auto 0;
  height:5px;
  background:linear-gradient(90deg,#16a34a 0%, #22c55e 55%, #86efac 100%);
}
.developer-credit-card::after{
  content:"";
  position:absolute;
  right:-34px;
  top:-34px;
  width:98px;
  height:98px;
  border-radius:50%;
  background:rgba(34,197,94,0.10);
}
.developer-credit-kicker{
  position:relative;
  z-index:1;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  color:#166534;
  font-size:10px;
  font-weight:900;
  letter-spacing:.7px;
  text-transform:uppercase;
  margin-bottom:4px;
}
.developer-credit-name{
  position:relative;
  z-index:1;
  color:#0f172a;
  font-size:14px;
  font-weight:900;
  line-height:1.18;
  margin-bottom:10px;
}
.developer-credit-sql{
  position:relative;
  z-index:1;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:5px 9px;
  border-radius:999px;
  border:1px solid #bbf7d0;
  background:#dcfce7;
  color:#166534;
  font-size:10px;
  font-weight:900;
  letter-spacing:.4px;
  text-transform:uppercase;
  margin-bottom:8px;
}
.developer-credit-chip-row{
  position:relative;
  z-index:1;
  display:flex;
  flex-direction:column;
  gap:6px;
}
.developer-credit-chip{
  display:flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:7px 10px;
  border-radius:14px;
  background:rgba(255,255,255,0.86);
  border:1px solid #d1fae5;
  color:#334155;
  font-size:12px;
  font-weight:800;
  box-shadow:0 8px 16px rgba(15,23,42,0.04);
}
"""



PREMIUM_V2_INTERACTION_CSS = """
/* ===== V2: rounded accents, click-to-view tables, daily menu controls ===== */
.kpi-top-accent{
  height:5px;
  width:100%;
  border-radius:22px 22px 0 0 !important;
  overflow:hidden !important;
  transform:translateZ(0);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.16);
}
.executive-kpi-card > .kpi-top-accent,
.executive-graph-card > .kpi-top-accent,
.executive-table-card > .kpi-top-accent{
  border-top-left-radius:22px !important;
  border-top-right-radius:22px !important;
}
.executive-kpi-card,
.executive-table-card{
  overflow:hidden !important;
}
.executive-graph-card{
  border-radius:22px !important;
}
.executive-table-card .dash-filter,
.executive-table-card .dash-filter--case,
.executive-table-card input.dash-filter{
  display:none !important;
}
.executive-table-card .dash-table-container,
.executive-table-card .dash-spreadsheet-container,
.executive-table-card .dash-spreadsheet-inner{
  border-radius:18px !important;
}
.executive-table-card .dash-cell,
.executive-table-card td{
  cursor:pointer !important;
}
.executive-table-card td:hover,
.executive-table-card .dash-cell:hover{
  background:#ecfdf5 !important;
}
.executive-date-picker{
  width:100%;
}
.executive-date-picker .DateRangePicker,
.executive-date-picker .DateRangePickerInput{
  width:100%;
}
.executive-date-picker .DateRangePickerInput{
  min-height:58px;
  border-radius:18px !important;
  border:1px solid #dce7ef !important;
  background:linear-gradient(180deg,#ffffff 0%, #f8fafc 100%) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.90), 0 10px 18px rgba(15,23,42,0.04) !important;
  display:flex;
  align-items:center;
  overflow:hidden;
}
.executive-date-picker .DateInput{
  width:calc(50% - 16px);
  background:transparent !important;
}
.executive-date-picker .DateInput_input{
  font-family:var(--ui-font) !important;
  font-size:14px !important;
  font-weight:700 !important;
  color:#0f172a !important;
  padding:15px 12px !important;
  border:0 !important;
  background:transparent !important;
}
.executive-date-picker .DateRangePickerInput_arrow{
  color:#16a34a !important;
}
.table-row-detail-hero{
  border-radius:24px;
  padding:16px 18px;
  color:#ffffff;
  background:linear-gradient(135deg,#0f172a 0%, #14532d 58%, #16a34a 100%);
  box-shadow:0 18px 36px rgba(15,23,42,0.16);
  margin-bottom:14px;
}
.table-row-detail-title{
  font-size:18px;
  font-weight:900;
  line-height:1.18;
}
.table-row-detail-subtitle{
  font-size:12px;
  font-weight:700;
  opacity:.86;
  margin-top:6px;
}
.table-row-detail-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:10px;
}
.table-row-detail-item{
  border:1px solid #e2e8f0;
  border-radius:18px;
  background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);
  padding:12px 13px;
  box-shadow:0 10px 20px rgba(15,23,42,0.05);
}
.table-row-detail-label{
  color:#64748b;
  font-size:11px;
  font-weight:900;
  text-transform:uppercase;
  letter-spacing:.4px;
  margin-bottom:6px;
}
.table-row-detail-value{
  color:#0f172a;
  font-size:14px;
  font-weight:800;
  line-height:1.35;
  word-break:break-word;
}
.daily-latest-badge{
  display:inline-flex;
  align-items:center;
  gap:7px;
  padding:8px 12px;
  border-radius:999px;
  background:#dcfce7;
  color:#166534;
  border:1px solid #bbf7d0;
  font-size:11px;
  font-weight:900;
}
"""


TOP_NAV_AND_CHART_TITLE_CSS = """
/* ===== V3 CONTINUATION: only the top hamburger/title/logo bar is sticky ===== */
.top-navigation-shell{
  position: sticky !important;
  top: 0 !important;
  z-index: 1045 !important;
  margin-top: 0 !important;
  margin-bottom: 10px !important;
  padding: 6px 8px !important;
  min-height: 48px;
  background: linear-gradient(180deg, rgba(245,247,251,.96) 0%, rgba(245,247,251,.88) 100%);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-bottom: 1px solid rgba(203,213,225,.66);
  box-shadow: 0 12px 26px rgba(15,23,42,.07);
}
.top-navigation-shell::after{
  content:"";
  position:absolute;
  left:10px;
  right:10px;
  bottom:-1px;
  height:2px;
  border-radius:999px;
  background:linear-gradient(90deg, rgba(22,163,74,.78), rgba(20,184,166,.34), rgba(22,163,74,0));
  pointer-events:none;
}
.top-navigation-shell #open-menu{
  width:38px;
  height:38px;
  border-radius:12px !important;
  display:inline-flex !important;
  align-items:center !important;
  justify-content:center !important;
  border:1px solid rgba(148,163,184,.62) !important;
  background:linear-gradient(180deg,#ffffff 0%,#eaf4f2 100%) !important;
  color:#0f172a !important;
  box-shadow:0 8px 18px rgba(15,23,42,.08), inset 0 1px 0 rgba(255,255,255,.82) !important;
}
.top-navigation-shell #open-menu:hover{
  transform:translateY(-1px);
  border-color:rgba(34,197,94,.75) !important;
  box-shadow:0 12px 24px rgba(15,23,42,.12), 0 0 0 4px rgba(34,197,94,.10) !important;
}
.top-navigation-shell #top-title{
  font-size:14px !important;
  font-weight:800 !important;
  line-height:1.25 !important;
  letter-spacing:.35px !important;
  color:#0f172a !important;
  text-transform:uppercase;
}
.top-navigation-shell img{
  max-height:44px !important;
}
.js-plotly-plot .gtitle,
.main-svg .gtitle{
  font-family:var(--ui-font, "DejaVu Sans", Arial, sans-serif) !important;
  font-weight:800 !important;
  letter-spacing:-.01em !important;
}
.js-plotly-plot .xtitle,
.js-plotly-plot .ytitle,
.js-plotly-plot .legend text{
  font-family:var(--ui-font, "DejaVu Sans", Arial, sans-serif) !important;
}
.dash-graph .svg-container,
#zoom-graph .svg-container{
  background:#ffffff !important;
}
@media(max-width:768px){
  .top-navigation-shell{
    padding:5px 6px !important;
    min-height:44px;
    margin-bottom:8px !important;
  }
  .top-navigation-shell #top-title{
    font-size:12px !important;
    letter-spacing:.15px !important;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
    max-width:58vw;
  }
  .top-navigation-shell #open-menu{
    width:34px;
    height:34px;
    border-radius:11px !important;
  }
  .top-navigation-shell img{
    max-height:34px !important;
  }
}
"""


PREMIUM_ROUNDED_POLISH_CSS = """
:root{--premium-card-radius:24px;--premium-accent-line:linear-gradient(90deg,rgba(22,163,74,.96) 0%,rgba(20,184,166,.80) 52%,rgba(134,239,172,.66) 100%)}
.executive-kpi-card,.executive-graph-card,.executive-table-card{border-radius:var(--premium-card-radius)!important;overflow:hidden!important;background-clip:padding-box!important;isolation:isolate;box-shadow:0 18px 40px rgba(15,23,42,.075)!important}
.executive-kpi-card .card-body,.executive-graph-card .card-body,.executive-table-card .card-body{border-radius:0 0 var(--premium-card-radius) var(--premium-card-radius)!important;background-clip:padding-box!important}
.executive-graph-card .card-body,.executive-graph-card .dash-graph{overflow:hidden!important}
.kpi-top-accent,.executive-kpi-card>.kpi-top-accent,.executive-graph-card>.kpi-top-accent,.executive-table-card>.kpi-top-accent{height:5px!important;width:auto!important;margin:10px 14px 0!important;border-radius:999px!important;background:var(--premium-accent-line)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.42)!important;overflow:hidden!important;transform:translateZ(0)}
.dash-graph,#zoom-graph{background:#fff!important;border:1px solid rgba(226,232,240,.96)!important;border-radius:20px!important;padding:0!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.92),0 10px 22px rgba(15,23,42,.045)!important;overflow:hidden!important;background-clip:padding-box!important}
.dash-graph .js-plotly-plot,.dash-graph .plot-container,.dash-graph .svg-container,.dash-graph .main-svg,#zoom-graph .js-plotly-plot,#zoom-graph .plot-container,#zoom-graph .svg-container,#zoom-graph .main-svg{border-radius:18px!important;overflow:hidden!important;background-clip:padding-box!important}
.executive-filter-panel::before{left:18px!important;right:18px!important;top:10px!important;height:5px!important;width:auto!important;border-radius:999px!important;background:var(--premium-accent-line)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.36)!important}
.executive-filter-panel>.card-body{padding-top:28px!important}.exec-filter-shell{border-radius:26px!important;background-clip:padding-box!important;isolation:isolate}
.exec-filter-shell::before{top:18px!important;bottom:18px!important;left:0!important;width:5px!important;height:auto!important;border-radius:0 999px 999px 0!important;background:linear-gradient(180deg,rgba(22,163,74,.95) 0%,rgba(34,197,94,.72) 100%)!important;box-shadow:none!important}
.exec-filter-shell::after{width:64px!important;height:64px!important;right:18px!important;top:18px!important;opacity:.45!important;background:radial-gradient(circle at center,rgba(34,197,94,.10) 0%,rgba(20,184,166,.035) 52%,transparent 72%)!important}.exec-filter-badge{box-shadow:0 10px 18px rgba(15,23,42,.10),inset 0 1px 0 rgba(255,255,255,.22)!important;background:linear-gradient(135deg,#16a34a 0%,#0f766e 100%)!important}
.executive-dropdown .Select-control,.exec-filter-shell .Select-control,.executive-date-picker .DateRangePickerInput{border-radius:20px!important;overflow:hidden!important;background-clip:padding-box!important}.executive-dropdown .Select-menu-outer,.exec-filter-shell .Select-menu-outer{border-radius:18px!important;overflow-x:hidden!important;overflow-y:auto!important}.executive-date-picker .DateInput,.executive-date-picker .DateInput_input{border-radius:16px!important}.DateRangePicker_picker,.DayPicker,.DayPicker__withBorder{border-radius:22px!important;overflow:hidden!important;box-shadow:0 22px 44px rgba(15,23,42,.14)!important}
.home-nav-card-inner{border-radius:26px!important;overflow:hidden!important;background-clip:padding-box!important;isolation:isolate}.home-nav-card-inner::before{left:18px!important;right:18px!important;top:10px!important;height:4px!important;width:auto!important;border-radius:999px!important;background:linear-gradient(90deg,var(--nav-accent,#22c55e) 0%,rgba(255,255,255,.42) 130%)!important;opacity:.92!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.35)!important}.home-nav-card-inner::after{right:-2px!important;top:-18px!important;width:94px!important;height:94px!important;border-radius:34px!important;opacity:.38!important;background:radial-gradient(circle at center,var(--nav-accent-soft,rgba(34,197,94,.10)) 0%,rgba(255,255,255,0) 70%)!important}.home-nav-icon{background:linear-gradient(180deg,#fff 0%,rgba(240,253,244,.92) 100%)!important;border:1px solid rgba(187,247,208,.72)!important;box-shadow:0 10px 20px rgba(15,23,42,.065),inset 0 1px 0 rgba(255,255,255,.88)!important}
.home-nav-group-shell{border-radius:28px!important;overflow:hidden!important;background-clip:padding-box!important;isolation:isolate}.home-nav-group-shell::before{left:10px!important;top:18px!important;bottom:18px!important;width:5px!important;border-radius:999px!important;background:linear-gradient(180deg,var(--group-accent,#22c55e) 0%,rgba(255,255,255,.50) 125%)!important}.home-nav-group-shell::after{top:-24px!important;right:-16px!important;width:132px!important;height:132px!important;opacity:.34!important;background:radial-gradient(circle at center,var(--group-accent-soft,rgba(34,197,94,.10)) 0%,transparent 70%)!important}.home-nav-cta{border-radius:16px!important;background:linear-gradient(90deg,rgba(255,255,255,.98) 0%,var(--nav-accent-soft,rgba(34,197,94,.10)) 100%)!important}
.executive-home-nav-panel::after,.executive-control-dock::after,.developer-credit-card::after,.ai-panel-intro::after,.data-status-card::after,.page-loading-hero::after{opacity:.55!important;background:radial-gradient(circle at center,rgba(255,255,255,.10) 0%,rgba(255,255,255,.035) 48%,transparent 72%)!important}.developer-credit-card::before{left:14px!important;right:14px!important;top:10px!important;height:5px!important;border-radius:999px!important;background:var(--premium-accent-line)!important}.developer-credit-card{padding-top:22px!important;border-radius:24px!important}
.executive-table-card .dash-table-container,.executive-table-card .dash-spreadsheet-container,.executive-table-card .dash-spreadsheet-inner,.executive-table-card .dash-spreadsheet-inner table{border-radius:18px!important;overflow:hidden!important;background-clip:padding-box!important}.executive-table-card th:first-child{border-top-left-radius:18px!important}.executive-table-card th:last-child{border-top-right-radius:18px!important}.executive-table-card th{box-shadow:inset 0 -2px 0 rgba(34,197,94,.55)!important}.executive-table-card .previous-next-container button,.executive-table-card .page-number{border-radius:14px!important}
@media(max-width:768px){.kpi-top-accent{margin-left:12px!important;margin-right:12px!important}.executive-filter-panel::before,.home-nav-card-inner::before{left:12px!important;right:12px!important}.executive-filter-panel>.card-body{padding-top:24px!important}}
"""


PREMIUM_TEXT_MASTER_CSS = """
/* =====================================================================
   PREMIUM TEXT MASTER SYSTEM - final override layer.
   Purpose: one typography scale, softer weights, stable Vietnamese text,
   stable numeric rendering, no callback/layout restructuring.
   ===================================================================== */
:root{
  --ui-font: "Inter", "SF Pro Display", "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif;
  --ui-text-strong:#0f172a;
  --ui-text-main:#1f2937;
  --ui-text-muted:#667085;
  --ui-text-soft:#94a3b8;
  --ui-green:#16a34a;
  --ui-font-body:500;
  --ui-font-label:600;
  --ui-font-title:700;
  --ui-font-display:800;
  --ui-letter-title:-0.018em;
  --ui-letter-label:.025em;
  --ui-line-body:1.55;
  font-family:var(--ui-font) !important;
}
html,
body,
#react-entry-point,
#_dash-app-content,
.dash-renderer,
.dash-debug-menu,
.dash-table-container,
.dash-spreadsheet-container{
  font-family:var(--ui-font) !important;
  color:var(--ui-text-main);
  -webkit-font-smoothing:antialiased !important;
  -moz-osx-font-smoothing:grayscale !important;
  text-rendering:geometricPrecision !important;
  font-kerning:normal !important;
  font-feature-settings:"kern" 1, "liga" 1, "tnum" 1 !important;
  font-synthesis:none !important;
}
body{
  font-size:13.5px !important;
  line-height:var(--ui-line-body) !important;
  font-weight:var(--ui-font-body) !important;
  letter-spacing:0 !important;
}
.fa,.fas,.far,.fab,.fa-solid,.fa-regular,.fa-brands,
i.fa,i.fas,i.fa-solid,i[class^="fa-"],i[class*=" fa-"]{
  font-family:"Font Awesome 6 Free" !important;
  font-weight:900 !important;
  letter-spacing:0 !important;
  text-rendering:auto !important;
}
#_dash-app-content [style*="font-weight: 900"],
#_dash-app-content [style*="font-weight:900"],
#_dash-app-content [style*="fontWeight: 900"],
#_dash-app-content [style*="fontWeight:900"]{
  font-weight:var(--ui-font-display) !important;
}
#_dash-app-content [style*="font-weight: bold"],
#_dash-app-content [style*="font-weight:bold"],
#_dash-app-content [style*="fontWeight: bold"],
#_dash-app-content [style*="fontWeight:bold"]{
  font-weight:var(--ui-font-title) !important;
}
.exec-title,
.page-loading-title,
.ai-panel-title,
.data-status-main{
  font-family:var(--ui-font) !important;
  font-weight:var(--ui-font-display) !important;
  letter-spacing:var(--ui-letter-title) !important;
  line-height:1.08 !important;
  color:inherit;
}
.exec-title{font-size:clamp(24px, 2.05vw, 31px) !important;}
.page-loading-title{font-size:clamp(22px, 1.9vw, 28px) !important;}
.ai-panel-title{font-size:clamp(20px, 1.65vw, 24px) !important;}
.data-status-main{font-size:clamp(23px, 1.75vw, 28px) !important;}
#top-title{
  font-family:var(--ui-font) !important;
  font-size:13.5px !important;
  font-weight:var(--ui-font-title) !important;
  letter-spacing:.018em !important;
  line-height:1.22 !important;
  text-transform:uppercase !important;
  color:var(--ui-text-strong) !important;
}
.section-eyebrow,
.kpi-card-title,
.filter-panel-title,
.exec-filter-title,
.home-nav-group,
.home-nav-code,
.data-status-kicker,
.ai-panel-kicker,
.ai-compose-title,
.ai-suggestion-title,
.ai-role,
.modal-title,
.offcanvas-title{
  font-family:var(--ui-font) !important;
  font-size:11.5px !important;
  font-weight:var(--ui-font-title) !important;
  letter-spacing:var(--ui-letter-label) !important;
  line-height:1.25 !important;
  text-transform:uppercase !important;
}
.kpi-card-title{color:#64748b !important;letter-spacing:.035em !important;}
.data-status-kicker,.ai-panel-kicker{color:rgba(255,255,255,.78) !important;letter-spacing:.055em !important;}
.exec-chip,
.summary-pill,
.filter-panel-chip,
.data-status-pill,
.ai-scope-pill,
.ai-compose-badge,
.ai-mini-badge,
.kpi-delta-pill,
.home-nav-meta-pill,
.exec-filter-live-tag,
.btn,
.quick-nav-btn,
.menu-tree-btn,
.home-nav-cta{
  font-family:var(--ui-font) !important;
  font-size:12px !important;
  font-weight:var(--ui-font-label) !important;
  line-height:1.25 !important;
  letter-spacing:.002em !important;
}
.btn.btn-sm{font-size:12px !important;}
.page-nav-btn{
  font-size:28px !important;
  font-weight:300 !important;
  letter-spacing:0 !important;
  line-height:1 !important;
}
.exec-subtitle,
.page-loading-subtitle,
.filter-panel-subtitle,
.exec-filter-helper,
.home-mini-note,
.home-nav-subtitle,
.home-nav-group-subtitle,
.menu-group-subtitle,
.data-status-caption,
.ai-panel-subtitle,
.ai-compose-caption,
.ai-empty-text,
.ai-bubble-body,
.ai-thread-note,
.card-text,
p,li,small,label{
  font-family:var(--ui-font) !important;
  font-size:12.5px !important;
  font-weight:var(--ui-font-body) !important;
  line-height:1.55 !important;
  letter-spacing:0 !important;
}
.exec-subtitle,.filter-panel-subtitle,.data-status-caption{font-size:13px !important;line-height:1.55 !important;}
.home-nav-title,.menu-group-title,.ai-empty-title{
  font-family:var(--ui-font) !important;
  font-size:14.5px !important;
  font-weight:var(--ui-font-title) !important;
  letter-spacing:-.006em !important;
  line-height:1.25 !important;
  color:var(--ui-text-strong) !important;
}
.home-nav-group-title,.filter-panel-title{font-size:13px !important;font-weight:var(--ui-font-title) !important;letter-spacing:.005em !important;}
.executive-table-card .section-eyebrow + div{
  font-family:var(--ui-font) !important;
  font-size:21px !important;
  font-weight:var(--ui-font-display) !important;
  line-height:1.16 !important;
  letter-spacing:var(--ui-letter-title) !important;
  color:var(--ui-text-strong) !important;
}
.executive-kpi-card [style*="font-size: 28px"],
.executive-kpi-card [style*="font-size:28px"],
.executive-kpi-card [style*="font-size: 30px"],
.executive-kpi-card [style*="font-size:30px"]{
  font-family:var(--ui-font) !important;
  font-size:clamp(25px, 2vw, 30px) !important;
  font-weight:var(--ui-font-display) !important;
  letter-spacing:-.025em !important;
  line-height:1.06 !important;
  font-variant-numeric:tabular-nums !important;
}
.executive-kpi-card [style*="font-size: 12px"],
.executive-kpi-card [style*="font-size:12px"]{
  font-size:12px !important;
  font-weight:var(--ui-font-body) !important;
  line-height:1.42 !important;
}
.data-status-pill{font-size:11.5px !important;font-weight:var(--ui-font-label) !important;letter-spacing:.004em !important;line-height:1.2 !important;}
.data-status-card strong,.data-status-card b{font-weight:var(--ui-font-title) !important;}
.Select-control,
.Select-placeholder,
.Select-value-label,
.Select-input > input,
.Select-option,
.VirtualizedSelectOption,
.DateInput_input,
input,textarea,button{
  font-family:var(--ui-font) !important;
  font-size:13px !important;
  font-weight:var(--ui-font-body) !important;
  letter-spacing:0 !important;
}
.Select-value-label,.Select-input > input,.DateInput_input{font-weight:var(--ui-font-label) !important;color:var(--ui-text-strong) !important;}
.Select-placeholder{color:#94a3b8 !important;font-weight:500 !important;}
.offcanvas,
.offcanvas-body,
.offcanvas-header,
.offcanvas .card,
.offcanvas .btn,
.offcanvas span,
.offcanvas div{font-family:var(--ui-font) !important;}
.offcanvas-title{font-size:13px !important;font-weight:var(--ui-font-title) !important;letter-spacing:.018em !important;}
.offcanvas [style*="font-weight: 900"],.offcanvas [style*="font-weight:900"]{font-weight:var(--ui-font-title) !important;}
.offcanvas .btn,.offcanvas .menu-tree-btn{font-size:12.5px !important;font-weight:var(--ui-font-label) !important;line-height:1.25 !important;}
.dash-table-container,
.dash-table-container *:not(.fa):not(.fas):not(.fa-solid),
.dash-spreadsheet-container,
.dash-spreadsheet-container *:not(.fa):not(.fas):not(.fa-solid){font-family:var(--ui-font) !important;}
.dash-spreadsheet-container th,.dash-spreadsheet-container th *{font-size:12px !important;font-weight:var(--ui-font-title) !important;line-height:1.25 !important;letter-spacing:.01em !important;}
.dash-spreadsheet-container td,.dash-spreadsheet-container td *{font-size:12.5px !important;font-weight:var(--ui-font-body) !important;line-height:1.35 !important;letter-spacing:0 !important;font-variant-numeric:tabular-nums !important;}
.modal,.modal *:not(.fa):not(.fas):not(.fa-solid){font-family:var(--ui-font) !important;}
.modal [style*="font-size: 44px"],.modal [style*="font-size:44px"]{font-size:42px !important;font-weight:var(--ui-font-display) !important;letter-spacing:-.035em !important;font-variant-numeric:tabular-nums !important;}
.modal [style*="font-size: 15px"],.modal [style*="font-size:15px"],.modal [style*="font-size: 14px"],.modal [style*="font-size:14px"]{font-weight:var(--ui-font-title) !important;letter-spacing:-.004em !important;}
.js-plotly-plot,
.js-plotly-plot .plotly,
.js-plotly-plot .svg-container,
.js-plotly-plot .main-svg,
.js-plotly-plot text,
.main-svg text{font-family:var(--ui-font) !important;text-rendering:geometricPrecision !important;}
.js-plotly-plot .gtitle,.main-svg .gtitle{font-weight:var(--ui-font-display) !important;letter-spacing:-.012em !important;}
.js-plotly-plot .xtitle,.js-plotly-plot .ytitle,.js-plotly-plot .legend text,.js-plotly-plot .xtick text,.js-plotly-plot .ytick text{font-weight:500 !important;letter-spacing:0 !important;}
strong,b{font-weight:var(--ui-font-title) !important;}
@media(max-width:768px){
  body{font-size:13px !important;}
  #top-title{font-size:12.2px !important; max-width:58vw !important;}
  .exec-title{font-size:24px !important;}
  .data-status-main{font-size:22px !important;}
  .executive-table-card .section-eyebrow + div{font-size:19px !important;}
  .home-nav-title{font-size:14px !important;}
  .exec-chip,.summary-pill,.filter-panel-chip,.data-status-pill,.btn{font-size:11.5px !important;}
  .page-nav-btn{font-size:26px !important;}
}
"""


DATA_STATUS_CONTRAST_HOTFIX_CSS = """
/* =====================================================================
   DATA STATUS CONTRAST HOTFIX - final layer after typography master.
   The typography master normalizes text globally; this card has a dark
   executive background, so these local rules force high contrast.
   ===================================================================== */
.data-status-card,
.data-status-card .data-status-inner{
  color:#ffffff !important;
}
.data-status-card .data-status-kicker{
  color:rgba(255,255,255,.86) !important;
  opacity:1 !important;
  text-shadow:0 1px 2px rgba(0,0,0,.18) !important;
}
.data-status-card .data-status-main{
  color:#ffffff !important;
  opacity:1 !important;
  font-weight:800 !important;
  text-shadow:0 2px 12px rgba(0,0,0,.24) !important;
  -webkit-text-fill-color:#ffffff !important;
}
.data-status-card .data-status-caption{
  color:rgba(255,255,255,.92) !important;
  opacity:1 !important;
  text-shadow:0 1px 2px rgba(0,0,0,.16) !important;
}
.data-status-card .data-status-pill,
.data-status-card .data-status-pill *,
.data-status-card .data-status-cta,
.data-status-card .data-status-cta *{
  color:#ffffff !important;
  opacity:1 !important;
  -webkit-text-fill-color:#ffffff !important;
}
.data-status-card .data-status-pill{
  background:rgba(255,255,255,.14) !important;
  border-color:rgba(255,255,255,.22) !important;
}
.data-status-card .data-status-pill.soft{
  background:rgba(255,255,255,.10) !important;
}
"""

app.index_string = app.index_string.replace(
    "</head>",
    f"<style>{DROPDOWN_FIX_CSS}\n{PAGINATION_PRO_CSS}\n{AI_CHAT_CSS}\n{AI_COPILOT_PRO_DOCK_CSS}\n{PREMIUM_DATA_STATUS_CSS}\n{AI_LAUNCHER_CSS}\n{PREMIUM_LOADING_CSS}\n{GREEN_UI_CSS}\n{EXECUTIVE_UI_CSS}\n{MENU_TREE_CSS}\n{PREMIUM_FILTER_NAV_CSS}\n{NEXT_LEVEL_HOME_UI_CSS}\n{UI_HOTFIX_DROPDOWN_FONT_CSS}\n{TYPOGRAPHY_UNIFY_CSS}\n{PREMIUM_DETAIL_TABLE_CSS}\n{DEVELOPER_CREDIT_CSS}\n{PREMIUM_V2_INTERACTION_CSS}\n{PREMIUM_ROUNDED_POLISH_CSS}\n{TOP_NAV_AND_CHART_TITLE_CSS}\n{PREMIUM_TEXT_MASTER_CSS}\n{DATA_STATUS_CONTRAST_HOTFIX_CSS}</style></head>"
)

ZOOM_TARGETS = [
    "home-kpi1", "home-kpi2", "home-kpi3", "home-kpi4",
    "home-main", "home-region-donut", "home-region-bar", "home-lh-donut", "home-hd-bar",
    "daily-kpi1", "daily-kpi2", "daily-kpi3", "daily-kpi4",
    "daily-main", "daily-region-donut", "daily-region-bar", "daily-lh-donut", "daily-hd-bar"
]
for p in DASH_PREFIXES:
    ZOOM_TARGETS += [f"{p}-p1-kpi1", f"{p}-p1-kpi2", f"{p}-p1-kpi3"]
    ZOOM_TARGETS += [f"{p}-kpi1", f"{p}-kpi2", f"{p}-kpi3"]
    ZOOM_TARGETS += [f"{p}-p1-line-kv", f"{p}-p1-line", f"{p}-p1-bar", f"{p}-p1-pie"]
    ZOOM_TARGETS += [f"{p}-p2-line", f"{p}-p2-bar", f"{p}-p2-pie"]

def _zoomable_wrap(kind: str, target: str):
    return {"type": "zoomable", "kind": kind, "target": target}

def executive_page_header(title: str, subtitle: str, right_id: str | None = None):
    right_children = html.Div(id=right_id) if right_id else None
    return executive_header(title, subtitle, right_children=right_children)

def page_title_block(title: str, subtitle: str):
    return executive_header(title, subtitle, right_children=[
        summary_pill("Chế độ điều hành", fa_icon("fa-gauge-high", 12, "#ffffff")),
        summary_pill("Người dùng", fa_icon("fa-sun", 12, "#ffffff"))
    ])


def _loading_metric_card(title: str):
    return html.Div(
        [
            html.Div(title, className="page-loading-skeleton-title"),
            html.Div(className="page-loading-skeleton lg"),
            html.Div(className="page-loading-skeleton md"),
            html.Div(className="page-loading-skeleton sm"),
        ],
        className="page-loading-skeleton-card"
    )


def build_premium_loading_shell():
    return dbc.Container(
        fluid=True,
        className="page-loading-shell",
        children=[
            html.Div(
                [
                    html.Div("PREMIUM DASHBOARD LOADING", className="page-loading-kicker"),
                    html.Div("Đang đồng bộ dữ liệu và dựng giao diện điều hành", className="page-loading-title"),
                    html.Div(
                        "Hệ thống đang nạp KPI, biểu đồ, bộ lọc và dữ liệu nền. Bạn sẽ luôn thấy trạng thái loading ở phần trên mà không cần kéo màn hình xuống.",
                        className="page-loading-subtitle"
                    ),
                    html.Div(
                        [
                            html.Span([fa_icon("fa-bolt", 12, "#ffffff"), html.Span("Warm-up nhanh", className="ms-1")], className="page-loading-pill"),
                            html.Span([fa_icon("fa-chart-line", 12, "#ffffff"), html.Span("Đang dựng KPI", className="ms-1")], className="page-loading-pill"),
                            html.Span([fa_icon("fa-layer-group", 12, "#ffffff"), html.Span("Multi-page lazy render", className="ms-1")], className="page-loading-pill"),
                        ],
                        className="page-loading-pill-row"
                    ),
                ],
                className="page-loading-hero"
            ),
            dbc.Row(
                [
                    dbc.Col(_loading_metric_card("Tổng hợp KPI"), md=3),
                    dbc.Col(_loading_metric_card("Snapshot dữ liệu"), md=3),
                    dbc.Col(_loading_metric_card("Hiệu suất vận hành"), md=3),
                    dbc.Col(_loading_metric_card("Đồng bộ bộ lọc"), md=3),
                ],
                className="g-3"
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Đang dựng biểu đồ điều hành", className="page-loading-skeleton-title"),
                                html.Div(className="page-loading-skeleton md"),
                                html.Div(
                                    [
                                        html.Div(className="page-loading-skeleton-bar bar h1"),
                                        html.Div(className="page-loading-skeleton-bar bar h2"),
                                        html.Div(className="page-loading-skeleton-bar bar h3"),
                                        html.Div(className="page-loading-skeleton-bar bar h4"),
                                        html.Div(className="page-loading-skeleton-bar bar h5"),
                                        html.Div(className="page-loading-skeleton-bar bar h6"),
                                        html.Div(className="page-loading-skeleton-bar bar h7"),
                                        html.Div(className="page-loading-skeleton-bar bar h8"),
                                    ],
                                    className="page-loading-chart-mini"
                                ),
                            ],
                            className="page-loading-chart-shell"
                        ),
                        md=8
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Đang tổng hợp insight nhanh", className="page-loading-skeleton-title"),
                                html.Div(className="page-loading-skeleton full"),
                                html.Div(className="page-loading-skeleton lg"),
                                html.Div(className="page-loading-skeleton md"),
                                html.Div(className="page-loading-skeleton full"),
                                html.Div(className="page-loading-skeleton lg"),
                                html.Div(className="page-loading-skeleton sm"),
                            ],
                            className="page-loading-chart-shell"
                        ),
                        md=4
                    ),
                ],
                className="g-3 mt-1"
            ),
        ]
    )

app.layout = dbc.Container(
    fluid=True,
    style={"backgroundColor": APP_LIGHT_BG, "minHeight": "100vh", "paddingBottom": "20px"},
    children=[
        dcc.Store(id="menu", data="home"),
        dcc.Store(id="page", data=0),
        dcc.Store(id="theme", data="light"),

        dcc.Store(id="filters-home", data={"year": DEFAULT_YEAR, "months": [], "dims": []}),
        *[dcc.Store(id=f"filters-{p}-p1", data=({"year": None, "months": []} if p in FLEET_MENU_PREFIXES else {"year": DEFAULT_YEAR, "months": []})) for p in DASH_PREFIXES],
        *[dcc.Store(id=f"filters-{p}-p2", data=({"year": None, "months": []} if p in FLEET_MENU_PREFIXES else {"year": DEFAULT_YEAR, "months": []})) for p in DASH_PREFIXES],

        dcc.Store(id="ai-chat-history", data=[]),
        dcc.Store(id="client-warm-sent", data=None),
        dcc.Interval(id="refresh-meta", interval=5 * 60 * 1000, n_intervals=0),
        dcc.Interval(id="client-warm-ping", interval=DASH_CLIENT_PRELOAD_DELAY_MS, n_intervals=0, max_intervals=1),

        dbc.Row([
            dbc.Col(
                dbc.Button([ICON_MENU], id="open-menu", color="secondary", outline=True, className="me-2"),
                width="auto"
            ),
            dbc.Col(
                html.Div(
                    id="top-title",
                    style={"fontSize": "18px", "fontWeight": "700", "letterSpacing": "1px", "color": TEXT_LIGHT_UI}
                )
            ),
            dbc.Col(
                html.Div(
                    [
                        dbc.Button(
                            [ICON_THEME, html.Span(" Theme", className="ms-2")],
                            id="toggle-theme",
                            color="secondary",
                            style={"display": "none"},
                            disabled=True
                        ),
                        html.Img(
                            src=COMPANY_LOGO_SRC,
                            style={
                                "height": "54px",
                                "width": "auto",
                                "objectFit": "contain",
                                "borderRadius": "10px",
                                "padding": "3px 6px",
                                "backgroundColor": "#ffffff",
                                "border": f"1.5px solid {GREEN_BORDER}",
                                "boxShadow": f"0 4px 14px {GREEN_SHADOW}"
                            }
                        ) if COMPANY_LOGO_SRC else html.Div(
                            "NAM THANG GROUP",
                            style={
                                "fontWeight": "900",
                                "fontSize": "14px",
                                "padding": "8px 12px",
                                "borderRadius": "10px",
                                "backgroundColor": "#fff",
                                "border": f"1.5px solid {GREEN_BORDER}",
                                "color": GREEN_PRIMARY,
                                "boxShadow": f"0 4px 14px {GREEN_SHADOW}"
                            }
                        )
                    ],
                    className="d-flex align-items-center justify-content-end gap-2"
                ),
                width="auto"
            )
        ], className="my-2 align-items-center top-navigation-shell"),

        dbc.Row([
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div("TRẠNG THÁI DỮ LIỆU", className="data-status-kicker"),
                                        html.Div(id="data-updated-at")
                                    ],
                                    style={"flex": "1 1 auto", "minWidth": 0}
                                ),
                                dbc.Button(
                                    [ICON_DL, html.Span(" Tải Excel", className="ms-1")],
                                    id="btn-download-excel",
                                    color="light",
                                    className="data-status-cta"
                                )
                            ],
                            className="data-status-inner"
                        ),
                        style={"padding": "18px 20px"}
                    ),
                    className="data-status-card"
                ),
                md=12,
                lg=8
            )
        ], className="mb-3"),

        dbc.Offcanvas(
            id="sidebar",
            title=html.Div([ICON_CHART, html.Span("  DASHBOARD MENU")]),
            is_open=False,
            placement="start",
            scrollable=True,
            style={"backgroundColor": "#ffffff", "color": TEXT_LIGHT_UI, "borderRight": f"1.5px solid {GREEN_BORDER}"},
            children=html.Div(
                [
                    html.Div(
                        [
                            html.Div("Menu điều hướng tổng thể", style={"fontWeight": "700", "marginBottom": "10px", "color": NAVY_PRIMARY}),
                            dbc.Button([ICON_HOME, html.Span(" HOME", className="ms-2")], id={"type": "menu-nav", "menu": "home", "source": "sidebar"}, color="success", className="w-100 mb-2"),
                            dbc.Button(
                                [fa_icon("fa-calendar-day", 14, GREEN_PRIMARY), html.Span(" Doanh thu cập nhật theo ngày", className="ms-2")],
                                id={"type": "menu-nav", "menu": "daily", "source": "sidebar"},
                                color="light",
                                className="w-100 mb-3",
                                style={"border": "1px solid #bbf7d0", "color": "#166534", "fontWeight": "700", "background": "linear-gradient(180deg,#ffffff 0%,#ecfdf5 100%)"},
                            ),
                            html.Div([build_sidebar_menu_section(group_cfg) for group_cfg in MENU_GROUPS], style={"paddingBottom": "12px"}),
                            html.Hr(style={"borderColor": "#d0d7e2"}),
                            html.Div("Điều hướng trang", style={"fontWeight": "700", "marginBottom": "10px", "color": NAVY_PRIMARY}),
                            dbc.Button("Home", id="go-home", color="secondary", outline=True, className="w-100 mb-2"),
                            dbc.Button("Page 1", id="go-page-1", color="secondary", outline=True, className="w-100 mb-2"),
                            dbc.Button("Page 2", id="go-page-2", color="secondary", outline=True, className="w-100 mb-2"),
                            dbc.Button(
                                [fa_icon("fa-right-from-bracket", 14, "#166534"), html.Span(" Đăng xuất", className="ms-2")],
                                href="/logout",
                                external_link=True,
                                color="light",
                                className="w-100 mt-2",
                                style={
                                    "border": "1px solid #dcfce7",
                                    "color": "#166534",
                                    "fontWeight": "700",
                                    "background": "#ffffff",
                                    "position": "relative",
                                    "zIndex": 3000,
                                    "pointerEvents": "auto",
                                },
                            ),
                        ],
                        style={"flex": "1 1 auto", "minHeight": 0}
                    ),
                    html.Div(
                        [
                            html.Div([fa_icon("fa-code", 11, "#166534"), html.Span("Intelligence Developer")], className="developer-credit-kicker"),
                            html.Div("Nguyen Huu Minh", className="developer-credit-name"),
                            html.Div([fa_icon("fa-database", 10, "#166534"), html.Span("SQL Data")], className="developer-credit-sql"),
                            html.Div(
                                [
                                    html.Div([fa_icon("fa-circle-check", 10, GREEN_PRIMARY), html.Span("Mai Nhat Truong")], className="developer-credit-chip"),
                                    html.Div([fa_icon("fa-circle-check", 10, GREEN_PRIMARY), html.Span("Danh The Trung")], className="developer-credit-chip"),
                                ],
                                className="developer-credit-chip-row"
                            ),
                        ],
                        className="developer-credit-card",
                    ),
                ],
                style={"minHeight": "100%", "display": "flex", "flexDirection": "column", "paddingBottom": "8px"}
            )
        ),

        dbc.Offcanvas(
            id="ai-box",
            title=html.Div([ICON_BOT, html.Span("  AI COPILOT")]),
            is_open=False,
            placement="end",
            scrollable=True,
            style={"backgroundColor": "#f7fbff", "color": TEXT_LIGHT_UI, "width": "500px", "borderLeft": f"1.5px solid {GREEN_BORDER}"},
            className="ai-premium-offcanvas",
            children=[
                html.Div(
                    [
                        html.Div("AI COPILOT", className="ai-panel-kicker"),
                        html.Div("Trợ lý phân tích dashboard", className="ai-panel-title"),
                        html.Div(
                            "Chat box hoạt động độc lập với page và bộ lọc hiện tại. Bạn chỉ cần nhập câu hỏi rõ ràng về năm, tháng, khu vực hoặc chỉ tiêu cần phân tích.",
                            className="ai-panel-subtitle"
                        ),
                        html.Div(
                            [
                                html.Span([fa_icon("fa-brain", 12, "#ffffff"), html.Span("Standalone Q&A", className="ms-1")], className="ai-scope-pill"),
                                html.Span([fa_icon("fa-filter", 12, "#ffffff"), html.Span("Không bám filter", className="ms-1")], className="ai-scope-pill"),
                                html.Span([fa_icon("fa-bolt", 12, "#ffffff"), html.Span("Fast prompt", className="ms-1")], className="ai-scope-pill"),
                            ],
                            className="ai-scope-row"
                        )
                    ],
                    className="ai-panel-intro"
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div([fa_icon("fa-message", 12, GREEN_PRIMARY), html.Span("Câu trả lời mới nhất")], className="ai-answer-title"),
                                html.Div([html.Span(className="exec-filter-live-dot"), html.Span("Luôn hiển thị trên cùng")], className="ai-answer-live"),
                            ],
                            className="ai-answer-dock-head"
                        ),
                        dcc.Loading(html.Div(ai_empty_state(), id="ai-output", className="ai-output-shell"), type="default")
                    ],
                    className="ai-answer-dock"
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div("Vùng soạn câu hỏi", className="ai-compose-title"),
                                        html.Div("Bạn có thể nhập 1 câu hoặc nhiều câu. AI sẽ phân tích theo nội dung bạn hỏi, không tự lấy context của page hoặc filter hiện tại.", className="ai-compose-caption"),
                                    ]
                                ),
                                html.Div([fa_icon("fa-sparkles", 12, GREEN_PRIMARY), html.Span("Chế độ điều hành", className="ms-1")], className="ai-compose-badge")
                            ],
                            className="ai-compose-head"
                        ),
                        dbc.Textarea(
                            id="ai-input",
                            placeholder="Ví dụ: Doanh thu tháng gần nhất so với tháng trước, hoặc Top 3 khu vực doanh thu cao nhất năm 2025...",
                        ),
                        dbc.Row([
                            dbc.Col(dbc.Button([ICON_SEND, html.Span(" Gửi phân tích")], id="ai-send", color="success", className="mt-3 w-100 ai-action-btn ai-send-btn")),
                            dbc.Col(dbc.Button([ICON_TRASH, html.Span(" Làm mới hội thoại")], id="ai-clear", color="secondary", outline=True, className="mt-3 w-100 ai-action-btn ai-clear-btn")),
                        ], className="g-2")
                    ],
                    className="ai-compose-shell"
                ),
                html.Div(
                    [
                        html.Div("Gợi ý nhanh", className="ai-suggestion-title"),
                        html.Div([
                            html.Span(
                                q,
                                className="ai-chip",
                                id={"type": "ai-chip", "idx": i},
                                n_clicks=0,
                                title="Click để hỏi AI ngay"
                            )
                            for i, q in enumerate(AI_SUGGESTIONS_V3)
                        ], className="ai-wrap")
                    ],
                    className="ai-suggestion-shell"
                ),
                html.Div("Gợi ý sẽ gửi câu hỏi trực tiếp; câu trả lời luôn xuất hiện ở khung trên cùng.", className="ai-thread-note")
            ]
        ),

        dcc.Loading(
            id="content-loading",
            type="default",
            delay_show=180,
            children=html.Div(id="content", className="page-content-shell", children=build_premium_loading_shell()),
        ),

        dbc.Button(ICON_CHEV_L, id="prev-page", className="page-nav-btn page-nav-left", title="Trang trước", style=PAGE_NAV_LEFT_BASE),
        dbc.Button(ICON_CHEV_R, id="next-page", className="page-nav-btn page-nav-right", title="Trang sau", style=PAGE_NAV_RIGHT_BASE),

        dbc.Button(
            [
                html.Span(fa_icon("fa-robot", 18, "#ffffff"), className="ai-launcher-orb"),
                html.Span(
                    [
                        html.Span("AI Copilot", className="ai-launcher-title"),
                        html.Span("Phân tích ngay trên dashboard", className="ai-launcher-sub"),
                    ],
                    className="ai-launcher-copy"
                )
            ],
            id="open-ai",
            color="success",
            className="ai-launcher-btn",
            title="Mở AI Copilot"
        ),

        dbc.Modal(
            id="zoom-modal",
            is_open=False,
            size="xl",
            scrollable=True,
            backdrop=True,
            centered=True,
            style={"maxWidth": "98vw", "width": "98vw"},
            children=[
                dbc.ModalHeader(dbc.ModalTitle(id="zoom-title", children="PHÓNG TO"), close_button=True),
                dbc.ModalBody(
                    dcc.Loading(type="default", children=html.Div([
                        html.Div(id="zoom-kpi-render", style={"width": "100%", "maxWidth": "100%"}),
                        dcc.Graph(
                            id="zoom-graph",
                            figure=empty_figure("Sẵn sàng phóng to biểu đồ", "light"),
                            config={"displayModeBar": True, "scrollZoom": True},
                            style=_zoom_graph_hidden_style()
                        ),
                        html.Hr(style={"borderColor": "#444", "marginTop": "10px", "marginBottom": "10px"}),
                        html.Div(id="zoom-detail", style={"display": "none", "width": "100%", "maxWidth": "100%", "overflowX": "hidden"})
                    ], style={"width": "100%", "maxWidth": "100%", "overflowX": "hidden"})),
                    style={"padding": "10px", "overflowX": "hidden"}
                )
            ],
        ),

        dbc.Modal(
            id="table-row-modal",
            is_open=False,
            size="lg",
            scrollable=True,
            centered=True,
            backdrop=True,
            children=[
                dbc.ModalHeader(dbc.ModalTitle(id="table-row-title", children="CHI TIẾT DÒNG DỮ LIỆU"), close_button=True),
                dbc.ModalBody(html.Div(id="table-row-body")),
                dbc.ModalFooter(dbc.Button("Đóng", id="table-row-close", color="success", className="px-4", n_clicks=0)),
            ],
        ),

        dcc.Store(id="zoom-target", data=None),
        dcc.Store(id="zoom-open-request", data=None),
        dcc.Store(id="zoom-selected-store", data=None),
        html.Div([dcc.Store(id={"type": "zoom-store", "target": t}, data=None) for t in ZOOM_TARGETS], style={"display": "none"}),
        dcc.Download(id="download-excel")
    ]
)

PAGE_LAYOUT_CACHE = {}

def _layout_scope_cache_key():
    user = current_auth_user()
    if not user:
        return "anonymous"
    return (
        str(user.get("username", "")),
        str(user.get("role", "")),
        tuple(sorted(str(x) for x in (user.get("regions") or []))),
    )

def _build_active_page_layout(menu, page):
    menu = menu or "home"
    try:
        p = int(page) if page is not None else (0 if menu in ["home", "daily"] else 1)
    except Exception:
        p = 0 if menu in ["home", "daily"] else 1

    cache_key = (str(menu), int(p), _layout_scope_cache_key())
    cached_layout = PAGE_LAYOUT_CACHE.get(cache_key)
    if cached_layout is not None:
        return cached_layout

    if menu == "home":
        layout = home_page()
    elif menu == "daily":
        layout = daily_latest_page()
    elif menu in DASH_PREFIXES:
        ensure_menu_data_loaded(menu)
        cfg = get_menu_config(menu)
        if p == 2:
            layout = page_2(menu, cfg["page2_title"], cfg["df"], "khu_vuc")
        else:
            layout = page_1(menu, cfg["page1_title"])
    else:
        layout = home_page()

    if len(PAGE_LAYOUT_CACHE) > 48:
        PAGE_LAYOUT_CACHE.clear()
    PAGE_LAYOUT_CACHE[cache_key] = layout
    return layout


@app.callback(
    Output("content","children"),
    Input("menu","data"),
    Input("page","data")
)
def render(menu, page):
    return _build_active_page_layout(menu, page)


UPDATE_TS_COL_CANDIDATES = [
    "updated_at", "updatedat", "updated at", "last_updated", "last updated", "last_update",
    "refresh_at", "refreshat", "refreshed_at", "refreshedat", "modified_at", "modifiedat",
    "ngay_cap_nhat", "ngay cap nhat", "thoi_gian_cap_nhat", "thoi gian cap nhat",
    "created_at", "createdat", "created at", "ngay_tao", "ngay tao", "timestamp"
]
LAST_UPDATED_CACHE = {"fingerprint": None, "payload": None}


def _normalize_scalar_to_vn_ts(value, assume_tz_if_naive: str = VN_TZ):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
            for unit in ("s", "ms"):
                try:
                    ts_num = pd.to_datetime(value, errors="coerce", unit=unit, utc=True)
                    if not pd.isna(ts_num):
                        return ts_num.tz_convert(VN_TZ)
                except Exception:
                    continue
        ts = pd.to_datetime(value, errors="coerce")
        if ts is None or pd.isna(ts):
            return None
        ts = pd.Timestamp(ts)
        if ts.tzinfo is not None:
            return ts.tz_convert(VN_TZ)
        return ts.tz_localize(assume_tz_if_naive)
    except Exception:
        try:
            ts = pd.to_datetime(value, errors="coerce", utc=True)
            if ts is None or pd.isna(ts):
                return None
            return pd.Timestamp(ts).tz_convert(VN_TZ)
        except Exception:
            return None


def _normalize_series_to_vn_ts(series_like: pd.Series, assume_tz_if_naive: str = VN_TZ) -> pd.Series:
    raw = pd.Series(series_like)
    try:
        s = pd.to_datetime(raw, errors="coerce")
    except Exception:
        s = pd.Series([pd.NaT] * len(raw), index=raw.index)
    if getattr(s, "notna", lambda: pd.Series(dtype=bool))().sum() == 0 and pd.api.types.is_numeric_dtype(raw):
        for unit in ("s", "ms"):
            try:
                s_num = pd.to_datetime(raw, errors="coerce", unit=unit, utc=True)
                if s_num.notna().sum() > 0:
                    return s_num.dt.tz_convert(VN_TZ)
            except Exception:
                continue
    try:
        if getattr(s.dt, "tz", None) is not None:
            return s.dt.tz_convert(VN_TZ)
        return s.dt.tz_localize(assume_tz_if_naive)
    except Exception:
        try:
            s = pd.to_datetime(raw, errors="coerce", utc=True)
            return s.dt.tz_convert(VN_TZ)
        except Exception:
            return pd.to_datetime(raw, errors="coerce")


def _is_reasonable_update_ts(ts) -> bool:
    ts_vn = _normalize_scalar_to_vn_ts(ts)
    if ts_vn is None:
        return False
    try:
        now_vn = pd.Timestamp.now(tz=VN_TZ)
        lower_bound = pd.Timestamp("2021-01-01", tz=VN_TZ)
        return lower_bound <= ts_vn <= now_vn + pd.Timedelta(days=2)
    except Exception:
        return False


def _excel_file_fingerprint(path: Path | None):
    if path is None:
        return None
    try:
        st = path.stat()
        return (str(path.resolve()), int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))))
    except Exception:
        return str(path)


def _read_excel_core_modified_ts(path: Path | None):
    if path is None:
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            if "docProps/core.xml" not in zf.namelist():
                return None
            root = ET.fromstring(zf.read("docProps/core.xml"))
            for tag_name in ("modified", "created"):
                node = root.find(f".//{{http://purl.org/dc/terms/}}{tag_name}")
                if node is not None and node.text:
                    ts = pd.to_datetime(node.text, errors="coerce", utc=True)
                    if ts is not None and not pd.isna(ts):
                        return ts.tz_convert(VN_TZ)
    except Exception:
        return None
    return None


def _latest_data_period_label() -> str | None:
    candidates = []
    cutoff_month = _current_vn_month_start()
    for dff in DASH_DATASETS:
        try:
            if isinstance(dff, pd.DataFrame) and not dff.empty and "thang_nam_vn" in dff.columns:
                s = _coerce_month_start(dff["thang_nam_vn"]).dropna()
                s = s[s <= cutoff_month]
                if not s.empty:
                    candidates.append(pd.Timestamp(s.max()))
        except Exception:
            continue
    if not candidates:
        return None
    return max(candidates).strftime("%m/%Y")


def _collect_loaded_update_candidates() -> list[dict]:
    out = []
    frame_candidates = [
        ("Doanh thu khu vực", df_dt),
        ("Loại hình", df_lh),
        ("Hợp đồng", df_hd),
        ("Nhân viên", df_emp),
        ("Tài xế", df_drv),
        ("Tiếp thị", df_mkt),
        ("Biên bản", df_bb),
        ("Xe trực thuộc", df_xdt),
        ("Xe phân quyền", df_xpq),
    ]
    for frame_label, dff in frame_candidates:
        try:
            if not isinstance(dff, pd.DataFrame) or dff.empty:
                continue
            col = find_col(dff, UPDATE_TS_COL_CANDIDATES)
            if not col or col not in dff.columns:
                continue
            s = _normalize_series_to_vn_ts(dff[col]).dropna()
            if s.empty:
                continue
            ts = s.max()
            if _is_reasonable_update_ts(ts):
                out.append({
                    "priority": 1,
                    "ts": _normalize_scalar_to_vn_ts(ts),
                    "source_label": "Timestamp trong dữ liệu",
                    "source_note": f"{frame_label}.{col}",
                    "trust_label": "Tin cậy cao",
                })
        except Exception:
            continue

    core_ts = _read_excel_core_modified_ts(EXCEL_FILE)
    if _is_reasonable_update_ts(core_ts):
        out.append({
            "priority": 2,
            "ts": _normalize_scalar_to_vn_ts(core_ts),
            "source_label": "cơ sở dữ liệu Tập Đoàn",
            "source_note": "SQL/n8n",
            "trust_label": "Cập nhật: Nguyễn Hữu Minh",
        })

    if EXCEL_FILE is not None:
        try:
            file_ts = pd.to_datetime(EXCEL_FILE.stat().st_mtime, unit="s", utc=True).tz_convert(VN_TZ)
            if _is_reasonable_update_ts(file_ts):
                out.append({
                    "priority": 3,
                    "ts": _normalize_scalar_to_vn_ts(file_ts),
                    "source_label": "Thời gian file",
                    "source_note": EXCEL_FILE.name,
                    "trust_label": "Fallback",
                })
        except Exception:
            pass

    out = [x for x in out if x.get("ts") is not None]
    out.sort(key=lambda item: (int(item.get("priority", 99)), -int(item["ts"].value)))
    return out


def get_dashboard_update_display_payload() -> dict:
    fingerprint = _excel_file_fingerprint(EXCEL_FILE)
    if LAST_UPDATED_CACHE.get("fingerprint") == fingerprint and LAST_UPDATED_CACHE.get("payload") is not None:
        return dict(LAST_UPDATED_CACHE["payload"])

    latest_period = _latest_data_period_label()
    candidates = _collect_loaded_update_candidates()

    if candidates:
        best = candidates[0]
        caption_parts = []
        if latest_period:
            caption_parts.append(f"Kỳ dữ liệu mới nhất: {latest_period}")
        if best.get("source_note"):
            caption_parts.append(f"Nguồn hiển thị: {best['source_label']} ({best['source_note']})")
        payload = {
            "headline": best["ts"].strftime("%d/%m/%Y %H:%M:%S (VN)"),
            "caption": " • ".join(caption_parts) if caption_parts else best["source_label"],
            "source_label": best["source_label"],
            "trust_label": best.get("trust_label", "Ổn định"),
            "status": "ok",
        }
    elif latest_period:
        payload = {
            "headline": f"Đến kỳ {latest_period}",
            "caption": "Không thấy timestamp chi tiết đáng tin cậy trong file Excel, hệ thống tự chuyển sang hiển thị kỳ dữ liệu mới nhất để tránh sai ngày sau khi deploy/GitHub.",
            "source_label": "Kỳ dữ liệu",
            "trust_label": "An toàn hiển thị",
            "status": "fallback",
        }
    else:
        payload = {
            "headline": "Không đọc được thời gian cập nhật",
            "caption": DATA_LOAD_ERROR or "Chưa xác định được file Excel hoặc metadata thời gian.",
            "source_label": "Không xác định",
            "trust_label": "Cần kiểm tra",
            "status": "error",
        }

    LAST_UPDATED_CACHE["fingerprint"] = fingerprint
    LAST_UPDATED_CACHE["payload"] = dict(payload)
    return payload

try:
    get_dashboard_update_display_payload()
except Exception:
    pass


@app.callback(
    Output("data-updated-at", "children"),
    Input("refresh-meta", "n_intervals")
)
def show_last_updated(_):
    info = get_dashboard_update_display_payload()
    state = str(info.get("status", "ok"))
    if state == "error":
        state_icon = "fa-circle-exclamation"
        source_icon = "fa-triangle-exclamation"
    elif state == "fallback":
        state_icon = "fa-shield-halved"
        source_icon = "fa-database"
    else:
        state_icon = "fa-circle-check"
        source_icon = "fa-database"
    return html.Div(
        [
            html.Div(
                [
                    html.Span([fa_icon(state_icon, 11, "#ffffff"), html.Span(info.get("trust_label", "Ổn định"), className="ms-1")], className="data-status-pill"),
                    html.Span([fa_icon(source_icon, 11, "#ffffff"), html.Span(info.get("source_label", "Nguồn dữ liệu"), className="ms-1")], className="data-status-pill soft"),
                ],
                className="data-status-pill-row"
            ),
            html.Div(info.get("headline", "Không đọc được thời gian cập nhật"), className="data-status-main"),
            html.Div(info.get("caption", ""), className="data-status-caption"),
        ]
    )

@app.callback(
    Output("download-excel", "data"),
    Input("btn-download-excel", "n_clicks"),
    State("menu", "data"),
    State("page", "data"),
    State("filters-home", "data"),
    State("daily-date-range", "start_date", allow_optional=True),
    State("daily-date-range", "end_date", allow_optional=True),
    State("daily-region", "value", allow_optional=True),
    State("daily-driver", "value", allow_optional=True),
    State("daily-vehicle-type", "value", allow_optional=True),
    State("daily-business-type", "value", allow_optional=True),
    *[State(f"filters-{p}-p1", "data") for p in DASH_PREFIXES],
    *[State(f"filters-{p}-p2", "data") for p in DASH_PREFIXES],
    prevent_initial_call=True
)
def download_excel(n, menu, page, f_home, daily_start, daily_end, daily_regions, daily_drivers, daily_vehicle_types, daily_business_types, *filter_states):
    try:
        p1_filter_map = dict(zip(DASH_PREFIXES, filter_states[:len(DASH_PREFIXES)]))
        p2_filter_map = dict(zip(DASH_PREFIXES, filter_states[len(DASH_PREFIXES):]))
        ts = pd.Timestamp.now(tz=VN_TZ).strftime("%Y%m%d_%H%M%S")

        if menu == "home":
            filt = f_home or {}
            year_val = filt.get("year")
            months = filt.get("months", []) or []
            dims = filt.get("dims", []) or []
            home_dt = apply_common_filters(df_dt, year_val=year_val, months=months, dims=dims)
            home_lh = apply_common_filters(df_lh, year_val=year_val, months=months, dims=dims)
            home_hd = apply_common_filters(df_hd, year_val=year_val, months=months, dims=dims)

            overview = _make_summary_for_export(home_dt, "home")
            region_share = pd.DataFrame()
            if not home_dt.empty and "khu_vuc" in home_dt.columns:
                region_share = home_dt.groupby("khu_vuc", as_index=False).agg({
                    "tong_doanh_thu": "sum",
                    "tong_so_cuoc": "sum"
                }).sort_values("tong_doanh_thu", ascending=False)
            lh_share = pd.DataFrame()
            if not home_lh.empty and LH_COL in home_lh.columns:
                lh_share = home_lh.groupby(LH_COL, as_index=False).agg({"tong_doanh_thu": "sum"}).sort_values("tong_doanh_thu", ascending=False)
            hd_share = pd.DataFrame()
            if not home_hd.empty and HD_COL in home_hd.columns:
                hd_share = home_hd.groupby(HD_COL, as_index=False).agg({"tong_so_cuoc": "sum"}).sort_values("tong_so_cuoc", ascending=False)

            filters_sheet = pd.DataFrame([{
                "menu": "home",
                "page": 0,
                "year": year_val,
                "months": ", ".join(months),
                "dims(khu_vuc)": ", ".join([str(x) for x in dims]),
            }])

            bio = BytesIO()
            with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                filters_sheet.to_excel(writer, sheet_name="FILTERS", index=False)
                home_dt.to_excel(writer, sheet_name="DT_FILTERED", index=False)
                home_lh.to_excel(writer, sheet_name="LH_FILTERED", index=False)
                home_hd.to_excel(writer, sheet_name="HD_FILTERED", index=False)
                if overview is not None and not overview.empty:
                    overview.to_excel(writer, sheet_name="OVERVIEW_MONTHLY", index=False)
                if region_share is not None and not region_share.empty:
                    region_share.to_excel(writer, sheet_name="REGION_SHARE", index=False)
                if lh_share is not None and not lh_share.empty:
                    lh_share.to_excel(writer, sheet_name="LH_SHARE", index=False)
                if hd_share is not None and not hd_share.empty:
                    hd_share.to_excel(writer, sheet_name="HD_SHARE", index=False)

            return dcc.send_bytes(bio.getvalue(), f"export_home_overview_{ts}.xlsx")

        if menu == "daily":
            daily_regions = _normalize_multi_value(daily_regions)
            daily_drivers = _normalize_multi_value(daily_drivers)
            daily_vehicle_types = _normalize_multi_value(daily_vehicle_types)
            daily_business_types = _normalize_multi_value(daily_business_types)
            source_dt, source_lh, source_hd = _daily_sources_for_driver_filter(daily_drivers)
            source_cross = _daily_cross_source_df(daily_drivers) if (daily_vehicle_types or daily_business_types) else pd.DataFrame()
            daily_dt = _filter_daily_frame(source_dt, daily_start, daily_end, daily_regions, source_label=_daily_source_label(), drivers=daily_drivers)
            daily_lh = _filter_daily_frame(source_lh, daily_start, daily_end, daily_regions, source_label="Loại hình ngày", drivers=daily_drivers)
            daily_hd = _filter_daily_frame(source_hd, daily_start, daily_end, daily_regions, source_label="Cơ cấu vận hành ngày", drivers=daily_drivers)
            daily_cross = pd.DataFrame()
            if isinstance(source_cross, pd.DataFrame) and not source_cross.empty:
                daily_cross = _filter_daily_frame(source_cross, daily_start, daily_end, daily_regions, source_label="Loại hình + hình thức ngày", drivers=daily_drivers)
                if daily_vehicle_types:
                    daily_cross = _filter_daily_vehicle_type_frame(daily_cross, daily_vehicle_types)
                if daily_business_types:
                    daily_cross = _filter_daily_business_type_frame(daily_cross, daily_business_types)
            if daily_vehicle_types:
                daily_lh = _filter_daily_vehicle_type_frame(daily_lh, daily_vehicle_types)
                daily_dt = _filter_daily_vehicle_type_frame(daily_dt, daily_vehicle_types) if _daily_frame_has_vehicle_type(daily_dt) else _daily_metric_frame_from_lh(daily_lh)
                daily_hd = _filter_daily_vehicle_type_frame(daily_hd, daily_vehicle_types)
            if daily_business_types:
                daily_hd = _filter_daily_business_type_frame(daily_hd, daily_business_types)
                daily_dt = _filter_daily_business_type_frame(daily_dt, daily_business_types) if _daily_frame_has_business_type(daily_dt) else _daily_metric_frame_from_business_type(daily_hd)
                if _daily_frame_has_business_type(daily_lh):
                    daily_lh = _filter_daily_business_type_frame(daily_lh, daily_business_types)
            if isinstance(daily_cross, pd.DataFrame) and not daily_cross.empty:
                daily_dt = daily_cross.copy(deep=False)
                daily_lh = daily_cross.copy(deep=False)
                daily_hd = daily_cross.copy(deep=False)
            daily_table = _daily_table_frame(daily_dt)
            region_share = pd.DataFrame()
            if not daily_dt.empty and "khu_vuc" in daily_dt.columns:
                region_share = daily_dt.groupby("khu_vuc", as_index=False).agg({"tong_doanh_thu": "sum", "tong_so_cuoc": "sum"}).sort_values("tong_doanh_thu", ascending=False)
            filters_sheet = pd.DataFrame([{
                "menu": "daily",
                "page": 0,
                "start_date": daily_start,
                "end_date": daily_end,
                "dims(khu_vuc)": ", ".join([str(x) for x in daily_regions]),
                "drivers": ", ".join([str(x) for x in daily_drivers]),
                "vehicle_types": ", ".join([str(x) for x in daily_vehicle_types]),
                "business_types": ", ".join([str(x) for x in daily_business_types]),
            }])
            bio = BytesIO()
            with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                filters_sheet.to_excel(writer, sheet_name="FILTERS", index=False)
                daily_dt.to_excel(writer, sheet_name="DAILY_DT_FILTERED", index=False)
                daily_lh.to_excel(writer, sheet_name="DAILY_LH_FILTERED", index=False)
                daily_hd.to_excel(writer, sheet_name="DAILY_HD_FILTERED", index=False)
                daily_table.to_excel(writer, sheet_name="DAILY_TABLE", index=False)
                if region_share is not None and not region_share.empty:
                    region_share.to_excel(writer, sheet_name="REGION_SHARE", index=False)
            return dcc.send_bytes(bio.getvalue(), f"export_daily_latest_{ts}.xlsx")

        filt = {}
        if int(page) == 1:
            filt = p1_filter_map.get(menu, {}) or {}
        elif int(page) == 2:
            filt = p2_filter_map.get(menu, {}) or {}

        dff = _apply_export_filters(menu, int(page), filt)
        summary = _make_summary_for_export(dff, menu)
        cfg = get_menu_config(menu) if menu in MENU_CONFIG else {}

        filters_sheet = pd.DataFrame([{
            "menu": menu,
            "page": int(page),
            "menu_label": cfg.get("menu_label", menu),
            "year": (filt or {}).get("year", None),
            "months": ", ".join((filt or {}).get("months", []) or []),
            "dims(khu_vuc)": ", ".join([str(x) for x in ((filt or {}).get("dims", []) or [])]),
            "type_filter": ", ".join([str(x) for x in ((filt or {}).get("type_filter", []) or [])]),
            "business_filter": ", ".join([str(x) for x in ((filt or {}).get("business_filter", []) or [])]),
        }])

        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            filters_sheet.to_excel(writer, sheet_name="FILTERS", index=False)
            dff.to_excel(writer, sheet_name="FILTERED_DATA", index=False)
            if summary is not None and not summary.empty:
                summary.to_excel(writer, sheet_name="SUMMARY", index=False)

        filename = f"export_{menu}_page{int(page)}_{ts}.xlsx"
        return dcc.send_bytes(bio.getvalue(), filename)
    except Exception:
        return no_update


# =========================================================
# CLIENTSIDE UI CALLBACKS
# =========================================================
# Các callback dưới đây chỉ đổi state UI/navigation thuần trình duyệt.
# Chúng không tính toán dữ liệu, không đổi chart/filter/RBAC/warm endpoint.
# Mục tiêu: bấm menu 3 gạch, AI, page nav phản hồi ngay trên Vercel,
# không phải chờ Python serverless function thức dậy.

_CLIENT_MENU_TITLE_MAP = {
    "home": "HOME  •  TRANG CHÍNH",
    "daily": "DOANH THU CẬP NHẬT  •  THEO NGÀY",
}
for _client_prefix, _client_cfg in MENU_CONFIG.items():
    _client_group_label = next((g["label"] for g in MENU_GROUPS if g["key"] == _client_cfg.get("group")), "Dashboard")
    _client_menu_label = str(_client_cfg.get("menu_label", _client_prefix))
    _CLIENT_MENU_TITLE_MAP[_client_prefix] = f"{_client_group_label.upper()}  •  {_client_menu_label.upper()}  •  PAGE {{page}}"

app.clientside_callback(
    """
    function(n_open, menuClicks, g0, g1, g2, isOpen) {
        const trig = dash_clientside.callback_context.triggered_id;
        if (trig === "open-menu") {
            return !Boolean(isOpen);
        }
        return false;
    }
    """,
    Output("sidebar", "is_open"),
    Input("open-menu", "n_clicks"),
    Input({"type": "menu-nav", "menu": ALL, "source": ALL}, "n_clicks"),
    Input("go-home", "n_clicks"),
    Input("go-page-1", "n_clicks"),
    Input("go-page-2", "n_clicks"),
    State("sidebar", "is_open"),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function(n, isOpen) {
        return !Boolean(isOpen);
    }
    """,
    Output("ai-box", "is_open"),
    Input("open-ai", "n_clicks"),
    State("ai-box", "is_open"),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function(menuClicks, nNext, nPrev, g0, g1, g2, currentMenu, currentPage) {
        const noUpdate = dash_clientside.no_update;
        const trig = dash_clientside.callback_context.triggered_id;
        let menu = currentMenu || "home";
        let page = parseInt(currentPage, 10);
        if (Number.isNaN(page)) {
            page = (menu === "home" || menu === "daily") ? 0 : 1;
        }
        if (trig && typeof trig === "object" && trig.type === "menu-nav") {
            const newMenu = trig.menu || "home";
            return [newMenu, (newMenu === "home" || newMenu === "daily") ? 0 : 1];
        }
        if (trig === "go-home") {
            return ["home", 0];
        }
        if (trig === "go-page-1") {
            return [menu, (menu === "home" || menu === "daily") ? 0 : 1];
        }
        if (trig === "go-page-2") {
            if (menu === "home" || menu === "daily") {
                return [noUpdate, noUpdate];
            }
            return [menu, 2];
        }
        if (menu === "home" || menu === "daily") {
            return [noUpdate, noUpdate];
        }
        if (trig === "next-page") {
            return [menu, (page !== 2) ? 2 : 1];
        }
        if (trig === "prev-page") {
            return [menu, (page !== 1) ? 1 : 2];
        }
        return [menu, page];
    }
    """,
    Output("menu","data"),
    Output("page","data"),
    Input({"type": "menu-nav", "menu": ALL, "source": ALL}, "n_clicks"),
    Input("next-page","n_clicks"),
    Input("prev-page","n_clicks"),
    Input("go-home","n_clicks"),
    Input("go-page-1","n_clicks"),
    Input("go-page-2","n_clicks"),
    State("menu","data"),
    State("page","data"),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function(n, theme) {
        return "light";
    }
    """,
    Output("theme","data"),
    Input("toggle-theme","n_clicks"),
    State("theme","data"),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function(menu, page) {
        const titles = CLIENT_MENU_TITLE_MAP;
        const key = menu || "home";
        let value = titles[key] || titles["home"];
        return String(value).replace("{page}", page || 1);
    }
    """.replace("CLIENT_MENU_TITLE_MAP", json.dumps(_CLIENT_MENU_TITLE_MAP, ensure_ascii=False)),
    Output("top-title", "children"),
    Input("menu", "data"),
    Input("page", "data"),
)

app.clientside_callback(
    """
    function(menu) {
        const hiddenLeft = Object.assign({}, PAGE_NAV_LEFT_BASE_JS, {display: "none"});
        const hiddenRight = Object.assign({}, PAGE_NAV_RIGHT_BASE_JS, {display: "none"});
        if (menu === "home" || menu === "daily") {
            return [hiddenLeft, hiddenRight];
        }
        return [PAGE_NAV_LEFT_BASE_JS, PAGE_NAV_RIGHT_BASE_JS];
    }
    """.replace("PAGE_NAV_LEFT_BASE_JS", json.dumps(PAGE_NAV_LEFT_BASE, ensure_ascii=False))
          .replace("PAGE_NAV_RIGHT_BASE_JS", json.dumps(PAGE_NAV_RIGHT_BASE, ensure_ascii=False)),
    Output("prev-page", "style"),
    Output("next-page", "style"),
    Input("menu", "data")
)

app.clientside_callback(
    """
    function(n) {
        if (!n) {
            return dash_clientside.no_update;
        }
        const enabled = CLIENT_PRELOAD_ENABLED_JS;
        const mode = CLIENT_PRELOAD_MODE_JS;
        if (!enabled || !mode) {
            return {sent: false, reason: "disabled"};
        }
        try {
            const runWarm = function(){
                try {
                    fetch("/_warm_user?preload=" + encodeURIComponent(mode), {
                        method: "GET",
                        credentials: "same-origin",
                        cache: "no-store",
                        keepalive: true
                    }).catch(function(){ return null; });
                } catch (e) {}
            };
            if (window.requestIdleCallback) {
                window.requestIdleCallback(runWarm, {timeout: 3500});
            } else {
                window.setTimeout(runWarm, 1800);
            }
        } catch (e) {}
        return {sent: true, mode: mode, ts: Date.now(), idle: true};
    }
    """.replace("CLIENT_PRELOAD_ENABLED_JS", json.dumps(bool(DASH_CLIENT_PRELOAD_AFTER_BOOT)))
          .replace("CLIENT_PRELOAD_MODE_JS", json.dumps(DASH_CLIENT_PRELOAD_MODE)),
    Output("client-warm-sent", "data"),
    Input("client-warm-ping", "n_intervals"),
    prevent_initial_call=True
)

@app.callback(
    Output("filters-home", "data"),
    Input("home-year", "value", allow_optional=True),
    Input("home-month", "value", allow_optional=True),
    Input("home-region", "value", allow_optional=True),
    prevent_initial_call=True
)
def store_filters_home(year_val, months, regions):
    regions = regions if isinstance(regions, list) else ([regions] if regions else [])
    return {"year": year_val, "months": months or [], "dims": regions}

@app.callback(
    Output("filters-dt-p1", "data"),
    Input("dt-year", "value", allow_optional=True),
    Input("dt-month", "value", allow_optional=True),
    prevent_initial_call=True
)
def _store_filters_dt_p1(year_val, months):
    return {"year": year_val, "months": months or []}

@app.callback(
    Output("filters-lh-p1", "data"),
    Input("lh-year", "value", allow_optional=True),
    Input("lh-month", "value", allow_optional=True),
    Input("lh-type-p1", "value", allow_optional=True),
    Input("lh-business-type-p1", "value", allow_optional=True),
    prevent_initial_call=True
)
def _store_filters_lh_p1(year_val, months, type_filter, business_filter):
    return {"year": year_val, "months": months or [], "type_filter": type_filter or [], "business_filter": business_filter or []}

@app.callback(
    Output("filters-hd-p1", "data"),
    Input("hd-year", "value", allow_optional=True),
    Input("hd-month", "value", allow_optional=True),
    Input("hd-type-p1", "value", allow_optional=True),
    prevent_initial_call=True
)
def _store_filters_hd_p1(year_val, months, type_filter):
    return {"year": year_val, "months": months or [], "type_filter": type_filter or []}

@app.callback(
    Output("filters-dt-p2", "data"),
    Input("dt-dim", "value", allow_optional=True),
    Input("dt-year-p2", "value", allow_optional=True),
    Input("dt-month-p2", "value", allow_optional=True),
    prevent_initial_call=True
)
def _store_filters_dt_p2(dims, year_val, months):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or []}

@app.callback(
    Output("filters-lh-p2", "data"),
    Input("lh-dim", "value", allow_optional=True),
    Input("lh-year-p2", "value", allow_optional=True),
    Input("lh-month-p2", "value", allow_optional=True),
    Input("lh-type-p2", "value", allow_optional=True),
    Input("lh-business-type-p2", "value", allow_optional=True),
    prevent_initial_call=True
)
def _store_filters_lh_p2(dims, year_val, months, type_filter, business_filter):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or [], "type_filter": type_filter or [], "business_filter": business_filter or []}

@app.callback(
    Output("filters-hd-p2", "data"),
    Input("hd-dim", "value", allow_optional=True),
    Input("hd-year-p2", "value", allow_optional=True),
    Input("hd-month-p2", "value", allow_optional=True),
    Input("hd-type-p2", "value", allow_optional=True),
    prevent_initial_call=True
)
def _store_filters_hd_p2(dims, year_val, months, type_filter):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or [], "type_filter": type_filter or []}

# Fleet filter stores are handled centrally inside _register_simple_menu_callbacks
# to avoid duplicate callback outputs for xdt/xpq.

@app.callback(
    Output({"type": "filter-wrap", "id": ALL}, "style"),
    Input("theme", "data"),
    State({"type": "filter-wrap", "id": ALL}, "id"),
    prevent_initial_call=False
)
def update_filter_wrap_styles(theme, ids):
    st = dropdown_container_style(theme)
    return [st] * len(ids)

def _month_options_for_year(year_val):
    if year_val is None:
        opts = MONTH_OPTIONS_ALL
    else:
        opts = MONTH_OPTIONS_BY_YEAR.get(int(year_val), [])
    return [{"label": m, "value": m} for m in opts], opts

@app.callback(
    Output("home-month", "options"),
    Output("home-month", "value"),
    Input("home-year", "value", allow_optional=True),
    State("home-month", "value", allow_optional=True),
    prevent_initial_call=False
)
def home_month_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

@app.callback(
    Output("dt-month", "options"),
    Output("dt-month", "value"),
    Input("dt-year", "value", allow_optional=True),
    State("dt-month", "value", allow_optional=True),
    prevent_initial_call=True
)
def dt_month_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

@app.callback(
    Output("lh-month", "options"),
    Output("lh-month", "value"),
    Input("lh-year", "value", allow_optional=True),
    State("lh-month", "value", allow_optional=True),
    prevent_initial_call=True
)
def lh_month_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

@app.callback(
    Output("hd-month", "options"),
    Output("hd-month", "value"),
    Input("hd-year", "value", allow_optional=True),
    State("hd-month", "value", allow_optional=True),
    prevent_initial_call=True
)
def hd_month_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

@app.callback(
    Output("dt-month-p2", "options"),
    Output("dt-month-p2", "value"),
    Input("dt-year-p2", "value", allow_optional=True),
    State("dt-month-p2", "value", allow_optional=True),
    prevent_initial_call=True
)
def dt_month_p2_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

@app.callback(
    Output("lh-month-p2", "options"),
    Output("lh-month-p2", "value"),
    Input("lh-year-p2", "value", allow_optional=True),
    State("lh-month-p2", "value", allow_optional=True),
    prevent_initial_call=True
)
def lh_month_p2_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

@app.callback(
    Output("hd-month-p2", "options"),
    Output("hd-month-p2", "value"),
    Input("hd-year-p2", "value", allow_optional=True),
    State("hd-month-p2", "value", allow_optional=True),
    prevent_initial_call=True
)
def hd_month_p2_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

def _store_filters_hr(prefix: str, page_key: str, year_val, months, regions, departments):
    regions = regions if isinstance(regions, list) else ([regions] if regions else [])
    departments = departments if isinstance(departments, list) else ([departments] if departments else [])
    payload = {"year": year_val, "months": months or [], "dims": regions, "departments": departments}
    if page_key == "p2":
        payload["dims"] = regions
    return payload


for _hr_prefix in HR_MENU_PREFIXES:
    @app.callback(
        Output(f"filters-{_hr_prefix}-p1", "data"),
        Input(f"{_hr_prefix}-year", "value", allow_optional=True),
        Input(f"{_hr_prefix}-month", "value", allow_optional=True),
        Input(f"{_hr_prefix}-region", "value", allow_optional=True),
        Input(f"{_hr_prefix}-dept", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _store_filters_hr_p1(year_val, months, regions, departments, _prefix=_hr_prefix):
        return _store_filters_hr(_prefix, "p1", year_val, months, regions, departments)

    @app.callback(
        Output(f"filters-{_hr_prefix}-p2", "data"),
        Input(f"{_hr_prefix}-dim", "value", allow_optional=True),
        Input(f"{_hr_prefix}-year-p2", "value", allow_optional=True),
        Input(f"{_hr_prefix}-month-p2", "value", allow_optional=True),
        Input(f"{_hr_prefix}-dept-p2", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _store_filters_hr_p2(dims, year_val, months, departments, _prefix=_hr_prefix):
        dims = dims if isinstance(dims, list) else ([dims] if dims else [])
        departments = departments if isinstance(departments, list) else ([departments] if departments else [])
        return {"dims": dims, "year": year_val, "months": months or [], "departments": departments}

    @app.callback(
        Output(f"{_hr_prefix}-month", "options"),
        Output(f"{_hr_prefix}-month", "value"),
        Input(f"{_hr_prefix}-year", "value", allow_optional=True),
        State(f"{_hr_prefix}-month", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _month_depends_on_year_hr_p1(year_val, cur_months, _prefix=_hr_prefix):
        options, allowed = _month_options_for_year(year_val)
        cur_months = cur_months or []
        new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
        return options, new_val

    @app.callback(
        Output(f"{_hr_prefix}-month-p2", "options"),
        Output(f"{_hr_prefix}-month-p2", "value"),
        Input(f"{_hr_prefix}-year-p2", "value", allow_optional=True),
        State(f"{_hr_prefix}-month-p2", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _month_depends_on_year_hr_p2(year_val, cur_months, _prefix=_hr_prefix):
        options, allowed = _month_options_for_year(year_val)
        cur_months = cur_months or []
        new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
        return options, new_val


EXTRA_DYNAMIC_PREFIXES = [p for p in DASH_PREFIXES if p not in ["dt", "lh", "hd", "emp", "drv"]]

def _register_simple_menu_callbacks(prefix: str):
    if prefix in FLEET_MENU_PREFIXES:
        @app.callback(
            Output(f"filters-{prefix}-p1", "data"),
            Input(f"{prefix}-type-p1", "value", allow_optional=True),
            Input(f"{prefix}-seat-p1", "value", allow_optional=True),
            prevent_initial_call=True
        )
        def _store_filters_p1_fleet(type_filter=None, seat_filter=None, _prefix=prefix):
            payload = {"year": None, "months": []}
            if type_filter:
                payload["type_filter"] = type_filter if isinstance(type_filter, list) else [type_filter]
            if seat_filter:
                payload["seat_filter"] = seat_filter if isinstance(seat_filter, list) else [seat_filter]
            return payload

        @app.callback(
            Output(f"filters-{prefix}-p2", "data"),
            Input(f"{prefix}-dim", "value", allow_optional=True),
            Input(f"{prefix}-type-p2", "value", allow_optional=True),
            Input(f"{prefix}-seat-p2", "value", allow_optional=True),
            prevent_initial_call=True
        )
        def _store_filters_p2_fleet(dims, type_filter=None, seat_filter=None, _prefix=prefix):
            dims = dims if isinstance(dims, list) else ([dims] if dims else [])
            payload = {"dims": dims, "year": None, "months": []}
            if type_filter:
                payload["type_filter"] = type_filter if isinstance(type_filter, list) else [type_filter]
            if seat_filter:
                payload["seat_filter"] = seat_filter if isinstance(seat_filter, list) else [seat_filter]
            return payload
        return

    @app.callback(
        Output(f"filters-{prefix}-p1", "data"),
        Input(f"{prefix}-year", "value", allow_optional=True),
        Input(f"{prefix}-month", "value", allow_optional=True),
        Input(f"{prefix}-type-p1", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _store_filters_p1(year_val, months, type_filter=None, _prefix=prefix):
        payload = {"year": year_val, "months": months or []}
        if type_filter:
            payload["type_filter"] = type_filter if isinstance(type_filter, list) else [type_filter]
        return payload

    @app.callback(
        Output(f"filters-{prefix}-p2", "data"),
        Input(f"{prefix}-dim", "value", allow_optional=True),
        Input(f"{prefix}-year-p2", "value", allow_optional=True),
        Input(f"{prefix}-month-p2", "value", allow_optional=True),
        Input(f"{prefix}-type-p2", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _store_filters_p2(dims, year_val, months, type_filter=None, _prefix=prefix):
        dims = dims if isinstance(dims, list) else ([dims] if dims else [])
        payload = {"dims": dims, "year": year_val, "months": months or []}
        if type_filter:
            payload["type_filter"] = type_filter if isinstance(type_filter, list) else [type_filter]
        return payload

    @app.callback(
        Output(f"{prefix}-month", "options"),
        Output(f"{prefix}-month", "value"),
        Input(f"{prefix}-year", "value", allow_optional=True),
        State(f"{prefix}-month", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _month_depends_on_year_p1(year_val, cur_months, _prefix=prefix):
        options, allowed = _month_options_for_year(year_val)
        cur_months = cur_months or []
        new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
        return options, new_val

    @app.callback(
        Output(f"{prefix}-month-p2", "options"),
        Output(f"{prefix}-month-p2", "value"),
        Input(f"{prefix}-year-p2", "value", allow_optional=True),
        State(f"{prefix}-month-p2", "value", allow_optional=True),
        prevent_initial_call=True
    )
    def _month_depends_on_year_p2(year_val, cur_months, _prefix=prefix):
        options, allowed = _month_options_for_year(year_val)
        cur_months = cur_months or []
        new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
        return options, new_val

for _prefix in EXTRA_DYNAMIC_PREFIXES:
    _register_simple_menu_callbacks(_prefix)

def _home_prev_period_metrics(dff_full: pd.DataFrame, selected_regions=None, current_month_ts=None):
    base = apply_region_scope_to_df(dff_full)
    base = _apply_real_data_cutoff(base)
    if selected_regions and "khu_vuc" in base.columns:
        sel = filter_regions_for_current_user(selected_regions if isinstance(selected_regions, list) else [selected_regions])
        base = base[base["khu_vuc"].astype(str).isin([str(x) for x in sel])] if sel else base.iloc[0:0].copy()
    if base.empty or "thang_nam_vn" not in base.columns:
        return {}
    g = base.groupby("thang_nam_vn", as_index=False).agg({
        "tong_doanh_thu": "sum" if "tong_doanh_thu" in base.columns else "count",
        "tong_so_cuoc": "sum" if "tong_so_cuoc" in base.columns else "count"
    }).sort_values("thang_nam_vn")
    if g.empty:
        return {}
    current_ts = current_month_ts if current_month_ts is not None else g["thang_nam_vn"].max()
    current_ts = pd.to_datetime(current_ts)
    prev_ts = (current_ts - pd.offsets.MonthBegin(1)).to_period("M").to_timestamp()
    cur = g[g["thang_nam_vn"] == current_ts]
    prv = g[g["thang_nam_vn"] == prev_ts]
    cur_rev = safe_number(cur["tong_doanh_thu"].sum()) if "tong_doanh_thu" in g.columns else 0.0
    cur_trip = safe_number(cur["tong_so_cuoc"].sum()) if "tong_so_cuoc" in g.columns else 0.0
    prv_rev = safe_number(prv["tong_doanh_thu"].sum()) if "tong_doanh_thu" in g.columns else 0.0
    prv_trip = safe_number(prv["tong_so_cuoc"].sum()) if "tong_so_cuoc" in g.columns else 0.0
    cur_avg = cur_rev / cur_trip if cur_trip else 0.0
    prv_avg = prv_rev / prv_trip if prv_trip else 0.0
    def _pct(cur_val, prev_val):
        if prev_val in [0, None]:
            return None
        return (cur_val - prev_val) / prev_val * 100.0
    return {
        "rev_pct": _pct(cur_rev, prv_rev),
        "trip_pct": _pct(cur_trip, prv_trip),
        "avg_pct": _pct(cur_avg, prv_avg),
        "current_ts": current_ts,
        "prev_ts": prev_ts,
        "cur_rev": cur_rev,
        "cur_trip": cur_trip,
        "prv_rev": prv_rev,
        "prv_trip": prv_trip
    }

def _delta_class(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "neutral"
    if float(v) > 0:
        return "positive"
    if float(v) < 0:
        return "negative"
    return "neutral"


HOME_OUTPUT_CACHE = {}
HOME_OUTPUT_CACHE_MAX = int(os.getenv("DASH_HOME_OUTPUT_CACHE_MAX", "96" if DASH_SERVERLESS_FAST_PRESET else "160"))


def _home_scope_cache_key():
    try:
        scope = current_user_region_scope()
        if scope is None:
            return "__all__"
        return tuple(sorted(str(x) for x in scope))
    except Exception:
        return "__na__"


def _home_output_cache_key(year_val, months, regions, theme):
    return (
        str(year_val or ""),
        tuple(sorted(_normalize_multi_value(months))),
        tuple(sorted(_normalize_multi_value(regions))),
        str(theme or "light"),
        _home_scope_cache_key(),
        _df_cache_signature(df_dt),
        _df_cache_signature(df_lh),
        _df_cache_signature(df_hd),
        str(DASH_DATA_VERSION),
        bool(DASH_HOME_LAZY_ZOOM_FIGURES),
        bool(DASH_ZOOM_STORE_INCLUDE_FIGURE),
        int(DASH_FIGURE_STORE_MAX_ROWS),
        int(_kpi_store_effective_row_limit([], DASH_KPI_STORE_MAX_ROWS)),
        "home-output-v2-lazy-zoom",
    )


def _home_output_cache_get(cache_key):
    cached = HOME_OUTPUT_CACHE.get(cache_key)
    return cached if cached is not None else None


def _home_output_cache_set(cache_key, value):
    try:
        if len(HOME_OUTPUT_CACHE) > HOME_OUTPUT_CACHE_MAX:
            HOME_OUTPUT_CACHE.clear()
        HOME_OUTPUT_CACHE[cache_key] = value
    except Exception:
        pass
    return value


def _table_records_for_dash(dff: pd.DataFrame, max_rows: int = 0) -> list:
    if not isinstance(dff, pd.DataFrame):
        return []
    out = dff
    try:
        limit = int(max_rows or 0)
    except Exception:
        limit = 0
    if limit > 0 and len(out) > limit:
        out = out.head(limit).copy()
    return out.to_dict("records")


@app.callback(
    Output("home-summary", "children"),
    Output("home-kpi1", "children"),
    Output("home-kpi2", "children"),
    Output("home-kpi3", "children"),
    Output("home-kpi4", "children"),
    Output("home-main", "figure"),
    Output("home-region-donut", "figure"),
    Output("home-region-bar", "figure"),
    Output("home-lh-donut", "figure"),
    Output("home-hd-bar", "figure"),
    Output("home-table", "data"),
    Output("home-table", "style_cell"),
    Output("home-table", "style_header"),

    Output({"type":"zoom-store","target":"home-kpi1"}, "data"),
    Output({"type":"zoom-store","target":"home-kpi2"}, "data"),
    Output({"type":"zoom-store","target":"home-kpi3"}, "data"),
    Output({"type":"zoom-store","target":"home-kpi4"}, "data"),
    Output({"type":"zoom-store","target":"home-main"}, "data"),
    Output({"type":"zoom-store","target":"home-region-donut"}, "data"),
    Output({"type":"zoom-store","target":"home-region-bar"}, "data"),
    Output({"type":"zoom-store","target":"home-lh-donut"}, "data"),
    Output({"type":"zoom-store","target":"home-hd-bar"}, "data"),

    Input("home-year", "value", allow_optional=True),
    Input("home-month", "value", allow_optional=True),
    Input("home-region", "value", allow_optional=True),
    State("theme", "data"),
)
@timed_callback("home")
def update_home(year_val, months, regions, theme):
    theme = theme or "light"
    regions = regions if isinstance(regions, list) else ([regions] if regions else [])
    home_cache_key = _home_output_cache_key(year_val, months or [], regions or [], theme)
    cached_home_output = _home_output_cache_get(home_cache_key)
    if cached_home_output is not None:
        return cached_home_output

    dff_dt = apply_common_filters(df_dt, year_val=year_val, months=months or [], dims=regions or [])
    dff_lh = apply_common_filters(df_lh, year_val=year_val, months=months or [], dims=regions or [])
    dff_hd = apply_common_filters(df_hd, year_val=year_val, months=months or [], dims=regions or [])

    year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
    month_txt = months[0] if isinstance(months, list) and len(months) == 1 else (f"{len(months)} tháng đã chọn" if months else "Tất cả tháng")
    region_txt = ", ".join(regions[:3]) if regions and len(regions) <= 3 else (f"{len(regions)} khu vực" if regions else ("Phạm vi tài khoản" if current_user_region_scope() is not None else "Tất cả khu vực"))

    summary_children = [
        summary_pill(year_txt, fa_icon("fa-calendar-days", 12, GREEN_PRIMARY)),
        summary_pill(month_txt, fa_icon("fa-clock", 12, GREEN_PRIMARY)),
        summary_pill(region_txt, fa_icon("fa-location-dot", 12, GREEN_PRIMARY)),
    ]

    total_rev = safe_number(dff_dt["tong_doanh_thu"].sum()) if "tong_doanh_thu" in dff_dt.columns else 0.0
    total_trip = safe_number(dff_dt["tong_so_cuoc"].sum()) if "tong_so_cuoc" in dff_dt.columns else (
        safe_number(dff_hd["tong_so_cuoc"].sum()) if "tong_so_cuoc" in dff_hd.columns else 0.0
    )
    avg_rev_trip = total_rev / total_trip if total_trip else 0.0
    active_regions = int(dff_dt["khu_vuc"].nunique()) if "khu_vuc" in dff_dt.columns and not dff_dt.empty else 0

    total_payload = region_payload_value(dff_dt, "tong_doanh_thu", selected_regions=regions or None, max_items=None) if "tong_doanh_thu" in dff_dt.columns else []
    trip_payload = region_payload_value(dff_dt, "tong_so_cuoc", selected_regions=regions or None, max_items=None) if "tong_so_cuoc" in dff_dt.columns else []
    avg_payload = region_payload_avg_revenue_per_trip(dff_dt, "tong_doanh_thu", selected_regions=regions or None, max_items=None) if "tong_doanh_thu" in dff_dt.columns and "tong_so_cuoc" in dff_dt.columns else []

    current_month_ts = dff_dt["thang_nam_vn"].max() if ("thang_nam_vn" in dff_dt.columns and not dff_dt.empty) else None
    compare = _home_prev_period_metrics(df_dt, selected_regions=regions or None, current_month_ts=current_month_ts)

    rev_delta_txt = f"{signed_pct_text(compare.get('rev_pct'))} so với tháng trước" if compare else "Không đủ dữ liệu so sánh"
    trip_delta_txt = f"{signed_pct_text(compare.get('trip_pct'))} so với tháng trước" if compare else "Không đủ dữ liệu so sánh"
    avg_delta_txt = f"{signed_pct_text(compare.get('avg_pct'))} so với tháng trước" if compare else "Không đủ dữ liệu so sánh"

    lead_region_name = total_payload[0]["khu_vuc"] if total_payload else "Không có dữ liệu"
    lead_region_pct = total_payload[0]["pct"] if total_payload else 0.0

    home_kpi1 = home_kpi_markup(
        fmt_vn(total_rev),
        f"{year_txt} • {month_txt}",
        rev_delta_txt,
        _delta_class(compare.get("rev_pct") if compare else None),
        region_value_lines_from_payload(total_payload, max_lines=3)
    )
    home_kpi2 = home_kpi_markup(
        fmt_vn(total_trip),
        f"{year_txt} • {month_txt}",
        trip_delta_txt,
        _delta_class(compare.get("trip_pct") if compare else None),
        region_value_lines_from_payload(trip_payload, max_lines=3)
    )
    home_kpi3 = home_kpi_markup(
        fmt_vn(avg_rev_trip),
        "Doanh thu trung bình trên mỗi cuốc",
        avg_delta_txt,
        _delta_class(compare.get("avg_pct") if compare else None),
        [_ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / cuốc']) for r in avg_payload[:3]]
    )
    home_kpi4 = home_kpi_markup(
        fmt_vn(active_regions),
        "Số khu vực có phát sinh doanh thu",
        f"Dẫn đầu: {lead_region_name} ({lead_region_pct:.1f}%)" if total_payload else "Chưa có khu vực dẫn đầu",
        "neutral",
        region_value_lines_from_payload(total_payload, max_lines=3)
    )

    home_kpi1_store = pack_kpi_store("Tổng doanh thu", fmt_vn(total_rev), f"{year_txt} • {month_txt}", total_payload)
    home_kpi2_store = pack_kpi_store("Tổng số cuốc", fmt_vn(total_trip), f"{year_txt} • {month_txt}", trip_payload)
    home_kpi3_store = pack_kpi_store("Doanh thu TB/cuốc", fmt_vn(avg_rev_trip), "So sánh theo khu vực", avg_payload)
    home_kpi4_store = pack_kpi_store("Khu vực hoạt động", fmt_vn(active_regions), f"Dẫn đầu: {lead_region_name}", total_payload)

    if not dff_dt.empty:
        g_month = dff_dt.groupby("thang_nam_vn", as_index=False).agg({
            "tong_doanh_thu": "sum",
            "tong_so_cuoc": "sum"
        }).sort_values("thang_nam_vn")
        g_month["thang_label"] = g_month["thang_nam_vn"].dt.strftime("%m/%Y")
        g_month["rev_fmt"] = g_month["tong_doanh_thu"].apply(fmt_vn)
        g_month["trip_fmt"] = g_month["tong_so_cuoc"].apply(fmt_vn)
        g_month["avg_per_trip"] = g_month["tong_doanh_thu"] / g_month["tong_so_cuoc"].replace(0, 1)
        g_month["avg_per_trip_fmt"] = g_month["avg_per_trip"].apply(fmt_vn)

        fig_home_main = make_subplots(specs=[[{"secondary_y": True}]])
        fig_home_main.add_trace(
            go.Bar(
                x=g_month["thang_nam_vn"],
                y=g_month["tong_doanh_thu"],
                name="Doanh thu",
                marker_color=GREEN_PRIMARY,
                customdata=np.stack([g_month["rev_fmt"], g_month["trip_fmt"], g_month["avg_per_trip_fmt"]], axis=-1),
                hovertemplate="Tháng: %{x|%m/%Y}<br>Doanh thu: %{customdata[0]}<br>Số cuốc: %{customdata[1]}<br>TB/cuốc: %{customdata[2]}<extra></extra>"
            ),
            secondary_y=False
        )
        fig_home_main.add_trace(
            go.Scatter(
                x=g_month["thang_nam_vn"],
                y=g_month["tong_so_cuoc"],
                mode="lines+markers+text",
                name="Số cuốc",
                line=dict(color=NAVY_PRIMARY, width=3),
                marker=dict(size=8, color=NAVY_PRIMARY),
                text=[v if len(g_month) <= 8 else "" for v in g_month["trip_fmt"]],
                textposition="top center",
                hovertemplate="Tháng: %{x|%m/%Y}<br>Số cuốc: %{y:,.0f}<extra></extra>"
            ),
            secondary_y=True
        )
        home_title_text = f"Doanh thu & số cuốc theo tháng<br>{year_txt} • {month_txt} • {region_txt}"
        fig_home_main.update_layout(
            title=_premium_chart_title_dict(home_title_text, theme=theme),
            plot_bgcolor=LIGHT_BG if theme == "light" else DARK_BG,
            paper_bgcolor=LIGHT_BG if theme == "light" else DARK_BG,
            font_color="black" if theme == "light" else "white",
            legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=_chart_title_margin(home_title_text, base_top=155, min_top=185, extra_per_line=32), b=20),
            title_automargin=True
        )
        fig_home_main.update_xaxes(
            tickformat="%m/%Y",
            dtick="M1",
            ticklabelmode="period",
            showgrid=True,
            gridcolor="#e5e7eb" if theme == "light" else "#333",
            showline=True,
            linecolor=GREEN_BORDER if theme == "light" else "#64748b",
            linewidth=1
        )
        fig_home_main.update_yaxes(
            title_text="Doanh thu",
            showgrid=True,
            gridcolor="#e5e7eb" if theme == "light" else "#333",
            showline=True,
            linecolor=GREEN_BORDER if theme == "light" else "#64748b",
            linewidth=1,
            secondary_y=False
        )
        fig_home_main.update_yaxes(
            title_text="Số cuốc",
            showline=True,
            linecolor=GREEN_BORDER if theme == "light" else "#64748b",
            linewidth=1,
            secondary_y=True
        )
        home_main_store = pack_home_fig_store(
            fig_home_main,
            rows=g_month[["thang_label", "rev_fmt", "trip_fmt", "avg_per_trip_fmt"]].to_dict("records"),
            meta={"chart": "home_combo", "metric_label": "Doanh thu & số cuốc"}
        )

        g_region = dff_dt.groupby("khu_vuc", as_index=False).agg({
            "tong_doanh_thu": "sum",
            "tong_so_cuoc": "sum"
        }).sort_values("tong_doanh_thu", ascending=False)
        g_region["rev_fmt"] = g_region["tong_doanh_thu"].apply(fmt_vn)
        g_region["trip_fmt"] = g_region["tong_so_cuoc"].apply(fmt_vn)

        fig_region_donut = make_vn_donut(
            g_region,
            names="khu_vuc",
            values="tong_doanh_thu",
            title=f"Cơ cấu doanh thu theo khu vực<br>{year_txt} • {month_txt}",
            max_slices=8,
            color_map=REGION_COLOR_MAP,
            theme=theme
        )
        home_region_donut_store = pack_home_fig_store(
            fig_region_donut,
            rows=[{"label": r["khu_vuc"], "metric": float(r["tong_doanh_thu"]), "metric_fmt": r["rev_fmt"]} for _, r in g_region.iterrows()],
            meta={"chart": "home_region_donut", "metric_label": "Doanh thu"}
        )

        g_top = g_region.head(8).copy()
        fig_region_bar = px.bar(
            g_top,
            y="khu_vuc",
            x="tong_doanh_thu",
            orientation="h",
            text="rev_fmt",
            color="khu_vuc",
            color_discrete_map=REGION_COLOR_MAP,
            hover_data={"rev_fmt": True, "tong_doanh_thu": False, "trip_fmt": True}
        )
        fig_region_bar.update_traces(textposition="outside", cliponaxis=False)
        fig_region_bar = apply_exec_layout(
            fig_region_bar,
            theme=theme,
            title=f"Top khu vực theo doanh thu<br>{year_txt} • {month_txt}",
            top=125,
            x_title="Doanh thu",
            y_title="Khu vực"
        )
        fig_region_bar.update_layout(showlegend=False)
        home_region_bar_store = pack_home_fig_store(
            fig_region_bar,
            rows=[{"khu_vuc": r["khu_vuc"], "metric": float(r["tong_doanh_thu"]), "metric_fmt": r["rev_fmt"]} for _, r in g_top.iterrows()],
            meta={"chart": "home_region_bar", "metric_label": "Doanh thu"}
        )

        if not dff_lh.empty and LH_COL in dff_lh.columns:
            g_lh = dff_lh.groupby(LH_COL, as_index=False).agg({"tong_doanh_thu": "sum"}).sort_values("tong_doanh_thu", ascending=False)
            g_lh["val_fmt"] = g_lh["tong_doanh_thu"].apply(fmt_vn)
            fig_lh = make_vn_donut(
                g_lh,
                names=LH_COL,
                values="tong_doanh_thu",
                title=f"Cơ cấu loại hình theo doanh thu<br>{year_txt} • {month_txt}",
                max_slices=8,
                theme=theme
            )
            home_lh_store = pack_home_fig_store(
                fig_lh,
                rows=[{"label": r[LH_COL], "metric": float(r["tong_doanh_thu"]), "metric_fmt": r["val_fmt"]} for _, r in g_lh.iterrows()],
                meta={"chart": "home_lh_donut", "metric_label": "Doanh thu"}
            )
        else:
            fig_lh = empty_figure("Không có dữ liệu loại hình", theme)
            home_lh_store = pack_home_fig_store(fig_lh, rows=[], meta={"chart": "home_lh_donut", "metric_label": "Doanh thu"})

        if not dff_hd.empty and HD_COL in dff_hd.columns and "tong_so_cuoc" in dff_hd.columns:
            g_hd = dff_hd.groupby(HD_COL, as_index=False).agg({"tong_so_cuoc": "sum"}).sort_values("tong_so_cuoc", ascending=False)
            g_hd["val_fmt"] = g_hd["tong_so_cuoc"].apply(fmt_vn)
            fig_hd = px.bar(
                g_hd,
                x=HD_COL,
                y="tong_so_cuoc",
                text="val_fmt",
                color=HD_COL,
                hover_data={"val_fmt": True, "tong_so_cuoc": False}
            )
            fig_hd.update_traces(textposition="outside", cliponaxis=False)
            fig_hd = apply_exec_layout(
                fig_hd,
                theme=theme,
                title=f"Cơ cấu hợp đồng theo số cuốc<br>{year_txt} • {month_txt}",
                top=125,
                x_title="Loại hợp đồng",
                y_title="Số cuốc"
            )
            fig_hd.update_layout(showlegend=False)
            home_hd_store = pack_home_fig_store(
                fig_hd,
                rows=[{"label": r[HD_COL], "metric": float(r["tong_so_cuoc"]), "metric_fmt": r["val_fmt"]} for _, r in g_hd.iterrows()],
                meta={"chart": "home_hd_bar", "metric_label": "Số cuốc"}
            )
        else:
            fig_hd = empty_figure("Không có dữ liệu hợp đồng", theme)
            home_hd_store = pack_home_fig_store(fig_hd, rows=[], meta={"chart": "home_hd_bar", "metric_label": "Số cuốc"})

        if "khu_vuc" in dff_dt.columns:
            g_top_region_month = dff_dt.groupby(["thang_label", "khu_vuc"], as_index=False)["tong_doanh_thu"].sum()
            g_top_region_month = g_top_region_month.sort_values(["thang_label", "tong_doanh_thu"], ascending=[True, False])
            top_region_map = g_top_region_month.drop_duplicates("thang_label").set_index("thang_label")["khu_vuc"].to_dict()
        else:
            top_region_map = {}

        snapshot = g_month.copy()
        snapshot["top_region"] = snapshot["thang_label"].map(top_region_map).fillna("")
        snapshot["tong_doanh_thu_fmt"] = snapshot["tong_doanh_thu"].apply(fmt_vn)
        snapshot["tong_so_cuoc_fmt"] = snapshot["tong_so_cuoc"].apply(fmt_vn)
        snapshot["avg_per_trip_fmt"] = snapshot["avg_per_trip"].apply(fmt_vn)
        home_table_data = snapshot.sort_values("thang_nam_vn", ascending=False)[
            ["thang_label", "tong_doanh_thu_fmt", "tong_so_cuoc_fmt", "avg_per_trip_fmt", "top_region"]
        ].to_dict("records")
    else:
        fig_home_main = empty_figure("Không có dữ liệu overview", theme)
        fig_region_donut = empty_figure("Không có dữ liệu khu vực", theme)
        fig_region_bar = empty_figure("Không có dữ liệu top khu vực", theme)
        fig_lh = empty_figure("Không có dữ liệu loại hình", theme)
        fig_hd = empty_figure("Không có dữ liệu hợp đồng", theme)
        home_table_data = []
        home_main_store = pack_home_fig_store(fig_home_main, rows=[], meta={"chart": "home_combo", "metric_label": "Doanh thu & số cuốc"})
        home_region_donut_store = pack_home_fig_store(fig_region_donut, rows=[], meta={"chart": "home_region_donut", "metric_label": "Doanh thu"})
        home_region_bar_store = pack_home_fig_store(fig_region_bar, rows=[], meta={"chart": "home_region_bar", "metric_label": "Doanh thu"})
        home_lh_store = pack_home_fig_store(fig_lh, rows=[], meta={"chart": "home_lh_donut", "metric_label": "Doanh thu"})
        home_hd_store = pack_home_fig_store(fig_hd, rows=[], meta={"chart": "home_hd_bar", "metric_label": "Số cuốc"})

    style_cell, style_header = _detail_table_theme_styles(theme, "home")

    result = (
        summary_children,
        home_kpi1,
        home_kpi2,
        home_kpi3,
        home_kpi4,
        fig_home_main,
        fig_region_donut,
        fig_region_bar,
        fig_lh,
        fig_hd,
        home_table_data,
        style_cell,
        style_header,
        home_kpi1_store,
        home_kpi2_store,
        home_kpi3_store,
        home_kpi4_store,
        home_main_store,
        home_region_donut_store,
        home_region_bar_store,
        home_lh_store,
        home_hd_store
    )
    return _home_output_cache_set(home_cache_key, result)


@app.callback(
    Output("daily-summary", "children"),
    Output("daily-kpi1", "children"),
    Output("daily-kpi2", "children"),
    Output("daily-kpi3", "children"),
    Output("daily-kpi4", "children"),
    Output("daily-main", "figure"),
    Output("daily-region-donut", "figure"),
    Output("daily-region-bar", "figure"),
    Output("daily-lh-donut", "figure"),
    Output("daily-hd-bar", "figure"),
    Output("daily-table", "data"),
    Output("daily-table", "style_cell"),
    Output("daily-table", "style_header"),
    Output({"type":"zoom-store","target":"daily-kpi1"}, "data"),
    Output({"type":"zoom-store","target":"daily-kpi2"}, "data"),
    Output({"type":"zoom-store","target":"daily-kpi3"}, "data"),
    Output({"type":"zoom-store","target":"daily-kpi4"}, "data"),
    Output({"type":"zoom-store","target":"daily-main"}, "data"),
    Output({"type":"zoom-store","target":"daily-region-donut"}, "data"),
    Output({"type":"zoom-store","target":"daily-region-bar"}, "data"),
    Output({"type":"zoom-store","target":"daily-lh-donut"}, "data"),
    Output({"type":"zoom-store","target":"daily-hd-bar"}, "data"),
    Input("daily-date-range", "start_date", allow_optional=True),
    Input("daily-date-range", "end_date", allow_optional=True),
    Input("daily-region", "value", allow_optional=True),
    Input("daily-driver", "value", allow_optional=True),
    Input("daily-vehicle-type", "value", allow_optional=True),
    Input("daily-business-type", "value", allow_optional=True),
    State("theme", "data"),
)
@timed_callback("daily_latest")
def update_daily_latest(start_date, end_date, regions, drivers, vehicle_types, business_types, theme):
    ensure_daily_data_loaded()
    theme = theme or "light"
    regions = _normalize_multi_value(regions)
    drivers = _normalize_multi_value(drivers)
    vehicle_types = _normalize_multi_value(vehicle_types)
    business_types = _normalize_multi_value(business_types)
    daily_source_label = _daily_source_label()
    source_dt, source_lh, source_hd = _daily_sources_for_driver_filter(drivers)
    source_cross = _daily_cross_source_df(drivers) if (vehicle_types or business_types) else pd.DataFrame()
    daily_cache_key = _daily_output_cache_key(start_date, end_date, regions, drivers, vehicle_types, business_types, None, theme, source_dt, source_lh, source_hd, source_cross)
    cached_daily_output = _daily_output_cache_get(daily_cache_key)
    if cached_daily_output is not None:
        return cached_daily_output
    dff_dt = _filter_daily_frame(source_dt, start_date, end_date, regions, source_label=daily_source_label, drivers=drivers)
    dff_lh = _filter_daily_frame(source_lh, start_date, end_date, regions, source_label="Loại hình ngày", drivers=drivers)
    dff_hd = _filter_daily_frame(source_hd, start_date, end_date, regions, source_label="Cơ cấu vận hành ngày", drivers=drivers)
    dff_cross = pd.DataFrame()
    if isinstance(source_cross, pd.DataFrame) and not source_cross.empty and (vehicle_types or business_types):
        dff_cross = _filter_daily_frame(source_cross, start_date, end_date, regions, source_label="Loại hình + hình thức ngày", drivers=drivers)
        if vehicle_types:
            dff_cross = _filter_daily_vehicle_type_frame(dff_cross, vehicle_types)
        if business_types:
            dff_cross = _filter_daily_business_type_frame(dff_cross, business_types)

    if vehicle_types:
        dff_lh = _filter_daily_vehicle_type_frame(dff_lh, vehicle_types)
        if _daily_frame_has_vehicle_type(dff_dt):
            dff_dt = _filter_daily_vehicle_type_frame(dff_dt, vehicle_types)
        else:
            dff_dt = _daily_metric_frame_from_lh(dff_lh)
        dff_hd = _filter_daily_vehicle_type_frame(dff_hd, vehicle_types)
    if business_types:
        dff_hd = _filter_daily_business_type_frame(dff_hd, business_types)
        if _daily_frame_has_business_type(dff_dt):
            dff_dt = _filter_daily_business_type_frame(dff_dt, business_types)
        else:
            dff_dt = _daily_metric_frame_from_business_type(dff_hd)
        if _daily_frame_has_business_type(dff_lh):
            dff_lh = _filter_daily_business_type_frame(dff_lh, business_types)
    if (vehicle_types or business_types) and isinstance(dff_cross, pd.DataFrame) and not dff_cross.empty:
        # Prefer true intersection sheet when refresh_data.py has produced it.
        dff_dt = dff_cross.copy(deep=False)
        dff_lh = dff_cross.copy(deep=False)
        dff_hd = dff_cross.copy(deep=False)
    date_txt = _format_date_range_text(start_date, end_date)
    region_txt = ", ".join(regions[:3]) if regions and len(regions) <= 3 else (f"{len(regions)} khu vực" if regions else ("Phạm vi tài khoản" if current_user_region_scope() is not None else "Tất cả khu vực"))
    driver_txt = ", ".join(drivers[:2]) if drivers and len(drivers) <= 2 else (f"{len(drivers)} tài xế" if drivers else "Tất cả tài xế")
    vehicle_type_txt = ", ".join(vehicle_types[:2]) if vehicle_types and len(vehicle_types) <= 2 else (f"{len(vehicle_types)} phân loại xe" if vehicle_types else "Tất cả phân loại xe")
    business_type_txt = ", ".join(business_types[:2]) if business_types and len(business_types) <= 2 else (f"{len(business_types)} hình thức KD" if business_types else "Tất cả hình thức KD")
    summary_children = [
        summary_pill(date_txt, fa_icon("fa-calendar-day", 12, GREEN_PRIMARY)),
        summary_pill(region_txt, fa_icon("fa-map-location-dot", 12, GREEN_PRIMARY)),
        summary_pill(driver_txt, fa_icon("fa-id-card", 12, GREEN_PRIMARY)),
        summary_pill(vehicle_type_txt, fa_icon("fa-car-side", 12, GREEN_PRIMARY)),
        summary_pill(business_type_txt, fa_icon("fa-charging-station", 12, GREEN_PRIMARY)),
        summary_pill(daily_source_label, fa_icon("fa-database", 12, GREEN_PRIMARY)),
        html.Span([fa_icon("fa-bolt", 11, GREEN_PRIMARY), html.Span("30 ngày gần nhất", className="ms-1")], className="daily-latest-badge"),
    ]

    style_cell, style_header = _detail_table_theme_styles(theme, "dt")

    daily_views = _daily_filtered_agg_view(dff_dt)
    region_g = daily_views.get("region", pd.DataFrame())
    g_day = daily_views.get("day", pd.DataFrame())

    total_rev = float(pd.to_numeric(region_g.get("tong_doanh_thu", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
    total_trip = float(pd.to_numeric(region_g.get("tong_so_cuoc", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
    total_km = float(pd.to_numeric(region_g.get("sokm_vandoanh", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
    paid_km = float(pd.to_numeric(region_g.get("sokm_cokhach", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
    km_paid_ratio = paid_km / total_km * 100.0 if total_km else 0.0
    avg_rev_trip = total_rev / total_trip if total_trip else 0.0
    vehicle_days = float(pd.to_numeric(region_g.get("so_xe", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
    avg_rev_vehicle_day = total_rev / vehicle_days if vehicle_days else 0.0
    active_regions = int(region_g["khu_vuc"].nunique()) if (not region_g.empty and "khu_vuc" in region_g.columns) else 0
    unique_counts = _daily_unique_operating_counts(start_date, end_date, regions, drivers, vehicle_types, business_types, None)
    if unique_counts is not None:
        active_vehicles = float(unique_counts.get("vehicles", 0))
        active_drivers = float(unique_counts.get("drivers", 0))
        active_regions = int(unique_counts.get("regions", active_regions))
    else:
        active_vehicles = float(pd.to_numeric(region_g.get("so_xe", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
        active_drivers = float(pd.to_numeric(region_g.get("so_tai_xe", 0), errors="coerce").fillna(0).sum()) if not region_g.empty else 0.0
    latest_label = "Không có dữ liệu"
    if not dff_dt.empty and "ngay_du_lieu" in dff_dt.columns:
        try:
            latest_label = pd.to_datetime(dff_dt["ngay_du_lieu"], errors="coerce").dropna().max().strftime("%d/%m/%Y")
        except Exception:
            latest_label = date_txt

    total_payload = _complete_daily_value_payload(
        _daily_payload_from_region_view(region_g, "tong_doanh_thu", regions),
        regions,
        value_key="value",
        fmt_key="value_fmt",
        pct_key="pct",
    )
    trip_payload = _complete_daily_value_payload(
        _daily_payload_from_region_view(region_g, "tong_so_cuoc", regions),
        regions,
        value_key="value",
        fmt_key="value_fmt",
        pct_key="pct",
    )
    avg_payload = _complete_daily_avg_payload(
        _daily_avg_payload_from_region_view(region_g, regions),
        regions,
    )
    vehicle_payload = _complete_daily_vehicle_payload(
        _daily_vehicle_kpi_payload(start_date, end_date, regions, drivers, vehicle_types, business_types, None, metric_frame=dff_dt, max_items=None),
        regions,
    )

    daily_kpi1 = home_kpi_markup(fmt_vn(total_rev), f"Doanh thu • {date_txt}", extra_lines=region_value_lines_from_payload(total_payload, 4))
    daily_kpi2 = home_kpi_markup(fmt_vn(total_trip), f"Số cuốc • {date_txt}", extra_lines=region_value_lines_from_payload(trip_payload, 4))
    daily_kpi3 = home_kpi_markup(fmt_vn(avg_rev_trip), f"TB/cuốc • KM khách {fmt_pct(km_paid_ratio, 1)}", extra_lines=region_value_lines_from_payload(avg_payload, 4, value_key="avg_fmt", pct_key=None))
    daily_kpi4 = home_kpi_markup(
        fmt_vn(active_vehicles),
        f"Xe hoạt động • {fmt_vn(active_drivers)} tài xế",
        extra_lines=[
            _ellipsis_div([fa_icon("fa-car-side", 11, GREEN_PRIMARY), html.Span(f" Lượt xe kinh doanh-ngày {fmt_vn(vehicle_days)} • DT TB/xe KD-ngày {fmt_vn(avg_rev_vehicle_day)}", className="ms-1")]),
            _ellipsis_div([fa_icon("fa-road", 11, GREEN_PRIMARY), html.Span(f" {fmt_vn(total_km)} KM vận doanh • mới nhất {latest_label}", className="ms-1")]),
        ],
    )

    daily_kpi1_store = pack_kpi_store("Doanh thu theo ngày", fmt_vn(total_rev), date_txt, total_payload)
    daily_kpi2_store = pack_kpi_store("Số cuốc theo ngày", fmt_vn(total_trip), date_txt, trip_payload)
    daily_kpi3_store = pack_kpi_store("TB / cuốc", fmt_vn(avg_rev_trip), f"KM khách {fmt_pct(km_paid_ratio, 1)}", avg_payload)
    daily_kpi4_store = pack_kpi_store("Xe hoạt động", fmt_vn(active_vehicles), f"{fmt_vn(active_drivers)} tài xế • Lượt xe KD-ngày {fmt_vn(vehicle_days)} • DT TB/xe KD-ngày {fmt_vn(avg_rev_vehicle_day)}", vehicle_payload)

    if dff_dt.empty:
        fig_empty = empty_figure("Không có dữ liệu theo ngày", theme)
        empty_store = pack_daily_fig_store(fig_empty, rows=[], meta={"chart": "daily_empty", "metric_label": "Dữ liệu theo ngày"})
        result = (
            summary_children, daily_kpi1, daily_kpi2, daily_kpi3, daily_kpi4,
            fig_empty, fig_empty, fig_empty, fig_empty, fig_empty,
            [], style_cell, style_header,
            daily_kpi1_store, daily_kpi2_store, daily_kpi3_store, daily_kpi4_store,
            empty_store, empty_store, empty_store, empty_store, empty_store,
        )
        return _daily_output_cache_set(daily_cache_key, result)

    # g_day and region_g were pre-grouped once in _daily_filtered_agg_view().

    fig_daily_main = make_subplots(specs=[[{"secondary_y": True}]])
    fig_daily_main.add_trace(
        go.Bar(
            x=g_day["ngay_du_lieu"],
            y=g_day["tong_doanh_thu"],
            name="Doanh thu",
            marker_color=GREEN_PRIMARY,
            customdata=np.stack([g_day["ngay_label"], g_day["rev_fmt"], g_day["trip_fmt"], g_day["avg_per_trip_fmt"]], axis=-1),
            hovertemplate="Ngày: %{customdata[0]}<br>Doanh thu: %{customdata[1]}<br>Số cuốc: %{customdata[2]}<br>TB/cuốc: %{customdata[3]}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig_daily_main.add_trace(
        go.Scatter(
            x=g_day["ngay_du_lieu"],
            y=g_day["tong_so_cuoc"],
            mode="lines+markers+text",
            name="Số cuốc",
            line=dict(color=NAVY_PRIMARY, width=3),
            marker=dict(size=8, color=NAVY_PRIMARY),
            text=[v if len(g_day) <= 10 else "" for v in g_day["trip_fmt"]],
            textposition="top center",
            hovertemplate="Ngày: %{x|%d/%m/%Y}<br>Số cuốc: %{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig_daily_main.add_trace(
        go.Scatter(
            x=g_day["ngay_du_lieu"],
            y=g_day["rev_ma7"],
            mode="lines",
            name="Xu hướng DT 7 ngày",
            line=dict(color=AMBER_PRIMARY, width=3, dash="dot"),
            customdata=np.stack([g_day["ngay_label"], g_day["rev_ma7_fmt"]], axis=-1),
            hovertemplate="Ngày: %{customdata[0]}<br>Xu hướng DT 7 ngày: %{customdata[1]}<extra></extra>",
        ),
        secondary_y=False,
    )
    daily_title = f"Doanh thu & số cuốc theo ngày<br>{date_txt} • {region_txt} • {vehicle_type_txt} • {business_type_txt}"
    fig_daily_main.update_layout(
        plot_bgcolor=LIGHT_BG if theme == "light" else DARK_BG,
        paper_bgcolor=LIGHT_BG if theme == "light" else DARK_BG,
        font_color="black" if theme == "light" else "white",
        legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0),
        hovermode="x unified",
        title=_premium_chart_title_dict(daily_title, theme=theme),
        margin=dict(l=20, r=20, t=_chart_title_margin(daily_title, base_top=155, min_top=190, extra_per_line=32), b=20),
        title_automargin=True,
    )
    fig_daily_main.update_xaxes(tickformat="%d/%m/%Y", showgrid=True, gridcolor="#e5e7eb" if theme == "light" else "#333", automargin=True)
    fig_daily_main.update_yaxes(title_text="Doanh thu", secondary_y=False, gridcolor="#e5e7eb" if theme == "light" else "#333", automargin=True)
    fig_daily_main.update_yaxes(title_text="Số cuốc", secondary_y=True, showgrid=False, automargin=True)
    daily_main_store = pack_daily_fig_store(fig_daily_main, rows=g_day[["ngay_label", "rev_fmt", "trip_fmt", "avg_per_trip_fmt", "rev_ma7_fmt"]].to_dict("records"), meta={"chart": "daily_combo", "metric_label": "Doanh thu & số cuốc"})

    fig_region_donut = make_vn_donut(region_g, names="khu_vuc", values="tong_doanh_thu", title=f"Tỷ trọng doanh thu theo khu vực<br>{date_txt}", max_slices=8, color_map=REGION_COLOR_MAP, theme=theme)
    daily_region_donut_store = pack_daily_fig_store(fig_region_donut, rows=region_g[["khu_vuc", "rev_fmt"]].to_dict("records"), meta={"chart": "daily_region_donut", "metric_label": "Doanh thu"})

    top_region = region_g.head(10).copy()
    fig_region_bar = px.bar(top_region.sort_values("tong_doanh_thu", ascending=True), x="tong_doanh_thu", y="khu_vuc", orientation="h", text="rev_fmt", color="khu_vuc", color_discrete_map=REGION_COLOR_MAP, hover_data={"rev_fmt": True, "tong_doanh_thu": False})
    fig_region_bar.update_traces(textposition="outside", cliponaxis=False)
    fig_region_bar.update_layout(showlegend=False)
    fig_region_bar = apply_exec_layout(fig_region_bar, theme=theme, title=f"Top khu vực theo doanh thu<br>{date_txt}", top=155, x_title="Doanh thu", y_title="Khu vực")
    daily_region_bar_store = pack_daily_fig_store(fig_region_bar, rows=top_region[["khu_vuc", "rev_fmt"]].to_dict("records"), meta={"chart": "daily_region_bar", "metric_label": "Doanh thu"})

    daily_lh_col = find_col_fuzzy(dff_lh, ["loai_hinh_std", "loaihinh_hoptac", "loại hình hợp tác", "loai hinh hop tac", "loai_hinh", "loại hình"]) if not dff_lh.empty else None
    if not dff_lh.empty and daily_lh_col in dff_lh.columns:
        lh_work = dff_lh.copy()
        lh_work["daily_lh_label"] = map_to_canon(lh_work[daily_lh_col], LH_MAP) if daily_lh_col != "loai_hinh_std" else lh_work[daily_lh_col].fillna("Khác")
        lh_g = lh_work.groupby("daily_lh_label", as_index=False)["tong_doanh_thu"].sum().sort_values("tong_doanh_thu", ascending=False)
        lh_g["rev_fmt"] = lh_g["tong_doanh_thu"].apply(fmt_vn)
        fig_lh = make_vn_donut(lh_g, names="daily_lh_label", values="tong_doanh_thu", title=f"Cơ cấu loại hình theo doanh thu ngày<br>{date_txt}", max_slices=8, color_map=None, theme=theme)
        daily_lh_store = pack_daily_fig_store(fig_lh, rows=lh_g[["daily_lh_label", "rev_fmt"]].to_dict("records"), meta={"chart": "daily_lh_donut", "metric_label": "Doanh thu", "series_field": "daily_lh_label"})
    else:
        fig_lh = empty_figure("Không có dữ liệu loại hình", theme)
        daily_lh_store = pack_daily_fig_store(fig_lh, rows=[], meta={"chart": "daily_lh_donut", "metric_label": "Doanh thu"})

    daily_mix_col = None
    daily_mix_label = "Loại hợp đồng"
    daily_mix_metric = "tong_so_cuoc"
    daily_mix_metric_label = "Số cuốc"
    daily_mix_title = "Số cuốc theo loại hợp đồng"
    if not dff_hd.empty:
        for candidates, label, metric, metric_label, title in [
            (["hinhthuc_kinhdoanh", "hình thức kinh doanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh"], "Hình thức kinh doanh", "tong_doanh_thu", "Doanh thu", "Doanh thu theo hình thức kinh doanh"),
            (["loai_luong", "loại lương", "loai luong"], "Loại lương", "tong_doanh_thu", "Doanh thu", "Doanh thu theo loại lương"),
            (["so_cho", "số chỗ", "so cho"], "Số chỗ", "tong_doanh_thu", "Doanh thu", "Doanh thu theo số chỗ"),
            (["loai_hop_dong_std", "loai_hopdong", "loại hợp đồng", "loai hop dong"], "Loại hợp đồng", "tong_so_cuoc", "Số cuốc", "Số cuốc theo loại hợp đồng"),
        ]:
            col = find_col_fuzzy(dff_hd, candidates)
            if col is not None and col in dff_hd.columns:
                daily_mix_col = col
                daily_mix_label = label
                daily_mix_metric = metric if metric in dff_hd.columns else "tong_so_cuoc"
                daily_mix_metric_label = metric_label if daily_mix_metric == metric else "Số cuốc"
                daily_mix_title = title if daily_mix_metric == metric else "Số cuốc theo loại hợp đồng"
                break
    if not dff_hd.empty and daily_mix_col in dff_hd.columns:
        if str(daily_mix_col) == "hinhthuc_kinhdoanh":
            dff_hd = dff_hd.copy()
            dff_hd[daily_mix_col] = _daily_business_type_label_series(dff_hd, daily_mix_col)
        hd_g = dff_hd.groupby(daily_mix_col, as_index=False)[daily_mix_metric].sum().sort_values(daily_mix_metric, ascending=False)
        hd_g["metric_fmt"] = hd_g[daily_mix_metric].apply(fmt_vn)
        fig_hd = px.bar(hd_g.sort_values(daily_mix_metric, ascending=True), x=daily_mix_metric, y=daily_mix_col, orientation="h", text="metric_fmt", hover_data={"metric_fmt": True, daily_mix_metric: False})
        fig_hd.update_traces(textposition="outside", cliponaxis=False, marker_color=GREEN_PRIMARY)
        fig_hd = apply_exec_layout(fig_hd, theme=theme, title=f"{daily_mix_title}<br>{date_txt}", top=155, x_title=daily_mix_metric_label, y_title=daily_mix_label)
        daily_hd_store = pack_daily_fig_store(fig_hd, rows=hd_g[[daily_mix_col, "metric_fmt"]].to_dict("records"), meta={"chart": "daily_mix_bar", "metric_label": daily_mix_metric_label, "series_field": daily_mix_col})
    else:
        fig_hd = empty_figure("Không có dữ liệu cơ cấu vận hành ngày", theme)
        daily_hd_store = pack_daily_fig_store(fig_hd, rows=[], meta={"chart": "daily_mix_bar", "metric_label": "Doanh thu"})

    daily_table_view = daily_views.get("table", pd.DataFrame())
    if isinstance(daily_table_view, pd.DataFrame):
        daily_table_data = _table_records_for_dash(daily_table_view, DASH_DAILY_TABLE_MAX_ROWS)
    else:
        daily_table_data = _table_records_for_dash(_daily_table_frame(dff_dt), DASH_DAILY_TABLE_MAX_ROWS)

    result = (
        summary_children,
        daily_kpi1,
        daily_kpi2,
        daily_kpi3,
        daily_kpi4,
        fig_daily_main,
        fig_region_donut,
        fig_region_bar,
        fig_lh,
        fig_hd,
        daily_table_data,
        style_cell,
        style_header,
        daily_kpi1_store,
        daily_kpi2_store,
        daily_kpi3_store,
        daily_kpi4_store,
        daily_main_store,
        daily_region_donut_store,
        daily_region_bar_store,
        daily_lh_store,
        daily_hd_store,
    )
    return _daily_output_cache_set(daily_cache_key, result)


BB_METRIC_ORDER = ["so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no"]
BB_METRIC_LABELS = {
    "so_tien_thu_duoc": "Số tiền đã xử lý",
    "so_tien_da_xu_ly": "Số tiền biên bản ghi nhận",
    "so_tien_con_no": "Số tiền chênh lệch",
}
BB_METRIC_COLOR_MAP = {
    "Số tiền đã xử lý": GREEN_PRIMARY,
    "Số tiền biên bản ghi nhận": NAVY_PRIMARY,
    "Số tiền chênh lệch": AMBER_PRIMARY,
}


def _bb_metric_long_df(dff: pd.DataFrame, group_cols):
    if dff is None or dff.empty:
        return pd.DataFrame(columns=list(group_cols) + ["metric_key", "metric_label", "gia_tri", "metric_fmt"])
    metric_cols = [c for c in BB_METRIC_ORDER if c in dff.columns]
    if not metric_cols:
        return pd.DataFrame(columns=list(group_cols) + ["metric_key", "metric_label", "gia_tri", "metric_fmt"])
    out = dff.groupby(list(group_cols), as_index=False)[metric_cols].sum()
    out = out.melt(id_vars=list(group_cols), value_vars=metric_cols, var_name="metric_key", value_name="gia_tri")
    out["metric_label"] = out["metric_key"].map(BB_METRIC_LABELS).fillna(out["metric_key"])
    out["metric_fmt"] = out["gia_tri"].apply(fmt_vn)
    return out


def _bb_table_frame(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame(columns=[
            "thang_nam", "khu_vuc", "so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
            "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no"
        ])
    out = dff.copy().sort_values([c for c in ["thang_nam_vn", "khu_vuc"] if c in dff.columns]).reset_index(drop=True)
    if "thang_nam_vn" in out.columns:
        out["thang_nam"] = pd.to_datetime(out["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y").fillna("")
    elif "thang_nam" in out.columns:
        out["thang_nam"] = pd.to_datetime(out["thang_nam"], errors="coerce").dt.strftime("%m/%Y").fillna("")
    keep_cols = [
        "thang_nam", "khu_vuc", "so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
        "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no"
    ]
    for c in keep_cols:
        if c not in out.columns:
            out[c] = 0 if c not in ["thang_nam", "khu_vuc"] else ""
    for c in ["so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat", "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).apply(fmt_vn)
    return out[keep_cols].copy()


BB_DRILL_VALUE_COLUMNS = [
    "so_bien_ban", "so_bien_ban_da_xu_ly", "so_bien_ban_thu_hoan_tat",
    "tong_tien_de_xuat", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no",
]
BB_DRILL_METRIC_LABELS = [BB_METRIC_LABELS[k] for k in BB_METRIC_ORDER]


def _bb_drill_rows(dff: pd.DataFrame, group_cols, metric_labels=None, label_from: str | None = None, label_col: str | None = None) -> list:
    """Build wide drill-down rows for Biên bản charts only.

    Chart traces may be long-form, but the drill-down table must show all money
    fields for the clicked point instead of only the selected series.
    """
    if dff is None or not isinstance(dff, pd.DataFrame) or dff.empty:
        return []
    group_cols = [c for c in (group_cols if isinstance(group_cols, (list, tuple)) else [group_cols]) if c in dff.columns]
    value_cols = [c for c in BB_DRILL_VALUE_COLUMNS if c in dff.columns]
    if not group_cols or not value_cols:
        return []
    try:
        g = dff.groupby(group_cols, as_index=False)[value_cols].sum()
    except Exception:
        return []

    if "thang_nam_vn" in g.columns and "thang_label" not in g.columns:
        try:
            g["thang_label"] = pd.to_datetime(g["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y").fillna("")
        except Exception:
            g["thang_label"] = g["thang_nam_vn"].astype(str)
    if label_col and label_from and label_from in g.columns:
        g[label_col] = g[label_from].astype(str)

    context_cols = []
    for c in ["thang_label", "thang", "khu_vuc", "label"]:
        if c in g.columns and c not in context_cols:
            context_cols.append(c)
    ordered_cols = context_cols + [c for c in BB_DRILL_VALUE_COLUMNS if c in g.columns]
    base_rows = g[ordered_cols].to_dict("records")

    if metric_labels:
        out = []
        for row in base_rows:
            for metric_label in metric_labels:
                rr = dict(row)
                rr["metric_label"] = str(metric_label)
                out.append(rr)
        return out
    return base_rows


def callbacks(prefix: str):
    cfg = get_menu_config(prefix)
    df = cfg["df"]
    value_col = cfg["value_col"]
    metric_label = cfg.get("metric_label", "Giá trị")
    metric_axis = metric_label
    secondary_col = cfg.get("secondary_col", "tong_so_cuoc")
    secondary_label = cfg.get("secondary_label", "Quy mô")
    avg_label = cfg.get("avg_label", "Trung bình")
    avg_mode = cfg.get("avg_mode", "per_secondary")
    avg_divisor_label = cfg.get("avg_divisor_label", secondary_label.lower())
    avg_numerator_col = cfg.get("avg_numerator_col", value_col)
    avg_denominator_col = cfg.get("avg_denominator_col", secondary_col)
    fleet_unit = cfg.get("fleet_unit", "xe")
    type_filter_kind = cfg.get("type_filter_kind")

    p1_filter_input = None
    p2_filter_input = None
    p1_business_filter_input = None
    p2_business_filter_input = None
    p1_seat_filter_input = None
    p2_seat_filter_input = None
    if type_filter_kind == "lh":
        p1_filter_input = Input("lh-type-p1", "value", allow_optional=True)
        p2_filter_input = Input("lh-type-p2", "value", allow_optional=True)
        p1_business_filter_input = Input("lh-business-type-p1", "value", allow_optional=True)
        p2_business_filter_input = Input("lh-business-type-p2", "value", allow_optional=True)
    elif type_filter_kind == "hd":
        p1_filter_input = Input("hd-type-p1", "value", allow_optional=True)
        p2_filter_input = Input("hd-type-p2", "value", allow_optional=True)
    elif type_filter_kind == "fleet":
        p1_filter_input = Input(f"{prefix}-type-p1", "value", allow_optional=True)
        p2_filter_input = Input(f"{prefix}-type-p2", "value", allow_optional=True)
        p1_seat_filter_input = Input(f"{prefix}-seat-p1", "value", allow_optional=True)
        p2_seat_filter_input = Input(f"{prefix}-seat-p2", "value", allow_optional=True)

    def _apply_type_filter(dff: pd.DataFrame, type_filter):
        if type_filter_kind == "lh" and type_filter and LH_COL in dff.columns:
            return dff[dff[LH_COL].astype(str).isin(type_filter)]
        if type_filter_kind == "hd" and type_filter and HD_COL in dff.columns:
            return dff[dff[HD_COL].astype(str).isin(type_filter)]
        if type_filter_kind == "fleet" and type_filter and "loai_xe" in dff.columns:
            return dff[dff["loai_xe"].astype(str).isin(type_filter)]
        return dff

    def _apply_fleet_seat_filter(dff: pd.DataFrame, seat_filter):
        if type_filter_kind != "fleet" or not seat_filter:
            return dff
        raw_vals = seat_filter if isinstance(seat_filter, list) else [seat_filter]
        seat_vals = []
        for x in raw_vals:
            try:
                seat_vals.append(int(float(x)))
            except Exception:
                continue
        seat_vals = sorted(set([x for x in seat_vals if x > 0]))
        if not seat_vals:
            return dff
        if "so_cho_loc" in dff.columns:
            seat_series = pd.to_numeric(dff["so_cho_loc"], errors="coerce").fillna(0).round().astype(int)
        elif "so_cho_binh_quan_xe" in dff.columns:
            seat_series = pd.to_numeric(dff["so_cho_binh_quan_xe"], errors="coerce").fillna(0).round().astype(int)
        else:
            return dff
        return dff[seat_series.isin(seat_vals)]

    def _avg_payload_and_lines(dff: pd.DataFrame, dims=None):
        if avg_mode == "per_month":
            avg_payload = region_payload_avg_metric_per_month(dff, value_col, selected_regions=dims, max_items=None)
            avg_lines = [
                _ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / tháng']) for r in avg_payload[:6]
            ]
            return avg_payload, avg_lines
        avg_payload = region_payload_avg_ratio(dff, avg_numerator_col, avg_denominator_col, selected_regions=dims, max_items=None)
        avg_lines = [
            _ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / {avg_divisor_label}']) for r in avg_payload[:6]
        ]
        return avg_payload, avg_lines

    if type_filter_kind == "fleet":
        inputs_p1 = []
    else:
        inputs_p1 = [
            Input(f"{prefix}-year", "value", allow_optional=True),
            Input(f"{prefix}-month", "value", allow_optional=True),
        ]
    if p1_filter_input is not None:
        inputs_p1.append(p1_filter_input)
    if p1_business_filter_input is not None:
        inputs_p1.append(p1_business_filter_input)
    if p1_seat_filter_input is not None:
        inputs_p1.append(p1_seat_filter_input)

    @app.callback(
        Output(f"{prefix}-p1-kpi1","children"),
        Output(f"{prefix}-p1-kpi2","children"),
        Output(f"{prefix}-p1-kpi3","children"),
        Output(f"{prefix}-p1-line-kv","figure"),
        Output(f"{prefix}-p1-line","figure"),
        Output(f"{prefix}-p1-bar","figure"),
        Output(f"{prefix}-p1-pie","figure"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi1"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi2"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi3"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-line-kv"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-line"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-bar"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-pie"}, "data"),
        *inputs_p1,
        State("theme", "data"),
        State("menu", "data"),
        State("page", "data"),
    )
    @timed_callback(f"{prefix}.p1")
    @timed_callback(f"{prefix}.hr_p1")
    def p1(*args):
        nonlocal cfg, df, value_col, metric_label, metric_axis, secondary_col, secondary_label, avg_label, avg_mode, avg_divisor_label, avg_numerator_col, avg_denominator_col, fleet_unit, type_filter_kind
        ensure_menu_data_loaded(prefix)
        cfg = get_menu_config(prefix)
        df = cfg["df"]
        value_col = cfg["value_col"]
        metric_label = cfg.get("metric_label", "Giá trị")
        metric_axis = metric_label
        secondary_col = cfg.get("secondary_col", "tong_so_cuoc")
        secondary_label = cfg.get("secondary_label", "Quy mô")
        avg_label = cfg.get("avg_label", "Trung bình")
        avg_mode = cfg.get("avg_mode", "per_secondary")
        avg_divisor_label = cfg.get("avg_divisor_label", secondary_label.lower())
        avg_numerator_col = cfg.get("avg_numerator_col", value_col)
        avg_denominator_col = cfg.get("avg_denominator_col", secondary_col)
        fleet_unit = cfg.get("fleet_unit", "xe")
        type_filter_kind = cfg.get("type_filter_kind")
        if type_filter_kind == "fleet":
            idx = 0
            type_filter = args[idx] if p1_filter_input is not None else None
            if p1_filter_input is not None:
                idx += 1
            seat_filter = args[idx] if p1_seat_filter_input is not None else None
            if p1_seat_filter_input is not None:
                idx += 1
            theme = args[idx]; idx += 1
            menu, page = args[idx], args[idx + 1]
            year_val = None
            months = []
        else:
            if p1_filter_input is not None and p1_business_filter_input is not None:
                year_val, months, type_filter, business_filter, theme, menu, page = args
            elif p1_filter_input is not None:
                year_val, months, type_filter, theme, menu, page = args
                business_filter = None
            else:
                year_val, months, theme, menu, page = args
                type_filter = None
                business_filter = None
            seat_filter = None

        if menu != prefix or int(page) != 1:
            raise PreventUpdate

        if type_filter_kind == "fleet":
            dff = apply_region_scope_to_df(df)
            dff = _latest_fleet_snapshot_df(dff)
        else:
            source_df = _lh_business_monthly_source_df() if type_filter_kind == "lh" and _normalize_multi_value(business_filter) else df
            dff = apply_common_filters(source_df, year_val=year_val, months=months, dims=[], real_cutoff=True)
        dff = _apply_type_filter(dff, type_filter)
        if type_filter_kind == "lh":
            dff = _apply_lh_business_filter_frame(dff, business_filter)
        dff = _apply_fleet_seat_filter(dff, seat_filter)
        if type_filter_kind == "fleet" and (dff is None or dff.empty):
            dff = apply_region_scope_to_df(_fleet_emergency_display_df(prefix, df))
            dff = _latest_fleet_snapshot_df(dff)

        if type_filter_kind == "fleet":
            _, tf_txt = _fleet_filter_text([], type_filter, seat_filter)
            snapshot_txt = _fleet_snapshot_period_text(dff)
            region_df = _fleet_region_snapshot(dff)
            type_df = _fleet_type_snapshot(dff)
            region_type_df = _fleet_region_type_snapshot(dff)
            total = float(pd.to_numeric(region_df.get("so_luong_xe", 0), errors="coerce").fillna(0).sum()) if not region_df.empty else 0.0
            active_regions = int(region_df["khu_vuc"].nunique()) if not region_df.empty and "khu_vuc" in region_df.columns else 0
            type_count = int(type_df["loai_xe"].nunique()) if not type_df.empty and "loai_xe" in type_df.columns else 0
            kpi_subtitle = f"{snapshot_txt}{tf_txt}"
            kpi1 = kpi_content(fmt_vn(total), kpi_subtitle, _fleet_kpi_lines_region(region_df, max_lines=6, unit=fleet_unit))
            kpi2 = kpi_content(fmt_vn(active_regions), f"{secondary_label} • {snapshot_txt}", _fleet_kpi_lines_region(region_df, max_lines=6, unit=fleet_unit))
            kpi3 = kpi_content(fmt_vn(type_count), f"{avg_label} • {snapshot_txt}", _fleet_kpi_lines_type(type_df, max_lines=6, unit=fleet_unit))
            kpi1_store = pack_kpi_store(f"Tổng {metric_label}", fmt_vn(total), kpi_subtitle, region_df[[c for c in ["khu_vuc", "xe_fmt", "ty_trong_fmt"] if c in region_df.columns]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records") if not region_df.empty else [])
            kpi2_store = pack_kpi_store(secondary_label, fmt_vn(active_regions), f"{secondary_label} • {snapshot_txt}", region_df[[c for c in ["khu_vuc", "xe_fmt", "ty_trong_fmt"] if c in region_df.columns]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records") if not region_df.empty else [])
            kpi3_store = pack_kpi_store(avg_label, fmt_vn(type_count), f"{avg_label} • {snapshot_txt}", type_df[[c for c in ["loai_xe", "xe_fmt", "ty_trong_fmt"] if c in type_df.columns]].rename(columns={"loai_xe": "label", "xe_fmt": "metric_fmt"}).to_dict("records") if not type_df.empty else [])

            if dff.empty:
                fig_kv = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
                fig_line = empty_figure("Không có dữ liệu loại xe", theme)
                fig_bar = empty_figure("Không có dữ liệu cơ cấu loại xe", theme)
                fig_pie = empty_figure("Không có dữ liệu bản đồ đội xe", theme)
                return (
                    kpi1, kpi2, kpi3,
                    fig_kv, fig_line, fig_bar, fig_pie,
                    kpi1_store, kpi2_store, kpi3_store,
                    pack_fig_store(fig_kv, rows=[], meta={"chart": "fleet_region_bar", "metric_label": metric_label}),
                    pack_fig_store(fig_line, rows=[], meta={"chart": "fleet_type_donut", "metric_label": metric_label}),
                    pack_fig_store(fig_bar, rows=[], meta={"chart": "fleet_type_bar", "metric_label": metric_label}),
                    pack_fig_store(fig_pie, rows=[], meta={"chart": "fleet_treemap", "metric_label": metric_label}),
                )

            g_region = region_df.copy()
            g_region["rank_fmt"] = [f"#{i}" for i in range(1, len(g_region) + 1)]
            fig_kv = go.Figure()
            fig_kv.add_bar(
                y=g_region["khu_vuc"],
                x=g_region["so_luong_xe"],
                orientation="h",
                text=[f"{x} xe • {p}" for x, p in zip(g_region["xe_fmt"], g_region["ty_trong_fmt"])],
                textposition="outside",
                cliponaxis=False,
                marker=dict(
                    color=[REGION_COLOR_MAP.get(str(x), GREEN_PRIMARY) for x in g_region["khu_vuc"]],
                    line=dict(color="#ffffff", width=1.2),
                ),
                customdata=np.column_stack([
                    g_region["xe_fmt"],
                    g_region["ty_trong_fmt"],
                    g_region["so_loai_xe"].apply(fmt_vn),
                    g_region["bks_fmt"],
                    g_region["rank_fmt"],
                ]),
                hovertemplate=(
                    "Khu vực: %{y}<br>"
                    "Số xe: %{customdata[0]}<br>"
                    "Tỷ trọng: %{customdata[1]}<br>"
                    "Loại xe: %{customdata[2]}<br>"
                    "Số BKS: %{customdata[3]}<br>"
                    "Xếp hạng: %{customdata[4]}<extra></extra>"
                ),
            )
            fig_kv = apply_exec_layout(fig_kv, theme=theme, title=f"Bản đồ phân bổ số lượng xe theo khu vực • {snapshot_txt}{tf_txt}", top=210, x_title="Số lượng xe", y_title="Khu vực")
            fig_kv.update_yaxes(categoryorder="array", categoryarray=g_region["khu_vuc"][::-1].tolist())
            fig_kv.update_layout(showlegend=False)
            if len(g_region) >= 2:
                avg_region = float(g_region["so_luong_xe"].mean())
                fig_kv.add_vline(x=avg_region, line_dash="dash", line_color="#94a3b8", annotation_text=f"TB: {fmt_vn(avg_region)} xe", annotation_position="top right")
            fig_kv_store = pack_fig_store(fig_kv, rows=g_region[["khu_vuc", "xe_fmt", "ty_trong_fmt", "bks_fmt"]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records"), meta={"chart": "fleet_region_bar", "metric_label": metric_label})

            g_type = type_df.copy()
            fig_line = make_vn_donut(g_type, names="loai_xe", values="so_luong_xe", title=f"Cơ cấu số lượng xe theo loại xe • {snapshot_txt}{tf_txt}", max_slices=10, color_map=None, theme=theme)
            fig_line_store = pack_fig_store(fig_line, rows=g_type[["loai_xe", "xe_fmt", "ty_trong_fmt"]].rename(columns={"loai_xe": "label", "xe_fmt": "metric_fmt"}).to_dict("records"), meta={"chart": "fleet_type_donut", "metric_label": metric_label})

            top_type = g_type.head(12).copy()
            fig_bar = go.Figure()
            fig_bar.add_bar(
                x=top_type["so_luong_xe"],
                y=top_type["loai_xe"],
                orientation="h",
                text=[f"{x} xe" for x in top_type["xe_fmt"]],
                textposition="outside",
                cliponaxis=False,
                marker=dict(color="#16a34a", line=dict(color="#14532d", width=1.1)),
                customdata=np.column_stack([top_type["xe_fmt"], top_type["ty_trong_fmt"], top_type["so_khu_vuc"].apply(fmt_vn)]),
                hovertemplate=(
                    "Loại xe: %{y}<br>"
                    "Số xe: %{customdata[0]}<br>"
                    "Tỷ trọng: %{customdata[1]}<br>"
                    "Hiện diện tại: %{customdata[2]} khu vực<extra></extra>"
                ),
            )
            fig_bar = apply_exec_layout(fig_bar, theme=theme, title=f"Top loại xe theo quy mô đội xe • {snapshot_txt}{tf_txt}", top=210, x_title="Số lượng xe", y_title="Loại xe")
            fig_bar.update_yaxes(categoryorder="array", categoryarray=top_type["loai_xe"][::-1].tolist())
            fig_bar.update_layout(showlegend=False)
            fig_bar_store = pack_fig_store(fig_bar, rows=top_type[["loai_xe", "xe_fmt", "ty_trong_fmt"]].rename(columns={"loai_xe": "label", "xe_fmt": "metric_fmt"}).to_dict("records"), meta={"chart": "fleet_type_bar", "metric_label": metric_label})

            treemap_source = region_type_df.copy()
            treemap_source["metric_fmt"] = treemap_source["xe_fmt"] + " xe"
            fig_pie = px.treemap(
                treemap_source,
                path=[px.Constant("Toàn đội xe"), "khu_vuc", "loai_xe"],
                values="so_luong_xe",
                color="khu_vuc",
                color_discrete_map=REGION_COLOR_MAP,
                custom_data=["xe_fmt"],
            )
            fig_pie.update_traces(
                textinfo="label+value",
                hovertemplate="Nhánh: %{label}<br>Số xe: %{customdata[0]}<extra></extra>",
                marker=dict(cornerradius=8),
            )
            fig_pie = apply_exec_layout(fig_pie, theme=theme, title=f"Bản đồ đội xe theo khu vực và loại xe • {snapshot_txt}{tf_txt}", top=210)
            fig_pie.update_layout(margin=dict(l=12, r=12, t=230, b=12))
            fig_pie_store = pack_fig_store(fig_pie, rows=treemap_source[["khu_vuc", "loai_xe", "xe_fmt"]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records"), meta={"chart": "fleet_treemap", "metric_label": metric_label})

            return (
                kpi1, kpi2, kpi3,
                fig_kv, fig_line, fig_bar, fig_pie,
                kpi1_store, kpi2_store, kpi3_store,
                fig_kv_store, fig_line_store, fig_bar_store, fig_pie_store
            )

        if prefix == "bb":
            year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
            mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else (f"{len(months)} tháng đã chọn" if months else "Tất cả tháng")
            count_total = safe_number(dff["so_bien_ban"].sum()) if "so_bien_ban" in dff.columns else 0.0
            collected_total = safe_number(dff["so_tien_thu_duoc"].sum()) if "so_tien_thu_duoc" in dff.columns else 0.0
            processed_total = safe_number(dff["so_tien_da_xu_ly"].sum()) if "so_tien_da_xu_ly" in dff.columns else 0.0
            debt_total = safe_number(dff["so_tien_con_no"].sum()) if "so_tien_con_no" in dff.columns else 0.0
            kpi_subtitle = f"{year_txt} • {mo_txt} • {fmt_vn(count_total)} biên bản"
            debt_ratio = (debt_total / processed_total * 100.0) if processed_total > 0 else 0.0

            payload1 = region_payload_value(dff, "so_tien_thu_duoc", selected_regions=None, max_items=None)
            payload2 = region_payload_value(dff, "so_tien_da_xu_ly", selected_regions=None, max_items=None)
            payload3 = region_payload_value(dff, "so_tien_con_no", selected_regions=None, max_items=None)

            kpi1 = kpi_content(fmt_vn(collected_total), kpi_subtitle, region_value_lines_from_payload(payload1, max_lines=4))
            kpi2 = kpi_content(fmt_vn(processed_total), f"{year_txt} • {mo_txt} • Giá trị biên bản ghi nhận", region_value_lines_from_payload(payload2, max_lines=4))
            kpi3 = kpi_content(fmt_vn(debt_total), f"chênh lệch / đã xử lý: {fmt_pct(debt_ratio, 1)}", region_value_lines_from_payload(payload3, max_lines=4))

            kpi1_store = pack_kpi_store("Số tiền đã xử lý", fmt_vn(collected_total), kpi_subtitle, payload1)
            kpi2_store = pack_kpi_store("Số tiền biên bản ghi nhận", fmt_vn(processed_total), f"{year_txt} • {mo_txt}", payload2)
            kpi3_store = pack_kpi_store("Số tiền chênh lệch", fmt_vn(debt_total), f"chênh lệch / đã xử lý: {fmt_pct(debt_ratio, 1)}", payload3)

            if dff.empty:
                fig_kv = empty_figure("Không có dữ liệu biên bản", theme)
                fig_line = empty_figure("Không có dữ liệu biên bản", theme)
                fig_bar = empty_figure("Không có dữ liệu biên bản", theme)
                fig_pie = empty_figure("Không có dữ liệu biên bản", theme)
                return (
                    kpi1, kpi2, kpi3,
                    fig_kv, fig_line, fig_bar, fig_pie,
                    kpi1_store, kpi2_store, kpi3_store,
                    pack_fig_store(fig_kv, rows=[], meta={"chart": "bb_region_grouped", "metric_label": "Biên bản"}),
                    pack_fig_store(fig_line, rows=[], meta={"chart": "bb_monthly_lines", "metric_label": "Biên bản"}),
                    pack_fig_store(fig_bar, rows=[], meta={"chart": "bb_monthly_bars", "metric_label": "Biên bản"}),
                    pack_fig_store(fig_pie, rows=[], meta={"chart": "bb_region_debt", "metric_label": "Biên bản"}),
                )

            g_region = dff.groupby("khu_vuc", as_index=False)[BB_METRIC_ORDER].sum()
            g_region = g_region.sort_values("so_tien_con_no", ascending=False)
            region_long = _bb_metric_long_df(dff, ["khu_vuc"])
            region_long = region_long.merge(
                g_region[["khu_vuc", "so_tien_thu_duoc", "so_tien_da_xu_ly", "so_tien_con_no"]],
                on="khu_vuc",
                how="left"
            )
            region_long["text_show"] = np.where(region_long["metric_key"].eq("so_tien_con_no"), region_long["metric_fmt"], "")
            region_long["ty_le_no"] = np.where(
                pd.to_numeric(region_long["so_tien_da_xu_ly"], errors="coerce").fillna(0) > 0,
                pd.to_numeric(region_long["so_tien_con_no"], errors="coerce").fillna(0)
                / pd.to_numeric(region_long["so_tien_da_xu_ly"], errors="coerce").fillna(0) * 100.0,
                0.0,
            )
            region_long["thu_fmt"] = pd.to_numeric(region_long["so_tien_thu_duoc"], errors="coerce").fillna(0).apply(fmt_vn)
            region_long["xl_fmt"] = pd.to_numeric(region_long["so_tien_da_xu_ly"], errors="coerce").fillna(0).apply(fmt_vn)
            region_long["no_fmt"] = pd.to_numeric(region_long["so_tien_con_no"], errors="coerce").fillna(0).apply(fmt_vn)
            region_long["ty_le_no_fmt"] = pd.to_numeric(region_long["ty_le_no"], errors="coerce").fillna(0).apply(lambda x: fmt_pct(x, 1))
            region_order = g_region["khu_vuc"].astype(str).tolist()
            fig_kv = px.bar(
                region_long,
                y="khu_vuc",
                x="gia_tri",
                orientation="h",
                color="metric_label",
                text="text_show",
                barmode="group",
                category_orders={"khu_vuc": region_order, "metric_label": [BB_METRIC_LABELS[k] for k in BB_METRIC_ORDER]},
                color_discrete_map=BB_METRIC_COLOR_MAP,
                hover_data={
                    "metric_fmt": True,
                    "gia_tri": False,
                    "thu_fmt": True,
                    "xl_fmt": True,
                    "no_fmt": True,
                    "ty_le_no_fmt": True,
                },
            )
            fig_kv.update_traces(
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "Khu vực: %{y}<br>"
                    "Chỉ số: %{fullData.name}<br>"
                    "Giá trị: %{customdata[0]}<br>"
                    "Đã xử lý: %{customdata[1]}<br>"
                    "Đã xử lý: %{customdata[2]}<br>"
                    "chênh lệch: %{customdata[3]}<br>"
                    "Tỷ lệ nợ / đã xử lý: %{customdata[4]}"
                    "<extra></extra>"
                )
            )
            fig_kv = apply_exec_layout(
                fig_kv,
                theme=theme,
                title=f"So sánh 3 chỉ số tài chính biên bản theo khu vực<br>{year_txt} • {mo_txt}",
                top=210,
                x_title="Giá trị",
                y_title="Khu vực"
            )
            fig_kv.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0),
                bargap=0.24,
                hovermode="y unified"
            )
            fig_kv.update_yaxes(categoryorder="array", categoryarray=region_order, autorange="reversed")
            top_debt_region = g_region.iloc[0]["khu_vuc"] if not g_region.empty else "-"
            top_debt_value = g_region.iloc[0]["so_tien_con_no"] if not g_region.empty else 0
            fig_kv.add_annotation(
                x=1,
                y=1.14,
                xref="paper",
                yref="paper",
                showarrow=False,
                text=f"Nợ cao nhất: {top_debt_region} • {fmt_vn(top_debt_value)}",
                font=dict(size=11, color=(TEXT_LIGHT_UI if theme == "light" else "white")),
                align="right"
            )
            rows_kv = _bb_drill_rows(dff, ["khu_vuc"], metric_labels=BB_DRILL_METRIC_LABELS)
            fig_kv_store = pack_fig_store(fig_kv, rows=rows_kv, meta={"chart": "bb_region_grouped", "metric_label": "Biên bản", "series_field": "metric_label"})

            monthly_long = _bb_metric_long_df(dff, ["thang_nam_vn"])
            monthly_long["thang_label"] = pd.to_datetime(monthly_long["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y")
            fig_line = px.line(
                monthly_long,
                x="thang_nam_vn",
                y="gia_tri",
                color="metric_label",
                markers=True,
                category_orders={"metric_label": [BB_METRIC_LABELS[k] for k in BB_METRIC_ORDER]},
                color_discrete_map=BB_METRIC_COLOR_MAP,
                hover_data={"metric_fmt": True, "gia_tri": False},
            )
            fig_line.update_traces(line_shape="spline", line_width=3, marker_size=7)
            fig_line.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
            fig_line = apply_theme(fig_line, theme)
            fig_line = apply_chart_title(fig_line, f"Xu hướng 3 chỉ số tài chính biên bản theo tháng<br>{year_txt} • {mo_txt}", top=220, y_title="Giá trị")
            fig_line = _add_line_point_labels(fig_line, show_all_if_points_le=8)
            rows_line = _bb_drill_rows(dff, ["thang_nam_vn"], metric_labels=BB_DRILL_METRIC_LABELS)
            fig_line_store = pack_fig_store(fig_line, rows=rows_line, meta={"chart": "bb_monthly_lines", "metric_label": "Biên bản", "series_field": "metric_label"})

            fig_bar = px.bar(
                monthly_long,
                x="thang_nam_vn",
                y="gia_tri",
                color="metric_label",
                text="metric_fmt",
                barmode="group",
                category_orders={"metric_label": [BB_METRIC_LABELS[k] for k in BB_METRIC_ORDER]},
                color_discrete_map=BB_METRIC_COLOR_MAP,
                hover_data={"metric_fmt": True, "gia_tri": False},
            )
            fig_bar.update_traces(textposition="outside", cliponaxis=False)
            fig_bar.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0), bargap=0.18)
            fig_bar = apply_theme(fig_bar, theme)
            fig_bar = apply_chart_title(fig_bar, f"Biểu đồ cột 3 chỉ số tài chính biên bản theo tháng<br>{year_txt} • {mo_txt}", top=220, y_title="Giá trị")
            fig_bar_store = pack_fig_store(fig_bar, rows=rows_line, meta={"chart": "bb_monthly_bars", "metric_label": "Biên bản", "series_field": "metric_label"})

            pie_source = dff.groupby("khu_vuc", as_index=False)["so_tien_con_no"].sum().sort_values("so_tien_con_no", ascending=False)
            if float(pd.to_numeric(pie_source.get("so_tien_con_no", 0), errors="coerce").fillna(0).sum()) <= 0:
                pie_source = dff.groupby("khu_vuc", as_index=False)["so_tien_thu_duoc"].sum().sort_values("so_tien_thu_duoc", ascending=False)
                pie_value = "so_tien_thu_duoc"
                pie_title = f"Tỷ trọng số tiền đã xử lý theo khu vực<br>{year_txt} • {mo_txt}"
            else:
                pie_value = "so_tien_con_no"
                pie_title = f"Tỷ trọng số tiền chênh lệch theo khu vực<br>{year_txt} • {mo_txt}"
            fig_pie = make_vn_donut(pie_source, names="khu_vuc", values=pie_value, title=pie_title, max_slices=10, color_map=REGION_COLOR_MAP, theme=theme)
            pie_source["metric_fmt"] = pie_source[pie_value].apply(fmt_vn)
            fig_pie_store = pack_fig_store(fig_pie, rows=_bb_drill_rows(dff, ["khu_vuc"], label_from="khu_vuc", label_col="label"), meta={"chart": "bb_region_debt", "metric_label": pie_title})

            return (
                kpi1, kpi2, kpi3,
                fig_kv, fig_line, fig_bar, fig_pie,
                kpi1_store, kpi2_store, kpi3_store,
                fig_kv_store, fig_line_store, fig_bar_store, fig_pie_store
            )

        total = safe_number(dff[value_col].sum()) if value_col in dff.columns else 0.0
        secondary_total = safe_number(dff[secondary_col].sum()) if secondary_col in dff.columns else 0.0
        months_n = max(int(dff["thang_label"].nunique()) if "thang_label" in dff.columns and not dff.empty else 1, 1)

        total_payload = region_payload_value(dff, value_col, selected_regions=None, max_items=None)
        secondary_payload = region_payload_value(dff, secondary_col, selected_regions=None, max_items=None) if secondary_col in dff.columns else []
        avg_payload, avg_lines = _avg_payload_and_lines(dff)

        if avg_mode == "per_month":
            avg = total / months_n
            avg_caption = f"{avg_label} • {months_n} tháng"
        else:
            avg_num_total = safe_number(dff[avg_numerator_col].sum()) if avg_numerator_col in dff.columns else total
            avg_den_total = safe_number(dff[avg_denominator_col].sum()) if avg_denominator_col in dff.columns else secondary_total
            avg = avg_num_total / max(avg_den_total, 1)
            avg_caption = f"{avg_label} • {fmt_vn(avg_den_total)} {avg_divisor_label}"

        year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
        mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else (f"{len(months)} tháng đã chọn" if months else "Tất cả tháng")
        tf_txt = ""
        if type_filter_kind == "lh" and type_filter:
            tf_txt = f" • Lọc loại hình: {', '.join(type_filter)}"
        if type_filter_kind == "lh" and _normalize_multi_value(business_filter):
            tf_txt += f" • Hình thức KD: {', '.join(_normalize_multi_value(business_filter))}"
        if type_filter_kind == "hd" and type_filter:
            tf_txt = f" • Lọc loại HĐ: {', '.join(type_filter)}"
        if type_filter_kind == "fleet" and type_filter:
            tf_txt = f" • Lọc loại xe: {', '.join(type_filter)}"

        kpi_subtitle = f"{year_txt} • {mo_txt}{tf_txt}"
        kpi1 = kpi_content(fmt_vn(total), kpi_subtitle, region_value_lines_from_payload(total_payload, max_lines=4))
        kpi2 = kpi_content(fmt_vn(secondary_total), kpi_subtitle, region_value_lines_from_payload(secondary_payload, max_lines=4))
        kpi3 = kpi_content(fmt_vn(avg), avg_caption, avg_lines[:4])

        kpi1_store = pack_kpi_store(f"Tổng {metric_label}", fmt_vn(total), kpi_subtitle, total_payload)
        kpi2_store = pack_kpi_store(secondary_label, fmt_vn(secondary_total), kpi_subtitle, secondary_payload)
        kpi3_store = pack_kpi_store(avg_label, fmt_vn(avg), avg_caption, avg_payload)

        if dff.empty:
            fig_kv = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
            fig_line = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
            fig_bar = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
            fig_pie = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
            fig_kv_store = pack_fig_store(fig_kv, rows=[], meta={"chart": "line_kv", "metric_label": metric_label})
            fig_line_store = pack_fig_store(fig_line, rows=[], meta={"chart": "line_total", "metric_label": metric_label})
            fig_bar_store = pack_fig_store(fig_bar, rows=[], meta={"chart": "bar_total", "metric_label": metric_label})
            fig_pie_store = pack_fig_store(fig_pie, rows=[], meta={"chart": "pie_month", "metric_label": metric_label})
            return (
                kpi1, kpi2, kpi3,
                fig_kv, fig_line, fig_bar, fig_pie,
                kpi1_store, kpi2_store, kpi3_store,
                fig_kv_store, fig_line_store, fig_bar_store, fig_pie_store
            )

        g = dff.groupby("thang_nam_vn", as_index=False).agg({value_col: "sum"}).sort_values("thang_nam_vn")
        g["val_fmt"] = g[value_col].apply(fmt_vn)
        g["thang_label"] = g["thang_nam_vn"].dt.strftime("%m/%Y")

        if "khu_vuc" in dff.columns:
            dff_kv, kv_col = top_n_keep_other(dff, "khu_vuc", value_col, n=None, other_label="Khác", keep_cats=PINNED_REGIONS)
            gkv = dff_kv.groupby(["thang_nam_vn", kv_col], as_index=False).agg({value_col: "sum"}).sort_values("thang_nam_vn")
            gkv["val_fmt"] = gkv[value_col].apply(fmt_vn)
            gkv["thang_label"] = gkv["thang_nam_vn"].dt.strftime("%m/%Y")
            kv_order = gkv.groupby(kv_col, as_index=False)[value_col].sum().sort_values(value_col, ascending=False)[kv_col].tolist()
            fig_kv = px.line(
                gkv,
                x="thang_nam_vn",
                y=value_col,
                color=kv_col,
                category_orders={kv_col: kv_order},
                color_discrete_map=REGION_COLOR_MAP,
                markers=True,
                hover_data={"val_fmt": True, value_col: False},
            )
            fig_kv.update_traces(line_shape="spline", line_width=3, marker_size=7)
            fig_kv.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
            fig_kv = apply_theme(fig_kv, theme)
            fig_kv = apply_chart_title(fig_kv, f"{metric_label} theo tháng • So sánh giữa các khu vực<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
            fig_kv = _add_line_point_labels(fig_kv, show_all_if_points_le=10)
            rows_kv = [{"thang_label": r["thang_label"], "khu_vuc": str(r[kv_col]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in gkv.iterrows()]
            fig_kv_store = pack_fig_store(fig_kv, rows=rows_kv, meta={"chart": "line_kv", "metric_label": metric_label, "series_field": kv_col})
        else:
            fig_kv = empty_figure("Không có dữ liệu khu vực", theme)
            fig_kv_store = pack_fig_store(fig_kv, rows=[], meta={"chart": "line_kv", "metric_label": metric_label})

        fig_line = px.line(g, x="thang_nam_vn", y=value_col, markers=True, hover_data={"val_fmt": True, value_col: False})
        fig_line.update_traces(line_shape="spline", line_width=3, marker_size=7)
        fig_line = apply_theme(fig_line, theme)
        fig_line = apply_chart_title(fig_line, f"{metric_label} theo tháng • Tổng toàn tập đoàn<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
        fig_line = _add_line_point_labels(fig_line, show_all_if_points_le=10)
        fig_line = enhance_p1_chart2_total_line(fig_line, g, "thang_nam_vn", value_col, metric_label, theme)
        fig_line_store = pack_fig_store(fig_line, rows=g[["thang_label", "val_fmt"]].to_dict("records"), meta={"chart": "line_total", "metric_label": metric_label})

        fig_bar = px.bar(g, x="thang_nam_vn", y=value_col, text="val_fmt", hover_data={"val_fmt": True, value_col: False})
        fig_bar.update_traces(textposition="outside", cliponaxis=False)
        fig_bar.update_layout(margin=dict(t=20))
        fig_bar = apply_theme(fig_bar, theme)
        fig_bar = apply_chart_title(fig_bar, f"{metric_label} theo tháng • Biểu đồ cột<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
        fig_bar = enhance_p1_chart3_monthly_bar(fig_bar, g, "thang_nam_vn", value_col, metric_label, theme)
        fig_bar_store = pack_fig_store(fig_bar, rows=g[["thang_label", "val_fmt"]].to_dict("records"), meta={"chart": "bar_total", "metric_label": metric_label})

        g_pie = g.copy()
        g_pie["thang"] = g_pie["thang_label"]
        fig_pie = px.pie(g_pie, names="thang", values=value_col, hole=0.45, hover_data={"val_fmt": True, value_col: False})
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie = apply_theme(fig_pie, theme)
        fig_pie = apply_chart_title(fig_pie, f"Tỷ trọng {metric_label.lower()} theo tháng<br>{year_txt} • {mo_txt}{tf_txt}", top=210)
        fig_pie_store = pack_fig_store(fig_pie, rows=g_pie[["thang", "val_fmt"]].to_dict("records"), meta={"chart": "pie_month", "metric_label": metric_label})

        return (
            kpi1, kpi2, kpi3,
            fig_kv, fig_line, fig_bar, fig_pie,
            kpi1_store, kpi2_store, kpi3_store,
            fig_kv_store, fig_line_store, fig_bar_store, fig_pie_store
        )

    if type_filter_kind == "fleet":
        inputs_p2 = [
            Input(f"{prefix}-dim","value", allow_optional=True),
        ]
    else:
        inputs_p2 = [
            Input(f"{prefix}-dim","value", allow_optional=True),
            Input(f"{prefix}-year-p2","value", allow_optional=True),
            Input(f"{prefix}-month-p2","value", allow_optional=True),
        ]
    if p2_filter_input is not None:
        inputs_p2.append(p2_filter_input)
    if p2_business_filter_input is not None:
        inputs_p2.append(p2_business_filter_input)
    if p2_seat_filter_input is not None:
        inputs_p2.append(p2_seat_filter_input)

    @app.callback(
        Output(f"{prefix}-kpi1","children"),
        Output(f"{prefix}-kpi2","children"),
        Output(f"{prefix}-kpi3","children"),
        Output(f"{prefix}-p2-line","figure"),
        Output(f"{prefix}-p2-bar","figure"),
        Output(f"{prefix}-p2-pie","figure"),
        Output(f"{prefix}-table","data"),
        Output(f"{prefix}-insight","children"),
        Output(f"{prefix}-table","style_cell"),
        Output(f"{prefix}-table","style_header"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi1"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi2"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi3"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-line"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-bar"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-pie"}, "data"),
        *inputs_p2,
        State("theme", "data"),
        State("menu", "data"),
        State("page", "data"),
    )
    @timed_callback(f"{prefix}.p2")
    @timed_callback(f"{prefix}.hr_p2")
    def p2(*args):
        nonlocal cfg, df, value_col, metric_label, metric_axis, secondary_col, secondary_label, avg_label, avg_mode, avg_divisor_label, avg_numerator_col, avg_denominator_col, fleet_unit, type_filter_kind
        ensure_menu_data_loaded(prefix)
        cfg = get_menu_config(prefix)
        df = cfg["df"]
        value_col = cfg["value_col"]
        metric_label = cfg.get("metric_label", "Giá trị")
        metric_axis = metric_label
        secondary_col = cfg.get("secondary_col", "tong_so_cuoc")
        secondary_label = cfg.get("secondary_label", "Quy mô")
        avg_label = cfg.get("avg_label", "Trung bình")
        avg_mode = cfg.get("avg_mode", "per_secondary")
        avg_divisor_label = cfg.get("avg_divisor_label", secondary_label.lower())
        avg_numerator_col = cfg.get("avg_numerator_col", value_col)
        avg_denominator_col = cfg.get("avg_denominator_col", secondary_col)
        fleet_unit = cfg.get("fleet_unit", "xe")
        type_filter_kind = cfg.get("type_filter_kind")
        if type_filter_kind == "fleet":
            idx = 0
            dim = args[idx]; idx += 1
            type_filter = args[idx] if p2_filter_input is not None else None
            if p2_filter_input is not None:
                idx += 1
            seat_filter = args[idx] if p2_seat_filter_input is not None else None
            if p2_seat_filter_input is not None:
                idx += 1
            theme = args[idx]; idx += 1
            menu, page = args[idx], args[idx + 1]
            year_val = None
            months = []
        else:
            if p2_filter_input is not None and p2_business_filter_input is not None:
                dim, year_val, months, type_filter, business_filter, theme, menu, page = args
            elif p2_filter_input is not None:
                dim, year_val, months, type_filter, theme, menu, page = args
                business_filter = None
            else:
                dim, year_val, months, theme, menu, page = args
                type_filter = None
                business_filter = None
            seat_filter = None

        if menu != prefix or int(page) != 2:
            raise PreventUpdate

        dims = dim if isinstance(dim, list) else ([dim] if dim else [])
        if type_filter_kind == "fleet":
            dff = apply_region_scope_to_df(df)
            dff = _latest_fleet_snapshot_df(dff)
            if dims and "khu_vuc" in dff.columns:
                dff = dff[dff["khu_vuc"].astype(str).isin([str(x) for x in dims])]
        else:
            source_df = _lh_business_monthly_source_df() if type_filter_kind == "lh" and _normalize_multi_value(business_filter) else df
            dff = apply_common_filters(source_df, year_val=year_val, months=months, dims=dims, real_cutoff=True)
        dff = _apply_type_filter(dff, type_filter)
        if type_filter_kind == "lh":
            dff = _apply_lh_business_filter_frame(dff, business_filter)
        dff = _apply_fleet_seat_filter(dff, seat_filter)
        if type_filter_kind == "fleet" and (dff is None or dff.empty):
            dff = apply_region_scope_to_df(_fleet_emergency_display_df(prefix, df))
            dff = _latest_fleet_snapshot_df(dff)
        dff = dff.sort_values("thang_nam_vn") if "thang_nam_vn" in dff.columns else dff

        if type_filter_kind == "fleet":
            dims_show, tf_txt = _fleet_filter_text(dims, type_filter, seat_filter)
            snapshot_txt = _fleet_snapshot_period_text(dff)
            region_df = _fleet_region_snapshot(dff)
            type_df = _fleet_type_snapshot(dff)
            region_type_df = _fleet_region_type_snapshot(dff)
            total = float(pd.to_numeric(region_df.get("so_luong_xe", 0), errors="coerce").fillna(0).sum()) if not region_df.empty else 0.0
            active_regions = int(region_df["khu_vuc"].nunique()) if not region_df.empty and "khu_vuc" in region_df.columns else 0
            type_count = int(type_df["loai_xe"].nunique()) if not type_df.empty and "loai_xe" in type_df.columns else 0
            kpi_subtitle = f"{dims_show} • {snapshot_txt}{tf_txt}"
            kpi1 = kpi_content(fmt_vn(total), kpi_subtitle, _fleet_kpi_lines_region(region_df, max_lines=6, unit=fleet_unit))
            kpi2 = kpi_content(fmt_vn(active_regions), f"{secondary_label} • {dims_show} • {snapshot_txt}", _fleet_kpi_lines_region(region_df, max_lines=6, unit=fleet_unit))
            kpi3 = kpi_content(fmt_vn(type_count), f"{avg_label} • {dims_show} • {snapshot_txt}", _fleet_kpi_lines_type(type_df, max_lines=6, unit=fleet_unit))
            kpi1_store = pack_kpi_store(f"Tổng {metric_label}", fmt_vn(total), kpi_subtitle, region_df[[c for c in ["khu_vuc", "xe_fmt", "ty_trong_fmt"] if c in region_df.columns]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records") if not region_df.empty else [])
            kpi2_store = pack_kpi_store(secondary_label, fmt_vn(active_regions), f"{secondary_label} • {dims_show} • {snapshot_txt}", region_df[[c for c in ["khu_vuc", "xe_fmt", "ty_trong_fmt"] if c in region_df.columns]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records") if not region_df.empty else [])
            kpi3_store = pack_kpi_store(avg_label, fmt_vn(type_count), f"{avg_label} • {dims_show} • {snapshot_txt}", type_df[[c for c in ["loai_xe", "xe_fmt", "ty_trong_fmt"] if c in type_df.columns]].rename(columns={"loai_xe": "label", "xe_fmt": "metric_fmt"}).to_dict("records") if not type_df.empty else [])
            insight = f"{dims_show} • {snapshot_txt} • {fmt_vn(total)} xe • {active_regions} khu vực có xe • {type_count} loại xe hoạt động"

            if dff.empty:
                fig1 = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
                fig2 = empty_figure("Không có dữ liệu heatmap đội xe", theme)
                fig3 = empty_figure("Không có dữ liệu cơ cấu", theme)
                style_cell, style_header = _detail_table_theme_styles(theme, prefix)
                return (
                    kpi1, kpi2, kpi3,
                    fig1, fig2, fig3,
                    [], insight,
                    style_cell, style_header,
                    kpi1_store, kpi2_store, kpi3_store,
                    pack_fig_store(fig1, rows=[], meta={"chart": "fleet_region_bar", "metric_label": metric_label}),
                    pack_fig_store(fig2, rows=[], meta={"chart": "fleet_heatmap", "metric_label": metric_label}),
                    pack_fig_store(fig3, rows=[], meta={"chart": "fleet_mix_donut", "metric_label": metric_label}),
                )

            g_region = region_df.copy()
            g_region["rank_fmt"] = [f"#{i}" for i in range(1, len(g_region) + 1)]
            fig1 = go.Figure()
            fig1.add_bar(
                y=g_region["khu_vuc"],
                x=g_region["so_luong_xe"],
                orientation="h",
                text=[f"{x} xe • {p}" for x, p in zip(g_region["xe_fmt"], g_region["ty_trong_fmt"])],
                textposition="outside",
                cliponaxis=False,
                marker=dict(
                    color=[REGION_COLOR_MAP.get(str(x), GREEN_PRIMARY) for x in g_region["khu_vuc"]],
                    line=dict(color="#ffffff", width=1.2),
                ),
                customdata=np.column_stack([
                    g_region["xe_fmt"],
                    g_region["ty_trong_fmt"],
                    g_region["so_loai_xe"].apply(fmt_vn),
                    g_region["bks_fmt"],
                    g_region["rank_fmt"],
                ]),
                hovertemplate=(
                    "Khu vực: %{y}<br>"
                    "Số xe: %{customdata[0]}<br>"
                    "Tỷ trọng: %{customdata[1]}<br>"
                    "Loại xe: %{customdata[2]}<br>"
                    "Số BKS: %{customdata[3]}<br>"
                    "Xếp hạng: %{customdata[4]}<extra></extra>"
                ),
            )
            fig1 = apply_exec_layout(fig1, theme=theme, title=f"Số lượng xe theo khu vực • {snapshot_txt}<br>{dims_show}{tf_txt}", top=220, x_title="Số lượng xe", y_title="Khu vực")
            fig1.update_yaxes(categoryorder="array", categoryarray=g_region["khu_vuc"][::-1].tolist())
            fig1.update_layout(showlegend=False)
            if len(g_region) >= 2:
                avg_region = float(g_region["so_luong_xe"].mean())
                fig1.add_vline(x=avg_region, line_dash="dash", line_color="#94a3b8", annotation_text=f"TB: {fmt_vn(avg_region)} xe", annotation_position="top right")
            rows1 = g_region[["khu_vuc", "xe_fmt", "ty_trong_fmt", "bks_fmt"]].rename(columns={"xe_fmt": "metric_fmt"}).to_dict("records")
            fig1_store = pack_fig_store(fig1, rows=rows1, meta={"chart": "fleet_region_bar", "metric_label": metric_label})

            pivot = region_type_df.pivot(index="loai_xe", columns="khu_vuc", values="so_luong_xe").fillna(0)
            z = pivot.values
            text_matrix = [[fmt_vn(v) for v in row] for row in z]
            fig2 = go.Figure(data=go.Heatmap(
                z=z,
                x=list(pivot.columns),
                y=list(pivot.index),
                text=text_matrix,
                texttemplate="%{text}",
                colorscale="Greens",
                hovertemplate="Khu vực: %{x}<br>Loại xe: %{y}<br>Số xe: %{z:,.0f}<extra></extra>",
                colorbar=dict(title="Số xe"),
            ))
            fig2 = apply_exec_layout(fig2, theme=theme, title=f"Ma trận phân bổ xe theo khu vực và loại xe<br>{dims_show} • {snapshot_txt}{tf_txt}", top=220, x_title="Khu vực", y_title="Loại xe")
            rows2 = [{"khu_vuc": str(r["khu_vuc"]), "loai_xe": str(r["loai_xe"]), "metric_fmt": r["xe_fmt"]} for _, r in region_type_df.iterrows()]
            fig2_store = pack_fig_store(fig2, rows=rows2, meta={"chart": "fleet_heatmap", "metric_label": metric_label})

            if type_count > 1:
                fig3 = make_vn_donut(type_df, names="loai_xe", values="so_luong_xe", title=f"Cơ cấu số lượng xe theo loại xe<br>{dims_show} • {snapshot_txt}{tf_txt}", max_slices=10, color_map=None, theme=theme)
                rows3 = type_df[["loai_xe", "xe_fmt", "ty_trong_fmt"]].rename(columns={"loai_xe": "label", "xe_fmt": "metric_fmt"}).to_dict("records")
            else:
                fig3 = make_vn_donut(region_df, names="khu_vuc", values="so_luong_xe", title=f"Tỷ trọng số lượng xe theo khu vực<br>{dims_show} • {snapshot_txt}{tf_txt}", max_slices=10, color_map=REGION_COLOR_MAP, theme=theme)
                rows3 = region_df[["khu_vuc", "xe_fmt", "ty_trong_fmt"]].rename(columns={"khu_vuc": "label", "xe_fmt": "metric_fmt"}).to_dict("records")
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "fleet_mix_donut", "metric_label": metric_label})

            table_df = _fleet_table_frame(dff)
            for c in [col for col in table_df.columns if col not in ["khu_vuc", "loai_xe", "nhom_nhien_lieu"]]:
                table_df[c] = pd.to_numeric(table_df[c], errors="coerce").fillna(0).apply(fmt_vn)
            style_cell, style_header = _detail_table_theme_styles(theme, prefix)
            return (
                kpi1, kpi2, kpi3,
                fig1, fig2, fig3,
                table_df.to_dict("records"), insight,
                style_cell, style_header,
                kpi1_store, kpi2_store, kpi3_store,
                fig1_store, fig2_store, fig3_store
            )

        if prefix == "bb":
            year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
            mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else (f"{len(months)} tháng đã chọn" if months else "Tất cả tháng")
            dims_show = ", ".join(dims[:3]) + (" ..." if len(dims) > 3 else "") if dims else "Toàn bộ khu vực"
            count_total = safe_number(dff["so_bien_ban"].sum()) if "so_bien_ban" in dff.columns else 0.0
            collected_total = safe_number(dff["so_tien_thu_duoc"].sum()) if "so_tien_thu_duoc" in dff.columns else 0.0
            processed_total = safe_number(dff["so_tien_da_xu_ly"].sum()) if "so_tien_da_xu_ly" in dff.columns else 0.0
            debt_total = safe_number(dff["so_tien_con_no"].sum()) if "so_tien_con_no" in dff.columns else 0.0
            debt_ratio = (debt_total / processed_total * 100.0) if processed_total > 0 else 0.0

            payload1 = region_payload_value(dff, "so_tien_thu_duoc", selected_regions=dims, max_items=None)
            payload2 = region_payload_value(dff, "so_tien_da_xu_ly", selected_regions=dims, max_items=None)
            payload3 = region_payload_value(dff, "so_tien_con_no", selected_regions=dims, max_items=None)

            kpi1_sub = f"{dims_show} • {year_txt} • {mo_txt} • {fmt_vn(count_total)} biên bản"
            kpi1 = kpi_content(fmt_vn(collected_total), kpi1_sub, region_value_lines_from_payload(payload1, max_lines=6))
            kpi2 = kpi_content(fmt_vn(processed_total), f"{dims_show} • {year_txt} • {mo_txt}", region_value_lines_from_payload(payload2, max_lines=6))
            kpi3 = kpi_content(fmt_vn(debt_total), f"chênh lệch / đã xử lý: {fmt_pct(debt_ratio, 1)}", region_value_lines_from_payload(payload3, max_lines=6))

            kpi1_store = pack_kpi_store("Số tiền đã xử lý", fmt_vn(collected_total), kpi1_sub, payload1)
            kpi2_store = pack_kpi_store("Số tiền biên bản ghi nhận", fmt_vn(processed_total), f"{dims_show} • {year_txt} • {mo_txt}", payload2)
            kpi3_store = pack_kpi_store("Số tiền chênh lệch", fmt_vn(debt_total), f"chênh lệch / đã xử lý: {fmt_pct(debt_ratio, 1)}", payload3)
            insight = f"đã xử lý {fmt_vn(collected_total)} / Đã xử lý {fmt_vn(processed_total)} / chênh lệch {fmt_vn(debt_total)} – {dims_show}"

            if dff.empty:
                fig1 = empty_figure("Không có dữ liệu biên bản", theme)
                fig2 = empty_figure("Không có dữ liệu biên bản", theme)
                fig3 = empty_figure("Không có dữ liệu biên bản", theme)
                if theme == "light":
                    style_cell = {"backgroundColor": LIGHT_BG, "color": "black", "textAlign": "center"}
                    style_header = {"backgroundColor": "#f2f2f2", "color": "black", "fontWeight": "700"}
                else:
                    style_cell = {"backgroundColor": DARK_BG, "color": "white", "textAlign": "center"}
                    style_header = {"backgroundColor": "#222", "color": "white", "fontWeight": "700"}
                return (
                    kpi1, kpi2, kpi3,
                    fig1, fig2, fig3,
                    [], insight,
                    style_cell, style_header,
                    kpi1_store, kpi2_store, kpi3_store,
                    pack_fig_store(fig1, rows=[], meta={"chart": "bb_line", "metric_label": "Biên bản"}),
                    pack_fig_store(fig2, rows=[], meta={"chart": "bb_bar", "metric_label": "Biên bản"}),
                    pack_fig_store(fig3, rows=[], meta={"chart": "bb_pie", "metric_label": "Biên bản"}),
                )

            if len(dims) >= 2:
                g1 = dff.groupby(["thang_nam_vn", "khu_vuc"], as_index=False)["so_tien_thu_duoc"].sum().sort_values("thang_nam_vn")
                g1["metric_fmt"] = g1["so_tien_thu_duoc"].apply(fmt_vn)
                g1["thang_label"] = g1["thang_nam_vn"].dt.strftime("%m/%Y")
                kv_order = g1.groupby("khu_vuc", as_index=False)["so_tien_thu_duoc"].sum().sort_values("so_tien_thu_duoc", ascending=False)["khu_vuc"].tolist()
                fig1 = px.line(g1, x="thang_nam_vn", y="so_tien_thu_duoc", color="khu_vuc", markers=True, category_orders={"khu_vuc": kv_order}, color_discrete_map=REGION_COLOR_MAP, hover_data={"metric_fmt": True, "so_tien_thu_duoc": False})
                fig1.update_traces(line_shape="spline", line_width=3, marker_size=7)
                fig1.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
                fig1 = apply_theme(fig1, theme)
                fig1 = apply_chart_title(fig1, f"Số tiền đã xử lý theo tháng • So sánh khu vực<br>{dims_show} • {year_txt} • {mo_txt}", top=220, y_title="Giá trị")
                fig1 = _add_line_point_labels(fig1, show_all_if_points_le=10)
                rows1 = _bb_drill_rows(dff, ["thang_nam_vn", "khu_vuc"], metric_labels=["Số tiền đã xử lý"])
                fig1_store = pack_fig_store(fig1, rows=rows1, meta={"chart": "bb_line", "metric_label": "Số tiền đã xử lý", "series_field": "khu_vuc"})
            else:
                monthly_long = _bb_metric_long_df(dff, ["thang_nam_vn"])
                monthly_long["thang_label"] = pd.to_datetime(monthly_long["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y")
                fig1 = px.line(monthly_long, x="thang_nam_vn", y="gia_tri", color="metric_label", markers=True, category_orders={"metric_label": [BB_METRIC_LABELS[k] for k in BB_METRIC_ORDER]}, color_discrete_map=BB_METRIC_COLOR_MAP, hover_data={"metric_fmt": True, "gia_tri": False})
                fig1.update_traces(line_shape="spline", line_width=3, marker_size=7)
                fig1.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
                fig1 = apply_theme(fig1, theme)
                fig1 = apply_chart_title(fig1, f"Xu hướng 3 chỉ số tài chính biên bản theo tháng<br>{dims_show} • {year_txt} • {mo_txt}", top=220, y_title="Giá trị")
                fig1 = _add_line_point_labels(fig1, show_all_if_points_le=10)
                rows1 = _bb_drill_rows(dff, ["thang_nam_vn"], metric_labels=BB_DRILL_METRIC_LABELS)
                fig1_store = pack_fig_store(fig1, rows=rows1, meta={"chart": "bb_line", "metric_label": "Biên bản", "series_field": "metric_label"})

            monthly_detail = _bb_metric_long_df(dff, ["thang_nam_vn", "khu_vuc"])
            monthly_detail["thang_label"] = pd.to_datetime(monthly_detail["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y")
            monthly_long = monthly_detail.groupby(["thang_nam_vn", "thang_label", "metric_label"], as_index=False)["gia_tri"].sum()
            monthly_long["metric_fmt"] = monthly_long["gia_tri"].apply(fmt_vn)
            fig2 = px.bar(
                monthly_long,
                x="thang_nam_vn",
                y="gia_tri",
                color="metric_label",
                text="metric_fmt",
                barmode="group",
                category_orders={"metric_label": [BB_METRIC_LABELS[k] for k in BB_METRIC_ORDER]},
                color_discrete_map=BB_METRIC_COLOR_MAP,
                hover_data={"metric_fmt": True, "gia_tri": False}
            )
            fig2.update_traces(textposition="outside", cliponaxis=False)
            fig2.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0), bargap=0.18)
            fig2 = apply_theme(fig2, theme)
            fig2_title = f"Biểu đồ cột 3 chỉ số tài chính biên bản theo tháng<br>{dims_show} • {year_txt} • {mo_txt}"
            fig2 = apply_chart_title(fig2, fig2_title, top=220, y_title="Giá trị")
            if len(dims) >= 2:
                fig2.add_annotation(
                    x=1,
                    y=1.14,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    text=f"Đang cộng gộp {len(dims)} khu vực đã chọn",
                    font=dict(size=11, color=(TEXT_LIGHT_UI if theme == "light" else "white")),
                    align="right"
                )
            rows2 = _bb_drill_rows(dff, ["thang_nam_vn", "khu_vuc"], metric_labels=BB_DRILL_METRIC_LABELS)
            fig2_store = pack_fig_store(fig2, rows=rows2, meta={"chart": "bb_bar", "metric_label": "Biên bản", "series_field": "metric_label"})

            if len(dims) >= 2 or not dims:
                pie_source = dff.groupby("khu_vuc", as_index=False)["so_tien_con_no"].sum().sort_values("so_tien_con_no", ascending=False)
                if float(pd.to_numeric(pie_source.get("so_tien_con_no", 0), errors="coerce").fillna(0).sum()) <= 0:
                    pie_source = dff.groupby("khu_vuc", as_index=False)["so_tien_thu_duoc"].sum().sort_values("so_tien_thu_duoc", ascending=False)
                    pie_value = "so_tien_thu_duoc"
                    pie_title = f"Tỷ trọng số tiền đã xử lý theo khu vực<br>{dims_show} • {year_txt} • {mo_txt}"
                else:
                    pie_value = "so_tien_con_no"
                    pie_title = f"Tỷ trọng số tiền chênh lệch theo khu vực<br>{dims_show} • {year_txt} • {mo_txt}"
                fig3 = make_vn_donut(pie_source, names="khu_vuc", values=pie_value, title=pie_title, max_slices=10, color_map=REGION_COLOR_MAP, theme=theme)
                pie_source["metric_fmt"] = pie_source[pie_value].apply(fmt_vn)
                rows3 = _bb_drill_rows(dff, ["khu_vuc"], label_from="khu_vuc", label_col="label")
            else:
                pie_source = dff.groupby("thang_label", as_index=False)["so_tien_con_no"].sum().sort_values("so_tien_con_no", ascending=False)
                if float(pd.to_numeric(pie_source.get("so_tien_con_no", 0), errors="coerce").fillna(0).sum()) <= 0:
                    pie_source = dff.groupby("thang_label", as_index=False)["so_tien_thu_duoc"].sum().sort_values("so_tien_thu_duoc", ascending=False)
                    pie_value = "so_tien_thu_duoc"
                    pie_title = f"Tỷ trọng số tiền đã xử lý theo tháng<br>{dims_show} • {year_txt} • {mo_txt}"
                else:
                    pie_value = "so_tien_con_no"
                    pie_title = f"Tỷ trọng số tiền chênh lệch theo tháng<br>{dims_show} • {year_txt} • {mo_txt}"
                pie_source = pie_source.rename(columns={"thang_label": "thang"})
                fig3 = make_vn_donut(pie_source, names="thang", values=pie_value, title=pie_title, max_slices=12, color_map=None, theme=theme)
                pie_source["metric_fmt"] = pie_source[pie_value].apply(fmt_vn)
                rows3 = _bb_drill_rows(dff, ["thang_label"], label_from="thang_label", label_col="label")
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "bb_pie", "metric_label": pie_title})

            table_df = _bb_table_frame(dff)
            style_cell, style_header = _detail_table_theme_styles(theme, prefix)

            return (
                kpi1, kpi2, kpi3,
                fig1, fig2, fig3,
                table_df.to_dict("records"), insight,
                style_cell, style_header,
                kpi1_store, kpi2_store, kpi3_store,
                fig1_store, fig2_store, fig3_store
            )

        total = safe_number(dff[value_col].sum()) if value_col in dff.columns else 0.0
        secondary_total = safe_number(dff[secondary_col].sum()) if secondary_col in dff.columns else 0.0
        months_n = max(int(dff["thang_label"].nunique()) if "thang_label" in dff.columns and not dff.empty else 1, 1)

        total_payload = region_payload_value(dff, value_col, selected_regions=dims, max_items=None)
        secondary_payload = region_payload_value(dff, secondary_col, selected_regions=dims, max_items=None) if secondary_col in dff.columns else []
        avg_payload, avg_lines = _avg_payload_and_lines(dff, dims=dims)

        if avg_mode == "per_month":
            avg = total / months_n
            avg_caption = f"{avg_label} • {months_n} tháng"
        else:
            avg_num_total = safe_number(dff[avg_numerator_col].sum()) if avg_numerator_col in dff.columns else total
            avg_den_total = safe_number(dff[avg_denominator_col].sum()) if avg_denominator_col in dff.columns else secondary_total
            avg = avg_num_total / max(avg_den_total, 1)
            avg_caption = f"{avg_label} • {fmt_vn(avg_den_total)} {avg_divisor_label}"

        year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
        mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else (f"{len(months)} tháng đã chọn" if months else "Tất cả tháng")
        dims_show = ", ".join([str(x) for x in dims]) if dims else "Tất cả khu vực"
        if dims and len(dims) > 3:
            dims_show = f"{len(dims)} khu vực đã chọn"
        tf_txt = ""
        if type_filter_kind == "lh" and type_filter:
            tf_txt = f" • Lọc loại hình: {', '.join(type_filter)}"
        if type_filter_kind == "lh" and _normalize_multi_value(business_filter):
            tf_txt += f" • Hình thức KD: {', '.join(_normalize_multi_value(business_filter))}"
        if type_filter_kind == "hd" and type_filter:
            tf_txt = f" • Lọc loại HĐ: {', '.join(type_filter)}"
        if type_filter_kind == "fleet" and type_filter:
            tf_txt = f" • Lọc loại xe: {', '.join(type_filter)}"

        kpi_subtitle = f"{dims_show} • {year_txt} • {mo_txt}{tf_txt}"
        kpi1 = kpi_content(fmt_vn(total), kpi_subtitle, region_value_lines_from_payload(total_payload, max_lines=6))
        kpi2 = kpi_content(fmt_vn(secondary_total), kpi_subtitle, region_value_lines_from_payload(secondary_payload, max_lines=6))
        kpi3 = kpi_content(fmt_vn(avg), avg_caption, avg_lines[:6])

        kpi1_store = pack_kpi_store(f"Tổng {metric_label}", fmt_vn(total), kpi_subtitle, total_payload)
        kpi2_store = pack_kpi_store(secondary_label, fmt_vn(secondary_total), kpi_subtitle, secondary_payload)
        kpi3_store = pack_kpi_store(avg_label, fmt_vn(avg), avg_caption, avg_payload)
        insight = f"Tổng {metric_label.lower()}: {fmt_vn(total)} – {dims_show}"

        if dff.empty:
            fig1 = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
            fig2 = empty_figure(f"Không có dữ liệu {secondary_label.lower()}", theme)
            fig3 = empty_figure(f"Không có dữ liệu {metric_label.lower()}", theme)
            style_cell, style_header = _detail_table_theme_styles(theme, prefix)
            return (
                kpi1, kpi2, kpi3,
                fig1, fig2, fig3,
                [], insight,
                style_cell, style_header,
                kpi1_store, kpi2_store, kpi3_store,
                pack_fig_store(fig1, rows=[], meta={"chart": "line_kv", "metric_label": metric_label}),
                pack_fig_store(fig2, rows=[], meta={"chart": "bar_kv", "metric_label": secondary_label}),
                pack_fig_store(fig3, rows=[], meta={"chart": "pie_kv", "metric_label": metric_label}),
            )

        if "khu_vuc" in dff.columns:
            dff_kv, kv_col = (dff.copy(), "khu_vuc") if dims else top_n_keep_other(dff, "khu_vuc", value_col, n=None, other_label="Khác", keep_cats=PINNED_REGIONS)
            gkv = dff_kv.groupby(["thang_nam_vn", kv_col], as_index=False).agg({value_col: "sum"}).sort_values("thang_nam_vn")
            gkv["val_fmt"] = gkv[value_col].apply(fmt_vn)
            gkv["thang_label"] = gkv["thang_nam_vn"].dt.strftime("%m/%Y")
            kv_order = gkv.groupby(kv_col, as_index=False)[value_col].sum().sort_values(value_col, ascending=False)[kv_col].tolist()
            fig1 = px.line(
                gkv, x="thang_nam_vn", y=value_col, color=kv_col,
                category_orders={kv_col: kv_order},
                color_discrete_map=REGION_COLOR_MAP,
                markers=True, hover_data={"val_fmt": True, value_col: False}
            )
            fig1.update_traces(line_shape="spline", line_width=3, marker_size=7)
            fig1.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
            fig1 = apply_theme(fig1, theme)
            fig1 = apply_chart_title(fig1, f"{metric_label} theo tháng • So sánh khu vực<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}", top=220, y_title=metric_axis)
            fig1 = _add_line_point_labels(fig1, show_all_if_points_le=10)
            rows1 = [{"thang_label": r["thang_label"], "khu_vuc": str(r[kv_col]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in gkv.iterrows()]
            fig1_store = pack_fig_store(fig1, rows=rows1, meta={"chart": "line_kv", "metric_label": metric_label, "series_field": kv_col})
        else:
            fig1 = empty_figure("Không có dữ liệu khu vực", theme)
            fig1_store = pack_fig_store(fig1, rows=[], meta={"chart": "line_kv", "metric_label": metric_label})

        if secondary_col in dff.columns:
            if len(dims) >= 2:
                gsc = dff.groupby(["thang_nam_vn", "khu_vuc"], as_index=False).agg({secondary_col: "sum"}).sort_values("thang_nam_vn")
                gsc["metric_fmt"] = gsc[secondary_col].apply(fmt_vn)
                gsc["thang_label"] = gsc["thang_nam_vn"].dt.strftime("%m/%Y")
                kv_order2 = gsc.groupby("khu_vuc", as_index=False)[secondary_col].sum().sort_values(secondary_col, ascending=False)["khu_vuc"].tolist()
                if prefix == "hd":
                    fig2 = px.bar(
                        gsc,
                        x="thang_nam_vn",
                        y=secondary_col,
                        color="khu_vuc",
                        category_orders={"khu_vuc": kv_order2},
                        color_discrete_map=REGION_COLOR_MAP,
                        hover_data={"metric_fmt": True, secondary_col: False}
                    )
                    fig2.update_layout(barmode="stack", bargap=0.18, legend=dict(orientation="h", yanchor="bottom", y=1.12, xanchor="left", x=0), hovermode="x unified")
                    gt = gsc.groupby("thang_nam_vn", as_index=False)[secondary_col].sum().sort_values("thang_nam_vn")
                    gt["metric_fmt"] = gt[secondary_col].apply(fmt_vn)
                    total_text = gt["metric_fmt"].tolist() if len(gt) <= 10 else ([""] * max(len(gt)-1,0) + [gt["metric_fmt"].iloc[-1]])
                    fig2.add_scatter(x=gt["thang_nam_vn"], y=gt[secondary_col], mode="lines+markers+text", name="Tổng", text=total_text, textposition="top center", line=dict(width=3), marker=dict(size=7))
                    fig2 = apply_theme(fig2, theme)
                    fig2 = apply_chart_title(fig2, f"{secondary_label} theo tháng • Stacked theo khu vực<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}", top=220, y_title=secondary_label)
                else:
                    fig2 = px.bar(
                        gsc,
                        x="thang_nam_vn",
                        y=secondary_col,
                        color="khu_vuc",
                        category_orders={"khu_vuc": kv_order2},
                        color_discrete_map=REGION_COLOR_MAP,
                        text="metric_fmt",
                        hover_data={"metric_fmt": True, secondary_col: False}
                    )
                    fig2.update_layout(barmode="group", legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
                    fig2.update_traces(textposition="auto", cliponaxis=False)
                    fig2 = apply_theme(fig2, theme)
                    fig2 = apply_chart_title(fig2, f"{secondary_label} theo tháng • So sánh theo khu vực<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}", top=220, y_title=secondary_label)
                rows2 = [{"thang_label": r["thang_label"], "khu_vuc": str(r["khu_vuc"]), "metric": float(r[secondary_col]), "metric_fmt": r["metric_fmt"]} for _, r in gsc.iterrows()]
                fig2_store = pack_fig_store(fig2, rows=rows2, meta={"chart": "bar_kv", "metric_label": secondary_label, "series_field": "khu_vuc"})
            else:
                dff_bar = dff.copy()
                dff_bar["metric_fmt"] = dff_bar[secondary_col].apply(fmt_vn)
                dff_bar["thang_label"] = dff_bar["thang_nam_vn"].dt.strftime("%m/%Y")
                fig2 = px.bar(dff_bar, x="thang_nam_vn", y=secondary_col, text="metric_fmt", hover_data={"metric_fmt": True, secondary_col: False})
                fig2.update_traces(textposition="outside", cliponaxis=False)
                fig2.update_layout(margin=dict(t=20))
                fig2 = apply_theme(fig2, theme)
                fig2 = apply_chart_title(fig2, f"{secondary_label} theo tháng • Khu vực đã chọn<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}", top=220, y_title=secondary_label)
                fig2_store = pack_fig_store(fig2, rows=dff_bar[["thang_label", "metric_fmt"]].to_dict("records"), meta={"chart": "bar_total", "metric_label": secondary_label})
        else:
            fig2 = empty_figure(f"Không có dữ liệu {secondary_label.lower()}", theme)
            fig2_store = pack_fig_store(fig2, rows=[], meta={"chart": "bar_unknown", "metric_label": secondary_label})

        if len(dims) >= 2 and "khu_vuc" in dff.columns:
            fig3 = make_vn_donut(dff, names="khu_vuc", values=value_col, title=f"Tỷ trọng đóng góp theo khu vực • {metric_label}<br>{year_txt} • {mo_txt}{tf_txt}", max_slices=10, color_map=REGION_COLOR_MAP, theme=theme)
            g3 = dff.groupby("khu_vuc", as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
            g3["val_fmt"] = g3[value_col].apply(fmt_vn)
            rows3 = [{"label": str(r["khu_vuc"]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in g3.iterrows()]
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "pie_kv", "metric_label": metric_label})
        else:
            dff_pie = dff.copy()
            dff_pie["thang"] = dff_pie["thang_nam_vn"].dt.strftime("%m/%Y")
            fig3 = make_vn_donut(dff_pie, names="thang", values=value_col, title=f"Tỷ trọng {metric_label.lower()} theo tháng<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}", max_slices=12, color_map=None, theme=theme)
            g3 = dff_pie.groupby("thang", as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
            g3["val_fmt"] = g3[value_col].apply(fmt_vn)
            rows3 = [{"label": str(r["thang"]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in g3.iterrows()]
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "pie_month", "metric_label": metric_label})

        dff_table = dff.copy()
        for col in ["thang_nam", "thang_nam_vn"]:
            if col in dff_table.columns:
                dff_table[col] = pd.to_datetime(dff_table[col], errors="coerce").dt.strftime("%m/%Y").fillna("")
        if "nam" in dff_table.columns:
            dff_table["nam"] = pd.to_numeric(dff_table["nam"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
        num_cols = [c for c in dff_table.select_dtypes(include="number").columns if c != "nam"]
        for c in num_cols:
            dff_table[c] = dff_table[c].apply(fmt_vn)

        style_cell, style_header = _detail_table_theme_styles(theme, prefix)

        return (
            kpi1, kpi2, kpi3,
            fig1, fig2, fig3,
            dff_table.to_dict("records"),
            insight,
            style_cell, style_header,
            kpi1_store, kpi2_store, kpi3_store,
            fig1_store, fig2_store, fig3_store
        )

def _hr_filter_df(dff: pd.DataFrame, year_val=None, months=None, regions=None, departments=None) -> pd.DataFrame:
    out = apply_region_scope_to_df(dff)
    out = _apply_real_data_cutoff(out)
    if year_val is not None and "nam" in out.columns:
        out = out[out["nam"] == int(year_val)]
    if months and "thang_label" in out.columns:
        out = out[out["thang_label"].isin(months)]
    if regions and "khu_vuc" in out.columns:
        allowed_regions = filter_regions_for_current_user(regions)
        if allowed_regions:
            out = out[out["khu_vuc"].astype(str).isin([str(x) for x in allowed_regions])]
        else:
            out = out.iloc[0:0].copy()
    if departments and "bo_phan" in out.columns:
        out = out[out["bo_phan"].astype(str).isin([str(x) for x in departments])]
    return out


def _hr_snapshot_df(dff: pd.DataFrame):
    if dff is None or dff.empty or "thang_nam_vn" not in dff.columns:
        return dff.iloc[0:0].copy(), None, ""
    latest_ts = pd.to_datetime(dff["thang_nam_vn"], errors="coerce").max()
    if pd.isna(latest_ts):
        return dff.iloc[0:0].copy(), None, ""
    snap = dff[dff["thang_nam_vn"] == latest_ts].copy()
    return snap, latest_ts, latest_ts.strftime("%m/%Y")


def _hr_filter_text(year_val=None, months=None, regions=None, departments=None):
    year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
    mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else (f"{len(months)} tháng đã chọn" if months else "Tất cả tháng")
    region_txt = regions[0] if isinstance(regions, list) and len(regions) == 1 else (f"{len(regions)} khu vực" if regions else ("Phạm vi tài khoản" if current_user_region_scope() is not None else "Tất cả khu vực"))
    dept_txt = departments[0] if isinstance(departments, list) and len(departments) == 1 else (f"{len(departments)} bộ phận" if departments else "Tất cả bộ phận")
    return year_txt, mo_txt, region_txt, dept_txt


def _hr_lifecycle_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "nhom": ["Dưới 1 năm", "1 - 3 năm", "Trên 3 năm"],
        "gia_tri": [
            float(snapshot.get("so_duoi_1_nam", pd.Series(dtype=float)).sum()),
            float(snapshot.get("so_tu_1_den_3_nam", pd.Series(dtype=float)).sum()),
            float(snapshot.get("so_tren_3_nam", pd.Series(dtype=float)).sum()),
        ]
    })


def _hr_driver_retention_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "nhom": ["Giữ ổn định", "Vào làm", "Nghỉ việc"],
        "gia_tri": [
            float(snapshot.get("so_giu_on_dinh", pd.Series(dtype=float)).sum()),
            float(snapshot.get("so_vao_lam", pd.Series(dtype=float)).sum()),
            float(snapshot.get("so_nghi_viec", pd.Series(dtype=float)).sum()),
        ]
    })


def _hr_previous_snapshot_df(dff: pd.DataFrame, latest_ts):
    if dff is None or dff.empty or latest_ts is None or "thang_nam_vn" not in dff.columns:
        return dff.iloc[0:0].copy(), None, ""
    ts_values = pd.to_datetime(dff["thang_nam_vn"], errors="coerce").dropna().sort_values().unique().tolist()
    prev_candidates = [ts for ts in ts_values if pd.Timestamp(ts) < pd.Timestamp(latest_ts)]
    if not prev_candidates:
        return dff.iloc[0:0].copy(), None, ""
    prev_ts = pd.Timestamp(prev_candidates[-1])
    snap = dff[dff["thang_nam_vn"] == prev_ts].copy()
    return snap, prev_ts, prev_ts.strftime("%m/%Y")


def _hr_metric_delta(curr: float, prev: float):
    curr = safe_number(curr)
    prev = safe_number(prev)
    diff = curr - prev
    pct = (diff / prev * 100.0) if prev > 0 else (100.0 if curr > 0 else 0.0)
    return diff, pct


def _hr_delta_class(diff: float) -> str:
    if diff > 0:
        return "positive"
    if diff < 0:
        return "negative"
    return "neutral"


def _hr_monthly_snapshot(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame(columns=["thang_nam_vn", "thang_label", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan", "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"])
    g = dff.groupby("thang_nam_vn", as_index=False).agg(
        so_luong_nhan_su=("so_luong_nhan_su", "sum"),
        so_vao_lam=("so_vao_lam", "sum"),
        so_nghi_viec=("so_nghi_viec", "sum"),
        so_duoi_1_nam=("so_duoi_1_nam", "sum"),
        so_tu_1_den_3_nam=("so_tu_1_den_3_nam", "sum"),
        so_tren_3_nam=("so_tren_3_nam", "sum"),
        headcount_dau_ky=("headcount_dau_ky", "sum"),
        so_giu_on_dinh=("so_giu_on_dinh", "sum"),
        bien_dong_thuan=("bien_dong_thuan", "sum"),
        ty_le_tang=("ty_le_tang", "mean"),
        ty_le_giam=("ty_le_giam", "mean"),
        ty_le_giu_chan=("ty_le_giu_chan", "mean"),
    ).sort_values("thang_nam_vn")
    g["thang_label"] = pd.to_datetime(g["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y")
    if "bien_dong_thuan" in g.columns:
        g["bien_dong_thuan"] = np.where(g["bien_dong_thuan"].abs() > 0, g["bien_dong_thuan"], g["so_vao_lam"] - g["so_nghi_viec"])
    return g


def _hr_region_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    if snapshot is None or snapshot.empty:
        return pd.DataFrame(columns=["khu_vuc", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "headcount_dau_ky", "so_giu_on_dinh", "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"])
    g = snapshot.groupby("khu_vuc", as_index=False).agg(
        so_luong_nhan_su=("so_luong_nhan_su", "sum"),
        so_vao_lam=("so_vao_lam", "sum"),
        so_nghi_viec=("so_nghi_viec", "sum"),
        so_duoi_1_nam=("so_duoi_1_nam", "sum"),
        so_tu_1_den_3_nam=("so_tu_1_den_3_nam", "sum"),
        so_tren_3_nam=("so_tren_3_nam", "sum"),
        headcount_dau_ky=("headcount_dau_ky", "sum"),
        so_giu_on_dinh=("so_giu_on_dinh", "sum"),
        ty_le_tang=("ty_le_tang", "mean"),
        ty_le_giam=("ty_le_giam", "mean"),
        ty_le_giu_chan=("ty_le_giu_chan", "mean"),
    ).sort_values(["so_luong_nhan_su", "so_giu_on_dinh"], ascending=[False, False])
    return g


def _hr_numeric_sum(dff: pd.DataFrame, col: str) -> float:
    if dff is None or dff.empty or col not in dff.columns:
        return 0.0
    return float(pd.to_numeric(dff[col], errors="coerce").fillna(0).sum())


def _hr_period_month_count(dff: pd.DataFrame) -> int:
    if dff is None or dff.empty or "thang_nam_vn" not in dff.columns:
        return 0
    return int(pd.to_datetime(dff["thang_nam_vn"], errors="coerce").dropna().dt.to_period("M").nunique())


def _hr_period_month_label(dff: pd.DataFrame) -> str:
    n = _hr_period_month_count(dff)
    if n <= 0:
        return "0 tháng"
    return "1 tháng" if n == 1 else f"{n} tháng"


def _hr_period_range_label(dff: pd.DataFrame) -> str:
    if dff is None or dff.empty or "thang_nam_vn" not in dff.columns:
        return ""
    months = pd.to_datetime(dff["thang_nam_vn"], errors="coerce").dropna().dt.to_period("M").drop_duplicates().sort_values()
    if months.empty:
        return ""
    first = months.iloc[0].to_timestamp().strftime("%m/%Y")
    last = months.iloc[-1].to_timestamp().strftime("%m/%Y")
    return first if first == last else f"{first} - {last}"


def _hr_previous_period_df(base_df: pd.DataFrame, current_dff: pd.DataFrame, regions=None, departments=None) -> pd.DataFrame:
    """Return the immediately previous month window with the same number of selected months.

    This is intentionally based on the already-filtered current period, so join/leave KPI
    deltas compare a full selected period against the equivalent previous period instead of
    accidentally comparing only the latest month.
    """
    if base_df is None or base_df.empty or current_dff is None or current_dff.empty or "thang_nam_vn" not in current_dff.columns:
        return base_df.iloc[0:0].copy() if isinstance(base_df, pd.DataFrame) else pd.DataFrame()
    months = pd.to_datetime(current_dff["thang_nam_vn"], errors="coerce").dropna().dt.to_period("M").drop_duplicates().sort_values()
    if months.empty:
        return base_df.iloc[0:0].copy()
    n_months = int(len(months))
    first_month = months.iloc[0].to_timestamp()
    prev_end = first_month - pd.DateOffset(months=1)
    prev_months = pd.date_range(end=prev_end, periods=n_months, freq="MS")
    prev_labels = [pd.Timestamp(x).strftime("%m/%Y") for x in prev_months]
    return _hr_filter_df(base_df, year_val=None, months=prev_labels, regions=regions, departments=departments)


def _hr_period_region_flow(dff: pd.DataFrame, snapshot: pd.DataFrame | None = None) -> pd.DataFrame:
    """Region frame for KPI lines/zoom: headcount stays snapshot, join/leave are period sums."""
    base_cols = [
        "khu_vuc", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec",
        "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam",
        "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
        "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"
    ]
    snap_region = _hr_region_snapshot(snapshot) if snapshot is not None and not snapshot.empty else pd.DataFrame(columns=base_cols)
    if dff is None or dff.empty or "khu_vuc" not in dff.columns:
        out = snap_region.copy()
    else:
        flow = dff.groupby("khu_vuc", as_index=False).agg(
            so_vao_lam=("so_vao_lam", "sum"),
            so_nghi_viec=("so_nghi_viec", "sum"),
            bien_dong_thuan=("bien_dong_thuan", "sum"),
            headcount_dau_ky_period=("headcount_dau_ky", "sum"),
        )
        # When source data has blank net movement, rebuild it from join/leave for the period.
        flow["bien_dong_thuan"] = np.where(
            pd.to_numeric(flow["bien_dong_thuan"], errors="coerce").fillna(0).abs() > 0,
            pd.to_numeric(flow["bien_dong_thuan"], errors="coerce").fillna(0),
            pd.to_numeric(flow["so_vao_lam"], errors="coerce").fillna(0) - pd.to_numeric(flow["so_nghi_viec"], errors="coerce").fillna(0)
        )
        if snap_region.empty:
            out = flow.rename(columns={"headcount_dau_ky_period": "headcount_dau_ky"}).copy()
        else:
            keep_snap = snap_region.drop(columns=["so_vao_lam", "so_nghi_viec", "bien_dong_thuan"], errors="ignore")
            out = keep_snap.merge(flow, on="khu_vuc", how="outer")
            if "headcount_dau_ky" not in out.columns and "headcount_dau_ky_period" in out.columns:
                out["headcount_dau_ky"] = out["headcount_dau_ky_period"]
    for c in base_cols:
        if c not in out.columns:
            out[c] = 0 if c != "khu_vuc" else ""
    for c in [x for x in base_cols if x != "khu_vuc"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    if "headcount_dau_ky_period" in out.columns:
        out["headcount_dau_ky_period"] = pd.to_numeric(out["headcount_dau_ky_period"], errors="coerce").fillna(0)
    return out[base_cols].sort_values(["so_luong_nhan_su", "so_vao_lam", "so_nghi_viec"], ascending=[False, False, False]).copy()


def _hr_period_rate_base(dff: pd.DataFrame, snapshot: pd.DataFrame) -> float:
    # Prefer cumulative headcount base for a selected period, fallback to snapshot headcount.
    base = _hr_numeric_sum(dff, "headcount_dau_ky")
    if base <= 0:
        base = _hr_numeric_sum(snapshot, "so_luong_nhan_su")
    return max(float(base), 1.0)

def _hr_make_kpi_card(main_value, subtitle, delta_text=None, delta_class="neutral", extra_lines=None):
    return home_kpi_markup(main_value, subtitle, delta_text=delta_text, delta_class=delta_class, extra_lines=extra_lines or [])


def _hr_build_kpi_lines(region_df: pd.DataFrame, value_col: str, mode: str = "value"):
    if region_df is None or region_df.empty or value_col not in region_df.columns:
        return []
    rows = region_df.head(4)
    lines = []
    for _, r in rows.iterrows():
        color = REGION_COLOR_MAP.get(str(r.get("khu_vuc", "Khác")), "#888")
        value_txt = fmt_pct(r.get(value_col, 0), 1) if mode == "pct" else fmt_vn(r.get(value_col, 0))
        lines.append(_ellipsis_div([_swatch(color), f"{r.get('khu_vuc', '')}: {value_txt}"]))
    return lines


def _hr_stacked_lifecycle_percent(gm: pd.DataFrame) -> pd.DataFrame:
    if gm is None or gm.empty:
        return pd.DataFrame(columns=["thang_nam_vn", "thang_label", "nhom_vong_doi", "gia_tri", "metric_fmt"])
    life = gm[["thang_nam_vn", "thang_label", "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"]].copy()
    denom = life[["so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"]].sum(axis=1).replace(0, np.nan)
    for c in ["so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"]:
        life[c] = (life[c] / denom * 100.0).fillna(0.0)
    life = life.melt(id_vars=["thang_nam_vn", "thang_label"], value_vars=["so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"], var_name="nhom_vong_doi", value_name="gia_tri")
    life["nhom_vong_doi"] = life["nhom_vong_doi"].map({"so_duoi_1_nam": "Dưới 1 năm", "so_tu_1_den_3_nam": "1 - 3 năm", "so_tren_3_nam": "Trên 3 năm"})
    life["metric_fmt"] = life["gia_tri"].apply(lambda x: fmt_pct(x, 1))
    return life


def _hr_driver_region_retention(region_snapshot: pd.DataFrame) -> pd.DataFrame:
    if region_snapshot is None or region_snapshot.empty:
        return pd.DataFrame(columns=["khu_vuc", "ty_le_giu_chan"])
    out = region_snapshot[["khu_vuc", "ty_le_giu_chan", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec"]].copy()
    out["ty_le_giu_chan"] = pd.to_numeric(out["ty_le_giu_chan"], errors="coerce").fillna(0.0)
    return out.sort_values(["ty_le_giu_chan", "so_luong_nhan_su"], ascending=[False, False])


def _hr_kpi_zoom_rows(region_df: pd.DataFrame, focus_col: str, focus_mode: str = "value") -> list:
    if region_df is None or region_df.empty or "khu_vuc" not in region_df.columns:
        return []
    d = region_df.copy()
    numeric_cols = [
        "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec",
        "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam",
        "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
        "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"
    ]
    for c in numeric_cols:
        if c not in d.columns:
            d[c] = 0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    if focus_col not in d.columns:
        d[focus_col] = 0
    d[focus_col] = pd.to_numeric(d[focus_col], errors="coerce").fillna(0)

    total_focus = float(d[focus_col].sum()) if focus_mode != "pct" else 0.0
    if focus_mode == "pct":
        d["value_fmt"] = d[focus_col].apply(lambda x: fmt_pct(x, 1))
    else:
        d["value_fmt"] = d[focus_col].apply(fmt_vn)
        d["pct"] = np.where(total_focus > 0, d[focus_col] / total_focus * 100.0, 0.0)
        d["pct_fmt"] = d["pct"].apply(lambda x: fmt_pct(x, 1))

    for c in ["so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "headcount_dau_ky", "so_giu_on_dinh"]:
        d[f"{c}_fmt"] = d[c].apply(fmt_vn)
    d["bien_dong_thuan_fmt"] = d["bien_dong_thuan"].apply(signed_diff_text)
    for c in ["ty_le_tang", "ty_le_giam", "ty_le_giu_chan"]:
        d[f"{c}_fmt"] = d[c].apply(lambda x: fmt_pct(x, 1))

    sort_cols = [focus_col]
    ascending = [False]
    if "so_luong_nhan_su" in d.columns and focus_col != "so_luong_nhan_su":
        sort_cols.append("so_luong_nhan_su")
        ascending.append(False)
    d = d.sort_values(sort_cols, ascending=ascending)

    keep = [
        "khu_vuc", "value_fmt", "pct", "pct_fmt",
        "so_luong_nhan_su_fmt", "so_vao_lam_fmt", "so_nghi_viec_fmt",
        "so_duoi_1_nam_fmt", "so_tu_1_den_3_nam_fmt", "so_tren_3_nam_fmt",
        "headcount_dau_ky_fmt", "so_giu_on_dinh_fmt", "bien_dong_thuan_fmt",
        "ty_le_tang_fmt", "ty_le_giam_fmt", "ty_le_giu_chan_fmt"
    ]
    keep = [c for c in keep if c in d.columns]
    return d[keep].to_dict("records")


def _hr_flow_drill_rows(dff: pd.DataFrame, join_label: str, leave_label: str) -> list:
    if dff is None or dff.empty:
        return []
    g = dff.groupby(["thang_label", "khu_vuc"], as_index=False).agg(
        so_vao_lam=("so_vao_lam", "sum"),
        so_nghi_viec=("so_nghi_viec", "sum"),
        bien_dong_thuan=("bien_dong_thuan", "sum")
    )
    g[join_label] = g["so_vao_lam"]
    g[leave_label] = g["so_nghi_viec"]
    g["Biến động thuần"] = g["bien_dong_thuan"]
    long = g.melt(
        id_vars=["thang_label", "khu_vuc"],
        value_vars=[join_label, leave_label, "Biến động thuần"],
        var_name="label",
        value_name="gia_tri"
    )
    long["metric_fmt"] = np.where(
        long["label"].eq("Biến động thuần"),
        long["gia_tri"].apply(signed_diff_text),
        long["gia_tri"].apply(fmt_vn)
    )
    return long[["thang_label", "khu_vuc", "label", "metric_fmt"]].to_dict("records")


def _hr_driver_rate_drill_rows(dff: pd.DataFrame) -> list:
    if dff is None or dff.empty:
        return []
    g = dff.groupby(["thang_label", "khu_vuc"], as_index=False).agg(
        headcount_dau_ky=("headcount_dau_ky", "sum"),
        so_vao_lam=("so_vao_lam", "sum"),
        so_nghi_viec=("so_nghi_viec", "sum"),
        so_giu_on_dinh=("so_giu_on_dinh", "sum")
    )
    g["Tỷ lệ tăng"] = np.where(g["headcount_dau_ky"] > 0, g["so_vao_lam"] / g["headcount_dau_ky"] * 100.0, np.where(g["so_vao_lam"] > 0, 100.0, 0.0))
    g["Tỷ lệ giảm"] = np.where(g["headcount_dau_ky"] > 0, g["so_nghi_viec"] / g["headcount_dau_ky"] * 100.0, 0.0)
    g["Tỷ lệ giữ chân"] = np.where(g["headcount_dau_ky"] > 0, g["so_giu_on_dinh"] / g["headcount_dau_ky"] * 100.0, np.where((g["so_giu_on_dinh"] + g["so_vao_lam"]) > 0, 100.0, 0.0))
    long = g.melt(
        id_vars=["thang_label", "khu_vuc"],
        value_vars=["Tỷ lệ tăng", "Tỷ lệ giảm", "Tỷ lệ giữ chân"],
        var_name="label",
        value_name="gia_tri"
    )
    long["metric_fmt"] = long["gia_tri"].apply(lambda x: fmt_pct(x, 1))
    return long[["thang_label", "khu_vuc", "label", "metric_fmt"]].to_dict("records")


def _hr_lifecycle_percent_by_region(dff: pd.DataFrame) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame(columns=["thang_label", "khu_vuc", "nhom_vong_doi", "metric_fmt", "count_fmt", "pct_segment_fmt"])
    g = dff.groupby(["thang_nam_vn", "thang_label", "khu_vuc"], as_index=False).agg(
        so_duoi_1_nam=("so_duoi_1_nam", "sum"),
        so_tu_1_den_3_nam=("so_tu_1_den_3_nam", "sum"),
        so_tren_3_nam=("so_tren_3_nam", "sum")
    )
    g["tong_vong_doi"] = g[["so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"]].sum(axis=1)
    long = g.melt(
        id_vars=["thang_nam_vn", "thang_label", "khu_vuc", "tong_vong_doi"],
        value_vars=["so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam"],
        var_name="nhom_vong_doi",
        value_name="so_luong"
    )
    long["nhom_vong_doi"] = long["nhom_vong_doi"].map({
        "so_duoi_1_nam": "Dưới 1 năm",
        "so_tu_1_den_3_nam": "1 - 3 năm",
        "so_tren_3_nam": "Trên 3 năm"
    })
    long["gia_tri"] = np.where(long["tong_vong_doi"] > 0, long["so_luong"] / long["tong_vong_doi"] * 100.0, 0.0)
    long["metric_fmt"] = long["gia_tri"].apply(lambda x: fmt_pct(x, 1))
    long["count_fmt"] = long["so_luong"].apply(fmt_vn)
    long["pct_segment_fmt"] = long["metric_fmt"]
    return long[["thang_label", "khu_vuc", "nhom_vong_doi", "metric_fmt", "count_fmt", "pct_segment_fmt"]]


def _hr_pie_drill_rows(region_snapshot: pd.DataFrame, prefix: str) -> list:
    if region_snapshot is None or region_snapshot.empty:
        return []
    d = region_snapshot.copy()
    if prefix == "drv":
        long = pd.DataFrame({
            "khu_vuc": list(d["khu_vuc"]) * 3,
            "label": (["Giữ ổn định"] * len(d)) + (["Vào làm"] * len(d)) + (["Nghỉ việc"] * len(d)),
            "gia_tri": list(pd.to_numeric(d.get("so_giu_on_dinh", 0), errors="coerce").fillna(0))
                       + list(pd.to_numeric(d.get("so_vao_lam", 0), errors="coerce").fillna(0))
                       + list(pd.to_numeric(d.get("so_nghi_viec", 0), errors="coerce").fillna(0))
        })
    else:
        long = pd.DataFrame({
            "khu_vuc": list(d["khu_vuc"]) * 3,
            "label": (["Dưới 1 năm"] * len(d)) + (["1 - 3 năm"] * len(d)) + (["Trên 3 năm"] * len(d)),
            "gia_tri": list(pd.to_numeric(d.get("so_duoi_1_nam", 0), errors="coerce").fillna(0))
                       + list(pd.to_numeric(d.get("so_tu_1_den_3_nam", 0), errors="coerce").fillna(0))
                       + list(pd.to_numeric(d.get("so_tren_3_nam", 0), errors="coerce").fillna(0))
        })
    total_by_label = long.groupby("label", as_index=False)["gia_tri"].sum().rename(columns={"gia_tri": "tong_label"})
    long = long.merge(total_by_label, on="label", how="left")
    long["pct"] = np.where(long["tong_label"] > 0, long["gia_tri"] / long["tong_label"] * 100.0, 0.0)
    long["metric_fmt"] = long["gia_tri"].apply(fmt_vn)
    long["pct_fmt"] = long["pct"].apply(lambda x: fmt_pct(x, 1))
    return long[["khu_vuc", "label", "metric_fmt", "pct", "pct_fmt"]].to_dict("records")


def _hr_style_table(theme: str):
    return _detail_table_theme_styles(theme, "emp")


def hr_callbacks(prefix: str):
    cfg = get_menu_config(prefix)
    df = cfg["df"]
    metric_label = cfg["metric_label"]
    join_label = cfg["secondary_label"]
    leave_label = cfg["avg_label"]

    @app.callback(
        Output(f"{prefix}-p1-kpi1","children"),
        Output(f"{prefix}-p1-kpi2","children"),
        Output(f"{prefix}-p1-kpi3","children"),
        Output(f"{prefix}-p1-line-kv","figure"),
        Output(f"{prefix}-p1-line","figure"),
        Output(f"{prefix}-p1-bar","figure"),
        Output(f"{prefix}-p1-pie","figure"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi1"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi2"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi3"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-line-kv"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-line"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-bar"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-pie"}, "data"),
        Input(f"{prefix}-year", "value", allow_optional=True),
        Input(f"{prefix}-month", "value", allow_optional=True),
        Input(f"{prefix}-region", "value", allow_optional=True),
        Input(f"{prefix}-dept", "value", allow_optional=True),
        State("theme", "data"),
        State("menu", "data"),
        State("page", "data"),
    )
    def hr_p1(year_val, months, regions, departments, theme, menu, page):
        nonlocal cfg, df, metric_label, join_label, leave_label
        ensure_menu_data_loaded(prefix)
        cfg = get_menu_config(prefix)
        df = cfg["df"]
        metric_label = cfg["metric_label"]
        join_label = cfg["secondary_label"]
        leave_label = cfg["avg_label"]
        if menu != prefix or int(page) != 1:
            raise PreventUpdate
        regions = regions if isinstance(regions, list) else ([regions] if regions else [])
        departments = departments if isinstance(departments, list) else ([departments] if departments else [])
        dff = _hr_filter_df(df, year_val, months or [], regions, departments)
        gm = _hr_monthly_snapshot(dff)
        snapshot, latest_ts, latest_label = _hr_snapshot_df(dff)
        prev_snapshot, _prev_ts, prev_label = _hr_previous_snapshot_df(dff, latest_ts)
        region_snapshot = _hr_region_snapshot(snapshot)
        period_region_flow = _hr_period_region_flow(dff, snapshot)
        prev_period_df = _hr_previous_period_df(df, dff, regions=regions, departments=departments)

        headcount = safe_number(snapshot.get("so_luong_nhan_su", pd.Series(dtype=float)).sum())
        join_count = safe_number(_hr_numeric_sum(dff, "so_vao_lam"))
        leave_count = safe_number(_hr_numeric_sum(dff, "so_nghi_viec"))
        prev_headcount = safe_number(prev_snapshot.get("so_luong_nhan_su", pd.Series(dtype=float)).sum())
        prev_join = safe_number(_hr_numeric_sum(prev_period_df, "so_vao_lam"))
        prev_leave = safe_number(_hr_numeric_sum(prev_period_df, "so_nghi_viec"))
        diff_head, pct_head = _hr_metric_delta(headcount, prev_headcount)
        diff_join, pct_join = _hr_metric_delta(join_count, prev_join)
        diff_leave, pct_leave = _hr_metric_delta(leave_count, prev_leave)
        year_txt, mo_txt, region_txt, dept_txt = _hr_filter_text(year_val, months or [], regions, departments)
        period_label = _hr_period_month_label(dff)
        subtitle = f"Snapshot tháng {latest_label if latest_label else ''} • {year_txt} • {mo_txt} • {region_txt} • {dept_txt}"
        flow_subtitle = f"Tổng theo bộ lọc • {period_label} • {year_txt} • {mo_txt} • {region_txt} • {dept_txt}"
        prev_period_txt = _hr_period_range_label(prev_period_df)
        compare_sub = prev_period_txt if prev_period_txt else (prev_label if prev_label else "kỳ liền trước")
        rate_base = _hr_period_rate_base(dff, snapshot)
        join_rate = (join_count / rate_base * 100.0) if rate_base > 0 else 0.0
        leave_rate = (leave_count / rate_base * 100.0) if rate_base > 0 else 0.0
        retention_rate = safe_number(snapshot.get("ty_le_giu_chan", pd.Series(dtype=float)).mean()) if prefix == "drv" else max(0.0, 100.0 - leave_rate)

        kpi1 = _hr_make_kpi_card(fmt_vn(headcount), subtitle, f"{signed_diff_text(diff_head)} • {signed_pct_text(pct_head)} • so với {prev_label if prev_label else 'kỳ trước'}", _hr_delta_class(diff_head), _hr_build_kpi_lines(region_snapshot, "so_luong_nhan_su"))
        kpi2 = _hr_make_kpi_card(fmt_vn(join_count), f"{join_label} • Tổng {period_label} • Tỷ lệ vào làm {fmt_pct(join_rate, 1)}", f"{signed_diff_text(diff_join)} • {signed_pct_text(pct_join)} • so với {compare_sub}", _hr_delta_class(diff_join), _hr_build_kpi_lines(period_region_flow, "so_vao_lam"))
        kpi3 = _hr_make_kpi_card(fmt_vn(leave_count), f"{leave_label} • Tổng {period_label} • Tỷ lệ nghỉ việc {fmt_pct(leave_rate, 1)}" + (f" • Giữ chân {fmt_pct(retention_rate, 1)}" if prefix == "drv" else ""), f"{signed_diff_text(diff_leave)} • {signed_pct_text(pct_leave)} • so với {compare_sub}", _hr_delta_class(-diff_leave), _hr_build_kpi_lines(period_region_flow, "so_nghi_viec"))

        kpi1_store = pack_kpi_store(metric_label, fmt_vn(headcount), subtitle, _hr_kpi_zoom_rows(region_snapshot, "so_luong_nhan_su"))
        kpi2_store = pack_kpi_store(join_label, fmt_vn(join_count), flow_subtitle, _hr_kpi_zoom_rows(period_region_flow, "so_vao_lam"))
        kpi3_store = pack_kpi_store(
            leave_label,
            fmt_vn(leave_count),
            flow_subtitle,
            _hr_kpi_zoom_rows(period_region_flow, "so_nghi_viec")
        )

        if dff.empty or gm.empty:
            fig_empty = empty_figure("Không có dữ liệu nhân sự", theme)
            empty_store = pack_fig_store(fig_empty, rows=[], meta={"chart": "hr_empty", "metric_label": metric_label})
            return kpi1, kpi2, kpi3, fig_empty, fig_empty, fig_empty, fig_empty, kpi1_store, kpi2_store, kpi3_store, empty_store, empty_store, empty_store, empty_store

        gkv = dff.groupby(["thang_nam_vn", "khu_vuc"], as_index=False).agg(so_luong_nhan_su=("so_luong_nhan_su", "sum")).sort_values("thang_nam_vn")
        gkv["metric_fmt"] = gkv["so_luong_nhan_su"].apply(fmt_vn)
        gkv["thang_label"] = gkv["thang_nam_vn"].dt.strftime("%m/%Y")
        kv_order = gkv.groupby("khu_vuc", as_index=False)["so_luong_nhan_su"].sum().sort_values("so_luong_nhan_su", ascending=False)["khu_vuc"].tolist()
        fig_kv = px.line(gkv, x="thang_nam_vn", y="so_luong_nhan_su", color="khu_vuc", category_orders={"khu_vuc": kv_order}, color_discrete_map=REGION_COLOR_MAP, markers=True, hover_data={"metric_fmt": True, "so_luong_nhan_su": False})
        fig_kv.update_traces(line_shape="spline", line_width=3, marker_size=7)
        fig_kv.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
        fig_kv = apply_theme(fig_kv, theme)
        fig_kv = apply_chart_title(fig_kv, f"{metric_label} theo tháng • So sánh khu vực<br>{year_txt} • {mo_txt} • {dept_txt}", top=210, y_title=metric_label)
        fig_kv = _add_line_point_labels(fig_kv, show_all_if_points_le=10)
        fig_kv_store = pack_fig_store(fig_kv, rows=gkv[["thang_label", "khu_vuc", "metric_fmt"]].to_dict("records"), meta={"chart": "line_kv", "metric_label": metric_label})

        gm["join_fmt"] = gm["so_vao_lam"].apply(fmt_vn)
        gm["leave_fmt"] = gm["so_nghi_viec"].apply(fmt_vn)
        gm["net_fmt"] = gm["bien_dong_thuan"].apply(signed_diff_text)
        fig_line = go.Figure()
        fig_line.add_bar(x=gm["thang_nam_vn"], y=gm["so_vao_lam"], name=join_label, customdata=gm[["join_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>" + join_label + ": %{customdata[0]}<extra></extra>")
        fig_line.add_bar(x=gm["thang_nam_vn"], y=-gm["so_nghi_viec"], name=leave_label, customdata=gm[["leave_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>" + leave_label + ": %{customdata[0]}<extra></extra>")
        fig_line.add_scatter(x=gm["thang_nam_vn"], y=gm["bien_dong_thuan"], name="Biến động thuần", mode="lines+markers+text", text=gm["net_fmt"], textposition="top center", customdata=gm[["net_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>Biến động thuần: %{customdata[0]}<extra></extra>")
        fig_line = apply_theme(fig_line, theme)
        fig_line.update_layout(barmode="relative", legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
        fig_line = apply_chart_title(fig_line, f"Dòng chảy nhân sự theo tháng • Vào làm / nghỉ việc / biến động thuần<br>{year_txt} • {region_txt} • {dept_txt}", top=220, y_title="Số lượng")
        fig_line_store = pack_fig_store(fig_line, rows=_hr_flow_drill_rows(dff, join_label, leave_label), meta={"chart": "hr_flow", "metric_label": "Dòng chảy nhân sự", "series_field": "label"})

        life = _hr_stacked_lifecycle_percent(gm)
        fig_bar = px.bar(life, x="thang_nam_vn", y="gia_tri", color="nhom_vong_doi", barmode="stack", text="metric_fmt", hover_data={"metric_fmt": True, "gia_tri": False})
        fig_bar.update_traces(textposition="inside")
        fig_bar.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0), yaxis_ticksuffix="%")
        fig_bar = apply_theme(fig_bar, theme)
        fig_bar = apply_chart_title(fig_bar, f"Cơ cấu vòng đời nhân sự theo tháng • Tỷ trọng 3 nhóm<br>{year_txt} • {region_txt} • {dept_txt}", top=210, y_title="Tỷ trọng (%)")
        fig_bar_store = pack_fig_store(fig_bar, rows=_hr_lifecycle_percent_by_region(dff).to_dict("records"), meta={"chart": "lifecycle_percent", "metric_label": "Tỷ trọng vòng đời", "series_field": "nhom_vong_doi"})

        pie_df = _hr_driver_retention_snapshot(snapshot) if prefix == "drv" else _hr_lifecycle_snapshot(snapshot)
        pie_title = (f"Cơ cấu giữ chân tài xế • Snapshot {latest_label}<br>{region_txt} • {dept_txt}" if prefix == "drv" else f"Cơ cấu vòng đời nhân sự • Snapshot {latest_label}<br>{region_txt} • {dept_txt}")
        fig_pie = make_vn_donut(pie_df, names="nhom", values="gia_tri", title=pie_title, max_slices=6, color_map=None, theme=theme)
        pie_df["metric_fmt"] = pie_df["gia_tri"].apply(fmt_vn)
        fig_pie_store = pack_fig_store(fig_pie, rows=_hr_pie_drill_rows(region_snapshot, prefix), meta={"chart": "pie", "metric_label": pie_title, "series_field": "label"})

        return kpi1, kpi2, kpi3, fig_kv, fig_line, fig_bar, fig_pie, kpi1_store, kpi2_store, kpi3_store, fig_kv_store, fig_line_store, fig_bar_store, fig_pie_store

    @app.callback(
        Output(f"{prefix}-kpi1","children"),
        Output(f"{prefix}-kpi2","children"),
        Output(f"{prefix}-kpi3","children"),
        Output(f"{prefix}-p2-line","figure"),
        Output(f"{prefix}-p2-bar","figure"),
        Output(f"{prefix}-p2-pie","figure"),
        Output(f"{prefix}-table","data"),
        Output(f"{prefix}-insight","children"),
        Output(f"{prefix}-table","style_cell"),
        Output(f"{prefix}-table","style_header"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi1"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi2"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi3"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-line"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-bar"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-pie"}, "data"),
        Input(f"{prefix}-dim","value", allow_optional=True),
        Input(f"{prefix}-year-p2","value", allow_optional=True),
        Input(f"{prefix}-month-p2","value", allow_optional=True),
        Input(f"{prefix}-dept-p2","value", allow_optional=True),
        State("theme", "data"),
        State("menu", "data"),
        State("page", "data"),
    )
    def hr_p2(dims, year_val, months, departments, theme, menu, page):
        nonlocal cfg, df, metric_label, join_label, leave_label
        ensure_menu_data_loaded(prefix)
        cfg = get_menu_config(prefix)
        df = cfg["df"]
        metric_label = cfg["metric_label"]
        join_label = cfg["secondary_label"]
        leave_label = cfg["avg_label"]
        if menu != prefix or int(page) != 2:
            raise PreventUpdate
        dims = dims if isinstance(dims, list) else ([dims] if dims else [])
        departments = departments if isinstance(departments, list) else ([departments] if departments else [])
        dff = _hr_filter_df(df, year_val, months or [], dims, departments)
        gm = _hr_monthly_snapshot(dff)
        snapshot, latest_ts, latest_label = _hr_snapshot_df(dff)
        prev_snapshot, _prev_ts, prev_label = _hr_previous_snapshot_df(dff, latest_ts)
        region_snapshot = _hr_region_snapshot(snapshot)
        period_region_flow = _hr_period_region_flow(dff, snapshot)
        prev_period_df = _hr_previous_period_df(df, dff, regions=dims, departments=departments)

        headcount = safe_number(snapshot.get("so_luong_nhan_su", pd.Series(dtype=float)).sum())
        join_count = safe_number(_hr_numeric_sum(dff, "so_vao_lam"))
        leave_count = safe_number(_hr_numeric_sum(dff, "so_nghi_viec"))
        prev_headcount = safe_number(prev_snapshot.get("so_luong_nhan_su", pd.Series(dtype=float)).sum())
        prev_join = safe_number(_hr_numeric_sum(prev_period_df, "so_vao_lam"))
        prev_leave = safe_number(_hr_numeric_sum(prev_period_df, "so_nghi_viec"))
        diff_head, pct_head = _hr_metric_delta(headcount, prev_headcount)
        diff_join, pct_join = _hr_metric_delta(join_count, prev_join)
        diff_leave, pct_leave = _hr_metric_delta(leave_count, prev_leave)
        year_txt, mo_txt, region_txt, dept_txt = _hr_filter_text(year_val, months or [], dims, departments)
        period_label = _hr_period_month_label(dff)
        subtitle = f"Snapshot tháng {latest_label if latest_label else ''} • {year_txt} • {mo_txt} • {region_txt} • {dept_txt}"
        flow_subtitle = f"Tổng theo bộ lọc • {period_label} • {year_txt} • {mo_txt} • {region_txt} • {dept_txt}"
        prev_period_txt = _hr_period_range_label(prev_period_df)
        compare_sub = prev_period_txt if prev_period_txt else (prev_label if prev_label else "kỳ liền trước")
        rate_base = _hr_period_rate_base(dff, snapshot)
        join_rate = (join_count / rate_base * 100.0) if rate_base > 0 else 0.0
        leave_rate = (leave_count / rate_base * 100.0) if rate_base > 0 else 0.0
        insight = f"{metric_label}: {fmt_vn(headcount)} • {join_label}: {fmt_vn(join_count)} • {leave_label}: {fmt_vn(leave_count)} • Tổng {period_label}"
        if prefix == "drv":
            retention = safe_number(snapshot.get("ty_le_giu_chan", pd.Series(dtype=float)).mean())
            insight += f" • Giữ chân tài xế: {fmt_pct(retention, 1)}"
        else:
            insight += f" • Biến động thuần: {signed_diff_text(join_count - leave_count)}"

        kpi1 = _hr_make_kpi_card(fmt_vn(headcount), subtitle, f"{signed_diff_text(diff_head)} • {signed_pct_text(pct_head)} • so với {prev_label if prev_label else 'kỳ trước'}", _hr_delta_class(diff_head), _hr_build_kpi_lines(region_snapshot, "so_luong_nhan_su"))
        kpi2 = _hr_make_kpi_card(fmt_vn(join_count), f"{join_label} • Tổng {period_label}", f"Tỷ lệ vào làm {fmt_pct(join_rate, 1)} • so với {compare_sub}: {signed_diff_text(diff_join)} / {signed_pct_text(pct_join)}", _hr_delta_class(diff_join), _hr_build_kpi_lines(period_region_flow, "so_vao_lam"))
        kpi3 = _hr_make_kpi_card(fmt_vn(leave_count), f"{leave_label} • Tổng {period_label} • Biến động thuần {signed_diff_text(join_count - leave_count)}", f"Tỷ lệ nghỉ việc {fmt_pct(leave_rate, 1)} • so với {compare_sub}: {signed_diff_text(diff_leave)} / {signed_pct_text(pct_leave)}", _hr_delta_class(-diff_leave), _hr_build_kpi_lines(period_region_flow, "so_nghi_viec"))

        kpi1_store = pack_kpi_store(metric_label, fmt_vn(headcount), subtitle, _hr_kpi_zoom_rows(region_snapshot, "so_luong_nhan_su"))
        kpi2_store = pack_kpi_store(join_label, fmt_vn(join_count), flow_subtitle, _hr_kpi_zoom_rows(period_region_flow, "so_vao_lam"))
        kpi3_store = pack_kpi_store(
            leave_label,
            fmt_vn(leave_count),
            flow_subtitle,
            _hr_kpi_zoom_rows(period_region_flow, "so_nghi_viec")
        )

        style_cell, style_header = _hr_style_table(theme)
        if dff.empty or gm.empty:
            fig_empty = empty_figure("Không có dữ liệu nhân sự", theme)
            empty_store = pack_fig_store(fig_empty, rows=[], meta={"chart": "hr_empty", "metric_label": metric_label})
            return kpi1, kpi2, kpi3, fig_empty, fig_empty, fig_empty, [], insight, style_cell, style_header, kpi1_store, kpi2_store, kpi3_store, empty_store, empty_store, empty_store

        gline = dff.groupby(["thang_nam_vn", "khu_vuc"], as_index=False).agg(so_luong_nhan_su=("so_luong_nhan_su", "sum")).sort_values("thang_nam_vn")
        gline["metric_fmt"] = gline["so_luong_nhan_su"].apply(fmt_vn)
        gline["thang_label"] = gline["thang_nam_vn"].dt.strftime("%m/%Y")
        kv_order = gline.groupby("khu_vuc", as_index=False)["so_luong_nhan_su"].sum().sort_values("so_luong_nhan_su", ascending=False)["khu_vuc"].tolist()
        fig1 = px.line(gline, x="thang_nam_vn", y="so_luong_nhan_su", color="khu_vuc", category_orders={"khu_vuc": kv_order}, color_discrete_map=REGION_COLOR_MAP, markers=True, hover_data={"metric_fmt": True, "so_luong_nhan_su": False})
        fig1.update_traces(line_shape="spline", line_width=3, marker_size=7)
        fig1.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
        fig1 = apply_theme(fig1, theme)
        fig1 = apply_chart_title(fig1, f"{metric_label} theo tháng • So sánh khu vực<br>{year_txt} • {mo_txt} • {dept_txt}", top=220, y_title=metric_label)
        fig1 = _add_line_point_labels(fig1, show_all_if_points_le=10)
        fig1_store = pack_fig_store(fig1, rows=gline[["thang_label", "khu_vuc", "metric_fmt"]].to_dict("records"), meta={"chart": "line_kv", "metric_label": metric_label})

        if prefix == "drv":
            gr = gm[["thang_nam_vn", "thang_label", "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"]].copy()
            gr["tang_fmt"] = gr["ty_le_tang"].apply(lambda x: fmt_pct(x, 1))
            gr["giam_fmt"] = gr["ty_le_giam"].apply(lambda x: fmt_pct(x, 1))
            gr["giu_fmt"] = gr["ty_le_giu_chan"].apply(lambda x: fmt_pct(x, 1))
            fig2 = go.Figure()
            fig2.add_bar(x=gr["thang_nam_vn"], y=gr["ty_le_tang"], name="Tỷ lệ tăng", customdata=gr[["tang_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>Tỷ lệ tăng: %{customdata[0]}<extra></extra>")
            fig2.add_bar(x=gr["thang_nam_vn"], y=gr["ty_le_giam"], name="Tỷ lệ giảm", customdata=gr[["giam_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>Tỷ lệ giảm: %{customdata[0]}<extra></extra>")
            fig2.add_scatter(x=gr["thang_nam_vn"], y=gr["ty_le_giu_chan"], name="Tỷ lệ giữ chân", mode="lines+markers+text", text=gr["giu_fmt"], textposition="top center", customdata=gr[["giu_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>Tỷ lệ giữ chân: %{customdata[0]}<extra></extra>")
            fig2 = apply_theme(fig2, theme)
            fig2.update_layout(barmode="group", legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0), yaxis_ticksuffix="%")
            fig2 = apply_chart_title(fig2, f"Tỷ trọng tăng / giảm và giữ chân tài xế theo tháng<br>{year_txt} • {region_txt} • {dept_txt}", top=220, y_title="Tỷ lệ (%)")
            fig2_store = pack_fig_store(fig2, rows=_hr_driver_rate_drill_rows(dff), meta={"chart": "driver_rate_combo", "metric_label": "Tỷ lệ tăng giảm và giữ chân", "series_field": "label"})
        else:
            gbar = gm[["thang_nam_vn", "thang_label", "so_vao_lam", "so_nghi_viec", "bien_dong_thuan"]].copy()
            gbar["join_fmt"] = gbar["so_vao_lam"].apply(fmt_vn)
            gbar["leave_fmt"] = gbar["so_nghi_viec"].apply(fmt_vn)
            gbar["net_fmt"] = gbar["bien_dong_thuan"].apply(signed_diff_text)
            fig2 = go.Figure()
            fig2.add_bar(x=gbar["thang_nam_vn"], y=gbar["so_vao_lam"], name=join_label, customdata=gbar[["join_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>" + join_label + ": %{customdata[0]}<extra></extra>")
            fig2.add_bar(x=gbar["thang_nam_vn"], y=gbar["so_nghi_viec"], name=leave_label, customdata=gbar[["leave_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>" + leave_label + ": %{customdata[0]}<extra></extra>")
            fig2.add_scatter(x=gbar["thang_nam_vn"], y=gbar["bien_dong_thuan"], name="Biến động thuần", mode="lines+markers+text", text=gbar["net_fmt"], textposition="top center", customdata=gbar[["net_fmt"]].to_numpy(), hovertemplate="Tháng: %{x|%m/%Y}<br>Biến động thuần: %{customdata[0]}<extra></extra>")
            fig2 = apply_theme(fig2, theme)
            fig2.update_layout(barmode="group", legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0))
            fig2 = apply_chart_title(fig2, f"Vào làm / nghỉ việc và biến động thuần theo tháng<br>{year_txt} • {region_txt} • {dept_txt}", top=220, y_title="Số lượng")
            fig2_store = pack_fig_store(fig2, rows=_hr_flow_drill_rows(dff, join_label, leave_label), meta={"chart": "join_leave_net", "metric_label": "Biến động nhân sự", "series_field": "label"})

        pie_df = _hr_driver_retention_snapshot(snapshot) if prefix == "drv" else _hr_lifecycle_snapshot(snapshot)
        pie_title = (f"Cơ cấu giữ chân tài xế • Snapshot {latest_label}<br>{region_txt} • {dept_txt}" if prefix == "drv" else f"Cơ cấu vòng đời nhân sự • Snapshot {latest_label}<br>{region_txt} • {dept_txt}")
        fig3 = make_vn_donut(pie_df, names="nhom", values="gia_tri", title=pie_title, max_slices=6, color_map=None, theme=theme)
        pie_df["metric_fmt"] = pie_df["gia_tri"].apply(fmt_vn)
        fig3_store = pack_fig_store(fig3, rows=_hr_pie_drill_rows(region_snapshot, prefix), meta={"chart": "pie", "metric_label": pie_title, "series_field": "label"})

        table_df = dff.copy().sort_values(["thang_nam_vn", "khu_vuc", "bo_phan"]).reset_index(drop=True)
        table_df["thang_nam"] = pd.to_datetime(table_df["thang_nam_vn"], errors="coerce").dt.strftime("%m/%Y").fillna("")
        table_df["net_flow"] = pd.to_numeric(table_df.get("so_vao_lam", 0), errors="coerce").fillna(0) - pd.to_numeric(table_df.get("so_nghi_viec", 0), errors="coerce").fillna(0)
        for col in ["so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan", "net_flow"]:
            if col in table_df.columns:
                table_df[col] = table_df[col].apply(fmt_vn)
        for col in ["ty_le_tang", "ty_le_giam", "ty_le_giu_chan"]:
            if col in table_df.columns:
                table_df[col] = table_df[col].apply(lambda x: fmt_pct(x, 1))
        keep_cols = [c for c in ["thang_nam", "khu_vuc", "bo_phan", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec", "net_flow", "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan", "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"] if c in table_df.columns]
        return kpi1, kpi2, kpi3, fig1, fig2, fig3, table_df[keep_cols].to_dict("records"), insight, style_cell, style_header, kpi1_store, kpi2_store, kpi3_store, fig1_store, fig2_store, fig3_store

for _prefix in [p for p in DASH_PREFIXES if p not in HR_MENU_PREFIXES]:
    callbacks(_prefix)
for _prefix in HR_MENU_PREFIXES:
    hr_callbacks(_prefix)

app.clientside_callback(
    """
    function(_clicks, allStoreData, homeMainFigure, homeRegionDonutFigure, homeRegionBarFigure, homeLhDonutFigure, homeHdBarFigure, dailyMainFigure, dailyRegionDonutFigure, dailyRegionBarFigure, dailyLhDonutFigure, dailyHdBarFigure) {
        const noUpdate = dash_clientside.no_update;
        const ctx = dash_clientside.callback_context || {};
        const trig = ctx.triggered_id;
        if (!trig || typeof trig !== "object" || trig.type !== "zoomable") {
            return [noUpdate, noUpdate];
        }
        const target = trig.target;
        const kind = trig.kind;
        if (!target) {
            return [noUpdate, noUpdate];
        }
        let nclick = 0;
        try {
            const tv = (ctx.triggered && ctx.triggered.length) ? ctx.triggered[0].value : null;
            nclick = parseInt(tv || 0, 10);
        } catch(e) { nclick = 0; }
        if (!nclick || nclick <= 0) {
            return [noUpdate, noUpdate];
        }

        const targetOrder = ZOOM_TARGETS_JS;
        let selectedStore = null;

        function flattenStates(items, out) {
            out = out || [];
            if (!items) { return out; }
            if (Array.isArray(items)) {
                items.forEach(function(x){ flattenStates(x, out); });
                return out;
            }
            if (items && typeof items === "object") { out.push(items); }
            return out;
        }

        try {
            const statesFlat = flattenStates(ctx.states_list || []);
            for (let i = 0; i < statesFlat.length; i++) {
                const item = statesFlat[i] || {};
                const id = item.id || {};
                if (id && id.type === "zoom-store" && id.target === target) {
                    selectedStore = item.value;
                    break;
                }
            }
        } catch(e) {}

        if (!selectedStore && Array.isArray(allStoreData)) {
            const idx = targetOrder.indexOf(target);
            if (idx >= 0 && idx < allStoreData.length) {
                selectedStore = allStoreData[idx];
            }
        }

        if (!selectedStore) {
            return [noUpdate, noUpdate];
        }

        // Home/Daily charts keep their figure out of hidden dcc.Store for fast page load.
        // When zoom is opened, reuse the visible dcc.Graph figure that is already in the browser.
        try {
            const graphFigureMap = {
                "home-main": homeMainFigure,
                "home-region-donut": homeRegionDonutFigure,
                "home-region-bar": homeRegionBarFigure,
                "home-lh-donut": homeLhDonutFigure,
                "home-hd-bar": homeHdBarFigure,
                "daily-main": dailyMainFigure,
                "daily-region-donut": dailyRegionDonutFigure,
                "daily-region-bar": dailyRegionBarFigure,
                "daily-lh-donut": dailyLhDonutFigure,
                "daily-hd-bar": dailyHdBarFigure
            };
            if (selectedStore && selectedStore.kind === "fig") {
                const figMissing = (!selectedStore.figure) ||
                    (typeof selectedStore.figure === "object" && Object.keys(selectedStore.figure).length === 0);
                if (figMissing && graphFigureMap[target]) {
                    selectedStore = Object.assign({}, selectedStore, {figure: graphFigureMap[target]});
                    selectedStore.meta = Object.assign({}, selectedStore.meta || {}, {
                        figure_included: true,
                        figure_lazy_from_graph: true
                    });
                }
            }
        } catch(e) {}

        return [{target: target, kind: kind, ts: Date.now(), n: nclick}, selectedStore];
    }
    """.replace("ZOOM_TARGETS_JS", json.dumps(ZOOM_TARGETS, ensure_ascii=False)),
    Output("zoom-open-request", "data"),
    Output("zoom-selected-store", "data"),
    Input({"type":"zoomable","kind":ALL,"target":ALL}, "n_clicks"),
    State({"type":"zoom-store","target":ALL}, "data"),
    State("home-main", "figure", allow_optional=True),
    State("home-region-donut", "figure", allow_optional=True),
    State("home-region-bar", "figure", allow_optional=True),
    State("home-lh-donut", "figure", allow_optional=True),
    State("home-hd-bar", "figure", allow_optional=True),
    State("daily-main", "figure", allow_optional=True),
    State("daily-region-donut", "figure", allow_optional=True),
    State("daily-region-bar", "figure", allow_optional=True),
    State("daily-lh-donut", "figure", allow_optional=True),
    State("daily-hd-bar", "figure", allow_optional=True),
    prevent_initial_call=True,
)


@app.callback(
    Output("zoom-modal", "is_open"),
    Output("zoom-title", "children"),
    Output("zoom-kpi-render", "children"),
    Output("zoom-graph", "figure"),
    Output("zoom-graph", "style"),
    Output("zoom-detail", "children"),
    Output("zoom-detail", "style"),
    Output("zoom-target", "data"),

    Input("zoom-open-request", "data"),
    Input("zoom-modal", "n_dismiss"),
    Input("zoom-graph", "clickData"),

    State("zoom-modal", "is_open"),
    State("zoom-target", "data"),
    State("zoom-selected-store", "data"),
    State("theme", "data"),
    prevent_initial_call=True
)
def zoom_all(zoom_request, n_dismiss, clickData, is_open, zoom_target, selected_store, theme):
    trig = ctx.triggered_id

    if trig == "zoom-modal":
        return False, no_update, no_update, no_update, _zoom_graph_hidden_style(), no_update, {"display":"none"}, None

    if trig == "zoom-graph":
        if not is_open or not zoom_target:
            raise PreventUpdate
        target = zoom_target.get("target")
        if not target:
            raise PreventUpdate

        store = selected_store or {}
        if not store or store.get("kind") != "fig":
            raise PreventUpdate

        detail_cache_key = _zoom_drill_cache_key(target, store, clickData, theme)
        cached_detail = _zoom_drill_cache_get(detail_cache_key)
        if cached_detail is not None:
            return cached_detail

        meta = store.get("meta", {}) or {}
        rows = store.get("rows", []) or []
        fig = store.get("figure", {}) or {}

        if not rows:
            detail = html.Div("Không có dữ liệu drill-down cho biểu đồ này.", style={"opacity":0.85})
            result = (True, no_update, no_update, no_update, no_update, detail, {"display":"block"}, zoom_target)
            return _zoom_drill_cache_set(detail_cache_key, result)

        pt = (clickData.get("points") or [{}])[0]
        df = pd.DataFrame(rows)
        df, subtitle = _zoom_filter_rows_for_point(df, meta, fig, pt)
        df = _zoom_prepare_detail_df(df, meta, pt)

        if df.empty:
            detail = html.Div("Không tìm thấy dòng dữ liệu phù hợp cho điểm bạn click.", style={"opacity":0.85})
            result = (True, no_update, no_update, no_update, no_update, detail, {"display":"block"}, zoom_target)
            return _zoom_drill_cache_set(detail_cache_key, result)

        metric_label = _zoom_metric_label(meta)
        detail = _zoom_detail_card(df, meta, theme, f"CHI TIẾT • {metric_label}", subtitle, dense=True)
        result = (True, no_update, no_update, no_update, no_update, detail, {"display":"block"}, zoom_target)
        return _zoom_drill_cache_set(detail_cache_key, result)

    if trig == "zoom-open-request":
        req = zoom_request or {}
        kind = req.get("kind")
        target = req.get("target")
        if not target:
            raise PreventUpdate

        store = selected_store or {}
        if not store:
            raise PreventUpdate

        open_cache_key = _zoom_open_cache_key(target, store, theme)
        cached_open = _zoom_open_cache_get(open_cache_key)
        if cached_open is not None:
            return cached_open

        title = f"PHÓNG TO • {target}"
        detail_children = []
        detail_style = {"display": "none"}

        if store.get("kind") == "kpi" or kind == "kpi":
            rows = store.get("rows", []) or []
            cols = []
            data = []
            df_zoom = pd.DataFrame(rows)

            if not df_zoom.empty and "pct" in df_zoom.columns and "pct_fmt" not in df_zoom.columns:
                df_zoom["pct_fmt"] = pd.to_numeric(df_zoom["pct"], errors="coerce").fillna(0).apply(lambda x: fmt_pct(x, 1))

            if not df_zoom.empty:
                kpi_meta = {"metric_label": store.get("title", "Giá trị")}
                df_zoom = _zoom_prepare_detail_df(df_zoom, kpi_meta)
                cols, data = _zoom_columns_data(df_zoom, kpi_meta, max_cols=12)

            z_style_header, z_style_cell, z_style_table, z_wrapper_style = _zoom_table_styles(theme, dense=False)
            if theme == "light":
                z_card_style = {"border": f"1.5px solid {GREEN_BORDER}", "boxShadow": f"0 8px 18px {GREEN_SHADOW}", "width": "100%", "maxWidth": "100%", "overflow": "hidden"}
            else:
                z_card_style = {"border":"1px solid #3b3b57","boxShadow":"0 0 20px rgba(90,80,255,0.15)", "width": "100%", "maxWidth": "100%", "overflow": "hidden"}

            kpi_card = dbc.Card(
                dbc.CardBody([
                    html.Div(store.get("title","KPI"), style={"fontSize":"14px","fontWeight":"900","opacity":0.85}),
                    html.Div(store.get("main","0"), style={"fontSize":"44px","fontWeight":"900","marginTop":"6px"}),
                    html.Div(store.get("subtitle",""), style={"fontSize":"13px","opacity":0.85,"fontWeight":"800","marginTop":"4px"}),
                    html.Hr(style={"borderColor":"#d0d7e2" if theme=="light" else "#444"}),
                    html.Div(
                        dash_table.DataTable(
                            columns=cols,
                            data=data,
                            page_size=12,
                            style_header=z_style_header,
                            style_cell=z_style_cell,
                            style_table=z_style_table,
                        ) if cols else html.Div("Không có breakdown theo khu vực.", style={"opacity":0.8}),
                        style=z_wrapper_style,
                    )
                ], style={"width": "100%", "maxWidth": "100%", "overflowX": "hidden"}),
                style=z_card_style
            )
            result = (True, title, kpi_card, no_update, _zoom_graph_hidden_style(), [], {"display":"none"}, {"kind":"kpi","target":target})
            return _zoom_open_cache_set(open_cache_key, result)

        fig_dict = store.get("figure", {}) or {}
        rows = store.get("rows", []) or []
        if not fig_dict:
            # Chart cards must never open directly as a table. Missing figures usually mean
            # an old env/deployment disabled figure storage; show a chart placeholder and
            # keep drill-down hidden until a real chart figure is available.
            fig_dict = empty_figure("Chưa có biểu đồ phóng to cho chart này. Hãy tải lại trang hoặc kiểm tra payload figure trên graph hiển thị.", theme).to_dict()
            fig_dict = enhance_zoom_figure(fig_dict)
            result = (True, title, None, fig_dict, _zoom_graph_visible_style(), [], {"display":"none"}, {"kind":"fig","target":target})
            return _zoom_open_cache_set(open_cache_key, result)

        fig_dict = enhance_zoom_figure(fig_dict)

        # First click on a chart only opens the enlarged chart. Drill-down table appears
        # only after the user clicks an actual point/bar/slice inside the zoomed chart.
        result = (True, title, None, fig_dict, _zoom_graph_visible_style(), [], {"display":"none"}, {"kind":"fig","target":target})
        return _zoom_open_cache_set(open_cache_key, result)

    raise PreventUpdate



TABLE_DETAIL_IDS = ["home-table", "daily-table"] + [f"{p}-table" for p in DASH_PREFIXES]


def _table_detail_title(table_id: str) -> str:
    if table_id == "home-table":
        return "HOME • BẢNG CHI TIẾT"
    if table_id == "daily-table":
        return "DOANH THU CẬP NHẬT THEO NGÀY"
    if table_id.endswith("-table"):
        prefix = table_id[:-6]
        if prefix in MENU_CONFIG:
            cfg = get_menu_config(prefix)
            return f"{cfg.get('menu_label', prefix).upper()} • DỮ LIỆU CHI TIẾT"
    return "CHI TIẾT DÒNG DỮ LIỆU"


def _stringify_table_value(value):
    try:
        if value is None:
            return ""
        if isinstance(value, float) and pd.isna(value):
            return ""
        if isinstance(value, (pd.Timestamp, datetime)):
            return pd.Timestamp(value).strftime("%d/%m/%Y %H:%M")
        return str(value)
    except Exception:
        return str(value)


def _render_table_row_detail(table_id: str, row: dict, columns: list | None, active_cell: dict | None = None):
    columns = columns or []
    if columns:
        ordered = []
        for c in columns:
            cid = c.get("id") if isinstance(c, dict) else None
            if cid in row:
                ordered.append((c.get("name", cid), cid))
        used = {cid for _, cid in ordered}
        for cid in row.keys():
            if cid not in used:
                ordered.append((cid, cid))
    else:
        ordered = [(k, k) for k in row.keys()]

    clicked_col = None
    if active_cell and isinstance(active_cell, dict):
        clicked_col = active_cell.get("column_id")
    subtitle = "Click dòng bất kỳ trong bảng để mở thẻ xem nhanh; dữ liệu hiển thị theo đúng dòng/cột đang chọn."
    if clicked_col:
        for name, cid in ordered:
            if cid == clicked_col:
                subtitle = f"Ô vừa chọn: {name}"
                break

    items = []
    for label, cid in ordered:
        val = _stringify_table_value(row.get(cid, ""))
        items.append(html.Div([
            html.Div(_zoom_vn_label(cid) if str(label) == str(cid) else str(label), className="table-row-detail-label"),
            html.Div(val, className="table-row-detail-value"),
        ], className="table-row-detail-item"))

    return html.Div([
        html.Div([
            html.Div(_table_detail_title(table_id), className="table-row-detail-title"),
            html.Div(subtitle, className="table-row-detail-subtitle"),
        ], className="table-row-detail-hero"),
        html.Div(items, className="table-row-detail-grid")
    ])


app.clientside_callback(
    """
    function(n_close) {
        const ids = TABLE_DETAIL_IDS_JS;
        const titleMap = TABLE_TITLE_MAP_JS;
        const labelMap = TABLE_LABEL_MAP_JS;
        const noUpdate = dash_clientside.no_update;
        const ctx = dash_clientside.callback_context || {};
        const trig = ctx.triggered_id;
        if (trig === "table-row-close") {
            return [false, noUpdate, noUpdate];
        }
        if (!trig || ids.indexOf(trig) === -1) {
            return [noUpdate, noUpdate, noUpdate];
        }

        const args = Array.prototype.slice.call(arguments, 1);
        const n = ids.length;
        const activeCells = args.slice(0, n);
        const viewportRows = args.slice(n, 2 * n);
        const rawRows = args.slice(2 * n, 3 * n);
        const columnsList = args.slice(3 * n, 4 * n);
        const idx = ids.indexOf(trig);
        const activeCell = activeCells[idx] || {};
        if (activeCell.row === undefined || activeCell.row === null) {
            return [noUpdate, noUpdate, noUpdate];
        }
        const rows = viewportRows[idx] || rawRows[idx] || [];
        if (!rows || !rows.length) {
            return [noUpdate, noUpdate, noUpdate];
        }
        const rowIndex = parseInt(activeCell.row || 0, 10);
        if (rowIndex < 0 || rowIndex >= rows.length) {
            return [noUpdate, noUpdate, noUpdate];
        }
        const row = rows[rowIndex] || {};
        const cols = columnsList[idx] || [];

        function comp(type, props, children) {
            const p = Object.assign({}, props || {});
            p.children = children;
            return {namespace: "dash_html_components", type: type, props: p};
        }
        function stringify(value) {
            if (value === null || value === undefined) { return ""; }
            return String(value);
        }
        function autoLabel(cid) {
            if (labelMap[cid]) { return labelMap[cid]; }
            return String(cid || "")
                .replace(/_fmt$/g, "")
                .replace(/_std$/g, "")
                .replace(/_/g, " ")
                .replace(/\\s+/g, " ")
                .trim()
                .replace(/^./, function(ch){ return ch.toUpperCase(); });
        }

        let ordered = [];
        let used = {};
        if (Array.isArray(cols) && cols.length) {
            cols.forEach(function(c) {
                const cid = c && c.id;
                if (cid !== undefined && cid !== null && Object.prototype.hasOwnProperty.call(row, cid)) {
                    let name = c.name || cid;
                    if (Array.isArray(name)) { name = name.join(" "); }
                    ordered.push([String(name), cid]);
                    used[cid] = true;
                }
            });
        }
        Object.keys(row).forEach(function(cid) {
            if (!used[cid]) { ordered.push([cid, cid]); }
        });

        const clickedCol = activeCell.column_id;
        let subtitle = "Click dòng bất kỳ trong bảng để mở thẻ xem nhanh; dữ liệu hiển thị theo đúng dòng/cột đang chọn.";
        if (clickedCol) {
            for (let i = 0; i < ordered.length; i++) {
                if (ordered[i][1] === clickedCol) {
                    subtitle = "Ô vừa chọn: " + autoLabel(ordered[i][1]);
                    break;
                }
            }
        }

        const items = ordered.map(function(pair) {
            const label = pair[0];
            const cid = pair[1];
            const displayLabel = (String(label) === String(cid)) ? autoLabel(cid) : String(label);
            return comp("Div", {className: "table-row-detail-item"}, [
                comp("Div", {className: "table-row-detail-label"}, displayLabel),
                comp("Div", {className: "table-row-detail-value"}, stringify(row[cid]))
            ]);
        });

        const title = titleMap[trig] || "CHI TIẾT DÒNG DỮ LIỆU";
        const body = comp("Div", {}, [
            comp("Div", {className: "table-row-detail-hero"}, [
                comp("Div", {className: "table-row-detail-title"}, title),
                comp("Div", {className: "table-row-detail-subtitle"}, subtitle)
            ]),
            comp("Div", {className: "table-row-detail-grid"}, items)
        ]);
        return [true, title, body];
    }
    """
      .replace("TABLE_DETAIL_IDS_JS", json.dumps(TABLE_DETAIL_IDS, ensure_ascii=False))
      .replace("TABLE_TITLE_MAP_JS", json.dumps({tid: _table_detail_title(tid) for tid in TABLE_DETAIL_IDS}, ensure_ascii=False))
      .replace("TABLE_LABEL_MAP_JS", json.dumps(ZOOM_DETAIL_COLUMN_LABELS, ensure_ascii=False)),
    Output("table-row-modal", "is_open"),
    Output("table-row-title", "children"),
    Output("table-row-body", "children"),
    Input("table-row-close", "n_clicks"),
    *[Input(tid, "active_cell", allow_optional=True) for tid in TABLE_DETAIL_IDS],
    *[State(tid, "derived_viewport_data", allow_optional=True) for tid in TABLE_DETAIL_IDS],
    *[State(tid, "data", allow_optional=True) for tid in TABLE_DETAIL_IDS],
    *[State(tid, "columns", allow_optional=True) for tid in TABLE_DETAIL_IDS],
    prevent_initial_call=True,
)


def strip_accents(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def norm_q(s: str) -> str:
    s = (s or "").strip().lower()
    s = strip_accents(s)
    s = re.sub(r"\s+", " ", s)
    return s

def detect_year(text: str):
    m = re.search(r"(19|20)\d{2}", text)
    return int(m.group()) if m else None

def detect_month_label(text: str):
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*/\s*((19|20)\d{2})\b", text)
    if m:
        mm = int(m.group(1))
        yy = int(m.group(2))
        return f"{mm:02d}/{yy}"
    m2 = re.search(r"\bthang\s*(0?[1-9]|1[0-2])\s*(nam)?\s*((19|20)\d{2})\b", norm_q(text))
    if m2:
        mm = int(m2.group(1))
        yy = int(m2.group(3))
        return f"{mm:02d}/{yy}"
    return None

def detect_month_number(text: str):
    t = norm_q(text)
    m = re.search(r"\bthang\s*(0?[1-9]|1[0-2])\b", t)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\bt\s*(0?[1-9]|1[0-2])\b", t)
    if m2:
        return int(m2.group(1))
    return None

def detect_top_n(text: str):
    m = re.search(r"\btop\s*(\d+)\b", norm_q(text))
    return int(m.group(1)) if m else None

def detect_bottom_n(text: str):
    m = re.search(r"\bbottom\s*(\d+)\b", norm_q(text))
    return int(m.group(1)) if m else None

def choose_dataset(question: str):
    q = norm_q(question)
    for prefix in DASH_PREFIXES:
        cfg = get_menu_config(prefix)
        if any(norm_q(k) in q for k in cfg.get("dataset_keywords", [])):
            ensure_menu_data_loaded(prefix)
            cfg = get_menu_config(prefix)
            return prefix, apply_region_scope_to_df(cfg["df"]), cfg["value_col"]
    if "hop dong" in q or "so cuoc" in q or "số cuốc" in question.lower():
        return "hd", apply_region_scope_to_df(df_hd), "tong_so_cuoc"
    if "loai hinh" in q or "loại hình" in question.lower():
        return "lh", apply_region_scope_to_df(df_lh), "tong_doanh_thu"
    return "dt", apply_region_scope_to_df(df_dt), "tong_doanh_thu"

def detect_metric_intent(question: str, value_col_default: str = "tong_doanh_thu"):
    q = norm_q(question)
    if any(k in q for k in ["thu duoc", "đã xử lý", "thu hoi", "thu hồi", "da thu", "đã thu"]):
        metric_col = "so_tien_thu_duoc"
    elif any(k in q for k in ["con no", "chênh lệch", "no dong", "nợ đọng", "chua thu", "chưa thu"]):
        metric_col = "so_tien_con_no"
    elif any(k in q for k in ["da xu ly", "đã xử lý", "hoan tat xu ly", "hoàn tất xử lý"]):
        metric_col = "so_tien_da_xu_ly"
    elif any(k in q for k in ["tong tien de xuat", "tổng tiền đề xuất", "de xuat", "đề xuất"]):
        metric_col = "tong_tien_de_xuat"
    else:
        primary_terms = ["doanh thu", "revenue", "chi phi", "chi phí", "gia tri", "giá trị", "diem tiep thi", "điểm tiếp thị"]
        secondary_terms = ["so cuoc", "số cuốc", "cuoc", "trip", "so nhan vien", "số nhân viên", "so tai xe", "số tài xế", "chien dich", "chiến dịch", "so bien ban", "số biên bản", "so xe", "số xe"]
        if any(k in q for k in primary_terms):
            metric_col = "tong_doanh_thu"
        elif any(k in q for k in secondary_terms):
            metric_col = "tong_so_cuoc"
        else:
            metric_col = value_col_default
    return {"metric_col": metric_col, "mode": "total"}

def extract_type_filter(question: str, key: str):
    q = norm_q(question)
    if key == "lh":
        hits = []
        for canon in LH_CANON + ["Khác"]:
            if norm_q(canon) in q:
                hits.append(canon)
        return hits or None
    if key == "hd":
        hits = []
        for canon in HD_CANON + ["Khác"]:
            if norm_q(canon) in q:
                hits.append(canon)
        return hits or None
    if key in {"xdt", "xpq"}:
        hits = []
        for opt in VEHICLE_TYPE_OPTIONS.get(key, []):
            val = str(opt.get("value"))
            if norm_q(val) in q:
                hits.append(val)
        return hits or None
    return None

def detect_regions_in_question(question: str, region_pool=None):
    q = norm_q(question)
    hits = []
    pool = region_pool if region_pool is not None else ALL_REGIONS
    for r in pool:
        rr = norm_q(r)
        if rr and rr in q:
            hits.append(r)
    if not hits:
        q2 = re.sub(r"[^a-z0-9\s]+", " ", q)
        q2 = re.sub(r"\s+", " ", q2).strip()
        for r in pool:
            rr = re.sub(r"[^a-z0-9\s]+", " ", norm_q(r))
            rr = re.sub(r"\s+", " ", rr).strip()
            if rr and rr in q2:
                hits.append(r)
    return list(dict.fromkeys(hits))

def detect_intent_advanced(question: str):
    q = norm_q(question)
    if any(k in q for k in ["cao nhat", "lon nhat", "nhieu nhat", "top "]):
        return "top"
    if any(k in q for k in ["thap nhat", "nho nhat", "it nhat", "bottom "]):
        return "bottom"
    if any(k in q for k in ["ty trong", "phan tram", "dong gop", "share", "contribution"]):
        return "share"
    if any(k in q for k in ["xu huong", "trend", "theo thang", "tang", "giam", "so sanh", "vs", "mom", "yoy"]):
        return "trend"
    return "total"

def _pct(a, total):
    return (a / total * 100.0) if total and total > 0 else 0.0

def answer_question(question: str, context: dict | None = None) -> str:
    context = context or {}
    q_raw = (question or "").strip()
    if not q_raw:
        return "Bạn hãy nhập câu hỏi (ví dụ: *Doanh thu T01/2025 khu vực Cà Mau?*)"
    qn = norm_q(q_raw)

    def _int(x, default=None):
        try:
            return int(x)
        except Exception:
            return default

    def _extract_years(text: str):
        yrs = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
        yrs = [y for y in yrs if 2000 <= y <= 2100]
        return list(dict.fromkeys(yrs))

    def _month_label(m: int, y: int):
        return f"{m:02d}/{y}"

    def _parse_month_label(lb: str):
        m = re.match(r"^\s*(\d{2})/(\d{4})\s*$", str(lb))
        if not m:
            return None
        mm = int(m.group(1))
        yy = int(m.group(2))
        try:
            return pd.Timestamp(year=yy, month=mm, day=1)
        except Exception:
            return None

    def _extract_month_pairs(text: str):
        pairs = []
        patterns = [
            r"(?:\b|t)(0?[1-9]|1[0-2])\s*[\/\-]\s*(20\d{2})\b",
            r"\bthang\s*(0?[1-9]|1[0-2])\s*(?:nam\s*)?(20\d{2})\b",
        ]
        for pat in patterns:
            for m, y in re.findall(pat, text, flags=re.I):
                mm, yy = _int(m), _int(y)
                if mm and yy and 1 <= mm <= 12:
                    pairs.append((mm, yy))
        return list(dict.fromkeys(pairs))

    def _extract_quarters(text: str):
        out = []
        patterns = [
            r"\bquy\s*([1-4])\s*(?:nam\s*)?(20\d{2})\b",
            r"\bq\s*([1-4])\s*[\/\-\s]?\s*(20\d{2})\b",
        ]
        for pat in patterns:
            for qv, yv in re.findall(pat, text, flags=re.I):
                qq, yy = _int(qv), _int(yv)
                if qq and yy:
                    out.append((qq, yy))
        return list(dict.fromkeys(out))

    def _extract_halfyears(text: str):
        out = []
        for half_word, half_id in [("dau", 1), ("cuoi", 2)]:
            pat = rf"\b(?:6|sau)\s*thang\s*{half_word}\s*(?:nam\s*)?(20\d{{2}})\b"
            for y in re.findall(pat, text, flags=re.I):
                yy = _int(y)
                if yy:
                    out.append((half_id, yy))
        for half_word, half_id in [("dau", 1), ("cuoi", 2)]:
            pat = rf"\bnua\s*{half_word}\s*(?:nam\s*)?(20\d{{2}})\b"
            for y in re.findall(pat, text, flags=re.I):
                yy = _int(y)
                if yy:
                    out.append((half_id, yy))
        for h, y in re.findall(r"\bh\s*([12])\s*[\/\-\s]?\s*(20\d{2})\b", text, flags=re.I):
            hh, yy = _int(h), _int(y)
            if hh and yy:
                out.append((hh, yy))
        return list(dict.fromkeys(out))

    def _quarter_months(qv: int, yv: int):
        mlist = {1: [1,2,3], 2: [4,5,6], 3: [7,8,9], 4: [10,11,12]}.get(qv, [])
        return [_month_label(m, yv) for m in mlist]

    def _halfyear_months(hv: int, yv: int):
        mlist = [1,2,3,4,5,6] if hv == 1 else [7,8,9,10,11,12]
        return [_month_label(m, yv) for m in mlist]

    def _month_range_labels(m1, y1, m2, y2):
        try:
            start = pd.Timestamp(year=y1, month=m1, day=1)
            end = pd.Timestamp(year=y2, month=m2, day=1)
            if end < start:
                start, end = end, start
            rng = pd.date_range(start, end, freq="MS")
            return [_month_label(int(d.month), int(d.year)) for d in rng]
        except Exception:
            return []

    def _shift_month_labels_by_year(labels, year_delta=-1):
        out = []
        for lb in (labels or []):
            ts = _parse_month_label(lb)
            if ts is None:
                continue
            out.append(_month_label(int(ts.month), int(ts.year + year_delta)))
        return out

    def _prev_month_label(lb: str):
        ts = _parse_month_label(lb)
        if ts is None:
            return None
        prev = ts - pd.offsets.MonthBegin(1)
        return _month_label(int(prev.month), int(prev.year))

    def _choose_dataset_with_context(q_norm: str):
        explicit = False
        for _prefix in DASH_PREFIXES:
            _cfg = get_menu_config(_prefix)
            if any(norm_q(k) in q_norm for k in _cfg.get("dataset_keywords", [])):
                explicit = True
                break
        if explicit:
            ds_key0, dfx0, _ = choose_dataset(q_norm)
            return ds_key0, dfx0
        default_menu = context.get("menu")
        if default_menu in DASH_PREFIXES:
            ensure_menu_data_loaded(default_menu)
            cfg_menu = get_menu_config(default_menu)
            return default_menu, apply_region_scope_to_df(cfg_menu["df"])
        if default_menu == "home":
            return "dt", apply_region_scope_to_df(df_dt)
        ds_key0, dfx0, _ = choose_dataset(q_norm)
        return ds_key0, dfx0

    def _pick_type_value(df_: pd.DataFrame, col: str, q_norm: str):
        if not col or col not in df_.columns:
            return None
        vals = [v for v in df_[col].dropna().astype(str).unique().tolist() if str(v).strip()]
        if not vals:
            return None
        q2 = re.sub(r"[^a-z0-9\s]+", " ", q_norm)
        q2 = re.sub(r"\s+", " ", q2).strip()
        best = None
        best_len = 0
        for v in vals:
            vn = norm_q(v)
            vn2 = re.sub(r"[^a-z0-9\s]+", " ", vn)
            vn2 = re.sub(r"\s+", " ", vn2).strip()
            if vn2 and vn2 in q2 and len(vn2) > best_len:
                best = v
                best_len = len(vn2)
        return best

    def _fmt_value(v):
        return fmt_vn(v)

    def _group_by_month(df_, metric_col, date_col, month_col):
        if date_col in df_.columns:
            try:
                s = df_.groupby(date_col)[metric_col].sum().sort_index()
                return s, "date"
            except Exception:
                pass
        if month_col in df_.columns:
            s = df_.groupby(month_col)[metric_col].sum()
            try:
                idx_order = sorted(
                    s.index,
                    key=lambda x: pd.to_datetime(f"01/{x}", format="%d/%m/%Y", errors="coerce")
                )
                s = s.reindex(idx_order)
            except Exception:
                pass
            return s, "label"
        return pd.Series(dtype=float), "none"

    def _latest_months_from_df(df_, metric_col, date_col, month_col):
        s, kind_s = _group_by_month(df_, metric_col, date_col, month_col)
        if len(s) == 0:
            return None, None, kind_s
        last_key = s.index[-1]
        if kind_s == "date":
            try:
                ts = pd.Timestamp(last_key)
                return _month_label(int(ts.month), int(ts.year)), last_key, kind_s
            except Exception:
                return None, last_key, kind_s
        return str(last_key), last_key, kind_s

    def _compare_text(cur_val, prev_val, cur_desc, prev_desc, ask_pct_first=False):
        diff = cur_val - prev_val
        pctv = (diff / prev_val * 100.0) if prev_val else None
        direction = "tăng" if diff > 0 else "giảm" if diff < 0 else "không đổi"
        lines = [
            f"**{cur_desc}:** {_fmt_value(cur_val)}",
            f"**{prev_desc}:** {_fmt_value(prev_val)}",
        ]
        if pctv is not None:
            if ask_pct_first:
                lines.append(f"**Biến động (%):** {pctv:+.1f}% ({direction})")
                lines.append(f"**Chênh lệch tuyệt đối:** {_fmt_value(diff)}")
            else:
                lines.append(f"**Chênh lệch:** {_fmt_value(diff)} ({pctv:+.1f}%)")
        else:
            lines.append(f"**Chênh lệch:** {_fmt_value(diff)}")
        return "\n".join(lines)

    ds_key, df = _choose_dataset_with_context(qn)
    REV_COL = "tong_doanh_thu"
    TRIP_COL = "tong_so_cuoc"
    MONTH_COL = "thang_label"
    DATE_COL = "thang_nam"
    YEAR_COL = "nam"
    REGION_COL = "khu_vuc"

    cfg_ds = get_menu_config(ds_key) if ds_key in MENU_CONFIG else {}
    default_metric_col = cfg_ds.get("value_col", TRIP_COL if ds_key == "hd" else REV_COL)
    metric_info = detect_metric_intent(q_raw, value_col_default=default_metric_col)
    metric = metric_info.get("metric_col", default_metric_col) if isinstance(metric_info, dict) else metric_info

    if metric not in df.columns:
        if default_metric_col in df.columns:
            metric = default_metric_col
        elif REV_COL in df.columns:
            metric = REV_COL
        else:
            metric = TRIP_COL

    if metric == cfg_ds.get("value_col"):
        metric_name = cfg_ds.get("metric_label", "Doanh thu" if metric == REV_COL else "Số cuốc")
    elif metric == cfg_ds.get("secondary_col"):
        metric_name = cfg_ds.get("secondary_label", "Số cuốc")
    else:
        metric_name = "Doanh thu" if metric == REV_COL else "Số cuốc"

    ctx_filters = context.get("filters") or {}
    ctx_year = ctx_filters.get("year") or ctx_filters.get("year_p2")
    if _is_fleet_menu(ds_key):
        ctx_year = None
    ctx_months = ctx_filters.get("months") or ctx_filters.get("months_p2")
    ctx_regions = ctx_filters.get("dim") or ctx_filters.get("dims")
    if isinstance(ctx_regions, str):
        ctx_regions = [ctx_regions]

    same_period_flag = any(k in qn for k in [
        "cung ky", "so voi cung ky", "so sanh cung ky", "cung ky nam truoc"
    ])
    mom_flag = any(k in qn for k in [
        " mom", "mom ", " month over month", "so voi thang truoc", "so sanh voi thang truoc", "mo m"
    ]) or ("mom" in qn)
    yoy_flag = any(k in qn for k in [
        " yoy", "yoy ", " year over year", "so voi cung ky", "so sanh cung ky", "cung ky nam truoc"
    ]) or ("yoy" in qn)
    ask_pct_first = any(k in qn for k in [
        "bao nhieu %", "bao nhieu phan tram", "bao nhiêu %", "bao nhiêu phần trăm", "phan tram", "%"
    ])

    latest_month_flag = any(k in qn for k in [
        "thang gan nhat", "thang moi nhat", "thang recent", "gan day nhat", "moi nhat"
    ])
    prev_month_flag = any(k in qn for k in [
        "thang lien truoc", "thang liền trước", "thang truoc", "tháng trước"
    ]) and not mom_flag

    years = _extract_years(qn)
    month_pairs = _extract_month_pairs(qn)
    quarter_pairs = _extract_quarters(qn)
    halfyear_pairs = _extract_halfyears(qn)

    range_labels = []
    mrange = re.search(
        r"(?:tu|từ)\s*(0?[1-9]|1[0-2])\s*[\/\-]\s*(20\d{2})\s*(?:den|đến)\s*(0?[1-9]|1[0-2])\s*[\/\-]\s*(20\d{2})",
        qn
    )
    if mrange:
        m1, y1, m2, y2 = map(int, mrange.groups())
        range_labels = _month_range_labels(m1, y1, m2, y2)

    months_labels = []
    time_scope_desc = None

    if range_labels:
        months_labels = range_labels
        if len(months_labels) >= 2:
            time_scope_desc = f"Từ {months_labels[0]} đến {months_labels[-1]}"
    elif month_pairs:
        months_labels = [_month_label(m, y) for m, y in month_pairs]
    elif quarter_pairs:
        tmp = []
        q_descs = []
        for qv, yv in quarter_pairs:
            tmp.extend(_quarter_months(qv, yv))
            q_descs.append(f"Q{qv}/{yv}")
        months_labels = list(dict.fromkeys(tmp))
        time_scope_desc = ", ".join(q_descs)
        if not years:
            years = list(dict.fromkeys([yv for _, yv in quarter_pairs]))
    elif halfyear_pairs:
        tmp = []
        h_descs = []
        for hv, yv in halfyear_pairs:
            tmp.extend(_halfyear_months(hv, yv))
            h_descs.append(f"H{hv}/{yv}")
        months_labels = list(dict.fromkeys(tmp))
        time_scope_desc = ", ".join(h_descs)
        if not years:
            years = list(dict.fromkeys([yv for _, yv in halfyear_pairs]))
    else:
        ml = detect_month_label(q_raw)
        if ml:
            months_labels = [ml]

    requested_regions = detect_regions_in_question(q_raw, region_pool=ALL_REGIONS)
    blocked_regions = [r for r in requested_regions if not user_can_access_region(r)]
    if blocked_regions:
        return "Tài khoản của bạn không có quyền xem dữ liệu của khu vực: " + ", ".join(blocked_regions) + ". Vui lòng dùng tài khoản tổng hoặc tài khoản đã được cấp đúng khu vực."
    regions = filter_regions_for_current_user(requested_regions)

    if not years and ctx_year is not None:
        years = [ctx_year] if isinstance(ctx_year, int) else [int(ctx_year)] if str(ctx_year).isdigit() else []
    if not months_labels and ctx_months:
        months_labels = ctx_months[:] if isinstance(ctx_months, list) else [ctx_months]
    if not regions and ctx_regions:
        regions = filter_regions_for_current_user(ctx_regions[:] if isinstance(ctx_regions, list) else [ctx_regions])

    type_col = LH_COL if ds_key == "lh" else HD_COL if ds_key == "hd" else None
    type_value = _pick_type_value(df, type_col, qn) if type_col else None
    if not type_value and type_col:
        tv = ctx_filters.get("type_filter")
        if isinstance(tv, list) and len(tv) == 1:
            type_value = tv[0]
        elif isinstance(tv, str) and tv.strip():
            type_value = tv
        elif ctx_filters.get("type"):
            type_value = ctx_filters.get("type")

    dff_scope = apply_region_scope_to_df(df)
    dff_scope = _apply_real_data_cutoff(dff_scope)
    if YEAR_COL in dff_scope.columns and years:
        dff_scope = dff_scope[dff_scope[YEAR_COL].isin(years)]
    if REGION_COL in dff_scope.columns and regions:
        dff_scope = dff_scope[dff_scope[REGION_COL].isin(regions)]
    if type_col and type_value and type_col in dff_scope.columns:
        dff_scope = dff_scope[dff_scope[type_col] == type_value]

    if not months_labels and (latest_month_flag or prev_month_flag):
        latest_lb, _, _ = _latest_months_from_df(dff_scope, metric, DATE_COL, MONTH_COL)
        if latest_lb:
            if latest_month_flag:
                months_labels = [latest_lb]
                time_scope_desc = f"Tháng gần nhất ({latest_lb})"
            elif prev_month_flag:
                prev_lb = _prev_month_label(latest_lb)
                if prev_lb:
                    months_labels = [prev_lb]
                    time_scope_desc = f"Tháng liền trước ({prev_lb})"

    dff = dff_scope.copy()
    if MONTH_COL in dff.columns and months_labels:
        dff = dff[dff[MONTH_COL].isin(months_labels)]

    if dff.empty:
        scope = []
        if time_scope_desc:
            scope.append(f"giai đoạn {time_scope_desc}")
        if years:
            scope.append(f"năm {', '.join(map(str, years))}")
        if months_labels:
            scope.append(f"tháng {', '.join(months_labels)}")
        if regions:
            scope.append(f"khu vực {', '.join(regions)}")
        if type_value:
            scope.append(f"{type_col} = {type_value}")
        s = ", ".join(scope) if scope else "điều kiện câu hỏi"
        return f"Không tìm thấy dữ liệu phù hợp với {s}. Bạn thử đổi năm/tháng/khu vực hoặc bỏ bớt điều kiện nhé."

    intent = detect_intent_advanced(q_raw)

    parts = []
    ds_name = get_menu_config(ds_key).get("menu_label", ds_key.upper()) if ds_key in MENU_CONFIG else ds_key.upper()
    parts.append(f"**Dataset:** {ds_name} • **Chỉ tiêu:** {metric_name}")

    f_desc = []
    if time_scope_desc:
        f_desc.append(f"Giai đoạn: {time_scope_desc}")
    if years:
        f_desc.append(f"Năm: {', '.join(map(str, years))}")
    if months_labels:
        if len(months_labels) <= 6:
            f_desc.append(f"Tháng: {', '.join(months_labels)}")
        else:
            f_desc.append(f"Tháng: {len(months_labels)} tháng")
    if regions:
        f_desc.append(f"Khu vực: {', '.join(regions)}")
    if type_value:
        f_desc.append(f"{type_col}: {type_value}")
    if f_desc:
        parts.append("**Bộ lọc:** " + " | ".join(f_desc))

    if len(months_labels) == 1 and (mom_flag or yoy_flag):
        cur_month = str(months_labels[0])
        comp_month = None
        comp_desc = None

        if mom_flag:
            comp_month = _prev_month_label(cur_month)
            comp_desc = f"Tháng trước ({comp_month})" if comp_month else "Tháng trước"
        elif yoy_flag:
            shifted = _shift_month_labels_by_year([cur_month], -1)
            comp_month = shifted[0] if shifted else None
            comp_desc = f"Cùng kỳ năm trước ({comp_month})" if comp_month else "Cùng kỳ năm trước"

        cur_val = float(dff[metric].sum()) if metric in dff.columns else 0.0
        prev_df = dff_scope.copy()
        if comp_month and MONTH_COL in prev_df.columns:
            prev_df = prev_df[prev_df[MONTH_COL].astype(str) == str(comp_month)]
        else:
            prev_df = prev_df.iloc[0:0]

        prev_val = float(prev_df[metric].sum()) if (not prev_df.empty and metric in prev_df.columns) else 0.0
        cur_desc = f"Hiện tại ({cur_month})"

        if mom_flag and yoy_flag:
            prev_m = _prev_month_label(cur_month)
            prev_y = _shift_month_labels_by_year([cur_month], -1)
            prev_y = prev_y[0] if prev_y else None

            prev_df_m = dff_scope.copy()
            if prev_m and MONTH_COL in prev_df_m.columns:
                prev_df_m = prev_df_m[prev_df_m[MONTH_COL].astype(str) == str(prev_m)]
            else:
                prev_df_m = prev_df_m.iloc[0:0]

            prev_df_y = dff_scope.copy()
            if prev_y and MONTH_COL in prev_df_y.columns:
                prev_df_y = prev_df_y[prev_df_y[MONTH_COL].astype(str) == str(prev_y)]
            else:
                prev_df_y = prev_df_y.iloc[0:0]

            prev_val_m = float(prev_df_m[metric].sum()) if (not prev_df_m.empty and metric in prev_df_m.columns) else 0.0
            prev_val_y = float(prev_df_y[metric].sum()) if (not prev_df_y.empty and metric in prev_df_y.columns) else 0.0

            block = []
            block.append(_compare_text(cur_val, prev_val_m, cur_desc, f"Tháng trước ({prev_m})", ask_pct_first))
            block.append(_compare_text(cur_val, prev_val_y, cur_desc, f"Cùng kỳ năm trước ({prev_y})", ask_pct_first))
            parts.append("**So sánh MoM & YoY:**\n" + "\n\n".join(block))
            return "\n\n".join(parts)

        parts.append(_compare_text(cur_val, prev_val, cur_desc, comp_desc or "Kỳ so sánh", ask_pct_first))
        return "\n\n".join(parts)

    if same_period_flag:
        prev_df = df.copy()
        prev_years = []
        prev_months = []

        if months_labels:
            prev_months = _shift_month_labels_by_year(months_labels, -1)
            prev_years = sorted(list(dict.fromkeys([int(m.split("/")[1]) for m in prev_months if "/" in m])))
        elif years:
            prev_years = [int(y) - 1 for y in years]
        else:
            if ctx_year is not None:
                try:
                    prev_years = [int(ctx_year) - 1]
                except Exception:
                    prev_years = []

        if YEAR_COL in prev_df.columns and prev_years:
            prev_df = prev_df[prev_df[YEAR_COL].isin(prev_years)]
        if MONTH_COL in prev_df.columns and prev_months:
            prev_df = prev_df[prev_df[MONTH_COL].isin(prev_months)]
        if REGION_COL in prev_df.columns and regions:
            prev_df = prev_df[prev_df[REGION_COL].isin(regions)]
        if type_col and type_value and type_col in prev_df.columns:
            prev_df = prev_df[prev_df[type_col] == type_value]

        cur_val = float(dff[metric].sum()) if metric in dff.columns else 0.0
        prev_val = float(prev_df[metric].sum()) if (not prev_df.empty and metric in prev_df.columns) else 0.0

        cur_period_desc = ""
        prev_period_desc = ""
        if months_labels:
            cur_period_desc = ", ".join(months_labels) if len(months_labels) <= 6 else f"{len(months_labels)} tháng"
            prev_period_desc = ", ".join(prev_months) if len(prev_months) <= 6 else f"{len(prev_months)} tháng (năm trước)"
        elif years:
            cur_period_desc = ", ".join(map(str, years))
            prev_period_desc = ", ".join(map(str, prev_years))

        parts.append(_compare_text(
            cur_val, prev_val,
            f"Kỳ hiện tại ({cur_period_desc or 'hiện tại'})",
            f"Cùng kỳ năm trước ({prev_period_desc or 'năm trước'})",
            ask_pct_first=ask_pct_first
        ))

        if months_labels and MONTH_COL in dff.columns:
            g_cur = dff.groupby(MONTH_COL)[metric].sum()
            g_prev = prev_df.groupby(MONTH_COL)[metric].sum() if (not prev_df.empty and MONTH_COL in prev_df.columns) else pd.Series(dtype=float)
            compare_rows = []
            for cur_m in months_labels:
                ts = _parse_month_label(cur_m)
                if ts is None:
                    continue
                prev_m = _month_label(int(ts.month), int(ts.year - 1))
                v_cur = float(g_cur.get(cur_m, 0.0))
                v_prev = float(g_prev.get(prev_m, 0.0))
                dlt = v_cur - v_prev
                pctv = (dlt / v_prev * 100.0) if v_prev else None
                if pctv is None:
                    compare_rows.append(f"- {cur_m} vs {prev_m}: {_fmt_value(dlt)}")
                else:
                    compare_rows.append(f"- {cur_m} vs {prev_m}: {_fmt_value(dlt)} ({pctv:+.1f}%)")
            if compare_rows:
                parts.append("**Chi tiết theo tháng:**\n" + "\n".join(compare_rows[:12]))

        return "\n\n".join(parts)

    if any(k in qn for k in ["trung binh", "tb", "avg", "average"]):
        if REV_COL in dff.columns and TRIP_COL in dff.columns and any(k in qn for k in ["moi cuoc", "mỗi cuốc", "/cuoc", "per trip", "1 cuoc"]):
            rev = float(dff[REV_COL].sum())
            trips = float(dff[TRIP_COL].sum())
            val = rev / trips if trips else 0.0
            parts.append(f"**Doanh thu TB / cuốc:** {_fmt_value(val)}")
            return "\n\n".join(parts)

        s_m, _ = _group_by_month(dff, metric, DATE_COL, MONTH_COL)
        if len(s_m) > 0:
            val = float(s_m.mean())
            parts.append(f"**Trung bình theo tháng:** {_fmt_value(val)} (trên {len(s_m)} tháng)")
            return "\n\n".join(parts)

    if any(k in qn for k in ["so sanh", "so voi", "vs", "versus", "khac nhau", "chenh"]):
        if MONTH_COL in dff.columns and REGION_COL in dff.columns and len(regions) >= 2 and len(months_labels) >= 2:
            regions_req = list(dict.fromkeys(regions))
            months_req = list(dict.fromkeys(months_labels))
            gcmp = dff.groupby([MONTH_COL, REGION_COL], as_index=False)[metric].sum()

            def _val_of(month_label, region_name):
                x = gcmp[
                    (gcmp[MONTH_COL].astype(str) == str(month_label)) &
                    (gcmp[REGION_COL].astype(str) == str(region_name))
                ]
                if x.empty:
                    return 0.0
                return float(x[metric].sum())

            lines = ["**So sánh theo tháng & khu vực:**"]
            for ml in months_req:
                lines.append(f"- **{ml}**")
                for rg in regions_req:
                    v = _val_of(ml, rg)
                    lines.append(f"  - {rg}: {_fmt_value(v)}")

            if len(regions_req) >= 2:
                r1, r2 = regions_req[0], regions_req[1]
                lines.append("**Chênh lệch từng tháng:**")
                for ml in months_req:
                    v1 = _val_of(ml, r1)
                    v2 = _val_of(ml, r2)
                    diff = v1 - v2
                    if diff > 0:
                        lead = r1
                    elif diff < 0:
                        lead = r2
                    else:
                        lead = None

                    if lead is None:
                        lines.append(f"- {ml}: bằng nhau ({_fmt_value(v1)})")
                    else:
                        lines.append(f"- {ml}: {lead} cao hơn {_fmt_value(abs(diff))}")

            if len(months_req) >= 2:
                m_first, m_last = months_req[0], months_req[-1]
                lines.append(f"**Biến động từ {m_first} đến {m_last}:**")
                for rg in regions_req:
                    v_first = _val_of(m_first, rg)
                    v_last = _val_of(m_last, rg)
                    delta = v_last - v_first
                    pctv = (delta / v_first * 100.0) if v_first else None
                    if pctv is None:
                        lines.append(f"- {rg}: {_fmt_value(delta)}")
                    else:
                        lines.append(f"- {rg}: {_fmt_value(delta)} ({pctv:+.1f}%)")

            parts.append("\n".join(lines))
            return "\n\n".join(parts)

        yrs_in_q = _extract_years(qn)
        if YEAR_COL in dff.columns and len(yrs_in_q) >= 2:
            yrs = yrs_in_q[:3]
            tmp = df.copy()
            tmp = tmp[tmp[YEAR_COL].isin(yrs)]
            if months_labels and MONTH_COL in tmp.columns:
                tmp = tmp[tmp[MONTH_COL].isin(months_labels)]
            if regions and REGION_COL in tmp.columns:
                tmp = tmp[tmp[REGION_COL].isin(regions)]
            if type_col and type_value and type_col in tmp.columns:
                tmp = tmp[tmp[type_col] == type_value]

            s = tmp.groupby(YEAR_COL)[metric].sum().sort_index()
            if len(s) >= 2:
                lines = [f"- {y}: {_fmt_value(v)}" for y, v in s.items()]
                y0, y1 = s.index[0], s.index[1]
                v0, v1 = float(s.iloc[0]), float(s.iloc[1])
                diff = v1 - v0
                pctv = (diff / v0 * 100.0) if v0 else None
                parts.append("**So sánh theo năm:**\n" + "\n".join(lines))
                if pctv is not None:
                    parts.append(f"**Chênh lệch {y1} so với {y0}:** {_fmt_value(diff)} ({pctv:+.1f}%)")
                else:
                    parts.append(f"**Chênh lệch {y1} so với {y0}:** {_fmt_value(diff)}")
                return "\n\n".join(parts)

        if REGION_COL in dff.columns and len(regions) >= 2:
            s = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=False)
            lines = [f"- {r}: {_fmt_value(s.loc[r])}" for r in regions if r in s.index]
            parts.append("**So sánh theo khu vực:**\n" + ("\n".join(lines) if lines else "- Không đủ dữ liệu"))

            if len(lines) >= 2:
                r0, r1 = regions[0], regions[1]
                v0 = float(s.loc[r0]) if r0 in s.index else 0.0
                v1 = float(s.loc[r1]) if r1 in s.index else 0.0
                diff = v0 - v1
                pctv = (diff / v1 * 100.0) if v1 else None
                if pctv is not None:
                    parts.append(f"**Chênh lệch {r0} so với {r1}:** {_fmt_value(diff)} ({pctv:+.1f}%)")
                else:
                    parts.append(f"**Chênh lệch {r0} so với {r1}:** {_fmt_value(diff)}")
            return "\n\n".join(parts)

    if intent in ("top", "bottom"):
        n = 5
        mtop = re.search(r"\btop\s*(\d{1,2})\b", qn)
        mbot = re.search(r"\bbottom\s*(\d{1,2})\b", qn)

        if mtop:
            n = max(1, min(20, int(mtop.group(1))))
        elif mbot:
            n = max(1, min(20, int(mbot.group(1))))
        else:
            if ("nao" in qn or "khu vuc nao" in qn or "thang nao" in qn):
                n = 1

        ascending = (intent == "bottom")
        month_ranking_hint = ("thang nao" in qn) or (("thang" in qn) and (mtop or mbot))
        if month_ranking_hint and (DATE_COL in dff.columns or MONTH_COL in dff.columns):
            g_m, kind_m = _group_by_month(dff, metric, DATE_COL, MONTH_COL)
            g_m = g_m.sort_values(ascending=ascending).head(n)

            def _to_month_label_from_key(x):
                if kind_m == "date":
                    try:
                        ts = pd.Timestamp(x)
                        return _month_label(int(ts.month), int(ts.year))
                    except Exception:
                        return str(x)
                return str(x)

            if len(g_m) > 0:
                if n == 1:
                    month_key = g_m.index[0]
                    month_lbl = _to_month_label_from_key(month_key)
                    month_val = float(g_m.iloc[0])
                    rank_label = "cao nhất" if not ascending else "thấp nhất"
                    parts.append(f"**Tháng có {metric_name.lower()} {rank_label}:** {month_lbl} ({_fmt_value(month_val)})")
                    return "\n\n".join(parts)
                else:
                    title = "Top" if not ascending else "Bottom"
                    lines = [f"- {_to_month_label_from_key(idx)}: {_fmt_value(val)}" for idx, val in g_m.items()]
                    parts.append(f"**{title} {n} tháng theo {metric_name}:**\n" + "\n".join(lines))
                    return "\n\n".join(parts)

        if REGION_COL in dff.columns:
            g = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=ascending).head(n)
            if n == 1 and len(g) > 0:
                top_region = str(g.index[0])
                top_value = float(g.iloc[0])
                label_rank = "cao nhất" if not ascending else "thấp nhất"
                parts.append(f"**Khu vực có {metric_name.lower()} {label_rank}:** {top_region} ({_fmt_value(top_value)})")
                return "\n\n".join(parts)
            title = "Top" if not ascending else "Bottom"
            lines = [f"- {idx}: {_fmt_value(val)}" for idx, val in g.items()]
            parts.append(f"**{title} {n} khu vực theo {metric_name}:**\n" + "\n".join(lines))
            return "\n\n".join(parts)

        total = float(dff[metric].sum())
        parts.append(f"**{metric_name}:** {_fmt_value(total)}")
        return "\n\n".join(parts)

    if intent == "share":
        if REGION_COL in dff.columns:
            g = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=False)
            total = float(g.sum())
            lines = []
            for idx, val in g.head(8).items():
                pctv = (float(val) / total * 100.0) if total else 0.0
                lines.append(f"- {idx}: {_fmt_value(val)} ({pctv:.1f}%)")
            parts.append("**Tỷ trọng theo khu vực:**\n" + "\n".join(lines))
            return "\n\n".join(parts)
        total = float(dff[metric].sum())
        parts.append(f"**Tổng {metric_name}:** {_fmt_value(total)}")
        return "\n\n".join(parts)

    if intent == "trend":
        s, kind_s = _group_by_month(dff, metric, DATE_COL, MONTH_COL)
        if len(s) > 0:
            lines = []
            show = s if len(s) <= 12 else pd.concat([s.head(6), s.tail(6)])
            for d, v in show.items():
                if kind_s == "date":
                    try:
                        ts = pd.Timestamp(d)
                        lab = _month_label(int(ts.month), int(ts.year))
                    except Exception:
                        lab = str(d)
                else:
                    lab = str(d)
                lines.append(f"- {lab}: {_fmt_value(v)}")

            parts.append("**Xu hướng theo tháng:**\n" + "\n".join(lines))

            if len(s) >= 2:
                last, prev = float(s.iloc[-1]), float(s.iloc[-2])
                diff = last - prev
                pctv = (diff / prev * 100.0) if prev else None
                if pctv is not None:
                    if ask_pct_first:
                        parts.append(f"**Biến động tháng gần nhất (%):** {pctv:+.1f}%")
                        parts.append(f"**Chênh lệch tuyệt đối:** {_fmt_value(diff)}")
                    else:
                        parts.append(f"**Tháng gần nhất so với tháng trước:** {_fmt_value(diff)} ({pctv:+.1f}%)")
                else:
                    parts.append(f"**Tháng gần nhất so với tháng trước:** {_fmt_value(diff)}")
            return "\n\n".join(parts)

    total = float(dff[metric].sum())
    parts.append(f"**Tổng {metric_name}:** {_fmt_value(total)}")

    if REGION_COL in dff.columns and not detect_regions_in_question(q_raw):
        g = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=False).head(5)
        lines = [f"- {idx}: {_fmt_value(val)}" for idx, val in g.items()]
        parts.append("**Top 5 khu vực (tham khảo):**\n" + "\n".join(lines))

    parts.append(
        '\n*Gợi ý:* Bạn có thể hỏi: **"Cà Mau tháng nào cao nhất"**, '
        '**"Top 3 tháng doanh thu cao nhất của Cà Mau năm 2025"**, '
        '**"Doanh thu tháng gần nhất so với tháng liền trước (MoM)"**, '
        '**"Doanh thu tháng gần nhất so với cùng kỳ năm trước (YoY)"**, '
        '**"Doanh thu quý 1/2025"**, **"Doanh thu 6 tháng đầu năm 2025"**, '
        '**"Doanh thu quý 1/2025 so với cùng kỳ năm trước"**, '
        '**"So sánh doanh thu của Rạch Giá và An Giang trong tháng 1 2025 và tháng 10 2025"**.'
    )
    return "\n\n".join(parts)

@app.callback(
    Output("ai-chat-history", "data"),
    Output("ai-output", "children"),
    Input("ai-send", "n_clicks"),
    Input("ai-clear", "n_clicks"),
    Input({"type": "ai-chip", "idx": ALL}, "n_clicks"),
    State("ai-input", "value"),
    State("ai-chat-history", "data"),
    prevent_initial_call=True
)
def ai_chat(n_send, n_clear, _chip_clicks, question, history):
    trigger = ctx.triggered_id
    history = history or []

    if trigger == "ai-clear":
        return [], ai_empty_state("Đã xoá lịch sử chat", "Hội thoại đã được làm mới. Hãy nhập câu hỏi mới hoặc chọn một gợi ý nhanh để bắt đầu lại.")

    q_raw = ""
    used_chip = False
    if isinstance(trigger, dict) and trigger.get("type") == "ai-chip":
        try:
            idx = int(trigger.get("idx"))
            if 0 <= idx < len(AI_SUGGESTIONS_V3):
                q_raw = AI_SUGGESTIONS_V3[idx]
                used_chip = True
        except Exception:
            q_raw = ""
    elif trigger == "ai-send":
        q_raw = (question or "").strip()
    else:
        raise PreventUpdate

    if not q_raw:
        return history, ai_empty_state("Chưa có câu hỏi hợp lệ", "Hãy nhập câu hỏi hoặc chọn một gợi ý nhanh ở phía trên để AI bắt đầu phân tích.")

    def split_questions(raw: str):
        raw = raw.replace(";", "\n")
        raw = re.sub(r"[?]+", "?\n", raw)
        parts = [x.strip() for x in raw.splitlines() if x.strip()]
        return parts[:8]

    questions = [q_raw] if used_chip else split_questions(q_raw)
    source_label = "chip" if used_chip else ("batch" if len(questions) > 1 else "typed")

    for q in questions:
        ans = answer_question(q, context=None)
        history.append({
            "q": q,
            "a": ans,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "source": source_label,
            "context_tags": [],
        })

    return history, render_ai_thread(history)

@app.callback(
    Output("ai-input", "value"),
    Input("ai-send", "n_clicks"),
    prevent_initial_call=True
)
def clear_ai_input(_):
    return ""

if DASH_LOG_BOOT_TIMING:
    _perf_log("app_import_total", _BOOT_STARTED)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8050")),
        debug=_env_flag("DASH_DEBUG", False)
    )
