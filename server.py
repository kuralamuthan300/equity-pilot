from mcp.server.fastmcp import FastMCP
import yfinance as yf
import json
import os
import urllib.request
from datetime import datetime

# Initialize the MCP server
mcp = FastMCP("cryptoscope-server")
PORTFOLIO_FILE = "portfolio.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_portfolio():
    """Load the portfolio from the local JSON file."""
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_portfolio(data):
    """Save the portfolio to the local JSON file."""
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ---------------------------------------------------------------------------
# Tool 1 — Internet: fetch live price + extended info for any ticker
# ---------------------------------------------------------------------------

@mcp.tool()
def get_asset_data(ticker: str) -> str:
    """Fetch current price, day high/low, 52-week high/low, market cap,
    volume, and company/coin name for any stock or crypto ticker (e.g. BTC-USD, ETH-USD, AAPL)."""
    try:
        asset = yf.Ticker(ticker)
        info = asset.info

        name = info.get("shortName") or info.get("longName") or ticker
        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
        day_high = info.get("dayHigh") or info.get("regularMarketDayHigh") or 0.0
        day_low = info.get("dayLow") or info.get("regularMarketDayLow") or 0.0
        week52_high = info.get("fiftyTwoWeekHigh") or 0.0
        week52_low = info.get("fiftyTwoWeekLow") or 0.0
        market_cap = info.get("marketCap") or 0
        volume = info.get("volume") or info.get("regularMarketVolume") or 0
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose") or 0.0

        change_pct = 0.0
        if prev_close and prev_close != 0:
            change_pct = round(((current_price - prev_close) / prev_close) * 100, 2)

        return json.dumps({
            "ticker": ticker.upper(),
            "name": name,
            "current_price": current_price,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "week52_high": week52_high,
            "week52_low": week52_low,
            "market_cap": market_cap,
            "volume": volume,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "ticker": ticker})


# ---------------------------------------------------------------------------
# Tool 2 — Internet: fetch Crypto Fear & Greed Index + compare multiple assets
# ---------------------------------------------------------------------------

@mcp.tool()
def get_fear_greed_index() -> str:
    """Fetch the current Crypto Fear & Greed Index from the Alternative.me public API.
    Returns the score (0-100), classification (e.g. 'Greed', 'Fear'), and timestamp."""
    try:
        url = "https://api.alternative.me/fng/?limit=3&format=json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = json.loads(resp.read().decode())

        entries = raw.get("data", [])
        results = []
        for entry in entries:
            results.append({
                "score": int(entry.get("value", 0)),
                "classification": entry.get("value_classification", "Unknown"),
                "timestamp": entry.get("timestamp", ""),
            })
        return json.dumps({"fear_greed_history": results})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def compare_assets(tickers: str) -> str:
    """Compare multiple assets side-by-side. Pass a comma-separated list of tickers
    (e.g. 'BTC-USD,ETH-USD,AAPL,MSFT'). Returns price, daily change %, and 52-week range for each."""
    try:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        results = []
        for t in ticker_list:
            raw = json.loads(get_asset_data(t))
            if "error" not in raw:
                results.append({
                    "ticker": raw["ticker"],
                    "name": raw["name"],
                    "price": raw["current_price"],
                    "change_pct": raw["change_pct"],
                    "week52_high": raw["week52_high"],
                    "week52_low": raw["week52_low"],
                })
            else:
                results.append({"ticker": t, "error": raw["error"]})
        return json.dumps({"comparison": results})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 3 — CRUD: portfolio tracker
# ---------------------------------------------------------------------------

@mcp.tool()
def manage_portfolio(action: str, ticker: str, note: str = "", quantity: float = 0.0) -> str:
    """Perform CRUD operations on the local portfolio tracker.
    Actions: create, read, update, delete.
    - create: adds a new asset entry with optional note and quantity.
    - read: returns the full portfolio as JSON.
    - update: updates the note and/or quantity for an existing entry.
    - delete: removes an entry by ticker."""
    portfolio = load_portfolio()
    ticker = ticker.upper()

    if action == "create":
        try:
            raw = json.loads(get_asset_data(ticker))
            price = raw.get("current_price", 0.0)
            name = raw.get("name", ticker)
        except Exception:
            price = 0.0
            name = ticker

        if any(item["ticker"] == ticker for item in portfolio):
            return f"{ticker} is already in the portfolio."

        entry = {
            "ticker": ticker,
            "name": name,
            "entry_price": price,
            "quantity": quantity,
            "note": note,
            "added_at": datetime.now().isoformat(),
        }
        portfolio.append(entry)
        save_portfolio(portfolio)
        return f"Added {ticker} ({name}) to portfolio at ${price:.2f}."

    elif action == "read":
        if not portfolio:
            return json.dumps([])
        return json.dumps(portfolio)

    elif action == "update":
        for item in portfolio:
            if item["ticker"] == ticker:
                if note:
                    item["note"] = note
                if quantity:
                    item["quantity"] = quantity
                item["updated_at"] = datetime.now().isoformat()
                save_portfolio(portfolio)
                return f"Updated {ticker} in portfolio."
        return f"{ticker} not found in portfolio."

    elif action == "delete":
        original_len = len(portfolio)
        portfolio = [item for item in portfolio if item["ticker"] != ticker]
        if len(portfolio) < original_len:
            save_portfolio(portfolio)
            return f"Removed {ticker} from portfolio."
        return f"{ticker} not found in portfolio."

    return "Invalid action. Use: create, read, update, or delete."


