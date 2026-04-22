from dotenv import load_dotenv
import os
import pyodbc
import pandas as pd
from pathlib import Path
from datetime import timedelta
import matplotlib
import unicodedata
import re
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

conn = pyodbc.connect(
    f"DRIVER={{{SQL_DRIVER}}};"
    f"SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};"
    f"Encrypt={SQL_ENCRYPT};TrustServerCertificate={SQL_TRUST_SERVER_CERTIFICATE};"
)

df_tx = pd.read_sql(
    """
    SELECT thoi_gian_tao, thang_nam, so_tai, ho_ten,
           doanh_thu, so_cuoc, khu_vuc, loaihinh_hoptac
    FROM doanhthulaixe
    """,
    conn
)

df_hd = pd.read_sql(
    """
    SELECT
        id,
        ngay_di_hop_dong,
        khu_vuc,
        loai_hopdong
    FROM cuocxehopdong
    """,
    conn
)

df_ns = pd.read_sql(
    """
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
    """,
    conn
)

df_bb = pd.read_sql(
    """
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
    """,
    conn
)

try:
    df_mkt_cost = pd.read_sql("SELECT * FROM dbo.chihoahongdtt", conn)
except Exception as e:
    print(f"[MKT LOAD] khong doc duoc dbo.chihoahongdtt: {e}")
    df_mkt_cost = pd.DataFrame()

try:
    df_mkt_point = pd.read_sql("SELECT * FROM dbo.danhsachdiemtiepthi", conn)
except Exception as e:
    print(f"[MKT LOAD] khong doc duoc dbo.danhsachdiemtiepthi: {e}")
    df_mkt_point = pd.DataFrame()

try:
    df_vehicle = pd.read_sql("SELECT * FROM dbo.thongtinphuongtien", conn)
except Exception as e:
    print(f"[FLEET LOAD] khong doc duoc dbo.thongtinphuongtien: {e}")
    df_vehicle = pd.DataFrame()

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
print(
    "[FLEET PIPELINE] "
    f"raw_rows={len(df_vehicle)} xdt_rows={len(xe_truc_thuoc_kv_thang)} xpq_rows={len(xe_phan_quyen_kv_thang)} "
    f"xdt_so_xe={pd.to_numeric(xe_truc_thuoc_kv_thang.get('so_luong_xe', 0), errors='coerce').fillna(0).sum():.0f} "
    f"xpq_so_xe={pd.to_numeric(xe_phan_quyen_kv_thang.get('so_luong_xe', 0), errors='coerce').fillna(0).sum():.0f}"
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

with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl") as writer:
    doanhthu_thang_khuvuc.to_excel(writer, "DoanhThu_Thang_KhuVuc", index=False)
    doanhthu_khuvuc.to_excel(writer, "Tong_DoanhThu_KhuVuc", index=False)

    doanhthu_lh.to_excel(writer, "DoanhThu_LoaiHinh", index=False)
    doanhthu_lh_kv.to_excel(writer, "DoanhThu_LH_KhuVuc", index=False)
    doanhthu_lh_thang.to_excel(writer, "DoanhThu_LH_Thang", index=False)
    doanhthu_lh_kv_thang.to_excel(writer, "DoanhThu_LH_KV_Thang", index=False)

    hopdong_tong.to_excel(writer, "HopDong_Tong", index=False)
    hopdong_khuvuc.to_excel(writer, "HopDong_KhuVuc", index=False)
    hopdong_thang.to_excel(writer, "HopDong_Thang", index=False)
    hopdong_kv_thang.to_excel(writer, "HopDong_KV_Thang", index=False)

    nhansu_nhanvien_kv_thang.to_excel(writer, "NhanSu_NhanVien_KV_Thang", index=False)
    nhansu_taixe_kv_thang.to_excel(writer, "NhanSu_TaiXe_KV_Thang", index=False)

    diemtiepthi_kv_thang.to_excel(writer, "KinhDoanh_DiemTiepThi_KV_Thang", index=False)
    diemtiepthi_kv_thang.to_excel(writer, "DiemTiepThi_KV_Thang", index=False)

    xe_truc_thuoc_kv_thang.to_excel(writer, "PhuongTien_XeTrucThuoc_KV_Thang", index=False)
    xe_truc_thuoc_kv_thang.to_excel(writer, "XeTrucThuoc_KV_Thang", index=False)
    xe_phan_quyen_kv_thang.to_excel(writer, "PhuongTien_XePhanQuyen_KV_Thang", index=False)
    xe_phan_quyen_kv_thang.to_excel(writer, "XePhanQuyen_KV_Thang", index=False)

    bienban_kv_thang.to_excel(writer, "KinhDoanh_BienBan_KV_Thang", index=False)
    bienban_kv_thang.to_excel(writer, "BienBan_KV_Thang", index=False)

    for kv, d in top10_driver.groupby("khu_vuc"):
        d.to_excel(writer, f"TOP10_{kv[:25]}", index=False)

print("PIPELINE COMPLETED")
print("Excel output:", EXCEL_FILE)
print("Date range:", START_DATE.strftime("%Y-%m-%d") if START_DATE is not None else "-", "->", END_DATE.strftime("%Y-%m-%d") if END_DATE is not None else "-")
