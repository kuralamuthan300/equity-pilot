import asyncio
import os
import re
import sys
import json
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.table import Table

console = Console()

from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_ITERATIONS = 8
LLM_SLEEP_SECONDS = 5
LLM_TIMEOUT = 45
MODEL = "gemini-3-flash-preview"
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

sys.path.append(str(Path(__file__).resolve().parents[1]))

from prompt_to_app import (
    dashboard,
)

TEMPLATES = {"dashboard": dashboard}
HERE = Path(__file__).parent
GENERATED = HERE / "generated_app.py"


# ---------------------------------------------------------------------------
# System prompt for the CryptoScope agent
# ---------------------------------------------------------------------------
PLANNER_PROMPT = """You are CryptoScope — an intelligent crypto and equity intelligence agent
powered by the CryptoScope MCP server. Your mission is to help users track assets,
analyse market sentiment, manage their portfolio, and generate beautiful dashboards
and HTML intelligence reports.

You have access to these MCP tools:
  • get_asset_data(ticker)          — live price, change %, day range, 52-week range, volume
  • get_fear_greed_index()          — Crypto Fear & Greed Index (score 0-100 + classification)
  • compare_assets(tickers)         — side-by-side comparison of comma-separated tickers
  • manage_portfolio(action, ticker, note, quantity) — CRUD on local portfolio.json
  • export_intelligence_report(ticker, analyst_summary) — generates a dark-themed HTML report

CRITICAL RULES:
1. ALWAYS call get_asset_data (or compare_assets) to get REAL live prices before populating any stat widget. Never invent prices.
2. ALWAYS call get_fear_greed_index to include real market sentiment data.
3. ALWAYS call export_intelligence_report to produce the HTML report for the primary asset.
4. Use manage_portfolio to add the primary asset to the portfolio if the user hasn't explicitly said not to.

You design interactive dashboards using the Prefab UI framework.
You have ONE template: `dashboard` which accepts these params:
  {{
    "template": "dashboard",
    "params": {{
      "title": "<dashboard title>",
      "subtitle": "<optional subtitle>",
      "show_header": true,
      "show_footer": true,
      "tabs": [
        {{
          "name": "<tab label>",
          "sections": [
            {{
              "title": "<optional section card title>",
              "cols": 1,
              "widgets": [ ... ]
            }},
            ...
          ]
        }},
        ...
      ]
    }}
  }}

IMPORTANT: Use the NEW structured layout with "sections" inside each tab instead of flat "widgets".
Each section is rendered as its own Card with an optional title and `cols` controls
how many widgets appear side-by-side (1 = vertical stack, 2 = two-column grid, etc.).
Always use `"cols": 2` for stat cards so price, market cap, volume, and range all appear
in a clean 2×2 grid. Use `"cols": 1` for charts, tables, and text blocks.

Each tab's widgets is an ORDERED list. Each widget MUST be EXACTLY one of:

  {{"kind": "stat",           "label": "<small label>", "value": "<big text>", "sub": "<optional caption>"}}
  {{"kind": "badges",         "items": [{{"label": "...", "variant": "default|success|warning|destructive"}}, ...]}}
  {{"kind": "checklist",      "title": "<optional>", "items": [{{"label": "..."}}, ...]}}
  {{"kind": "progress_list",  "title": "<optional>", "items": [{{"label": "...", "value": 0..100}}, ...]}}
  {{"kind": "ring",           "label": "<optional>", "value": 0..100, "suffix": "%"}}
  {{"kind": "pie",            "title": "<optional>", "data": [{{"name": "...", "value": <number>}}, ...]}}
  {{"kind": "bar",            "title": "<optional>", "data": [{{"x": "...", "y": <number>}}, ...], "x_key": "x", "y_keys": ["y"]}}
  {{"kind": "line",           "title": "<optional>", "data": [...], "x_key": "x", "y_keys": ["y"]}}
  {{"kind": "sparkline",      "title": "<optional>", "values": [<number>, ...]}}
  {{"kind": "table",          "title": "<optional>", "columns": ["Col A", ...], "rows": [["v1","v2",...], ...]}}
  {{"kind": "text",           "heading": "<optional>", "body": "<optional>", "level": "h1|h2|h3"}}

Dashboard design guidelines:
- Use tab names that fit crypto/finance (e.g. Overview, Sentiment, Portfolio, Comparison).
- Every good tab has: at least one stat widget with real data, one visual (ring/pie/bar/line), and one list/table.
- Use the Fear & Greed score as a ring widget (value = score, label = "Fear & Greed").
- Use badges to show sentiment signals (e.g. {{"label": "Bullish", "variant": "success"}}).
- For comparison requests, use a table widget with columns: Ticker, Price, Change %, 52W High, 52W Low.
- Invent realistic supporting data only for things that cannot be fetched (e.g. historical sparkline values).
- If modifying an existing dashboard, preserve unaffected tabs and widgets.

Respond with EXACTLY ONE JSON object (no prose, no markdown fences):
  {{"template": "dashboard", "params": {{...}}}}

Current spec: {{current_spec}}
User request: {{user_request}}
"""


