from __future__ import annotations

import re

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _slug(s: str, default: str = "k") -> str:
    out = re.sub(r"[^a-zA-Z0-9_]+", "_", str(s)).strip("_").lower()
    return out or default


def _safe(name: str, idx: int, default: str = "item") -> str:
    return _slug(name, default) or f"{default}_{idx}"


# ---------------------------------------------------------------------------
# Widget renderer — each kind returns a list of indented source lines
# ---------------------------------------------------------------------------

def widget_lines(w: dict, ctx: dict) -> list[str]:
    kind = w.get("kind", "")
    ctx["uid"] = ctx.get("uid", 0) + 1
    uid = ctx["uid"]

    # ------------------------------------------------------------------
    # stat — headline number card
    # ------------------------------------------------------------------
    if kind == "stat":
        label = w.get("label", "")
        value = str(w.get("value", ""))
        sub   = w.get("sub", "")
        out = [
            "with Column(gap=1):",
            f"    Muted({label!r})",
            f"    H1({value!r})",
        ]
        if sub:
            out.append(f"    Muted({sub!r})")
        return out

    # ------------------------------------------------------------------
    # alert_stat — stat with a coloured accent badge (new widget)
    # ------------------------------------------------------------------
    if kind == "alert_stat":
        label   = w.get("label", "")
        value   = str(w.get("value", ""))
        sub     = w.get("sub", "")
        variant = w.get("variant", "default")   # success | warning | destructive | default
        out = [
            "with Column(gap=2):",
            f"    Muted({label!r})",
            f"    H1({value!r})",
            f"    Badge({sub!r}, variant={variant!r})" if sub else f"    Badge({label!r}, variant={variant!r})",
        ]
        return out

    # ------------------------------------------------------------------
    # badges — row of status pills
    # ------------------------------------------------------------------
    if kind == "badges":
        items = w.get("items", [])
        out = ["with Row(gap=2):"]
        for it in items:
            lbl = it.get("label", "") if isinstance(it, dict) else str(it)
            var = it.get("variant", "default") if isinstance(it, dict) else "default"
            out.append(f"    Badge({lbl!r}, variant={var!r})")
        return out or ['Muted("(no badges)")']

    # ------------------------------------------------------------------
    # checklist — interactive checkbox list
    # ------------------------------------------------------------------
    if kind == "checklist":
        items = w.get("items", [])
        title = w.get("title")
        out: list[str] = []
        if title:
            out.append(f"H3({title!r})")
        out.append("with Column(gap=2):")
        for i, it in enumerate(items):
            label = it.get("label", f"Item {i+1}") if isinstance(it, dict) else str(it)
            out += [
                "    with Row(gap=3):",
                f'        Checkbox(name="cb_{uid}_{i}")',
                f"        Text({label!r})",
            ]
        return out

    # ------------------------------------------------------------------
    # progress_list — labelled progress bars
    # ------------------------------------------------------------------
    if kind == "progress_list":
        items = w.get("items", [])
        title = w.get("title")
        out: list[str] = []
        if title:
            out.append(f"H3({title!r})")
        out.append("with Column(gap=3):")
        for it in items:
            if not isinstance(it, dict):
                continue
            label = it.get("label", "")
            val   = it.get("value", 0)
            try:
                val = max(0, min(100, int(val)))
            except Exception:
                val = 0
            out += [
                "    with Column(gap=1):",
                f"        Text({label!r})",
                f"        Progress(value={val})",
            ]
        return out

    # ------------------------------------------------------------------
    # ring — circular progress / score gauge
    # ------------------------------------------------------------------
    if kind == "ring":
        label  = w.get("label", "")
        value  = w.get("value", 0)
        try:
            value = max(0, min(100, int(value)))
        except Exception:
            value = 0
        suffix  = w.get("suffix", "%")
        display = f"{value}{suffix}" if suffix else f"{value}"
        out = ["with Column(gap=2):"]
        if label:
            out.append(f"    H3({label!r})")
        out.append(f"    Ring(value={value}, label={display!r})")
        return out

    # ------------------------------------------------------------------
    # score_ring — ring with an extra descriptive badge below (new widget)
    # ------------------------------------------------------------------
    if kind == "score_ring":
        label       = w.get("label", "")
        value       = w.get("value", 0)
        description = w.get("description", "")
        variant     = w.get("variant", "default")
        try:
            value = max(0, min(100, int(value)))
        except Exception:
            value = 0
        display = f"{value}"
        out = ["with Column(gap=2):"]
        if label:
            out.append(f"    H3({label!r})")
        out.append(f"    Ring(value={value}, label={display!r})")
        if description:
            out.append(f"    Badge({description!r}, variant={variant!r})")
        return out

    # ------------------------------------------------------------------
    # pie — pie / donut chart
    # ------------------------------------------------------------------
    if kind == "pie":
        title      = w.get("title", "")
        data       = w.get("data", [])
        name_key   = w.get("name_key", "name")
        value_key  = w.get("value_key", "value")
        clean = []
        for row in data:
            if isinstance(row, dict) and name_key in row and value_key in row:
                clean.append({name_key: row[name_key], value_key: row[value_key]})
        out = ["with Column(gap=2):"]
        if title:
            out.append(f"    H3({title!r})")
        out.append(
            f"    PieChart(data={clean!r}, data_key={value_key!r}, "
            f"name_key={name_key!r}, show_legend=True)"
        )
        return out

    # ------------------------------------------------------------------
    # bar — vertical bar chart
    # ------------------------------------------------------------------
    if kind == "bar":
        title  = w.get("title", "")
        data   = w.get("data", [])
        x_key  = w.get("x_key", "x")
        y_keys = w.get("y_keys", ["y"])
        if isinstance(y_keys, str):
            y_keys = [y_keys]
        series_lines = ", ".join(
            f"ChartSeries(data_key={yk!r}, label={yk!r})" for yk in y_keys
        )
        out = ["with Column(gap=2):"]
        if title:
            out.append(f"    H3({title!r})")
        out += [
            f"    BarChart(data={data!r},",
            f"             series=[{series_lines}],",
            f"             x_axis={x_key!r}, show_legend={len(y_keys) > 1})",
        ]
        return out

    # ------------------------------------------------------------------
    # line — line / area chart
    # ------------------------------------------------------------------
    if kind == "line":
        title  = w.get("title", "")
        data   = w.get("data", [])
        x_key  = w.get("x_key", "x")
        y_keys = w.get("y_keys", ["y"])
        if isinstance(y_keys, str):
            y_keys = [y_keys]
        series_lines = ", ".join(
            f"ChartSeries(data_key={yk!r}, label={yk!r})" for yk in y_keys
        )
        out = ["with Column(gap=2):"]
        if title:
            out.append(f"    H3({title!r})")
        out += [
            f"    LineChart(data={data!r},",
            f"              series=[{series_lines}],",
            f"              x_axis={x_key!r}, show_legend={len(y_keys) > 1})",
        ]
        return out

    # ------------------------------------------------------------------
    # sparkline — compact inline trend line
    # ------------------------------------------------------------------
    if kind == "sparkline":
        values = w.get("values", [])
        title  = w.get("title", "")
        out = ["with Column(gap=2):"]
        if title:
            out.append(f"    H3({title!r})")
        out.append(f"    Sparkline(data={values!r})")
        return out

    # ------------------------------------------------------------------
    # table — data grid
    # ------------------------------------------------------------------
    if kind == "table":
        title   = w.get("title", "")
        columns = w.get("columns", [])
        rows    = w.get("rows", [])
        out = ["with Column(gap=2):"]
        if title:
            out.append(f"    H3({title!r})")
        # Header row
        out.append("    with Row(gap=3):")
        for col in columns:
            out.append(f"        Text({str(col)!r})")
        # Data rows
        for row in rows:
            out.append("    with Row(gap=3):")
            cells = row if isinstance(row, list) else [row.get(c, "") for c in columns]
            for cell in cells:
                out.append(f"        Text({str(cell)!r})")
        return out

    # ------------------------------------------------------------------
    # kv_list — key-value pairs rendered as a compact list (new widget)
    # ------------------------------------------------------------------
    if kind == "kv_list":
        title = w.get("title", "")
        items = w.get("items", [])   # [{"key": "...", "value": "..."}, ...]
        out: list[str] = []
        if title:
            out.append(f"H3({title!r})")
        out.append("with Column(gap=2):")
        for it in items:
            if not isinstance(it, dict):
                continue
            k = str(it.get("key", ""))
            v = str(it.get("value", ""))
            out += [
                "    with Row(gap=4):",
                f"        Muted({k!r})",
                f"        Text({v!r})",
            ]
        return out

    # ------------------------------------------------------------------
    # text — heading + body copy block
    # ------------------------------------------------------------------
    if kind == "text":
        heading = w.get("heading", "")
        body    = w.get("body", "")
        level   = str(w.get("level", "h3")).lower()
        out = ["with Column(gap=1):"]
        if heading:
            if level == "h1":
                out.append(f"    H1({heading!r})")
            elif level == "h2":
                out.append(f"    H2({heading!r})")
            else:
                out.append(f"    H3({heading!r})")
        if body:
            out.append(f"    Muted({body!r})")
        return out

    # ------------------------------------------------------------------
    # Fallback for unknown kinds
    # ------------------------------------------------------------------
    return [f'Muted({f"Unknown widget kind: {kind!r}"!r})']


