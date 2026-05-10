#!/usr/bin/env python3
"""
EAG V3 Session 4 — MCP Server  (Prefab UI edition)
Tools:
  1. fetch_web_data   – internet  (URL fetch or DuckDuckGo search)
  2. crud_file        – CRUD on a local JSON data-store
  3. show_dashboard   – rich interactive UI via Prefab / PrefectHQ
"""

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from fastmcp import FastMCP

# ── Prefab UI ──────────────────────────────────────────────────────────────
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Heading,
    Markdown,
    Metric,
    Muted,
    Row,
    Separator,
    Text,
)

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

mcp = FastMCP("research-agent")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — Internet
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def fetch_web_data(url: str | None = None, search_query: str | None = None) -> str:
    """
    Fetch data from the internet.
    Pass `url` to retrieve a webpage, or `search_query` to search DuckDuckGo.
    Returns raw text / JSON as a string.
    """
    headers = {"User-Agent": "Mozilla/5.0 (research-agent/1.0)"}

    if search_query:
        endpoint = (
            f"https://api.duckduckgo.com/?q={quote_plus(search_query)}"
            "&format=json&no_redirect=1&no_html=1&skip_disambig=1"
        )
        resp = httpx.get(endpoint, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        result = {
            "query":          search_query,
            "abstract":       data.get("AbstractText") or data.get("Abstract", ""),
            "abstract_url":   data.get("AbstractURL", ""),
            "answer":         data.get("Answer", ""),
            "related_topics": [
                t.get("Text", "") for t in data.get("RelatedTopics", [])[:6]
                if isinstance(t, dict) and t.get("Text")
            ],
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }
        return json.dumps(result, indent=2)

    if url:
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.text[:8_000]

    return json.dumps({"error": "Provide either `url` or `search_query`."})


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — CRUD on a local JSON file
# ─────────────────────────────────────────────────────────────────────────────
def _load(filename: str) -> dict:
    path = DATA_DIR / filename
    if path.exists():
        return json.loads(path.read_text())
    return {"records": [], "meta": {"created": datetime.utcnow().isoformat()}}


def _save(filename: str, data: dict) -> None:
    (DATA_DIR / filename).write_text(json.dumps(data, indent=2))


@mcp.tool()
def crud_file(
    operation: str,
    filename: str,
    record: dict | None = None,
    record_id: str | None = None,
) -> str:
    """
    CRUD operations on a local JSON file inside the data/ folder.
    operation: create | read | update | delete | list_files
    """
    op = operation.lower().strip()

    if op == "list_files":
        return json.dumps({"files": [f.name for f in DATA_DIR.iterdir() if f.suffix == ".json"]})

    if op == "read":
        return json.dumps(_load(filename), indent=2)

    if op == "create":
        if not record:
            return json.dumps({"error": "Provide `record` for create."})
        record.setdefault("id", datetime.utcnow().strftime("%Y%m%d%H%M%S%f"))
        record.setdefault("saved_at", datetime.utcnow().isoformat())
        data = _load(filename)
        data["records"].append(record)
        _save(filename, data)
        return json.dumps({"status": "created", "record": record})

    if op == "update":
        if not record_id or not record:
            return json.dumps({"error": "Provide `record_id` and `record` for update."})
        data = _load(filename)
        for i, r in enumerate(data["records"]):
            if str(r.get("id")) == str(record_id):
                data["records"][i] = {**r, **record, "id": r["id"]}
                _save(filename, data)
                return json.dumps({"status": "updated", "record": data["records"][i]})
        return json.dumps({"error": f"Record '{record_id}' not found."})

    if op == "delete":
        if not record_id:
            return json.dumps({"error": "Provide `record_id` for delete."})
        data = _load(filename)
        before = len(data["records"])
        data["records"] = [r for r in data["records"] if str(r.get("id")) != str(record_id)]
        if len(data["records"]) == before:
            return json.dumps({"error": f"Record '{record_id}' not found."})
        _save(filename, data)
        return json.dumps({"status": "deleted", "record_id": record_id})

    return json.dumps({"error": f"Unknown operation '{op}'."})


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — Prefab UI dashboard
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool(app=True)
def show_dashboard(
    title: str,
    sections: list[dict],
    filename: str | None = None,
    metrics: list[dict] | None = None,
) -> PrefabApp:
    """
    Render a rich Prefab UI dashboard inside the MCP client (Claude Desktop, etc).

    title    : Main title
    sections : List of { "heading": str, "content": str | list[str] }
    filename : Optional JSON file — records are shown as a DataTable
    metrics  : Optional list of { "label": str, "value": str }
    """
    with Column(gap=6, css_class="p-6 max-w-5xl mx-auto") as view:

        # header card
        with Card(css_class="border-0 bg-gradient-to-r from-violet-600 to-cyan-500 text-white"):
            with CardHeader():
                with Row(align="center", justify="between"):
                    Heading(title, css_class="text-2xl font-bold text-white")
                    Badge(
                        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                        variant="secondary",
                        css_class="text-xs",
                    )
            with CardContent():
                Muted("Research Agent · FastMCP + Prefab UI (PrefectHQ) · EAG V3 S4",
                      css_class="text-white/70 text-sm")

        # optional metric strip
        if metrics:
            with Row(gap=4, wrap=True):
                for m in metrics:
                    with Card(css_class="flex-1 min-w-[150px]"):
                        with CardContent(css_class="pt-4"):
                            Metric(label=str(m.get("label", "")),
                                   value=str(m.get("value", "")))

        # section cards
        for sec in sections:
            heading = sec.get("heading", "")
            content = sec.get("content", "")
            with Card():
                with CardHeader():
                    CardTitle(heading)
                with CardContent():
                    if isinstance(content, list):
                        for item in content:
                            with Row(gap=2, align="start", css_class="mb-1"):
                                Text("•", css_class="text-violet-500 font-bold")
                                Text(str(item))
                    else:
                        Markdown(str(content))

        # optional DataTable from saved JSON
        if filename:
            records = _load(filename).get("records", [])
            if records:
                all_keys = list(dict.fromkeys(k for r in records for k in r))
                cols = [
                    DataTableColumn(key=k, header=k.replace("_", " ").title())
                    for k in all_keys
                ]
                Separator()
                with Card():
                    with CardHeader():
                        with Row(align="center", justify="between"):
                            CardTitle(f"📂 Saved Records — {filename}")
                            Badge(f"{len(records)} rows")
                    with CardContent():
                        DataTable(rows=records, columns=cols)

        Separator()
        Muted("Built with FastMCP · Prefab UI by PrefectHQ · EAG V3 Session 4",
              css_class="text-center text-xs")

    return PrefabApp(view=view)


if __name__ == "__main__":
    mcp.run(transport="stdio")