def write_app(spec: dict) -> None:
    name = spec.get("template", "dashboard")
    params = spec.get("params", {})
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template {name!r}.")
    source = TEMPLATES[name](**params)
    compile(source, "<generated_app>", "exec")   # syntax check
    GENERATED.write_text(source, encoding="utf-8")
    os.utime(GENERATED, None)
    console.print(f"  [green]→ wrote {GENERATED.name}[/green]")


async def generate_with_timeout(chat, content, timeout: int = LLM_TIMEOUT):
    """Run the blocking Gemini call in a thread with a timeout."""
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, chat.send_message, content),
        timeout=timeout,
    )


def print_banner():
    """Print the CryptoScope welcome banner."""
    console.print()
    console.print(Rule(style="bright_blue"))
    title = Text()
    title.append("  🔭  ", style="bold")
    title.append("C R Y P T O S C O P E", style="bold bright_cyan")
    title.append("  ·  ", style="dim")
    title.append("Crypto & Equity Intelligence Agent", style="italic bright_white")
    console.print(Panel(title, border_style="bright_blue", padding=(0, 2)))
    console.print(Rule(style="bright_blue"))
    console.print()


def print_tool_call(name: str, args: dict):
    tbl = Table(show_header=False, box=None, padding=(0, 1))
    tbl.add_column("k", style="dim cyan", no_wrap=True)
    tbl.add_column("v", style="white")
    for k, v in args.items():
        tbl.add_row(k, str(v))
    console.print(f"  [bold cyan]⚙  Tool:[/bold cyan] [bold yellow]{name}[/bold yellow]")
    console.print(tbl)


