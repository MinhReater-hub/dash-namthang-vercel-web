from pathlib import Path
import re
from datetime import datetime
from io import BytesIO

import pandas as pd
from dash import Dash, html, dcc, Input, Output, State, ctx, dash_table, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.express as px
import unicodedata
import copy
from dash.exceptions import PreventUpdate

VN_TZ = "Asia/Ho_Chi_Minh"

# =========================
# TIME / FORMAT HELPERS
# =========================
def to_vn_datetime(series: pd.Series, assume_tz_if_naive: str = VN_TZ) -> pd.Series:
    """
    FIX lệch tháng:
    - Trước đây assume naive = UTC => 00:00 UTC -> 07:00 VN, làm lệch tick/điểm trên trục thời gian.
    - Nay assume naive = VN_TZ => giữ đúng 00:00 theo VN.
    """
    s = pd.to_datetime(series, errors="coerce")
    try:
        if getattr(s.dt, "tz", None) is not None:
            return s.dt.tz_convert(VN_TZ).dt.tz_localize(None)
        return s.dt.tz_localize(assume_tz_if_naive).dt.tz_convert(VN_TZ).dt.tz_localize(None)
    except Exception:
        return pd.to_datetime(series, errors="coerce")

def fmt_vn(n) -> str:
    try:
        if n is None or (isinstance(n, float) and pd.isna(n)):
            return "0"
        return f"{float(n):,.0f}".replace(",", ".")
    except Exception:
        return str(n)

def find_col(df: pd.DataFrame, candidates):
    cols = list(df.columns)
    norm = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        key = str(cand).strip().lower()
        if key in norm:
            return norm[key]
    return None

def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)

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

LH_CANON = ["Xe Công ty", "Xe thương quyền hợp tác", "Xe thương quyền trả góp"]
HD_CANON = ["Hợp đồng thường", "Tuyến chiến lược", "Xe tiện chuyến"]

LH_MAP = {
    "xe cong ty": "Xe Công ty",
    "xe thuong quyen hop tac": "Xe thương quyền hợp tác",
    "xe thuong quyen tra gop": "Xe thương quyền trả góp",
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

def map_to_canon(series: pd.Series, mapping: dict) -> pd.Series:
    s = series.astype(str).map(norm_text)

    mapping_norm = {norm_text(k): v for k, v in mapping.items()}
    out = s.map(mapping_norm)

    m = out.isna()
    if m.any():
        ss = s[m]
        out.loc[m & ss.str.contains(r"\bhop dong\b") & ss.str.contains(r"\bthuong\b")] = "Hợp đồng thường"
        out.loc[m & ss.str.contains(r"\btuyen\b") & (ss.str.contains("chien luoc") | ss.str.contains("chuyen luoc"))] = "Tuyến chiến lược"
        out.loc[m & ss.str.contains(r"\bxe\b") & ss.str.contains("tien chuyen")] = "Xe tiện chuyến"

    return out.fillna("Khác")

# =========================
# DATA
# =========================
BASE_DIR = Path("output")
EXCEL_FILE = BASE_DIR / "bao_cao_doanh_thu_tong_hop.xlsx"

df_dt = pd.read_excel(EXCEL_FILE, sheet_name="DoanhThu_Thang_KhuVuc")
df_lh = pd.read_excel(EXCEL_FILE, sheet_name="DoanhThu_LH_KV_Thang")
df_hd = pd.read_excel(EXCEL_FILE, sheet_name="HopDong_KV_Thang")

for df in [df_dt, df_lh, df_hd]:
    df["thang_nam"] = pd.to_datetime(df["thang_nam"]).dt.to_period("M").dt.to_timestamp()
    df["thang_nam_vn"] = to_vn_datetime(df["thang_nam"])
    df["thang_nam_vn"] = pd.to_datetime(df["thang_nam_vn"]).dt.to_period("M").dt.to_timestamp()

    df["thang_label"] = df["thang_nam_vn"].dt.strftime("%m/%Y")
    df["nam"] = df["thang_nam_vn"].dt.year

# ==========================================================
# FIX: normalize khu_vuc + đặc biệt “Cần Thơ” không vào “Khác”
# ==========================================================
REGION_CANON_MAP = {
    "can tho": "Cần Thơ",
    "tp can tho": "Cần Thơ",
    "tp. can tho": "Cần Thơ",
    "thanh pho can tho": "Cần Thơ",
    "cần thơ": "Cần Thơ",
    "cantho": "Cần Thơ",
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

# ==========================================================
# FIX: MONTH_OPTIONS lấy theo TOÀN BỘ dữ liệu (dt + lh + hd)
# ==========================================================
_all_months = pd.concat(
    [df_dt["thang_nam_vn"], df_lh["thang_nam_vn"], df_hd["thang_nam_vn"]],
    ignore_index=True
)
MONTH_OPTIONS_ALL = (
    _all_months.dropna()
              .drop_duplicates()
              .sort_values()
              .dt.strftime("%m/%Y")
              .tolist()
)

# ==========================================================
# NEW: YEAR OPTIONS theo toàn bộ dữ liệu (dt + lh + hd)
# ==========================================================
_all_years = pd.concat([df_dt["nam"], df_lh["nam"], df_hd["nam"]], ignore_index=True)
YEAR_OPTIONS_ALL = sorted(_all_years.dropna().astype(int).drop_duplicates().tolist())

# ==========================================================
# NEW: mapping YEAR -> MONTH_OPTIONS (tháng phụ thuộc năm)
# ==========================================================
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

# detect raw column names
LH_COL_RAW = find_col(df_lh, [
    "loaihinh_hoptac",
    "loai_hinh", "loại_hình", "loaihinh", "loai hinh", "type", "loai"
])

HD_COL_RAW = find_col(df_hd, [
    "loai_hopdong",
    "loai_hop_dong", "loại_hợp_đồng", "loai hop dong",
    "loaihd", "loai_hd", "phan_loai", "nhom_hop_dong"
])

# create standardized columns (critical fix)
if LH_COL_RAW and LH_COL_RAW in df_lh.columns:
    df_lh["loai_hinh_std"] = map_to_canon(df_lh[LH_COL_RAW], LH_MAP)
else:
    df_lh["loai_hinh_std"] = "Khác"

if HD_COL_RAW and HD_COL_RAW in df_hd.columns:
    df_hd["loai_hop_dong_std"] = map_to_canon(df_hd[HD_COL_RAW], HD_MAP)
else:
    df_hd["loai_hop_dong_std"] = "Khác"

# use standardized columns everywhere
LH_COL = "loai_hinh_std"
HD_COL = "loai_hop_dong_std"

LH_OPTIONS = [{"label": x, "value": x} for x in (LH_CANON + ["Khác"])]
HD_OPTIONS = [{"label": x, "value": x} for x in (HD_CANON + ["Khác"])]

# ==========================================================
# COLOR MAP khu vực (nhất quán line/bar/pie)
# ==========================================================
REGION_PALETTE = (
    px.colors.qualitative.Bold
    + px.colors.qualitative.D3
    + px.colors.qualitative.Dark24
    + px.colors.qualitative.Alphabet
)

ALL_REGIONS = sorted(
    set(df_dt.get("khu_vuc", pd.Series(dtype=str)).astype(str).dropna().unique().tolist())
    | set(df_lh.get("khu_vuc", pd.Series(dtype=str)).astype(str).dropna().unique().tolist())
    | set(df_hd.get("khu_vuc", pd.Series(dtype=str)).astype(str).dropna().unique().tolist())
)

REGION_COLOR_MAP = {r: REGION_PALETTE[i % len(REGION_PALETTE)] for i, r in enumerate(ALL_REGIONS)}
REGION_COLOR_MAP["Khác"] = "#9aa0a6"

# ==========================================================
# KPI helpers
# ==========================================================
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

def region_payload_value(dff: pd.DataFrame, metric_col: str, selected_regions=None, max_items: int = 8):
    if dff is None or dff.empty or "khu_vuc" not in dff.columns or metric_col not in dff.columns:
        return []
    tmp = dff.copy()
    if selected_regions:
        sel = [str(x) for x in (selected_regions if isinstance(selected_regions, list) else [selected_regions])]
        tmp = tmp[tmp["khu_vuc"].astype(str).isin(sel)]
    if tmp.empty:
        return []
    g = tmp.groupby("khu_vuc", as_index=False)[metric_col].sum().sort_values(metric_col, ascending=False)
    total = float(g[metric_col].sum()) if not g.empty else 0.0
    rows = []
    for _, r in g.head(max_items).iterrows():
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
    if len(g) > max_items:
        rest_val = float(g.iloc[max_items:][metric_col].sum())
        pct = (rest_val / total * 100.0) if total > 0 else 0.0
        rows.append({
            "khu_vuc": "Khác",
            "value": rest_val,
            "value_fmt": fmt_vn(rest_val),
            "pct": pct,
            "color": REGION_COLOR_MAP.get("Khác", "#9aa0a6")
        })
    return rows

def region_payload_avg_revenue_per_trip(dff: pd.DataFrame, revenue_col: str, selected_regions=None, max_items: int = 8):
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
    rows = []
    for _, r in g.head(max_items).iterrows():
        name = str(r["khu_vuc"])
        avg = float(r["avg"]) if r["avg"] is not None else 0.0
        rows.append({
            "khu_vuc": name,
            "avg": avg,
            "avg_fmt": fmt_vn(avg),
            "color": REGION_COLOR_MAP.get(name, "#888")
        })
    return rows

def region_payload_avg_trips_per_month(dff: pd.DataFrame, selected_regions=None, max_items: int = 8):
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
    rows = []
    for _, r in g.head(max_items).iterrows():
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
        html.Div(main_text, className="kpi-value"),
        html.Div(subtitle_text, className="kpi-sub") if subtitle_text else None,
        html.Div(extra_lines, style={"marginTop": "6px"}) if extra_lines else None
    ])

# =========================
# PRO UI / THEME (v2)
# =========================
FA_CDN = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"
INTER_FONT = "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap"

