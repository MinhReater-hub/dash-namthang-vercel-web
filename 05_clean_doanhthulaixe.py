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

df = pd.read_sql("SELECT * FROM doanhthulaixe", conn)
conn.close()

df["thoi_gian_tao"] = pd.to_datetime(df["thoi_gian_tao"])

df["doanh_thu"] = df["doanh_thu"].fillna(0)
df["so_cuoc"] = df["so_cuoc"].fillna(0)

df["thang"] = df["thoi_gian_tao"].dt.to_period("M").astype(str)

print(" DỮ LIỆU SAU KHI LÀM SẠCH:")
print(df.head())
