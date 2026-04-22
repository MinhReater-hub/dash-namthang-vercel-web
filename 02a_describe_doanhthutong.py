import pyodbc

SERVER = "103.67.196.240"
DATABASE = "doanhthu-taxi"
USERNAME = "sa"
PASSWORD = "NhutTruong@123"

TABLE_NAME = "doanhthutong"

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
)

cursor = conn.cursor()

cursor.execute(f"""
SELECT 
    COLUMN_NAME,
    DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = '{TABLE_NAME}'
""")

print(f" CẤU TRÚC BẢNG {TABLE_NAME}:")
for row in cursor.fetchall():
    print(f"- {row[0]} ({row[1]})")

conn.close()