PRO_APP_CSS = """
:root{
  --font: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;

  /* Dark */
  --bg: #070A14;
  --bg2: #0B1022;
  --panel: rgba(255,255,255,0.06);
  --panel2: rgba(255,255,255,0.08);
  --stroke: rgba(255,255,255,0.10);
  --stroke2: rgba(160,170,255,0.22);
  --text: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.70);

  --a1: #6D5EFC;
  --a2: #18D2FF;
  --good: #2EE59D;
  --bad: #FF4D6D;

  --shadow: 0 18px 55px rgba(0,0,0,0.45);
  --shadow2: 0 10px 30px rgba(0,0,0,0.35);

  --r16: 16px;
  --r20: 20px;
}

.theme-light{
  --bg: #F6F7FB;
  --bg2: #FFFFFF;
  --panel: rgba(255,255,255,0.92);
  --panel2: rgba(255,255,255,0.98);
  --stroke: rgba(20,20,40,0.10);
  --stroke2: rgba(80,90,160,0.18);
  --text: rgba(20,20,30,0.92);
  --muted: rgba(20,20,30,0.70);

  --shadow: 0 18px 55px rgba(20,20,40,0.10);
  --shadow2: 0 10px 28px rgba(20,20,40,0.10);
}

html, body{
  font-family: var(--font);
  background: radial-gradient(1200px 800px at 20% 10%, rgba(109,94,252,0.25), transparent 55%),
              radial-gradient(1000px 650px at 85% 20%, rgba(24,210,255,0.18), transparent 60%),
              linear-gradient(180deg, var(--bg), var(--bg2));
  color: var(--text);
}

/* Shell */
.app-shell{ min-height: 100vh; padding-bottom: 26px; }
.app-header{
  position: sticky; top: 0; z-index: 1000;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  background: linear-gradient(180deg, rgba(20,20,40,0.55), rgba(20,20,40,0.18));
  border-bottom: 1px solid var(--stroke);
}
.theme-light .app-header{
  background: linear-gradient(180deg, rgba(255,255,255,0.88), rgba(255,255,255,0.55));
}

/* Card */
.pro-card{
  border-radius: var(--r20) !important;
  background: var(--panel) !important;
  border: 1px solid var(--stroke) !important;
  box-shadow: var(--shadow2);
}
.pro-card:hover{ border-color: var(--stroke2) !important; }

/* KPI */
.kpi-title{
  font-size: 12px;
  letter-spacing: .12em;
  text-transform: uppercase;
  font-weight: 900;
  color: var(--muted);
  margin-bottom: 8px;
}
.kpi-value{
  font-size: 34px;
  font-weight: 900;
  line-height: 1.05;
}
.kpi-sub{
  font-size: 12px;
  font-weight: 800;
  color: var(--muted);
  margin-top: 6px;
}
.kpi-icon{
  width: 40px; height: 40px; border-radius: 999px;
  display:flex; align-items:center; justify-content:center;
  background: radial-gradient(80% 80% at 30% 30%, rgba(109,94,252,0.40), rgba(24,210,255,0.18));
  border: 1px solid rgba(160,170,255,0.20);
  box-shadow: 0 12px 24px rgba(0,0,0,0.25);
}

/* Filter label */
.filter-label{
  font-size: 12px;
  font-weight: 900;
  letter-spacing: .10em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 6px;
}

/* Dropdown theme (react-select) */
.Select-control{
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid var(--stroke) !important;
  border-radius: 14px !important;
  min-height: 46px !important;
}
.theme-light .Select-control{
  background: rgba(255,255,255,0.95) !important;
}
.Select-placeholder, .Select-value-label, .Select-input{
  color: var(--text) !important;
  font-weight: 800 !important;
}
.theme-light .Select-placeholder, .theme-light .Select-value-label, .theme-light .Select-input{
  color: rgba(20,20,30,0.92) !important;
}
.Select-menu-outer{ border-radius: 14px !important; }

/* Make dropdown menu text readable */
.Select-menu-outer .Select-option,
.Select-menu-outer .VirtualizedSelectOption,
.VirtualizedSelectOption{
  color: #111 !important;
  opacity: 1 !important;
}

/* Graph card spacing */
.graph-card{ padding: 10px 10px 6px 10px; }
.graph-title{
  font-weight: 900;
  letter-spacing: .04em;
  opacity: .92;
  margin: 4px 6px 10px 6px;
}

/* AI bubbles */
.ai-wrap{ margin-top: 6px; }
.ai-bubble{
  border-radius: 16px;
  padding: 10px 12px;
  margin-bottom: 10px;
  box-shadow: var(--shadow2);
  border: 1px solid var(--stroke);
  background: var(--panel);
}
.ai-user{ border-color: rgba(160,170,255,0.22); }
.ai-bot{ border-color: rgba(24,210,255,0.18); }
.ai-chip{
  display:inline-block;
  padding:6px 10px;
  margin:6px 6px 0 0;
  border-radius:999px;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
  border:1px solid rgba(140,140,200,0.22);
  background: rgba(20,20,35,0.35);
}
.ai-chip:hover{ background: rgba(40,40,70,0.45); }
"""

# =========================================================
# EXISTING PAGINATION CSS (kept)
# =========================================================
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

# =========================
# APP
# =========================
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG, FA_CDN, INTER_FONT],
    suppress_callback_exceptions=True
)

# inject CSS
app.index_string = app.index_string.replace(
    "</head>",
    f"<style>{PRO_APP_CSS}\n{PAGINATION_PRO_CSS}</style></head>"
)

# =========================
# ICONS (Font Awesome)
# =========================
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

# =========================
# ZOOM TARGETS + WRAPPERS
# =========================
ZOOM_TARGETS = []
for p in ["dt", "lh", "hd"]:
    ZOOM_TARGETS += [f"{p}-p1-kpi1", f"{p}-p1-kpi2", f"{p}-p1-kpi3"]
    ZOOM_TARGETS += [f"{p}-kpi1", f"{p}-kpi2", f"{p}-kpi3"]
    ZOOM_TARGETS += [f"{p}-p1-line-kv", f"{p}-p1-line", f"{p}-p1-bar", f"{p}-p1-pie"]
    ZOOM_TARGETS += [f"{p}-p2-line", f"{p}-p2-bar", f"{p}-p2-pie"]

def _zoomable_wrap(kind: str, target: str):
    return {"type": "zoomable", "kind": kind, "target": target}

# =========================
# UI HELPERS v2
# =========================
GRAPH_CONFIG_PRO = {
    "displayModeBar": True,
    "displaylogo": False,
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

def kpi_card_pro(title: str, icon, body_id: str, zoom_target: str):
    return html.Div(
        dbc.Card(
            dbc.CardBody([
                html.Div(className="d-flex justify-content-between align-items-start", children=[
                    html.Div([
                        html.Div(title, className="kpi-title"),
                        html.Div(id=body_id),
                    ], style={"minWidth": 0}),
                    html.Div(icon, className="kpi-icon"),
                ])
            ]),
            className="pro-card"
        ),
        id=_zoomable_wrap("kpi", zoom_target),
        n_clicks=0,
        style={"cursor": "pointer"}
    )

def graph_card_pro(title: str, graph_id: str, zoom_target: str, height: int = 420):
    return html.Div(
        dbc.Card(
            dbc.CardBody([
                html.Div(title, className="graph-title"),
                dcc.Graph(id=graph_id, config=GRAPH_CONFIG_PRO, style={"height": f"{height}px"}),
            ]),
            className="pro-card graph-card"
        ),
        id=_zoomable_wrap("fig", zoom_target),
        n_clicks=0,
        style={"cursor": "zoom-in"}
    )

# ==========================================================
# ZOOM helpers
# ==========================================================
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

        for ax in ["xaxis", "yaxis"]:
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

def pack_fig_store(fig, rows=None, meta=None):
    try:
        fig_dict = fig.to_dict()
    except Exception:
        fig_dict = fig
    return {"kind": "fig", "figure": fig_dict, "rows": rows or [], "meta": meta or {}}

def pack_kpi_store(title, main, subtitle, rows=None, kind="kpi"):
    return {"kind": kind, "title": title, "main": main, "subtitle": subtitle, "rows": rows or []}

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

# =========================================================
# NEW: Export helpers (filtered by current page filters)
# =========================================================
def _apply_export_filters(menu: str, page: int, filt: dict) -> pd.DataFrame:
    if menu == "dt":
        base = df_dt.copy()
        key = "dt"
    elif menu == "lh":
        base = df_lh.copy()
        key = "lh"
    else:
        base = df_hd.copy()
        key = "hd"

    year_val = (filt or {}).get("year", None)
    months = (filt or {}).get("months", []) or []
    dims = (filt or {}).get("dims", []) or []
    type_filter = (filt or {}).get("type_filter", []) or []

    dff = base

    if page == 2 and dims and "khu_vuc" in dff.columns:
        dff = dff[dff["khu_vuc"].astype(str).isin([str(x) for x in dims])]

    if year_val is not None and "nam" in dff.columns:
        dff = dff[dff["nam"] == int(year_val)]

    if months and "thang_label" in dff.columns:
        dff = dff[dff["thang_label"].isin(months)]

    if key == "lh" and type_filter and LH_COL in dff.columns:
        dff = dff[dff[LH_COL].astype(str).isin(type_filter)]
    if key == "hd" and type_filter and HD_COL in dff.columns:
        dff = dff[dff[HD_COL].astype(str).isin(type_filter)]

    return dff.copy()

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
    if menu in ["dt", "lh"]:
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

# =========================
# PLOTLY THEME v2
# =========================
def apply_time_axis(fig):
    fig.update_xaxes(
        tickformat="%m/%Y",
        dtick="M1",
        ticklabelmode="period",
        tickangle=0,
        showgrid=True,
        automargin=True,
        zeroline=False,
    )
    for tr in fig.data:
        t = getattr(tr, "type", "")
        if t in (None, "scatter"):
            try:
                tr.update(xperiod="M1", xperiodalignment="middle")
            except Exception:
                pass
        if t == "bar":
            try:
                tr.update(xperiod="M1", xperiodalignment="middle")
            except Exception:
                pass
    return fig

def _plotly_template(theme: str):
    return "plotly_dark" if theme == "dark" else "plotly_white"

def apply_theme(fig, theme):
    fig = apply_time_axis(fig)
    fig.update_layout(
        template=_plotly_template(theme),
        hovermode="x unified",
        legend_itemclick="toggleothers",
        legend_itemdoubleclick="toggle",
        margin=dict(l=18, r=18, t=120, b=18),
        title=dict(x=0.5, xanchor="center"),
        font=dict(family="Inter, Arial", size=13),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(0,0,0,0)"
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    if theme == "dark":
        fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)")
        fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)")
    else:
        fig.update_xaxes(gridcolor="rgba(20,20,40,0.08)")
        fig.update_yaxes(gridcolor="rgba(20,20,40,0.08)")
    return fig

def apply_chart_title(fig, title: str, top: int = 120, y_title: str = None):
    lines = (title.count("<br>") + 1) if isinstance(title, str) else 1
    extra = max(0, lines - 1) * 22
    top2 = max(top + extra, 190)

    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            xanchor="center",
            y=0.985,
            yanchor="top",
            pad=dict(t=14, b=10),
            font=dict(size=16, family="Inter, Arial")
        ),
        margin=dict(l=16, r=16, t=top2, b=16),
        title_automargin=True
    )
    try:
        fig.update_xaxes(title_text="Tháng", automargin=True)
    except Exception:
        pass
    if y_title:
        try:
            fig.update_yaxes(title_text=y_title, automargin=True)
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

# ==========================================================
# helpers làm chart
# ==========================================================
def top_n_keep_other(df: pd.DataFrame, cat_col: str, val_col: str, n: int = 8, other_label: str = "Khác", keep_cats=None):
    if cat_col not in df.columns or val_col not in df.columns or df.empty:
        return df.copy(), cat_col
    tmp = df.copy()
    tmp[cat_col] = tmp[cat_col].astype(str)

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

    new_col = f"{cat_col}__show"
    tmp[new_col] = tmp[cat_col].where(tmp[cat_col].isin(top_cats), other_label)
    return tmp, new_col

def make_vn_donut(df: pd.DataFrame, names: str, values: str, title: str, max_slices: int = 8, color_map=None, theme="dark"):
    dff = df.copy()
    if dff.empty:
        fig = px.pie(dff, names=names, values=values, hole=0.45)
        fig = apply_theme(fig, theme)
        fig = apply_chart_title(fig, title, top=130)
        return fig

    dff[names] = dff[names].astype(str)
    g = dff.groupby(names, as_index=False)[values].sum().sort_values(values, ascending=False)
    if len(g) > max_slices:
        top = g.head(max_slices).copy()
        other = pd.DataFrame({names: ["Khác"], values: [g.iloc[max_slices:][values].sum()]})
        g = pd.concat([top, other], ignore_index=True)

    g["val_fmt"] = g[values].apply(fmt_vn)

    kwargs = dict(names=names, values=values, hole=0.45, hover_data={"val_fmt": True, values: False})
    if color_map is not None:
        kwargs["color_discrete_map"] = color_map

    fig = px.pie(g, **kwargs)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig = apply_theme(fig, theme)
    fig = apply_chart_title(fig, title, top=135)
    return fig

