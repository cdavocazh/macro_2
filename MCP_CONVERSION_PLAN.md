# MCP Server Conversion Plan

> **Status: PROPOSED — not started.** This is a design + feasibility analysis for adding a Model Context Protocol (MCP) server as a 5th frontend over the existing `data_aggregator` data layer. No code has been written. Drafted 2026-05-23. Mirror of `~/.claude/plans/how-would-you-convert-jaunty-quasar.md` plus the RAM/performance analysis from that session (which the external plan file does not contain).

## Context

The repo aggregates 88+ macro indicators into `data_cache/all_indicators.json`. Four frontends (Streamlit, Dash, Grafana, React) and an OpenAI-Agents helper already consume this cache, but none expose the data to generic MCP clients (Claude Desktop, Claude Code, Cursor). An MCP server is a thin 5th frontend that lets any MCP-compatible client use the data without bespoke per-client integration — same code, same cache, same VPS.

**Key distinction (why MCP ≠ the existing FastAPI backends):** the React/Grafana backends already serve URLs, but each consumer needs custom integration. MCP is a *standardized protocol* — clients auto-discover tools via `tools/list`, parse a shared JSON-Schema contract, and plug in via one config entry. A local stdio MCP has no URL at all (stdin/stdout subprocess). The value is the standardized handshake, not "having endpoints."

## Confirmed decisions (this session)

1. **Transport:** ship both — stdio for local Claude Desktop/Code AND streamable HTTP on the Hostinger VPS (port 8765 behind nginx + bearer token).
2. **Refresh:** tiered — read-only by default; `fast_extract.py` (~5s, yfinance only) allowed; full `fetch_all_indicators()` (~40s) gated behind `MCP_ALLOW_FULL_REFRESH=1`.
3. **QA tools:** include — wrap `agent/shared/tools.py` + `agent/shared/qa_tools.py` so Claude can self-diagnose data integrity.

## Repo layout

New top-level `mcp_server/` mirroring `react_dashboard/`:

```
mcp_server/
  server.py      # FastMCP app, transport switch (stdio | http), lifecycle
  tools.py       # @mcp.tool() wrapping data_aggregator + agent.shared.*
  resources.py   # @mcp.resource() cache snapshot + progress
  prompts.py     # @mcp.prompt() reusable templates
  config.py      # env loading
  auth.py        # bearer-token middleware for HTTP transport
  requirements.txt  # mcp>=1.2 + -r ../requirements.txt
  README.md / CLAUDE.md
deploy/systemd/macro-mcp.service  # VPS HTTP transport unit
deploy/nginx-macro-mcp.conf       # reverse proxy + TLS
```

## Tool catalog (16 tools)

| Group | Tools | Wraps |
|---|---|---|
| Read-only data (5) | `get_cache_status`, `list_indicators(group)`, `get_indicator(key)`, `get_indicator_history(key, lookback_days)`, `get_metrics_summary` | `data_aggregator.py:58/74/780`; grafana flattener `api_bridge/main.py:436` |
| On-demand fetch (4) | `get_company_financials(ticker, source)`, `get_intraday_ohlcv(key, interval)`, `get_hyperliquid_ohlcv(coin, interval)`, `get_polymarket_history(token_id, interval)` | `equity_financials_extractor` / `sec_extractor`; React `main.py:543/580/626` |
| QA / health (4) | `check_data_quality`, `compare_equity_sources(ticker)`, `detect_missing_equity_data(ticker, source)`, `validate_sec_xbrl_concepts(ticker)` | `agent/shared/qa_tools.py:623`; `agent/shared/tools.py:29/114/195` |
| CSV access (2) | `list_csv_files(prefix)`, `read_csv_file(name, lookback_days)` | `historical_data/*.csv` |
| Refresh (1, gated) | `refresh_cache(force_full=False)` | `fast_extract.main()` / `data_aggregator.fetch_all_indicators` |

**Resources (2):** `cache://snapshot` (full JSON), `cache://progress` (`.extract_progress.json`). CSVs are NOT resources (500+ equity files would bloat the resource list) — accessed via the two CSV tools.

**Prompts (5):** `summarize_macro_regime`, `find_stale_indicators`, `compare_equity_sources_prompt`, `weekly_freshness_review`, `crypto_macro_correlation`.

## Key engineering rules

- **Reuse, never re-fetch.** The MCP sits on `data_aggregator` like the other 4 frontends. Every tool wraps an existing function.
- **Serialization:** wrap returns with `utils/helpers.py:_serialize_value` (already handles `pd.Series`/`pd.DataFrame`/numpy/NaN). Add a thin `_to_records()` to convert the `{"__type__":"pd.Series",...}` sentinel into compact `[{date,value}]` for LLM consumption.
- **Refresh gate (two-key):** `force_full=True` requires `MCP_ALLOW_FULL_REFRESH=1` AND the explicit arg — prevents an agent saturating yfinance during market hours.
- **HTTP auth:** bearer token (`MCP_BEARER_TOKEN`) middleware; TLS at nginx; port 8765 (avoids 8000/3000/5173).
- **Config env vars:** `FRED_API_KEY` (existing), `MCP_TRANSPORT`, `MCP_HTTP_PORT`, `MCP_BEARER_TOKEN`, `MCP_ALLOW_FULL_REFRESH`.