async def main():
    if "GEMINI_API_KEY" not in os.environ:
        console.print("[bold red]Error: GEMINI_API_KEY environment variable not set.[/bold red]")
        console.print("[yellow]Create a .env file with: GEMINI_API_KEY=your_key[/yellow]")
        sys.exit(1)

    print_banner()

    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
    else:
        console.print("[dim]Examples:[/dim]")
        console.print("  [dim]• Analyse Bitcoin (BTC-USD) and show me a full dashboard[/dim]")
        console.print("  [dim]• Compare BTC-USD, ETH-USD, and AAPL side by side[/dim]")
        console.print("  [dim]• Add Ethereum to my portfolio with note 'long-term hold'[/dim]")
        console.print()
        user_prompt = console.input(
            "[bold bright_cyan]🔭 What would you like to analyse? [/bold bright_cyan]"
        ).strip()
        if not user_prompt:
            user_prompt = "Analyse Bitcoin (BTC-USD) — show price, Fear & Greed, and build a full dashboard"

    console.print()
    console.print(Panel(
        f"[bold white]{user_prompt}[/bold white]",
        title="[bright_cyan]Request[/bright_cyan]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    # MCP server connection
    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            with console.status("[bold green]Connecting to CryptoScope MCP server…[/bold green]"):
                await session.initialize()
            console.print("[bold green]✅  MCP server connected.[/bold green]\n")

            # Declare all MCP tools to Gemini
            mcp_tools = [
                types.FunctionDeclaration(
                    name="get_asset_data",
                    description="Fetch live price, change %, day range, 52-week range, market cap, and volume for any stock or crypto ticker.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"ticker": types.Schema(type=types.Type.STRING)},
                        required=["ticker"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="get_fear_greed_index",
                    description="Fetch the current Crypto Fear & Greed Index (score 0-100 and classification).",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={},
                    ),
                ),
                types.FunctionDeclaration(
                    name="compare_assets",
                    description="Compare multiple assets side-by-side. Pass comma-separated tickers.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={"tickers": types.Schema(type=types.Type.STRING)},
                        required=["tickers"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="manage_portfolio",
                    description="CRUD operations on the local portfolio tracker. Actions: create, read, update, delete.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action":   types.Schema(type=types.Type.STRING),
                            "ticker":   types.Schema(type=types.Type.STRING),
                            "note":     types.Schema(type=types.Type.STRING),
                            "quantity": types.Schema(type=types.Type.NUMBER),
                        },
                        required=["action", "ticker"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="export_intelligence_report",
                    description="Generate a dark-themed HTML intelligence report for an asset with live data, portfolio notes, Fear & Greed, and AI summary.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "ticker":           types.Schema(type=types.Type.STRING),
                            "analyst_summary":  types.Schema(type=types.Type.STRING),
                        },
                        required=["ticker", "analyst_summary"],
                    ),
                ),
            ]

            tool_config = types.Tool(function_declarations=mcp_tools)
            current_spec: dict | None = None

            # Build system prompt
            system_instruction = PLANNER_PROMPT.replace(
                "{{current_spec}}", json.dumps(current_spec)
            ).replace("{{user_request}}", user_prompt)

            chat = client.chats.create(
                model=MODEL,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[tool_config],
                    temperature=0.0,
                ),
            )

            prompt_payload = (
                f"Current spec: {json.dumps(current_spec)}\n"
                f"User request: {user_prompt}"
            )

            console.print("[bold bright_blue]🤖  Agent loop starting…[/bold bright_blue]\n")

            try:
                with console.status("[bold yellow]Thinking…[/bold yellow]"):
                    response = await generate_with_timeout(chat, prompt_payload)
            except asyncio.TimeoutError:
                console.print(f"[bold red]Error: LLM timed out after {LLM_TIMEOUT}s.[/bold red]")
                return

            # ----------------------------------------------------------------
            # Agent tool-use loop
            # ----------------------------------------------------------------
            iterations = 0
            while response.function_calls and iterations < MAX_ITERATIONS:
                iterations += 1
                console.print(Rule(f"[dim]Iteration {iterations}[/dim]", style="dim"))

                for function_call in response.function_calls:
                    args_dict = dict(function_call.args) if function_call.args else {}
                    print_tool_call(function_call.name, args_dict)

                    try:
                        mcp_result = await session.call_tool(
                            function_call.name, arguments=args_dict
                        )
                        tool_result_text = mcp_result.content[0].text
                        console.print(f"  [green]✓  Result received ({len(tool_result_text)} chars)[/green]\n")
                    except Exception as e:
                        tool_result_text = f"Error executing tool: {repr(e)}"
                        console.print(f"  [red]✗  Tool error: {repr(e)}[/red]\n")

                    with console.status(f"[dim]Rate-limit pause ({LLM_SLEEP_SECONDS}s)…[/dim]"):
                        await asyncio.sleep(LLM_SLEEP_SECONDS)

                    try:
                        with console.status("[bold yellow]Thinking…[/bold yellow]"):
                            response = await generate_with_timeout(
                                chat,
                                types.Part.from_function_response(
                                    name=function_call.name,
                                    response={"result": tool_result_text},
                                ),
                            )
                    except asyncio.TimeoutError:
                        console.print(f"[bold red]Error: LLM timed out after {LLM_TIMEOUT}s.[/bold red]")
                        return

            if iterations >= MAX_ITERATIONS:
                console.print(
                    f"[bold yellow]⚠  Reached max iterations ({MAX_ITERATIONS}). Stopping.[/bold yellow]"
                )

            # ----------------------------------------------------------------
            # Final re-prompt: ask the LLM to produce ONLY the JSON spec
            # (no more function calls). This is needed because some models
            # return None text after the last tool result, or keep trying to
            # call functions.
            # ----------------------------------------------------------------
            console.print(
                "[bold bright_blue]📋  Generating final dashboard spec…[/bold bright_blue]\n"
            )
            FINAL_PROMPT = (
                "Based on ALL the data you have gathered above, "
                "produce the FINAL dashboard specification as a single JSON object. "
                "Do NOT call any functions. "
                "Output ONLY valid JSON matching this exact schema — "
                "no markdown fences, no explanations, just raw JSON:\n"
                '{"template": "dashboard", "params": {"title": "...", "tabs": [...]}}\n'
            )

            # Retry the final prompt up to 3 times if the model still wants
            # to call functions instead of producing text.
            final_retries = 3
            for attempt in range(final_retries):
                try:
                    with console.status("[bold yellow]Assembling dashboard spec…[/bold yellow]"):
                        response = await generate_with_timeout(chat, FINAL_PROMPT)
                except asyncio.TimeoutError:
                    console.print(
                        f"[bold red]Error: LLM timed out after {LLM_TIMEOUT}s.[/bold red]"
                    )
                    return

                # If the model produced text, we're done
                if response.text and response.text.strip():
                    break

                # If the model still wants to call functions, tell it to stop
                # and try again with a stricter prompt
                if response.function_calls:
                    console.print(
                        f"  [yellow]⚠  Model tried to call functions again "
                        f"(attempt {attempt + 1}/{final_retries}). "
                        f"Re-prompting for JSON only…[/yellow]"
                    )
                    # Feed back an empty tool result to satisfy function call
                    for fc in response.function_calls:
                        response = await generate_with_timeout(
                            chat,
                            types.Part.from_function_response(
                                name=fc.name,
                                response={
                                    "result": "IGNORED — produce JSON only, no tool calls"
                                },
                            ),
                        )
                    continue

                # If text is empty and no function calls, break
                break

            console.print(Rule(style="bright_blue"))

            # ----------------------------------------------------------------
            # Extract JSON spec robustly — try multiple strategies
            # ----------------------------------------------------------------
            def extract_json(text: str) -> str | None:
                """Try multiple strategies to extract a JSON object from LLM text."""
                if not text or not text.strip():
                    return None

                text = text.strip()

                # Strategy 1: code fences (```json ... ``` or ``` ... ```)
                match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
                if match:
                    candidate = match.group(1).strip()
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        pass

                # Strategy 2: raw JSON object — find outermost { ... }
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    candidate = text[start : end + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        pass

                # Strategy 3: try parsing the entire text as-is
                try:
                    json.loads(text)
                    return text
                except json.JSONDecodeError:
                    pass

                # Strategy 4: walk through looking for valid JSON objects
                for i in range(len(text)):
                    if text[i] == "{":
                        depth = 0
                        for j in range(i, len(text)):
                            if text[j] == "{":
                                depth += 1
                            elif text[j] == "}":
                                depth -= 1
                                if depth == 0:
                                    candidate = text[i : j + 1]
                                    try:
                                        json.loads(candidate)
                                        return candidate
                                    except json.JSONDecodeError:
                                        break
                return None

            final_text = (response.text or "").strip()

            # Log the raw response for debugging
            console.print(Panel(
                final_text[:2000] + ("…" if len(final_text) > 2000 else ""),
                title="[bright_cyan]Agent Final Response[/bright_cyan]",
                border_style="bright_blue",
            ))

            json_str = extract_json(final_text)

            if json_str is None:
                console.print(
                    "\n[bold red]❌  Could not extract a valid JSON spec "
                    "from the LLM response.[/bold red]"
                )
                console.print(
                    "[dim]The LLM response is shown above. "
                    "It should contain a JSON object like: "
                    '{"template": "dashboard", "params": {...}}[/dim]'
                )
                return

            # Parse JSON first — separate from write_app error handling
            try:
                spec = json.loads(json_str)
            except json.JSONDecodeError as e:
                console.print(
                    f"\n[bold red]❌  Failed to parse JSON spec: {e}[/bold red]"
                )
                console.print("[dim]Raw text attempted (first 200 chars): "
                              f"{json_str[:200]!r}[/dim]")
                return

            # Validate that spec has the expected structure
            if "template" not in spec:
                console.print(
                    "\n[bold red]❌  JSON spec is missing 'template' key.[/bold red]"
                )
                console.print(f"[dim]Received keys: {list(spec.keys())}[/dim]")
                return
            if "params" not in spec:
                console.print(
                    "\n[bold red]❌  JSON spec is missing 'params' key.[/bold red]"
                )
                return

            # Generate the dashboard — catch both ValueErrors from write_app
            # and TypeError from passing wrong kwargs to dashboard()
            try:
                write_app(spec)
            except (ValueError, TypeError) as e:
                console.print(
                    f"\n[bold red]❌  Failed to generate dashboard: {e}[/bold red]"
                )
                console.print(
                    "[dim]The JSON spec was valid, but the dashboard template "
                    "rejected the parameters. Check the spec above.[/dim]"
                )
                return
            except Exception as e:
                console.print(
                    f"\n[bold red]❌  Unexpected error generating dashboard: {e}[/bold red]"
                )
                return

            console.print(
                "\n[bold green]✅  generated_app.py written successfully![/bold green]"
            )

            console.print("\n[bold bright_blue]🚀  Launching Prefab dashboard…[/bold bright_blue]")
            try:
                process = subprocess.Popen(
                    ["prefab", "serve", "generated_app.py"],
                    stdout=sys.stdout,
                    stderr=subprocess.STDOUT,
                )
                console.print(
                    f"[green]Prefab server started (PID {process.pid}). "
                    f"Dashboard opening in your browser.[/green]"
                )
                console.print("[dim]Press Ctrl+C to stop.[/dim]")
                process.wait()
            except FileNotFoundError:
                console.print(
                    "\n[bold red]❌  'prefab' command not found. "
                    "Install Prefab UI and ensure it is in your PATH.[/bold red]"
                )
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping Prefab server…[/yellow]")
                process.terminate()
            except Exception as e:
                console.print(f"\n[bold red]❌  Failed to start prefab server: {e}[/bold red]")


if __name__ == "__main__":
    asyncio.run(main())