# =========================
# LAYOUT
# =========================
app.layout = html.Div(
    id="app-shell",
    className="app-shell theme-dark",
    children=[
        dcc.Store(id="menu", data="dt"),
        dcc.Store(id="page", data=1),
        dcc.Store(id="theme", data="dark"),

        dcc.Store(id="filters-dt-p1", data={}),
        dcc.Store(id="filters-dt-p2", data={}),
        dcc.Store(id="filters-lh-p1", data={}),
        dcc.Store(id="filters-lh-p2", data={}),
        dcc.Store(id="filters-hd-p1", data={}),
        dcc.Store(id="filters-hd-p2", data={}),

        dcc.Store(id="ai-chat-history", data=[]),
        dcc.Interval(id="refresh-meta", interval=30 * 1000, n_intervals=0),

        html.Div(
            className="app-header",
            children=[
                dbc.Container(fluid=True, children=[
                    dbc.Row([
                        dbc.Col(
                            dbc.Button([ICON_MENU], id="open-menu", color="secondary", outline=True, className="me-2"),
                            width="auto"
                        ),
                        dbc.Col(
                            html.Div(id="top-title", style={"fontSize": "18px", "fontWeight": "900", "letterSpacing": "0.8px"})
                        ),
                        dbc.Col(
                            dbc.Button([ICON_THEME, html.Span(" Theme", className="ms-2")], id="toggle-theme",
                                       color="secondary", outline=True, className="float-end"),
                            width="auto"
                        )
                    ], className="py-2 align-items-center"),

                    dbc.Row([
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody([
                                    html.Div("DỮ LIỆU CẬP NHẬT LÚC", style={"fontWeight": "900", "opacity": 0.85, "letterSpacing": ".08em"}),
                                    dbc.Row([
                                        dbc.Col(html.Div(id="data-updated-at", style={"fontSize": "18px", "fontWeight": "900"})),
                                        dbc.Col(
                                            dbc.Button([ICON_DL, html.Span(" Tải Excel")], id="btn-download-excel",
                                                       color="secondary", outline=True, className="float-end"),
                                            width="auto"
                                        )
                                    ], className="g-2 align-items-center")
                                ]),
                                className="pro-card"
                            ),
                            md=7
                        )
                    ], className="pb-2"),
                ])
            ]
        ),

        dbc.Container(fluid=True, children=[
            dbc.Offcanvas(
                id="sidebar",
                title=html.Div([ICON_CHART, html.Span("  DASHBOARD MENU")]),
                is_open=False,
                placement="start",
                scrollable=True,
                style={"backgroundColor": "var(--bg2)", "color": "var(--text)"},
                children=[
                    html.Div("Chọn dashboard:", style={"fontWeight": "900", "marginBottom": "10px", "opacity": 0.9}),
                    dbc.Button("DOANH THU", id="btn-dt", color="primary", className="w-100 mb-2"),
                    dbc.Button("LOẠI HÌNH", id="btn-lh", color="warning", className="w-100 mb-2"),
                    dbc.Button("HỢP ĐỒNG", id="btn-hd", color="success", className="w-100 mb-2"),
                    html.Hr(style={"borderColor": "rgba(255,255,255,0.12)"}),
                    html.Div("Điều hướng trang:", style={"fontWeight": "900", "marginBottom": "10px", "opacity": 0.9}),
                    dbc.Button("Page 1", id="go-page-1", color="secondary", outline=True, className="w-100 mb-2"),
                    dbc.Button("Page 2", id="go-page-2", color="secondary", outline=True, className="w-100"),
                    html.Div(
                        [
                            "Intelligence Developer Nguyen Huu Minh",
                            html.Br(),
                            "SQL Data:",
                            html.Br(),
                            "Mai Nhat Truong",
                            html.Br(),
                            "Danh The Trung",
                        ],
                        style={
                            "position": "absolute",
                            "bottom": "14px",
                            "left": "16px",
                            "right": "16px",
                            "textAlign": "center",
                            "opacity": 0.85,
                            "fontSize": "14px",
                            "fontWeight": "700",
                            "whiteSpace": "pre-line",
                        },
                    ),
                ]
            ),

            dbc.Offcanvas(
                id="ai-box",
                title=html.Div([ICON_BOT, html.Span("  AI INSIGHTS")]),
                is_open=False,
                placement="end",
                scrollable=True,
                style={"backgroundColor": "var(--bg2)", "color": "var(--text)", "width": "420px"},
                children=[
                    html.Div(
                        "Hỏi bất kỳ câu nào về dữ liệu trong dashboard. Ví dụ: "
                        "“Top 3 khu vực doanh thu cao nhất năm 2025”, “Tỷ trọng doanh thu theo khu vực 2025”, "
                        "“Xu hướng doanh thu theo tháng năm 2025”.",
                        style={"opacity": 0.85, "marginBottom": "10px"}
                    ),
                    dbc.Textarea(
                        id="ai-input",
                        placeholder="Nhập câu hỏi...",
                        style={"backgroundColor": "rgba(255,255,255,0.06)", "color": "var(--text)",
                               "border": "1px solid var(--stroke)", "borderRadius": "14px"}
                    ),
                    dbc.Row([
                        dbc.Col(dbc.Button([ICON_SEND, html.Span(" Gửi")], id="ai-send", color="info", className="mt-2 w-100")),
                        dbc.Col(dbc.Button([ICON_TRASH, html.Span(" Xoá chat")], id="ai-clear",
                                           color="secondary", outline=True, className="mt-2 w-100")),
                    ], className="g-2"),
                    html.Div(
                        [
                            html.Span("Gợi ý nhanh:", style={"fontWeight": "900", "opacity": 0.85, "display": "block", "marginTop": "10px"}),
                            html.Div([
                                html.Span("Top 5 khu vực doanh thu cao nhất năm 2025", className="ai-chip"),
                                html.Span("Tỷ trọng doanh thu theo khu vực năm 2025", className="ai-chip"),
                                html.Span("Xu hướng doanh thu theo tháng năm 2025", className="ai-chip"),
                                html.Span("Bottom 3 khu vực số cuốc thấp nhất 2025", className="ai-chip"),
                            ], className="ai-wrap")
                        ],
                        style={"marginTop": "6px"}
                    ),
                    html.Hr(style={"borderColor": "rgba(255,255,255,0.12)"}),
                    dcc.Loading(html.Div(id="ai-output"), type="default")
                ]
            ),

            dcc.Loading(html.Div(id="content"), type="default"),

            dbc.Button(ICON_CHEV_L, id="prev-page", className="page-nav-btn page-nav-left", title="Trang trước"),
            dbc.Button(ICON_CHEV_R, id="next-page", className="page-nav-btn page-nav-right", title="Trang sau"),

            dbc.Button(
                ICON_BOT,
                id="open-ai",
                color="info",
                className="position-fixed end-0 me-4",
                style={"bottom": "88px", "borderRadius": "999px", "width": "56px", "height": "56px",
                       "boxShadow": "0 0 22px rgba(0,255,255,0.25)", "fontSize": "20px"}
            ),

            dbc.Modal(
                id="zoom-modal",
                is_open=False,
                size="xl",
                scrollable=True,
                backdrop=True,
                centered=True,
                style={"maxWidth": "98vw"},
                children=[
                    dbc.ModalHeader(dbc.ModalTitle(id="zoom-title", children="PHÓNG TO"), close_button=True),
                    dbc.ModalBody(
                        dcc.Loading(type="default", children=html.Div([
                            html.Div(id="zoom-kpi-render"),
                            dcc.Graph(
                                id="zoom-graph",
                                figure={},
                                config={"displayModeBar": True, "scrollZoom": True, "displaylogo": False},
                                style={"display": "none", "height": "82vh"}
                            ),
                            html.Hr(style={"borderColor": "rgba(255,255,255,0.12)", "marginTop": "10px", "marginBottom": "10px"}),
                            html.Div(id="zoom-detail", style={"display": "none"})
                        ])),
                        style={"padding": "10px"}
                    )
                ],
            ),

            dcc.Store(id="zoom-target", data=None),
            html.Div([dcc.Store(id={"type": "zoom-store", "target": t}, data=None) for t in ZOOM_TARGETS], style={"display": "none"}),
            dcc.Download(id="download-excel"),
        ])
    ]
)

# =========================
# THEME -> shell className
# =========================
@app.callback(
    Output("app-shell", "className"),
    Input("theme", "data"),
)
def _apply_shell_theme(theme):
    return f"app-shell {'theme-light' if theme == 'light' else 'theme-dark'}"

# =========================
# META
# =========================
@app.callback(
    Output("data-updated-at", "children"),
    Input("refresh-meta", "n_intervals")
)
def show_last_updated(_):
    try:
        ts = EXCEL_FILE.stat().st_mtime
        dt_local = pd.to_datetime(ts, unit="s", utc=True).tz_convert(VN_TZ)
        return dt_local.strftime("%d/%m/%Y %H:%M:%S (VN)")
    except Exception:
        return "Không đọc được thời gian cập nhật"

@app.callback(
    Output("download-excel", "data"),
    Input("btn-download-excel", "n_clicks"),
    State("menu", "data"),
    State("page", "data"),
    State("filters-dt-p1", "data"),
    State("filters-dt-p2", "data"),
    State("filters-lh-p1", "data"),
    State("filters-lh-p2", "data"),
    State("filters-hd-p1", "data"),
    State("filters-hd-p2", "data"),
    prevent_initial_call=True
)
def download_excel(n, menu, page, f_dt_p1, f_dt_p2, f_lh_p1, f_lh_p2, f_hd_p1, f_hd_p2):
    try:
        filt = {}
        if menu == "dt" and int(page) == 1: filt = f_dt_p1 or {}
        if menu == "dt" and int(page) == 2: filt = f_dt_p2 or {}
        if menu == "lh" and int(page) == 1: filt = f_lh_p1 or {}
        if menu == "lh" and int(page) == 2: filt = f_lh_p2 or {}
        if menu == "hd" and int(page) == 1: filt = f_hd_p1 or {}
        if menu == "hd" and int(page) == 2: filt = f_hd_p2 or {}

        dff = _apply_export_filters(menu, int(page), filt)
        summary = _make_summary_for_export(dff, menu)

        filters_sheet = pd.DataFrame([{
            "menu": menu,
            "page": int(page),
            "year": (filt or {}).get("year", None),
            "months": ", ".join((filt or {}).get("months", []) or []),
            "dims(khu_vuc)": ", ".join([str(x) for x in ((filt or {}).get("dims", []) or [])]),
            "type_filter": ", ".join([str(x) for x in ((filt or {}).get("type_filter", []) or [])]),
        }])

        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            filters_sheet.to_excel(writer, sheet_name="FILTERS", index=False)
            dff.to_excel(writer, sheet_name="FILTERED_DATA", index=False)
            if summary is not None and not summary.empty:
                summary.to_excel(writer, sheet_name="SUMMARY", index=False)

        ts = pd.Timestamp.now(tz=VN_TZ).strftime("%Y%m%d_%H%M%S")
        filename = f"export_{menu}_page{int(page)}_{ts}.xlsx"

        return dcc.send_bytes(bio.getvalue(), filename)
    except Exception:
        return no_update

# ===== Sidebar toggle =====
@app.callback(
    Output("sidebar", "is_open"),
    Input("open-menu", "n_clicks"),
    Input("btn-dt", "n_clicks"),
    Input("btn-lh", "n_clicks"),
    Input("btn-hd", "n_clicks"),
    State("sidebar", "is_open"),
    prevent_initial_call=True
)
def toggle_sidebar(n_open, a, b, c, is_open):
    if ctx.triggered_id == "open-menu":
        return not is_open
    return False

