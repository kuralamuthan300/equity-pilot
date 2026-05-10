#!/usr/bin/env python3
"""
demo_agent.py — EAG V3 Session 4
Ollama Cloud edition — no local Ollama installation needed.

Usage:
  export OLLAMA_API_KEY=ollama_...          # set your key once
  python3 demo_agent.py                     # default cloud model
  python3 demo_agent.py --model qwen2.5:14b-cloud
  python3 demo_agent.py "custom prompt here"
"""

import argparse
import json
import os
import sys
from pathlib import Path

import ollama

sys.path.insert(0, str(Path(__file__).parent))
from server import fetch_web_data, crud_file, show_dashboard  # noqa: E402

# ── Ollama tool schemas ──────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_web_data",
            "description": (
                "Fetch data from the internet. "
                "Pass `url` to retrieve a webpage, or `search_query` to search DuckDuckGo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url":          {"type": "string", "description": "Full URL to fetch"},
                    "search_query": {"type": "string", "description": "Search terms for DuckDuckGo"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crud_file",
            "description": (
                "CRUD operations on a local JSON file. "
                "operations: create | read | update | delete | list_files"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["create", "read", "update", "delete", "list_files"],
                    },
                    "filename":  {"type": "string", "description": "e.g. research.json"},
                    "record":    {"type": "object", "description": "Dict with at least an 'id' key"},
                    "record_id": {"type": "string", "description": "ID of record to update/delete"},
                },
                "required": ["operation", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_dashboard",
            "description": (
                "Render a Prefab UI dashboard inside the MCP client. "
                "Provide a title, list of sections, optionally a filename and metrics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "content": {"description": "String or list of strings"},
                            },
                        },
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional JSON file whose records are shown as a table",
                    },
                    "metrics": {
                        "type": "array",
                        "description": "Optional key stats shown as metric cards",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["title", "sections"],
            },
        },
    },
]

TOOL_FN = {
    "fetch_web_data": fetch_web_data,
    "crud_file":      crud_file,
    "show_dashboard": show_dashboard,
}


def call_tool(name: str, args: dict) -> str:
    fn = TOOL_FN.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**args)
        if isinstance(result, str):
            return result
        # show_dashboard returns PrefabApp (Pydantic model) — serialise it
        try:
            return result.model_dump_json()
        except AttributeError:
            return json.dumps({"status": "rendered", "type": type(result).__name__})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── agent loop ────────────────────────────────────────────────────────────────
def run_agent(prompt: str, model: str, api_key: str) -> None:
    # Build cloud client — points directly to ollama.com, no local daemon needed
    client = ollama.Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    print("=" * 70)
    print(f"☁️   Ollama Cloud Research Agent  |  model: {model}")
    print(f"     Endpoint: https://ollama.com  (no local Ollama needed)")
    print("=" * 70)
    print(f"\nPrompt:\n{prompt}\n")
    print("-" * 70)

    system = (
        "You are a research agent. You MUST use ALL THREE tools in this order:\n"
        "1. fetch_web_data  — search or fetch information from the internet\n"
        "2. crud_file       — save the findings to a local JSON file\n"
        "3. show_dashboard  — display the results in a Prefab UI dashboard\n\n"
        "Do not skip any tool. Do not ask the user for confirmation. "
        "Execute each tool and proceed to the next automatically."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    tools_used: set[str] = set()

    while True:
        resp = client.chat(
            model=model,
            messages=messages,
            tools=TOOLS,
            options={"temperature": 0},
        )

        msg = resp.message
        messages.append(msg)

        # No tool calls → agent finished
        if not msg.tool_calls:
            print(f"\n🗣  Agent:\n{msg.content or ''}")
            break

        # Execute each tool call
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = tc.function.arguments   # already a dict in ollama SDK

            tools_used.add(fn_name)
            print(f"\n⚙️  Tool call : {fn_name}")
            print(f"   Args      : {json.dumps(fn_args, indent=4)}")

            result  = call_tool(fn_name, fn_args)
            snippet = result[:400] + "…" if len(result) > 400 else result
            print(f"   Result    : {snippet}")

            messages.append({"role": "tool", "content": result, "tool_name": fn_name})

    # Summary
    print("\n" + "=" * 70)
    print(f"✅  Tools used : {', '.join(tools_used) or 'none'}")
    missing = {"fetch_web_data", "crud_file", "show_dashboard"} - tools_used
    if missing:
        print(f"⚠️   Not called  : {', '.join(missing)}")
    else:
        print("🎉  All 3 tools executed successfully!")
    print("=" * 70)


# ── CLI ───────────────────────────────────────────────────────────────────────
DEMO_PROMPT = (
    "Find the ownership and company details of Tata Sons using the internet. "
    "Save those details into a file called 'tata_sons.json'. "
    "Then display everything on a Prefab UI dashboard. "
    "Use all three tools: fetch_web_data, crud_file, and show_dashboard. "
    "When calling show_dashboard, also pass a metrics list with key stats like "
    "founded year and number of subsidiaries."
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Cloud Research Agent — EAG V3 S4")
    parser.add_argument("prompt",    nargs="?", default=DEMO_PROMPT, help="User prompt")
    parser.add_argument("--model",   default="llama3.1:cloud",       help="Ollama cloud model name")
    parser.add_argument("--api-key", default=None,                   help="Ollama API key (or set OLLAMA_API_KEY env var)")
    args = parser.parse_args()

    # Resolve API key: CLI flag → env var → error
    api_key = args.api_key or os.environ.get("OLLAMA_API_KEY", "")
    if not api_key:
        print("❌  No API key found.")
        print("    Set it with:  export OLLAMA_API_KEY=ollama_...")
        print("    Or pass it:   python3 demo_agent.py --api-key ollama_...")
        sys.exit(1)

    run_agent(args.prompt, model=args.model, api_key=api_key)