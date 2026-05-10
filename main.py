from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import Badge, Card, CardContent, CardFooter, CardHeader, Column, H1 ,H2, H3, Input, Muted, Row, Div, Grid, GridItem, Text, Button
from prefab_ui.components.charts import BarChart, LineChart, PieChart, ChartSeries, Sparkline
from prefab_ui.components import DataTable, DataTableColumn
from prefab_ui.actions import AppendState, PopState, SetState
from prefab_ui.rx import Rx
from FastMCP import fastmcp

mcp = fastmcp(model="gpt-5-mini")

@mcp.tool()
def ask_equity_pilot(prompt: str) -> None:
    print(prompt)

# State
user_prompt = Rx("user_prompt")
agent_response = Rx("agent_response")

with PrefabApp(css_class="p-6 bg-slate-50 min-h-screen", gap=6) as app:
    with Column(gap=4):
        H1("Equity Pilot", color="primary")
        with Row(gap=2):
            Input(name="user_prompt", placeholder="Type Your Prompt Here")
            Button(
                "Ask Equity Pilot",
                on_click=[
                    SetState("user_prompt", "user_prompt"),  # or use Input's name= to auto-sync
                    CallTool("ask_equity_pilot", arguments={"prompt": user_prompt}),
                ],
            )
    