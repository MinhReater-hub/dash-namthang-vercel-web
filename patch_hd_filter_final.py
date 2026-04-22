# -*- coding: utf-8 -*-
"""
Auto-merge patch: thêm lọc Loại hợp đồng cho menu HỢP ĐỒNG (Page 1 + Page 2)
Giữ nguyên cấu trúc code gốc, chỉ patch các đoạn cần thiết.

Usage:
    python patch_hd_filter_final.py input.py output.py
"""
import sys
from pathlib import Path


def must_replace(src: str, old: str, new: str, label: str) -> str:
    if old not in src:
        raise RuntimeError(f"Không tìm thấy block cần patch: {label}")
    return src.replace(old, new, 1)


def main():
    if len(sys.argv) < 3:
        print("Usage: python patch_hd_filter_final.py input.py output.py")
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    s = in_path.read_text(encoding="utf-8")

    # 1) page_1(prefix, title): thêm hd filter UI
    old1 = '''    if prefix == "lh":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hình", style=filter_label_style("light")),
                dcc.Dropdown(
                    id="lh-type-p1",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hình",
                    style=dropdown_style("light"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"lh-type-p1-wrap"}, style=dropdown_container_style("light")),
            md=4
        )

    return dbc.Container(fluid=True, children=['''

    new1 = '''    if prefix == "lh":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hình", style=filter_label_style("light")),
                dcc.Dropdown(
                    id="lh-type-p1",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hình",
                    style=dropdown_style("light"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"lh-type-p1-wrap"}, style=dropdown_container_style("light")),
            md=4
        )

    if prefix == "hd":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hợp đồng", style=filter_label_style("light")),
                dcc.Dropdown(
                    id="hd-type-p1",
                    options=HD_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hợp đồng",
                    style=dropdown_style("light"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"hd-type-p1-wrap"}, style=dropdown_container_style("light")),
            md=4
        )

    return dbc.Container(fluid=True, children=['''
    s = must_replace(s, old1, new1, "page_1 hd filter UI")

    # 2) page_2(prefix, title, df, dim): thêm hd filter UI
    old2 = '''    if prefix == "lh":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hình", style=filter_label_style("light")),
                dcc.Dropdown(
                    id="lh-type-p2",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hình",
                    style=dropdown_style("light"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"lh-type-p2-wrap"}, style=dropdown_container_style("light")),
            md=4
        )

    return dbc.Container(fluid=True, children=['''

    new2 = '''    if prefix == "lh":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hình", style=filter_label_style("light")),
                dcc.Dropdown(
                    id="lh-type-p2",
                    options=LH_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hình",
                    style=dropdown_style("light"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"lh-type-p2-wrap"}, style=dropdown_container_style("light")),
            md=4
        )

    if prefix == "hd":
        extra_filter = dbc.Col(
            html.Div([
                html.Div("Loại hợp đồng", style=filter_label_style("light")),
                dcc.Dropdown(
                    id="hd-type-p2",
                    options=HD_OPTIONS,
                    multi=True,
                    placeholder="Lọc loại hợp đồng",
                    style=dropdown_style("light"),
                    clearable=True
                )
            ], id={"type":"filter-wrap","id":"hd-type-p2-wrap"}, style=dropdown_container_style("light")),
            md=2
        )

    return dbc.Container(fluid=True, children=['''
    s = must_replace(s, old2, new2, "page_2 hd filter UI")

    # 3) store filters hd p1 callback
    old3 = '''@app.callback(
    Output("filters-hd-p1", "data"),
    Input("hd-year", "value"),
    Input("hd-month", "value"),
    prevent_initial_call=True
)
def _store_filters_hd_p1(year_val, months):
    # Bỏ filter loại hợp đồng ở UI => luôn để rỗng
    return {"year": year_val, "months": months or [], "type_filter": []}
'''

    new3 = '''@app.callback(
    Output("filters-hd-p1", "data"),
    Input("hd-year", "value"),
    Input("hd-month", "value"),
    Input("hd-type-p1", "value"),
    prevent_initial_call=True
)
def _store_filters_hd_p1(year_val, months, type_filter):
    return {"year": year_val, "months": months or [], "type_filter": type_filter or []}
'''
    s = must_replace(s, old3, new3, "filters-hd-p1 callback")

    # 4) store filters hd p2 callback
    old4 = '''@app.callback(
    Output("filters-hd-p2", "data"),
    Input("hd-dim", "value"),
    Input("hd-year-p2", "value"),
    Input("hd-month-p2", "value"),
    prevent_initial_call=True
)
def _store_filters_hd_p2(dims, year_val, months):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    # Bỏ filter loại hợp đồng ở UI => luôn để rỗng
    return {"dims": dims, "year": year_val, "months": months or [], "type_filter": []}
'''

    new4 = '''@app.callback(
    Output("filters-hd-p2", "data"),
    Input("hd-dim", "value"),
    Input("hd-year-p2", "value"),
    Input("hd-month-p2", "value"),
    Input("hd-type-p2", "value"),
    prevent_initial_call=True
)
def _store_filters_hd_p2(dims, year_val, months, type_filter):
    dims = dims if isinstance(dims, list) else ([dims] if dims else [])
    return {"dims": dims, "year": year_val, "months": months or [], "type_filter": type_filter or []}
'''
    s = must_replace(s, old4, new4, "filters-hd-p2 callback")

    out_path.write_text(s, encoding="utf-8")
    print(f"✅ Đã tạo file merged: {out_path}")


if __name__ == "__main__":
    main()
