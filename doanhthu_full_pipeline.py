from dotenv import load_dotenv
import os
import pyodbc
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

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

query = """
SELECT thoi_gian_tao, thang_nam, so_tai, ho_ten, doanh_thu, so_cuoc, khu_vuc
FROM doanhthulaixe
"""
df = pd.read_sql(query, conn)
conn.close()

if not df.empty:
    df["thoi_gian_tao"] = pd.to_datetime(df["thoi_gian_tao"], errors="coerce")
    df["doanh_thu"] = pd.to_numeric(df["doanh_thu"], errors="coerce").fillna(0)
    df["so_cuoc"] = pd.to_numeric(df["so_cuoc"], errors="coerce").fillna(0)
    df["thang_nam"] = pd.to_datetime(df["thang_nam"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    df = df[(df["thoi_gian_tao"] >= START_DATE) & (df["thoi_gian_tao"] <= END_DATE)]

    region_to_province = {
        "Rạch Giá": "Kiên Giang", "Hà Tiên": "Kiên Giang", "Phú Quốc": "Kiên Giang",
        "Cà Mau": "Cà Mau", "Sóc Trăng": "Sóc Trăng", "Bạc Liêu": "Bạc Liêu",
        "Vĩnh Long": "Vĩnh Long", "Cần Thơ": "Cần Thơ", "An Giang": "An Giang"
    }
    df["province"] = df["khu_vuc"].map(region_to_province)

    doanhthu_thang_khuvuc = (
        df.groupby(["thang_nam", "khu_vuc"], as_index=False)
          .agg(tong_doanh_thu=("doanh_thu", "sum"), tong_so_cuoc=("so_cuoc", "sum"))
    )
    doanhthu_thang_khuvuc["doanh_thu_tren_cuoc"] = (
        (doanhthu_thang_khuvuc["tong_doanh_thu"] / doanhthu_thang_khuvuc["tong_so_cuoc"]).fillna(0)
    )
    doanhthu_thang_khuvuc["rank"] = doanhthu_thang_khuvuc["tong_doanh_thu"].rank(method="min", ascending=False)
    doanhthu_thang_khuvuc["xu_huong"] = np.where(
        doanhthu_thang_khuvuc["doanh_thu_tren_cuoc"] >= doanhthu_thang_khuvuc["doanh_thu_tren_cuoc"].mean(),
        "▲", "▼"
    )

    doanhthu_khuvuc = (
        df.groupby("khu_vuc", as_index=False)
          .agg(tong_doanh_thu=("doanh_thu", "sum"), tong_so_cuoc=("so_cuoc", "sum"))
          .sort_values("tong_doanh_thu", ascending=False)
    )

    top10_driver_by_area = (
        df.groupby(["khu_vuc", "so_tai", "ho_ten"], as_index=False)
          .agg(tong_doanh_thu=("doanh_thu", "sum"), tong_so_cuoc=("so_cuoc", "sum"))
          .sort_values(["khu_vuc", "tong_doanh_thu"], ascending=[True, False])
          .groupby("khu_vuc")
          .head(10)
    )

    with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl") as writer:
        doanhthu_thang_khuvuc.to_excel(writer, sheet_name="DoanhThu_Thang_KhuVuc", index=False)
        doanhthu_khuvuc.to_excel(writer, sheet_name="Tong_DoanhThu_KhuVuc", index=False)
        for khu_vuc, data in top10_driver_by_area.groupby("khu_vuc"):
            sheet = khu_vuc.replace("/", "-")[:31]
            data.to_excel(writer, sheet_name=sheet, index=False)

    if not doanhthu_thang_khuvuc.empty:
        plt.figure()
        doanhthu_thang_khuvuc.set_index("khu_vuc")["tong_doanh_thu"].plot(kind="bar")
        plt.tight_layout()
        plt.savefig(CHART_DIR / "doanh_thu_khu_vuc.png")
        plt.close()

    if not doanhthu_khuvuc.empty:
        plt.figure()
        doanhthu_khuvuc.set_index("khu_vuc")["tong_so_cuoc"].plot(kind="bar")
        plt.tight_layout()
        plt.savefig(CHART_DIR / "so_cuoc_khu_vuc.png")
        plt.close()

print("PIPELINE COMPLETED")
print("Excel output:", EXCEL_FILE)
print("Charts output:", CHART_DIR)

def get_data():
    return df.copy()