# ===== AI toggle =====
@app.callback(
    Output("ai-box", "is_open"),
    Input("open-ai", "n_clicks"),
    State("ai-box", "is_open"),
    prevent_initial_call=True
)
def toggle_ai(n, is_open):
    return not is_open

@app.callback(
    Output("menu", "data"),
    Input("btn-dt", "n_clicks"),
    Input("btn-lh", "n_clicks"),
    Input("btn-hd", "n_clicks"),
    prevent_initial_call=True
)
def switch_menu(a, b, c):
    if ctx.triggered_id == "btn-lh": return "lh"
    if ctx.triggered_id == "btn-hd": return "hd"
    return "dt"

@app.callback(
    Output("page", "data"),
    Input("next-page", "n_clicks"),
    Input("prev-page", "n_clicks"),
    Input("go-page-1", "n_clicks"),
    Input("go-page-2", "n_clicks"),
    State("page", "data"),
    prevent_initial_call=True
)
def switch_page(n1, n2, g1, g2, p):
    if ctx.triggered_id == "go-page-1":
        return 1
    if ctx.triggered_id == "go-page-2":
        return 2
    return 2 if ctx.triggered_id == "next-page" else 1

@app.callback(
    Output("theme", "data"),
    Input("toggle-theme", "n_clicks"),
    State("theme", "data"),
    prevent_initial_call=True
)
def toggle_theme(n, theme):
    return "light" if theme == "dark" else "dark"

@app.callback(
    Output("top-title", "children"),
    Input("menu", "data"),
    Input("page", "data"),
)
def update_top_title(menu, page):
    m = {"dt": "DOANH THU", "lh": "LOẠI HÌNH", "hd": "HỢP ĐỒNG"}.get(menu, "DASHBOARD")
    return f"{m}  •  PAGE {page}"

# =========================
# PAGES
# =========================
def page_1(prefix, title):
    extra_filter = None
    year_id = f"{prefix}-year"

    if prefix == "lh":
        extra_filter = dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Loại hình", className="filter-label"),
                    dcc.Dropdown(
                        id="lh-type-p1",
                        options=LH_OPTIONS,
                        multi=True,
                        placeholder="Lọc loại hình",
                        clearable=True
                    )
                ]),
                className="pro-card"
            ),
            md=4
        )
    elif prefix == "hd":
        extra_filter = dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Loại hợp đồng", className="filter-label"),
                    dcc.Dropdown(
                        id="hd-type-p1",
                        options=HD_OPTIONS,
                        multi=True,
                        placeholder="Lọc loại hợp đồng",
                        clearable=True
                    )
                ]),
                className="pro-card"
            ),
            md=4
        )

    return dbc.Container(fluid=True, children=[
        html.H3(title, className="text-center my-3", style={"fontWeight": "900"}),

        dbc.Row([
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([
                        html.Div("Năm", className="filter-label"),
                        dcc.Dropdown(
                            id=year_id,
                            options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                            value=None,
                            multi=False,
                            placeholder="Chọn năm",
                            clearable=True
                        )
                    ]),
                    className="pro-card"
                ),
                md=3
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([
                        html.Div("Tháng", className="filter-label"),
                        dcc.Dropdown(
                            id=f"{prefix}-month",
                            options=[{"label": m, "value": m} for m in MONTH_OPTIONS_ALL],
                            multi=True,
                            placeholder="Chọn tháng",
                            clearable=True
                        )
                    ]),
                    className="pro-card"
                ),
                md=5
            ),
            extra_filter if extra_filter is not None else dbc.Col(html.Div(), md=4),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(kpi_card_pro("TỔNG", ICON_CHART, f"{prefix}-p1-kpi1", f"{prefix}-p1-kpi1"), md=4),
            dbc.Col(kpi_card_pro("SỐ CUỐC", ICON_CHART, f"{prefix}-p1-kpi2", f"{prefix}-p1-kpi2"), md=4),
            dbc.Col(kpi_card_pro("TRUNG BÌNH", ICON_CHART, f"{prefix}-p1-kpi3", f"{prefix}-p1-kpi3"), md=4),
        ], className="mb-4 g-2"),

        dbc.Row([
            dbc.Col(graph_card_pro("So sánh theo khu vực", f"{prefix}-p1-line-kv", f"{prefix}-p1-line-kv", height=460), md=12),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(graph_card_pro("Xu hướng tổng", f"{prefix}-p1-line", f"{prefix}-p1-line", height=420), md=6),
            dbc.Col(graph_card_pro("Biểu đồ cột", f"{prefix}-p1-bar", f"{prefix}-p1-bar", height=420), md=6),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(graph_card_pro("Tỷ trọng theo tháng", f"{prefix}-p1-pie", f"{prefix}-p1-pie", height=420), md=6),
        ], className="g-2"),
    ])

def page_2(prefix, title, df, dim):
    extra_filter = None
    year_id = f"{prefix}-year-p2"

    if prefix == "lh":
        extra_filter = dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Loại hình", className="filter-label"),
                    dcc.Dropdown(
                        id="lh-type-p2",
                        options=LH_OPTIONS,
                        multi=True,
                        placeholder="Lọc loại hình",
                        clearable=True
                    )
                ]),
                className="pro-card"
            ),
            md=4
        )
    elif prefix == "hd":
        extra_filter = dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("Loại hợp đồng", className="filter-label"),
                    dcc.Dropdown(
                        id="hd-type-p2",
                        options=HD_OPTIONS,
                        multi=True,
                        placeholder="Lọc loại hợp đồng",
                        clearable=True
                    )
                ]),
                className="pro-card"
            ),
            md=4
        )

    kv_options = sorted(df[dim].astype(str).unique())
    default_kv = [kv_options[0]] if kv_options else []

    return dbc.Container(fluid=True, children=[
        html.H3(title, className="text-center my-3", style={"fontWeight": "900"}),
        html.Div(id=f"{prefix}-insight", className="text-center mb-3",
                 style={"fontSize": "16px", "fontWeight": "900", "opacity": 0.9}),

        dbc.Row([
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([
                        html.Div("Khu vực", className="filter-label"),
                        dcc.Dropdown(
                            id=f"{prefix}-dim",
                            options=[{"label": x, "value": x} for x in kv_options],
                            value=default_kv,
                            multi=True,
                            clearable=True
                        )
                    ]),
                    className="pro-card"
                ),
                md=3
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([
                        html.Div("Năm", className="filter-label"),
                        dcc.Dropdown(
                            id=year_id,
                            options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                            value=None,
                            multi=False,
                            placeholder="Chọn năm",
                            clearable=True
                        )
                    ]),
                    className="pro-card"
                ),
                md=3
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody([
                        html.Div("Tháng", className="filter-label"),
                        dcc.Dropdown(
                            id=f"{prefix}-month-p2",
                            options=[{"label": m, "value": m} for m in MONTH_OPTIONS_ALL],
                            multi=True,
                            placeholder="Chọn tháng",
                            clearable=True
                        )
                    ]),
                    className="pro-card"
                ),
                md=4
            ),
            extra_filter if extra_filter is not None else dbc.Col(html.Div(), md=2),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(kpi_card_pro("TỔNG", ICON_CHART, f"{prefix}-kpi1", f"{prefix}-kpi1"), md=4),
            dbc.Col(kpi_card_pro("SỐ CUỐC", ICON_CHART, f"{prefix}-kpi2", f"{prefix}-kpi2"), md=4),
            dbc.Col(kpi_card_pro("TRUNG BÌNH", ICON_CHART, f"{prefix}-kpi3", f"{prefix}-kpi3"), md=4),
        ], className="mb-4 g-2"),

        dbc.Row([
            dbc.Col(graph_card_pro("Line", f"{prefix}-p2-line", f"{prefix}-p2-line", height=420), md=6),
            dbc.Col(graph_card_pro("Bar", f"{prefix}-p2-bar", f"{prefix}-p2-bar", height=420), md=6),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(graph_card_pro("Donut", f"{prefix}-p2-pie", f"{prefix}-p2-pie", height=420), md=6),
        ], className="mb-3 g-2"),

        dbc.Card(
            dbc.CardBody([
                html.Div("Bảng dữ liệu", className="graph-title"),
                dash_table.DataTable(
                    id=f"{prefix}-table",
                    page_action=("none" if prefix in ["lh", "hd"] else "native"),
                    page_size=12,
                    fixed_rows={"headers": True},
                    style_table={"borderRadius": "16px", "overflow": "hidden", "border": "1px solid rgba(255,255,255,0.10)"},
                    style_header={"backgroundColor": "rgba(0,0,0,0)", "color": "var(--muted)", "fontWeight": "900", "border": "none"},
                    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": "var(--text)", "textAlign": "center", "padding": "10px", "border": "none"},
                    style_data_conditional=[
                        {"if": {"row_index": "odd"}, "backgroundColor": "rgba(255,255,255,0.03)"},
                        {"if": {"state": "active"}, "border": "1px solid rgba(109,94,252,0.45)"},
                    ],
                ),
            ]),
            className="pro-card"
        ),
    ])

@app.callback(
    Output("content", "children"),
    Input("menu", "data"),
    Input("page", "data")
)
def render(menu, page):
    def wrap(children, show):
        return html.Div(children, style={"display": "block" if show else "none"})

    try:
        p = int(page) if page is not None else 1
    except Exception:
        p = 1

    return html.Div([
        wrap(page_1("dt", "DOANH THU TỔNG – TOÀN TẬP ĐOÀN"), menu == "dt" and p == 1),
        wrap(page_2("dt", "PHÂN TÍCH DOANH THU THEO KHU VỰC", df_dt, "khu_vuc"), menu == "dt" and p == 2),

        wrap(page_1("lh", "DOANH THU LOẠI HÌNH – TOÀN TẬP ĐOÀN"), menu == "lh" and p == 1),
        wrap(page_2("lh", "PHÂN TÍCH LOẠI HÌNH THEO KHU VỰC", df_lh, "khu_vuc"), menu == "lh" and p == 2),

        wrap(page_1("hd", "HỢP ĐỒNG – TOÀN TẬP ĐOÀN"), menu == "hd" and p == 1),
        wrap(page_2("hd", "PHÂN TÍCH HỢP ĐỒNG THEO KHU VỰC", df_hd, "khu_vuc"), menu == "hd" and p == 2),
    ])

# ==========================================================
# Store current filters per (menu, page) for export
# ==========================================================
@app.callback(
    Output("filters-dt-p1", "data"),
    Input("dt-year", "value"),
    Input("dt-month", "value"),
    prevent_initial_call=True
)
def _store_filters_dt_p1(year_val, months):
    return {"year": year_val, "months": months or []}

@app.callback(
    Output("filters-lh-p1", "data"),
    Input("lh-year", "value"),
    Input("lh-month", "value"),
    Input("lh-type-p1", "value"),
    prevent_initial_call=True
)
def _store_filters_lh_p1(year_val, months, type_filter):
    return {"year": year_val, "months": months or [], "type_filter": type_filter or []}

@app.callback(
    Output("filters-hd-p1", "data"),
    Input("hd-year", "value"),
    Input("hd-month", "value"),
    Input("hd-type-p1", "value"),
    prevent_initial_call=True
)
def _store_filters_hd_p1(year_val, months, type_filter):
    return {"year": year_val, "months": months or [], "type_filter": type_filter or []}

@app.callback(
    Output("filters-dt-p2", "data"),
    Input("dt-dim", "value"),
    Input("dt-year-p2", "value"),
    Input("dt-month-p2", "value"),
    prevent_initial_call=True
)
def _store_filters_dt_p2(dims, year_val, months):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or []}

