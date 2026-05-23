# CLAUDE.md — Agent Development Guide

## What is this?

Two agents under `agent/`, both running on **Minimax** LLM via its OpenAI-compatible API (`https://api.minimax.io/v1`):

1. **Equity Financials QA Agent** — Interactive CLI that cross-compares Yahoo Finance vs SEC EDGAR for S&P 500 tickers. Two implementations:
   - `openai_agents/agent.py` — OpenAI Agents SDK (`openai-agents` package)
   - `langchain_agents/agent.py` — LangChain + LangGraph

2. **Dashboard Data QA Agent** — Scheduled (every 12h on VPS) health checker for the full macro_2 dashboard. Single implementation:
   - `openai_agents/qa_agent.py` — OpenAI Agents SDK + Minimax LLM triage + Telegram alerts

Both agents share `shared/` but use different tool modules:
- `shared/tools.py` → 8 tools for equity cross-source validation (original)
- `shared/qa_tools.py` → 11 tools for dashboard data QA (new)
- `shared/freshness_sla.py` → SLA map used by the Data QA agent

**Operator SOP for the Dashboard Data QA Agent: [SOP_DATA_QA.md](./SOP_DATA_QA.md)**

**MANDATORY:** When any data extractor is fixed or a broken data source is replaced, add a new entry to **[QA_learnings.md](./QA_learnings.md)**. This file is the persistent record of all data reliability fixes and must be kept up-to-date alongside the root `CLAUDE.md` "Known-broken indicators" table.

## Quick commands

### Equity Financials QA Agent
```bash
# Run OpenAI Agents version (async, uses Runner.run)
python -m agent.openai_agents.agent "your query here"

# Run LangChain version (sync, uses LangGraph ReAct agent)
python -m agent.langchain_agents.agent "your query here"

# Interactive mode (no args)
python -m agent.openai_agents.agent
python -m agent.langchain_agents.agent
```

### Dashboard Data QA Agent
```bash
# Full QA run (11 checks + LLM synthesis + Telegram alerts)
python -m agent.openai_agents.qa_agent

# Single check (e.g. IBKR streaming health)
python -m agent.openai_agents.qa_agent --check C3

# Include weekly equity cross-source (C10)
python -m agent.openai_agents.qa_agent --weekly

# Skip LLM synthesis (no MINIMAX_API_KEY needed)
python -m agent.openai_agents.qa_agent --no-llm --no-telegram
```

### Install deps (both)
```bash
pip install -r agent/requirements.txt
```

## Architecture decisions

### Shared tools pattern
All data validation logic lives in `shared/` as plain Python functions.
Each framework wrapper (`openai_agents/agent.py`, `langchain_agents/agent.py`)
wraps these into framework-specific tool decorators (`@function_tool` vs `@tool`).
This avoids code duplication and ensures both agents have identical capabilities.

The Dashboard Data QA Agent does NOT use framework tool decorators — its runner
(`openai_agents/qa_agent.py`) calls the check functions directly in a fixed
sequence, then sends the aggregated findings to Minimax for triage synthesis.
The LLM's job is to summarize, not to decide which tools to call — this simpler
pipeline is more reliable for scheduled/automated runs.

### Minimax integration
- **OpenAI Agents SDK**: Uses `OpenAIChatCompletionsModel` with a custom `AsyncOpenAI` client pointing to `api.minimax.io/v1`. Tracing is disabled (requires OpenAI platform key).
- **LangChain**: Uses `ChatOpenAI` with custom `base_url` pointing to Minimax. The LangGraph `create_react_agent` provides the ReAct loop.
- **Data QA Agent**: Uses the plain `openai` SDK with `base_url=MINIMAX_BASE_URL` — no agent framework, just one Chat Completions call to synthesize findings into triage advice.

### Tool design
Equity QA tools mirror conversation inquiries from development:

| Tool | Mirrors conversation inquiry |
|------|------------------------------|
| `compare_sources` | "Why are the numbers different between Yahoo and SEC?" |
| `detect_missing_data` | "Why are Q1/Q2 2025 missing? Why is NVIDIA cash flow missing?" |
| `validate_sec_xbrl_concepts` | "What XBRL concepts does this company use?" |
| `batch_missing_data_scan` | "Review all reasons for missing data across all companies" |
| `read_extractor_source` | "Review the extraction logic and find bugs" |
| `suggest_code_fix` | "How should the code be changed to fix this?" |
| `format_web_search_query` | "Research this issue on the internet" |

Data QA tools (see **[SOP_DATA_QA.md](./SOP_DATA_QA.md)** for the full table of 11):

| Tool | Catches |
|------|---------|
| `check_indicator_freshness` (C1) | Stale cache entries vs per-tier SLA |
| `check_indicator_errors` (C2) | Error fields in cache (FRED rate-limit etc.) |
| `check_ibkr_streaming_health` (C3) | Dead IBKR subscriptions |
| `check_fred_csv_freshness` (C4) | FRED CSV tail dates stale |
| `check_yfinance_vs_ibkr_consistency` (C5) | Price drift |
| `check_cache_vs_csv_consistency` (C6) | Cache/CSV divergence |
| `check_dashboard_endpoints` (C7) | Backend 5xx / unreachable |
| `check_systemd_services` (C8) | Any macro-* service down |
| `check_ib_gateway_health` (C9) | Gateway dead / auth failed |
| `check_equity_financials_drift` (C10) | Yahoo vs SEC drift (weekly) |
| `compute_data_quality_score` (C11) | Aggregate 0-100 score |

## Key files

