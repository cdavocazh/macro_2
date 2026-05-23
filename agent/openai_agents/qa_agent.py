#!/usr/bin/env python3
"""
Data QA Agent for macro_2 dashboard — OpenAI Agents SDK + Minimax LLM.

Runs all 11 standard checks (defined in agent/shared/qa_tools.py),
collects findings, has the LLM synthesize a triage summary, and
writes both JSONL events and a Markdown report to /var/log/macro-data-qa/.

Run modes:
    python -m agent.openai_agents.qa_agent           # full QA run
    python -m agent.openai_agents.qa_agent --check C3   # single check
    python -m agent.openai_agents.qa_agent --no-llm     # skip LLM synthesis
    python -m agent.openai_agents.qa_agent --weekly     # include C10

Environment:
    MINIMAX_API_KEY  — required (unless --no-llm)
    MINIMAX_MODEL    — default "MiniMax-M2.5"
    MINIMAX_BASE_URL — default "https://api.minimax.io/v1"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Make project root importable
_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.shared.qa_tools import (
    ALL_CHECKS,
    LOG_DIR,
    check_equity_financials_drift,
    compute_data_quality_score,
    write_jsonl_log,
    write_markdown_report,
)


# ── Historical Context ──────────────────────────────────────────────────
# Load prior 3 runs so the LLM can see trends / recurring issues

HISTORY_RUNS = 3  # number of prior runs to include as context


def _load_prior_markdown_reports(n: int = HISTORY_RUNS,
                                 exclude_run_id: str | None = None) -> list[dict]:
    """Return up to N most-recent previous Markdown reports as {run_id, text}."""
    if not LOG_DIR.exists():
        return []
    md_files = sorted(
        (p for p in LOG_DIR.glob("*.md")
         if exclude_run_id is None or p.stem != exclude_run_id),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:n]
    out = []
    for p in md_files:
        try:
            text = p.read_text()
            if len(text) > 6000:  # truncate very long historical reports
                text = text[:6000] + "\n...[truncated]"
            out.append({"run_id": p.stem, "text": text})
        except OSError:
            continue
    # Oldest-first for chronological reading by LLM
    out.reverse()
    return out


def _load_prior_event_stats(exclude_run_id: str | None = None) -> dict:
    """Scan qa-events.jsonl for the N most-recent prior run_ids and summarize.

    Returns:
        {
          "runs_considered": [run_id, ...],
          "severity_counts_by_run": {run_id: {CRITICAL: 0, HIGH: 3, ...}, ...},
          "recurring_issues": {
              "{check_id}/{indicator|-}": {"runs_seen": [...], "last_message": ...}
          }
        }
    """
    events_path = LOG_DIR / "qa-events.jsonl"
    if not events_path.exists():
        return {"runs_considered": [], "severity_counts_by_run": {},
                "recurring_issues": {}}

    # Read all events (file is usually <few MB — fine to load in memory)
    by_run: dict[str, list[dict]] = {}
    try:
        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = obj.get("run_id")
                if not rid or rid == exclude_run_id:
                    continue
                by_run.setdefault(rid, []).append(obj)
    except OSError:
        return {"runs_considered": [], "severity_counts_by_run": {},
                "recurring_issues": {}}

    # Take the last N runs (lexicographically largest run_id = most recent, since
    # run_id format is YYYY-MM-DD-HHMM)
    recent_run_ids = sorted(by_run.keys())[-HISTORY_RUNS:]

    sev_counts: dict[str, dict] = {}
    issue_runs: dict[str, set] = {}
    last_message: dict[str, str] = {}

    for rid in recent_run_ids:
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for ev in by_run[rid]:
            sev = ev.get("severity", "INFO")
            counts[sev] = counts.get(sev, 0) + 1
            if sev in ("CRITICAL", "HIGH", "MEDIUM"):
                key = f"{ev.get('check_id', '?')}/{ev.get('indicator') or '-'}"
                issue_runs.setdefault(key, set()).add(rid)
                last_message[key] = str(ev.get("message", ""))[:200]
        sev_counts[rid] = counts

    # Only surface issues that appeared in ≥2 of the last N runs
    recurring = {
        k: {"runs_seen": sorted(v), "last_message": last_message.get(k, "")}
        for k, v in issue_runs.items() if len(v) >= 2
    }

    return {
        "runs_considered": recent_run_ids,
        "severity_counts_by_run": sev_counts,
        "recurring_issues": recurring,
    }


# ── LLM Synthesis ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a data quality triage assistant for a macroeconomic dashboard.

You will receive:
1. CURRENT findings from the automated checks just completed
2. PRIOR CONTEXT — summaries of up to 3 previous QA runs (score trends, recurring issues)
3. Up to 3 PRIOR REPORTS (full markdown) for narrative context

Your job is to:

1. Identify the top 3 most urgent CURRENT issues (CRITICAL → HIGH → MEDIUM)
2. Look for PATTERNS: is this a new issue or recurring? Is it getting worse/better across
   the 3 prior runs? Flag recurring issues that have appeared in ≥2 previous runs as
   higher priority — they indicate a persistent problem that one-shot fixes aren't resolving
3. Explain the LIKELY ROOT CAUSE in 1-2 sentences each
4. Suggest a CONCRETE NEXT ACTION the operator should take, prioritized

Be concise (<300 words total). Use markdown formatting. Do NOT just list the findings —
the report already does that. SYNTHESIZE with historical context.

If everything is healthy (no CRITICAL/HIGH) AND no recurring issues, say so in one sentence.
"""