## RAM footprint (measured 2026-05-23 on dev Mac)

Resident set at each import stage, cache loaded:

| Stage | RSS | Delta |
|---|---|---|
| Python baseline | 8 MB | — |
| `+ pandas + numpy` | 83 MB | +75 MB |
| `+ fastapi + uvicorn` | 103 MB | +20 MB |
| `+ aggregator + cache (87 indicators)` | **485 MB** | **+382 MB** |
| `+ yfinance / requests / bs4` | 485 MB | 0 (already imported) |

**The 9.1 MB cache file balloons ~40× to ~382 MB resident** — 87 indicators × 3–5 `pd.Series`/`DataFrame` each, and every `pd.Series` with a `DatetimeIndex` carries heavy per-object overhead. Under load: +5–15 MB/concurrent request, +20–50 MB if `get_company_financials` fetches, +30 MB during fast refresh (full refresh can briefly hit ~700 MB). **Operating range: 500–600 MB steady, ~700 MB peak.**

**VPS sizing:** 1 GB = risky (OOM-likely under refresh, no headroom); 2 GB = workable with swap; **4 GB = recommended** (room for MCP + React backend + Grafana + nginx).

**Two RAM-reduction levers if needed:**
1. **Lazy historical loading** — load cache without deserializing `historical`/`historical_ohlcv` Series; deserialize only on `get_indicator_history()`. Steady state → **~150 MB**. ~20 LOC in `data_aggregator.load_from_local_cache()`.
2. **Share the singleton** — mount MCP routes onto the existing React FastAPI process instead of a separate process. Saves the full 485 MB duplication. Adds coupling — see next section.

## Shared-process performance (if mounting MCP onto the React FastAPI app)

Chosen path when the VPS is RAM-constrained (≤2 GB) or to avoid the 485 MB duplication. Real risks + mitigations:

| Risk | Mechanism | Mitigation |
|---|---|---|
| GIL contention | MCP tool calls + dashboard requests serialize on one GIL; pandas/JSON block | `asyncio.to_thread()` every sync tool (uvicorn ships a 40-worker pool; numpy releases GIL) |
| Refresh freezes event loop | `fetch_all_indicators()` ~40s blocks all requests + WebSocket if run inline | `refresh_cache` returns immediately, runs `asyncio.create_task(asyncio.to_thread(...))`, client polls `cache://progress` |
| Cache-reload race | `reload_if_stale()` 9.1 MB parse can run twice concurrently | `asyncio.Lock()` single-flight around the reload |
| WebSocket tick lag | heavy MCP CPU stalls the `/ws/hl` asyncio loop | covered by `to_thread` — keeps event loop free; tick lag <100 ms |

**Impact with mitigations (~30 LOC total):** dashboard +50–100 ms during heavy MCP queries (vs +200–500 ms without); refresh runs in background (no freeze); WebSocket <100 ms lag.

**Decision matrix — share process when:** personal/single-user dashboard, bursty (not sustained) LLM queries, RAM-constrained VPS. **Keep separate when:** multi-tenant VPS, multiple concurrent dashboard users, sustained MCP polling, or sub-second WebSocket precision matters for trading. For this repo's profile (single user, intermittent queries, 4 GB VPS), a separate MCP process is fine; on a 2 GB VPS, prefer lazy-loading + separate processes.

## Verification plan

1. `mcp dev mcp_server/server.py --port 5174` (avoid Vite's 5173) — confirm 16 tools + 2 resources + 5 prompts in the Inspector.
2. Parity: `get_indicator("01_vix")` == `curl localhost:8002/api/indicators/01_vix`; `check_data_quality` count == `qa_agent --no-llm --no-telegram`.
3. `pytest mcp_server/tests/test_parity.py` over 6 representative keys vs the running React backend.
4. Refresh gate: `refresh_cache(force_full=True)` without env → `PermissionError`; with env → cache mtime bumps.
5. HTTP auth: no bearer → 401; valid bearer → 200. Then `systemctl status macro-mcp.service` + remote smoke test.

## Documentation updates required when built

Per the CLAUDE.md doc-sync rule: bump the frontend tally 4→5 in CLAUDE.md (architecture tree + Quick Commands) and README.md; add a row to STATUS.md production state + QA_SOP.md health checks; cross-reference from `agent/CLAUDE.md`; add `mcp>=1.2.0` to `requirements.txt`; register in `.claude.json` + Claude Desktop config.

## Execution estimate

~8–10 hrs over 3 sessions: (1) server + tools + resources + Claude Desktop wiring + Inspector smoke test; (2) prompts + parity tests + refresh gating + serialization helper; (3) HTTP transport + auth + systemd + nginx + VPS deploy + doc updates.