@app.callback(
    Output("filters-lh-p2", "data"),
    Input("lh-dim", "value"),
    Input("lh-year-p2", "value"),
    Input("lh-month-p2", "value"),
    Input("lh-type-p2", "value"),
    prevent_initial_call=True
)
def _store_filters_lh_p2(dims, year_val, months, type_filter):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or [], "type_filter": type_filter or []}

@app.callback(
    Output("filters-hd-p2", "data"),
    Input("hd-dim", "value"),
    Input("hd-year-p2", "value"),
    Input("hd-month-p2", "value"),
    Input("hd-type-p2", "value"),
    prevent_initial_call=True
)
def _store_filters_hd_p2(dims, year_val, months, type_filter):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or [], "type_filter": type_filter or []}

# ==========================================================
# Year -> Month options phụ thuộc year (P1 + P2 cho dt/lh/hd)
# ==========================================================
def _month_options_for_year(year_val):
    if year_val is None:
        opts = MONTH_OPTIONS_ALL
    else:
        opts = MONTH_OPTIONS_BY_YEAR.get(int(year_val), [])
    return [{"label": m, "value": m} for m in opts], opts

@app.callback(
    Output("dt-month", "options"),
    Output("dt-month", "value"),
    Input("dt-year", "value"),
    State("dt-month", "value"),
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
    Input("lh-year", "value"),
    State("lh-month", "value"),
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
    Input("hd-year", "value"),
    State("hd-month", "value"),
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
    Input("dt-year-p2", "value"),
    State("dt-month-p2", "value"),
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
    Input("lh-year-p2", "value"),
    State("lh-month-p2", "value"),
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
    Input("hd-year-p2", "value"),
    State("hd-month-p2", "value"),
    prevent_initial_call=True
)
def hd_month_p2_depends_on_year(year_val, cur_months):
    options, allowed = _month_options_for_year(year_val)
    cur_months = cur_months or []
    new_val = [m for m in cur_months if m in allowed] if year_val is not None else cur_months
    return options, new_val

