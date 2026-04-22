import pyodbc

SERVER = "103.67.196.240"
DATABASE = "doanhthu-taxi"
USERNAME = "sa"
PASSWORD = "NhutTruong@123"

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
)

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    cursor.execute("SELECT @@VERSION")
    version = cursor.fetchone()[0]

    print(" KẾT NỐI SQL SERVER THÀNH CÔNG")
    print(" SQL Version:")
    print(version)

except Exception as e:
    print(" KẾT NỐI THẤT BẠI")
    print("LỖI:", e)

finally:
    try:
        conn.close()
    except:
        pass
