# SOP — Data QA for `macro_2` Dashboard

**Audience:** Operator of the macro_2 dashboard at `http://187.77.136.160/` and the IBKR portfolio dashboard at `http://187.77.136.160/IBKR_KZ/`.

**Purpose:** This SOP defines the data-quality checks the automated QA agent runs every 12 hours against every data source the dashboard depends on. It also defines the log format and how to triage flagged issues.

---

## 1. Scope of QA

| Surface | Source | Coverage |
|---------|--------|----------|
| 88 indicators in `data_cache/all_indicators.json` | yfinance + FRED + web scrapers + SEC + CFTC + IBKR overlay | All keys, freshness vs SLA, error fields, value sanity |
| 17 IBKR streaming instruments (`data_cache/ibkr_realtime.json`) | IBKR API via `ibkr_fast_extract.py` daemon | Tick freshness per instrument, subscription health, snapshot age |
| FRED CSVs in `historical_data/` | FRED API via `scheduled_extract.py` | Tail date vs FRED API current value, gaps, revision drift |
| Equity financials | Yahoo Finance + SEC EDGAR | Cross-source comparison via existing `compare_sources` tool |
| Backend HTTP endpoints | FastAPI on port 8002 | 200 OK + payload sanity for `/api/status`, `/api/indicators`, `/api/ibkr/contracts/*`, `/api/ibkr/subscriptions` |
| Streaming services | systemd | All `macro-*` services and timers active, no recent failures |
| IB Gateway | Docker | Container running, port 4001 listening, account responding |
| Cache vs CSV consistency | Cross-source | Latest cache prices match the last row of the corresponding CSV |

Out of scope: Hyperliquid (deferred per user), historical data older than 90 days (separate audit).

## 2. Severity Levels

The agent classifies each finding into **5 severity tiers**. Field operators triage CRITICAL and HIGH within 1 hour; MEDIUM next business day; LOW logged but not actioned individually.

| Severity | Definition | Typical Response Time |
|----------|------------|----------------------|
| **CRITICAL** | Service down / dashboard unavailable / IB Gateway dead / data corruption | Within 1 hour |
| **HIGH** | Daily-frequency data >7 days stale; weekly data >2 weeks stale; monthly data >1 month past expected release; cache contains errors; IBKR subscription dead with market open | Within 4 hours |
| **MEDIUM** | Daily data 3-7 days stale; cross-source value deviation >2%; CSV vs cache drift >1%; expected release missed by ≤1 day | Next business day |
| **LOW** | Daily data 1-3 days stale (acceptable lag); minor formatting issues; rounding mismatches; non-critical optional metrics missing | Logged, batched weekly |
| **INFO** | Healthy update detected; expected behavior; status notes | No action |

**Edge cases:**
- A FRED indicator showing `None` is HIGH (likely an extraction failure)
- An IBKR instrument with no ticks during weekend / market closed = LOW (expected)
- An IBKR instrument with no ticks during US trading hours = HIGH
- A scheduled extract that ran but produced 0 indicators = CRITICAL
- A scheduled extract that failed to run at all = HIGH (after 6h of missed schedule)

## 3. The 11 Standard Checks

Each check returns 0+ `Finding` objects (severity + category + indicator + message + suggested_fix).

