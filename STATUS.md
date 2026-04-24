# STATUS — macro_2

_Auto-maintained by `/update-session-status`. Last updated: 2026-04-24 — fixed OECD CLI staleness (CFNAI Tier 3 fallback) and suppressed yfinance 404 noise for delisted symbols; extended SP500 coverage to MidCap 400 + Russell 1000._

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
| VPS systemd timers | Hostinger VPS 187.77.136.160 | 2026-04-24 | 7 timers; fast_extract confirmed 404-clean (06:42 run) |

## Open threads

- **Housing starts HIGH alert** — FRED `HOUST` update lag (Census Mar data published but FRED hasn't propagated); not a code bug, monitor `data_extractors/fred_extractors.py`. QA score: 1 remaining HIGH, 54/100.
- **Stale VPS cron entries** — `/etc/cron.d` has legacy `fast_extract.py` / `scheduled_extract.py` entries using `/usr/bin/python3` (causes `ModuleNotFoundError: fredapi`); systemd timers are the authoritative schedulers. Chip spawned for cleanup; pending user action on VPS.
- **VPS unreachable** — 187.77.136.160 timed out during this session; changes pushed to GitHub main, VPS needs `git pull` in `/root/macro_2` (or wherever repo lives) once connectivity restores.

## Known infrastructure quirks

- **OECD SDMX 3.0 migration** — Old `DSD_CLI@DF_CLI,1.0` endpoint 404s; new URL requires 9 key dimensions; VPS datacenter IPs get throttled. `_oecd_cli_fallback()` in `openbb_extractors.py` uses CFNAI (FRED:CFNAI) as Tier 3, normalised to `100 + (cfnai × 10)`. Staleness guard skips FRED Tier 2 if data is >400 days old.
- **yfinance delisted symbols emit 404 WARNING noise** — `VX=F`, `^PCPUT`, `^BDI`, `BDIY` are all delisted from Yahoo Finance. Suppressed in `yfinance_extractors.py` via `_suppress_yf_warnings()` context manager; these symbols return `{'error': ...}` gracefully; logs are now clean.
- **SEC EDGAR rate limit** — 10 req/sec max; `sec_extractor.py` uses `_rate_limit()` helper. Don't run parallel SEC extraction without delay.
- **VPS stale cron (pre-systemd)** — Crontab still has 6 entries for fast/scheduled extract using system Python; they fail silently. Systemd timers are live. Clean crontab when VPS is accessible.

## What to read first (cold-start orientation)

1. `CLAUDE.md` — session anchor, full architecture, all design decisions, known-broken indicators table
2. `QA_SOP.md` — mandatory testing checklist before every commit
3. `agent/QA_learnings.md` — accumulated fix history (root causes + solutions for all past bugs)
4. `data_aggregator.py` — orchestrator; understand the fetch-all → cache → CSV flow here first

---

## Manual notes

_(Content below is preserved from prior hand-edited STATUS.md — auto-maintained sections above take precedence.)_

### Project: Macroeconomic Indicators Dashboard
**Version:** 2.7.0 | **Repository:** https://github.com/cdavocazh/macro_2

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
| Forward P/E 403 errors | MacroMicro bot detection | `65_sp500_multiples` (Finviz) provides alternative |
| TSM (IFRS) | SEC EDGAR returns no us-gaap data | Yahoo Finance only |
| Baltic Dry Index | yfinance ^BDI/BDIY delisted | Returns error dict gracefully |
| VX=F / ^PCPUT delisted | yfinance 404 | Returns error dict gracefully; logs suppressed |
| Tab 6 in Grafana | Interactive ticker selection not suited | Use Streamlit/Dash/React |
| Housing Starts (FRED) | FRED update lag vs Census | Not a code bug; monitor for propagation |
