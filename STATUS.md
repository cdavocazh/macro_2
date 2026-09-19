# STATUS — macro_2

_Auto-maintained by `/update-session-status`. Last updated: 2026-09-01 — dashboard data-integrity + performance sweep: fixed the yfinance trailing-NaN family (4 Market Indices cards + a fabricated breadth signal), Hyperliquid OI denomination + HIP-3 builder-dex resolution, the `5_spx_call_skew` two-writer key clash, PEG/Price-Cash on `65_sp500_multiples`; installed OpenBB providers on the VPS in an isolated `venv-openbb`; cut first-visit load ~5–8 s → ~1.5 s and put awehawk.cloud on HTTPS/HTTP2. Five commits merged to main (`a355a27`), deployed and verified live._

Operator briefing for this repository. Read FIRST when opening this repo in a new session — it reflects what's deployed, what's in flight, and what gotchas exist. For deeper context: see "What to read first" below.

## Production state

| Component | Where it runs | Last verified | Notes |
|---|---|---|---|
| Streamlit dashboard | localhost:8501 (macOS) | 2026-03-30 | Primary frontend, compact CSS, 88+ indicators |
| Dash dashboard | localhost:8050 (macOS) | 2026-03-30 | Production gunicorn, expandable charts |
| React + FastAPI | localhost:5173 + 8002 (macOS) | 2026-03-30 | Vite + React 18, WebSocket HL live |
| Grafana | localhost:3000 + 8001 (macOS) | 2026-03-30 | Docker or local mode, Infinity plugin |
| launchd: hl-extract | macOS launchd, 1-min (24/7) | 2026-03-30 | HL perps + HIP-3 spot, partial cache merge (keys 84/85) |
| launchd: fast-extract | macOS launchd, 5-min (24/7) | 2026-03-30 | 31 yfinance extractors, ~5s, 3-min freshness guard |
| launchd: scheduled-extract | macOS launchd, 5x/day Mon-Sat | 2026-03-30 | Full FRED/SEC/web scrapers, 15-min freshness guard |
| **awehawk.cloud (public)** | nginx → `macro-react.service` (uvicorn :8002) on <VPS_HOST> | 2026-09-01 | HTTPS + HTTP/2, HTTP 301s. Cert to 2026-11-29 (certbot.timer). First paint ~1.5 s: lite API (57 KB) then full; plotly lazy-chunked; `/assets/` immutable + `gzip_static` |
| VPS systemd timers | Hostinger VPS <VPS_HOST> | 2026-09-01 | 7 timers; steady-state peaks: fast-extract ~149 MB, hl-extract ~188 MB (both every 5 min), all exit 0 |
| VPS: `venv-openbb` | `/root/macro_2/venv-openbb` (666 MB) | 2026-09-01 | OpenBB + cboe/ecb providers; used ONLY by `macro-extract.service`. Daily peak ~1.1–1.2 GB (was ~400 MB), capped `MemoryMax=2G` |
| VPS: IBKR stream | systemd macro2-ibkr-stream.service | 2026-05-17 | Long-running daemon, ib_async, 3s JSON snapshots |
| VPS: Data QA agent | systemd macro-data-qa.timer (12h) | 2026-05-17 | 11 checks → LLM triage → Telegram alerts |
| VPS: Cache repair | systemd macro-cache-repair.timer | 2026-05-17 | Periodic cache error detection + auto-repair |

## Open threads

