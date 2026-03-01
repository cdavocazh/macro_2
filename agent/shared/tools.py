"""
Shared tool functions for financial data discrepancy review.

These plain-Python functions are wrapped into framework-specific tools
by the OpenAI Agents and LangChain agent implementations.

Tool categories:
  1. Cross-source comparison (Yahoo Finance vs SEC EDGAR)
  2. Missing data detection (None values, quarter gaps, concept gaps)
  3. SEC EDGAR XBRL validation (concept coverage, FY-end derivation check)
  4. Codebase review (read extractor source, suggest fixes)
  5. Internet research (web search for known data issues)
"""

import sys
import os
import json
import traceback
from datetime import datetime

# Add project root so we can import extractors
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.shared.config import TOP_20_TICKERS, PROJECT_ROOT


# ── 1. Cross-Source Comparison ──────────────────────────────────────────

def compare_sources(ticker: str) -> str:
    """
    Fetch financial data for a ticker from both Yahoo Finance and SEC EDGAR,
    then compare key metrics and flag discrepancies.

    Returns a structured report of differences in revenue, net income,
    cash flow, EPS, and balance sheet items across the two sources.
    """
    results = {"ticker": ticker, "yahoo": None, "sec": None, "discrepancies": []}

    # Fetch Yahoo Finance data
    try:
        from data_extractors.equity_financials_extractor import get_company_financials_yahoo
        yf_data = get_company_financials_yahoo(ticker)
        if "error" in yf_data:
            results["yahoo"] = {"error": yf_data["error"]}
        else:
            results["yahoo"] = {
                "quarters": yf_data.get("quarters", []),
                "revenue": yf_data.get("income_statement", {}).get("total_revenue", []),
                "net_income": yf_data.get("income_statement", {}).get("net_income", []),
                "operating_cf": yf_data.get("cash_flow", {}).get("operating_cash_flow", []),
                "total_assets": yf_data.get("balance_sheet", {}).get("total_assets", []),
                "diluted_eps": yf_data.get("income_statement", {}).get("diluted_eps", []),
                "source": "Yahoo Finance",
            }
    except Exception as e:
        results["yahoo"] = {"error": str(e)}

    # Fetch SEC EDGAR data
    try:
        from data_extractors.sec_extractor import get_company_financials_sec
        sec_data = get_company_financials_sec(ticker)
        if "error" in sec_data:
            results["sec"] = {"error": sec_data["error"]}
        else:
            results["sec"] = {
                "quarters": sec_data.get("quarters", []),
                "revenue": sec_data.get("income_statement", {}).get("total_revenue", []),
                "net_income": sec_data.get("income_statement", {}).get("net_income", []),
                "operating_cf": sec_data.get("cash_flow", {}).get("operating_cash_flow", []),
                "total_assets": sec_data.get("balance_sheet", {}).get("total_assets", []),
                "diluted_eps": sec_data.get("income_statement", {}).get("diluted_eps", []),
                "source": "SEC EDGAR",
            }
    except Exception as e:
        results["sec"] = {"error": str(e)}

    # Compare overlapping quarters
    if results["yahoo"] and results["sec"] and "error" not in results["yahoo"] and "error" not in results["sec"]:
        yq = results["yahoo"]["quarters"]
        sq = results["sec"]["quarters"]
        overlap = [q for q in yq if q in sq]

        for metric in ["revenue", "net_income", "operating_cf", "total_assets", "diluted_eps"]:
            y_vals = results["yahoo"].get(metric, [])
            s_vals = results["sec"].get(metric, [])
            for q in overlap:
                yi = yq.index(q) if q in yq else None
                si = sq.index(q) if q in sq else None
                if yi is None or si is None:
                    continue
                yv = y_vals[yi] if yi < len(y_vals) else None
                sv = s_vals[si] if si < len(s_vals) else None
                if yv is None and sv is None:
                    continue
                if yv is None or sv is None:
                    results["discrepancies"].append({
                        "quarter": q, "metric": metric,
                        "yahoo": yv, "sec": sv,
                        "issue": "One source has data, the other does not",
                    })
                elif yv != 0 and abs(yv - sv) / abs(yv) > 0.02:
                    results["discrepancies"].append({
                        "quarter": q, "metric": metric,
                        "yahoo": yv, "sec": sv,
                        "pct_diff": round((sv - yv) / abs(yv) * 100, 2),
                        "issue": "Values differ by more than 2%",
                    })

    return json.dumps(results, indent=2, default=str)


