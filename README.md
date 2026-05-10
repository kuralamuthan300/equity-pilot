# 🔭 CryptoScope

**CryptoScope** is an agentic crypto and equity intelligence terminal powered by Google Gemini and the Model Context Protocol (MCP). It acts as your personal market analyst — fetching live asset data, tracking the Crypto Fear & Greed Index, managing a local portfolio, comparing multiple assets side-by-side, generating dark-themed HTML intelligence reports, and dynamically building interactive Prefab dashboards — all from a single conversational prompt.

## ✨ Features

- **🤖 Agentic AI Orchestration:** A Gemini-driven agent loop autonomously decides which tools to call, chains multiple data sources together, and reasons through your request before producing a final dashboard spec and HTML report.
- **📡 Live Asset Data:** Fetches current price, daily change %, day high/low, 52-week range, market cap, and volume for any stock or crypto ticker via `yfinance` (e.g. `BTC-USD`, `ETH-USD`, `AAPL`, `MSFT`).
- **😨 Fear & Greed Index:** Pulls the real-time Crypto Fear & Greed Index (score 0–100 + classification) from the Alternative.me public API and surfaces it as a ring gauge on the dashboard.
- **⚖️ Multi-Asset Comparison:** Compare any number of tickers side-by-side in a single table — price, daily change, and 52-week range — using the `compare_assets` tool.
- **📁 Portfolio Tracker:** Full local CRUD operations on `portfolio.json` — add assets with notes and quantities, update them, or remove them. Data persists across sessions.
- **🌐 HTML Intelligence Reports:** Generates a polished, dark-themed HTML report (`<TICKER>_Report.html`) containing live price cards, Fear & Greed context, portfolio notes, and an AI analyst summary. Open it in any browser.
- **🖥️ Generative Prefab UI:** Translates a JSON dashboard spec (produced by the LLM) into a runnable `generated_app.py` using the Prefab UI widget catalog — stat cards, rings, score rings, pie charts, bar/line charts, sparklines, tables, kv-lists, checklists, and badge rows.
- **🎨 Rich Terminal Experience:** Styled CLI with `rich` — coloured panels, horizontal rules, iteration counters, tool-call tables, and live spinners.

## 🆕 New Capabilities vs. Stock Sentinel

| Feature | Stock Sentinel | CryptoScope |
|---|---|---|
| Asset coverage | Stocks only | Stocks **+** Crypto (BTC-USD, ETH-USD, …) |
| Market sentiment | ✗ | ✅ Fear & Greed Index (live API) |
| Multi-asset compare | ✗ | ✅ `compare_assets` tool |
| Report format | PDF | ✅ Dark-themed **HTML** (browser-ready) |
| Extra widgets | — | ✅ `alert_stat`, `score_ring`, `kv_list` |
| Portfolio fields | ticker + note | ticker + note + **quantity** + name |
| 52-week range | ✗ | ✅ Fetched and displayed |
| Terminal UI | Basic panels | Rich rules, tables, iteration counters |

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- The `uv` package manager (recommended)
- A Google Gemini API Key

### Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone git@github.com:kuralamuthan300/equity-pilot.git cryptoscope
   cd cryptoscope
   ```

2. Sync the environment and install all dependencies:
   ```bash
   uv sync
   ```

3. Create a `.env` file with your Gemini API key:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

### Usage

Run the agent interactively:
```bash
uv run main.py
```

Or pass your request directly as an argument:
```bash
uv run main.py "Analyse Bitcoin (BTC-USD) and build a full dashboard"
```

### Example Prompts

```
Analyse Bitcoin (BTC-USD) — show price, Fear & Greed index, and build a full dashboard
```
```
Compare BTC-USD, ETH-USD, SOL-USD, and AAPL side by side in a table
```
```
Add Ethereum (ETH-USD) to my portfolio with note 'long-term hold', quantity 2.5. Then build a dashboard.
```
```
Show me a Sentiment tab with the Fear & Greed ring and a Portfolio tab with all my holdings
```
```
Generate an intelligence report for NVDA and build a two-tab dashboard: Overview and Fundamentals
```

## 🏗️ Architecture

```
cryptoscope/
├── main.py             # Gemini agent loop, rich terminal UI, Prefab launcher
├── server.py           # MCP server exposing 5 tools (get_asset_data,
│                       #   get_fear_greed_index, compare_assets,
│                       #   manage_portfolio, export_intelligence_report)
├── prompt_to_app.py    # Widget catalog + Prefab code generator
├── pyproject.toml      # Project metadata and dependencies
├── portfolio.json      # Local portfolio store (auto-created)
└── generated_app.py    # Auto-generated Prefab dashboard (auto-created)
```

### MCP Tools

| Tool | Description |
|---|---|
| `get_asset_data(ticker)` | Live price, change %, day range, 52-week range, market cap, volume |
| `get_fear_greed_index()` | Crypto Fear & Greed score + classification (last 3 days) |
| `compare_assets(tickers)` | Side-by-side comparison of comma-separated tickers |
| `manage_portfolio(action, ticker, note, quantity)` | CRUD on `portfolio.json` |
| `export_intelligence_report(ticker, analyst_summary)` | Dark-themed HTML report |

### Widget Catalog (Prefab)

| Widget kind | Description |
|---|---|
| `stat` | Headline number with label and optional sub-caption |
| `alert_stat` | Stat with a coloured accent badge (new) |
| `badges` | Row of status pills (success / warning / destructive / default) |
| `ring` | Circular progress gauge |
| `score_ring` | Ring + descriptive badge below (new) |
| `pie` | Pie / donut chart |
| `bar` | Vertical bar chart |
| `line` | Line / area chart |
| `sparkline` | Compact inline trend line |
| `table` | Data grid with header row |
| `kv_list` | Key-value pair list (new) |
| `checklist` | Interactive checkbox list |
| `progress_list` | Labelled progress bars |
| `text` | Heading + body copy block |
