import pyodbc
import pandas as pd
from pathlib import Path

SERVER = "103.67.196.240"
DATABASE = "doanhthu-taxi"
USERNAME = "sa"
PASSWORD = "NhutTruong@123"

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

output_file = output_dir / "bao_cao_top10_tai_xe_theo_khu_vuc.xlsx"

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
)

query = """
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
FROM doanhthulaixe
"""

df = pd.read_sql(query, conn)
conn.close()

df["thoi_gian_tao"] = pd.to_datetime(df["thoi_gian_tao"])
df["doanh_thu"] = pd.to_numeric(df["doanh_thu"], errors="coerce").fillna(0)
df["so_cuoc"] = pd.to_numeric(df["so_cuoc"], errors="coerce").fillna(0)

df = df[
    (df["thoi_gian_tao"] >= START_DATE) &
    (df["thoi_gian_tao"] <= END_DATE)
]

report_thang_khuvuc = (
    df.groupby(["thang_nam", "khu_vuc"])
      .agg(
          tong_doanh_thu=("doanh_thu", "sum"),
          tong_so_cuoc=("so_cuoc", "sum")
      )
      .reset_index()
      .sort_values(["thang_nam", "tong_doanh_thu"], ascending=[True, False])
)

top_driver_by_area = (
    df.groupby(["khu_vuc", "ho_ten"])
      .agg(
          tong_doanh_thu=("doanh_thu", "sum"),
          tong_so_cuoc=("so_cuoc", "sum")
      )
      .reset_index()
      .sort_values(["khu_vuc", "tong_doanh_thu"], ascending=[True, False])
      .groupby("khu_vuc")
      .head(10)
)

with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    report_thang_khuvuc.to_excel(
        writer,
        sheet_name="Doanh_thu_theo_thang",
        index=False
    )

    for khu_vuc, data in top_driver_by_area.groupby("khu_vuc"):
        data.to_excel(
            writer,
            sheet_name=khu_vuc[:31],
            index=False
        )
