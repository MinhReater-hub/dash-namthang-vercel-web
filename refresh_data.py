from dotenv import load_dotenv
import os
import pyodbc
import pandas as pd
from pathlib import Path
from datetime import timedelta
import matplotlib
import unicodedata
import re
import time
matplotlib.use("Agg")

load_dotenv()

def _env_datetime(name: str, default=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    value = pd.to_datetime(raw, errors="coerce")
    return default if pd.isna(value) else value

SERVER = os.getenv("SQL_SERVER")
DATABASE = os.getenv("SQL_DATABASE")
USERNAME = os.getenv("SQL_USERNAME")
PASSWORD = os.getenv("SQL_PASSWORD")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
SQL_ENCRYPT = os.getenv("SQL_ENCRYPT", "no")
SQL_TRUST_SERVER_CERTIFICATE = os.getenv("SQL_TRUST_SERVER_CERTIFICATE", "yes")

today = pd.Timestamp.today().normalize()
START_DATE = _env_datetime("START_DATE", today - timedelta(days=365))
END_DATE = _env_datetime("END_DATE", today)

DAILY_CHECKER_EXPORT_RAW = str(os.getenv("DAILY_CHECKER_EXPORT_RAW", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
DAILY_CHECKER_SQL_TABLE_HINT = os.getenv("DAILY_CHECKER_SQL_TABLE_HINT", "").strip()
DAILY_CHECKER_TABLE_EXPR = "dbo.doanhthungaychecker" + (f" WITH ({DAILY_CHECKER_SQL_TABLE_HINT})" if DAILY_CHECKER_SQL_TABLE_HINT else "")

# Daily fleet availability source. dbo.danhSachLenCa is used to compute
# "Xe đang có-ngày" from real daily rows. Business rule:
# - count both "Lên ca" and "Xuống ca" rows
# - keep electric taxi business rows (Taxi điện / Khoán điện / Điện ăn chia), exclude Xe công vụ
# - if hinhthuc_kinhdoanh is blank and trangthai_len_xuong_ca is Xuống ca,
#   still count the vehicle because these rows represent available / parked / no-revenue vehicles
# - exclude VF3 service vehicles in the transform
LENCA_EXPORT_DAILY_FLEET = str(os.getenv("LENCA_EXPORT_DAILY_FLEET", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
LENCA_SQL_TABLE = os.getenv("LENCA_SQL_TABLE", "dbo.danhSachLenCa").strip() or "dbo.danhSachLenCa"
LENCA_SQL_TABLE_HINT = os.getenv("LENCA_SQL_TABLE_HINT", "").strip()
LENCA_DATE_COLUMN = os.getenv("LENCA_DATE_COLUMN", "").strip()
LENCA_TABLE_EXPR = LENCA_SQL_TABLE + (f" WITH ({LENCA_SQL_TABLE_HINT})" if LENCA_SQL_TABLE_HINT else "")


missing_env = [name for name, value in {
    "SQL_SERVER": SERVER,
    "SQL_DATABASE": DATABASE,
    "SQL_USERNAME": USERNAME,
    "SQL_PASSWORD": PASSWORD,
}.items() if not value]
if missing_env:
    raise ValueError("Thiếu biến môi trường SQL bắt buộc: " + ", ".join(missing_env))
if START_DATE is not None and END_DATE is not None and START_DATE > END_DATE:
    raise ValueError("START_DATE phải nhỏ hơn hoặc bằng END_DATE.")

BASE_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
CHART_DIR = BASE_DIR / "charts"
BASE_DIR.mkdir(exist_ok=True)
CHART_DIR.mkdir(exist_ok=True)
EXCEL_FILE = BASE_DIR / os.getenv("OUTPUT_EXCEL_NAME", "bao_cao_doanh_thu_tong_hop.xlsx")

# Runtime cache for Dash web app. Excel is still exported for download/audit,
# but the Dash app should read these smaller cache files first on Vercel.
CACHE_DIR = Path(os.getenv("OUTPUT_CACHE_DIR", str(BASE_DIR / "cache")))
EXPORT_DASH_CACHE = str(os.getenv("EXPORT_DASH_CACHE", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
CACHE_DIR.mkdir(exist_ok=True)

SQL_QUERY_TIMEOUT = int(os.getenv("SQL_QUERY_TIMEOUT", "90"))
SQL_ENABLE_DATE_PUSHDOWN = str(os.getenv("SQL_ENABLE_DATE_PUSHDOWN", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
SQL_LOG_TIMING = str(os.getenv("SQL_LOG_TIMING", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}


def _dt_param(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).to_pydatetime()


def _read_sql_fast(label: str, sql: str, params=None, fallback_sql: str | None = None) -> pd.DataFrame:
    started = time.perf_counter()
    try:
        out = pd.read_sql_query(sql, conn, params=params)
        if SQL_LOG_TIMING:
            print(f"[SQL LOAD] {label}: {len(out):,} rows in {time.perf_counter() - started:.2f}s")
        return out
    except Exception as e:
        if fallback_sql is None:
            raise
        print(f"[SQL LOAD] {label}: filtered query failed, fallback full query. Error: {e}")
        started = time.perf_counter()
        out = pd.read_sql_query(fallback_sql, conn)
        if SQL_LOG_TIMING:
            print(f"[SQL LOAD] {label}/fallback: {len(out):,} rows in {time.perf_counter() - started:.2f}s")
        return out


conn = pyodbc.connect(
    f"DRIVER={{{SQL_DRIVER}}};"
    f"SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};"
    f"Encrypt={SQL_ENCRYPT};TrustServerCertificate={SQL_TRUST_SERVER_CERTIFICATE};"
)
try:
    conn.timeout = SQL_QUERY_TIMEOUT
except Exception:
    pass

start_param = _dt_param(START_DATE)
end_param = _dt_param(END_DATE)

_df_tx_sql = """
    SELECT thoi_gian_tao, thang_nam, so_tai, ho_ten,
           doanh_thu, so_cuoc, khu_vuc, loaihinh_hoptac
    FROM doanhthulaixe
"""
df_tx = _read_sql_fast(
    "doanhthulaixe",
    _df_tx_sql + ("""
    WHERE thoi_gian_tao >= ? AND thoi_gian_tao < DATEADD(day, 1, ?)
    """ if SQL_ENABLE_DATE_PUSHDOWN else ""),
    params=[start_param, end_param] if SQL_ENABLE_DATE_PUSHDOWN else None,
    fallback_sql=_df_tx_sql,
)

_df_hd_sql = """
    SELECT
        id,
        ngay_di_hop_dong,
        khu_vuc,
        loai_hopdong
    FROM cuocxehopdong
"""
df_hd = _read_sql_fast(
    "cuocxehopdong",
    _df_hd_sql + ("""
    WHERE ngay_di_hop_dong >= ? AND ngay_di_hop_dong < DATEADD(day, 1, ?)
    """ if SQL_ENABLE_DATE_PUSHDOWN else ""),
    params=[start_param, end_param] if SQL_ENABLE_DATE_PUSHDOWN else None,
    fallback_sql=_df_hd_sql,
)

_df_ns_sql = """
    SELECT
        ID_NV,
        HO_TEN,
        DON_VI_CT,
        VI_TRI_CONG_VIEC,
        TRANG_THAI,
        KHU_VUC,
        DIA_DIEM_LAM_VIEC,
        NGAY_THU_VIEC,
        NGAY_CHINH_THUC,
        NGAY_NGHI_VIEC,
        UpdatedAt,
        VONG_DOI
    FROM dbo.nhansutapdoan
"""
df_ns = _read_sql_fast(
    "nhansutapdoan",
    _df_ns_sql + ("""
    WHERE
        (COALESCE(NGAY_CHINH_THUC, NGAY_THU_VIEC, UpdatedAt) IS NULL OR COALESCE(NGAY_CHINH_THUC, NGAY_THU_VIEC, UpdatedAt) <= ?)
        AND (NGAY_NGHI_VIEC IS NULL OR NGAY_NGHI_VIEC >= ?)
    """ if SQL_ENABLE_DATE_PUSHDOWN else ""),
    params=[end_param, start_param] if SQL_ENABLE_DATE_PUSHDOWN else None,
    fallback_sql=_df_ns_sql,
)

_month_start = START_DATE.to_period("M").to_timestamp() if START_DATE is not None and not pd.isna(START_DATE) else START_DATE
_month_end = END_DATE.to_period("M").to_timestamp() if END_DATE is not None and not pd.isna(END_DATE) else END_DATE
_df_bb_sql = """
    SELECT
        ID,
        LOAI_BIEN_BAN,
        TINH_TRANG_BIEN_BAN,
        TONG_TIEN_DE_XUAT,
        CON_LAI,
        TRANG_THAI_THU,
        KHU_VUC,
        thang_nam
    FROM dbo.bienban
"""
df_bb = _read_sql_fast(
    "bienban",
    _df_bb_sql + ("""
    WHERE thang_nam >= ? AND thang_nam < DATEADD(month, 1, ?)
    """ if SQL_ENABLE_DATE_PUSHDOWN else ""),
    params=[_dt_param(_month_start), _dt_param(_month_end)] if SQL_ENABLE_DATE_PUSHDOWN else None,
    fallback_sql=_df_bb_sql,
)

try:
    df_mkt_cost = _read_sql_fast("chihoahongdtt", "SELECT * FROM dbo.chihoahongdtt")
except Exception as e:
    print(f"[MKT LOAD] khong doc duoc dbo.chihoahongdtt: {e}")
    df_mkt_cost = pd.DataFrame()

try:
    df_mkt_point = _read_sql_fast("danhsachdiemtiepthi", "SELECT * FROM dbo.danhsachdiemtiepthi")
except Exception as e:
    print(f"[MKT LOAD] khong doc duoc dbo.danhsachdiemtiepthi: {e}")
    df_mkt_point = pd.DataFrame()

try:
    df_vehicle = _read_sql_fast("thongtinphuongtien", "SELECT * FROM dbo.thongtinphuongtien")
except Exception as e:
    print(f"[FLEET LOAD] khong doc duoc dbo.thongtinphuongtien: {e}")
    df_vehicle = pd.DataFrame()

if LENCA_EXPORT_DAILY_FLEET:
    try:
        _lenca_base_sql = f"SELECT * FROM {LENCA_TABLE_EXPR}"
        _lenca_sql = _lenca_base_sql
        _lenca_params = None
        # Optional pushdown when the exact date column is known. If not set, read
        # the table and filter in pandas because dbo.danhSachLenCa schemas vary.
        if SQL_ENABLE_DATE_PUSHDOWN and LENCA_DATE_COLUMN:
            safe_date_col = LENCA_DATE_COLUMN.replace("]", "")
            _lenca_sql = _lenca_base_sql + f" WHERE [{safe_date_col}] >= ? AND [{safe_date_col}] < DATEADD(day, 1, ?)"
            _lenca_params = [start_param, end_param]
        df_lenca = _read_sql_fast(
            "danhSachLenCa",
            _lenca_sql,
            params=_lenca_params,
            fallback_sql=_lenca_base_sql,
        )
    except Exception as e:
        print(f"[LENCA LOAD] khong doc duoc {LENCA_SQL_TABLE}: {e}")
        df_lenca = pd.DataFrame()
else:
    df_lenca = pd.DataFrame()

_daily_checker_sql = f"""
        SELECT
            id,
            thoi_gian_tao,
            thang_nam,
            bks,
            so_tai,
            ho_ten,
            doanh_thu,
            so_cuoc,
            sokm_vandoanh,
            sokm_cokhach,
            loaihinh_hoptac,
            hinhthuc_kinhdoanh,
            loai_luong,
            so_cho,
            khu_vuc
        FROM {DAILY_CHECKER_TABLE_EXPR}
"""
try:
    df_daily_checker = _read_sql_fast(
        "doanhthungaychecker",
        _daily_checker_sql + ("""
        WHERE thoi_gian_tao >= ? AND thoi_gian_tao < DATEADD(day, 1, ?)
        """ if SQL_ENABLE_DATE_PUSHDOWN else ""),
        params=[start_param, end_param] if SQL_ENABLE_DATE_PUSHDOWN else None,
        fallback_sql=_daily_checker_sql,
    )
except Exception as e:
    print(f"[DAILY CHECKER LOAD] khong doc duoc dbo.doanhthungaychecker: {e}")
    df_daily_checker = pd.DataFrame()

conn.close()

df_tx["thoi_gian_tao"] = pd.to_datetime(df_tx["thoi_gian_tao"], errors="coerce")
df_tx["thang_nam"] = pd.to_datetime(df_tx["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
df_tx["doanh_thu"] = pd.to_numeric(df_tx["doanh_thu"], errors="coerce").fillna(0)
df_tx["so_cuoc"] = pd.to_numeric(df_tx["so_cuoc"], errors="coerce").fillna(0)

df_tx = df_tx[
    (df_tx["thoi_gian_tao"] >= START_DATE) &
    (df_tx["thoi_gian_tao"] <= END_DATE)
]

df_hd["ngay_di_hop_dong"] = pd.to_datetime(df_hd["ngay_di_hop_dong"], errors="coerce")

df_hd = df_hd[df_hd["ngay_di_hop_dong"].notna()]
if pd.notna(START_DATE):
    df_hd = df_hd[df_hd["ngay_di_hop_dong"] >= START_DATE]
if pd.notna(END_DATE):
    df_hd = df_hd[df_hd["ngay_di_hop_dong"] <= END_DATE]

df_hd["thang_nam"] = (
    df_hd["ngay_di_hop_dong"]
    .dt.to_period("M")
    .dt.to_timestamp()
)

df_hd["so_cuoc"] = 1


def _norm_text(value):
    if pd.isna(value):
        return ""
    s = str(value).strip().lower()
    s = s.replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_key(value):
    s = _norm_text(value)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _compact_norm_key(value):
    return re.sub(r"[^a-z0-9]+", "", _norm_key(value))


def _is_phu_quoc_value(value) -> bool:
    key = _compact_norm_key(value)
    return key in {"phuquoc", "pq"}


def _is_phu_quoc_series(series_like) -> pd.Series:
    return pd.Series(series_like).map(_is_phu_quoc_value).fillna(False).astype(bool)


def _is_khoan_dien_series(series_like) -> pd.Series:
    s = pd.Series(series_like).apply(_norm_text)
    return s.str.contains("khoan dien", regex=False, na=False) | s.str.contains("khoang dien", regex=False, na=False)


def _find_first_existing_col(df_source, candidates):
    if df_source is None or df_source.empty:
        return None
    lookup = {_norm_key(col): col for col in df_source.columns}
    for cand in candidates:
        key = _norm_key(cand)
        if key in lookup:
            return lookup[key]
    return None


def _safe_datetime_month(series_like):
    return pd.to_datetime(series_like, errors="coerce").dt.to_period("M").dt.to_timestamp()


def _prepare_marketing_monthly_summary(df_cost_raw: pd.DataFrame, df_point_raw: pd.DataFrame) -> pd.DataFrame:
    expected_cols = [
        "thang_nam", "khu_vuc", "tong_phai_chi", "so_diem_tiep_thi", "so_ho_so_hoa_hong",
        "tong_da_chi_du", "tong_chua_chi_du", "tong_khong_chi",
        "so_ho_so_da_chi_du", "so_ho_so_chua_chi_du", "so_ho_so_khong_chi",
        "so_diem_moi_ky_hd", "so_loai_hinh_kd", "chi_phi_binh_quan_moi_diem", "chi_phi_binh_quan_moi_ho_so",
        "tong_doanh_thu", "tong_so_cuoc", "so_luong"
    ]
    if df_cost_raw is None or df_cost_raw.empty:
        return pd.DataFrame(columns=expected_cols)

    cost = df_cost_raw.copy()
    point = df_point_raw.copy() if df_point_raw is not None else pd.DataFrame()

    cost_id_col = _find_first_existing_col(cost, ["id", "ma chi hoa hong", "ma_hoa_hong"])
    cost_point_id_col = _find_first_existing_col(cost, ["id_dtt", "id diem tiep thi", "diem_tiep_thi_id", "ma_dtt"])
    cost_month_col = _find_first_existing_col(cost, ["thang/nam", "thang_nam", "thang nam", "thang", "month", "period"])
    cost_name_col = _find_first_existing_col(cost, ["diem_tiep_thi", "diem tiep thi", "ten diem tiep thi", "ten_diem_tiep_thi", "ten dtt"])
    cost_status_col = _find_first_existing_col(cost, ["trang_thai_hh", "trang thai hh", "trang_thai", "trang thai hoa hong", "tinh_trang_hh"])
    cost_amount_col = _find_first_existing_col(cost, ["tong_phai_chi", "tong phai chi", "tong_tien", "tong tien", "gia_tri", "so_tien", "hoa_hong"])
    cost_region_col = _find_first_existing_col(cost, ["khu_vuc", "khu vuc", "region", "area"])

    if cost_month_col is None or cost_amount_col is None:
        return pd.DataFrame(columns=expected_cols)

    cost_base = pd.DataFrame({
        "cost_id": cost[cost_id_col] if cost_id_col else pd.Series(range(1, len(cost) + 1), index=cost.index),
        "id_dtt": cost[cost_point_id_col] if cost_point_id_col else pd.Series(index=cost.index, dtype=object),
        "thang_nam": _safe_datetime_month(cost[cost_month_col]),
        "diem_tiep_thi_cost": cost[cost_name_col] if cost_name_col else pd.Series(index=cost.index, dtype=object),
        "trang_thai_hh": cost[cost_status_col] if cost_status_col else pd.Series(index=cost.index, dtype=object),
        "tong_phai_chi": pd.to_numeric(cost[cost_amount_col], errors="coerce").fillna(0),
        "khu_vuc_cost": cost[cost_region_col] if cost_region_col else pd.Series(index=cost.index, dtype=object),
    })

    point_base = pd.DataFrame()
    if point is not None and not point.empty:
        point_id_col = _find_first_existing_col(point, ["id", "id_dtt", "ma_dtt", "ma diem tiep thi"])
        point_name_col = _find_first_existing_col(point, ["diem_tiep_thi", "diem tiep thi", "ten diem tiep thi", "ten_diem_tiep_thi"])
        point_type_col = _find_first_existing_col(point, ["loai_hinh_kd", "loai hinh kd", "loai_hinh", "loai hinh", "nganh_hang", "category"])
        point_sign_col = _find_first_existing_col(point, ["ngay_ky_hd", "ngay ky hd", "ngay_ky", "ngay ky hop dong", "sign_date"])
        point_region_col = _find_first_existing_col(point, ["khu_vuc", "khu vuc", "region", "area"])

        point_base = pd.DataFrame({
            "id_dtt_dim": point[point_id_col] if point_id_col else pd.Series(index=point.index, dtype=object),
            "diem_tiep_thi_dim": point[point_name_col] if point_name_col else pd.Series(index=point.index, dtype=object),
            "loai_hinh_kd": point[point_type_col] if point_type_col else pd.Series(index=point.index, dtype=object),
            "ngay_ky_hd": pd.to_datetime(point[point_sign_col], errors="coerce") if point_sign_col else pd.Series(index=point.index, dtype='datetime64[ns]'),
            "khu_vuc_dim": point[point_region_col] if point_region_col else pd.Series(index=point.index, dtype=object),
        })

        point_base = point_base.drop_duplicates(subset=[c for c in ["id_dtt_dim", "diem_tiep_thi_dim"] if c in point_base.columns and point_base[c].notna().any()], keep="first")

    merged = cost_base.copy()
    if not point_base.empty and "id_dtt" in merged.columns:
        merged = merged.merge(point_base, left_on="id_dtt", right_on="id_dtt_dim", how="left")

        missing_dim_rate = merged.get("diem_tiep_thi_dim", pd.Series(index=merged.index, dtype=object)).isna().mean() if len(merged) else 1.0
        if missing_dim_rate >= 0.9 and merged["diem_tiep_thi_cost"].notna().any() and point_base["diem_tiep_thi_dim"].notna().any():
            point_name_map = point_base.copy()
            point_name_map["diem_tiep_thi_norm"] = point_name_map["diem_tiep_thi_dim"].apply(_norm_key)
            point_name_map = point_name_map[point_name_map["diem_tiep_thi_norm"].ne("")]
            point_name_map = point_name_map.drop_duplicates(subset=["diem_tiep_thi_norm"], keep="first")
            merged["diem_tiep_thi_norm"] = merged["diem_tiep_thi_cost"].apply(_norm_key)
            merged = merged.merge(
                point_name_map[["diem_tiep_thi_norm", "diem_tiep_thi_dim", "loai_hinh_kd", "ngay_ky_hd", "khu_vuc_dim"]],
                on="diem_tiep_thi_norm",
                how="left",
                suffixes=("", "_by_name")
            )
            for base_col, alt_col in [
                ("diem_tiep_thi_dim", "diem_tiep_thi_dim_by_name"),
                ("loai_hinh_kd", "loai_hinh_kd_by_name"),
                ("ngay_ky_hd", "ngay_ky_hd_by_name"),
                ("khu_vuc_dim", "khu_vuc_dim_by_name"),
            ]:
                if alt_col in merged.columns:
                    merged[base_col] = merged[base_col].combine_first(merged[alt_col])

    merged["diem_tiep_thi"] = merged.get("diem_tiep_thi_cost").combine_first(merged.get("diem_tiep_thi_dim"))
    merged["khu_vuc"] = merged.get("khu_vuc_cost").combine_first(merged.get("khu_vuc_dim"))
    merged["khu_vuc"] = merged["khu_vuc"].fillna("Tổng hợp").astype(str).str.strip()
    merged.loc[merged["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"

    merged["thang_nam"] = pd.to_datetime(merged["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    merged = merged[merged["thang_nam"].notna()].copy()
    if pd.notna(START_DATE):
        merged = merged[merged["thang_nam"] >= START_DATE.to_period("M").to_timestamp()]
    if pd.notna(END_DATE):
        merged = merged[merged["thang_nam"] <= END_DATE.to_period("M").to_timestamp()]

    merged["trang_thai_hh_norm"] = merged["trang_thai_hh"].apply(_norm_text)
    merged["is_da_chi_du"] = merged["trang_thai_hh_norm"].str.contains("da chi du", regex=False)
    merged["is_chua_chi_du"] = merged["trang_thai_hh_norm"].str.contains("chua chi du", regex=False)
    merged["is_khong_chi"] = merged["trang_thai_hh_norm"].str.contains("khong chi", regex=False)

    merged["ky_hd_month"] = _safe_datetime_month(merged.get("ngay_ky_hd"))
    merged["is_diem_moi_ky_hd"] = merged["ky_hd_month"].eq(merged["thang_nam"])

    diem_series = merged.get("id_dtt")
    if diem_series is None:
        diem_series = pd.Series(index=merged.index, dtype=object)
    merged["diem_key"] = diem_series
    if "id_dtt_dim" in merged.columns:
        merged["diem_key"] = merged["diem_key"].combine_first(merged["id_dtt_dim"])
    merged["diem_key"] = merged["diem_key"].combine_first(merged["diem_tiep_thi"])
    merged["diem_key"] = merged["diem_key"].fillna(merged["cost_id"])
    merged["diem_key"] = merged["diem_key"].astype(str)

    merged["loai_hinh_kd"] = merged.get("loai_hinh_kd").fillna("Chưa rõ loại hình")
    merged.loc[merged["loai_hinh_kd"].astype(str).str.strip().eq(""), "loai_hinh_kd"] = "Chưa rõ loại hình"

    if merged.empty:
        return pd.DataFrame(columns=expected_cols)

    records = []
    for (thang_nam, khu_vuc), grp in merged.groupby(["thang_nam", "khu_vuc"], dropna=False):
        so_diem = grp["diem_key"].nunique()
        so_ho_so = len(grp)
        tong_phai_chi = float(pd.to_numeric(grp["tong_phai_chi"], errors="coerce").fillna(0).sum())
        tong_da_chi_du = float(pd.to_numeric(grp.loc[grp["is_da_chi_du"], "tong_phai_chi"], errors="coerce").fillna(0).sum())
        tong_chua_chi_du = float(pd.to_numeric(grp.loc[grp["is_chua_chi_du"], "tong_phai_chi"], errors="coerce").fillna(0).sum())
        tong_khong_chi = float(pd.to_numeric(grp.loc[grp["is_khong_chi"], "tong_phai_chi"], errors="coerce").fillna(0).sum())
        records.append({
            "thang_nam": thang_nam,
            "khu_vuc": khu_vuc,
            "tong_phai_chi": tong_phai_chi,
            "so_diem_tiep_thi": int(so_diem),
            "so_ho_so_hoa_hong": int(so_ho_so),
            "tong_da_chi_du": tong_da_chi_du,
            "tong_chua_chi_du": tong_chua_chi_du,
            "tong_khong_chi": tong_khong_chi,
            "so_ho_so_da_chi_du": int(grp["is_da_chi_du"].sum()),
            "so_ho_so_chua_chi_du": int(grp["is_chua_chi_du"].sum()),
            "so_ho_so_khong_chi": int(grp["is_khong_chi"].sum()),
            "so_diem_moi_ky_hd": int(grp.loc[grp["is_diem_moi_ky_hd"], "diem_key"].nunique()),
            "so_loai_hinh_kd": int(grp["loai_hinh_kd"].astype(str).nunique()),
            "chi_phi_binh_quan_moi_diem": tong_phai_chi / max(int(so_diem), 1),
            "chi_phi_binh_quan_moi_ho_so": tong_phai_chi / max(int(so_ho_so), 1),
        })

    out = pd.DataFrame(records).sort_values(["thang_nam", "khu_vuc"]).reset_index(drop=True)
    out["tong_doanh_thu"] = out["tong_phai_chi"]
    out["tong_so_cuoc"] = out["so_diem_tiep_thi"]
    out["so_luong"] = out["so_diem_tiep_thi"]
    ordered_front = [
        "thang_nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc", "so_luong",
        "tong_phai_chi", "so_diem_tiep_thi", "so_ho_so_hoa_hong",
        "tong_da_chi_du", "tong_chua_chi_du", "tong_khong_chi",
        "so_ho_so_da_chi_du", "so_ho_so_chua_chi_du", "so_ho_so_khong_chi",
        "so_diem_moi_ky_hd", "so_loai_hinh_kd",
        "chi_phi_binh_quan_moi_diem", "chi_phi_binh_quan_moi_ho_so"
    ]
    keep_front = [c for c in ordered_front if c in out.columns]
    other_cols = [c for c in out.columns if c not in keep_front]

    return out[keep_front + other_cols].copy()


def _classify_vehicle_energy(value):
    s = _norm_text(value)
    if ("dien" in s) or ("electric" in s) or ("ev" == s):
        return "Xe điện"
    if ("xang" in s) or ("gasoline" in s) or ("petrol" in s) or ("fuel" in s):
        return "Xe xăng"
    return "Khác"


def _parse_vehicle_seat_count(series_like):
    s = series_like.astype(str).str.extract(r"(\d+)")[0]
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _resolve_snapshot_month(df_source: pd.DataFrame) -> pd.Series:
    if df_source is None or df_source.empty:
        base_month = END_DATE.to_period("M").to_timestamp() if pd.notna(END_DATE) else (
            START_DATE.to_period("M").to_timestamp() if pd.notna(START_DATE) else pd.Timestamp.today().to_period("M").to_timestamp()
        )
        return pd.Series(dtype="datetime64[ns]")

    month_col = _find_first_existing_col(df_source, [
        "thang_nam", "thang/nam", "thang nam", "month", "period",
        "updatedat", "updated_at", "ngay_cap_nhat", "ngay cap nhat",
        "createdat", "created_at", "ngay_tao", "ngay tao"
    ])
    if month_col:
        parsed = _safe_datetime_month(df_source[month_col])
        if parsed.notna().any():
            return parsed

    base_month = END_DATE.to_period("M").to_timestamp() if pd.notna(END_DATE) else (
        START_DATE.to_period("M").to_timestamp() if pd.notna(START_DATE) else pd.Timestamp.today().to_period("M").to_timestamp()
    )
    return pd.Series([base_month] * len(df_source), index=df_source.index)


def _prepare_vehicle_monthly_summary(df_vehicle_raw: pd.DataFrame):
    expected_cols = [
        "thang_nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu",
        "so_luong_xe", "tong_so_cho", "so_cho_binh_quan_xe",
        "so_bien_kiem_soat", "so_so_tai",
        "tong_doanh_thu", "tong_so_cuoc", "so_luong"
    ]
    empty = pd.DataFrame(columns=expected_cols)
    if df_vehicle_raw is None or df_vehicle_raw.empty:
        return empty.copy(), empty.copy()

    vf = df_vehicle_raw.copy()

    id_col = _find_first_existing_col(vf, ["id", "vehicle_id", "ma_xe", "ma xe"])
    plate_col = _find_first_existing_col(vf, ["bien_kiem_soat", "bien kiem soat", "bien_so", "bien so", "plate"])
    sotai_col = _find_first_existing_col(vf, ["so_tai", "so tai", "fleet_code", "ma_nhan_dien"])
    type_col = _find_first_existing_col(vf, ["loai_xe", "loai xe", "dong_xe", "dong xe", "model"])
    seat_col = _find_first_existing_col(vf, ["so_cho", "so cho", "seat", "seats"])
    fuel_col = _find_first_existing_col(vf, ["dien_xang", "dien xang", "nhien_lieu", "nhien lieu", "fuel_type", "fuel"])
    region_col = _find_first_existing_col(vf, ["khu_vuc", "khu vuc", "region", "area"])

    vehicle_key = pd.Series(index=vf.index, dtype=object)
    if plate_col:
        vehicle_key = vf[plate_col]
    if vehicle_key.isna().all() and sotai_col:
        vehicle_key = vf[sotai_col]
    if vehicle_key.isna().all() and id_col:
        vehicle_key = vf[id_col]
    if vehicle_key.isna().all():
        vehicle_key = pd.Series(range(1, len(vf) + 1), index=vf.index)

    work = pd.DataFrame({
        "thang_nam": _resolve_snapshot_month(vf),
        "vehicle_key": vehicle_key.astype(str),
        "bien_kiem_soat": vf[plate_col] if plate_col else pd.Series(index=vf.index, dtype=object),
        "so_tai": vf[sotai_col] if sotai_col else pd.Series(index=vf.index, dtype=object),
        "loai_xe": vf[type_col] if type_col else "Chưa rõ loại xe",
        "so_cho_raw": vf[seat_col] if seat_col else pd.Series(index=vf.index, dtype=object),
        "dien_xang": vf[fuel_col] if fuel_col else pd.Series(index=vf.index, dtype=object),
        "khu_vuc": vf[region_col] if region_col else "Tổng hợp",
    })

    work["thang_nam"] = pd.to_datetime(work["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    work["khu_vuc"] = work["khu_vuc"].fillna("Tổng hợp").astype(str).str.strip()
    work.loc[work["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"
    work["loai_xe"] = work["loai_xe"].fillna("Chưa rõ loại xe").astype(str).str.strip()
    work.loc[work["loai_xe"].eq(""), "loai_xe"] = "Chưa rõ loại xe"
    work["nhom_nhien_lieu"] = work["dien_xang"].apply(_classify_vehicle_energy)
    work["so_cho"] = _parse_vehicle_seat_count(work["so_cho_raw"])
    work["vehicle_key"] = work["vehicle_key"].fillna("").astype(str).str.strip()
    work.loc[work["vehicle_key"].eq(""), "vehicle_key"] = work.index.astype(str)

    if pd.notna(END_DATE):
        work = work[work["thang_nam"] <= END_DATE.to_period("M").to_timestamp()]
    if work.empty:
        return empty.copy(), empty.copy()

    agg = work.groupby(["thang_nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu"], as_index=False).agg(
        so_luong_xe=("vehicle_key", "nunique"),
        tong_so_cho=("so_cho", "sum"),
        so_bien_kiem_soat=("bien_kiem_soat", lambda s: s.astype(str).str.strip().replace({"": pd.NA}).dropna().nunique()),
        so_so_tai=("so_tai", lambda s: s.astype(str).str.strip().replace({"": pd.NA}).dropna().nunique()),
    )
    agg["so_cho_binh_quan_xe"] = agg["tong_so_cho"] / agg["so_luong_xe"].replace(0, 1)
    agg["tong_doanh_thu"] = agg["so_luong_xe"]
    agg["tong_so_cuoc"] = agg["tong_so_cho"]
    agg["so_luong"] = agg["so_luong_xe"]

    ordered = [
        "thang_nam", "khu_vuc", "loai_xe", "nhom_nhien_lieu",
        "so_luong_xe", "tong_so_cho", "so_cho_binh_quan_xe",
        "so_bien_kiem_soat", "so_so_tai",
        "tong_doanh_thu", "tong_so_cuoc", "so_luong"
    ]
    agg = agg[ordered].sort_values(["thang_nam", "khu_vuc", "loai_xe"]).reset_index(drop=True)

    xe_dien = agg[agg["nhom_nhien_lieu"].eq("Xe điện")].reset_index(drop=True)
    xe_xang = agg[agg["nhom_nhien_lieu"].eq("Xe xăng")].reset_index(drop=True)
    return xe_dien, xe_xang



def _classify_lenca_vehicle_prefix(series_like) -> pd.Series:
    """Classify dbo.danhSachLenCa rows into dashboard fleet prefixes."""
    s = pd.Series(series_like).fillna("").astype(str).apply(_norm_text)
    out = pd.Series("", index=s.index, dtype=object)
    xdt_mask = s.str.contains("xe cong ty|truc thuoc|xdt|xe dt|xe dien|cong ty|so huu", regex=True, na=False)
    xpq_mask = s.str.contains("thuong quyen|tra gop|hop tac|phan quyen|xpq|xe pq|nhuong quyen|doi tac|xe xang", regex=True, na=False)
    out.loc[xdt_mask] = "xdt"
    out.loc[xpq_mask] = "xpq"
    return out


def _lenca_vf3_mask(df_source: pd.DataFrame) -> pd.Series:
    """Detect VF3 service vehicles across likely text columns."""
    if df_source is None or df_source.empty:
        return pd.Series(dtype=bool)
    preferred = [
        "dong_xe", "dong xe", "model", "ten_dong_xe", "ten dong xe", "loai_xe", "loai xe",
        "nhan_hieu", "nhan hieu", "hang_xe", "hang xe", "ghi_chu", "ghi chu",
        "muc_dich_su_dung", "muc dich su dung",
    ]
    cols = []
    for cand in preferred:
        col = _find_first_existing_col(df_source, [cand])
        if col and col in df_source.columns and col not in cols:
            cols.append(col)
    if not cols:
        for col in df_source.columns:
            try:
                if pd.api.types.is_object_dtype(df_source[col]) or pd.api.types.is_string_dtype(df_source[col]):
                    cols.append(col)
            except Exception:
                continue
    if not cols:
        return pd.Series(False, index=df_source.index)
    joined = df_source[cols].fillna("").astype(str).agg(" ".join, axis=1).apply(_norm_key)
    compact = joined.str.replace(" ", "", regex=False)
    return compact.str.contains("vf3", na=False)


def _prepare_lenca_daily_fleet_snapshot(df_lenca_raw: pd.DataFrame):
    """Build daily available fleet snapshots from dbo.danhSachLenCa.

    Output is split into XDT/XPQ daily sheets so the Dash app can sum the two
    prefixes without double-counting. It includes parked/inactive/no-revenue
    vehicles if they are present in dbo.danhSachLenCa, excludes VF3, and never
    multiplies a monthly/latest snapshot by the number of days.
    """
    expected_cols = [
        "ngay_du_lieu", "khu_vuc", "bien_kiem_soat", "so_tai", "loai_hinh",
        "so_cho", "dong_xe", "trang_thai", "hinhthuc_kinhdoanh", "fleet_prefix", "so_luong_xe"
    ]
    empty = pd.DataFrame(columns=expected_cols)
    if df_lenca_raw is None or df_lenca_raw.empty:
        return empty.copy(), empty.copy()

    raw = df_lenca_raw.copy()
    date_col = _find_first_existing_col(raw, [
        "ngay_du_lieu", "ngay du lieu", "ngay", "date", "report_date", "ngay_bao_cao", "ngay bao cao",
        "ngay_len_ca", "ngay len ca", "ngay_lenca", "ngay lenca", "ngay_lam_viec", "ngay lam viec",
        "ngay_ca", "ngay ca", "ngay_ghi_nhan", "ngay ghi nhan", "ngay_cap_nhat", "ngay cap nhat",
        "createdat", "created_at", "updatedat", "updated_at", "thoi_gian_tao", "thoi gian tao",
        "thoigian_tao", "time", "timestamp",
    ])
    if date_col is None:
        print("[LENCA PIPELINE] khong tim thay cot ngay trong dbo.danhSachLenCa, bo qua XeDangCo_*_KV_Ngay")
        return empty.copy(), empty.copy()

    region_col = _find_first_existing_col(raw, [
        "khu_vuc", "khu vuc", "region", "area", "chi_nhanh", "chi nhanh", "don_vi", "don vi",
        "dia_ban", "dia ban", "tram", "tuyen",
    ])
    plate_col = _find_first_existing_col(raw, [
        "bien_kiem_soat", "bien kiem soat", "bien_so", "bien so", "bks", "license_plate", "plate",
    ])
    id_col = _find_first_existing_col(raw, ["id", "ma", "record_id", "vehicle_id", "ma_xe", "ma xe"])
    sotai_col = _find_first_existing_col(raw, ["so_tai", "so tai", "ma_tai", "ma tai", "vehicle_no", "taxi_no", "fleet_code"])
    type_col = _find_first_existing_col(raw, [
        "loaihinh_hoptac", "loai hinh hop tac", "loai_hinh_hop_tac", "loai_hinh", "loai hinh",
        "loai_xe", "loai xe", "nhom_xe", "nhom xe", "hinh_thuc_so_huu", "hinh thuc so huu",
        "hinh_thuc_quan_ly", "hinh thuc quan ly", "nguon_xe", "nguon xe",
    ])
    hinhthuc_col = _find_first_existing_col(raw, [
        "hinhthuc_kinhdoanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh",
        "hinh thuc kd", "hinh_thuc_kd", "kinh_doanh", "loai_kinh_doanh",
    ])
    seat_col = _find_first_existing_col(raw, ["so_cho", "so cho", "seat", "seats", "cho_ngoi", "cho ngoi", "suc_chua", "suc chua"])
    model_col = _find_first_existing_col(raw, [
        "dong_xe", "dong xe", "model", "ten_dong_xe", "ten dong xe", "loai_xe", "loai xe", "nhan_hieu", "nhan hieu", "hang_xe", "hang xe",
    ])
    status_col = _find_first_existing_col(raw, [
        "trangthai_len_xuong_ca", "trang thai len xuong ca", "trang_thai_len_xuong_ca",
        "trang_thai_lenca", "trang thai lenca", "trang_thai_len_ca", "trang thai len ca",
        "trang_thai", "trang thai", "tinh_trang", "tinh trang", "trang_thai_xe", "trang thai xe",
        "ghi_chu", "ghi chu",
    ])
    count_col = _find_first_existing_col(raw, ["so_luong_xe", "so luong xe", "so_xe", "so xe", "tong_so_xe", "tong so xe", "so_luong", "so luong", "quantity", "count"])
    sotai_text_col = _find_first_existing_col(raw, [
        "sotai_hoten_msnv", "so tai ho ten msnv", "so_tai_hoten_msnv",
        "sotai hoten", "so_tai_hoten", "ma_tai_hoten",
    ])

    work = pd.DataFrame(index=raw.index)
    work["ngay_du_lieu"] = pd.to_datetime(raw[date_col], errors="coerce").dt.normalize()
    work["khu_vuc"] = raw[region_col] if region_col else "Tổng hợp"
    work["bien_kiem_soat"] = raw[plate_col] if plate_col else pd.Series(index=raw.index, dtype=object)
    work["so_tai"] = raw[sotai_col] if sotai_col else pd.Series(index=raw.index, dtype=object)
    work["loai_hinh"] = raw[type_col] if type_col else ""
    work["hinhthuc_kinhdoanh"] = raw[hinhthuc_col] if hinhthuc_col else ""
    work["so_cho"] = raw[seat_col] if seat_col else pd.Series(index=raw.index, dtype=object)
    work["dong_xe"] = raw[model_col] if model_col else pd.Series(index=raw.index, dtype=object)
    work["trang_thai"] = raw[status_col] if status_col else ""
    work["so_luong_xe"] = pd.to_numeric(raw[count_col], errors="coerce").fillna(0) if count_col else 1

    # Build the strongest possible vehicle key. The app counts distinct
    # bien_kiem_soat when that column exists, so fill it from so_tai /
    # sotai_hoten_msnv when BKS is blank instead of leaving it empty.
    if sotai_text_col and sotai_text_col in raw.columns:
        sotai_from_text = raw[sotai_text_col].fillna("").astype(str).str.extract(r"([A-Za-z]{1,4}\d{2,6})")[0]
        work["so_tai"] = work["so_tai"].where(work["so_tai"].fillna("").astype(str).str.strip().ne(""), sotai_from_text)
    work["bien_kiem_soat"] = work["bien_kiem_soat"].where(work["bien_kiem_soat"].fillna("").astype(str).str.strip().ne(""), work["so_tai"])
    if id_col and id_col in raw.columns:
        work["bien_kiem_soat"] = work["bien_kiem_soat"].where(work["bien_kiem_soat"].fillna("").astype(str).str.strip().ne(""), raw[id_col])
    work["bien_kiem_soat"] = work["bien_kiem_soat"].where(work["bien_kiem_soat"].fillna("").astype(str).str.strip().ne(""), raw.index.astype(str))

    work = work[work["ngay_du_lieu"].notna()].copy()
    if pd.notna(START_DATE):
        work = work[work["ngay_du_lieu"] >= START_DATE.normalize()]
    if pd.notna(END_DATE):
        work = work[work["ngay_du_lieu"] <= END_DATE.normalize()]
    if work.empty:
        return empty.copy(), empty.copy()

    for col in ["khu_vuc", "bien_kiem_soat", "so_tai", "loai_hinh", "so_cho", "dong_xe", "trang_thai", "hinhthuc_kinhdoanh"]:
        work[col] = work[col].fillna("").astype(str).str.strip()
    work.loc[work["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"
    # Normalize common branch aliases before export so Dash merges revenue and fleet rows correctly.
    _region_alias = {
        "phuquoc": "Phú Quốc", "phu quoc": "Phú Quốc", "pq": "Phú Quốc",
        "rachgia": "Rạch Giá", "rach gia": "Rạch Giá", "rg": "Rạch Giá",
        "baclieu": "Bạc Liêu", "bac lieu": "Bạc Liêu", "bl": "Bạc Liêu",
        "camau": "Cà Mau", "ca mau": "Cà Mau", "cm": "Cà Mau",
        "vinhlong": "Vĩnh Long", "vinh long": "Vĩnh Long", "vl": "Vĩnh Long",
        "angiang": "An Giang", "an giang": "An Giang", "ag": "An Giang",
        "cantho": "Cần Thơ", "can tho": "Cần Thơ", "ct": "Cần Thơ",
        "haugiang": "Hậu Giang", "hau giang": "Hậu Giang", "hg": "Hậu Giang",
        "soctrang": "Sóc Trăng", "soc trang": "Sóc Trăng", "st": "Sóc Trăng",
    }
    work["khu_vuc"] = work["khu_vuc"].apply(lambda x: _region_alias.get(_norm_key(x).replace(" ", ""), _region_alias.get(_norm_key(x), x)))

    # Business rule from operations:
    # - count both len ca and xuong ca records
    # - never keep Xe cong vu
    # - outside Phu Quoc, exclude Khoan dien from both xe dang co and xe kinh doanh denominators
    # - Phu Quoc is the exception: Khoan dien / Dien an chia are still valid electric taxi operations
    # - if hinhthuc_kinhdoanh is blank AND the row is Xuong ca, keep it too
    #   because these rows represent xe dang co / nam bai / no-revenue vehicles.
    ht_norm = work["hinhthuc_kinhdoanh"].apply(_norm_text)
    status_norm = work["trang_thai"].apply(_norm_text)
    is_len_ca = status_norm.str.contains("len ca", regex=False, na=False)
    is_xuong_ca = status_norm.str.contains("xuong ca", regex=False, na=False)
    is_cong_vu = ht_norm.str.contains("cong vu", regex=False, na=False)
    # In danhSachLenCa, blank hinhthuc_kinhdoanh may arrive as empty string
    # or as Excel time-like placeholders such as 00:00:00 / 05:00:00.
    is_blank_ht = ht_norm.eq("") | ht_norm.str.fullmatch(r"\d{1,2}[:\s]\d{2}([:\s]\d{2})?", na=False)
    is_phu_quoc = _is_phu_quoc_series(work["khu_vuc"])
    is_khoan_dien = _is_khoan_dien_series(work["hinhthuc_kinhdoanh"])
    is_taxi_dien = ht_norm.str.contains("taxi dien", regex=False, na=False)
    is_dien_an_chia = ht_norm.str.contains("dien an chia", regex=False, na=False)
    keep_electric_business = is_taxi_dien | is_dien_an_chia | (is_khoan_dien & is_phu_quoc)
    keep_business = (is_len_ca | is_xuong_ca) & (~is_cong_vu) & (keep_electric_business | (is_blank_ht & is_xuong_ca))
    work = work.loc[keep_business].copy()
    if work.empty:
        print("[LENCA PIPELINE] khong co row xe dien / Xuong ca hop le sau khi loai Xe cong vu")
        return empty.copy(), empty.copy()

    # When loaihinh_hoptac is blank on kept Xuong ca rows, treat it as Xe Cong ty
    # so parked/down vehicles are still counted in the available fleet denominator.
    blank_type = work["loai_hinh"].apply(_norm_text).eq("")
    xuong_type = work["trang_thai"].apply(_norm_text).str.contains("xuong ca", regex=False, na=False)
    work.loc[blank_type & xuong_type, "loai_hinh"] = "Xe Công ty"

    # Exclude VF3 service vehicles before snapshot aggregation.
    vf3_mask = _lenca_vf3_mask(raw.loc[work.index])
    if len(vf3_mask) == len(work):
        work = work.loc[~vf3_mask.values].copy()
    if work.empty:
        return empty.copy(), empty.copy()

    # Classify by real vehicle type/source. Rows that cannot be classified are not
    # forced into a bucket, because that would distort XDT/XPQ denominators.
    classify_text = (
        work["loai_hinh"].fillna("").astype(str) + " " +
        work["dong_xe"].fillna("").astype(str) + " " +
        work["trang_thai"].fillna("").astype(str)
    )
    work["fleet_prefix"] = _classify_lenca_vehicle_prefix(classify_text)
    work = work[work["fleet_prefix"].isin(["xdt", "xpq"])].copy()
    if work.empty:
        print("[LENCA PIPELINE] co du lieu danhSachLenCa nhung khong phan loai duoc XDT/XPQ, bo qua")
        return empty.copy(), empty.copy()

    # If plate is available, one vehicle can appear multiple times per day/shift;
    # keep one row per vehicle-day-region-prefix. If there is only a count column,
    # aggregate counts by day/region/prefix.
    if work["bien_kiem_soat"].astype(str).str.strip().ne("").any():
        work = work[work["bien_kiem_soat"].astype(str).str.strip().ne("")].copy()
        work = work.drop_duplicates(subset=["ngay_du_lieu", "khu_vuc", "bien_kiem_soat", "fleet_prefix"], keep="last")
        work["so_luong_xe"] = 1
    else:
        work["so_luong_xe"] = pd.to_numeric(work["so_luong_xe"], errors="coerce").fillna(0)
        work = work[work["so_luong_xe"] > 0].copy()

    work = work[expected_cols].sort_values(["ngay_du_lieu", "khu_vuc", "fleet_prefix", "bien_kiem_soat"]).reset_index(drop=True)
    return (
        work[work["fleet_prefix"].eq("xdt")].reset_index(drop=True),
        work[work["fleet_prefix"].eq("xpq")].reset_index(drop=True),
    )


def _first_series_or_default(df_source: pd.DataFrame, col_name, default_value=None):
    if col_name and col_name in df_source.columns:
        return df_source[col_name]
    return pd.Series([default_value] * len(df_source), index=df_source.index)


def _extract_numeric_seat_count(series_like):
    s = pd.Series(series_like).astype(str).str.extract(r"(\d+)")[0]
    return pd.to_numeric(s, errors="coerce").fillna(0)



def _prepare_daily_checker_outputs(df_source: pd.DataFrame):
    """
    Build all daily checker outputs once in the refresh pipeline.
    App-level callbacks should only filter these already-aggregated sheets.
    This is intentionally wider than the menu currently needs so driver filters
    never have to re-group a raw sheet during dashboard interaction.
    """
    base_cols = [
        "ngay_du_lieu", "thang_nam", "khu_vuc", "tong_doanh_thu", "tong_so_cuoc",
        "sokm_vandoanh", "sokm_cokhach", "so_xe", "so_tai_xe", "so_tai", "bks",
        "doanh_thu_binh_quan_cuoc", "doanh_thu_binh_quan_xe", "cuoc_binh_quan_xe",
        "km_co_khach_ratio", "km_rong", "doanh_thu_moi_km_vd", "doanh_thu_moi_km_khach",
        "so_luong",
    ]

    def _empty(extra_cols=None):
        extra_cols = extra_cols or []
        return pd.DataFrame(columns=base_cols + [c for c in extra_cols if c not in base_cols])

    empty_base = _empty()
    empty_lh = _empty(["loaihinh_hoptac"])
    empty_hinhthuc = _empty(["hinhthuc_kinhdoanh"])
    empty_luong = _empty(["loai_luong"])
    empty_socho = _empty(["so_cho", "so_cho_num"])
    empty_taixe = _empty(["so_tai", "bks", "ho_ten"])
    empty_taixe_lh = _empty(["so_tai", "bks", "ho_ten", "loaihinh_hoptac"])
    empty_taixe_hinhthuc = _empty(["so_tai", "bks", "ho_ten", "hinhthuc_kinhdoanh"])
    empty_taixe_luong = _empty(["so_tai", "bks", "ho_ten", "loai_luong"])
    empty_taixe_socho = _empty(["so_tai", "bks", "ho_ten", "so_cho", "so_cho_num"])
    empty_raw = pd.DataFrame(columns=[
        "id", "ngay_du_lieu", "thang_nam", "bks", "so_tai", "ho_ten", "doanh_thu", "so_cuoc",
        "sokm_vandoanh", "sokm_cokhach", "loaihinh_hoptac", "hinhthuc_kinhdoanh", "loai_luong",
        "so_cho", "so_cho_num", "khu_vuc", "bks_xe_kinh_doanh",
    ])

    empty_tuple = (
        empty_base, empty_lh, empty_hinhthuc, empty_luong, empty_socho, empty_taixe,
        empty_taixe_lh, empty_taixe_hinhthuc, empty_taixe_luong, empty_taixe_socho, empty_raw,
    )
    if df_source is None or df_source.empty:
        return empty_tuple

    dff = df_source.copy()
    date_col = _find_first_existing_col(dff, ["thoi_gian_tao", "ngay_du_lieu", "ngay du lieu", "ngay", "date", "report_date", "ngay_bao_cao", "created_at", "updated_at"])
    month_col = _find_first_existing_col(dff, ["thang_nam", "thang nam", "thang/nam", "month", "period"])
    region_col = _find_first_existing_col(dff, ["khu_vuc", "khu vuc", "region", "area", "chi_nhanh", "don_vi"])
    id_col = _find_first_existing_col(dff, ["id", "ma", "record_id"])
    bks_col = _find_first_existing_col(dff, ["bks", "bien_kiem_soat", "bien kiem soat", "bien_so", "bien so"])
    sotai_col = _find_first_existing_col(dff, ["so_tai", "so tai", "ma_tai", "ma tai"])
    driver_col = _find_first_existing_col(dff, ["ho_ten", "ho ten", "tai_xe", "tai xe", "ten_tai_xe", "driver"])
    revenue_col = _find_first_existing_col(dff, ["doanh_thu", "doanh thu", "tong_doanh_thu", "revenue", "amount"])
    trip_col = _find_first_existing_col(dff, ["so_cuoc", "so cuoc", "tong_so_cuoc", "trips", "trip_count"])
    km_vd_col = _find_first_existing_col(dff, ["sokm_vandoanh", "so km van doanh", "km_van_doanh", "km van doanh", "tong_km", "km_total"])
    km_khach_col = _find_first_existing_col(dff, ["sokm_cokhach", "so km co khach", "km_co_khach", "km co khach", "km_khach"])
    loaihinh_col = _find_first_existing_col(dff, ["loaihinh_hoptac", "loai hinh hop tac", "loai_hinh_hoptac", "loai_hinh", "loai hinh"])
    hinhthuc_col = _find_first_existing_col(dff, ["hinhthuc_kinhdoanh", "hinh thuc kinh doanh", "hinh_thuc_kinh_doanh", "kenh_kinh_doanh"])
    luong_col = _find_first_existing_col(dff, ["loai_luong", "loai luong", "nhom_luong"])
    socho_col = _find_first_existing_col(dff, ["so_cho", "so cho", "seat", "seats"])

    if date_col is None:
        return empty_tuple

    work = pd.DataFrame(index=dff.index)
    work["id"] = _first_series_or_default(dff, id_col, None)
    work["ngay_du_lieu"] = pd.to_datetime(dff[date_col], errors="coerce").dt.normalize()
    if month_col:
        work["thang_nam"] = pd.to_datetime(dff[month_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    else:
        work["thang_nam"] = work["ngay_du_lieu"].dt.to_period("M").dt.to_timestamp()

    work["khu_vuc"] = _first_series_or_default(dff, region_col, "Tổng hợp").fillna("Tổng hợp").astype(str).str.strip()
    work.loc[work["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"
    work["bks"] = _first_series_or_default(dff, bks_col, None)
    work["so_tai"] = _first_series_or_default(dff, sotai_col, None)
    work["ho_ten"] = _first_series_or_default(dff, driver_col, "Chưa rõ tài xế").fillna("Chưa rõ tài xế").astype(str).str.strip()
    work.loc[work["ho_ten"].eq(""), "ho_ten"] = "Chưa rõ tài xế"

    work["doanh_thu"] = pd.to_numeric(_first_series_or_default(dff, revenue_col, 0), errors="coerce").fillna(0)
    work["so_cuoc"] = pd.to_numeric(_first_series_or_default(dff, trip_col, 0), errors="coerce").fillna(0)
    work["sokm_vandoanh"] = pd.to_numeric(_first_series_or_default(dff, km_vd_col, 0), errors="coerce").fillna(0)
    work["sokm_cokhach"] = pd.to_numeric(_first_series_or_default(dff, km_khach_col, 0), errors="coerce").fillna(0)

    work["loaihinh_hoptac"] = _first_series_or_default(dff, loaihinh_col, "Chưa rõ loại hình").fillna("Chưa rõ loại hình").astype(str).str.strip()
    work.loc[work["loaihinh_hoptac"].eq(""), "loaihinh_hoptac"] = "Chưa rõ loại hình"
    work["hinhthuc_kinhdoanh"] = _first_series_or_default(dff, hinhthuc_col, "Chưa rõ hình thức").fillna("Chưa rõ hình thức").astype(str).str.strip()
    work.loc[work["hinhthuc_kinhdoanh"].eq(""), "hinhthuc_kinhdoanh"] = "Chưa rõ hình thức"
    work["loai_luong"] = _first_series_or_default(dff, luong_col, "Chưa rõ loại lương").fillna("Chưa rõ loại lương").astype(str).str.strip()
    work.loc[work["loai_luong"].eq(""), "loai_luong"] = "Chưa rõ loại lương"
    work["so_cho"] = _first_series_or_default(dff, socho_col, "Chưa rõ số chỗ").fillna("Chưa rõ số chỗ").astype(str).str.strip()
    work.loc[work["so_cho"].eq(""), "so_cho"] = "Chưa rõ số chỗ"
    work["so_cho_num"] = _extract_numeric_seat_count(work["so_cho"])

    work = work[work["ngay_du_lieu"].notna()].copy()
    if pd.notna(START_DATE):
        work = work[work["ngay_du_lieu"] >= START_DATE.normalize()]
    if pd.notna(END_DATE):
        work = work[work["ngay_du_lieu"] <= END_DATE.normalize()]
    if work.empty:
        return empty_tuple

    for col in ["khu_vuc", "bks", "so_tai", "ho_ten", "loaihinh_hoptac", "hinhthuc_kinhdoanh", "loai_luong", "so_cho"]:
        if col in work.columns:
            work[col] = work[col].fillna("").astype(str).str.strip()

    # Daily revenue business rule:
    # Outside Phu Quoc, Khoan dien must be removed from every Daily metric
    # (revenue, trips, KM, active vehicles, averages, charts and detail tables).
    # Phu Quoc is the only exception where Khoan dien remains valid.
    is_pq_daily = _is_phu_quoc_series(work["khu_vuc"])
    is_khoan_daily = _is_khoan_dien_series(work["hinhthuc_kinhdoanh"])
    khoan_outside_pq = is_khoan_daily & ~is_pq_daily
    if bool(khoan_outside_pq.any()):
        print(f"[DAILY CHECKER PIPELINE] drop Khoan dien outside Phu Quoc rows={int(khoan_outside_pq.sum())}")
        work = work.loc[~khoan_outside_pq].copy()
    work["bks_xe_kinh_doanh"] = work["bks"]

    def _nunique_clean(series):
        return series.fillna("").astype(str).str.strip().replace({"": pd.NA}).dropna().nunique()

    def _finalize_daily_group(grouped: pd.DataFrame) -> pd.DataFrame:
        grouped = grouped.copy()
        grouped["doanh_thu_binh_quan_cuoc"] = grouped["tong_doanh_thu"] / grouped["tong_so_cuoc"].replace(0, 1)
        grouped["doanh_thu_binh_quan_xe"] = grouped["tong_doanh_thu"] / grouped["so_xe"].replace(0, 1)
        grouped["cuoc_binh_quan_xe"] = grouped["tong_so_cuoc"] / grouped["so_xe"].replace(0, 1)
        grouped["km_co_khach_ratio"] = grouped["sokm_cokhach"] / grouped["sokm_vandoanh"].replace(0, 1) * 100
        grouped["km_rong"] = (grouped["sokm_vandoanh"] - grouped["sokm_cokhach"]).clip(lower=0)
        grouped["doanh_thu_moi_km_vd"] = grouped["tong_doanh_thu"] / grouped["sokm_vandoanh"].replace(0, 1)
        grouped["doanh_thu_moi_km_khach"] = grouped["tong_doanh_thu"] / grouped["sokm_cokhach"].replace(0, 1)
        grouped["so_luong"] = grouped["so_xe"]
        return grouped.sort_values(["ngay_du_lieu", "khu_vuc"]).reset_index(drop=True)

    def _agg_by(keys):
        agg_spec = {
            "tong_doanh_thu": ("doanh_thu", "sum"),
            "tong_so_cuoc": ("so_cuoc", "sum"),
            "sokm_vandoanh": ("sokm_vandoanh", "sum"),
            "sokm_cokhach": ("sokm_cokhach", "sum"),
            "so_xe": ("bks_xe_kinh_doanh", _nunique_clean),
            "so_tai_xe": ("ho_ten", _nunique_clean),
        }
        if "so_tai" not in keys:
            agg_spec["so_tai"] = ("so_tai", _nunique_clean)
        if "bks" not in keys:
            agg_spec["bks"] = ("bks", _nunique_clean)
        out = work.groupby(keys, as_index=False, dropna=False, sort=False).agg(**agg_spec)
        if "so_tai" not in out.columns:
            out["so_tai"] = out["so_tai_xe"]
        if "bks" not in out.columns:
            out["bks"] = out["so_xe"]
        return _finalize_daily_group(out)

    base = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc"])
    by_lh = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "loaihinh_hoptac"])
    by_hinhthuc = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "hinhthuc_kinhdoanh"])
    by_luong = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "loai_luong"])
    by_socho = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "so_cho", "so_cho_num"])

    by_taixe = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "so_tai", "bks", "ho_ten"])
    by_taixe_lh = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "so_tai", "bks", "ho_ten", "loaihinh_hoptac"])
    by_taixe_hinhthuc = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "so_tai", "bks", "ho_ten", "hinhthuc_kinhdoanh"])
    by_taixe_luong = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "so_tai", "bks", "ho_ten", "loai_luong"])
    by_taixe_socho = _agg_by(["ngay_du_lieu", "thang_nam", "khu_vuc", "so_tai", "bks", "ho_ten", "so_cho", "so_cho_num"])

    raw_cols = [
        "id", "ngay_du_lieu", "thang_nam", "bks", "so_tai", "ho_ten", "doanh_thu", "so_cuoc",
        "sokm_vandoanh", "sokm_cokhach", "loaihinh_hoptac", "hinhthuc_kinhdoanh", "loai_luong",
        "so_cho", "so_cho_num", "khu_vuc", "bks_xe_kinh_doanh"
    ]
    raw_out = work[raw_cols].copy() if DAILY_CHECKER_EXPORT_RAW else empty_raw
    return (
        base, by_lh, by_hinhthuc, by_luong, by_socho, by_taixe,
        by_taixe_lh, by_taixe_hinhthuc, by_taixe_luong, by_taixe_socho, raw_out,
    )

def _is_driver_role(role_value):
    s = _norm_text(role_value)
    return ("lai xe" in s) or ("tai xe" in s) or ("driver" in s)


def _classify_lifecycle(years_value):
    try:
        y = float(years_value)
    except Exception:
        y = 0.0
    if y < 1:
        return "duoi_1_nam"
    if y <= 3:
        return "tu_1_den_3_nam"
    return "tren_3_nam"


def _build_hr_monthly_summary(df_source):
    dff = df_source.copy()

    for col in ["NGAY_THU_VIEC", "NGAY_CHINH_THUC", "NGAY_NGHI_VIEC", "UpdatedAt"]:
        dff[col] = pd.to_datetime(dff[col], errors="coerce")

    dff["VONG_DOI"] = pd.to_numeric(dff.get("VONG_DOI"), errors="coerce")
    dff["ngay_bat_dau"] = dff["NGAY_CHINH_THUC"].combine_first(dff["NGAY_THU_VIEC"])
    dff["ngay_bat_dau"] = dff["ngay_bat_dau"].fillna(dff["UpdatedAt"])

    status_norm = dff["TRANG_THAI"].apply(_norm_text)
    dff["is_nghi_viec"] = status_norm.str.contains("nghi viec", regex=False)

    dff["ngay_ket_thuc"] = dff["NGAY_NGHI_VIEC"]
    dff.loc[dff["is_nghi_viec"] & dff["ngay_ket_thuc"].isna(), "ngay_ket_thuc"] = dff.loc[
        dff["is_nghi_viec"] & dff["ngay_ket_thuc"].isna(), "UpdatedAt"
    ]
    dff["ngay_ket_thuc"] = dff["ngay_ket_thuc"].fillna(END_DATE)

    dff = dff[dff["ngay_bat_dau"].notna()].copy()
    dff["ngay_bat_dau"] = dff["ngay_bat_dau"].clip(lower=START_DATE, upper=END_DATE)
    dff["ngay_ket_thuc"] = dff["ngay_ket_thuc"].clip(lower=START_DATE, upper=END_DATE)
    dff = dff[dff["ngay_bat_dau"] <= dff["ngay_ket_thuc"]].copy()

    dff["khu_vuc"] = dff["KHU_VUC"].fillna(dff["DIA_DIEM_LAM_VIEC"])
    dff["khu_vuc"] = dff["khu_vuc"].fillna("Tổng hợp")
    dff["khu_vuc"] = dff["khu_vuc"].astype(str).str.strip()
    dff.loc[dff["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"

    dff["bo_phan"] = dff["DON_VI_CT"].fillna("Chưa rõ bộ phận")
    dff["bo_phan"] = dff["bo_phan"].astype(str).str.strip()
    dff.loc[dff["bo_phan"].eq(""), "bo_phan"] = "Chưa rõ bộ phận"

    records = []
    for row in dff.itertuples(index=False):
        start_month = row.ngay_bat_dau.to_period("M").to_timestamp()
        end_month = row.ngay_ket_thuc.to_period("M").to_timestamp()
        leave_month = row.NGAY_NGHI_VIEC.to_period("M").to_timestamp() if pd.notna(row.NGAY_NGHI_VIEC) else pd.NaT
        for month_start in pd.date_range(start_month, end_month, freq="MS"):
            month_end = month_start + pd.offsets.MonthEnd(0)
            computed_years = max((month_end - row.ngay_bat_dau).days / 365.25, 0)
            lifecycle_years = row.VONG_DOI if pd.notna(row.VONG_DOI) and pd.notna(leave_month) and month_start == leave_month else computed_years
            lifecycle_group = _classify_lifecycle(lifecycle_years)
            vao_lam = int(month_start == start_month)
            nghi_viec = int(pd.notna(leave_month) and month_start == leave_month and bool(row.is_nghi_viec))
            records.append({
                "thang_nam": month_start,
                "khu_vuc": row.khu_vuc,
                "bo_phan": row.bo_phan,
                "ID_NV": row.ID_NV,
                "so_luong_nhan_su": 1,
                "so_vao_lam": vao_lam,
                "so_nghi_viec": nghi_viec,
                "so_duoi_1_nam": 1 if lifecycle_group == "duoi_1_nam" else 0,
                "so_tu_1_den_3_nam": 1 if lifecycle_group == "tu_1_den_3_nam" else 0,
                "so_tren_3_nam": 1 if lifecycle_group == "tren_3_nam" else 0,
            })

    if not records:
        return pd.DataFrame(columns=[
            "thang_nam", "khu_vuc", "bo_phan", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec",
            "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam", "headcount_dau_ky",
            "so_giu_on_dinh", "bien_dong_thuan", "ty_le_tang", "ty_le_giam", "ty_le_giu_chan", "chi_phi"
        ])

    detail = pd.DataFrame(records)
    result = detail.groupby(["thang_nam", "khu_vuc", "bo_phan"], as_index=False).agg(
        so_luong_nhan_su=("ID_NV", "nunique"),
        so_vao_lam=("so_vao_lam", "sum"),
        so_nghi_viec=("so_nghi_viec", "sum"),
        so_duoi_1_nam=("so_duoi_1_nam", "sum"),
        so_tu_1_den_3_nam=("so_tu_1_den_3_nam", "sum"),
        so_tren_3_nam=("so_tren_3_nam", "sum"),
    )

    result = result.sort_values(["khu_vuc", "bo_phan", "thang_nam"]).reset_index(drop=True)
    result["headcount_dau_ky"] = result.groupby(["khu_vuc", "bo_phan"])["so_luong_nhan_su"].shift(1)
    fallback_opening = (result["so_luong_nhan_su"] - result["so_vao_lam"] + result["so_nghi_viec"]).clip(lower=0)
    result["headcount_dau_ky"] = result["headcount_dau_ky"].fillna(fallback_opening)
    result["so_giu_on_dinh"] = (result["so_luong_nhan_su"] - result["so_vao_lam"]).clip(lower=0)
    result["bien_dong_thuan"] = result["so_vao_lam"] - result["so_nghi_viec"]
    result["ty_le_tang"] = (result["so_vao_lam"] / result["headcount_dau_ky"].clip(lower=1) * 100).round(2)
    result["ty_le_giam"] = (result["so_nghi_viec"] / result["headcount_dau_ky"].clip(lower=1) * 100).round(2)
    result["ty_le_giu_chan"] = (result["so_giu_on_dinh"] / result["headcount_dau_ky"].clip(lower=1) * 100).round(2)
    result["chi_phi"] = 0
    return result.reset_index(drop=True)


df_ns["VI_TRI_CONG_VIEC_norm"] = df_ns["VI_TRI_CONG_VIEC"].apply(_norm_text)

df_ns_drv = df_ns[df_ns["VI_TRI_CONG_VIEC"].apply(_is_driver_role)].copy()
df_ns_emp = df_ns[~df_ns["VI_TRI_CONG_VIEC"].apply(_is_driver_role)].copy()

nhansu_nhanvien_kv_thang = _build_hr_monthly_summary(df_ns_emp)
nhansu_taixe_kv_thang = _build_hr_monthly_summary(df_ns_drv)


def _make_hr_dashboard_compatible(dff: pd.DataFrame, count_alias: str) -> pd.DataFrame:
    out = dff.copy()

    num_cols = [
        "chi_phi",
        "so_luong_nhan_su",
        "so_vao_lam",
        "so_nghi_viec",
        "so_duoi_1_nam",
        "so_tu_1_den_3_nam",
        "so_tren_3_nam",
        "headcount_dau_ky",
        "so_giu_on_dinh",
        "bien_dong_thuan",
        "ty_le_tang",
        "ty_le_giam",
        "ty_le_giu_chan",
    ]
    for c in num_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    if "thang_nam" in out.columns:
        out["thang_nam"] = pd.to_datetime(out["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()

    if "khu_vuc" in out.columns:
        out["khu_vuc"] = out["khu_vuc"].fillna("Tổng hợp").astype(str).str.strip()
        out.loc[out["khu_vuc"].eq(""), "khu_vuc"] = "Tổng hợp"

    if "bo_phan" in out.columns:
        out["bo_phan"] = out["bo_phan"].fillna("Chưa rõ bộ phận").astype(str).str.strip()
        out.loc[out["bo_phan"].eq(""), "bo_phan"] = "Chưa rõ bộ phận"

    if "chi_phi" not in out.columns:
        out["chi_phi"] = 0
    if "so_luong_nhan_su" not in out.columns:
        out["so_luong_nhan_su"] = 0

    out["tong_doanh_thu"] = pd.to_numeric(out["chi_phi"], errors="coerce").fillna(0)
    out["tong_so_cuoc"] = pd.to_numeric(out["so_luong_nhan_su"], errors="coerce").fillna(0)
    out["so_luong"] = out["tong_so_cuoc"]
    out[count_alias] = out["tong_so_cuoc"]

    ordered_front = [
        "thang_nam", "khu_vuc", "bo_phan",
        "tong_doanh_thu", "tong_so_cuoc", "so_luong", count_alias,
        "chi_phi", "so_luong_nhan_su", "so_vao_lam", "so_nghi_viec",
        "so_duoi_1_nam", "so_tu_1_den_3_nam", "so_tren_3_nam",
        "headcount_dau_ky", "so_giu_on_dinh", "bien_dong_thuan",
        "ty_le_tang", "ty_le_giam", "ty_le_giu_chan"
    ]
    keep_front = [c for c in ordered_front if c in out.columns]
    other_cols = [c for c in out.columns if c not in keep_front]
    return out[keep_front + other_cols].copy()


nhansu_nhanvien_kv_thang = _make_hr_dashboard_compatible(
    nhansu_nhanvien_kv_thang,
    "so_nhan_vien"
)

nhansu_taixe_kv_thang = _make_hr_dashboard_compatible(
    nhansu_taixe_kv_thang,
    "so_tai_xe"
)

# =========================
# BIEN BAN
# =========================
df_bb["thang_nam"] = pd.to_datetime(df_bb.get("thang_nam"), errors="coerce").dt.to_period("M").dt.to_timestamp()
if pd.notna(START_DATE):
    df_bb = df_bb[df_bb["thang_nam"] >= START_DATE.to_period("M").to_timestamp()]
if pd.notna(END_DATE):
    df_bb = df_bb[df_bb["thang_nam"] <= END_DATE.to_period("M").to_timestamp()]
df_bb["TONG_TIEN_DE_XUAT"] = pd.to_numeric(df_bb.get("TONG_TIEN_DE_XUAT"), errors="coerce").fillna(0)
df_bb["CON_LAI"] = pd.to_numeric(df_bb.get("CON_LAI"), errors="coerce").fillna(0)
df_bb["KHU_VUC"] = df_bb.get("KHU_VUC").fillna("Tổng hợp").astype(str).str.strip()
df_bb.loc[df_bb["KHU_VUC"].eq(""), "KHU_VUC"] = "Tổng hợp"

df_bb["TINH_TRANG_BIEN_BAN_norm"] = df_bb.get("TINH_TRANG_BIEN_BAN").apply(_norm_text)
df_bb["TRANG_THAI_THU_norm"] = df_bb.get("TRANG_THAI_THU").apply(_norm_text)

df_bb = df_bb[df_bb["thang_nam"].notna()].copy()
if pd.notna(START_DATE):
    start_month = START_DATE.to_period("M").to_timestamp()
    df_bb = df_bb[df_bb["thang_nam"] >= start_month]
if pd.notna(END_DATE):
    end_month = END_DATE.to_period("M").to_timestamp()
    df_bb = df_bb[df_bb["thang_nam"] <= end_month]

df_bb["so_tien_thu_duoc"] = (df_bb["TONG_TIEN_DE_XUAT"] - df_bb["CON_LAI"]).clip(lower=0)
df_bb["so_tien_con_no"] = df_bb["CON_LAI"].clip(lower=0)
df_bb["so_tien_da_xu_ly"] = 0
mask_da_xu_ly = df_bb["TINH_TRANG_BIEN_BAN_norm"].str.contains("da xu ly", regex=False)
df_bb.loc[mask_da_xu_ly, "so_tien_da_xu_ly"] = df_bb.loc[mask_da_xu_ly, "TONG_TIEN_DE_XUAT"]

df_bb["so_bien_ban"] = 1
df_bb["so_bien_ban_da_xu_ly"] = mask_da_xu_ly.astype(int)
df_bb["so_bien_ban_thu_hoan_tat"] = df_bb["TRANG_THAI_THU_norm"].str.contains("thu hoan tat", regex=False).astype(int)
df_bb["tong_doanh_thu"] = df_bb["so_tien_thu_duoc"]
df_bb["tong_so_cuoc"] = df_bb["so_bien_ban"]

bienban_kv_thang = df_bb.groupby(
    ["thang_nam", "KHU_VUC"], as_index=False
).agg(
    tong_tien_de_xuat=("TONG_TIEN_DE_XUAT", "sum"),
    so_tien_thu_duoc=("so_tien_thu_duoc", "sum"),
    so_tien_da_xu_ly=("so_tien_da_xu_ly", "sum"),
    so_tien_con_no=("so_tien_con_no", "sum"),
    so_bien_ban=("so_bien_ban", "sum"),
    so_bien_ban_da_xu_ly=("so_bien_ban_da_xu_ly", "sum"),
    so_bien_ban_thu_hoan_tat=("so_bien_ban_thu_hoan_tat", "sum"),
)

bienban_kv_thang = bienban_kv_thang.rename(columns={"KHU_VUC": "khu_vuc"})
bienban_kv_thang["tong_doanh_thu"] = bienban_kv_thang["so_tien_thu_duoc"]
bienban_kv_thang["tong_so_cuoc"] = bienban_kv_thang["so_bien_ban"]

print(
    "[BIEN BAN PIPELINE] "
    f"raw_rows={len(df_bb)} agg_rows={len(bienban_kv_thang)} "
    f"thu_duoc={bienban_kv_thang['so_tien_thu_duoc'].sum():.0f} "
    f"da_xu_ly={bienban_kv_thang['so_tien_da_xu_ly'].sum():.0f} "
    f"con_no={bienban_kv_thang['so_tien_con_no'].sum():.0f}"
)

print(f"[HR PIPELINE] raw_total={len(df_ns)} emp_raw={len(df_ns_emp)} drv_raw={len(df_ns_drv)} emp_rows={len(nhansu_nhanvien_kv_thang)} drv_rows={len(nhansu_taixe_kv_thang)}")

diemtiepthi_kv_thang = _prepare_marketing_monthly_summary(df_mkt_cost, df_mkt_point)
print(
    "[MKT PIPELINE] "
    f"cost_rows={len(df_mkt_cost)} point_rows={len(df_mkt_point)} agg_rows={len(diemtiepthi_kv_thang)} "
    f"tong_phai_chi={pd.to_numeric(diemtiepthi_kv_thang.get('tong_phai_chi', 0), errors='coerce').fillna(0).sum():.0f} "
    f"so_diem={pd.to_numeric(diemtiepthi_kv_thang.get('so_diem_tiep_thi', 0), errors='coerce').fillna(0).sum():.0f}"
)

xe_truc_thuoc_kv_thang, xe_phan_quyen_kv_thang = _prepare_vehicle_monthly_summary(df_vehicle)
xe_dang_co_xdt_kv_ngay, xe_dang_co_xpq_kv_ngay = _prepare_lenca_daily_fleet_snapshot(df_lenca)
print(
    "[FLEET PIPELINE] "
    f"raw_rows={len(df_vehicle)} xdt_rows={len(xe_truc_thuoc_kv_thang)} xpq_rows={len(xe_phan_quyen_kv_thang)} "
    f"xdt_so_xe={pd.to_numeric(xe_truc_thuoc_kv_thang.get('so_luong_xe', 0), errors='coerce').fillna(0).sum():.0f} "
    f"xpq_so_xe={pd.to_numeric(xe_phan_quyen_kv_thang.get('so_luong_xe', 0), errors='coerce').fillna(0).sum():.0f}"
)
print(
    "[LENCA DAILY FLEET PIPELINE] "
    f"raw_rows={len(df_lenca)} xdt_rows={len(xe_dang_co_xdt_kv_ngay)} xpq_rows={len(xe_dang_co_xpq_kv_ngay)} "
    f"xdt_vehicle_days={pd.to_numeric(xe_dang_co_xdt_kv_ngay.get('so_luong_xe', 0), errors='coerce').fillna(0).sum():.0f} "
    f"xpq_vehicle_days={pd.to_numeric(xe_dang_co_xpq_kv_ngay.get('so_luong_xe', 0), errors='coerce').fillna(0).sum():.0f}"
)

(
    doanhthu_ngay_checker,
    doanhthu_ngay_lh_checker,
    doanhthu_ngay_hinhthuc_checker,
    doanhthu_ngay_luong_checker,
    doanhthu_ngay_socho_checker,
    doanhthu_ngay_taixe_checker,
    doanhthu_ngay_taixe_lh_checker,
    doanhthu_ngay_taixe_hinhthuc_checker,
    doanhthu_ngay_taixe_luong_checker,
    doanhthu_ngay_taixe_socho_checker,
    doanhthu_ngay_raw_checker,
) = _prepare_daily_checker_outputs(df_daily_checker)
print(
    "[DAILY CHECKER PIPELINE] "
    f"raw_rows={len(df_daily_checker)} agg_rows={len(doanhthu_ngay_checker)} "
    f"tong_doanh_thu={pd.to_numeric(doanhthu_ngay_checker.get('tong_doanh_thu', 0), errors='coerce').fillna(0).sum():.0f} "
    f"tong_so_cuoc={pd.to_numeric(doanhthu_ngay_checker.get('tong_so_cuoc', 0), errors='coerce').fillna(0).sum():.0f} "
    f"so_xe={pd.to_numeric(doanhthu_ngay_checker.get('so_xe', 0), errors='coerce').fillna(0).sum():.0f} "
    f"driver_agg_rows={len(doanhthu_ngay_taixe_checker)}"
)

doanhthu_thang_khuvuc = df_tx.groupby(
    ["thang_nam", "khu_vuc"], as_index=False
).agg(
    tong_doanh_thu=("doanh_thu", "sum"),
    tong_so_cuoc=("so_cuoc", "sum")
)

doanhthu_khuvuc = df_tx.groupby(
    "khu_vuc", as_index=False
).agg(
    tong_doanh_thu=("doanh_thu", "sum"),
    tong_so_cuoc=("so_cuoc", "sum")
)

top10_driver = (
    df_tx.groupby(["khu_vuc", "so_tai", "ho_ten"], as_index=False)
         .agg(tong_doanh_thu=("doanh_thu", "sum"))
         .sort_values(["khu_vuc", "tong_doanh_thu"], ascending=[True, False])
         .groupby("khu_vuc")
         .head(10)
)

doanhthu_lh = df_tx.groupby(
    "loaihinh_hoptac", as_index=False
).agg(
    tong_doanh_thu=("doanh_thu", "sum"),
    tong_so_cuoc=("so_cuoc", "sum")
)

doanhthu_lh_kv = df_tx.groupby(
    ["khu_vuc", "loaihinh_hoptac"], as_index=False
).agg(
    tong_doanh_thu=("doanh_thu", "sum"),
    tong_so_cuoc=("so_cuoc", "sum")
)

doanhthu_lh_thang = df_tx.groupby(
    ["thang_nam", "loaihinh_hoptac"], as_index=False
).agg(
    tong_doanh_thu=("doanh_thu", "sum"),
    tong_so_cuoc=("so_cuoc", "sum")
)

doanhthu_lh_kv_thang = df_tx.groupby(
    ["thang_nam", "khu_vuc", "loaihinh_hoptac"], as_index=False
).agg(
    tong_doanh_thu=("doanh_thu", "sum"),
    tong_so_cuoc=("so_cuoc", "sum")
)

hopdong_tong = df_hd.groupby(
    "loai_hopdong", as_index=False
).agg(
    tong_so_cuoc=("so_cuoc", "sum")
)

hopdong_khuvuc = df_hd.groupby(
    ["khu_vuc", "loai_hopdong"], as_index=False
).agg(
    tong_so_cuoc=("so_cuoc", "sum")
)

hopdong_thang = df_hd.groupby(
    ["thang_nam", "loai_hopdong"], as_index=False
).agg(
    tong_so_cuoc=("so_cuoc", "sum")
)

hopdong_kv_thang = df_hd.groupby(
    ["thang_nam", "khu_vuc", "loai_hopdong"], as_index=False
).agg(
    tong_so_cuoc=("so_cuoc", "sum")
)

def _cache_safe_sheet_name(sheet_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(sheet_name)).strip("_") or "sheet"


def _export_cache_sheet(df: pd.DataFrame, sheet_name: str) -> None:
    if not EXPORT_DASH_CACHE:
        return
    try:
        CACHE_DIR.mkdir(exist_ok=True)
    except Exception:
        pass
    safe_name = _cache_safe_sheet_name(sheet_name)
    # Prefer Parquet for fast cold-start reads. If the deployment does not have
    # pyarrow/fastparquet, fall back to pickle, which app.py also supports.
    try:
        df.to_parquet(CACHE_DIR / f"{safe_name}.parquet", index=False)
        return
    except Exception as e:
        print(f"[CACHE EXPORT] parquet failed for {sheet_name}: {e}")
    try:
        df.reset_index(drop=True).to_feather(CACHE_DIR / f"{safe_name}.feather")
        return
    except Exception as e:
        print(f"[CACHE EXPORT] feather failed for {sheet_name}: {e}")
    try:
        df.to_pickle(CACHE_DIR / f"{safe_name}.pkl")
    except Exception as e:
        print(f"[CACHE EXPORT] pickle failed for {sheet_name}: {e}")


def _write_sheet(writer, df: pd.DataFrame, sheet_name: str) -> None:
    df.to_excel(writer, sheet_name, index=False)
    _export_cache_sheet(df, sheet_name)


EXCEL_WRITER_ENGINE = os.getenv("OUTPUT_EXCEL_ENGINE", "xlsxwriter").strip() or "xlsxwriter"
try:
    _excel_writer = pd.ExcelWriter(EXCEL_FILE, engine=EXCEL_WRITER_ENGINE)
except Exception as e:
    print(f"[EXCEL WRITE] engine {EXCEL_WRITER_ENGINE} khong kha dung, fallback openpyxl: {e}")
    _excel_writer = pd.ExcelWriter(EXCEL_FILE, engine="openpyxl")

with _excel_writer as writer:
    _write_sheet(writer, doanhthu_thang_khuvuc, "DoanhThu_Thang_KhuVuc")
    _write_sheet(writer, doanhthu_khuvuc, "Tong_DoanhThu_KhuVuc")

    _write_sheet(writer, doanhthu_lh, "DoanhThu_LoaiHinh")
    _write_sheet(writer, doanhthu_lh_kv, "DoanhThu_LH_KhuVuc")
    _write_sheet(writer, doanhthu_lh_thang, "DoanhThu_LH_Thang")
    _write_sheet(writer, doanhthu_lh_kv_thang, "DoanhThu_LH_KV_Thang")

    _write_sheet(writer, doanhthu_ngay_checker, "DoanhThu_Ngay_Checker")
    _write_sheet(writer, doanhthu_ngay_lh_checker, "DoanhThu_Ngay_LH_Checker")
    _write_sheet(writer, doanhthu_ngay_hinhthuc_checker, "DoanhThu_Ngay_HinhThuc")
    _write_sheet(writer, doanhthu_ngay_luong_checker, "DoanhThu_Ngay_Luong")
    _write_sheet(writer, doanhthu_ngay_socho_checker, "DoanhThu_Ngay_SoCho")
    _write_sheet(writer, doanhthu_ngay_taixe_checker, "DoanhThu_Ngay_TaiXe")
    _write_sheet(writer, doanhthu_ngay_taixe_lh_checker, "DoanhThu_Ngay_TaiXe_LH")
    _write_sheet(writer, doanhthu_ngay_taixe_hinhthuc_checker, "DoanhThu_Ngay_TaiXe_HinhThuc")
    _write_sheet(writer, doanhthu_ngay_taixe_luong_checker, "DoanhThu_Ngay_TaiXe_Luong")
    _write_sheet(writer, doanhthu_ngay_taixe_socho_checker, "DoanhThu_Ngay_TaiXe_SoCho")
    _write_sheet(writer, doanhthu_ngay_raw_checker, "DoanhThu_Ngay_Raw_Checker")

    _write_sheet(writer, hopdong_tong, "HopDong_Tong")
    _write_sheet(writer, hopdong_khuvuc, "HopDong_KhuVuc")
    _write_sheet(writer, hopdong_thang, "HopDong_Thang")
    _write_sheet(writer, hopdong_kv_thang, "HopDong_KV_Thang")

    _write_sheet(writer, nhansu_nhanvien_kv_thang, "NhanSu_NhanVien_KV_Thang")
    _write_sheet(writer, nhansu_taixe_kv_thang, "NhanSu_TaiXe_KV_Thang")

    _write_sheet(writer, diemtiepthi_kv_thang, "KinhDoanh_DiemTiepThi_KV_Thang")
    _write_sheet(writer, diemtiepthi_kv_thang, "DiemTiepThi_KV_Thang")

    _write_sheet(writer, xe_truc_thuoc_kv_thang, "PhuongTien_XeTrucThuoc_KV_Thang")
    _write_sheet(writer, xe_truc_thuoc_kv_thang, "XeTrucThuoc_KV_Thang")
    _write_sheet(writer, xe_phan_quyen_kv_thang, "PhuongTien_XePhanQuyen_KV_Thang")
    _write_sheet(writer, xe_phan_quyen_kv_thang, "XePhanQuyen_KV_Thang")
    _write_sheet(writer, xe_dang_co_xdt_kv_ngay, "XeDangCo_XeTrucThuoc_KV_Ngay")
    _write_sheet(writer, xe_dang_co_xdt_kv_ngay, "PhuongTien_XeTrucThuoc_KV_Ngay")
    _write_sheet(writer, xe_dang_co_xpq_kv_ngay, "XeDangCo_XePhanQuyen_KV_Ngay")
    _write_sheet(writer, xe_dang_co_xpq_kv_ngay, "PhuongTien_XePhanQuyen_KV_Ngay")

    _write_sheet(writer, bienban_kv_thang, "KinhDoanh_BienBan_KV_Thang")
    _write_sheet(writer, bienban_kv_thang, "BienBan_KV_Thang")

    for kv, d in top10_driver.groupby("khu_vuc"):
        _write_sheet(writer, d, f"TOP10_{kv[:25]}")

print("PIPELINE COMPLETED")
print("Excel output:", EXCEL_FILE)
print("Dash cache output:", CACHE_DIR if EXPORT_DASH_CACHE else "disabled")
print("Date range:", START_DATE.strftime("%Y-%m-%d") if START_DATE is not None else "-", "->", END_DATE.strftime("%Y-%m-%d") if END_DATE is not None else "-")