def _llm_synthesize(findings: list[dict], score: dict,
                    prior_events: dict | None = None,
                    prior_reports: list[dict] | None = None) -> str:
    """Call Minimax via OpenAI Chat Completions to synthesize a triage summary.

    Includes prior-run context (event stats + full markdown reports)
    so the LLM can identify trends and recurring issues.
    """
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        return "*(LLM synthesis skipped — MINIMAX_API_KEY not set)*"

    try:
        from openai import OpenAI
    except ImportError:
        return "*(LLM synthesis skipped — `openai` package not installed)*"

    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.5")

    # --- Compact CURRENT findings ---
    current_json = json.dumps({
        "score": score,
        "findings": [
            {k: v for k, v in f.items() if k != "context"} for f in findings
        ],
    }, indent=2, default=str)
    if len(current_json) > 18000:
        current_json = current_json[:18000] + "\n[truncated]"

    # --- Compact PRIOR event stats ---
    prior_events = prior_events or {}
    prior_stats_json = json.dumps(prior_events, indent=2, default=str)
    if len(prior_stats_json) > 6000:
        prior_stats_json = prior_stats_json[:6000] + "\n[truncated]"

    # --- Compact PRIOR markdown reports ---
    prior_reports_blob = ""
    if prior_reports:
        parts = []
        for r in prior_reports:
            parts.append(f"### Prior run: {r['run_id']}\n{r['text']}")
        prior_reports_blob = "\n\n---\n\n".join(parts)
        # Hard cap on total context (keep under ~25k tokens)
        if len(prior_reports_blob) > 16000:
            prior_reports_blob = prior_reports_blob[-16000:]

    user_msg = (
        "## CURRENT findings (just completed)\n"
        f"```json\n{current_json}\n```\n\n"
        "## PRIOR RUN STATS (severity counts by run + recurring issues)\n"
        f"```json\n{prior_stats_json}\n```\n"
    )
    if prior_reports_blob:
        user_msg += "\n## PRIOR MARKDOWN REPORTS\n\n" + prior_reports_blob

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return resp.choices[0].message.content or "*(empty response)*"
    except Exception as e:
        return f"*(LLM synthesis failed: {e})*"


# ── Telegram alert (CRITICAL only) ───────────────────────────────────────

def _maybe_telegram_alert(findings: list[dict], score: dict, run_id: str):
    """Post a CRITICAL-only alert to Telegram if any CRITICAL findings exist."""
    crit = [f for f in findings if f["severity"] == "CRITICAL"]
    if not crit:
        return
    # Reuse the bot token from /root/Finl_Agent_CC/.env
    env_path = Path("/root/Finl_Agent_CC/.env")
    if not env_path.exists():
        return
    bot_token = chat_id = None
    for line in env_path.read_text().splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            bot_token = line.split("=", 1)[1].strip().strip("'\"")
        elif line.startswith("TELEGRAM_CHAT_ID=") or line.startswith("TELEGRAM_USER_ID="):
            chat_id = line.split("=", 1)[1].strip().strip("'\"")
    chat_id = chat_id or "1130846055"
    if not bot_token:
        return

    summary_lines = [f"🚨 *Data QA CRITICAL* — {datetime.now():%Y-%m-%d %H:%M GMT+8}",
                     f"Score: *{score['score']}/100*", ""]
    for f in crit[:5]:
        ind = f" / `{f['indicator']}`" if f.get("indicator") else ""
        summary_lines.append(f"• *{f['check_id']}{ind}*: {f['message']}")
        if f.get("suggested_fix"):
            summary_lines.append(f"  Fix: `{f['suggested_fix']}`")
    summary_lines.append(f"\nFull report: `/var/log/macro-data-qa/{run_id}.md`")

    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": "\n".join(summary_lines),
            "parse_mode": "Markdown",
        }).encode()
        urllib.request.urlopen(url, data, timeout=10).read()
    except Exception:
        pass  # silent fail — log file is the source of truth