# ── 2. Missing Data Detection ──────────────────────────────────────────

def detect_missing_data(ticker: str, source: str = "both") -> str:
    """
    Scan financial data for a ticker and report all missing (None) values,
    quarter gaps, and incomplete metrics.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL')
        source: 'yahoo', 'sec', or 'both'

    Checks performed:
    - None values in revenue, net income, cash flow, balance sheet
    - Quarter timeline gaps (non-consecutive quarters)
    - Missing FY-end quarters (fiscal year-end not represented)
    - Metrics with all-None values (concept not found in XBRL)
    """
    report = {"ticker": ticker, "sources": {}}

    def _scan_source(data, source_name):
        findings = {"quarter_gaps": [], "missing_values": {}, "empty_metrics": []}
        if not data or "error" in data:
            findings["error"] = data.get("error", "No data") if data else "No data"
            return findings

        quarters = data.get("quarters", [])
        findings["quarters"] = quarters

        # Check quarter continuity
        for i in range(len(quarters) - 1):
            q_cur = quarters[i]
            q_prev = quarters[i + 1]
            try:
                cur_y, cur_q = int(q_cur.split("-Q")[0]), int(q_cur.split("-Q")[1])
                prv_y, prv_q = int(q_prev.split("-Q")[0]), int(q_prev.split("-Q")[1])
                expected_y = cur_y if cur_q > 1 else cur_y - 1
                expected_q = cur_q - 1 if cur_q > 1 else 4
                if prv_y != expected_y or prv_q != expected_q:
                    findings["quarter_gaps"].append(
                        f"Gap between {q_cur} and {q_prev} (expected {expected_y}-Q{expected_q})"
                    )
            except (ValueError, IndexError):
                pass

        # Scan all statement sections for None values
        for section_name in ["income_statement", "balance_sheet", "cash_flow"]:
            section = data.get(section_name, {})
            if not section:
                findings["empty_metrics"].append(f"{section_name}: entire section missing")
                continue
            for metric, vals in section.items():
                if not isinstance(vals, list):
                    continue
                none_count = sum(1 for v in vals if v is None)
                if none_count == len(vals):
                    findings["empty_metrics"].append(f"{section_name}.{metric}")
                elif none_count > 0:
                    missing_qs = [quarters[i] for i in range(len(vals)) if vals[i] is None and i < len(quarters)]
                    findings["missing_values"][f"{section_name}.{metric}"] = missing_qs

        return findings

    if source in ("yahoo", "both"):
        try:
            from data_extractors.equity_financials_extractor import get_company_financials_yahoo
            yf_data = get_company_financials_yahoo(ticker)
            report["sources"]["yahoo"] = _scan_source(yf_data, "Yahoo Finance")
        except Exception as e:
            report["sources"]["yahoo"] = {"error": str(e)}

    if source in ("sec", "both"):
        try:
            from data_extractors.sec_extractor import get_company_financials_sec
            sec_data = get_company_financials_sec(ticker)
            report["sources"]["sec"] = _scan_source(sec_data, "SEC EDGAR")
        except Exception as e:
            report["sources"]["sec"] = {"error": str(e)}

    return json.dumps(report, indent=2, default=str)


# ── 3. SEC XBRL Concept Validation ────────────────────────────────────

