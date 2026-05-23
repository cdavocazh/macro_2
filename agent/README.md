# macro_2 Agent Harness

Two AI agents that review data quality for the macro_2 dashboard. Both share infrastructure (`shared/`) and both run on **Minimax** via its OpenAI-compatible API.

| Agent | Purpose | Entry points |
|-------|---------|-------------|
| **Equity Financials QA Agent** (original) | Cross-source comparison of Yahoo Finance vs SEC EDGAR for the top 20 S&P 500 tickers; detects XBRL concept drift, missing quarters, bank-specific revenue concepts | `openai_agents/agent.py`, `langchain_agents/agent.py` |
| **Dashboard Data QA Agent** (new) | Automated health checks across all 88 dashboard indicators + 17 IBKR streaming subscriptions + systemd services + IB Gateway; runs every 12h on VPS via systemd timer | `openai_agents/qa_agent.py` |

The Dashboard Data QA Agent is the more comprehensive one — see **[SOP_DATA_QA.md](./SOP_DATA_QA.md)** for full operator documentation.

## Architecture

```
agent/
├── SOP_DATA_QA.md              Operator SOP for Dashboard Data QA Agent
│                                (severity tiers, log formats, triage workflow)
├── README.md                   This file
├── CLAUDE.md                   Development instructions
├── STATUS.md                   Initial implementation status
│
├── shared/                     Shared tools + config (used by all agents)
│   ├── config.py               Minimax API config, tickers, project paths
│   ├── tools.py                8 tools for equity cross-source validation
│   │                             (compare_sources, detect_missing_data, etc.)
│   ├── qa_tools.py             11 tools for dashboard data QA
│   │                             (freshness, IBKR health, systemd, endpoints)
│   └── freshness_sla.py        Per-indicator SLA mapping for QA agent
│
├── openai_agents/              OpenAI Agents SDK implementations
│   ├── agent.py                Equity Financials agent (interactive)
│   ├── qa_agent.py             Dashboard Data QA agent (scheduled)
│   └── requirements.txt
│
├── langchain_agents/           LangChain SDK implementation (equity only)
│   ├── agent.py
│   └── requirements.txt
│
└── requirements.txt            Combined dependencies
```

Deployment unit files (systemd) live at the repo root under `deploy/systemd/` — see `deploy/systemd/README.md`.

---

## A. Dashboard Data QA Agent

Automated checks that detect stale data, broken extractors, dead IBKR subscriptions, down services, and unreachable endpoints. Runs every 12h on VPS and alerts on CRITICAL issues via Telegram.

**→ Full operator SOP: [SOP_DATA_QA.md](./SOP_DATA_QA.md)**

The SOP documents:
- **5 severity tiers** (CRITICAL / HIGH / MEDIUM / LOW / INFO) with response-time guidance
- **11 standard checks** covering every data source the dashboard depends on
- **Freshness SLAs** per indicator (daily / weekly / monthly / quarterly)
- **Log format** (structured JSONL + Markdown report + Telegram alert)
- **Triage workflow** for operators

### Quick Start (Dashboard QA)

```bash
# Full run (all 11 checks + LLM synthesis)
python -m agent.openai_agents.qa_agent

# Single check (e.g. IBKR streaming health only)
python -m agent.openai_agents.qa_agent --check C3

# Include weekly equity cross-source check
python -m agent.openai_agents.qa_agent --weekly

# Skip LLM synthesis (useful if MINIMAX_API_KEY isn't set)
python -m agent.openai_agents.qa_agent --no-llm --no-telegram
```

### Output Locations

| File | Purpose |
|------|---------|
| `/var/log/macro-data-qa/qa-events.jsonl` | Append-only structured events (one per finding) |
| `/var/log/macro-data-qa/YYYY-MM-DD-HHMM.md` | Human-readable per-run report with LLM triage |
| Telegram chat `1130846055` (via `/root/Finl_Agent_CC/.env`) | CRITICAL-only push alerts |

### The 11 Standard Checks

| ID | Name | Catches |
|----|------|---------|
| C1 | `check_indicator_freshness` | Stale cache entries vs per-tier SLA |
| C2 | `check_indicator_errors` | Error fields in cache (e.g. FRED rate-limit) |
| C3 | `check_ibkr_streaming_health` | Dead IBKR subscriptions, stale snapshot |
| C4 | `check_fred_csv_freshness` | FRED CSV tail dates exceeding SLA |
| C5 | `check_yfinance_vs_ibkr_consistency` | Price drift between yfinance & IBKR |
| C6 | `check_cache_vs_csv_consistency` | Divergence between cache JSON and CSV rows |
| C7 | `check_dashboard_endpoints` | Backend HTTP 5xx / unreachable |
| C8 | `check_systemd_services` | Any `macro-*` service down |
| C9 | `check_ib_gateway_health` | IB Gateway docker / port / account |
| C10 | `check_equity_financials_drift` | Weekly: Yahoo vs SEC (reuses equity tools) |
| C11 | `compute_data_quality_score` | Aggregate 0-100 score |

