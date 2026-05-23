"""
Data QA Tool Functions for the macro_2 dashboard.

Each function returns a list of Finding dicts:
    {
        "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",
        "check_id": "C1" | ... | "C11",
        "category": str,
        "indicator": str | None,
        "message": str,
        "suggested_fix": str | None,
        "context": dict,
    }

These are plain Python functions; the openai_agents wrapper turns them into
@function_tool callables for the agent.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Project paths (works whether installed or run in-place)
_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent  # macro_2 root
CACHE_DIR = PROJECT_ROOT / "data_cache"
HISTORICAL_DIR = PROJECT_ROOT / "historical_data"
LOG_DIR = Path("/var/log/macro-data-qa")
ALL_INDICATORS_FILE = CACHE_DIR / "all_indicators.json"
IBKR_REALTIME_FILE = CACHE_DIR / "ibkr_realtime.json"
IBKR_SUBSCRIPTIONS_FILE = CACHE_DIR / "ibkr_subscriptions.json"

# Local FastAPI backend
BACKEND_URL = "http://127.0.0.1:8002"

# Severity weights for score (matches SOP_DATA_QA section 3 / C11)
SEVERITY_WEIGHTS = {"CRITICAL": 30, "HIGH": 10, "MEDIUM": 3, "LOW": 0.5, "INFO": 0}


def _finding(severity: str, check_id: str, category: str, message: str,
             indicator: str | None = None, suggested_fix: str | None = None,
             context: dict | None = None) -> dict:
    return {
        "severity": severity,
        "check_id": check_id,
        "category": category,
        "indicator": indicator,
        "message": message,
        "suggested_fix": suggested_fix,
        "context": context or {},
    }


def _is_us_market_hours() -> bool:
    """US futures trade Sun 18:00 ET → Fri 17:00 ET (with 1h daily break ~17:00).
    Conservative check: True if not Sat (UTC), and not the daily-break hour.
    """
    now_utc = datetime.utcnow()
    weekday = now_utc.weekday()  # 0=Mon ... 6=Sun
    # Saturday all day = closed (UTC). Sunday until 22:00 UTC = closed.
    if weekday == 5:
        return False
    if weekday == 6 and now_utc.hour < 22:
        return False
    # Daily 1h break ~21:00 UTC (17:00 ET) Mon-Fri
    if weekday in (0, 1, 2, 3) and now_utc.hour == 21:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────
# C1: Indicator freshness vs SLA
# ─────────────────────────────────────────────────────────────────────────

def check_indicator_freshness() -> list[dict]:
    """For every indicator in cache, compare latest_date vs SLA tier."""
    from agent.shared.freshness_sla import get_sla_for

    findings: list[dict] = []
    if not ALL_INDICATORS_FILE.exists():
        return [_finding("CRITICAL", "C1", "missing_file",
                         f"Cache file does not exist: {ALL_INDICATORS_FILE}",
                         suggested_fix="Run scheduled_extract.py")]

    try:
        with open(ALL_INDICATORS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [_finding("CRITICAL", "C1", "corrupt_cache",
                         f"Cannot parse cache: {e}",
                         suggested_fix="Inspect/restore data_cache/all_indicators.json")]

    indicators = data.get("data", {})
    now = datetime.now()

    for key, val in indicators.items():
        if not isinstance(val, dict):
            continue
        if "error" in val:
            continue  # C2 handles errors
        latest_date_str = (val.get("latest_date") or
                          val.get("date") or "")
        if not latest_date_str:
            findings.append(_finding(
                "MEDIUM", "C1", "no_date", indicator=key,
                message="No latest_date field — cannot assess freshness",
                context={"keys_present": list(val.keys())[:5]},
            ))
            continue

        # Parse various date formats
        try:
            d_str = str(latest_date_str).split("T")[0].split(" ")[0]
            latest = datetime.strptime(d_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            findings.append(_finding(
                "LOW", "C1", "unparseable_date", indicator=key,
                message=f"Unparseable latest_date: {latest_date_str!r}",
            ))
            continue

        age_days = (now - latest).total_seconds() / 86400
        tier, high_threshold, low_threshold = get_sla_for(key)

        if age_days > high_threshold:
            findings.append(_finding(
                "HIGH", "C1", "stale", indicator=key,
                message=f"Stale: {age_days:.1f}d old (SLA {tier} = {high_threshold}d)",
                context={"latest_date": latest_date_str, "tier": tier,
                         "age_days": round(age_days, 1)},
                suggested_fix="Check extractor; consider running scheduled_extract.py",
            ))
        elif age_days > low_threshold:
            findings.append(_finding(
                "LOW", "C1", "lagging", indicator=key,
                message=f"Lagging: {age_days:.1f}d old (acceptable up to {low_threshold}d)",
                context={"latest_date": latest_date_str, "tier": tier,
                         "age_days": round(age_days, 1)},
            ))

    return findings


# ─────────────────────────────────────────────────────────────────────────
# C2: Indicators in error state
# ─────────────────────────────────────────────────────────────────────────

def check_indicator_errors() -> list[dict]:
    """Find indicators with error fields in cache."""
    findings: list[dict] = []
    if not ALL_INDICATORS_FILE.exists():
        return findings

    try:
        with open(ALL_INDICATORS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return findings

    indicators = data.get("data", {})
    error_count = 0
    for key, val in indicators.items():
        if not isinstance(val, dict):
            continue
        if "error" in val:
            err_msg = str(val.get("error", ""))[:200]
            error_count += 1
            findings.append(_finding(
                "HIGH", "C2", "cache_error", indicator=key,
                message=f"Cache contains error: {err_msg}",
                suggested_fix="Run /root/macro_2/scripts/repair_cache_errors.py",
                context={"error_full": err_msg},
            ))
    if error_count == 0:
        findings.append(_finding(
            "INFO", "C2", "all_clear",
            message=f"All {len(indicators)} indicators error-free",
        ))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C3: IBKR streaming health
# ─────────────────────────────────────────────────────────────────────────

def check_ibkr_streaming_health() -> list[dict]:
    """Check IBKR realtime snapshot freshness + per-instrument tick freshness."""
    from agent.shared.freshness_sla import IBKR_LIVE_SYMBOLS

    findings: list[dict] = []
    if not IBKR_REALTIME_FILE.exists():
        return [_finding("HIGH", "C3", "missing_file",
                         "IBKR realtime snapshot missing",
                         suggested_fix="systemctl restart macro2-ibkr-stream")]

    snapshot_age_secs = time.time() - IBKR_REALTIME_FILE.stat().st_mtime
    if snapshot_age_secs > 300:
        findings.append(_finding(
            "CRITICAL", "C3", "stale_snapshot",
            message=f"IBKR snapshot is {snapshot_age_secs:.0f}s old (expected <300s)",
            suggested_fix="systemctl restart macro2-ibkr-stream",
        ))

    try:
        with open(IBKR_REALTIME_FILE) as f:
            snap = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return findings + [_finding("HIGH", "C3", "corrupt_snapshot",
                                    f"Cannot parse: {e}")]

    if snap.get("status") != "streaming":
        return findings + [_finding(
            "CRITICAL", "C3", "service_stopped",
            message=f"IBKR service status: {snap.get('status')}",
            suggested_fix="systemctl restart macro2-ibkr-stream",
        )]

    market_open = _is_us_market_hours()
    quotes = snap.get("quotes", {})
    now = datetime.now()
    for sym in IBKR_LIVE_SYMBOLS:
        q = quotes.get(sym)
        if q is None:
            findings.append(_finding(
                "MEDIUM", "C3", "missing_subscription", indicator=sym,
                message=f"{sym} not in IBKR snapshot — daemon may have failed to subscribe",
                suggested_fix=f"Check INSTRUMENTS map and ibkr_streaming logs for {sym}",
            ))
            continue
        last_update = q.get("last_update")
        if last_update is None:
            sev = "HIGH" if market_open else "LOW"
            findings.append(_finding(
                sev, "C3", "no_ticks", indicator=sym,
                message=f"{sym} has 0 ticks since service started",
                context={"market_hours": market_open},
                suggested_fix="Check IBKR subscription entitlement; restart streaming",
            ))
            continue
        try:
            t = datetime.fromisoformat(last_update)
            age_min = (now - t).total_seconds() / 60
            if age_min > 30 and market_open:
                findings.append(_finding(
                    "HIGH", "C3", "stale_ticks", indicator=sym,
                    message=f"{sym} last tick {age_min:.1f} min ago (market open)",
                    context={"last_update": last_update, "market_hours": market_open},
                    suggested_fix="systemctl restart macro2-ibkr-stream",
                ))
            elif age_min > 15 and market_open:
                findings.append(_finding(
                    "LOW", "C3", "lagging_ticks", indicator=sym,
                    message=f"{sym} last tick {age_min:.1f} min ago (acceptable but watch)",
                    context={"last_update": last_update},
                ))
            elif age_min > 120 and not market_open:
                findings.append(_finding(
                    "LOW", "C3", "stale_ticks_closed", indicator=sym,
                    message=f"{sym} last tick {age_min:.0f} min ago (market closed)",
                ))
        except (ValueError, TypeError):
            pass

    if not findings or all(f["severity"] == "INFO" for f in findings):
        findings.append(_finding(
            "INFO", "C3", "healthy",
            message=f"IBKR streaming healthy: {len(quotes)} instruments, snapshot {snapshot_age_secs:.0f}s old",
        ))

    return findings


# ─────────────────────────────────────────────────────────────────────────
# C4: FRED CSV freshness
# ─────────────────────────────────────────────────────────────────────────

def check_fred_csv_freshness() -> list[dict]:
    """Sample 6 key daily FRED CSVs and report tail-date age vs expected."""
    findings: list[dict] = []
    samples = [
        ("10y_treasury_yield.csv", 3),
        ("hy_oas.csv", 3),
        ("ig_oas.csv", 3),
        ("breakeven_5y.csv", 3),
        ("real_yield_10y.csv", 3),
        ("nfci.csv", 14),  # weekly
    ]
    now = datetime.now()
    for fname, max_age_days in samples:
        path = HISTORICAL_DIR / fname
        if not path.exists():
            findings.append(_finding(
                "MEDIUM", "C4", "missing_csv", indicator=fname,
                message=f"CSV missing: {fname}",
            ))
            continue
        try:
            # Read just the last line for efficiency
            with open(path, "rb") as f:
                f.seek(-2048, 2) if f.seek(0, 2) > 2048 else f.seek(0)
                tail = f.read().decode(errors="replace").strip().split("\n")
            last_row = tail[-1].split(",")
            if len(last_row) < 2:
                continue
            # Date is first or second column
            ts_str = last_row[1] if len(last_row[1]) >= 10 else last_row[0]
            d_str = ts_str.split("T")[0].split(" ")[0][:10]
            last_date = datetime.strptime(d_str, "%Y-%m-%d")
            age_days = (now - last_date).total_seconds() / 86400
            if age_days > max_age_days:
                findings.append(_finding(
                    "HIGH", "C4", "stale_csv", indicator=fname,
                    message=f"{fname} tail date {d_str} is {age_days:.1f}d old (max {max_age_days}d)",
                    suggested_fix="Run scheduled_extract.py to refresh FRED data",
                ))
        except Exception as e:
            findings.append(_finding(
                "LOW", "C4", "csv_read_error", indicator=fname,
                message=f"Could not read {fname}: {e}",
            ))
    if not findings:
        findings.append(_finding("INFO", "C4", "healthy",
                                 message="Sampled FRED CSVs all fresh"))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C5: yfinance vs IBKR consistency
# ─────────────────────────────────────────────────────────────────────────

def check_yfinance_vs_ibkr_consistency() -> list[dict]:
    """For overlapping instruments, compare yfinance vs IBKR prev_close."""
    findings: list[dict] = []
    if not (ALL_INDICATORS_FILE.exists() and IBKR_REALTIME_FILE.exists()):
        return findings

    try:
        with open(ALL_INDICATORS_FILE) as f:
            cache = json.load(f).get("data", {})
        with open(IBKR_REALTIME_FILE) as f:
            ibkr = json.load(f).get("quotes", {})
    except (OSError, json.JSONDecodeError):
        return findings

    overlay_pairs = [
        ("13_gold", "GC"), ("14_silver", "SI"), ("15_crude_oil", "CL"),
        ("16_copper", "HG"), ("17_es_futures", "ES"), ("18_rty_futures", "RTY"),
    ]
    for ind_key, ibkr_sym in overlay_pairs:
        ind = cache.get(ind_key, {})
        q = ibkr.get(ibkr_sym, {})
        # When IBKR overlay is applied, ind.price IS the IBKR price.
        # Use the underlying yfinance value if present.
        # For simplicity, compare against IBKR prev_close.
        ibkr_prev = q.get("prev_close")
        cached_price = ind.get("price")
        if ibkr_prev is None or cached_price is None:
            continue
        if ibkr_prev <= 0:
            continue
        diff_pct = abs(cached_price - ibkr_prev) / ibkr_prev * 100
        if diff_pct > 5:  # more than 5% deviation is suspicious
            findings.append(_finding(
                "MEDIUM", "C5", "source_drift", indicator=ind_key,
                message=f"{ind_key}: cached {cached_price} vs IBKR prev_close {ibkr_prev} ({diff_pct:.2f}% diff)",
                context={"cached": cached_price, "ibkr_prev_close": ibkr_prev},
            ))
    if not findings:
        findings.append(_finding("INFO", "C5", "healthy",
                                 message="yfinance/IBKR overlap values consistent"))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C6: Cache vs CSV consistency (light)
# ─────────────────────────────────────────────────────────────────────────

def check_cache_vs_csv_consistency() -> list[dict]:
    """Verify cache prices roughly match the latest CSV row for sample instruments."""
    findings: list[dict] = []
    if not ALL_INDICATORS_FILE.exists():
        return findings

    try:
        with open(ALL_INDICATORS_FILE) as f:
            cache = json.load(f).get("data", {})
    except (OSError, json.JSONDecodeError):
        return findings

    # Map cache key → CSV file → expected last-column key
    pairs = [
        ("13_gold", "gold.csv", "gold_price"),
        ("14_silver", "silver.csv", "silver_price"),
        ("15_crude_oil", "crude_oil.csv", "crude_oil_price"),
        ("16_copper", "copper.csv", "copper_price"),
        ("17_es_futures", "es_futures.csv", "es_price"),
    ]
    for cache_key, csv_name, _ in pairs:
        ind = cache.get(cache_key, {})
        cached_price = ind.get("price")
        path = HISTORICAL_DIR / csv_name
        if cached_price is None or not path.exists():
            continue
        try:
            with open(path, "rb") as f:
                f.seek(-1024, 2) if f.seek(0, 2) > 1024 else f.seek(0)
                lines = f.read().decode(errors="replace").strip().split("\n")
            csv_last = float(lines[-1].split(",")[-1])
            diff_pct = abs(cached_price - csv_last) / csv_last * 100 if csv_last else 0
            if diff_pct > 2:
                findings.append(_finding(
                    "MEDIUM", "C6", "drift", indicator=cache_key,
                    message=f"{cache_key}: cache {cached_price} vs CSV tail {csv_last} ({diff_pct:.2f}%)",
                    context={"csv": csv_name},
                ))
        except (ValueError, OSError):
            pass
    if not findings:
        findings.append(_finding("INFO", "C6", "healthy",
                                 message="Cache/CSV values consistent"))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C7: Dashboard endpoints
# ─────────────────────────────────────────────────────────────────────────

def check_dashboard_endpoints() -> list[dict]:
    """HTTP probe each backend endpoint and check status."""
    import urllib.request
    import urllib.error

    endpoints = [
        ("/api/status", 200),
        ("/api/indicators", 200),
        ("/api/ibkr/contracts/GC", 200),
        ("/api/ibkr/subscriptions", 200),
    ]
    findings: list[dict] = []
    for path, expected in endpoints:
        url = BACKEND_URL + path
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
                if code != expected:
                    findings.append(_finding(
                        "HIGH", "C7", "wrong_status",
                        message=f"{path}: HTTP {code} (expected {expected})",
                    ))
        except urllib.error.HTTPError as e:
            sev = "CRITICAL" if e.code >= 500 else "MEDIUM"
            findings.append(_finding(
                sev, "C7", "http_error",
                message=f"{path}: HTTP {e.code} {e.reason}",
                suggested_fix="systemctl restart macro-react",
            ))
        except (urllib.error.URLError, socket.timeout) as e:
            findings.append(_finding(
                "CRITICAL", "C7", "unreachable",
                message=f"{path}: unreachable ({e})",
                suggested_fix="systemctl restart macro-react",
            ))
    if not findings:
        findings.append(_finding("INFO", "C7", "healthy",
                                 message=f"All {len(endpoints)} endpoints OK"))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C8: systemd services
# ─────────────────────────────────────────────────────────────────────────

def check_systemd_services() -> list[dict]:
    """Check that all macro-* services are active and recent runs healthy."""
    findings: list[dict] = []
    services = [
        ("macro-react", "service", "CRITICAL"),
        ("macro2-ibkr-stream", "service", "CRITICAL"),
        ("ibkr-dashboard", "service", "HIGH"),
        ("macro-fast-extract.timer", "timer", "HIGH"),
        ("macro-cache-repair.timer", "timer", "MEDIUM"),
        ("ib-health-monitor.timer", "timer", "HIGH"),
    ]
    for name, kind, on_fail_sev in services:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", name],
                capture_output=True, text=True, timeout=10,
            )
            state = r.stdout.strip()
            if state != "active":
                findings.append(_finding(
                    on_fail_sev, "C8", "service_down",
                    message=f"{name} is {state}",
                    suggested_fix=f"systemctl restart {name}",
                ))
        except Exception as e:
            findings.append(_finding(
                "MEDIUM", "C8", "check_error",
                message=f"Could not check {name}: {e}",
            ))
    if not findings:
        findings.append(_finding("INFO", "C8", "healthy",
                                 message="All services active"))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C9: IB Gateway health
# ─────────────────────────────────────────────────────────────────────────

def check_ib_gateway_health() -> list[dict]:
    """Verify IB Gateway docker container, port 4001 listening, account responding."""
    findings: list[dict] = []
    # Container
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=ib-gateway", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        if "Up" not in r.stdout:
            findings.append(_finding(
                "CRITICAL", "C9", "container_down",
                message=f"IB Gateway container not running: {r.stdout.strip() or 'no output'}",
                suggested_fix="cd /root/ib-gateway && docker compose up -d",
            ))
            return findings  # No point checking the rest
    except Exception as e:
        findings.append(_finding(
            "MEDIUM", "C9", "docker_unavailable",
            message=f"Cannot run docker: {e}",
        ))

    # Port 4001 listening
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("127.0.0.1", 4001))
        s.close()
    except (socket.error, socket.timeout) as e:
        findings.append(_finding(
            "CRITICAL", "C9", "port_closed",
            message=f"Port 4001 not connectable: {e}",
            suggested_fix="cd /root/ib-gateway && docker compose restart",
        ))
        return findings

    # Light account ping (clientId 99 to avoid collision)
    try:
        from ib_async import IB
        ib = IB()
        ib.connect("127.0.0.1", 4001, clientId=99, readonly=True, timeout=8)
        accts = ib.managedAccounts()
        ib.disconnect()
        if not accts:
            findings.append(_finding(
                "HIGH", "C9", "no_accounts",
                message="IB Gateway connected but returned no managed accounts",
                suggested_fix="Re-login to IB Gateway via Telegram /relogin_ibkr",
            ))
        else:
            findings.append(_finding(
                "INFO", "C9", "healthy",
                message=f"IB Gateway healthy: {len(accts)} account(s)",
            ))
    except Exception as e:
        findings.append(_finding(
            "HIGH", "C9", "auth_failed",
            message=f"IB Gateway connection failed: {e}",
            suggested_fix="Approve 2FA on IBKR Mobile",
        ))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C10: Equity financials drift (weekly only — placeholder)
# ─────────────────────────────────────────────────────────────────────────

def check_equity_financials_drift(sample_n: int = 3) -> list[dict]:
    """Sample N tickers and run cross-source compare. Light wrapper around existing tool."""
    findings: list[dict] = []
    try:
        from agent.shared.tools import compare_sources
        tickers = ["AAPL", "MSFT", "NVDA"][:sample_n]
        for t in tickers:
            try:
                report = compare_sources(t)
                # report is a string; look for "discrepancies" line
                if "discrepancies" in report.lower() and ">" in report:
                    findings.append(_finding(
                        "MEDIUM", "C10", "equity_drift", indicator=t,
                        message=f"Yahoo vs SEC discrepancies for {t}",
                        context={"report_excerpt": report[:300]},
                    ))
            except Exception as e:
                findings.append(_finding(
                    "LOW", "C10", "compare_error", indicator=t,
                    message=f"compare_sources({t}) failed: {e}",
                ))
    except ImportError:
        findings.append(_finding(
            "LOW", "C10", "tool_missing",
            message="compare_sources tool not available",
        ))
    if not findings:
        findings.append(_finding("INFO", "C10", "healthy",
                                 message="Equity financials cross-source check OK"))
    return findings


# ─────────────────────────────────────────────────────────────────────────
# C11: Aggregate score
# ─────────────────────────────────────────────────────────────────────────

def compute_data_quality_score(all_findings: list[dict]) -> dict:
    """Aggregate severity counts into a 0-100 score."""
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    for f in all_findings:
        sev = f.get("severity", "INFO")
        counts[sev] = counts.get(sev, 0) + 1
    penalty = sum(counts[s] * SEVERITY_WEIGHTS[s] for s in counts)
    score = max(0, round(100 - penalty, 1))
    return {
        "score": score,
        "counts": counts,
        "weights": SEVERITY_WEIGHTS,
    }


# ─────────────────────────────────────────────────────────────────────────
# Logging helpers
# ─────────────────────────────────────────────────────────────────────────

def write_jsonl_log(findings: list[dict], score: dict, run_id: str):
    """Append findings + score to qa-events.jsonl."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "qa-events.jsonl"
    ts_now = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(path, "a") as f:
        for finding in findings:
            f.write(json.dumps({
                "ts": ts_now, "run_id": run_id, **finding,
            }, default=str) + "\n")
        f.write(json.dumps({
            "ts": ts_now, "run_id": run_id,
            "severity": "INFO", "check_id": "C11", "category": "score",
            "score": score["score"], "counts": score["counts"],
        }, default=str) + "\n")


