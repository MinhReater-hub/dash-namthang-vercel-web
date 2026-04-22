from dash import html, dcc
import dash_bootstrap_components as dbc

filters = dbc.Card(
    dbc.CardBody(
        dbc.Row(
            [
                dbc.Col(
                    dcc.DatePickerRange(
                        id="filter-date",
                        display_format="YYYY-MM-DD",
                    ),
                    width=4,
                ),
                dbc.Col(
                    dcc.Dropdown(
                        id="filter-khu-vuc",
                        placeholder="Chọn khu vực",
                        multi=True,
                    ),
                    width=4,
                ),
            ],
            align="center",
        )
    ),
    className="mb-4",
)