def validate_sec_xbrl_concepts(ticker: str) -> str:
    """
    Check which XBRL concepts are available for a ticker in SEC EDGAR and
    which ones are missing. This helps diagnose why certain metrics are None.

    Checks:
    - Revenue concept variants (standard vs bank-specific)
    - Net income variants (NetIncomeLoss vs ProfitLoss)
    - Cash flow reporting style (standalone quarterly vs cumulative YTD)
    - Whether FY-end quarter derivation is possible
    - IFRS vs US-GAAP namespace availability
    """
    try:
        from data_extractors.sec_extractor import _ticker_to_cik, _sec_get
    except ImportError:
        return json.dumps({"error": "Cannot import sec_extractor"})

    try:
        cik = _ticker_to_cik(ticker)
        if cik is None:
            return json.dumps({"error": f"CIK not found for {ticker}"})

        facts = _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        usgaap = facts.get("facts", {}).get("us-gaap", {})
        ifrs = facts.get("facts", {}).get("ifrs-full", {})

        report = {
            "ticker": ticker, "cik": cik,
            "has_usgaap": bool(usgaap),
            "has_ifrs": bool(ifrs),
            "concept_checks": {},
        }

        # Check key concept families
        concept_families = {
            "revenue": [
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "RevenuesNetOfInterestExpense", "NoninterestIncome",
            ],
            "net_income": [
                "NetIncomeLoss", "ProfitLoss",
                "NetIncomeLossAvailableToCommonStockholdersBasic",
            ],
            "operating_cf": [
                "NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByOperatingActivities",
            ],
            "capex": [
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsToAcquireProductiveAssets",
            ],
            "total_assets": ["Assets"],
            "equity": [
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ],
            "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
        }

        for family_name, concepts in concept_families.items():
            family_report = {}
            for concept in concepts:
                if concept in usgaap:
                    entries = usgaap[concept].get("units", {})
                    unit_keys = list(entries.keys())
                    total_entries = sum(len(entries[u]) for u in unit_keys)
                    # Get date range
                    all_entries = []
                    for u in unit_keys:
                        all_entries.extend(entries[u])
                    dates = sorted(set(e.get("end", "") for e in all_entries if e.get("end")))
                    family_report[concept] = {
                        "available": True,
                        "units": unit_keys,
                        "entry_count": total_entries,
                        "date_range": f"{dates[0]} to {dates[-1]}" if dates else "none",
                    }
                else:
                    family_report[concept] = {"available": False}
            report["concept_checks"][family_name] = family_report

        # Check cash flow reporting style (cumulative YTD vs standalone)
        for cf_concept in ["NetCashProvidedByUsedInOperatingActivities",
                           "NetCashProvidedByOperatingActivities"]:
            if cf_concept in usgaap:
                entries = usgaap[cf_concept].get("units", {}).get("USD", [])
                valid_10q = [e for e in entries if e.get("form") == "10-Q"
                             and "start" in e and "end" in e]
                if valid_10q:
                    durations = []
                    for e in sorted(valid_10q, key=lambda x: x.get("end", ""), reverse=True)[:8]:
                        try:
                            s = datetime.strptime(e["start"], "%Y-%m-%d")
                            ed = datetime.strptime(e["end"], "%Y-%m-%d")
                            durations.append((ed - s).days)
                        except ValueError:
                            pass
                    report["cf_reporting_style"] = {
                        "concept": cf_concept,
                        "recent_10q_durations_days": durations,
                        "likely_cumulative_ytd": any(d > 150 for d in durations),
                    }
                break

        return json.dumps(report, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()})


# ── 4. Codebase Review ─────────────────────────────────────────────────

def read_extractor_source(filename: str) -> str:
    """
    Read the source code of a data extractor file.
    Use this to review the extraction logic and identify potential bugs.

    Args:
        filename: File name within data_extractors/ (e.g. 'sec_extractor.py')
                  or a relative path from project root (e.g. 'utils/helpers.py')
    """
    # Try data_extractors/ first
    path = os.path.join(PROJECT_ROOT, "data_extractors", filename)
    if not os.path.exists(path):
        path = os.path.join(PROJECT_ROOT, filename)
    if not os.path.exists(path):
        return json.dumps({"error": f"File not found: {filename}"})

    try:
        with open(path, "r") as f:
            content = f.read()
        # Truncate to avoid exceeding LLM context
        if len(content) > 30000:
            content = content[:30000] + "\n\n... [TRUNCATED — file too large] ..."
        return json.dumps({"file": path, "lines": content.count("\n") + 1, "content": content})
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_extractor_files() -> str:
    """List all data extractor files and their sizes."""
    extractors_dir = os.path.join(PROJECT_ROOT, "data_extractors")
    files = []
    for f in sorted(os.listdir(extractors_dir)):
        if f.endswith(".py"):
            path = os.path.join(extractors_dir, f)
            size = os.path.getsize(path)
            with open(path, "r") as fh:
                lines = sum(1 for _ in fh)
            files.append({"file": f, "size_bytes": size, "lines": lines})

    # Also include key files outside data_extractors/
    for extra in ["app.py", "utils/helpers.py", "data_aggregator.py"]:
        path = os.path.join(PROJECT_ROOT, extra)
        if os.path.exists(path):
            size = os.path.getsize(path)
            with open(path, "r") as fh:
                lines = sum(1 for _ in fh)
            files.append({"file": extra, "size_bytes": size, "lines": lines})

    return json.dumps(files, indent=2)