- **Macro catalyst calendar** — `data_extractors/macro_calendar_extractor.py` landed (commit 2026-05-10). Builds forward-looking US macro release schedule from FRED release/dates API + FOMC scraping. Output: `historical_data/macro_catalyst_calendar.csv`. Consumed by `Finl_Agent_CC/tools/option_strategy.py`.
- **IBKR streaming infrastructure** — `ibkr_fast_extract.py` + `data_extractors/ibkr_streaming.py` ready for VPS deployment with IB Gateway. Writes `data_cache/ibkr_realtime.json` (3s atomic snapshots). Systemd unit: `deploy/systemd/macro2-ibkr-stream.service`.
- **Dashboard Data QA agent** — `agent/openai_agents/qa_agent.py` with 11 health checks, Minimax LLM triage, Telegram CRITICAL alerts. See `agent/SOP_DATA_QA.md` for operator workflow.
- **Polymarket tab (React)** — Tab 9 added to React dashboard showing prediction market events with price charts, volumes, and multi-outcome markets.
- **Housing starts HIGH alert** — FRED `HOUST` update lag (Census Mar data published but FRED hasn't propagated); not a code bug, monitor `data_extractors/fred_extractors.py`. QA score: 1 remaining HIGH, 54/100.
- **Stale VPS cron entries** — `/etc/cron.d` has legacy `fast_extract.py` / `scheduled_extract.py` entries using `/usr/bin/python3` (causes `ModuleNotFoundError: fredapi`); systemd timers are the authoritative schedulers. Chip spawned for cleanup; pending user action on VPS.
- **VPS deploys are rsync, not `git pull`** — `/root/macro_2` on <VPS_HOST> is **not a git repo**; it's a file-sync target. Pushing to GitHub does NOT update the VPS. Deploy with `rsync -avz <changed files> hostinger:/root/macro_2/...`, then restart the affected unit (`macro-react.service` for backend/frontend changes). Frontend also needs `npx vite build` + `gzip -k9f dist/assets/*` + rsync of `dist/`. (Resolved 2026-09-01 the prior "VPS unreachable" thread — host has been reachable and deployed to throughout.)
- **MCP server conversion** — design + RAM/performance analysis in [`MCP_CONVERSION_PLAN.md`](MCP_CONVERSION_PLAN.md) (proposed, not started). 5th frontend wrapping `data_aggregator` via MCP (stdio + VPS HTTP); ~485 MB standalone RAM or share the React process. External mirror: `~/.claude/plans/how-would-you-convert-jaunty-quasar.md`.

- **International PMI has no free source** — EU/JP/CN/UK manufacturing PMI remain `None` in `81_global_pmi`. EconDB carries no manufacturing PMI series (`obb.economy.pmi` was removed from the OpenBB router) and Trading Economics now renders the value client-side, breaking the `"last":` JSON regex. Needs a paid feed or a headless-browser scrape. The same TE change also costs `43_ism_services` its `change_1d`/`interpretation`.
- **`openbb-yfinance` is unsatisfied in `venv-openbb`** — deliberately: `yfinance` is pinned to 1.2.0 there to match the shared venv so every extractor behaves identically across jobs, while `openbb-yfinance 1.6.3` wants >=1.4.0. No indicator uses the OpenBB yfinance provider as its serving path, so this is inert — but a future `pip install` in that venv may try to "fix" it.

- **CSV writers are locked and atomic (v2.9.1, 2026-09-16)** — see CLAUDE.md "Append-only CSVs". Seven feed defects fixed the same day (gold blank-timestamp row, treasury curve column split, VIX/SKEW history frozen since 08-28, 10Y/2Y/VIX same-date duplicates, jpy date labels, AAII misparse, SPY trailing EPS); details in QA_SOP.md Bug Log and agent/QA_learnings.md. One-off cleanup: `scripts/repair_feed_defects_20260916.py`, backups in `/root/macro_2/.deploy_backup_20260916/`. **Open:** AAII weekly history needs a manually downloaded `sentiment.xls` (scripted requests hit Imperva); `natural_gas_fred.csv` mixes FRED Henry Hub *spot* with IBKR NG *futures* rows (`ibkr_streaming.py` NG spec).

## Known infrastructure quirks

- **The full extraction transiently wipes `86_polymarket` (Tab 9 goes blank ≤3 min)** — `scheduled_extract.py` writes the WHOLE cache from `fetch_all_indicators()`, which does not produce Polymarket; that key is owned by `polymarket_extract.py` (5-min partial merge). So every daily full extraction drops it, and `polymarket_extract.py`'s 180 s freshness guard means an immediate re-run *skips* rather than restores — it self-heals only on the next scheduled tick. If you need it back now: `./venv/bin/python polymarket_extract.py --force`. The same shape applies to any partial-merge-owned key (`84`/`85` survive only because `hl_extract` happens to run after). Diagnosed 2026-08-30; not fixed — fixing means changing `scheduled_extract.py`'s whole-cache write semantics.
- **A systemd `MemoryPeak` from a freshness-guard-skipped run is not the steady-state peak** — `hl-extract` measured 6 MB on a run whose guard short-circuited it, versus ~188 MB when it actually works (that wrong figure reached this file and was corrected 2026-09-01). Check `journalctl -u <unit> | grep Consumed` and compare CPU time across runs: sub-second CPU means the guard skipped and the memory figure is meaningless. Always sample several consecutive runs before recording a peak here.
- **awehawk.cloud is HTTPS since 2026-08-31** — certbot-managed cert (`/etc/nginx/sites-enabled/dashboards` now edited by certbot on renewal; backups in `/root/nginx-backups/`, NOT in sites-enabled — nginx parses everything there). HTTP 301s to HTTPS, `http2 on;`. `server_name` is explicit now, no longer `_`.
- **Yahoo serves price-less trailing bars** — Yahoo intermittently returns the most recent daily bar with OHLC all `NaN` and only Volume populated, across every US cash equity/ETF/index at once (futures and FX unaffected). Observed 2026-08-28. All `yf.Ticker` access now goes through `data_extractors/yf_safe.py`, which trims those rows at the fetch boundary. **Never add a raw `yf.Ticker(...)` call** — use `yf_safe.Ticker(...)` or the null resurfaces.
- **Two venvs on the VPS, on purpose** — `openbb-core` hard-pins `uvicorn<0.41`; installing OpenBB into `/root/macro_2/venv` would downgrade the uvicorn running `macro-react.service` (0.42.0 → 0.40.0). Hence `venv-openbb`, wired in via `/etc/systemd/system/macro-extract.service.d/openbb-venv.conf`. Do not `pip install openbb` into the shared venv. **Conversely: a new dependency added to `requirements.txt` must be installed into BOTH venvs** — the 5-minute jobs run on `venv`, but the daily full extraction runs on `venv-openbb`, so installing only into `venv` leaves `macro-extract.service` to `ImportError` at 00:30 UTC while every fast job stays green. `statsmodels` was added to `requirements.txt` on 2026-09-09 for the pairs cointegration test and is installed in both (dry-run confirmed the uvicorn/yfinance pins untouched).
- **OECD SDMX 3.0 migration** — Old `DSD_CLI@DF_CLI,1.0` endpoint 404s; new URL requires 9 key dimensions; VPS datacenter IPs get throttled. `_oecd_cli_fallback()` in `openbb_extractors.py` uses CFNAI (FRED:CFNAI) as Tier 3, normalised to `100 + (cfnai × 10)`. Staleness guard skips FRED Tier 2 if data is >400 days old.
- **yfinance delisted symbols emit 404 WARNING noise** — `VX=F`, `^PCPUT`, `^BDI`, `BDIY` are all delisted from Yahoo Finance. Suppressed in `yfinance_extractors.py` via `_suppress_yf_warnings()` context manager; these symbols return `{'error': ...}` gracefully; logs are now clean.
- **SEC EDGAR rate limit** — 10 req/sec max; `sec_extractor.py` uses `_rate_limit()` helper. Don't run parallel SEC extraction without delay.
- **VPS stale cron (pre-systemd)** — Crontab still has 6 entries for fast/scheduled extract using system Python; they fail silently. Systemd timers are live. Clean crontab when VPS is accessible.

## What to read first (cold-start orientation)

1. `CLAUDE.md` — session anchor, full architecture, all design decisions, known-broken indicators table
2. `QA_SOP.md` — mandatory testing checklist before every commit
3. `agent/QA_learnings.md` — accumulated fix history (root causes + solutions for all past bugs)
4. `agent/SOP_DATA_QA.md` — operator SOP for the Dashboard Data QA agent (severity levels, triage workflow)
5. `data_aggregator.py` — orchestrator; understand the fetch-all → cache → CSV flow here first

---

## Manual notes

_(Content below is preserved from prior hand-edited STATUS.md — auto-maintained sections above take precedence.)_

### Project: Macroeconomic Indicators Dashboard
**Version:** 2.9.1 | **Repository:** https://github.com/cdavocazh/macro_2

### Dashboard Frontends (4 implementations)

| Frontend | Folder | Port(s) | Status |
|----------|--------|---------|--------|
| **Streamlit** | `app.py` | 8501 | Production — compact CSS, 88+ indicators |
| **Dash** | `dash_dashboard/` | 8050 | Production — gunicorn, all 8 tabs, candlestick charts |
| **React + FastAPI** | `react_dashboard/` | 5173 + 8002 | Production — Vite + React 18, WebSocket HL live |
| **Grafana** | `grafana_dashboard/` | 3000 + 8001 | v1.0.0 — Docker or Homebrew, 70+ stat panels |

### Scheduling (macOS launchd)
- **hl-extract**: Every 1 min (24/7) — HL perps + spot, 45s freshness guard, 50s timeout
- **fast-extract**: Every 5 min (24/7) — 31 yfinance extractors (~5s), 3-min freshness guard, 4-min timeout
- **scheduled-extract**: 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) — full extraction, 15-min freshness guard, 20-min timeout

### Known Limitations
| Issue | Impact | Workaround |
|-------|--------|------------|
| Forward P/E 403 errors | MacroMicro bot detection; `1_sp500_forward_pe` falls back to SPY *trailing* P/E, so the card labelled "Forward P/E" is an approximation | **No real forward P/E is available anywhere in the project (2026-09-16).** `65_sp500_multiples` is served by multpl.com (its Finviz tier is dead), and its `forward_pe` is `100 / earnings yield` — a *trailing* yield — so it equals the trailing P/E; the forward ERP inherits this. Needs a real forward-estimate source |
| TSM (IFRS) | SEC EDGAR returns no us-gaap data | Yahoo Finance only |
| Baltic Dry Index | yfinance ^BDI/BDIY delisted | Returns error dict gracefully |
| VX=F / ^PCPUT delisted | yfinance 404 | Returns error dict gracefully; logs suppressed |
| Tab 6 in Grafana | Interactive ticker selection not suited | Use Streamlit/Dash/React |
| Housing Starts (FRED) | FRED update lag vs Census | Not a code bug; monitor for propagation |
