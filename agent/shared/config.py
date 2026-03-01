"""
Shared configuration for the financial data review agent.

Environment variables:
  MINIMAX_API_KEY  — required, from platform.minimax.io
  MINIMAX_MODEL    — optional, default MiniMax-M2.5
  MINIMAX_BASE_URL — optional, default https://api.minimax.io/v1
"""

import os

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1")

# Path to the macro_2 project root (parent of /agent)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Top 20 tickers (mirrors equity_financials_extractor.py)
TOP_20_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "BRK-B", "TSM", "LLY", "AVGO",
    "JPM", "V", "WMT", "MA", "XOM",
    "UNH", "COST", "HD", "PG", "JNJ",
]

# SEC EDGAR constants
SEC_USER_AGENT = "MacroDashboard/1.0 contact@example.com"
SEC_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}
