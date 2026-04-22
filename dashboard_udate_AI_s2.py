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

# =========================
# TIMEZONE: VIETNAM
# =========================
VN_TZ = "Asia/Ho_Chi_Minh"

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

# =========================
# NUMBER FORMAT: VIETNAM (.)
# =========================
def fmt_vn(n) -> str:
    try:
        if n is None or (isinstance(n, float) and pd.isna(n)):
            return "0"
        return f"{float(n):,.0f}".replace(",", ".")
    except Exception:
        return str(n)

# =========================
# HELPERS: detect column names safely
# =========================
def find_col(df: pd.DataFrame, candidates):
    cols = list(df.columns)
    norm = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        key = str(cand).strip().lower()
        if key in norm:
            return norm[key]
    return None

# =========================
# HELPERS: normalize + map categories
# =========================
def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)

    # FIX: dọn ký tự ẩn hay gặp trong Excel/copy-paste (NBSP/BOM/zero-width/newline)
    s = (s.replace("\u200b", " ")   # zero-width space
           .replace("\ufeff", " ")  # BOM
           .replace("\xa0", " ")    # NBSP
           .replace("\t", " ")
           .replace("\r", " ")
           .replace("\n", " "))

    s = s.strip().lower()

    # FIX: chữ "đ" không tách dấu theo NFKD (nếu không sẽ thành "hop ong")
    s = s.replace("đ", "d")

    # FIX: chuẩn hóa viết tắt phổ biến trước khi bỏ dấu
    s = s.replace("hđ", "hop dong").replace("hd", "hop dong")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # bỏ dấu

    # FIX: bỏ ký tự đặc biệt để tránh “Hợp đồng thường” bị rơi sang Khác do dấu câu/ẩn
    s = re.sub(r"[^a-z0-9\s]+", " ", s)

    s = re.sub(r"\s+", " ", s).strip()
    return s

# 3 loại hình chuẩn
LH_CANON = ["Xe Công ty", "Xe thương quyền hợp tác", "Xe thương quyền trả góp"]
# 3 loại hợp đồng chuẩn
HD_CANON = ["Hợp đồng thường", "Tuyến chiến lược", "Xe tiện chuyến"]

LH_MAP = {
    "xe cong ty": "Xe Công ty",
    "xe thuong quyen hop tac": "Xe thương quyền hợp tác",
    "xe thuong quyen tra gop": "Xe thương quyền trả góp",
}

# FIX: mở rộng mapping hợp đồng để tránh “Hợp đồng thường” bị rơi sang nhãn khác
HD_MAP = {
    # chuẩn
    "hop dong thuong": "Hợp đồng thường",
    "tuyen chien luoc": "Tuyến chiến lược",
    "xe tien chuyen": "Xe tiện chuyến",

    # biến thể hay gặp
    "hop dong thong thuong": "Hợp đồng thường",
    "hop dong binh thuong": "Hợp đồng thường",
    "hop dong thuong le": "Hợp đồng thường",
    "hop dong thuong quy": "Hợp đồng thường",
    "hop dong thuong (thuong)": "Hợp đồng thường",
    "hop dong  thuong": "Hợp đồng thường",
    "hop dong thuong ": "Hợp đồng thường",
    "hd thuong": "Hợp đồng thường",

    # FIX: typo trong data thực tế
    "tuyen chuyen luoc": "Tuyến chiến lược",
}

def map_to_canon(series: pd.Series, mapping: dict) -> pd.Series:
    s = series.astype(str).map(norm_text)

    # FIX: normalize luôn key của mapping để khớp 100% dù mapping key/giá trị có khác format
    mapping_norm = {norm_text(k): v for k, v in mapping.items()}
    out = s.map(mapping_norm)

    # FIX: fallback theo từ khoá (giải quyết case "Hợp đồng thường" bị ký tự ẩn)
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
    # đảm bảo luôn ở đầu tháng 00:00 (tránh lệch giờ nếu có)
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

DARK_BG = "#1e1e2f"
LIGHT_BG = "#ffffff"

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
# KPI helpers: hiển thị breakdown theo khu vực
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
        html.Div(main_text, style={"fontSize": "28px", "fontWeight": "900", "lineHeight": "1.1"}),
        html.Div(subtitle_text, style={"fontSize": "12px", "opacity": 0.85, "marginTop": "4px,","fontWeight": "700"}) if subtitle_text else None,
        html.Div(extra_lines, style={"marginTop": "6px"}) if extra_lines else None
    ])

# ==========================================================
# FIX: CHỮ TRONG MENU DROPDOWN BỊ TRẮNG
# ==========================================================
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

