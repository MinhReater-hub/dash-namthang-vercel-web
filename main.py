import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_excel("data/doanh_thu.xlsx")

print("DỮ LIỆU GỐC")
print(df)

df["Doanh thu"] = df["Doanh thu"].fillna(0)
df["Ngày"] = pd.to_datetime(df["Ngày"])

df["Tháng"] = df["Ngày"].dt.to_period("M").astype(str)

print("\nDỮ LIỆU SAU KHI XỬ LÝ")
print(df)

monthly_area = (
    df.groupby(["Tháng", "Khu vực"])["Doanh thu"]
      .sum()
      .reset_index()
)

print("\nBÁO CÁO THEO THÁNG + KHU VỰC")
print(monthly_area)

monthly_total = (
    df.groupby("Tháng")["Doanh thu"]
      .sum()
      .reset_index()
)

print("\nTỔNG DOANH THU THEO THÁNG")
print(monthly_total)

with pd.ExcelWriter("bao_cao_doanh_thu_theo_thang.xlsx") as writer:
    monthly_area.to_excel(writer, sheet_name="Theo khu vực", index=False)
    monthly_total.to_excel(writer, sheet_name="Tổng theo tháng", index=False)

monthly_total.plot(
    kind="line",
    x="Tháng",
    y="Doanh thu",
    marker="o",
    legend=False
)

plt.title("Doanh thu theo tháng")
plt.ylabel("Doanh thu")
plt.xlabel("Tháng")
plt.tight_layout()
plt.show()
