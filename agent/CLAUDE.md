# CLAUDE.md — Agent Development Guide

## What is this?

Financial data discrepancy review agent with two implementations:
- `/openai_agents/` — OpenAI Agents SDK (`openai-agents` package)
- `/langchain_agents/` — LangChain SDK (`langchain` + `langgraph`)

Both use **Minimax** LLM via its OpenAI-compatible API (`https://api.minimax.io/v1`).

## Quick commands

```bash
# Run OpenAI Agents version (async, uses Runner.run)
python -m agent.openai_agents.agent "your query here"

# Run LangChain version (sync, uses LangGraph ReAct agent)
python -m agent.langchain_agents.agent "your query here"

# Interactive mode (no args)
python -m agent.openai_agents.agent
python -m agent.langchain_agents.agent

# Install all deps
pip install -r agent/requirements.txt
```

## Architecture decisions

### Shared tools pattern
All data validation logic lives in `shared/tools.py` as plain Python functions.
Each framework wrapper (`openai_agents/agent.py`, `langchain_agents/agent.py`)
wraps these into framework-specific tool decorators (`@function_tool` vs `@tool`).
This avoids code duplication and ensures both agents have identical capabilities.

### Minimax integration
- **OpenAI Agents SDK**: Uses `OpenAIChatCompletionsModel` with a custom `AsyncOpenAI` client pointing to `api.minimax.io/v1`. Tracing is disabled (requires OpenAI platform key).
- **LangChain**: Uses `ChatOpenAI` with custom `base_url` pointing to Minimax. The LangGraph `create_react_agent` provides the ReAct loop.

### Tool design
Tools are designed around the discrepancy patterns discovered during development:

| Tool | Mirrors conversation inquiry |
|------|------------------------------|
| `compare_sources` | "Why are the numbers different between Yahoo and SEC?" |
| `detect_missing_data` | "Why are Q1/Q2 2025 missing? Why is NVIDIA cash flow missing?" |
| `validate_sec_xbrl_concepts` | "What XBRL concepts does this company use?" |
| `batch_missing_data_scan` | "Review all reasons for missing data across all companies" |
| `read_extractor_source` | "Review the extraction logic and find bugs" |
| `suggest_code_fix` | "How should the code be changed to fix this?" |
| `format_web_search_query` | "Research this issue on the internet" |

## Key files

| File | Purpose | When to modify |
|------|---------|----------------|
| `shared/config.py` | API keys, model name, project paths | Adding new env vars |
| `shared/tools.py` | All 8 tool functions | Adding new validation checks |
| `openai_agents/agent.py` | Agent + tool wrappers + CLI | Changing agent behavior or adding tools |
| `langchain_agents/agent.py` | Agent + tool wrappers + CLI | Same, for LangChain version |

## Adding a new tool

1. Add the plain Python function to `shared/tools.py`
2. Add `@function_tool` wrapper in `openai_agents/agent.py`
3. Add `@tool` wrapper in `langchain_agents/agent.py`
4. Add to `ALL_TOOLS` list in both agent files
5. Update system instructions if the tool needs specific guidance

## Conversation inquiry patterns encoded in the agent

The agent's system prompt and tools encode the following investigation patterns
from the development conversation:

1. **Market cap / sector / industry not available** → Yahoo Finance supplement
2. **Valuation metrics need price data** → Hybrid SEC fundamentals + Yahoo price
3. **Revenue segments from XBRL filings** → Parse individual 10-K instance documents
4. **Missing Q1/Q2 quarters** → Check if quarterly dates are being filtered correctly
5. **Missing cash flow (NVDA)** → Cumulative YTD detection and subtraction
6. **Missing FY-end quarter** → Annual − (Q1+Q2+Q3) derivation
7. **GOOGL revenue gaps** → Cross-concept date merging
8. **JPM stale data** → Bank-specific revenue concepts
9. **AVGO/MA missing net income** → ProfitLoss vs NetIncomeLoss concept
10. **TSM errors** → IFRS vs US-GAAP namespace detection
11. **Forward P/E 403** → Web scraper fallback chain analysis
12. **QoQ/YoY discrepancies** → Cross-source quarterly alignment

## Environment variables

```bash
MINIMAX_API_KEY=xxx     # Required — from platform.minimax.io
MINIMAX_MODEL=MiniMax-M2.5    # Optional — default model
MINIMAX_BASE_URL=https://api.minimax.io/v1  # Optional — API endpoint
```

## Dependencies on parent project

The agent imports from the parent project's `data_extractors/` and `utils/`:
- `data_extractors.sec_extractor` — SEC EDGAR XBRL extraction
- `data_extractors.equity_financials_extractor` — Yahoo Finance extraction
- Parent project deps (pandas, yfinance, requests, beautifulsoup4) must be installed

## Do NOT modify

- `shared/config.py` constants that mirror `data_extractors/equity_financials_extractor.py`
  (TOP_20_TICKERS) — keep them in sync manually
- The parent project's extractors — the agent only reads them, never writes
