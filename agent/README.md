# Financial Data Discrepancy Review Agent

AI agent that reviews financial data quality across multiple sources (Yahoo Finance, SEC EDGAR, FRED, web scrapers), detects discrepancies, diagnoses root causes, and suggests code fixes to the extraction logic.

## Architecture

```
agent/
├── shared/               Shared tools and config (used by both implementations)
│   ├── config.py         Minimax API config, tickers, project paths
│   └── tools.py          8 tool functions: cross-source compare, missing data scan, etc.
├── openai_agents/        OpenAI Agents SDK implementation
│   ├── agent.py          Agent definition, Minimax client, CLI entry point
│   └── requirements.txt
├── langchain_agents/     LangChain SDK implementation
│   ├── agent.py          Agent definition, LangGraph ReAct agent, CLI entry point
│   └── requirements.txt
├── requirements.txt      Combined dependencies
├── CLAUDE.md             Development instructions
├── STATUS.md             Current status and known limitations
└── README.md             This file
```

## Quick Start

```bash
# 1. Install dependencies (from project root)
pip install -r agent/requirements.txt

# 2. Set Minimax API key
export MINIMAX_API_KEY=your_key_from_platform.minimax.io

# 3. Run with OpenAI Agents SDK
python -m agent.openai_agents.agent "Scan all companies for missing SEC data"

# 4. Run with LangChain SDK
python -m agent.langchain_agents.agent "Compare Yahoo vs SEC for AAPL"
```

## Interactive Mode

```bash
# OpenAI Agents SDK (async, streaming)
python -m agent.openai_agents.agent

# LangChain SDK (sync, ReAct loop)
python -m agent.langchain_agents.agent
```

## LLM Configuration

Both implementations connect to **Minimax** via their OpenAI-compatible API:

| Setting | Default | Env Var |
|---------|---------|---------|
| API Key | (required) | `MINIMAX_API_KEY` |
| Model | `MiniMax-M2.5` | `MINIMAX_MODEL` |
| Base URL | `https://api.minimax.io/v1` | `MINIMAX_BASE_URL` |

## Available Tools

| Tool | Purpose |
|------|---------|
| `compare_sources` | Compare Yahoo Finance vs SEC EDGAR for a ticker, flag >2% differences |
| `detect_missing_data` | Scan for None values, quarter gaps, empty metrics |
| `validate_sec_xbrl_concepts` | Check which XBRL concepts exist/missing for a company |
| `batch_missing_data_scan` | Scan all 20 companies at once for coverage issues |
| `read_extractor_source` | Read extractor source code for review |
| `list_extractor_files` | List all extractor files with sizes |
| `suggest_code_fix` | Prepare structured code fix suggestion with source context |
| `format_web_search_query` | Generate research queries for data issues |

## Discrepancy Patterns the Agent Checks

These patterns are derived from real issues discovered during development:

### Data Source Issues
- **XBRL concept name variations**: Companies use different concept names for the same metric (e.g., `NetIncomeLoss` vs `ProfitLoss` for AVGO/MA)
- **Revenue concept switches**: GOOGL switched from `RevenueFromContractWithCustomerExcludingAssessedTax` to `Revenues` mid-2025
- **Bank-specific concepts**: JPM uses `RevenuesNetOfInterestExpense` instead of standard revenue concepts
- **CapEx concept variations**: NVDA uses `PaymentsToAcquireProductiveAssets` instead of `PaymentsToAcquirePropertyPlantAndEquipment`

### Reporting Style Issues
- **Cumulative YTD cash flows**: NVDA reports cumulative instead of standalone quarterly cash flows (Q2 = Q1+Q2, not just Q2)
- **FY-end quarter gap**: The fiscal year-end quarter (e.g., AAPL Sep, MSFT Jun) only appears in 10-K annual filings, not as standalone 10-Q quarterly entries
- **IFRS foreign issuers**: TSM files under `ifrs-full` namespace, not `us-gaap`

### Web Scraping Issues
- **Forward P/E 403 errors**: MacroMicro bot detection blocks scraping
- **Put/Call ratio instability**: CBOE/ycharts DOM changes break scrapers
- **ISM PMI proxy**: Uses Industrial Production index normalized to PMI scale (approximation)

### Cross-Source Discrepancies
- **Trailing vs Forward P/E**: Yahoo provides trailing, MacroMicro provides forward (10-15% difference expected)
- **Revenue timing**: Yahoo and SEC may report different quarter end dates (fiscal vs calendar)
- **EPS computation**: Yahoo uses its own diluted share count vs SEC reported shares

## Example Queries

```
# Single company deep dive
"Review NVDA for all data discrepancies between Yahoo and SEC EDGAR"

# Batch scan
"Scan all 20 companies for missing SEC EDGAR data and summarize the issues"

# Root cause investigation
"Why is AVGO net income showing as None in SEC EDGAR? Check the XBRL concepts"

# Code review and fix
"Read sec_extractor.py and suggest how to fix missing data for companies that use ProfitLoss"

# Cross-source comparison
"Compare GOOGL revenue numbers between Yahoo and SEC for all 5 quarters"
```

## How It Works

1. **Agent receives query** → Minimax LLM interprets intent
2. **Tool selection** → LLM picks appropriate tools (compare, scan, validate, read code)
3. **Tool execution** → Tools call the actual extractors (SEC EDGAR API, Yahoo Finance API)
4. **Analysis** → LLM analyzes tool results, identifies patterns
5. **Code review** → If needed, reads extractor source and suggests fixes
6. **Report** → Structured findings with specific recommendations
