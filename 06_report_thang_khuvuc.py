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
df["thang"] = df["thoi_gian_tao"].dt.to_period("M").astype(str)

report = (
    df.groupby(["thang", "khu_vuc"])["doanh_thu"]
      .sum()
      .reset_index()
      .sort_values(["thang", "khu_vuc"])
)

print(" DOANH THU THEO THÁNG & KHU VỰC:")
print(report.head(20))
