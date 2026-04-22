import pandas as pd
from db.db_connect import get_connection



def get_doanh_thu_tong():
    sql = """
        SELECT
            khu_vuc,
            SUM(doanh_thu) AS tong_doanh_thu
        FROM doanh_thu
        GROUP BY khu_vuc
        ORDER BY tong_doanh_thu DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_doanh_thu_xe_cong_ty():
    sql = """
        SELECT
            ngay,
            khu_vuc,
            bien_so_xe,
            doanh_thu
        FROM doanh_thu
        WHERE loai_xe = N'Xe công ty'
        ORDER BY ngay DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_doanh_thu_thuong_quyen_gop():
    sql = """
        SELECT
            ngay,
            khu_vuc,
            bien_so_xe,
            doanh_thu
        FROM doanh_thu
        WHERE loai_xe = N'Thương quyền góp'
        ORDER BY ngay DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_doanh_thu_thuong_quyen_hop_tac():
    sql = """
        SELECT
            ngay,
            khu_vuc,
            bien_so_xe,
            doanh_thu
        FROM doanh_thu
        WHERE loai_xe = N'Thương quyền hợp tác'
        ORDER BY ngay DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_doanh_thu_xe_khoan():
    sql = """
        SELECT
            ngay,
            khu_vuc,
            bien_so_xe,
            doanh_thu
        FROM doanh_thu
        WHERE loai_xe = N'Xe khoán'
        ORDER BY ngay DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_cuoc_xe_tong():
    sql = """
        SELECT
            khu_vuc,
            COUNT(*) AS so_cuoc_xe
        FROM cuoc_xe
        GROUP BY khu_vuc
        ORDER BY so_cuoc_xe DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_cuoc_xe_hop_dong():
    sql = """
        SELECT
            ma_cuoc_xe,
            bien_so_xe,
            khu_vuc,
            thoi_gian_bat_dau,
            thoi_gian_ket_thuc,
            tong_km,
            tong_tien
        FROM cuoc_xe
        WHERE nguon_cuoc_xe = N'Hợp đồng'
        ORDER BY thoi_gian_bat_dau DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_cuoc_xe_xanhsm():
    sql = """
        SELECT
            ma_cuoc_xe,
            bien_so_xe,
            khu_vuc,
            thoi_gian_bat_dau,
            thoi_gian_ket_thuc,
            tong_km,
            tong_tien
        FROM cuoc_xe
        WHERE nguon_cuoc_xe = N'XanhSM'
        ORDER BY thoi_gian_bat_dau DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_cuoc_xe_app():
    sql = """
        SELECT
            ma_cuoc_xe,
            bien_so_xe,
            khu_vuc,
            thoi_gian_bat_dau,
            thoi_gian_ket_thuc,
            tong_km,
            tong_tien
        FROM cuoc_xe
        WHERE nguon_cuoc_xe = N'App Nam Thắng'
        ORDER BY thoi_gian_bat_dau DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


def get_cuoc_xe_tong_dai():
    sql = """
        SELECT
            ma_cuoc_xe,
            bien_so_xe,
            khu_vuc,
            thoi_gian_bat_dau,
            thoi_gian_ket_thuc,
            tong_km,
            tong_tien
        FROM cuoc_xe
        WHERE nguon_cuoc_xe = N'Tổng đài Nam Thắng'
        ORDER BY thoi_gian_bat_dau DESC
    """
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df
