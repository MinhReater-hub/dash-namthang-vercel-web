from pathlib import Path
import pandas as pd
import re
import unicodedata

VN_TZ = "Asia/Ho_Chi_Minh"

def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = s.replace("\u200b", " ").replace("\ufeff", " ").replace("\xa0", " ")
    s = s.strip().lower()
    s = s.replace("hđ", "hop dong").replace("hd", "hop dong")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def find_col(df: pd.DataFrame, candidates):
    cols = list(df.columns)

    def canon_header(x):
        x = norm_text(str(x))
        x = re.sub(r"\s+", "_", x).strip("_")
        return x

    norm = {canon_header(c): c for c in cols}
    for cand in candidates:
        key = canon_header(cand)
        if key in norm:
            return norm[key]
    return None

def map_to_canon(series: pd.Series, mapping: dict) -> pd.Series:
    s = series.astype(str).map(norm_text)
    mapping_norm = {norm_text(k): v for k, v in mapping.items()}
    return s.map(mapping_norm).fillna("Khác")

HD_MAP = {
    "hop dong thuong": "Hợp đồng thường",
    "tuyen chien luoc": "Tuyến chiến lược",
    "xe tien chuyen": "Xe tiện chuyến",
}

BASE_DIR = Path("output")
EXCEL_FILE = BASE_DIR / "bao_cao_doanh_thu_tong_hop.xlsx"

df_hd = pd.read_excel(EXCEL_FILE, sheet_name="HopDong_KV_Thang")

# clean header
df_hd.columns = [str(c).replace("\ufeff", "").strip() for c in df_hd.columns]

HD_COL_RAW = find_col(df_hd, [
    "loai_hopdong",
    "loai_hop_dong", "loai hop dong", "loại hợp đồng",
    "loaihd", "loai_hd", "phan_loai", "nhom_hop_dong"
])

print("HD_COL_RAW =", HD_COL_RAW)
print("COLUMNS repr =", [repr(c) for c in df_hd.columns])

if HD_COL_RAW and HD_COL_RAW in df_hd.columns:
    df_hd["loai_hop_dong_std"] = map_to_canon(df_hd[HD_COL_RAW], HD_MAP)
else:
    df_hd["loai_hop_dong_std"] = "Khác"

print(df_hd["loai_hop_dong_std"].value_counts(dropna=False).head(20))

# nếu vẫn còn "Khác", in ra vài giá trị thô để soi
if (df_hd["loai_hop_dong_std"] == "Khác").any() and HD_COL_RAW:
    raw_bad = df_hd.loc[df_hd["loai_hop_dong_std"] == "Khác", HD_COL_RAW].astype(str).unique()[:30]
    print("RAW values mapped to Khác (sample):", [repr(x) for x in raw_bad])