### Shared
| File | Purpose | When to modify |
|------|---------|----------------|
| `shared/config.py` | API keys, model name, project paths | Adding new env vars |
| `shared/tools.py` | 8 equity QA tools | Adding equity validation checks |
| `shared/qa_tools.py` | 11 data QA tools + logging helpers | Adding/adjusting dashboard checks |
| `shared/freshness_sla.py` | Per-indicator SLA + tier thresholds | Updating expected update frequency |

### Equity Financials QA Agent
| File | Purpose |
|------|---------|
| `openai_agents/agent.py` | Equity agent + CLI |
| `langchain_agents/agent.py` | LangChain version |

### Dashboard Data QA Agent
| File | Purpose |
|------|---------|
| `openai_agents/qa_agent.py` | Runner: runs 11 checks → LLM triage → JSONL + Markdown log → Telegram |
| `SOP_DATA_QA.md` | **Operator SOP** — severity levels, log format, triage workflow, schedule |

### VPS Deployment
| File | Purpose |
|------|---------|
| `../deploy/systemd/macro-data-qa.service` | systemd one-shot for the Data QA agent |
| `../deploy/systemd/macro-data-qa.timer` | 12h schedule (00:00 + 12:00 UTC) |
| `../deploy/systemd/README.md` | Deployment + verify instructions |

## Adding a new tool

### To the Equity QA Agent
1. Add the plain Python function to `shared/tools.py`
2. Add `@function_tool` wrapper in `openai_agents/agent.py`
3. Add `@tool` wrapper in `langchain_agents/agent.py`
4. Add to `ALL_TOOLS` list in both agent files
5. Update system instructions if the tool needs specific guidance

### To the Dashboard Data QA Agent
1. Add a plain Python function to `shared/qa_tools.py` that returns `list[dict]` findings
2. Each finding dict must have: `severity`, `check_id`, `category`, `message`; optionally `indicator`, `suggested_fix`, `context`
3. Append `(check_id, function, description)` tuple to `ALL_CHECKS` at the bottom of `qa_tools.py`
4. If the new check needs an SLA, extend `shared/freshness_sla.py`
5. Document in **[SOP_DATA_QA.md](./SOP_DATA_QA.md)** — add row to the "11 Standard Checks" table and describe the severity range

## Conversation inquiry patterns encoded in the Equity QA Agent

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
MINIMAX_API_KEY=xxx                         # Required — from platform.minimax.io
MINIMAX_MODEL=MiniMax-M2.5                  # Optional — default model
MINIMAX_BASE_URL=https://api.minimax.io/v1  # Optional — API endpoint

# Data QA agent reads these too:
TELEGRAM_BOT_TOKEN=xxx                      # Optional — for CRITICAL push alerts
TELEGRAM_CHAT_ID=1130846055                 # Optional — target chat
```

On the VPS, both `MINIMAX_API_KEY` and Telegram tokens are loaded from:
- `/root/macro_2/.env`
- `/root/Finl_Agent_CC/.env` (Telegram token fallback)

## Dependencies on parent project

Both agents import from the parent project's `data_extractors/` and `data_cache/`:

**Equity QA Agent:**
- `data_extractors.sec_extractor` — SEC EDGAR XBRL extraction
- `data_extractors.equity_financials_extractor` — Yahoo Finance extraction

**Data QA Agent:**
- `data_cache/all_indicators.json` — 88 indicator cache (read-only)
- `data_cache/ibkr_realtime.json` — IBKR streaming snapshot (read-only)
- `data_cache/ibkr_subscriptions.json` — IBKR subscription manifest (read-only)
- `historical_data/*.csv` — FRED CSVs (read-only, tail sampling)
- `/api/*` endpoints on FastAPI backend (HTTP probes)
- `systemctl`, `docker ps`, port 4001 — VPS system-level probes (read-only)

Parent project deps (pandas, yfinance, requests, beautifulsoup4, ib_async) must be installed.

## Do NOT modify

- `shared/config.py` constants that mirror `data_extractors/equity_financials_extractor.py`
  (TOP_20_TICKERS) — keep them in sync manually
- The parent project's extractors — the agents only READ them, never write
- The cache JSON files from within the QA agent — the agent is READ-ONLY against
  dashboard state. The only "write" it does is its own logs under `/var/log/macro-data-qa/`
  and (optionally) a Telegram message on CRITICAL.

## Data QA Agent Calibration Notes

After the first production run (2026-04-15), SLA thresholds were relaxed from
strict (monthly=45d, daily=3d) to realistic (monthly=75d, daily=5d) to account
for real publication schedules. Adjust further in `shared/freshness_sla.py` if
the agent is flagging too many/few issues. See **[SOP_DATA_QA.md](./SOP_DATA_QA.md)**
section 4 for the calibration table.

A 12h QA cycle is the minimum practical frequency — most US econ data releases
happen at 8:30 ET, and the 12:00 UTC / 00:00 UTC timer catches both pre- and
post-release windows. A more frequent schedule (e.g. hourly) would create
noise without catching more issues.

## See Also

- **[SOP_DATA_QA.md](./SOP_DATA_QA.md)** — Operator SOP for the Dashboard Data QA Agent
- **[README.md](./README.md)** — User-facing overview of both agents
- **[STATUS.md](./STATUS.md)** — Equity QA Agent implementation status
- **[/QA_SOP.md](../QA_SOP.md)** — Repo-level *code* quality SOP (complementary, not data-focused)
- **[/deploy/systemd/](../deploy/systemd/)** — Systemd unit files for VPS deployment
