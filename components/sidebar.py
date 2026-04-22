from dash import html
import dash_bootstrap_components as dbc

SIDEBAR_STYLE = {
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "width": "260px",
    "padding": "16px",
    "backgroundColor": "#020617",
}

LINK_STYLE = {
    "color": "#cbd5f5",
    "padding": "6px 12px",
    "textDecoration": "none",
    "display": "block",
}

sidebar = html.Div(
    [
        html.H4("NAM THẮNG GROUP", className="text-center text-light mb-4"),

        dbc.Nav(
            [
                dbc.NavLink("🏠 Trang chủ", href="/", active="exact"),

                html.Hr(),

                html.Div("DOANH THU", className="text-light fw-bold mb-2"),

                dbc.NavLink("📊 Tổng doanh thu (All KV)",
                            href="/doanh-thu/tong", style=LINK_STYLE),

                dbc.NavLink("• Xe công ty",
                            href="/doanh-thu/xe-cong-ty", style=LINK_STYLE),

                dbc.NavLink("• Thương quyền góp",
                            href="/doanh-thu/thuong-quyen", style=LINK_STYLE),

                dbc.NavLink("• Thương quyền hợp tác",
                            href="/doanh-thu/hop-tac", style=LINK_STYLE),

                dbc.NavLink("• Xe khoán",
                            href="/doanh-thu/xe-khoan", style=LINK_STYLE),

                html.Hr(),

                html.Div("CUỐC XE", className="text-light fw-bold mb-2"),

                dbc.NavLink("🚕 Tổng cuốc xe (All KV)",
                            href="/cuoc-xe/tong", style=LINK_STYLE),

                dbc.NavLink("• Cuốc xe hợp đồng",
                            href="/cuoc-xe/hop-dong", style=LINK_STYLE),

                dbc.NavLink("• Cuốc xe XanhSM",
                            href="/cuoc-xe/xanhsm", style=LINK_STYLE),

                dbc.NavLink("• Cuốc xe App Nam Thắng",
                            href="/cuoc-xe/app", style=LINK_STYLE),

                dbc.NavLink("• Cuốc xe Tổng đài",
                            href="/cuoc-xe/tong-dai", style=LINK_STYLE),
            ],
            vertical=True,
            pills=True,
        ),
    ],
    style=SIDEBAR_STYLE,
)