| ID | Name | Tool | Frequency | Severity Range |
|----|------|------|-----------|---------------|
| C1 | `check_indicator_freshness` | Compares `latest_date` of every indicator vs its expected SLA (daily/weekly/monthly). Uses metadata dict mapping each indicator → SLA. | every run | LOW–HIGH |
| C2 | `check_indicator_errors` | Scans cache for `{"error": ...}` entries. Groups by error pattern. | every run | HIGH (if any) |
| C3 | `check_ibkr_streaming_health` | For each of 17 IBKR instruments, checks `last_update` ≤ 15 min during market hours. Verifies daemon snapshot ≤ 5 min old. | every run | LOW–HIGH |
| C4 | `check_fred_csv_freshness` | For each FRED CSV in `historical_data/`, sample 5–10 series and compare tail date with current FRED API value. Reports gaps. | every run | MEDIUM–HIGH |
| C5 | `check_yfinance_vs_ibkr_consistency` | For overlapping instruments (gold, silver, copper, ES, etc.), compare yfinance daily close vs IBKR `prev_close`. Flag deviations >1%. | every run | MEDIUM |
| C6 | `check_cache_vs_csv_consistency` | Verify cache `price` matches the last row of the per-instrument CSV in `historical_data/`. | every run | LOW–MEDIUM |
| C7 | `check_dashboard_endpoints` | HTTP probe `/api/status`, `/api/indicators`, `/api/ibkr/contracts/GC`, `/api/ibkr/subscriptions`. | every run | CRITICAL on 5xx |
| C8 | `check_systemd_services` | Run `systemctl is-active` + check journal for failures in last 12h on: macro-react, macro2-ibkr-stream, macro-fast-extract.timer, macro-cache-repair.timer, ibkr-dashboard, ib-health-monitor.timer. | every run | CRITICAL if down |
| C9 | `check_ib_gateway_health` | `docker ps` for ib-gateway-ib-gateway-1, `ss -tlnp` for port 4001, lightweight account ping with `clientId=99`. | every run | CRITICAL if dead |
| C10 | `check_equity_financials_drift` | Reuse existing `compare_sources` tool from agent/shared/tools.py — checks Yahoo vs SEC for top tickers. | weekly only | MEDIUM |
| C11 | `compute_data_quality_score` | Aggregate: 100 minus (CRITICAL × 30 + HIGH × 10 + MEDIUM × 3 + LOW × 0.5). | every run | INFO |

## 4. Indicator Freshness SLAs

Used by `check_indicator_freshness` (C1). Stored as a Python dict in `agent/shared/freshness_sla.py`.

| Frequency tier | SLA (max age before HIGH) | Tolerance (LOW threshold) | Examples |
|---------------|---------------------------|---------------------------|----------|
| **Real-time (IBKR)** | 15 min during market hours | 5 min | All 17 IBKR instruments |
| **Daily** | 3 business days | 1 business day | VIX, DXY, treasury yields, HY/IG OAS, breakeven, gold, ES |
| **Weekly** | 14 days | 7 days | Initial claims, NFCI, mortgage 30Y, gasoline, fed balance sheet |
| **Monthly** | 45 days | 35 days | CPI, PCE, NFP, unemployment, housing starts, retail sales, JOLTS |
| **Quarterly** | 100 days | 95 days | GDP, productivity, bank lending standards, delinquency rates |
| **Other** | Per-indicator override | — | COT (weekly), FF futures (daily), Fama-French (monthly) |

Market hours for IBKR (US futures): Sun 18:00 ET → Fri 17:00 ET, with 1h daily break. Outside market hours, no-tick = LOW.

## 5. Log Output Format

The agent writes two streams:

### 5.1 Human-readable Markdown report (per run)
Path: `/var/log/macro-data-qa/YYYY-MM-DD-HHMM.md`

Structure:
```markdown
# Data QA Report — 2026-04-15 11:00 GMT+8

## Summary
- Data Quality Score: **87 / 100**
- Findings: 0 CRITICAL · 2 HIGH · 5 MEDIUM · 12 LOW

## Critical
*(none)*

## High
- **C2 / 45_ig_oas** — Cache contains error: "FRED Internal Server Error"
  Suggested fix: Run `python /root/macro_2/scripts/repair_cache_errors.py`

- **C3 / EURUSD** — IBKR ticker has 0 ticks for 47 minutes (FX market open)
  Suggested fix: Restart `systemctl restart macro2-ibkr-stream`

## Medium
... (truncated)

## LLM Synthesis
The cache repair timer should have run 3 times since the last QA cycle.
Check `journalctl -u macro-cache-repair.timer` for errors. The EURUSD
issue is recurring — consider increasing IBKR subscription timeout from
10s to 20s in ibkr_streaming.py:294.

## Run Metadata
- Started: 2026-04-15T11:00:00+08:00
- Duration: 47.3s
- Tools called: 11
- LLM tokens: ~6,200
```