# =========================
# CHART + KPI callbacks
# =========================
def callbacks(prefix, df, value_col):
    p1_filter_input = None
    p2_filter_input = None

    if prefix == "lh":
        p1_filter_input = Input("lh-type-p1", "value", allow_optional=True)
        p2_filter_input = Input("lh-type-p2", "value", allow_optional=True)
    elif prefix == "hd":
        p1_filter_input = Input("hd-type-p1", "value", allow_optional=True)
        p2_filter_input = Input("hd-type-p2", "value", allow_optional=True)

    inputs_p1 = [
        Input(f"{prefix}-year", "value", allow_optional=True),
        Input(f"{prefix}-month", "value", allow_optional=True),
        Input("theme", "data"),
    ]
    if p1_filter_input is not None:
        inputs_p1.append(p1_filter_input)

    @app.callback(
        Output(f"{prefix}-p1-kpi1", "children"),
        Output(f"{prefix}-p1-kpi2", "children"),
        Output(f"{prefix}-p1-kpi3", "children"),
        Output(f"{prefix}-p1-line-kv", "figure"),
        Output(f"{prefix}-p1-line", "figure"),
        Output(f"{prefix}-p1-bar", "figure"),
        Output(f"{prefix}-p1-pie", "figure"),

        Output({"type": "zoom-store", "target": f"{prefix}-p1-kpi1"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p1-kpi2"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p1-kpi3"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p1-line-kv"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p1-line"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p1-bar"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p1-pie"}, "data"),

        *inputs_p1,
        State("menu", "data"),
        State("page", "data"),
    )
    def p1(*args):
        if p1_filter_input is not None:
            year_val, months, theme, type_filter, menu, page = args
        else:
            year_val, months, theme, menu, page = args
            type_filter = None

        if menu != prefix or int(page) != 1:
            raise PreventUpdate

        dff = df.copy()

        if year_val is not None and "nam" in dff.columns:
            dff = dff[dff["nam"] == int(year_val)]
        if months:
            dff = dff[dff["thang_label"].isin(months)]
        if prefix == "lh" and type_filter and LH_COL in dff.columns:
            dff = dff[dff[LH_COL].astype(str).isin(type_filter)]
        if prefix == "hd" and type_filter and HD_COL in dff.columns:
            dff = dff[dff[HD_COL].astype(str).isin(type_filter)]

        metric_label = "Doanh thu" if value_col != "tong_so_cuoc" else "Số cuốc"
        metric_axis = metric_label

        year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
        if months:
            mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else f"{len(months)} tháng đã chọn"
        else:
            mo_txt = "Tất cả tháng"

        tf_txt = ""
        if prefix == "lh" and type_filter:
            tf_txt = f" • Lọc loại hình: {', '.join(type_filter)}"
        if prefix == "hd" and type_filter:
            tf_txt = f" • Lọc loại HĐ: {', '.join(type_filter)}"

        total = dff[value_col].sum() if value_col in dff.columns else 0
        sc = dff["tong_so_cuoc"].sum() if "tong_so_cuoc" in dff.columns else 0
        months_n = int(dff["thang_label"].nunique()) if "thang_label" in dff.columns else 1
        months_n = max(months_n, 1)

        total_payload = region_payload_value(dff, value_col, selected_regions=None, max_items=8)
        sc_payload = region_payload_value(dff, "tong_so_cuoc", selected_regions=None, max_items=8) if "tong_so_cuoc" in dff.columns else []

        if value_col == "tong_so_cuoc":
            avg = total / months_n
            avg_caption = f"TB cuốc/tháng • {months_n} tháng"
            avg_payload = region_payload_avg_trips_per_month(dff, selected_regions=None, max_items=8)
            avg_lines = [
                _ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / tháng']) for r in avg_payload[:6]
            ]
        else:
            avg = total / max(sc, 1)
            avg_caption = f"TB doanh thu/cuốc • {fmt_vn(sc)} cuốc"
            avg_payload = region_payload_avg_revenue_per_trip(dff, value_col, selected_regions=None, max_items=8)
            avg_lines = [
                _ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / cuốc']) for r in avg_payload[:6]
            ]

        kpi_subtitle = f"{year_txt} • {mo_txt}{tf_txt}"

        kpi1 = kpi_content(fmt_vn(total), kpi_subtitle, region_value_lines_from_payload(total_payload, max_lines=4))
        kpi2 = kpi_content(fmt_vn(sc), kpi_subtitle, region_value_lines_from_payload(sc_payload, max_lines=4))
        kpi3 = kpi_content(fmt_vn(avg), avg_caption, avg_lines[:4])

        kpi1_store = pack_kpi_store("TỔNG", fmt_vn(total), kpi_subtitle, total_payload)
        kpi2_store = pack_kpi_store("SỐ CUỐC", fmt_vn(sc), kpi_subtitle, sc_payload)
        kpi3_store = pack_kpi_store("TRUNG BÌNH", fmt_vn(avg), avg_caption, avg_payload)

        g = dff.groupby("thang_nam_vn", as_index=False).agg({value_col: "sum"}).sort_values("thang_nam_vn")
        g["val_fmt"] = g[value_col].apply(fmt_vn)
        g["thang_label"] = g["thang_nam_vn"].dt.strftime("%m/%Y")

        if "khu_vuc" in dff.columns:
            dff_kv, kv_col = top_n_keep_other(dff, "khu_vuc", value_col, n=8, other_label="Khác", keep_cats=PINNED_REGIONS)
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
            fig_kv = apply_chart_title(
                fig_kv,
                f"{metric_label} theo tháng • So sánh giữa các khu vực (Top 8 + Khác)<br>{year_txt} • {mo_txt}{tf_txt}",
                top=210,
                y_title=metric_axis
            )
            fig_kv = _add_line_point_labels(fig_kv, show_all_if_points_le=10)

            rows_kv = []
            for _, r in gkv.iterrows():
                rows_kv.append({
                    "thang_label": r["thang_label"],
                    "khu_vuc": str(r[kv_col]),
                    "metric": float(r[value_col]),
                    "metric_fmt": r["val_fmt"]
                })
            fig_kv_store = pack_fig_store(fig_kv, rows=rows_kv, meta={"chart": "line_kv", "metric_label": metric_label, "series_key": kv_col})
        else:
            fig_kv = px.line(g, x="thang_nam_vn", y=value_col, markers=True, hover_data={"val_fmt": True, value_col: False})
            fig_kv.update_traces(line_shape="spline", line_width=3, marker_size=7)
            fig_kv = apply_theme(fig_kv, theme)
            fig_kv = apply_chart_title(fig_kv, f"{metric_label} theo tháng<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
            fig_kv = _add_line_point_labels(fig_kv, show_all_if_points_le=10)
            fig_kv_store = pack_fig_store(fig_kv, rows=g.to_dict("records"), meta={"chart": "line_total", "metric_label": metric_label})

        fig_line = px.line(g, x="thang_nam_vn", y=value_col, markers=True, hover_data={"val_fmt": True, value_col: False})
        fig_line.update_traces(line_shape="spline", line_width=3, marker_size=7)
        fig_line = apply_theme(fig_line, theme)
        fig_line = apply_chart_title(fig_line, f"{metric_label} theo tháng • Tổng toàn tập đoàn<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
        fig_line = _add_line_point_labels(fig_line, show_all_if_points_le=10)
        fig_line_store = pack_fig_store(fig_line, rows=g.to_dict("records"), meta={"chart": "line_total", "metric_label": metric_label})

        fig_bar = px.bar(g, x="thang_nam_vn", y=value_col, text="val_fmt", hover_data={"val_fmt": True, value_col: False})
        fig_bar.update_traces(textposition="outside", cliponaxis=False)
        fig_bar.update_layout(margin=dict(t=20))
        fig_bar = apply_theme(fig_bar, theme)
        fig_bar = apply_chart_title(fig_bar, f"{metric_label} theo tháng • Biểu đồ cột<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
        fig_bar_store = pack_fig_store(fig_bar, rows=g.to_dict("records"), meta={"chart": "bar_total", "metric_label": metric_label})

        g_pie = g.copy()
        g_pie["thang"] = g_pie["thang_label"]
        fig_pie = px.pie(g_pie, names="thang", values=value_col, hole=0.45, hover_data={"val_fmt": True, value_col: False})
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie = apply_theme(fig_pie, theme)
        fig_pie = apply_chart_title(fig_pie, f"Tỷ trọng {metric_label.lower()} theo tháng<br>{year_txt} • {mo_txt}{tf_txt}", top=210)
        fig_pie_store = pack_fig_store(fig_pie, rows=g_pie.to_dict("records"), meta={"chart": "pie_month", "metric_label": metric_label})

        return (
            kpi1, kpi2, kpi3,
            fig_kv, fig_line, fig_bar, fig_pie,
            kpi1_store, kpi2_store, kpi3_store,
            fig_kv_store, fig_line_store, fig_bar_store, fig_pie_store
        )

    inputs_p2 = [
        Input(f"{prefix}-dim", "value", allow_optional=True),
        Input(f"{prefix}-year-p2", "value", allow_optional=True),
        Input(f"{prefix}-month-p2", "value", allow_optional=True),
        Input("theme", "data"),
    ]
    if p2_filter_input is not None:
        inputs_p2.append(p2_filter_input)

    @app.callback(
        Output(f"{prefix}-kpi1", "children"),
        Output(f"{prefix}-kpi2", "children"),
        Output(f"{prefix}-kpi3", "children"),
        Output(f"{prefix}-p2-line", "figure"),
        Output(f"{prefix}-p2-bar", "figure"),
        Output(f"{prefix}-p2-pie", "figure"),
        Output(f"{prefix}-table", "data"),
        Output(f"{prefix}-insight", "children"),
        Output(f"{prefix}-table", "style_cell"),
        Output(f"{prefix}-table", "style_header"),

        Output({"type": "zoom-store", "target": f"{prefix}-kpi1"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-kpi2"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-kpi3"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p2-line"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p2-bar"}, "data"),
        Output({"type": "zoom-store", "target": f"{prefix}-p2-pie"}, "data"),

        *inputs_p2,
        State("menu", "data"),
        State("page", "data"),
    )
    def p2(*args):
        if p2_filter_input is not None:
            dim, year_val, months, theme, type_filter, menu, page = args
        else:
            dim, year_val, months, theme, menu, page = args
            type_filter = None

        if menu != prefix or int(page) != 2:
            raise PreventUpdate

        dims = dim if isinstance(dim, list) else ([dim] if dim else [])
        dff = df.copy()
        if dims:
            dff = dff[dff["khu_vuc"].astype(str).isin([str(x) for x in dims])]
        if year_val is not None and "nam" in dff.columns:
            dff = dff[dff["nam"] == int(year_val)]
        if months:
            dff = dff[dff["thang_label"].isin(months)]
        if prefix == "lh" and type_filter and LH_COL in dff.columns:
            dff = dff[dff[LH_COL].astype(str).isin(type_filter)]
        if prefix == "hd" and type_filter and HD_COL in dff.columns:
            dff = dff[dff[HD_COL].astype(str).isin(type_filter)]

        metric_label = "Doanh thu" if value_col != "tong_so_cuoc" else "Số cuốc"
        metric_axis = metric_label

        year_txt = f"Năm {int(year_val)}" if year_val is not None else "Tất cả năm"
        if months:
            mo_txt = months[0] if isinstance(months, list) and len(months) == 1 else f"{len(months)} tháng đã chọn"
        else:
            mo_txt = "Tất cả tháng"

        dims_show = ", ".join([str(x) for x in dims]) if dims else "Tất cả khu vực"
        if dims and len(dims) > 3:
            dims_show = f"{len(dims)} khu vực đã chọn"

        tf_txt = ""
        if prefix == "lh" and type_filter:
            tf_txt = f" • Lọc loại hình: {', '.join(type_filter)}"
        if prefix == "hd" and type_filter:
            tf_txt = f" • Lọc loại HĐ: {', '.join(type_filter)}"

        dff = dff.sort_values("thang_nam_vn")

        total = dff[value_col].sum() if value_col in dff.columns else 0
        sc = dff["tong_so_cuoc"].sum() if "tong_so_cuoc" in dff.columns else 0
        months_n = int(dff["thang_label"].nunique()) if "thang_label" in dff.columns else 1
        months_n = max(months_n, 1)

        total_payload = region_payload_value(dff, value_col, selected_regions=dims, max_items=12)
        sc_payload = region_payload_value(dff, "tong_so_cuoc", selected_regions=dims, max_items=12) if "tong_so_cuoc" in dff.columns else []

        if value_col == "tong_so_cuoc":
            avg = total / months_n
            avg_caption = f"TB cuốc/tháng • {months_n} tháng"
            avg_payload = region_payload_avg_trips_per_month(dff, selected_regions=dims, max_items=12)
            avg_lines = [
                _ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / tháng']) for r in avg_payload[:6]
            ]
        else:
            avg = total / max(sc, 1)
            avg_caption = f"TB doanh thu/cuốc • {fmt_vn(sc)} cuốc"
            avg_payload = region_payload_avg_revenue_per_trip(dff, value_col, selected_regions=dims, max_items=12)
            avg_lines = [
                _ellipsis_div([_swatch(r["color"]), f'{r["khu_vuc"]}: {r["avg_fmt"]} / cuốc']) for r in avg_payload[:6]
            ]

        kpi_subtitle = f"{dims_show} • {year_txt} • {mo_txt}{tf_txt}"

        kpi1 = kpi_content(fmt_vn(total), kpi_subtitle, region_value_lines_from_payload(total_payload, max_lines=6))
        kpi2 = kpi_content(fmt_vn(sc), kpi_subtitle, region_value_lines_from_payload(sc_payload, max_lines=6))
        kpi3 = kpi_content(fmt_vn(avg), avg_caption, avg_lines[:6])

        kpi1_store = pack_kpi_store("TỔNG", fmt_vn(total), kpi_subtitle, total_payload)
        kpi2_store = pack_kpi_store("SỐ CUỐC", fmt_vn(sc), kpi_subtitle, sc_payload)
        kpi3_store = pack_kpi_store("TRUNG BÌNH", fmt_vn(avg), avg_caption, avg_payload)

        insight = f"Tổng {fmt_vn(total)} – {dims_show}"

        # FIG1
        if "khu_vuc" in dff.columns:
            if dims:
                dff_kv = dff.copy()
                kv_col = "khu_vuc"
            else:
                dff_kv, kv_col = top_n_keep_other(dff, "khu_vuc", value_col, n=8, other_label="Khác", keep_cats=PINNED_REGIONS)

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
            fig1 = apply_chart_title(
                fig1,
                f"{metric_label} theo tháng • So sánh khu vực (1 biểu đồ)<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}",
                top=220, y_title=metric_axis
            )
            fig1 = _add_line_point_labels(fig1, show_all_if_points_le=10)

            rows1 = []
            for _, r in gkv.iterrows():
                rows1.append({
                    "thang_label": r["thang_label"],
                    "khu_vuc": str(r[kv_col]),
                    "metric": float(r[value_col]),
                    "metric_fmt": r["val_fmt"]
                })
            fig1_store = pack_fig_store(fig1, rows=rows1, meta={"chart": "line_kv", "metric_label": metric_label, "series_key": kv_col})
        else:
            g = dff.groupby("thang_nam_vn", as_index=False).agg({value_col: "sum"}).sort_values("thang_nam_vn")
            g["val_fmt"] = g[value_col].apply(fmt_vn)
            g["thang_label"] = g["thang_nam_vn"].dt.strftime("%m/%Y")
            fig1 = px.line(g, x="thang_nam_vn", y=value_col, markers=True, hover_data={"val_fmt": True, value_col: False})
            fig1.update_traces(line_shape="spline", line_width=3, marker_size=7)
            fig1 = apply_theme(fig1, theme)
            fig1 = apply_chart_title(fig1, f"{metric_label} theo tháng<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}", top=220, y_title=metric_axis)
            fig1 = _add_line_point_labels(fig1, show_all_if_points_le=10)
            fig1_store = pack_fig_store(fig1, rows=g.to_dict("records"), meta={"chart": "line_total", "metric_label": metric_label})

        # FIG2
        if "tong_so_cuoc" in dff.columns:
            if len(dims) >= 2:
                gsc = dff.groupby(["thang_nam_vn", "khu_vuc"], as_index=False).agg({"tong_so_cuoc": "sum"}).sort_values("thang_nam_vn")
                gsc["sc_fmt"] = gsc["tong_so_cuoc"].apply(fmt_vn)
                gsc["thang_label"] = gsc["thang_nam_vn"].dt.strftime("%m/%Y")

                kv_order = gsc.groupby("khu_vuc", as_index=False)["tong_so_cuoc"].sum().sort_values("tong_so_cuoc", ascending=False)["khu_vuc"].tolist()

                fig2 = px.bar(
                    gsc,
                    x="thang_nam_vn",
                    y="tong_so_cuoc",
                    color="khu_vuc",
                    category_orders={"khu_vuc": kv_order},
                    color_discrete_map=REGION_COLOR_MAP,
                    text="sc_fmt",
                    hover_data={"sc_fmt": True, "tong_so_cuoc": False}
                )
                fig2.update_layout(
                    barmode="group",
                    legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0)
                )
                fig2.update_traces(textposition="auto", cliponaxis=False)
                fig2 = apply_theme(fig2, theme)
                fig2 = apply_chart_title(
                    fig2,
                    f"Số cuốc theo tháng • So sánh theo khu vực (Grouped Bar)<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}",
                    top=220,
                    y_title="Số cuốc"
                )

                rows2 = []
                for _, r in gsc.iterrows():
                    rows2.append({
                        "thang_label": r["thang_label"],
                        "khu_vuc": str(r["khu_vuc"]),
                        "metric": float(r["tong_so_cuoc"]),
                        "metric_fmt": r["sc_fmt"]
                    })
                fig2_store = pack_fig_store(fig2, rows=rows2, meta={"chart": "bar_kv", "metric_label": "Số cuốc", "series_key": "khu_vuc"})
            else:
                dff_bar = dff.copy()
                dff_bar["sc_fmt"] = dff_bar["tong_so_cuoc"].apply(fmt_vn)
                dff_bar["thang_label"] = dff_bar["thang_nam_vn"].dt.strftime("%m/%Y")
                fig2 = px.bar(dff_bar, x="thang_nam_vn", y="tong_so_cuoc", text="sc_fmt", hover_data={"sc_fmt": True, "tong_so_cuoc": False})
                fig2.update_traces(textposition="outside", cliponaxis=False)
                fig2.update_layout(margin=dict(t=20))
                fig2 = apply_theme(fig2, theme)
                fig2 = apply_chart_title(
                    fig2,
                    f"Số cuốc theo tháng • Khu vực đã chọn<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}",
                    top=220,
                    y_title="Số cuốc"
                )
                fig2_store = pack_fig_store(fig2, rows=dff_bar[["thang_label", "tong_so_cuoc", "sc_fmt"]].to_dict("records"), meta={"chart": "bar_total", "metric_label": "Số cuốc"})
        else:
            fig2 = apply_theme(px.bar(dff, x="thang_nam_vn", y=value_col), theme)
            fig2 = apply_chart_title(
                fig2,
                f"Biểu đồ cột theo tháng<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}",
                top=220
            )
            fig2_store = pack_fig_store(fig2, rows=[], meta={"chart": "bar_unknown", "metric_label": metric_label})

        # FIG3
        if len(dims) >= 2 and "khu_vuc" in dff.columns:
            fig3 = make_vn_donut(
                dff,
                names="khu_vuc",
                values=value_col,
                title=f"Tỷ trọng đóng góp theo khu vực • {metric_label}<br>{year_txt} • {mo_txt}{tf_txt}",
                max_slices=10,
                color_map=REGION_COLOR_MAP,
                theme=theme
            )
            fig3 = apply_theme(fig3, theme)

            g3 = dff.groupby("khu_vuc", as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
            g3["val_fmt"] = g3[value_col].apply(fmt_vn)
            rows3 = [{"label": str(r["khu_vuc"]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in g3.iterrows()]
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "pie_kv", "metric_label": metric_label})
        else:
            dff_pie = dff.copy()
            dff_pie["thang"] = dff_pie["thang_nam_vn"].dt.strftime("%m/%Y")
            fig3 = make_vn_donut(
                dff_pie,
                names="thang",
                values=value_col,
                title=f"Tỷ trọng {metric_label.lower()} theo tháng<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}",
                max_slices=12,
                color_map=None,
                theme=theme
            )
            fig3 = apply_theme(fig3, theme)

            g3 = dff_pie.groupby("thang", as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
            g3["val_fmt"] = g3[value_col].apply(fmt_vn)
            rows3 = [{"label": str(r["thang"]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in g3.iterrows()]
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "pie_month", "metric_label": metric_label})

        # Table formatting
        dff_table = dff.copy()
        for col in ["thang_nam", "thang_nam_vn"]:
            if col in dff_table.columns:
                dff_table[col] = (
                    pd.to_datetime(dff_table[col], errors="coerce")
                      .dt.strftime("%m/%Y")
                      .fillna("")
                )
        if "nam" in dff_table.columns:
            dff_table["nam"] = (
                pd.to_numeric(dff_table["nam"], errors="coerce")
                  .astype("Int64")
                  .astype(str)
                  .replace("<NA>", "")
            )
        num_cols = dff_table.select_dtypes(include="number").columns
        num_cols = [c for c in num_cols if c != "nam"]
        for c in num_cols:
            dff_table[c] = dff_table[c].apply(fmt_vn)

        style_cell = {"backgroundColor": "rgba(0,0,0,0)", "color": "var(--text)", "textAlign": "center", "padding": "10px", "border": "none"}
        style_header = {"backgroundColor": "rgba(0,0,0,0)", "color": "var(--muted)", "fontWeight": "900", "border": "none"}

        return (
            kpi1, kpi2, kpi3,
            fig1, fig2, fig3,
            dff_table.to_dict("records"),
            insight,
            style_cell, style_header,
            kpi1_store, kpi2_store, kpi3_store,
            fig1_store, fig2_store, fig3_store
        )

callbacks("dt", df_dt, "tong_doanh_thu")
callbacks("lh", df_lh, "tong_doanh_thu")
callbacks("hd", df_hd, "tong_so_cuoc")

# =========================
# ZOOM (SINGLE CALLBACK)
# =========================
@app.callback(
    Output("zoom-modal", "is_open"),
    Output("zoom-title", "children"),
    Output("zoom-kpi-render", "children"),
    Output("zoom-graph", "figure"),
    Output("zoom-graph", "style"),
    Output("zoom-detail", "children"),
    Output("zoom-detail", "style"),
    Output("zoom-target", "data"),

    Input({"type": "zoomable", "kind": ALL, "target": ALL}, "n_clicks"),
    Input("zoom-modal", "n_dismiss"),
    Input("zoom-graph", "clickData"),

    State("zoom-modal", "is_open"),
    State("zoom-target", "data"),
    State({"type": "zoom-store", "target": ALL}, "data"),
    State("theme", "data"),
    prevent_initial_call=True
)
def zoom_all(_clicks, n_dismiss, clickData, is_open, zoom_target, _all_store_data, theme):
    trig = ctx.triggered_id

    if trig == "zoom-modal":
        return False, no_update, no_update, no_update, {"display": "none"}, no_update, {"display": "none"}, None

    if trig == "zoom-graph":
        if not is_open or not zoom_target:
            raise PreventUpdate
        target = zoom_target.get("target")
        if not target:
            raise PreventUpdate

        store = _get_store_for_target(target, _all_store_data) or {}
        if not store or store.get("kind") != "fig":
            raise PreventUpdate

        meta = store.get("meta", {}) or {}
        rows = store.get("rows", []) or {}
        fig = store.get("figure", {}) or {}

        if not rows:
            detail = html.Div("Không có dữ liệu drill-down cho biểu đồ này.", style={"opacity": 0.85})
            return True, no_update, no_update, no_update, no_update, detail, {"display": "block"}, zoom_target

        pt = (clickData.get("points") or [{}])[0]
        x = pt.get("x", None)
        label = pt.get("label", None)

        region = None
        try:
            curve = pt.get("curveNumber", None)
            if curve is not None and isinstance(fig.get("data", []), list) and curve < len(fig["data"]):
                region = fig["data"][curve].get("name", None)
        except Exception:
            region = None

        month_label = safe_month_label(x) if x is not None else (str(label) if label else None)

        df = pd.DataFrame(rows)

        if "thang_label" in df.columns and month_label:
            df = df[df["thang_label"].astype(str) == str(month_label)]

        if "khu_vuc" in df.columns and region and region != "Khác":
            df2 = df[df["khu_vuc"].astype(str) == str(region)]
            if not df2.empty:
                df = df2

        if "label" in df.columns and label:
            df2 = df[df["label"].astype(str) == str(label)]
            if not df2.empty:
                df = df2

        if df.empty:
            detail = html.Div("Không tìm thấy dòng dữ liệu phù hợp cho điểm bạn click.", style={"opacity": 0.85})
            return True, no_update, no_update, no_update, no_update, detail, {"display": "block"}, zoom_target

        metric_label = meta.get("metric_label", "Giá trị")

        out_cols = []
        if "thang_label" in df.columns:
            out_cols.append(("Tháng", "thang_label"))
        if "khu_vuc" in df.columns:
            out_cols.append(("Khu vực", "khu_vuc"))
        if "metric_fmt" in df.columns:
            out_cols.append((metric_label, "metric_fmt"))
        elif "val_fmt" in df.columns:
            out_cols.append((metric_label, "val_fmt"))

        if not out_cols:
            out_cols = [(c, c) for c in df.columns[:6]]

        columns = [{"name": a, "id": b} for a, b in out_cols]
        data = df[[b for _, b in out_cols if b in df.columns]].to_dict("records")

        title = f"CHI TIẾT • {metric_label}"
        subtitle = []
        if month_label:
            subtitle.append(f"Tháng: {month_label}")
        if region:
            subtitle.append(f"Trace/KV: {region}")

        detail = dbc.Card(
            dbc.CardBody([
                html.Div(title, style={"fontSize": "15px", "fontWeight": "900"}),
                html.Div(" • ".join(subtitle), style={"opacity": 0.85, "marginBottom": "8px", "fontWeight": "800"}),
                dash_table.DataTable(
                    columns=columns,
                    data=data,
                    page_size=14,
                    style_table={"borderRadius": "16px", "overflow": "hidden", "border": "1px solid rgba(255,255,255,0.10)"},
                    style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": "var(--text)", "textAlign": "center", "padding": "10px", "border": "none"},
                    style_header={"backgroundColor": "rgba(0,0,0,0)", "color": "var(--muted)", "fontWeight": "900", "border": "none"},
                )
            ]),
            className="pro-card"
        )
        return True, no_update, no_update, no_update, no_update, detail, {"display": "block"}, zoom_target

    if isinstance(trig, dict) and trig.get("type") == "zoomable":
        nclick = None
        try:
            nclick = (ctx.triggered[0] or {}).get("value", None)
        except Exception:
            nclick = None
        if not nclick or int(nclick) <= 0:
            raise PreventUpdate

        kind = trig.get("kind")
        target = trig.get("target")
        if not target:
            raise PreventUpdate

        store = _get_store_for_target(target, _all_store_data) or {}
        if not store:
            raise PreventUpdate

        title = f"PHÓNG TO • {target}"
        detail_children = []
        detail_style = {"display": "none"}

        if store.get("kind") == "kpi" or kind == "kpi":
            rows = store.get("rows", []) or []
            cols = []
            data = []

            if rows and "value_fmt" in rows[0]:
                cols = [
                    {"name": "Khu vực", "id": "khu_vuc"},
                    {"name": "Giá trị", "id": "value_fmt"},
                    {"name": "%", "id": "pct_fmt"},
                ]
                data = []
                for r in rows:
                    data.append({
                        "khu_vuc": r.get("khu_vuc", ""),
                        "value_fmt": r.get("value_fmt", "0"),
                        "pct_fmt": f'{r.get("pct", 0):.1f}%',
                    })
            elif rows and "avg_fmt" in rows[0]:
                cols = [
                    {"name": "Khu vực", "id": "khu_vuc"},
                    {"name": "Trung bình", "id": "avg_fmt"},
                ]
                data = [{"khu_vuc": r.get("khu_vuc", ""), "avg_fmt": r.get("avg_fmt", "0")} for r in rows]

            kpi_card = dbc.Card(
                dbc.CardBody([
                    html.Div(store.get("title", "KPI"), className="kpi-title"),
                    html.Div(store.get("main", "0"), style={"fontSize": "44px", "fontWeight": "900", "marginTop": "6px"}),
                    html.Div(store.get("subtitle", ""), className="kpi-sub"),
                    html.Hr(style={"borderColor": "rgba(255,255,255,0.12)"}),
                    dash_table.DataTable(
                        columns=cols,
                        data=data,
                        page_size=12,
                        style_table={"borderRadius": "16px", "overflow": "hidden", "border": "1px solid rgba(255,255,255,0.10)"},
                        style_cell={"backgroundColor": "rgba(0,0,0,0)", "color": "var(--text)", "textAlign": "center", "padding": "10px", "border": "none"},
                        style_header={"backgroundColor": "rgba(0,0,0,0)", "color": "var(--muted)", "fontWeight": "900", "border": "none"},
                    ) if cols else html.Div("Không có breakdown theo khu vực.", style={"opacity": 0.8})
                ]),
                className="pro-card"
            )

            return True, title, kpi_card, {}, {"display": "none"}, [], {"display": "none"}, {"kind": "kpi", "target": target}

        fig_dict = store.get("figure", {})
        fig_dict = enhance_zoom_figure(fig_dict)
        detail_style = {"display": "block"}
        detail_children = html.Div("Click vào 1 điểm/cột để xem chi tiết.", style={"opacity": 0.8, "fontWeight": "800"})

        return True, title, None, fig_dict, {"display": "block", "height": "82vh"}, detail_children, detail_style, {"kind": "fig", "target": target}

    raise PreventUpdate

# =========================
# AI (FIXED & UPGRADED)
# =========================
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

def choose_dataset(question: str):
    q = norm_q(question)
    if "hop dong" in q or "so cuoc" in q or "cuoc" in q or "trip" in q:
        return "hd", df_hd, "tong_so_cuoc"
    if "loai hinh" in q:
        return "lh", df_lh, "tong_doanh_thu"
    return "dt", df_dt, "tong_doanh_thu"

def detect_metric_intent_ai(question: str, default_col: str):
    q = norm_q(question)
    if ("doanh thu" in q) or ("revenue" in q):
        return "tong_doanh_thu"
    if ("so cuoc" in q) or ("cuoc" in q) or ("trip" in q):
        return "tong_so_cuoc"
    return default_col

def detect_regions_in_question(question: str):
    q = norm_q(question)
    hits = []
    for r in ALL_REGIONS:
        rr = norm_q(r)
        if rr and rr in q:
            hits.append(r)
    if not hits:
        q2 = re.sub(r"[^a-z0-9\s]+", " ", q)
        q2 = re.sub(r"\s+", " ", q2).strip()
        for r in ALL_REGIONS:
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
    if any(k in q for k in ["xu huong", "trend", "theo thang", "tang", "giam", "so sanh", "vs"]):
        return "trend"
    return "total"

def answer_question(question: str, context: dict | None = None) -> str:
    context = context or {}
    q_raw = (question or "").strip()
    if not q_raw:
        return "Bạn hãy nhập câu hỏi (ví dụ: *Top 5 khu vực doanh thu cao nhất năm 2025*)."

    qn = norm_q(q_raw)

    def _extract_years(text: str):
        yrs = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
        yrs = [y for y in yrs if 2000 <= y <= 2100]
        return list(dict.fromkeys(yrs))

    def _extract_month_pairs(text: str):
        pairs = []
        for m, y in re.findall(r"(?:\b|t)(0?[1-9]|1[0-2])\s*[\/\-]\s*(20\d{2})\b", text, flags=re.I):
            pairs.append((int(m), int(y)))
        return list(dict.fromkeys(pairs))

    def _month_label(m: int, y: int):
        # IMPORTANT: dataset uses "MM/YYYY"
        return f"{m:02d}/{y}"

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

    def _pick_type_values(df: pd.DataFrame, col: str, q_norm: str):
        if not col or col not in df.columns:
            return None
        vals = [v for v in df[col].dropna().astype(str).unique().tolist() if str(v).strip()]
        if not vals:
            return None
        q2 = re.sub(r"[^a-z0-9\s]+", " ", q_norm)
        q2 = re.sub(r"\s+", " ", q2).strip()
        hits = []
        for v in vals:
            vn2 = re.sub(r"[^a-z0-9\s]+", " ", norm_q(v))
            vn2 = re.sub(r"\s+", " ", vn2).strip()
            if vn2 and vn2 in q2:
                hits.append(v)
        return list(dict.fromkeys(hits)) or None

    # dataset selection: explicit in question OR fallback to current menu
    default_menu = context.get("menu")
    if any(k in qn for k in ["hop dong", "loai hinh", "doanh thu", "so cuoc", "cuoc", "trip"]):
        ds_key, df, default_metric = choose_dataset(qn)
    else:
        if default_menu in ("dt", "lh", "hd"):
            if default_menu == "dt": ds_key, df, default_metric = "dt", df_dt, "tong_doanh_thu"
            elif default_menu == "lh": ds_key, df, default_metric = "lh", df_lh, "tong_doanh_thu"
            else: ds_key, df, default_metric = "hd", df_hd, "tong_so_cuoc"
        else:
            ds_key, df, default_metric = choose_dataset(qn)

    REV_COL = "tong_doanh_thu"
    TRIP_COL = "tong_so_cuoc"
    MONTH_COL = "thang_label"
    DATE_COL = "thang_nam_vn"
    YEAR_COL = "nam"
    REGION_COL = "khu_vuc"

    metric = detect_metric_intent_ai(q_raw, default_metric)
    metric_name = "Doanh thu" if metric == REV_COL else "Số cuốc"

    ctx_filters = context.get("filters") or {}
    ctx_year = ctx_filters.get("year")
    ctx_months = ctx_filters.get("months")
    ctx_regions = ctx_filters.get("dims") or ctx_filters.get("dim")

    if isinstance(ctx_regions, str):
        ctx_regions = [ctx_regions]

    years = _extract_years(qn)
    month_pairs = _extract_month_pairs(qn)

    range_labels = []
    mrange = re.search(r"(?:tu|từ)\s*(0?[1-9]|1[0-2])\s*[\/\-]\s*(20\d{2})\s*(?:den|đến)\s*(0?[1-9]|1[0-2])\s*[\/\-]\s*(20\d{2})", qn)
    if mrange:
        m1, y1, m2, y2 = map(int, mrange.groups())
        range_labels = _month_range_labels(m1, y1, m2, y2)

    months_labels = []
    if range_labels:
        months_labels = range_labels
    elif month_pairs:
        months_labels = [_month_label(m, y) for m, y in month_pairs]

    regions = detect_regions_in_question(q_raw)

    # apply context defaults if missing
    if not years and ctx_year is not None:
        try:
            years = [int(ctx_year)]
        except Exception:
            years = []
    if not months_labels and ctx_months:
        months_labels = ctx_months[:] if isinstance(ctx_months, list) else [ctx_months]
    if not regions and ctx_regions:
        regions = ctx_regions[:] if isinstance(ctx_regions, list) else [ctx_regions]

    type_col = LH_COL if ds_key == "lh" else (HD_COL if ds_key == "hd" else None)
    type_values = _pick_type_values(df, type_col, qn) if type_col else None
    if not type_values and type_col:
        tv = ctx_filters.get("type_filter")
        if tv:
            type_values = tv if isinstance(tv, list) else [tv]

    # filter df
    dff = df.copy()
    if YEAR_COL in dff.columns and years:
        dff = dff[dff[YEAR_COL].isin(years)]
    if MONTH_COL in dff.columns and months_labels:
        dff = dff[dff[MONTH_COL].isin(months_labels)]
    if REGION_COL in dff.columns and regions:
        dff = dff[dff[REGION_COL].isin(regions)]
    if type_col and type_values and type_col in dff.columns:
        dff = dff[dff[type_col].astype(str).isin([str(x) for x in type_values])]

    if dff.empty:
        scope = []
        if years: scope.append(f"năm {', '.join(map(str, years))}")
        if months_labels: scope.append(f"tháng {', '.join(months_labels)}")
        if regions: scope.append(f"khu vực {', '.join(regions)}")
        if type_values: scope.append(f"{type_col} ∈ {', '.join(map(str, type_values))}")
        s = ", ".join(scope) if scope else "bộ lọc hiện tại"
        return f"Không tìm thấy dữ liệu phù hợp với {s}. Bạn thử đổi/bớt điều kiện nhé."

    intent = detect_intent_advanced(q_raw)

    def _fmt_value(v):
        return fmt_vn(v)

    parts = []
    ds_name = {"dt": "Doanh thu", "lh": "Loại hình", "hd": "Hợp đồng"}.get(ds_key, ds_key.upper())
    parts.append(f"**Dataset:** {ds_name} • **Chỉ tiêu:** {metric_name}")

    f_desc = []
    if years: f_desc.append(f"Năm: {', '.join(map(str, years))}")
    if months_labels: f_desc.append(f"Tháng: {', '.join(months_labels)}")
    if regions: f_desc.append(f"Khu vực: {', '.join(regions)}")
    if type_values: f_desc.append(f"{type_col}: {', '.join(map(str, type_values))}")
    if f_desc:
        parts.append("**Bộ lọc:** " + " | ".join(f_desc))

    if any(k in qn for k in ["trung binh", "tb", "avg", "average"]):
        if REV_COL in dff.columns and TRIP_COL in dff.columns and any(k in qn for k in ["moi cuoc", "mỗi cuốc", "/cuoc", "per trip", "1 cuoc"]):
            rev = float(dff[REV_COL].sum())
            trips = float(dff[TRIP_COL].sum())
            val = rev / trips if trips else 0.0
            parts.append(f"**Doanh thu TB / cuốc:** {_fmt_value(val)}")
            return "\n\n".join(parts)
        if DATE_COL in dff.columns and metric in dff.columns:
            by_m = dff.groupby(DATE_COL)[metric].sum()
            val = float(by_m.mean())
            parts.append(f"**Trung bình theo tháng:** {_fmt_value(val)} (trên {len(by_m)} tháng)")
            return "\n\n".join(parts)

    if intent in ("top", "bottom"):
        n = 5
        mtop = re.search(r"\b(top|bottom)\s*(\d{1,2})\b", qn)
        if mtop:
            n = max(1, min(20, int(mtop.group(2))))
        ascending = (intent == "bottom")
        g = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=ascending).head(n)
        title = "Top" if not ascending else "Bottom"
        lines = [f"- {idx}: {_fmt_value(val)}" for idx, val in g.items()]
        parts.append(f"**{title} {n} khu vực theo {metric_name}:**\n" + "\n".join(lines))
        return "\n\n".join(parts)

    if intent == "trend":
        if DATE_COL in dff.columns and metric in dff.columns:
            s = dff.groupby(DATE_COL)[metric].sum().sort_index()
            lines = []
            if len(s) <= 12:
                show = s
            else:
                show = pd.concat([s.head(6), s.tail(6)])
            for d, v in show.items():
                lab = pd.Timestamp(d).strftime("%m/%Y")
                lines.append(f"- {lab}: {_fmt_value(v)}")
            parts.append("**Xu hướng theo tháng:**\n" + "\n".join(lines))
            if len(s) >= 2:
                last, prev = float(s.iloc[-1]), float(s.iloc[-2])
                diff = last - prev
                pct = (diff / prev * 100.0) if prev else None
                if pct is not None:
                    parts.append(f"**Tháng gần nhất so với tháng trước:** {_fmt_value(diff)} ({pct:+.1f}%)")
                else:
                    parts.append(f"**Tháng gần nhất so với tháng trước:** {_fmt_value(diff)}")
            return "\n\n".join(parts)

    if intent == "share":
        g = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=False)
        total = float(g.sum())
        lines = []
        for idx, val in g.head(8).items():
            pct = (float(val) / total * 100.0) if total else 0.0
            lines.append(f"- {idx}: {_fmt_value(val)} ({pct:.1f}%)")
        parts.append("**Tỷ trọng theo khu vực:**\n" + "\n".join(lines))
        return "\n\n".join(parts)

    total = float(dff[metric].sum()) if metric in dff.columns else 0.0
    parts.append(f"**Tổng {metric_name}:** {_fmt_value(total)}")

    if REGION_COL in dff.columns and not detect_regions_in_question(q_raw):
        g = dff.groupby(REGION_COL)[metric].sum().sort_values(ascending=False).head(5)
        lines = [f"- {idx}: {_fmt_value(val)}" for idx, val in g.items()]
        parts.append("**Top 5 khu vực (tham khảo):**\n" + "\n".join(lines))

    parts.append('\n*Gợi ý:* "So sánh doanh thu 2024 vs 2025", "Top 10 số cuốc 01/2026", "Xu hướng từ 01/2025 đến 06/2025", "Tỷ trọng theo khu vực".')
    return "\n\n".join(parts)

@app.callback(
    Output("ai-chat-history", "data"),
    Output("ai-output", "children"),
    Input("ai-send", "n_clicks"),
    Input("ai-clear", "n_clicks"),
    State("ai-input", "value"),
    State("ai-chat-history", "data"),
    State("menu", "data"),
    State("page", "data"),
    State("filters-dt-p1", "data"),
    State("filters-dt-p2", "data"),
    State("filters-lh-p1", "data"),
    State("filters-lh-p2", "data"),
    State("filters-hd-p1", "data"),
    State("filters-hd-p2", "data"),
    prevent_initial_call=True
)
def ai_chat(n_send, n_clear, question, history,
            menu, page,
            f_dt_p1, f_dt_p2, f_lh_p1, f_lh_p2, f_hd_p1, f_hd_p2):

    trigger = ctx.triggered_id
    history = history or []

    if trigger == "ai-clear":
        return [], html.Div("✅ Đã xoá lịch sử chat.", style={"opacity": 0.9})

    if trigger != "ai-send":
        raise PreventUpdate

    q_raw = (question or "").strip()
    if not q_raw:
        return history, html.Div("Bạn hãy nhập câu hỏi (có thể nhập nhiều dòng / nhiều câu).")

    try:
        p = int(page) if page is not None else 1
    except Exception:
        p = 1

    filters = {}
    if menu == "dt" and p == 1:
        filters = f_dt_p1 or {}
    elif menu == "dt" and p == 2:
        filters = f_dt_p2 or {}
    elif menu == "lh" and p == 1:
        filters = f_lh_p1 or {}
    elif menu == "lh" and p == 2:
        filters = f_lh_p2 or {}
    elif menu == "hd" and p == 1:
        filters = f_hd_p1 or {}
    elif menu == "hd" and p == 2:
        filters = f_hd_p2 or {}

    context = {"menu": menu, "page": p, "filters": filters}

    def split_questions(raw: str):
        raw = raw.replace(";", "\n")
        raw = re.sub(r"[?]+", "?\n", raw)
        parts = [x.strip() for x in raw.splitlines() if x.strip()]
        return parts[:8]

    questions = split_questions(q_raw)

    answers = []
    for q in questions:
        ans = answer_question(q, context=context)
        answers.append(ans)
        history.append({"q": q, "a": ans, "ts": datetime.now().isoformat(timespec="seconds")})

    md_lines = []
    for item in history[-6:]:
        md_lines.append(f"**Bạn:** {item.get('q','')}\n\n{item.get('a','')}\n\n---")

    header = ""
    if len(questions) > 1:
        header = f"✅ Đã trả lời {len(questions)} câu hỏi trong 1 lần gửi.\n\n"

    return history, dcc.Markdown(header + "\n".join(md_lines), link_target="_blank")

@app.callback(
    Output("ai-input", "value"),
    Input("ai-send", "n_clicks"),
    prevent_initial_call=True
)
def clear_ai_input(_):
    return ""

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