---

## B. Equity Financials QA Agent

Original cross-source comparison tool. Interactive (CLI query → LLM → tool calls → report). Detects the XBRL concept variations, reporting style issues, and web scraping breakages documented in the next section.

### Quick Start (Equity QA)

```bash
# Install deps
pip install -r agent/requirements.txt

# Set Minimax API key
export MINIMAX_API_KEY=your_key_from_platform.minimax.io

# OpenAI Agents SDK (async, streaming)
python -m agent.openai_agents.agent "Compare AAPL across Yahoo and SEC"
python -m agent.openai_agents.agent                                     # interactive

# LangChain SDK (sync, ReAct loop)
python -m agent.langchain_agents.agent "Scan all companies for missing SEC data"
python -m agent.langchain_agents.agent                                  # interactive
```

### The 8 Equity Tools (`shared/tools.py`)

| Tool | Purpose |
|------|---------|
| `compare_sources` | Yahoo vs SEC EDGAR side-by-side, flag >2% differences |
| `detect_missing_data` | Scan for None values, quarter gaps, empty metrics |
| `validate_sec_xbrl_concepts` | Check which XBRL concepts exist/missing for a company |
| `batch_missing_data_scan` | Scan all 20 S&P 500 tickers at once |
| `read_extractor_source` | Read extractor source code for review |
| `list_extractor_files` | Inventory of extractor files |
| `suggest_code_fix` | Prepare structured code-fix suggestion |
| `format_web_search_query` | Generate research queries for data issues |

### Discrepancy Patterns the Equity Agent Checks

Derived from real issues discovered during development:

**Data Source Issues**
- **XBRL concept name variations**: Companies use different concept names for the same metric (e.g., `NetIncomeLoss` vs `ProfitLoss` for AVGO/MA)
- **Revenue concept switches**: GOOGL switched from `RevenueFromContractWithCustomerExcludingAssessedTax` to `Revenues` mid-2025
- **Bank-specific concepts**: JPM uses `RevenuesNetOfInterestExpense` instead of standard revenue concepts
- **CapEx concept variations**: NVDA uses `PaymentsToAcquireProductiveAssets` instead of `PaymentsToAcquirePropertyPlantAndEquipment`

**Reporting Style Issues**
- **Cumulative YTD cash flows**: NVDA reports cumulative instead of standalone quarterly cash flows (Q2 = Q1+Q2, not just Q2)
- **FY-end quarter gap**: The fiscal year-end quarter (e.g., AAPL Sep, MSFT Jun) only appears in 10-K annual filings, not as standalone 10-Q quarterly entries
- **IFRS foreign issuers**: TSM files under `ifrs-full` namespace, not `us-gaap`

**Web Scraping Issues**
- **Forward P/E 403 errors**: MacroMicro bot detection blocks scraping
- **Put/Call ratio instability**: CBOE/ycharts DOM changes break scrapers
- **ISM PMI proxy**: Uses Industrial Production index normalized to PMI scale (approximation)

**Cross-Source Discrepancies**
- **Trailing vs Forward P/E**: Yahoo provides trailing, MacroMicro provides forward (10-15% difference expected)
- **Revenue timing**: Yahoo and SEC may report different quarter end dates (fiscal vs calendar)
- **EPS computation**: Yahoo uses its own diluted share count vs SEC reported shares

---

## LLM Configuration (both agents)

| Setting | Default | Env Var |
|---------|---------|---------|
| API Key | (required) | `MINIMAX_API_KEY` |
| Model | `MiniMax-M2.5` | `MINIMAX_MODEL` |
| Base URL | `https://api.minimax.io/v1` | `MINIMAX_BASE_URL` |

## Example Queries (Equity QA)

```
"Review NVDA for all data discrepancies between Yahoo and SEC EDGAR"
"Scan all 20 companies for missing SEC EDGAR data and summarize"
"Why is AVGO net income showing as None in SEC EDGAR? Check the XBRL concepts"
"Read sec_extractor.py and suggest how to fix missing data for companies that use ProfitLoss"
"Compare GOOGL revenue numbers between Yahoo and SEC for all 5 quarters"
```

## See Also

- **[SOP_DATA_QA.md](./SOP_DATA_QA.md)** — Operator SOP for the Dashboard Data QA Agent (severity, checks, log format, triage)
- **[CLAUDE.md](./CLAUDE.md)** — Development guide (adding tools, architecture decisions, patterns)
- **[STATUS.md](./STATUS.md)** — Initial implementation status of the Equity QA Agent
- **[/QA_SOP.md](../QA_SOP.md)** — Repo-level *code* quality SOP (React patterns, build verification, etc.) — complements this file which is about *data* quality
- **[/deploy/systemd/README.md](../deploy/systemd/README.md)** — Systemd unit files for VPS deployment