### 5.1a Historical Context (prior 3 runs)

Before LLM synthesis, the agent loads:
- **Prior event stats** from `qa-events.jsonl` — severity counts per run + any
  issue (`check_id / indicator`) that has appeared in ≥2 of the last 3 runs
  (flagged as "recurring")
- **Prior markdown reports** — up to 3 previous `YYYY-MM-DD-HHMM.md` files
  (most recent first, truncated to 6KB each) passed as context

The LLM uses this history to:
- Promote priority of recurring issues (a HIGH that has appeared 3 runs in a row
  is more urgent than a new HIGH)
- Detect regressions (score trending down) vs improvements (score recovering)
- Avoid raising new alerts for known/chronic problems already being tracked

If `/var/log/macro-data-qa/` is empty (first run ever), context is skipped
silently — the agent still runs normally on just the current findings.

### 5.2 Structured JSONL events (machine-readable)
Path: `/var/log/macro-data-qa/qa-events.jsonl` (append-only)

One JSON object per line, suitable for `jq` / Loki / log shippers:
```json
{"ts": "2026-04-15T11:00:23+08:00", "run_id": "20260415-1100", "severity": "HIGH", "check_id": "C2", "category": "cache_error", "indicator": "45_ig_oas", "message": "FRED Internal Server Error", "suggested_fix": "Run repair_cache_errors.py", "context": {"latest_date": "2026-04-10", "error_full": "..."}}
{"ts": "2026-04-15T11:00:24+08:00", "run_id": "20260415-1100", "severity": "INFO", "check_id": "C11", "category": "score", "score": 87, "weights": {"CRITICAL": 30, "HIGH": 10, "MEDIUM": 3, "LOW": 0.5}}
```

### 5.3 Telegram alert (immediate)
For CRITICAL findings only, the agent posts to the existing Telegram bot (`TELEGRAM_BOT_TOKEN` from `/root/Finl_Agent_CC/.env`):
```
🚨 Data QA CRITICAL @ 2026-04-15 11:00 GMT+8
3 critical issues found:
- macro2-ibkr-stream service is DOWN
- Backend /api/indicators returning 503
- IB Gateway port 4001 not listening

Score: 12/100 — DASHBOARD UNUSABLE
Full report: /var/log/macro-data-qa/2026-04-15-1100.md
```

## 6. Run Schedule

- **Cron:** systemd timer `macro-data-qa.timer` runs every 12h at **00:00 UTC and 12:00 UTC** (= 08:00 and 20:00 GMT+8)
- **Manual run:** `systemctl start macro-data-qa.service` or `python -m agent.openai_agents.qa_agent`
- **On-demand single check:** `python -m agent.openai_agents.qa_agent --check C3` (run only IBKR check)

## 7. Triage Workflow

When a CRITICAL or HIGH finding lands:

1. Read the latest report at `/var/log/macro-data-qa/`
2. Apply the `suggested_fix` from the finding (most are one-liners)
3. Re-run the QA agent to confirm: `systemctl start macro-data-qa.service`
4. If the score doesn't recover, escalate to manual debugging
5. Add a brief note to `/var/log/macro-data-qa/triage-log.md` with:
   - Time of detection
   - Action taken
   - Outcome
   - Whether the fix needs to be persisted (e.g., as a permanent code change)

## 8. Versioning & Maintenance

- This SOP version: **v1.0** (2026-04-15)
- Add a new check: extend `agent/shared/qa_tools.py` with a `@tool` and update `STANDARD_CHECKS` list in `agent/openai_agents/qa_agent.py`
- Update SLA: edit `agent/shared/freshness_sla.py`
- Adjust severity weights: edit `compute_data_quality_score` in `agent/shared/qa_tools.py`