# ---------------------------------------------------------------------------
# The one template — generates a complete Prefab app source file
# ---------------------------------------------------------------------------

def dashboard(title: str, tabs: list[dict]) -> str:
    """Render a multi-tab Prefab dashboard from a spec dict."""
    if not tabs:
        tabs = [{"name": "Main", "widgets": [{"kind": "text", "heading": "Empty dashboard"}]}]

    ctx: dict = {"uid": 0}
    TAB_INDENT = " " * 24   # body of `with Column(gap=5):` at 24 spaces

    built_tabs: list[tuple[str, str, str]] = []   # (name, value, indented_body)
    for i, tab in enumerate(tabs):
        name    = str(tab.get("name") or f"Tab {i+1}")
        value   = _slug(tab.get("value") or name, f"tab_{i+1}")
        widgets = tab.get("widgets") or []

        body_lines: list[str] = []
        if not widgets:
            body_lines = [TAB_INDENT + 'Muted("(empty tab)")']
        else:
            for w in widgets:
                for line in widget_lines(w, ctx):
                    body_lines.append((TAB_INDENT + line) if line else "")

        built_tabs.append((name, value, "\n".join(body_lines)))

    first_value = built_tabs[0][1]

    parts = [
        "from prefab_ui.app import PrefabApp",
        "from prefab_ui.components import (",
        "    Badge, Button, Card, CardContent, CardHeader, CardTitle,",
        "    Checkbox, Column, H1, H2, H3, Muted, Progress, Ring, Row,",
        "    Tab, Tabs, Text,",
        ")",
        "from prefab_ui.components.charts import (",
        "    BarChart, ChartSeries, LineChart, PieChart, Sparkline,",
        ")",
        "",
        'with PrefabApp(css_class="max-w-6xl mx-auto p-8 bg-slate-950") as app:',
        "    with Card():",
        "        with CardHeader():",
        f"            CardTitle({title!r})",
        "        with CardContent():",
        f"            with Tabs(value={first_value!r}):",
    ]

    for name, value, body in built_tabs:
        parts.append(f"                with Tab({name!r}, value={value!r}):")
        parts.append("                    with Column(gap=5):")
        parts.append(body)

    return "\n".join(parts) + "\n"
