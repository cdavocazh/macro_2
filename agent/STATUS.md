# STATUS.md — Financial Data Review Agent

## Current Status: v1.0 — Initial Implementation

**Date**: 2026-03-01

## What Works

### OpenAI Agents SDK (`/openai_agents/`)
- [x] Agent definition with Minimax LLM via `OpenAIChatCompletionsModel`
- [x] 8 tools registered via `@function_tool` decorator
- [x] CLI with single-query and interactive REPL modes
- [x] Async execution via `Runner.run()`

### LangChain SDK (`/langchain_agents/`)
- [x] Agent definition with Minimax LLM via `ChatOpenAI` custom base_url
- [x] 8 tools registered via `@tool` decorator
- [x] LangGraph `create_react_agent` for ReAct loop
- [x] CLI with single-query and interactive REPL modes

### Shared Tools (`/shared/`)
- [x] `compare_sources` — Cross-source comparison (Yahoo vs SEC EDGAR)
- [x] `detect_missing_data` — None values, quarter gaps, empty metrics
- [x] `validate_sec_xbrl_concepts` — XBRL concept availability check
- [x] `batch_missing_data_scan` — Scan all 20 companies at once
- [x] `read_extractor_source` — Read extractor Python source code
- [x] `list_extractor_files` — List all extractor files
- [x] `suggest_code_fix` — Structured code fix suggestion
- [x] `format_web_search_query` — Generate research queries

## Known Limitations

### Agent Capabilities
- **No direct web search execution**: The `format_web_search_query` tool generates queries but does not execute them. The agent would need a web search tool (e.g., Tavily, SerpAPI) for actual internet research.
- **No code write-back**: The agent can read extractors and suggest fixes but cannot modify files directly. Fixes must be applied manually.
- **Minimax context window**: MiniMax-M2.5 has 204K tokens. Large batch scans of all 20 companies may approach context limits.

### Data Source Limitations
- **TSM (IFRS)**: SEC EDGAR returns no `us-gaap` data. TSM files under `ifrs-full` namespace. The SEC extractor correctly reports this as an error.
- **Forward P/E**: MacroMicro web scraper returns 403. Falls back to trailing P/E (10-15% proxy error).
- **Put/Call Ratio**: CBOE/ycharts scrapers are unreliable. Multi-level fallback may all fail.
- **Rate limits**: SEC EDGAR allows 10 req/sec. Batch scanning all 20 companies takes ~30-60 seconds.

### Framework-Specific
- **OpenAI Agents SDK**: Tracing disabled (requires OpenAI platform key). No streaming output in CLI yet.
- **LangChain**: `create_react_agent` may retry on tool errors. No conversation memory across CLI invocations.

## Discrepancy Coverage

| Discrepancy Type | Detection | Root Cause | Code Fix |
|------------------|-----------|------------|----------|
| Missing XBRL concepts | `validate_sec_xbrl_concepts` | Shows which concepts exist | `suggest_code_fix` |
| Cross-source value differences | `compare_sources` | Shows % diff per metric | Agent analysis |
| Quarter timeline gaps | `detect_missing_data` | Identifies gap locations | Agent analysis |
| Cumulative YTD cash flow | `validate_sec_xbrl_concepts` | Detects duration patterns | `read_extractor_source` |
| FY-end quarter missing | `detect_missing_data` | Checks quarter continuity | Agent analysis |
| IFRS vs US-GAAP | `validate_sec_xbrl_concepts` | `has_ifrs` / `has_usgaap` flags | N/A (known limitation) |
| Web scraper 403 errors | `detect_missing_data` | Error messages in data | `read_extractor_source` |

## Roadmap

### v1.1 — Planned
- [ ] Add web search tool (Tavily or SerpAPI integration)
- [ ] Add conversation memory for multi-turn investigations
- [ ] Add HTML report generation
- [ ] Add automated fix application (with user confirmation)

### v1.2 — Future
- [ ] Multi-agent architecture: Triage agent → specialist agents (SEC, Yahoo, Web)
- [ ] Scheduled discrepancy monitoring (run daily, alert on new issues)
- [ ] Integration with the Streamlit dashboard (sidebar panel)
- [ ] Historical discrepancy tracking (what changed since last scan)