# ---------------------------------------------------------------------------
# Tool 4 — Export: generate an HTML intelligence report
# ---------------------------------------------------------------------------

@mcp.tool()
def export_intelligence_report(ticker: str, analyst_summary: str) -> str:
    """Generate a styled HTML intelligence report for a given asset.
    Includes live price data, portfolio notes, Fear & Greed context, and the AI analyst summary.
    Saves the file as '<TICKER>_Report.html' and returns the filename."""
    try:
        # Fetch asset data
        raw = json.loads(get_asset_data(ticker))
        if "error" in raw:
            return f"Failed to fetch asset data: {raw['error']}"

        name = raw.get("name", ticker)
        price = raw.get("current_price", 0.0)
        change_pct = raw.get("change_pct", 0.0)
        day_high = raw.get("day_high", 0.0)
        day_low = raw.get("day_low", 0.0)
        w52h = raw.get("week52_high", 0.0)
        w52l = raw.get("week52_low", 0.0)

        # Fetch Fear & Greed
        fg_raw = json.loads(get_fear_greed_index())
        fg_entries = fg_raw.get("fear_greed_history", [])
        fg_score = fg_entries[0]["score"] if fg_entries else "N/A"
        fg_class = fg_entries[0]["classification"] if fg_entries else "N/A"

        # Portfolio notes
        portfolio = load_portfolio()
        notes = [
            item.get("note", "")
            for item in portfolio
            if item.get("ticker", "").upper() == ticker.upper() and item.get("note")
        ]
        notes_html = "".join(f"<li>{n}</li>" for n in notes) if notes else "<li>No portfolio notes found.</li>"

        change_color = "#22c55e" if change_pct >= 0 else "#ef4444"
        change_arrow = "▲" if change_pct >= 0 else "▼"
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>CryptoScope — {name} Intelligence Report</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      padding: 2rem;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 1px solid #334155;
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
    }}
    .brand {{ font-size: 0.85rem; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; }}
    .asset-title {{ font-size: 2rem; font-weight: 700; color: #f8fafc; margin-top: 0.25rem; }}
    .ticker-badge {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 0.25rem 0.75rem;
      font-size: 0.9rem;
      color: #94a3b8;
      margin-top: 0.5rem;
      display: inline-block;
    }}
    .timestamp {{ font-size: 0.8rem; color: #475569; text-align: right; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 1.25rem;
    }}
    .card-label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem; }}
    .card-value {{ font-size: 1.6rem; font-weight: 700; color: #f1f5f9; }}
    .card-sub {{ font-size: 0.8rem; color: #94a3b8; margin-top: 0.25rem; }}
    .change {{ color: {change_color}; font-size: 1.1rem; font-weight: 600; }}
    .section {{ margin-bottom: 2rem; }}
    .section-title {{
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #64748b;
      margin-bottom: 0.75rem;
      border-left: 3px solid #6366f1;
      padding-left: 0.75rem;
    }}
    .notes-list {{ list-style: none; }}
    .notes-list li {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 0.75rem 1rem;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      color: #cbd5e1;
    }}
    .verdict-box {{
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
      border: 1px solid #6366f1;
      border-radius: 12px;
      padding: 1.5rem;
      font-size: 0.95rem;
      line-height: 1.7;
      color: #e2e8f0;
    }}
    .fg-badge {{
      display: inline-block;
      background: #312e81;
      color: #a5b4fc;
      border-radius: 999px;
      padding: 0.2rem 0.8rem;
      font-size: 0.8rem;
      font-weight: 600;
      margin-left: 0.5rem;
    }}
    .footer {{
      margin-top: 3rem;
      text-align: center;
      font-size: 0.75rem;
      color: #334155;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <div class="brand">CryptoScope · Intelligence Report</div>
      <div class="asset-title">{name}</div>
      <div class="ticker-badge">{ticker.upper()}</div>
    </div>
    <div class="timestamp">Generated<br/>{generated_at}</div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-label">Current Price</div>
      <div class="card-value">${price:,.2f}</div>
      <div class="card-sub change">{change_arrow} {abs(change_pct):.2f}% today</div>
    </div>
    <div class="card">
      <div class="card-label">Day Range</div>
      <div class="card-value" style="font-size:1.1rem;">${day_low:,.2f} – ${day_high:,.2f}</div>
      <div class="card-sub">Intraday low / high</div>
    </div>
    <div class="card">
      <div class="card-label">52-Week Range</div>
      <div class="card-value" style="font-size:1.1rem;">${w52l:,.2f} – ${w52h:,.2f}</div>
      <div class="card-sub">Annual low / high</div>
    </div>
    <div class="card">
      <div class="card-label">Fear & Greed Index</div>
      <div class="card-value">{fg_score}</div>
      <div class="card-sub">{fg_class} <span class="fg-badge">Market Sentiment</span></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Portfolio Notes</div>
    <ul class="notes-list">{notes_html}</ul>
  </div>

  <div class="section">
    <div class="section-title">AI Analyst Summary</div>
    <div class="verdict-box">{analyst_summary}</div>
  </div>

  <div class="footer">CryptoScope · Powered by Gemini &amp; MCP · {generated_at}</div>
</body>
</html>"""

        filename = f"{ticker.upper()}_Report.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)

        return f"Successfully generated {filename}"

    except Exception as e:
        return f"Failed to generate intelligence report: {str(e)}"


if __name__ == "__main__":
    mcp.run()
