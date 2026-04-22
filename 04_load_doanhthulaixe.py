import pandas as pd
import pyodbc

SERVER = "103.67.196.240"
DATABASE = "doanhthu-taxi"
USERNAME = "sa"
PASSWORD = "NhutTruong@123"

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
    thoi_gian_tao,
    thang_nam,
    khu_vuc,
    so_tai,
    ho_ten,
    doanh_thu,
    so_cuoc,
    sokm_cokhach
FROM doanhthulaixe
"""

df = pd.read_sql(query, conn)
conn.close()

print(" DỮ LIỆU MẪU:")
print(df.head())
print("\n📏 SỐ DÒNG:", len(df))
