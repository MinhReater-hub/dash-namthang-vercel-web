from dotenv import load_dotenv
import os
import pyodbc
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")

load_dotenv()

SERVER = os.getenv("SQL_SERVER")
DATABASE = os.getenv("SQL_DATABASE")
USERNAME = os.getenv("SQL_USERNAME")
PASSWORD = os.getenv("SQL_PASSWORD")
START_DATE = pd.to_datetime(os.getenv("START_DATE"))
END_DATE = pd.to_datetime(os.getenv("END_DATE"))

BASE_DIR = Path("output")
CHART_DIR = BASE_DIR / "charts"
BASE_DIR.mkdir(exist_ok=True)
CHART_DIR.mkdir(exist_ok=True)
EXCEL_FILE = BASE_DIR / "bao_cao_doanh_thu_tong_hop.xlsx"

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
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

    for kv, d in top10_driver.groupby("khu_vuc"):
        d.to_excel(writer, f"TOP10_{kv[:25]}", index=False)

print("PIPELINE COMPLETED")
print("Excel output:", EXCEL_FILE)