# ── Main runner ──────────────────────────────────────────────────────────

def run_all_checks(weekly: bool = False, single_check: str | None = None) -> list[dict]:
    """Execute all QA checks and return findings."""
    findings: list[dict] = []

    checks = ALL_CHECKS
    if single_check:
        checks = [c for c in ALL_CHECKS if c[0] == single_check.upper()]
        if not checks:
            print(f"Unknown check: {single_check}")
            sys.exit(2)

    for cid, fn, desc in checks:
        print(f"  Running {cid}: {desc}...", flush=True)
        try:
            results = fn()
            if isinstance(results, list):
                findings.extend(results)
            else:
                findings.append({
                    "severity": "MEDIUM", "check_id": cid,
                    "category": "bad_return",
                    "message": f"{cid} returned non-list: {type(results).__name__}",
                })
        except Exception as e:
            tb = traceback.format_exc(limit=3)
            findings.append({
                "severity": "MEDIUM", "check_id": cid,
                "category": "tool_crash",
                "message": f"{cid} crashed: {e}",
                "context": {"traceback": tb},
            })

    # Weekly checks
    if weekly and not single_check:
        print("  Running C10 (weekly): equity financials drift...", flush=True)
        try:
            findings.extend(check_equity_financials_drift())
        except Exception as e:
            findings.append({
                "severity": "LOW", "check_id": "C10",
                "category": "tool_crash",
                "message": f"C10 crashed: {e}",
            })

    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Data QA Agent for macro_2 dashboard")
    parser.add_argument("--check", help="Run only one check (e.g. C3)")
    parser.add_argument("--weekly", action="store_true",
                        help="Include C10 weekly equity drift check")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip Minimax LLM synthesis")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Skip Telegram alert for CRITICAL")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-check progress output")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y-%m-%d-%H%M")
    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M:%S}] Starting QA run {run_id}", flush=True)

    findings = run_all_checks(weekly=args.weekly, single_check=args.check)
    score = compute_data_quality_score(findings)

    print(f"  Score: {score['score']}/100  |  "
          f"CRITICAL={score['counts']['CRITICAL']} "
          f"HIGH={score['counts']['HIGH']} "
          f"MEDIUM={score['counts']['MEDIUM']} "
          f"LOW={score['counts']['LOW']}", flush=True)

    # Gather context from the prior N runs (recurring-issue detection)
    prior_events = _load_prior_event_stats(exclude_run_id=run_id)
    prior_reports = _load_prior_markdown_reports(
        n=HISTORY_RUNS, exclude_run_id=run_id,
    )
    if prior_reports:
        print(f"  Loaded {len(prior_reports)} prior report(s) for context: "
              f"{[r['run_id'] for r in prior_reports]}", flush=True)
    if prior_events.get("recurring_issues"):
        recurring_count = len(prior_events["recurring_issues"])
        print(f"  {recurring_count} recurring issue(s) detected across prior runs",
              flush=True)

    # LLM synthesis (with historical context)
    summary = ""
    if not args.no_llm:
        print("  Calling Minimax LLM for triage synthesis...", flush=True)
        summary = _llm_synthesize(findings, score,
                                  prior_events=prior_events,
                                  prior_reports=prior_reports)

    # Write outputs
    write_jsonl_log(findings, score, run_id)
    md_path = write_markdown_report(findings, score, run_id, summary)
    print(f"  Wrote report: {md_path}", flush=True)

    # CRITICAL → Telegram
    if not args.no_telegram:
        _maybe_telegram_alert(findings, score, run_id)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Done in {elapsed:.1f}s", flush=True)

    # Exit code: 2 if CRITICAL, 1 if HIGH, 0 otherwise (useful for scripting)
    if score["counts"]["CRITICAL"] > 0:
        sys.exit(2)
    if score["counts"]["HIGH"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