# =========================================================
# NEW: PRO NAV BUTTONS (center screen, subtle tech look)
# =========================================================
PAGINATION_PRO_CSS = """
/* === Floating page navigation (‹ ›) — slim tech & professional === */
.page-nav-btn{
  position:fixed !important;
  top:50% !important;
  transform:translateY(-50%) !important;

  /* always above charts/loading */
  z-index:9999 !important;

  width:48px;
  height:48px;
  padding:0 !important;
  border-radius:999px;

  display:flex !important;
  align-items:center !important;
  justify-content:center !important;

  /* subtle / faint when idle */
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

/* glow + brighten on hover */
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

/* placement */
.page-nav-left{ left:16px !important; }
.page-nav-right{ right:16px !important; }

/* mobile */
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

# =========================================================
# NEW: AI CHAT UI CSS (bubble + modern)
# =========================================================
AI_CHAT_CSS = """
.ai-wrap{ margin-top: 6px; }
.ai-bubble{
  border-radius: 16px;
  padding: 10px 12px;
  margin-bottom: 10px;
  box-shadow: 0 10px 26px rgba(0,0,0,0.20);
  border: 1px solid rgba(120,120,180,0.22);
}
.ai-user{
  background: linear-gradient(135deg, rgba(40,45,85,0.55), rgba(25,25,45,0.55));
}
.ai-bot{
  background: linear-gradient(135deg, rgba(10,30,60,0.70), rgba(10,18,35,0.70));
  border: 1px solid rgba(0,200,255,0.18);
}
.ai-meta{
  font-weight: 900;
  opacity: 0.88;
  font-size: 12px;
  letter-spacing: .4px;
}
.ai-time{
  font-size: 11px;
  opacity: 0.65;
  margin-top: 4px;
}
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
.ai-chip:hover{
  background: rgba(40,40,70,0.45);
}
"""

# ==========================================================
# UI STYLE cho dropdown theo theme
# ==========================================================
def dropdown_style(theme: str):
    if theme == "light":
        return {
            "backgroundColor": "#ffffff",
            "color": "#111",
            "borderRadius": "14px",
            "border": "1px solid #d6d6d6",
            "minHeight": "46px",
            "fontSize": "15px",
            "fontWeight": "700",
        }
    return {
        "backgroundColor": "#141423",
        "color": "white",
        "borderRadius": "14px",
        "border": "1px solid #3b3b57",
        "minHeight": "46px",
        "fontSize": "15px",
        "fontWeight": "700",
    }

def dropdown_container_style(theme: str):
    if theme == "light":
        return {
            "backgroundColor": "#ffffff",
            "padding": "10px 12px",
            "borderRadius": "16px",
            "border": "1px solid #e6e6e6",
            "boxShadow": "0 8px 18px rgba(0,0,0,0.06)",
        }
    return {
        "backgroundColor": "#0f1020",
        "padding": "10px 12px",
        "borderRadius": "16px",
        "border": "1px solid #2b2b47",
        "boxShadow": "0 8px 22px rgba(90,80,255,0.12)",
    }

def filter_label_style(theme: str):
    return {
        "fontWeight": "900",
        "letterSpacing": "0.5px",
        "opacity": 0.9,
        "marginBottom": "6px",
        "fontSize": "12px",
        "textTransform": "uppercase",
        "color": "#111" if theme == "light" else "white"
    }

# ==========================================================
# FIX: trục thời gian khớp điểm (xperiod) + ticklabelmode=period
# ==========================================================
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

def apply_theme(fig, theme):
    fig = apply_time_axis(fig)
    # Legend isolate chuyên nghiệp
    fig.update_layout(legend_itemclick="toggleothers", legend_itemdoubleclick="toggle")
    if theme == "dark":
        fig.update_layout(
            plot_bgcolor=DARK_BG,
            paper_bgcolor=DARK_BG,
            font_color="white",
            xaxis=dict(gridcolor="#333"),
            yaxis=dict(gridcolor="#333"),
            legend_title_text="",
            hovermode="x unified"
        )
    else:
        fig.update_layout(
            plot_bgcolor=LIGHT_BG,
            paper_bgcolor=LIGHT_BG,
            font_color="black",
            xaxis=dict(gridcolor="#ddd"),
            yaxis=dict(gridcolor="#ddd"),
            legend_title_text="",
            hovermode="x unified"
        )
    return fig

# ==========================================================
# FIX: title không bị cắt + tăng margin top theo số dòng
# ==========================================================
def apply_chart_title(fig, title: str, top: int = 120, y_title: str = None):
    # tăng top theo số dòng <br> để tránh bị cắt chữ
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
            font=dict(size=16)
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

# ==========================================================
# NEW: line chart labels gọn (ít điểm => hiện hết, nhiều điểm => chỉ hiện điểm cuối)
# ==========================================================
def _add_line_point_labels(fig, show_all_if_points_le=10):
    try:
        for tr in fig.data:
            t = getattr(tr, "type", "")
            if t not in (None, "scatter"):
                continue
            ys = getattr(tr, "y", None)
            xs = getattr(tr, "x", None)
            if ys is None:
                continue
            n = len(ys) if hasattr(ys, "__len__") else 0
            if n <= 0:
                continue

            text_vals = [""] * n
            if n <= show_all_if_points_le:
                # ít điểm => show hết
                for i, y in enumerate(ys):
                    text_vals[i] = fmt_vn(y)
            else:
                # nhiều điểm => chỉ show điểm cuối
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

        # nới top đủ để label không đụng title
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
    # pin các khu vực cần giữ (vd Cần Thơ)
    for k in keep_cats:
        if k in tmp[cat_col].unique().tolist() and k not in top_cats:
            top_cats.append(k)

    new_col = f"{cat_col}__show"
    tmp[new_col] = tmp[cat_col].where(tmp[cat_col].isin(top_cats), other_label)
    return tmp, new_col

def make_vn_donut(df: pd.DataFrame, names: str, values: str, title: str, max_slices: int = 8, color_map=None):
    dff = df.copy()
    if dff.empty:
        fig = px.pie(dff, names=names, values=values, hole=0.45)
        fig = apply_theme(fig, "dark")
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
    fig = apply_theme(fig, "dark")
    fig = apply_chart_title(fig, title, top=135)
    return fig

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
    # Ưu tiên đọc từ ctx.states (ổn định, không phụ thuộc thứ tự ALL)
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

    # page 2 has region filter (dims)
    if page == 2 and dims and "khu_vuc" in dff.columns:
        dff = dff[dff["khu_vuc"].astype(str).isin([str(x) for x in dims])]

    if year_val is not None and "nam" in dff.columns:
        dff = dff[dff["nam"] == int(year_val)]

    if months and "thang_label" in dff.columns:
        dff = dff[dff["thang_label"].isin(months)]

    # type filter (lh/hd)
    if key == "lh" and type_filter and LH_COL in dff.columns:
        dff = dff[dff[LH_COL].astype(str).isin(type_filter)]
    if key == "hd" and type_filter and HD_COL in dff.columns:
        dff = dff[dff[HD_COL].astype(str).isin(type_filter)]

    return dff.copy()

def _make_summary_for_export(dff: pd.DataFrame, menu: str) -> pd.DataFrame:
    if dff is None or dff.empty:
        return pd.DataFrame()

    # ưu tiên sort đúng theo thời gian
    time_col = "thang_nam_vn" if "thang_nam_vn" in dff.columns else None
    group_cols = []
    if time_col:
        group_cols.append(time_col)
    elif "thang_label" in dff.columns:
        group_cols.append("thang_label")

    if "khu_vuc" in dff.columns:
        group_cols.append("khu_vuc")

    # chọn cột metric phù hợp + thêm cột phụ nếu có
    agg = {}
    if menu in ["dt", "lh"]:
        if "tong_doanh_thu" in dff.columns:
            agg["tong_doanh_thu"] = "sum"
        if "tong_so_cuoc" in dff.columns:
            agg["tong_so_cuoc"] = "sum"
    else:  # hd
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
# APP
# =========================
FA_CDN = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FA_CDN], suppress_callback_exceptions=True)

# =========================================================
# ICONS (Font Awesome) — FIX lỗi html.Svg
# =========================================================
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

# inject CSS
app.index_string = app.index_string.replace(
    "</head>",
    f"<style>{DROPDOWN_FIX_CSS}\n{PAGINATION_PRO_CSS}\n{AI_CHAT_CSS}</style></head>"
)

# ===== zoom store targets (always exist) =====
ZOOM_TARGETS = []
for p in ["dt", "lh", "hd"]:
    # KPI
    ZOOM_TARGETS += [f"{p}-p1-kpi1", f"{p}-p1-kpi2", f"{p}-p1-kpi3"]
    ZOOM_TARGETS += [f"{p}-kpi1", f"{p}-kpi2", f"{p}-kpi3"]
    # P1 figs
    ZOOM_TARGETS += [f"{p}-p1-line-kv", f"{p}-p1-line", f"{p}-p1-bar", f"{p}-p1-pie"]
    # P2 figs
    ZOOM_TARGETS += [f"{p}-p2-line", f"{p}-p2-bar", f"{p}-p2-pie"]

def _zoomable_wrap(kind: str, target: str):
    # kind: "kpi" | "fig"
    return {"type": "zoomable", "kind": kind, "target": target}

app.layout = dbc.Container(fluid=True, children=[
    dcc.Store(id="menu", data="dt"),
    dcc.Store(id="page", data=1),
    dcc.Store(id="theme", data="dark"),

    # ===== Export filters (always exist) =====
    dcc.Store(id="filters-dt-p1", data={}),
    dcc.Store(id="filters-dt-p2", data={}),
    dcc.Store(id="filters-lh-p1", data={}),
    dcc.Store(id="filters-lh-p2", data={}),
    dcc.Store(id="filters-hd-p1", data={}),
    dcc.Store(id="filters-hd-p2", data={}),

    dcc.Store(id="ai-chat-history", data=[]),
    dcc.Interval(id="refresh-meta", interval=30 * 1000, n_intervals=0),

    # ===== Top bar =====
    dbc.Row([
        dbc.Col(
            dbc.Button([ICON_MENU], id="open-menu", color="secondary", outline=True, className="me-2"),
            width="auto"
        ),
        dbc.Col(
            html.Div(
                id="top-title",
                style={"fontSize": "18px", "fontWeight": "700", "letterSpacing": "1px"}
            )
        ),
        dbc.Col(
            dbc.Button([ICON_THEME, html.Span(" Theme", className="ms-2")], id="toggle-theme", color="secondary", className="float-end"),
            width="auto"
        )
    ], className="my-2 align-items-center"),

    # Card last updated + download
    dbc.Row([
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div("DỮ LIỆU CẬP NHẬT LÚC", style={"fontWeight": "700", "opacity": 0.85}),
                    dbc.Row([
                        dbc.Col(html.Div(id="data-updated-at", style={"fontSize": "18px", "fontWeight": "800"})),
                        dbc.Col(
                            dbc.Button([ICON_DL, html.Span(" Tải Excel")], id="btn-download-excel", color="secondary",
                                       outline=True, className="float-end"),
                            width="auto"
                        )
                    ], className="g-2 align-items-center")
                ]),
                style={"border": "1px solid #3b3b57", "boxShadow": "0 0 20px rgba(90,80,255,0.15)"}
            ),
            md=6
        )
    ], className="mb-2"),

    # ===== Sidebar =====
    dbc.Offcanvas(
        id="sidebar",
        title=html.Div([ICON_CHART, html.Span("  DASHBOARD MENU")]),
        is_open=False,
        placement="start",
        scrollable=True,
        style={"backgroundColor": DARK_BG, "color": "white"},
        children=[
            html.Div("Chọn dashboard:", style={"fontWeight": "700", "marginBottom": "10px"}),
            dbc.Button("DOANH THU", id="btn-dt", color="primary", className="w-100 mb-2"),
            dbc.Button("LOẠI HÌNH", id="btn-lh", color="warning", className="w-100 mb-2"),
            dbc.Button("HỢP ĐỒNG", id="btn-hd", color="success", className="w-100 mb-2"),
            html.Hr(style={"borderColor": "#444"}),
            html.Div("Điều hướng trang:", style={"fontWeight": "700", "marginBottom": "10px"}),
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
                    "opacity": 0.9,
                    "fontSize": "14px",
                    "fontWeight": "600",
                    "whiteSpace": "pre-line",
                },
            ),
        ]
    ),

    # ===== AI box =====
    dbc.Offcanvas(
        id="ai-box",
        title=html.Div([ICON_BOT, html.Span("  AI INSIGHTS")]),
        is_open=False,
        placement="end",
        scrollable=True,
        style={"backgroundColor": DARK_BG, "color": "white", "width": "420px"},
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
                style={"backgroundColor": "#141423", "color": "white", "border": "1px solid #3b3b57", "borderRadius":"14px"}
            ),
            dbc.Row([
                dbc.Col(dbc.Button([ICON_SEND, html.Span(" Gửi")], id="ai-send", color="info", className="mt-2 w-100")),
                dbc.Col(dbc.Button([ICON_TRASH, html.Span(" Xoá chat")], id="ai-clear", color="secondary", outline=True, className="mt-2 w-100")),
            ], className="g-2"),
            html.Div(
                [
                    html.Span("Gợi ý nhanh:", style={"fontWeight":"900","opacity":0.85,"display":"block","marginTop":"10px"}),
                    html.Div([
                        html.Span("Top 5 khu vực doanh thu cao nhất năm 2025", className="ai-chip"),
                        html.Span("Tỷ trọng doanh thu theo khu vực năm 2025", className="ai-chip"),
                        html.Span("Xu hướng doanh thu theo tháng năm 2025", className="ai-chip"),
                        html.Span("Bottom 3 khu vực số cuốc thấp nhất 2025", className="ai-chip"),
                    ], className="ai-wrap")
                ],
                style={"marginTop":"6px"}
            ),
            html.Hr(style={"borderColor": "#444"}),
            dcc.Loading(html.Div(id="ai-output"), type="default")
        ]
    ),

    dcc.Loading(html.Div(id="content"), type="default"),

    # === New pro page nav buttons (center) ===
    dbc.Button(ICON_CHEV_L, id="prev-page", className="page-nav-btn page-nav-left", title="Trang trước",
               style={"position":"fixed","top":"50%","left":"16px","zIndex":9999}),
    dbc.Button(ICON_CHEV_R, id="next-page", className="page-nav-btn page-nav-right", title="Trang sau",
               style={"position":"fixed","top":"50%","right":"16px","zIndex":9999}),

    dbc.Button(
        ICON_BOT,
        id="open-ai",
        color="info",
        className="position-fixed end-0 me-4",
        style={"bottom": "88px", "borderRadius": "999px", "width": "56px", "height": "56px",
               "boxShadow": "0 0 22px rgba(0,255,255,0.25)", "fontSize": "20px"}
    ),

    # ===== ZOOM MODAL =====
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
                        config={"displayModeBar": True, "scrollZoom": True},
                        style={"display": "none", "height": "82vh"}
                    ),
                    html.Hr(style={"borderColor": "#444", "marginTop": "10px", "marginBottom": "10px"}),
                    html.Div(id="zoom-detail", style={"display": "none"})
                ])),
                style={"padding": "10px"}
            )
        ],
    ),

    dcc.Store(id="zoom-target", data=None),

    # ===== Zoom stores (always exist) =====
    html.Div([dcc.Store(id={"type": "zoom-store", "target": t}, data=None) for t in ZOOM_TARGETS], style={"display": "none"}),

    dcc.Download(id="download-excel")
])

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
        # chọn đúng filters theo menu/page hiện tại
        filt = {}
        if menu == "dt" and int(page) == 1: filt = f_dt_p1 or {}
        if menu == "dt" and int(page) == 2: filt = f_dt_p2 or {}
        if menu == "lh" and int(page) == 1: filt = f_lh_p1 or {}
        if menu == "lh" and int(page) == 2: filt = f_lh_p2 or {}
        if menu == "hd" and int(page) == 1: filt = f_hd_p1 or {}
        if menu == "hd" and int(page) == 2: filt = f_hd_p2 or {}

        dff = _apply_export_filters(menu, int(page), filt)
        summary = _make_summary_for_export(dff, menu)

        # sheet FILTERS để “khớp” 100% theo trạng thái hiện tại
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
    Output("menu","data"),
    Input("btn-dt","n_clicks"),
    Input("btn-lh","n_clicks"),
    Input("btn-hd","n_clicks"),
    prevent_initial_call=True
)
def switch_menu(a,b,c):
    if ctx.triggered_id == "btn-lh": return "lh"
    if ctx.triggered_id == "btn-hd": return "hd"
    return "dt"

@app.callback(
    Output("page","data"),
    Input("next-page","n_clicks"),
    Input("prev-page","n_clicks"),
    Input("go-page-1","n_clicks"),
    Input("go-page-2","n_clicks"),
    State("page","data"),
    prevent_initial_call=True
)
def switch_page(n1,n2,g1,g2,p):
    if ctx.triggered_id == "go-page-1":
        return 1
    if ctx.triggered_id == "go-page-2":
        return 2
    return 2 if ctx.triggered_id=="next-page" else 1

@app.callback(
    Output("theme","data"),
    Input("toggle-theme","n_clicks"),
    State("theme","data"),
    prevent_initial_call=True
)
def toggle_theme(n, theme):
    return "light" if theme=="dark" else "dark"

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
            html.Div([
                html.Div("Loại hình", style=filter_label_style("dark")),
                dcc.Dropdown(
                    id="lh-type-p1",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hình",
                    style=dropdown_style("dark"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"lh-type-p1-wrap"}, style=dropdown_container_style("dark")),
            md=4
        )
    elif prefix == "hd":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hợp đồng", style=filter_label_style("dark")),
                dcc.Dropdown(
                    id="hd-type-p1",
                    options=HD_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hợp đồng",
                    style=dropdown_style("dark"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"hd-type-p1-wrap"}, style=dropdown_container_style("dark")),
            md=4
        )

    return dbc.Container(fluid=True, children=[
        html.H3(title, className="text-center my-3"),

        dbc.Row([
            dbc.Col(
                html.Div([
                    html.Div("Năm", style=filter_label_style("dark")),
                    dcc.Dropdown(
                        id=year_id,
                        options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                        value=None,
                        multi=False,
                        placeholder="Chọn năm",
                        style=dropdown_style("dark"),
                        clearable=True
                    )
                ], id={"type":"filter-wrap","id":f"{prefix}-year-wrap"}, style=dropdown_container_style("dark")),
                md=3
            ),
            dbc.Col(
                html.Div([
                    html.Div("Tháng", style=filter_label_style("dark")),
                    dcc.Dropdown(
                        id=f"{prefix}-month",
                        options=[{"label": m, "value": m} for m in MONTH_OPTIONS_ALL],
                        multi=True,
                        placeholder="Chọn tháng",
                        style=dropdown_style("dark"),
                        clearable=True
                    )
                ], id={"type":"filter-wrap","id":f"{prefix}-month-wrap"}, style=dropdown_container_style("dark")),
                md=5
            ),
            extra_filter if extra_filter is not None else dbc.Col(html.Div(), md=4),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(
                html.Div(
                    dbc.Card(dbc.CardBody([html.H6("TỔNG"), html.Div(id=f"{prefix}-p1-kpi1")])) ,
                    id=_zoomable_wrap("kpi", f"{prefix}-p1-kpi1"), n_clicks=0, style={"cursor": "pointer"}
                ),
                md=4
            ),
            dbc.Col(
                html.Div(
                    dbc.Card(dbc.CardBody([html.H6("SỐ CUỐC"), html.Div(id=f"{prefix}-p1-kpi2")])) ,
                    id=_zoomable_wrap("kpi", f"{prefix}-p1-kpi2"), n_clicks=0, style={"cursor": "pointer"}
                ),
                md=4
            ),
            dbc.Col(
                html.Div(
                    dbc.Card(dbc.CardBody([html.H6("TRUNG BÌNH"), html.Div(id=f"{prefix}-p1-kpi3")])) ,
                    id=_zoomable_wrap("kpi", f"{prefix}-p1-kpi3"), n_clicks=0, style={"cursor": "pointer"}
                ),
                md=4
            ),
        ], className="mb-4"),

        dbc.Row([
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p1-line-kv"),
                         id=_zoomable_wrap("fig", f"{prefix}-p1-line-kv"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=12
            ),
        ], className="mb-3"),

        dbc.Row([
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p1-line"),
                         id=_zoomable_wrap("fig", f"{prefix}-p1-line"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=6
            ),
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p1-bar"),
                         id=_zoomable_wrap("fig", f"{prefix}-p1-bar"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=6
            ),
        ]),
        dbc.Row([
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p1-pie"),
                         id=_zoomable_wrap("fig", f"{prefix}-p1-pie"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=6
            ),
        ]),
    ])

def page_2(prefix, title, df, dim):
    extra_filter = None
    year_id = f"{prefix}-year-p2"

    if prefix == "lh":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hình", style=filter_label_style("dark")),
                dcc.Dropdown(
                    id="lh-type-p2",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hình",
                    style=dropdown_style("dark"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"lh-type-p2-wrap"}, style=dropdown_container_style("dark")),
            md=4
        )
    elif prefix == "hd":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hợp đồng", style=filter_label_style("dark")),
                dcc.Dropdown(
                    id="hd-type-p2",
                    options=HD_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hợp đồng",
                    style=dropdown_style("dark"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"hd-type-p2-wrap"}, style=dropdown_container_style("dark")),
            md=4
        )

    return dbc.Container(fluid=True, children=[
        html.H3(title, className="text-center my-3"),
        html.Div(id=f"{prefix}-insight", className="text-center mb-3",
                 style={"fontSize":"18px","fontWeight":"bold"}),

        dbc.Row([
            dbc.Col(
                html.Div([
                    html.Div("Khu vực", style=filter_label_style("dark")),
                    dcc.Dropdown(
                        id=f"{prefix}-dim",
                        options=[{"label":x,"value":x} for x in sorted(df[dim].astype(str).unique())],
                        value=[sorted(df[dim].astype(str).unique())[0]],
                        multi=True,
                        style=dropdown_style("dark"),
                        clearable=True
                    )
                ], id={"type":"filter-wrap","id":f"{prefix}-dim-wrap"}, style=dropdown_container_style("dark")),
                md=3
            ),
            dbc.Col(
                html.Div([
                    html.Div("Năm", style=filter_label_style("dark")),
                    dcc.Dropdown(
                        id=year_id,
                        options=[{"label": str(y), "value": int(y)} for y in YEAR_OPTIONS_ALL],
                        value=None,
                        multi=False,
                        placeholder="Chọn năm",
                        style=dropdown_style("dark"),
                        clearable=True
                    )
                ], id={"type":"filter-wrap","id":f"{prefix}-year-p2-wrap"}, style=dropdown_container_style("dark")),
                md=3
            ),
            dbc.Col(
                html.Div([
                    html.Div("Tháng", style=filter_label_style("dark")),
                    dcc.Dropdown(
                        id=f"{prefix}-month-p2",
                        options=[{"label": m, "value": m} for m in MONTH_OPTIONS_ALL],
                        multi=True,
                        placeholder="Chọn tháng",
                        style=dropdown_style("dark"),
                        clearable=True
                    )
                ], id={"type":"filter-wrap","id":f"{prefix}-month-p2-wrap"}, style=dropdown_container_style("dark")),
                md=4
            ),
            extra_filter if extra_filter is not None else dbc.Col(html.Div(), md=2),
        ], className="mb-3 g-2"),

        dbc.Row([
            dbc.Col(
                html.Div(
                    dbc.Card(dbc.CardBody([html.H6("TỔNG"), html.Div(id=f"{prefix}-kpi1")])) ,
                    id=_zoomable_wrap("kpi", f"{prefix}-kpi1"), n_clicks=0, style={"cursor":"pointer"}
                ),
                md=4
            ),
            dbc.Col(
                html.Div(
                    dbc.Card(dbc.CardBody([html.H6("SỐ CUỐC"), html.Div(id=f"{prefix}-kpi2")])) ,
                    id=_zoomable_wrap("kpi", f"{prefix}-kpi2"), n_clicks=0, style={"cursor":"pointer"}
                ),
                md=4
            ),
            dbc.Col(
                html.Div(
                    dbc.Card(dbc.CardBody([html.H6("TRUNG BÌNH"), html.Div(id=f"{prefix}-kpi3")])) ,
                    id=_zoomable_wrap("kpi", f"{prefix}-kpi3"), n_clicks=0, style={"cursor":"pointer"}
                ),
                md=4
            ),
        ], className="mb-4"),

        dbc.Row([
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p2-line"),
                         id=_zoomable_wrap("fig", f"{prefix}-p2-line"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=6
            ),
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p2-bar"),
                         id=_zoomable_wrap("fig", f"{prefix}-p2-bar"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=6
            ),
        ]),
        dbc.Row([
            dbc.Col(
                html.Div(dcc.Graph(id=f"{prefix}-p2-pie"),
                         id=_zoomable_wrap("fig", f"{prefix}-p2-pie"), n_clicks=0, style={"cursor":"zoom-in"}),
                md=6
            ),
        ]),

        dash_table.DataTable(
            id=f"{prefix}-table",
            page_action=("none" if prefix in ["lh", "hd"] else "native"),
            page_size=12,
            style_header={"backgroundColor":"#222","color":"white"},
            style_cell={"backgroundColor":DARK_BG,"color":"white","textAlign":"center"}
        ),
    ])

@app.callback(
    Output("content","children"),
    Input("menu","data"),
    Input("page","data")
)
def render(menu,page):
    if menu=="dt":
        return page_1("dt","DOANH THU TỔNG – TOÀN TẬP ĐOÀN") if page==1 else page_2("dt","PHÂN TÍCH DOANH THU THEO KHU VỰC",df_dt,"khu_vuc")
    if menu=="lh":
        return page_1("lh","DOANH THU LOẠI HÌNH – TOÀN TẬP ĐOÀN") if page==1 else page_2("lh","PHÂN TÍCH LOẠI HÌNH THEO KHU VỰC",df_lh,"khu_vuc")
    return page_1("hd","HỢP ĐỒNG – TOÀN TẬP ĐOÀN") if page==1 else page_2("hd","PHÂN TÍCH HỢP ĐỒNG THEO KHU VỰC",df_hd,"khu_vuc")

# ==========================================================
# NEW: Store current filters per (menu, page) for export
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
# FIX HOÀN TOÀN: Theme -> wrap style (ổn định 100%, trả đúng số lượng ALL)
# ==========================================================
@app.callback(
    Output({"type": "filter-wrap", "id": ALL}, "style"),
    Input("theme", "data"),
    State({"type": "filter-wrap", "id": ALL}, "id"),
    prevent_initial_call=False
)
def update_filter_wrap_styles(theme, ids):
    st = dropdown_container_style(theme)
    return [st] * len(ids)

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
    # NOTE: FIX runtime "nonexistent object" when switching theme:
    # - inputs for other pages/menus may not exist in current layout
    # - make them optional + gate callback execution by current (menu, page)
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
        Output(f"{prefix}-p1-kpi1","children"),
        Output(f"{prefix}-p1-kpi2","children"),
        Output(f"{prefix}-p1-kpi3","children"),
        Output(f"{prefix}-p1-line-kv","figure"),
        Output(f"{prefix}-p1-line","figure"),
        Output(f"{prefix}-p1-bar","figure"),
        Output(f"{prefix}-p1-pie","figure"),

        # stores
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi1"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi2"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-kpi3"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-line-kv"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-line"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-bar"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p1-pie"}, "data"),

        *inputs_p1,
        State("menu", "data"),
        State("page", "data"),
    )
    def p1(*args):
        # parse args with/without type_filter
        if p1_filter_input is not None:
            year_val = args[0]
            months = args[1]
            theme = args[2]
            type_filter = args[3]
            menu = args[4]
            page = args[5]
        else:
            year_val = args[0]
            months = args[1]
            theme = args[2]
            type_filter = None
            menu = args[3]
            page = args[4]

        # gate: only run when current view matches this callback
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

        # KPI payload theo khu vực
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

        # ===== charts =====
        g = dff.groupby("thang_nam_vn", as_index=False).agg({value_col: "sum"}).sort_values("thang_nam_vn")
        g["val_fmt"] = g[value_col].apply(fmt_vn)
        g["thang_label"] = g["thang_nam_vn"].dt.strftime("%m/%Y")

        # Chart 1: compare khu vực (Top 8 + Khác) nhưng PIN Cần Thơ
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

        # Chart 2: total trend
        fig_line = px.line(g, x="thang_nam_vn", y=value_col, markers=True, hover_data={"val_fmt": True, value_col: False})
        fig_line.update_traces(line_shape="spline", line_width=3, marker_size=7)
        fig_line = apply_theme(fig_line, theme)
        fig_line = apply_chart_title(fig_line, f"{metric_label} theo tháng • Tổng toàn tập đoàn<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
        fig_line = _add_line_point_labels(fig_line, show_all_if_points_le=10)
        fig_line_store = pack_fig_store(fig_line, rows=g.to_dict("records"), meta={"chart": "line_total", "metric_label": metric_label})

        # Chart 3: bar
        fig_bar = px.bar(g, x="thang_nam_vn", y=value_col, text="val_fmt", hover_data={"val_fmt": True, value_col: False})
        fig_bar.update_traces(textposition="outside", cliponaxis=False)
        fig_bar.update_layout(margin=dict(t=20))
        fig_bar = apply_theme(fig_bar, theme)
        fig_bar = apply_chart_title(fig_bar, f"{metric_label} theo tháng • Biểu đồ cột<br>{year_txt} • {mo_txt}{tf_txt}", top=210, y_title=metric_axis)
        fig_bar_store = pack_fig_store(fig_bar, rows=g.to_dict("records"), meta={"chart": "bar_total", "metric_label": metric_label})

        # Chart 4: pie theo tháng
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
        Input(f"{prefix}-dim","value", allow_optional=True),
        Input(f"{prefix}-year-p2","value", allow_optional=True),
        Input(f"{prefix}-month-p2","value", allow_optional=True),
        Input("theme","data"),
    ]
    if p2_filter_input is not None:
        inputs_p2.append(p2_filter_input)

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

        # stores
        Output({"type":"zoom-store","target": f"{prefix}-kpi1"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi2"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-kpi3"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-line"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-bar"}, "data"),
        Output({"type":"zoom-store","target": f"{prefix}-p2-pie"}, "data"),

        *inputs_p2,
        State("menu", "data"),
        State("page", "data"),
    )
    def p2(*args):
        if p2_filter_input is not None:
            dim = args[0]
            year_val = args[1]
            months = args[2]
            theme = args[3]
            type_filter = args[4]
            menu = args[5]
            page = args[6]
        else:
            dim = args[0]
            year_val = args[1]
            months = args[2]
            theme = args[3]
            type_filter = None
            menu = args[4]
            page = args[5]

        # gate: only run when current view matches this callback
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

        # FIG1: so sánh khu vực
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

        # FIG2: Bar Số cuốc
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
                fig2_store = pack_fig_store(fig2, rows=dff_bar[["thang_label","tong_so_cuoc","sc_fmt"]].to_dict("records"), meta={"chart": "bar_total", "metric_label": "Số cuốc"})
        else:
            fig2 = apply_theme(px.bar(dff, x="thang_nam_vn", y=value_col), theme)
            fig2 = apply_chart_title(
                fig2,
                f"Biểu đồ cột theo tháng<br>{dims_show} • {year_txt} • {mo_txt}{tf_txt}",
                top=220
            )
            fig2_store = pack_fig_store(fig2, rows=[], meta={"chart": "bar_unknown", "metric_label": metric_label})

        # FIG3: Donut
        if len(dims) >= 2 and "khu_vuc" in dff.columns:
            fig3 = make_vn_donut(
                dff,
                names="khu_vuc",
                values=value_col,
                title=f"Tỷ trọng đóng góp theo khu vực • {metric_label}<br>{year_txt} • {mo_txt}{tf_txt}",
                max_slices=10,
                color_map=REGION_COLOR_MAP
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
                color_map=None
            )
            fig3 = apply_theme(fig3, theme)

            g3 = dff_pie.groupby("thang", as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
            g3["val_fmt"] = g3[value_col].apply(fmt_vn)
            rows3 = [{"label": str(r["thang"]), "metric": float(r[value_col]), "metric_fmt": r["val_fmt"]} for _, r in g3.iterrows()]
            fig3_store = pack_fig_store(fig3, rows=rows3, meta={"chart": "pie_month", "metric_label": metric_label})

        # Table formatting
        dff_table = dff.copy()

        # 1) FIX: thang_nam & thang_nam_vn chỉ hiển thị MM/YYYY
        for col in ["thang_nam", "thang_nam_vn"]:
            if col in dff_table.columns:
                dff_table[col] = (
                    pd.to_datetime(dff_table[col], errors="coerce")
                      .dt.strftime("%m/%Y")
                      .fillna("")
                )

        # 2) FIX: cột nam hiển thị 2025 (không thành 2.025)
        if "nam" in dff_table.columns:
            dff_table["nam"] = (
                pd.to_numeric(dff_table["nam"], errors="coerce")
                  .astype("Int64")
                  .astype(str)
                  .replace("<NA>", "")
            )

        # 3) Format số VN cho các cột số, nhưng LOẠI TRỪ cột nam
        num_cols = dff_table.select_dtypes(include="number").columns
        num_cols = [c for c in num_cols if c != "nam"]
        for c in num_cols:
            dff_table[c] = dff_table[c].apply(fmt_vn)

        if theme == "light":
            style_cell = {"backgroundColor": LIGHT_BG, "color": "black", "textAlign": "center"}
            style_header = {"backgroundColor": "#f2f2f2", "color": "black", "fontWeight": "700"}
        else:
            style_cell = {"backgroundColor": DARK_BG, "color": "white", "textAlign": "center"}
            style_header = {"backgroundColor": "#222", "color": "white", "fontWeight": "700"}

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

    Input({"type":"zoomable","kind":ALL,"target":ALL}, "n_clicks"),
    Input("zoom-modal", "n_dismiss"),
    Input("zoom-graph", "clickData"),

    State("zoom-modal", "is_open"),
    State("zoom-target", "data"),
    State({"type":"zoom-store","target":ALL}, "data"),
    State("theme", "data"),
    prevent_initial_call=True
)
def zoom_all(_clicks, n_dismiss, clickData, is_open, zoom_target, _all_store_data, theme):
    trig = ctx.triggered_id

    # close
    if trig == "zoom-modal":
        return False, no_update, no_update, no_update, {"display":"none"}, no_update, {"display":"none"}, None

    # drilldown click on zoom chart
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
        rows = store.get("rows", []) or []
        fig = store.get("figure", {}) or {}

        if not rows:
            detail = html.Div("Không có dữ liệu drill-down cho biểu đồ này.", style={"opacity":0.85})
            return True, no_update, no_update, no_update, no_update, detail, {"display":"block"}, zoom_target

        pt = (clickData.get("points") or [{}])[0]
        x = pt.get("x", None)
        label = pt.get("label", None)

        # trace name -> region
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
            detail = html.Div("Không tìm thấy dòng dữ liệu phù hợp cho điểm bạn click.", style={"opacity":0.85})
            return True, no_update, no_update, no_update, no_update, detail, {"display":"block"}, zoom_target

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

        if theme == "light":
            style_cell = {"backgroundColor": LIGHT_BG, "color": "black", "textAlign": "center", "padding":"8px"}
            style_header = {"backgroundColor":"#f2f2f2","color":"black","fontWeight":"900"}
        else:
            style_cell = {"backgroundColor": DARK_BG, "color": "white", "textAlign": "center", "padding":"8px"}
            style_header = {"backgroundColor":"#222","color":"white","fontWeight":"900"}

        detail = dbc.Card(
            dbc.CardBody([
                html.Div(title, style={"fontSize":"15px","fontWeight":"900"}),
                html.Div(" • ".join(subtitle), style={"opacity":0.85,"marginBottom":"8px","fontWeight":"700"}),
                dash_table.DataTable(
                    columns=columns,
                    data=data,
                    page_size=14,
                    style_cell=style_cell,
                    style_header=style_header,
                )
            ]),
            style={"border":"1px solid #3b3b57","boxShadow":"0 0 20px rgba(90,80,255,0.12)"}
        )
        return True, no_update, no_update, no_update, no_update, detail, {"display":"block"}, zoom_target

    # open modal from KPI/FIG click
    if isinstance(trig, dict) and trig.get("type") == "zoomable":
        # chặn tự bật khi re-render
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

        # reset detail on open
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
                        "khu_vuc": r.get("khu_vuc",""),
                        "value_fmt": r.get("value_fmt","0"),
                        "pct_fmt": f'{r.get("pct",0):.1f}%',
                    })
            elif rows and "avg_fmt" in rows[0]:
                cols = [
                    {"name": "Khu vực", "id": "khu_vuc"},
                    {"name": "Trung bình", "id": "avg_fmt"},
                ]
                data = [{"khu_vuc": r.get("khu_vuc",""), "avg_fmt": r.get("avg_fmt","0")} for r in rows]

            kpi_card = dbc.Card(
                dbc.CardBody([
                    html.Div(store.get("title","KPI"), style={"fontSize":"14px","fontWeight":"900","opacity":0.85}),
                    html.Div(store.get("main","0"), style={"fontSize":"44px","fontWeight":"900","marginTop":"6px"}),
                    html.Div(store.get("subtitle",""), style={"fontSize":"13px","opacity":0.85,"fontWeight":"800","marginTop":"4px"}),
                    html.Hr(style={"borderColor":"#444"}),
                    dash_table.DataTable(
                        columns=cols,
                        data=data,
                        page_size=12,
                        style_header={"backgroundColor":"#222","color":"white","fontWeight":"900"},
                        style_cell={"backgroundColor":DARK_BG,"color":"white","textAlign":"center","padding":"8px"},
                    ) if cols else html.Div("Không có breakdown theo khu vực.", style={"opacity":0.8})
                ]),
                style={"border":"1px solid #3b3b57","boxShadow":"0 0 20px rgba(90,80,255,0.15)"}
            )

            return True, title, kpi_card, {}, {"display":"none"}, [], {"display":"none"}, {"kind":"kpi","target":target}

        # FIG
        fig_dict = store.get("figure", {})
        fig_dict = enhance_zoom_figure(fig_dict)

        detail_style = {"display":"block"}
        detail_children = html.Div("Click vào 1 điểm/cột để xem chi tiết.", style={"opacity":0.8, "fontWeight":"700"})

        return True, title, None, fig_dict, {"display":"block","height":"82vh"}, detail_children, detail_style, {"kind":"fig","target":target}

    raise PreventUpdate

# =========================
# AI (UPGRADE INTELLIGENCE, giữ cấu trúc callback/ID)
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

def detect_year(text: str):
    m = re.search(r"(19|20)\d{2}", text)
    return int(m.group()) if m else None

def detect_month_label(text: str):
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*/\s*((19|20)\d{2})\b", text)
    if m:
        mm = int(m.group(1))
        yy = int(m.group(2))
        return f"{mm:02d}/{yy}"
    m2 = re.search(r"\bthang\s*(0?[1-9]|1[0-2])\s*(nam)?\s*((19|20)\d{2})\b", text)
    if m2:
        mm = int(m2.group(1))
        yy = int(m2.group(3))
        return f"{mm:02d}/{yy}"
    return None

def detect_month_number(text: str):
    m = re.search(r"\bthang\s*(0?[1-9]|1[0-2])\b", text)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b[tT]\s*(0?[1-9]|1[0-2])\b", text)
    if m2:
        return int(m2.group(1))
    return None

def detect_top_n(text: str):
    m = re.search(r"\btop\s*(\d+)\b", text.lower())
    return int(m.group(1)) if m else None

def detect_bottom_n(text: str):
    m = re.search(r"\bbottom\s*(\d+)\b", text.lower())
    return int(m.group(1)) if m else None

def choose_dataset(question: str):
    q = norm_q(question)
    if "hop dong" in q or "hợp đồng" in question.lower() or "so cuoc" in q or "số cuốc" in question.lower():
        return "hd", df_hd, "tong_so_cuoc"
    if "loai hinh" in q or "loại hình" in question.lower():
        return "lh", df_lh, "tong_doanh_thu"
    return "dt", df_dt, "tong_doanh_thu"

def detect_metric_intent(question: str, value_col_default: str):
    q = norm_q(question)

    if ("doanh thu" in q) or ("revenue" in q):
        metric_col = "tong_doanh_thu"
    elif ("so cuoc" in q) or ("số cuốc" in question.lower()) or ("cuoc" in q) or ("trip" in q):
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
    return None

def detect_regions_in_question(question: str):
    q = norm_q(question)
    hits = []
    for r in ALL_REGIONS:
        if norm_q(r) and norm_q(r) in q:
            hits.append(r)
    # trường hợp gõ không dấu / dính chữ:
    if not hits:
        q2 = re.sub(r"[^a-z0-9\s]+", " ", q)
        q2 = re.sub(r"\s+", " ", q2).strip()
        for r in ALL_REGIONS:
            rr = re.sub(r"[^a-z0-9\s]+", " ", norm_q(r))
            rr = re.sub(r"\s+", " ", rr).strip()
            if rr and rr in q2:
                hits.append(r)
    return list(dict.fromkeys(hits))  # unique giữ thứ tự

def detect_intent_advanced(question: str):
    q = norm_q(question)
    # ưu tiên top/bottom
    if any(k in q for k in ["cao nhat", "lon nhat", "nhieu nhat", "top "]):
        return "top"
    if any(k in q for k in ["thap nhat", "nho nhat", "it nhat", "bottom "]):
        return "bottom"
    # tỷ trọng / đóng góp
    if any(k in q for k in ["ty trong", "tỷ trọng", "phan tram", "phần trăm", "dong gop", "đóng góp", "share", "contribution"]):
        return "share"
    # xu hướng
    if any(k in q for k in ["xu huong", "xu hướng", "trend", "theo thang", "theo tháng", "tang", "giảm", "giam", "so sanh", "vs"]):
        return "trend"
    # mặc định
    return "total"

def _pct(a, total):
    return (a / total * 100.0) if total and total > 0 else 0.0

def answer_question(question: str) -> str:
    if not question or not question.strip():
        return "Bạn hãy nhập câu hỏi trước nhé."

    key, df, value_col_default = choose_dataset(question)
    qn = norm_q(question)

    year = detect_year(qn)
    month_label = detect_month_label(qn)
    month_num = detect_month_number(qn) if month_label is None else None
    assume_note = ""

    intent_metric = detect_metric_intent(question, value_col_default)
    metric_col = intent_metric["metric_col"]

    type_filter = extract_type_filter(question, key)
    regions_asked = detect_regions_in_question(question)
    intent = detect_intent_advanced(question)

    dff = df.copy()

    if metric_col not in dff.columns:
        metric_col = value_col_default

    if year is not None and "nam" in dff.columns:
        dff = dff[dff["nam"] == year]

    if month_label is None and month_num is not None:
        if "thang_nam_vn" in dff.columns:
            tmp = dff[dff["thang_nam_vn"].dt.month == month_num]
            if year is None and "nam" in tmp.columns and not tmp.empty:
                year = int(tmp["nam"].max())
                month_label = f"{month_num:02d}/{year}"
                assume_note = f" (mặc định {month_label})"
            elif year is not None:
                month_label = f"{month_num:02d}/{year}"
                assume_note = ""
            else:
                dff = tmp

    if month_label is not None and "thang_label" in dff.columns:
        dff = dff[dff["thang_label"] == month_label]

    if key == "lh" and type_filter and LH_COL in dff.columns:
        dff = dff[dff[LH_COL].astype(str).isin(type_filter)]
    if key == "hd" and type_filter and HD_COL in dff.columns:
        dff = dff[dff[HD_COL].astype(str).isin(type_filter)]

    if regions_asked and "khu_vuc" in dff.columns:
        dff = dff[dff["khu_vuc"].astype(str).isin([str(x) for x in regions_asked])]

    if dff.empty:
        if month_label and year:
            return f"Mình không thấy dữ liệu cho **{month_label}** (năm **{year}**) trong dataset hiện tại."
        if month_label:
            return f"Mình không thấy dữ liệu cho **{month_label}** trong dataset hiện tại."
        if year is not None:
            return f"Mình không thấy dữ liệu cho năm **{year}** trong dataset hiện tại."
        return "Mình không thấy dữ liệu phù hợp trong dataset hiện tại."

    metric_name = "doanh thu" if metric_col != "tong_so_cuoc" else "số cuốc"
    yr_text = f" năm {year}" if year is not None else ""
    mo_text = f" tháng {month_label}{assume_note}" if month_label is not None else (f" tháng {month_num}" if month_num else "")
    tf_text = f" (lọc: {', '.join(type_filter)})" if type_filter else ""
    rg_text = f" (khu vực: {', '.join(regions_asked)})" if regions_asked else ""

    # ===== INTENTS =====
    if intent in ["top", "bottom"] and "khu_vuc" in dff.columns:
        n = detect_top_n(question) or detect_bottom_n(question) or 5
        g = dff.groupby("khu_vuc", as_index=False)[metric_col].sum().sort_values(metric_col, ascending=(intent=="bottom"))
        total_all = float(g[metric_col].sum()) if not g.empty else 0.0

        head = g.head(n).copy()
        lines = []
        for i, row in head.iterrows():
            kv = str(row["khu_vuc"])
            val = float(row[metric_col]) if row[metric_col] is not None else 0.0
            lines.append(f"- **{kv}**: **{fmt_vn(val)}** ({_pct(val, total_all):.1f}%)")

        best = head.iloc[0] if not head.empty else None
        if best is not None:
            best_kv = str(best["khu_vuc"])
            best_val = float(best[metric_col]) if best[metric_col] is not None else 0.0
            tag = "cao nhất" if intent=="top" else "thấp nhất"
            return (
                f"**{n} khu vực {tag}** về **{metric_name}**{yr_text}{mo_text}{tf_text}:\n"
                + "\n".join(lines)
                + f"\n\n➡️ Kết luận: **{best_kv}** {tag} với **{fmt_vn(best_val)}**.{rg_text}"
            )

    if intent == "share":
        if "khu_vuc" in dff.columns:
            g = dff.groupby("khu_vuc", as_index=False)[metric_col].sum().sort_values(metric_col, ascending=False)
            total_all = float(g[metric_col].sum()) if not g.empty else 0.0
            head = g.head(8).copy()
            lines = []
            for _, row in head.iterrows():
                kv = str(row["khu_vuc"])
                val = float(row[metric_col]) if row[metric_col] is not None else 0.0
                lines.append(f"- **{kv}**: **{_pct(val, total_all):.1f}%** ({fmt_vn(val)})")
            return (
                f"**Tỷ trọng {metric_name} theo khu vực**{yr_text}{mo_text}{tf_text}{rg_text}:\n"
                + "\n".join(lines)
                + ("\n\n(Gợi ý: bạn có thể hỏi thêm “Top 3 khu vực đóng góp nhiều nhất ...”)")
            )
        else:
            # fallback theo tháng
            if "thang_label" in dff.columns:
                g = dff.groupby("thang_label", as_index=False)[metric_col].sum().sort_values(metric_col, ascending=False)
                total_all = float(g[metric_col].sum()) if not g.empty else 0.0
                head = g.head(12)
                lines = []
                for _, row in head.iterrows():
                    m = str(row["thang_label"])
                    val = float(row[metric_col]) if row[metric_col] is not None else 0.0
                    lines.append(f"- **{m}**: **{_pct(val, total_all):.1f}%** ({fmt_vn(val)})")
                return f"**Tỷ trọng {metric_name} theo tháng**{yr_text}{tf_text}:\n" + "\n".join(lines)

    if intent == "trend":
        if "thang_label" in dff.columns and "thang_nam_vn" in dff.columns:
            g = dff.groupby(["thang_nam_vn"], as_index=False)[metric_col].sum().sort_values("thang_nam_vn")
            g["thang_label"] = g["thang_nam_vn"].dt.strftime("%m/%Y")
            if len(g) >= 2:
                first_val = float(g.iloc[0][metric_col])
                last_val = float(g.iloc[-1][metric_col])
                diff = last_val - first_val
                pct = (diff / first_val * 100.0) if first_val != 0 else 0.0
                direction = "tăng" if diff >= 0 else "giảm"

                # show top 6 months by value if asked "cao nhất theo tháng"
                if any(k in qn for k in ["cao nhat theo thang", "lon nhat theo thang", "max theo thang"]):
                    g2 = g.sort_values(metric_col, ascending=False).head(6)
                    lines = [f"- **{r['thang_label']}**: **{fmt_vn(r[metric_col])}**" for _, r in g2.iterrows()]
                    return f"**Top tháng cao nhất** về {metric_name}{yr_text}{tf_text}{rg_text}:\n" + "\n".join(lines)

                # default trend summary
                preview = g.tail(6).copy()
                lines = [f"- {r['thang_label']}: {fmt_vn(r[metric_col])}" for _, r in preview.iterrows()]
                return (
                    f"**Xu hướng {metric_name}**{yr_text}{tf_text}{rg_text}:\n"
                    f"- Từ **{g.iloc[0]['thang_label']}**: **{fmt_vn(first_val)}**\n"
                    f"- Đến **{g.iloc[-1]['thang_label']}**: **{fmt_vn(last_val)}**\n"
                    f"- Kết quả: **{direction} {fmt_vn(abs(diff))}** ({pct:+.1f}%)\n\n"
                    f"📌 6 tháng gần nhất trong phạm vi lọc:\n" + "\n".join(lines)
                )
            else:
                only = float(g.iloc[0][metric_col])
                return f"Trong phạm vi lọc{yr_text}{mo_text}{tf_text}{rg_text}, **{metric_name}** là **{fmt_vn(only)}**."

    # default total
    total = float(dff[metric_col].sum())
    return f"Tổng **{metric_name}**{yr_text}{mo_text}{tf_text}{rg_text} là **{fmt_vn(total)}**."

@app.callback(
    Output("ai-chat-history", "data"),
    Output("ai-output", "children"),
    Input("ai-send", "n_clicks"),
    Input("ai-clear", "n_clicks"),
    State("ai-input", "value"),
    State("ai-chat-history", "data"),
    prevent_initial_call=True
)
def ai_chat(n_send, n_clear, question, history):
    history = history or []
    if ctx.triggered_id == "ai-clear":
        return [], []

    ans = answer_question(question)
    now_txt = datetime.now().strftime("%H:%M:%S")

    history.append({"role": "user", "text": question or "", "time": now_txt})
    history.append({"role": "ai", "text": ans, "time": now_txt})

    rendered = []
    for item in history[-12:]:
        if item["role"] == "user":
            rendered.append(
                html.Div([
                    html.Div("BẠN", className="ai-meta"),
                    html.Div(item["text"]),
                    html.Div(item.get("time",""), className="ai-time")
                ], className="ai-bubble ai-user")
            )
        else:
            rendered.append(
                html.Div([
                    html.Div("AI", className="ai-meta"),
                    dcc.Markdown(item["text"]),
                    html.Div(item.get("time",""), className="ai-time")
                ], className="ai-bubble ai-bot")
            )

    return history, rendered

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