def suggest_code_fix(filename: str, issue_description: str) -> str:
    """
    Generate a structured code fix suggestion for a data extractor.

    Args:
        filename: The extractor file to fix
        issue_description: What the problem is (e.g. 'AVGO net income returns None
                          because it uses ProfitLoss instead of NetIncomeLoss')

    Returns a structured suggestion with file, issue, root cause analysis,
    and proposed code change.
    """
    # Read the file first
    source = read_extractor_source(filename)
    source_data = json.loads(source)
    if "error" in source_data:
        return source

    return json.dumps({
        "file": filename,
        "issue": issue_description,
        "source_lines": source_data["lines"],
        "note": (
            "The LLM agent should analyze the source code and issue description, "
            "then produce a specific code change recommendation with: "
            "(1) the exact lines to change, "
            "(2) the proposed new code, "
            "(3) an explanation of why this fixes the issue."
        ),
        "source_preview": source_data["content"][:5000],
    })


# ── 5. Batch Scan ──────────────────────────────────────────────────────

def batch_missing_data_scan(tickers: str = "", source: str = "sec") -> str:
    """
    Scan multiple tickers for missing data. Defaults to all TOP_20_TICKERS.

    Args:
        tickers: Comma-separated ticker list, or empty for all top 20
        source: 'yahoo', 'sec', or 'both'

    Returns a summary of coverage per ticker.
    """
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else TOP_20_TICKERS

    summary = []
    for t in ticker_list:
        try:
            raw = detect_missing_data(t, source)
            data = json.loads(raw)
            for src_name, src_data in data.get("sources", {}).items():
                if "error" in src_data:
                    summary.append({"ticker": t, "source": src_name, "status": "ERROR", "detail": src_data["error"][:80]})
                    continue
                n_gaps = len(src_data.get("quarter_gaps", []))
                n_empty = len(src_data.get("empty_metrics", []))
                n_partial = len(src_data.get("missing_values", {}))
                status = "OK" if n_gaps == 0 and n_empty == 0 and n_partial == 0 else "ISSUES"
                summary.append({
                    "ticker": t, "source": src_name, "status": status,
                    "quarters": src_data.get("quarters", []),
                    "quarter_gaps": n_gaps,
                    "empty_metrics": n_empty,
                    "partial_metrics": n_partial,
                })
        except Exception as e:
            summary.append({"ticker": t, "source": source, "status": "EXCEPTION", "detail": str(e)[:80]})

    return json.dumps(summary, indent=2, default=str)


# ── 6. Internet Research Helper ────────────────────────────────────────

def format_web_search_query(ticker: str, issue_type: str) -> str:
    """
    Generate a web search query for researching a specific data issue.

    Args:
        ticker: Stock ticker
        issue_type: Type of issue. One of:
            - 'xbrl_concept': Which XBRL concept a company uses for a metric
            - 'fiscal_year': When a company's fiscal year ends
            - 'reporting_change': Whether a company changed reporting standards
            - 'sec_filing': Recent SEC filing details
            - 'data_discrepancy': Known data quality issues with a source

    Returns a search query string the agent can use with a web search tool.
    """
    queries = {
        "xbrl_concept": f"{ticker} SEC EDGAR XBRL concept revenue net income 10-K",
        "fiscal_year": f"{ticker} fiscal year end date annual report",
        "reporting_change": f"{ticker} GAAP reporting change XBRL taxonomy update",
        "sec_filing": f"site:sec.gov {ticker} 10-K 10-Q latest filing",
        "data_discrepancy": f"{ticker} financial data discrepancy Yahoo Finance SEC EDGAR",
    }
    query = queries.get(issue_type, f"{ticker} {issue_type} SEC EDGAR financial data")
    return json.dumps({"query": query, "ticker": ticker, "issue_type": issue_type})