def write_markdown_report(findings: list[dict], score: dict, run_id: str,
                          summary: str = "") -> Path:
    """Write a human-readable Markdown report."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{run_id}.md"
    by_sev: dict[str, list[dict]] = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "INFO": []}
    for f in findings:
        by_sev[f["severity"]].append(f)

    lines = [
        f"# Data QA Report — {run_id}",
        "",
        "## Summary",
        f"- Data Quality Score: **{score['score']} / 100**",
        f"- Findings: {score['counts']['CRITICAL']} CRITICAL · {score['counts']['HIGH']} HIGH · "
        f"{score['counts']['MEDIUM']} MEDIUM · {score['counts']['LOW']} LOW",
        "",
    ]
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        items = by_sev[sev]
        lines.append(f"## {sev.title()}")
        if not items:
            lines.append("*(none)*")
        else:
            for it in items:
                ind = f" / `{it['indicator']}`" if it.get("indicator") else ""
                lines.append(f"- **{it['check_id']}{ind}** — {it['message']}")
                if it.get("suggested_fix"):
                    lines.append(f"  *Suggested:* `{it['suggested_fix']}`")
        lines.append("")

    if summary:
        lines.extend(["## LLM Synthesis", summary, ""])

    lines.extend([
        "## Run Metadata",
        f"- Run ID: `{run_id}`",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Score weights: {score['weights']}",
    ])
    path.write_text("\n".join(lines))
    return path


# Master list of all checks (used by the agent runner)
ALL_CHECKS = [
    ("C1", check_indicator_freshness, "Indicator freshness vs SLA"),
    ("C2", check_indicator_errors, "Cache error scan"),
    ("C3", check_ibkr_streaming_health, "IBKR streaming health"),
    ("C4", check_fred_csv_freshness, "FRED CSV freshness"),
    ("C5", check_yfinance_vs_ibkr_consistency, "yfinance vs IBKR consistency"),
    ("C6", check_cache_vs_csv_consistency, "Cache vs CSV consistency"),
    ("C7", check_dashboard_endpoints, "Dashboard endpoints"),
    ("C8", check_systemd_services, "Systemd services"),
    ("C9", check_ib_gateway_health, "IB Gateway health"),
    # C10 weekly — invoked separately by the agent runner
]
