"""
SEC EDGAR Direct Data Extraction — Financial data from 10-K and 10-Q filings.

Uses the free SEC EDGAR XBRL API (data.sec.gov):
- No API key required
- Rate limit: 10 requests/second
- Requires User-Agent header with contact info

Data flow:
1. company_tickers.json → CIK lookup (cached locally)
2. /api/xbrl/companyfacts/CIK{cik}.json → all financial facts
3. Parse quarterly values from XBRL entries (filter by ~90-day periods)

Limitations:
- Valuation ratios (P/E, P/B, etc.) require market price — not in SEC filings
- Revenue segment breakdowns require parsing individual filing XBRL (not in companyfacts)
- Foreign issuers (e.g. TSM) may file 20-F/6-K instead of 10-K/10-Q
"""

import requests
import json
import os
import re
from datetime import datetime, timedelta
import time
import traceback


SEC_USER_AGENT = 'MacroDashboard/1.0 contact@example.com'
SEC_HEADERS = {'User-Agent': SEC_USER_AGENT, 'Accept': 'application/json'}
CIK_CACHE_DIR = 'data_cache'
CIK_CACHE_FILE = os.path.join(CIK_CACHE_DIR, 'sec_cik_mapping.json')

# Rate limiting (10 req/sec max, we use ~7/sec to be safe)
_last_request_time = 0
_MIN_REQUEST_INTERVAL = 0.15

# Valid SEC filing forms for financial data
_VALID_FORMS = ('10-K', '10-Q', '20-F', '6-K')


def _rate_limit():
    """Enforce SEC rate limit."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _sec_get(url):
    """GET request to SEC EDGAR with proper headers and rate limiting."""
    _rate_limit()
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── CIK Mapping ────────────────────────────────────────────────────

_cik_mapping_cache = None


def _load_cik_mapping():
    """Load or download ticker-to-CIK mapping (cached in memory and on disk)."""
    global _cik_mapping_cache
    if _cik_mapping_cache is not None:
        return _cik_mapping_cache

    # Check disk cache (7-day TTL)
    if os.path.exists(CIK_CACHE_FILE):
        age_hours = (time.time() - os.path.getmtime(CIK_CACHE_FILE)) / 3600
        if age_hours < 168:
            with open(CIK_CACHE_FILE, 'r') as f:
                _cik_mapping_cache = json.load(f)
                return _cik_mapping_cache

    # Download from SEC
    print("    Downloading SEC CIK mapping...")
    data = _sec_get('https://www.sec.gov/files/company_tickers.json')

    mapping = {}
    for entry in data.values():
        ticker = entry.get('ticker', '').upper()
        cik = str(entry.get('cik_str', ''))
        if ticker and cik:
            mapping[ticker] = cik

    os.makedirs(CIK_CACHE_DIR, exist_ok=True)
    with open(CIK_CACHE_FILE, 'w') as f:
        json.dump(mapping, f)

    _cik_mapping_cache = mapping
    return mapping


def _ticker_to_cik(ticker_symbol):
    """Convert ticker to zero-padded CIK string. Tries common variations."""
    mapping = _load_cik_mapping()
    t = ticker_symbol.upper()

    # Try exact match first
    cik = mapping.get(t)
    if cik:
        return cik.zfill(10)

    # Try common variations: BRK-B → BRK/B, GOOGL → GOOG
    for variant in [t.replace('-', '/'), t.replace('-', '.'), t.replace('-', ''), t[:4], t[:3]]:
        cik = mapping.get(variant)
        if cik:
            return cik.zfill(10)

    return None


# ── XBRL Data Extraction Helpers ───────────────────────────────────

def _safe_round(val, decimals=2):
    if val is None:
        return None
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return None


def _safe_divide(n, d, decimals=4):
    if n is None or d is None:
        return None
    try:
        nf, df = float(n), float(d)
        if df == 0:
            return None
        return round(nf / df, decimals)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def _get_values_at_dates(usgaap, concept_names, end_dates, value_type='duration', unit='USD'):
    """
    Extract values for a concept aligned to specific end dates.

    Tries each concept name and merges results: the first non-None value for each
    date wins. This handles companies that changed concept names mid-year (e.g.,
    GOOGL switched revenue concepts in 2025).

    Args:
        usgaap: the 'us-gaap' dict from companyfacts
        concept_names: list of XBRL concept name alternatives
        end_dates: list of end-date strings to align values to
        value_type: 'duration' (income/cashflow) or 'instant' (balance sheet)
        unit: 'USD', 'USD/shares', or 'shares'

    Returns: list of values aligned to end_dates (None if not found)
    """
    if isinstance(concept_names, str):
        concept_names = [concept_names]

    merged = [None] * len(end_dates)

    for concept in concept_names:
        if concept not in usgaap:
            continue

        # All slots filled, stop early
        if all(v is not None for v in merged):
            break

        units_data = usgaap[concept].get('units', {})
        all_entries = units_data.get(unit, [])
        if not all_entries:
            continue

        # Filter by form
        filtered = [e for e in all_entries if e.get('form') in _VALID_FORMS]
        if not filtered:
            continue

        if value_type == 'duration':
            quarterly = []
            for e in filtered:
                if 'start' not in e or 'end' not in e:
                    continue
                try:
                    start = datetime.strptime(e['start'], '%Y-%m-%d')
                    end = datetime.strptime(e['end'], '%Y-%m-%d')
                    days = (end - start).days
                    if 80 <= days <= 100:
                        quarterly.append(e)
                except (ValueError, KeyError):
                    continue
            filtered = quarterly

        # Build end_date -> value map (prefer most recently filed)
        date_val = {}
        for e in sorted(filtered, key=lambda x: x.get('filed', ''), reverse=True):
            ed = e.get('end', '')
            if ed not in date_val and e.get('val') is not None:
                date_val[ed] = float(e['val'])

        if not date_val:
            continue

        available_dates = sorted(date_val.keys(), reverse=True)

        for i, target in enumerate(end_dates):
            if merged[i] is not None:
                continue  # already filled by a prior concept

            # Exact match
            if target in date_val:
                merged[i] = date_val[target]
                continue

            # Fuzzy match: ±7 days
            try:
                target_dt = datetime.strptime(target, '%Y-%m-%d')
                best_val = None
                best_diff = 8
                for avail in available_dates:
                    avail_dt = datetime.strptime(avail, '%Y-%m-%d')
                    diff = abs((target_dt - avail_dt).days)
                    if diff < best_diff:
                        best_diff = diff
                        best_val = date_val[avail]
                if best_val is not None:
                    merged[i] = best_val
            except ValueError:
                pass

    return merged


def _get_cashflow_quarterly_values(usgaap, concept_names, end_dates, unit='USD'):
    """
    Extract quarterly cash flow values, handling cumulative YTD reporting.

    Many companies (e.g. NVDA) report cumulative year-to-date cash flows in 10-Qs:
    - Q1 10-Q: standalone Q1 (~90 days)
    - Q2 10-Q: cumulative Q1+Q2 (~181 days)
    - Q3 10-Q: cumulative Q1+Q2+Q3 (~272 days)
    - 10-K: full year (~363 days)

    This function first tries the standard quarterly filter (80-100 days).
    If that yields mostly None, it derives standalone quarterly values by
    subtracting consecutive cumulative values.
    """
    if isinstance(concept_names, str):
        concept_names = [concept_names]

    # First try standard quarterly extraction
    standard = _get_values_at_dates(usgaap, concept_names, end_dates, 'duration', unit)
    non_none = sum(1 for v in standard if v is not None)
    if non_none >= len(end_dates) // 2 + 1:
        return standard  # Enough data from standard approach

    # Try cumulative YTD approach across all concepts, keep best result
    best_result = standard
    best_count = non_none

    for concept in concept_names:
        if concept not in usgaap:
            continue

        units_data = usgaap[concept].get('units', {})
        all_entries = units_data.get(unit, [])
        if not all_entries:
            continue

        filtered = [e for e in all_entries if e.get('form') in _VALID_FORMS
                     and 'start' in e and 'end' in e and e.get('val') is not None]
        if not filtered:
            continue

        # Build map: (start_date, end_date) -> value, keeping most recently filed
        period_map = {}
        for e in sorted(filtered, key=lambda x: x.get('filed', ''), reverse=True):
            key = (e['start'], e['end'])
            if key not in period_map:
                period_map[key] = float(e['val'])

        # Group by fiscal year start date
        fy_starts = {}
        for (start, end), val in period_map.items():
            if start not in fy_starts:
                fy_starts[start] = []
            fy_starts[start].append((end, val))
        for s in fy_starts:
            fy_starts[s].sort(key=lambda x: x[0])  # sort by end date

        # For each target end_date, find matching cumulative entry and derive quarterly
        result = []
        for target in end_dates:
            found = False
            try:
                target_dt = datetime.strptime(target, '%Y-%m-%d')
            except ValueError:
                result.append(None)
                continue

            for fy_start, cumulative_entries in fy_starts.items():
                for idx, (end_date, cum_val) in enumerate(cumulative_entries):
                    try:
                        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    except ValueError:
                        continue

                    if abs((target_dt - end_dt).days) <= 7:
                        if idx == 0:
                            result.append(cum_val)
                        else:
                            prev_cum = cumulative_entries[idx - 1][1]
                            result.append(round(cum_val - prev_cum, 2))
                        found = True
                        break
                if found:
                    break

            if not found:
                result.append(None)

        this_count = sum(1 for v in result if v is not None)
        if this_count > best_count:
            best_count = this_count
            best_result = result

    return best_result


def _derive_fy_end_values(usgaap, concept_names, end_dates, extracted_values, unit='USD'):
    """
    Fill in None values for fiscal year-end quarters by deriving: Annual - (Q1 + Q2 + Q3).

    The 10-K annual filing reports the full-year total for duration metrics but not
    the standalone Q4 (fiscal year-end quarter). This function derives Q4 by
    finding the annual entry and subtracting the 3 quarterly values.

    Searches across ALL concept alternatives for both the annual value and the
    3 quarterly values, handling companies that switched concepts mid-year
    (e.g., GOOGL changed revenue concepts in 2025).

    Only applies to duration metrics (income statement, cash flow). Balance sheet
    (instant) values are already available from the 10-K filing directly.

    Args:
        usgaap: the 'us-gaap' dict from companyfacts
        concept_names: list of XBRL concept name alternatives
        end_dates: list of end-date strings to align values to
        extracted_values: already-extracted values (with None gaps for FY-end quarters)
        unit: 'USD', 'USD/shares', or 'shares'

    Returns: list of values with FY-end gaps filled in where possible
    """
    if isinstance(concept_names, str):
        concept_names = [concept_names]

    result = list(extracted_values)

    # Collect all valid entries across ALL concept alternatives
    all_valid = []
    for concept in concept_names:
        if concept not in usgaap:
            continue
        entries = usgaap[concept].get('units', {}).get(unit, [])
        for e in entries:
            if (e.get('form') in _VALID_FORMS
                    and 'start' in e and 'end' in e and e.get('val') is not None):
                all_valid.append(e)

    if not all_valid:
        return result

    # Sort by filed date descending (prefer most recently filed)
    all_valid.sort(key=lambda x: x.get('filed', ''), reverse=True)

    for i, val in enumerate(result):
        if val is not None:
            continue  # already has data

        target = end_dates[i]
        try:
            target_dt = datetime.strptime(target, '%Y-%m-%d')
        except ValueError:
            continue

        # Find the annual entry ending at this target date (±7 days)
        annual_val = None
        annual_start = None
        annual_end_dt = None
        for e in all_valid:
            try:
                start = datetime.strptime(e['start'], '%Y-%m-%d')
                end = datetime.strptime(e['end'], '%Y-%m-%d')
                days = (end - start).days
                if 340 <= days <= 380 and abs((end - target_dt).days) <= 7:
                    annual_val = float(e['val'])
                    annual_start = start
                    annual_end_dt = end
                    break
            except ValueError:
                continue

        if annual_val is None or annual_start is None:
            continue

        # Find the 3 quarterly entries within this fiscal year from ALL concepts
        # Deduplicate by end_date, keeping most recently filed (already sorted)
        quarterly_vals = {}
        for e in all_valid:
            try:
                start = datetime.strptime(e['start'], '%Y-%m-%d')
                end = datetime.strptime(e['end'], '%Y-%m-%d')
                days = (end - start).days
                end_str = e['end']
                if 80 <= days <= 100 and end_str not in quarterly_vals:
                    # Quarter must start at/after FY start and end before FY end
                    if (start >= annual_start - timedelta(days=7)
                            and end < annual_end_dt - timedelta(days=30)):
                        quarterly_vals[end_str] = float(e['val'])
            except ValueError:
                continue

        if len(quarterly_vals) == 3:
            q_sum = sum(quarterly_vals.values())
            result[i] = round(annual_val - q_sum, 2)

    return result


def _get_recent_quarters(usgaap, n_quarters=5):
    """
    Determine the most recent N quarterly end dates from revenue data.
    Returns list of end-date strings, most recent first.

    Merges dates from all revenue concepts to handle companies that changed
    concept names mid-year (e.g., GOOGL, NVDA). Also includes bank-specific
    revenue concepts (RevenuesNetOfInterestExpense, NoninterestIncome).

    Also includes fiscal year-end dates from annual filings (10-K). These dates
    don't have standalone quarterly entries (only the full-year total), so
    duration metrics must be derived via: Annual - (Q1 + Q2 + Q3).
    """
    quarterly_dates = set()
    annual_dates = set()

    _REVENUE_CONCEPTS = [
        'RevenueFromContractWithCustomerExcludingAssessedTax',
        'Revenues', 'SalesRevenueNet',
        'RevenueFromContractWithCustomerIncludingAssessedTax',
        'RevenuesNetOfInterestExpense',
        'NoninterestIncome',
    ]

    for concept in _REVENUE_CONCEPTS:
        if concept not in usgaap:
            continue

        entries = usgaap[concept].get('units', {}).get('USD', [])
        filtered = [e for e in entries if e.get('form') in _VALID_FORMS]

        for e in filtered:
            if 'start' not in e or 'end' not in e:
                continue
            try:
                start = datetime.strptime(e['start'], '%Y-%m-%d')
                end = datetime.strptime(e['end'], '%Y-%m-%d')
                days = (end - start).days
                if 80 <= days <= 100:
                    quarterly_dates.add(e['end'])
                elif 340 <= days <= 380:
                    annual_dates.add(e['end'])
            except (ValueError, KeyError):
                continue

    # Include FY-end dates that don't already have quarterly entries
    all_dates = quarterly_dates.copy()
    for ad in annual_dates:
        # Only add if no quarterly entry exists within ±7 days
        ad_dt = datetime.strptime(ad, '%Y-%m-%d')
        has_quarterly = any(
            abs((ad_dt - datetime.strptime(qd, '%Y-%m-%d')).days) <= 7
            for qd in quarterly_dates
        )
        if not has_quarterly:
            all_dates.add(ad)

    if not all_dates:
        return []

    return sorted(all_dates, reverse=True)[:n_quarters]


def _end_date_to_quarter(end_str):
    """Convert end date string to quarter label like '2025-Q4'."""
    try:
        dt = datetime.strptime(end_str, '%Y-%m-%d')
        return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
    except ValueError:
        return end_str


# ── Yahoo Finance Supplement ──────────────────────────────────────

def _supplement_with_yahoo(result):
    """
    Supplement SEC EDGAR data with Yahoo Finance metadata and price data.
    Adds: market_cap, sector, industry, price, and computes valuation ratios.
    """
    ticker = result.get('ticker')
    if not ticker:
        return result

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}

        # Metadata
        result['sector'] = info.get('sector', 'N/A')
        result['industry'] = info.get('industry', 'N/A')
        result['market_cap'] = info.get('marketCap')

        # Price data
        price = info.get('currentPrice') or info.get('regularMarketPrice')

        val = result.get('valuation', {})
        val['price'] = price
        val['market_cap'] = info.get('marketCap')
        val['forward_pe'] = info.get('forwardPE')
        val['fifty_two_week_high'] = info.get('fiftyTwoWeekHigh')
        val['fifty_two_week_low'] = info.get('fiftyTwoWeekLow')
        val['beta'] = info.get('beta')
        val['dividend_yield'] = info.get('dividendYield')

        # Store current price for dashboard component display
        val['current_price'] = price
        val['forward_eps'] = info.get('forwardEps')

        # Trailing P/E from SEC TTM EPS + Yahoo price
        eps_ttm = val.get('diluted_eps_ttm')
        if price and eps_ttm and eps_ttm > 0:
            val['trailing_pe'] = _safe_round(price / eps_ttm, 2)

        # P/B from Yahoo price + SEC book value per share
        bvps = val.get('book_value_per_share')
        if price and bvps and bvps > 0:
            val['price_to_book'] = _safe_round(price / bvps, 2)

        # P/S = Market Cap / TTM Revenue
        inc = result.get('income_statement', {})
        rev = inc.get('total_revenue', [])
        rev_recent = [r for r in rev[:4] if r is not None]
        mc = info.get('marketCap')
        ttm_rev = sum(rev_recent) if len(rev_recent) == 4 else None
        if ttm_rev and mc and ttm_rev > 0:
            val['price_to_sales'] = _safe_round(mc / ttm_rev, 2)
        val['ttm_revenue'] = ttm_rev  # store for dashboard

        # EV = Market Cap + Total Debt - Cash
        bs = result.get('balance_sheet', {})
        td_list = bs.get('total_debt', [])
        cash_list = bs.get('cash_and_equivalents', [])
        td0 = td_list[0] if td_list and td_list[0] is not None else 0
        cash0 = cash_list[0] if cash_list and cash_list[0] is not None else 0
        if mc:
            ev = mc + td0 - cash0
            val['enterprise_value'] = ev

            # EV/EBITDA
            ebitda = inc.get('ebitda', [])
            ebitda_recent = [e for e in ebitda[:4] if e is not None]
            ttm_ebitda = sum(ebitda_recent) if len(ebitda_recent) == 4 else None
            if ttm_ebitda and ttm_ebitda > 0:
                val['ev_to_ebitda'] = _safe_round(ev / ttm_ebitda, 2)
            val['ttm_ebitda'] = ttm_ebitda  # store for dashboard

            # EV/Revenue
            if ttm_rev and ttm_rev > 0:
                val['ev_to_revenue'] = _safe_round(ev / ttm_rev, 2)

            # EV/FCF
            cf = result.get('cash_flow', {})
            fcf = cf.get('free_cash_flow', [])
            fcf_recent = [f for f in fcf[:4] if f is not None]
            ttm_fcf = sum(fcf_recent) if len(fcf_recent) == 4 else None
            if ttm_fcf and ttm_fcf > 0:
                val['ev_to_fcf'] = _safe_round(ev / ttm_fcf, 2)
            val['ttm_fcf'] = ttm_fcf  # store for dashboard

        # PEG ratio
        growth = result.get('financial_analysis', {}).get('growth', {})
        eps_g = growth.get('eps_growth')
        if val.get('trailing_pe') and eps_g and eps_g > 0:
            val['peg_ratio'] = _safe_round(val['trailing_pe'] / eps_g, 2)

        # Payout ratio
        cf = result.get('cash_flow', {})
        divs = cf.get('dividends_paid', [])
        ni_list = inc.get('net_income', [])
        div_recent = [abs(d) for d in divs[:4] if d is not None]
        ni_recent = [n for n in ni_list[:4] if n is not None]
        if len(div_recent) == 4 and len(ni_recent) == 4:
            ttm_div = sum(div_recent)
            ttm_ni = sum(ni_recent)
            if ttm_ni > 0:
                val['payout_ratio'] = _safe_round(ttm_div / ttm_ni, 4)

        val['_note'] = 'Fundamentals from SEC EDGAR (10-K/10-Q). Price & market data from Yahoo Finance.'
        val['_price_source'] = 'Yahoo Finance'
        result['valuation'] = val

    except Exception as e:
        result['_yahoo_supplement_error'] = str(e)

    return result


# ── Revenue Segment Parsing ───────────────────────────────────────

def _parse_revenue_segments(cik, ticker_symbol):
    """
    Parse revenue segment breakdown from the latest 10-K filing's XBRL data.

    Fetches the XBRL instance document and extracts dimensional revenue data
    (product/service segments, business segments, and geographic segments).

    Returns dict with 'product_segments', 'business_segments', 'geographic_segments'
    or None on failure.
    """
    try:
        from bs4 import BeautifulSoup

        # Step 1: Get latest 10-K filing accession from submissions API
        submissions = _sec_get(f'https://data.sec.gov/submissions/CIK{cik}.json')
        recent = submissions.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        accessions = recent.get('accessionNumber', [])
        primary_docs = recent.get('primaryDocument', [])

        accession = None
        primary_doc = None
        for i, form in enumerate(forms):
            if form in ('10-K', '20-F'):
                accession = accessions[i].replace('-', '')
                primary_doc = primary_docs[i]
                break

        if not accession:
            return None

        # Step 2: Find the XBRL instance document (_htm.xml)
        cik_num = cik.lstrip('0')
        xbrl_doc = primary_doc.replace('.htm', '_htm.xml')

        _rate_limit()
        url = f'https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession}/{xbrl_doc}'
        resp = requests.get(url, headers=SEC_HEADERS, timeout=60)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, 'xml')

        # Step 3: Parse contexts with segment dimensions
        segment_contexts = {}
        for ctx in soup.find_all('context'):
            ctx_id = ctx.get('id', '')
            seg_elem = ctx.find('segment')
            period = ctx.find('period')
            if not seg_elem or not period:
                continue

            members = seg_elem.find_all('explicitMember')
            start_el = period.find('startDate')
            end_el = period.find('endDate')
            p_start = start_el.text if start_el else None
            p_end = end_el.text if end_el else None

            seg_dims = []
            for m in members:
                dim = m.get('dimension', '')
                member_val = m.text.strip()
                seg_dims.append((dim, member_val))

            if seg_dims and p_end:
                segment_contexts[ctx_id] = {
                    'dims': seg_dims,
                    'start': p_start,
                    'end': p_end,
                }

        if not segment_contexts:
            return None

        # Step 4: Extract revenue facts with segment contexts
        revenue_concepts = (
            'RevenueFromContractWithCustomerExcludingAssessedTax',
            'Revenues', 'SalesRevenueNet',
            'RevenueFromContractWithCustomerIncludingAssessedTax',
        )
        _SEGMENT_DIMS = ('ProductOrService', 'StatementBusinessSegments',
                         'Geographical', 'Geographic', 'StatementGeographical')

        # Collect all (end_date, dim, member, val) from revenue facts with segment contexts
        seg_facts = []
        for tag in soup.find_all():
            concept = tag.name
            if not concept or concept not in revenue_concepts:
                continue

            ctx_ref = tag.get('contextRef', '')
            if ctx_ref not in segment_contexts:
                continue

            info = segment_contexts[ctx_ref]
            try:
                val_text = tag.text.strip().replace(',', '')
                val = float(val_text)
            except (ValueError, AttributeError):
                continue

            for dim, member in info['dims']:
                if any(sd in dim for sd in _SEGMENT_DIMS):
                    seg_facts.append((info['end'], dim, member, val))

        if not seg_facts:
            return None

        # Find the latest end date among revenue segment facts
        max_end = max(f[0] for f in seg_facts)

        product_segments = {}
        business_segments = {}
        geographic_segments = {}

        for end_date, dim, member, val in seg_facts:
            if end_date != max_end:
                continue

            # Clean member name: "nvda:DataCenterMember" -> "Data Center"
            member_clean = member.split(':')[-1]
            member_clean = member_clean.replace('Member', '')
            # CamelCase to spaces, but keep acronyms together
            member_clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', member_clean)
            member_clean = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', member_clean)
            # Fix common patterns: "I Phone" -> "iPhone", "I Pad" -> "iPad"
            member_clean = re.sub(r'\bI (Phone|Pad|Cloud|Mac|Watch|Tunes)\b', r'i\1', member_clean)
            # Fix "Homeand" -> "Home and"
            member_clean = member_clean.replace('Homeand', 'Home and')
            member_clean = member_clean.replace('Includng', 'Including')
            # Collapse multiple spaces
            member_clean = re.sub(r'\s+', ' ', member_clean).strip()

            if 'ProductOrService' in dim:
                product_segments[member_clean] = val
            elif 'StatementBusinessSegments' in dim:
                business_segments[member_clean] = val
            elif 'Geographical' in dim or 'Geographic' in dim:
                geographic_segments[member_clean] = val

        result = {}
        if product_segments:
            result['product_segments'] = dict(sorted(product_segments.items(), key=lambda x: x[1], reverse=True))
        if business_segments:
            result['business_segments'] = dict(sorted(business_segments.items(), key=lambda x: x[1], reverse=True))
        if geographic_segments:
            result['geographic_segments'] = dict(sorted(geographic_segments.items(), key=lambda x: x[1], reverse=True))

        if result:
            result['_period'] = max_end
            result['_source'] = 'SEC EDGAR (10-K XBRL)'
            return result

        return None

    except Exception as e:
        return None


# ── Main SEC Extractor ──────────────────────────────────────────────

def get_company_financials_sec(ticker_symbol):
    """
    Fetch comprehensive financial data from SEC EDGAR XBRL filings.

    Returns data in the same structure as the Yahoo Finance extractor
    for easy source switching in the dashboard.
    """
    try:
        # Step 1: CIK lookup
        cik = _ticker_to_cik(ticker_symbol)
        if cik is None:
            return {'ticker': ticker_symbol, 'error': f'CIK not found for {ticker_symbol}. May be a foreign issuer not in SEC system.'}

        # Step 2: Fetch companyfacts
        facts = _sec_get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
        entity_name = facts.get('entityName', ticker_symbol)
        usgaap = facts.get('facts', {}).get('us-gaap', {})

        if not usgaap:
            return {'ticker': ticker_symbol, 'error': f'No us-gaap data for {ticker_symbol} (CIK {cik})'}

        # Step 3: Determine quarter timeline from revenue data
        end_dates = _get_recent_quarters(usgaap, n_quarters=5)
        if not end_dates:
            return {'ticker': ticker_symbol, 'error': f'No quarterly revenue data found for {ticker_symbol}'}

        quarters = [_end_date_to_quarter(d) for d in end_dates]
        n_q = len(end_dates)

        # Shorthand helpers
        def dur(concepts, unit='USD'):
            """Standard quarterly extraction (80-100 day periods)."""
            return _get_values_at_dates(usgaap, concepts, end_dates, 'duration', unit)

        def fy_dur(concepts, unit='USD'):
            """Quarterly extraction + FY-end derivation (Annual - Q1 - Q2 - Q3)."""
            vals = _get_values_at_dates(usgaap, concepts, end_dates, 'duration', unit)
            return _derive_fy_end_values(usgaap, concepts, end_dates, vals, unit)

        def inst(concepts):
            return _get_values_at_dates(usgaap, concepts, end_dates, 'instant', 'USD')

        # ── Income Statement (duration — with FY-end derivation) ──
        _rev_concepts = ['RevenueFromContractWithCustomerExcludingAssessedTax',
                         'Revenues', 'SalesRevenueNet',
                         'RevenueFromContractWithCustomerIncludingAssessedTax',
                         'RevenuesNetOfInterestExpense', 'NoninterestIncome']
        revenue = fy_dur(_rev_concepts)
        cost_of_rev = fy_dur(['CostOfGoodsAndServicesSold', 'CostOfRevenue'])
        gross_profit = fy_dur(['GrossProfit'])
        operating_income = fy_dur(['OperatingIncomeLoss'])
        rd_expense = fy_dur(['ResearchAndDevelopmentExpense'])
        sga_expense = fy_dur(['SellingGeneralAndAdministrativeExpense'])
        op_expense = fy_dur(['OperatingExpenses', 'CostsAndExpenses'])
        net_income = fy_dur(['NetIncomeLoss', 'ProfitLoss',
                             'NetIncomeLossAvailableToCommonStockholdersBasic'])
        pretax_income = fy_dur([
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
        ])
        tax_provision = fy_dur(['IncomeTaxExpenseBenefit'])
        diluted_eps = fy_dur(['EarningsPerShareDiluted'], unit='USD/shares')
        basic_eps = fy_dur(['EarningsPerShareBasic'], unit='USD/shares')
        diluted_shares = fy_dur([
            'WeightedAverageNumberOfDilutedSharesOutstanding',
        ], unit='shares')
        basic_shares = fy_dur([
            'WeightedAverageNumberOfSharesOutstandingBasic',
            'WeightedAverageNumberOfShareOutstandingBasicAndDiluted',
        ], unit='shares')
        depreciation = fy_dur(['DepreciationDepletionAndAmortization',
                               'DepreciationAmortizationAndAccretionNet', 'Depreciation'])

        # EBITDA = Operating Income + D&A
        ebitda = [
            round(oi + dep, 2) if oi is not None and dep is not None else oi
            for oi, dep in zip(operating_income, depreciation)
        ]

        income_statement = {
            'total_revenue': revenue,
            'cost_of_revenue': cost_of_rev,
            'gross_profit': gross_profit,
            'operating_expense': op_expense,
            'research_development': rd_expense,
            'selling_general_admin': sga_expense,
            'operating_income': operating_income,
            'ebitda': ebitda,
            'ebit': operating_income,
            'pretax_income': pretax_income,
            'tax_provision': tax_provision,
            'net_income': net_income,
            'diluted_eps': diluted_eps,
            'basic_eps': basic_eps,
            'diluted_shares': diluted_shares,
            'basic_shares': basic_shares,
        }

        # ── Balance Sheet (instant) ──────────────────────────
        total_assets = inst(['Assets'])
        current_assets = inst(['AssetsCurrent'])
        cash_equiv = inst(['CashAndCashEquivalentsAtCarryingValue'])
        marketable_sec = inst(['MarketableSecuritiesCurrent', 'ShortTermInvestments',
                               'AvailableForSaleSecuritiesDebtSecuritiesCurrent'])
        cash_and_st = [
            round(c + m, 2) if c is not None and m is not None else c
            for c, m in zip(cash_equiv, marketable_sec)
        ]
        accts_recv = inst(['AccountsReceivableNetCurrent', 'AccountsReceivableNet'])
        inventory = inst(['InventoryNet', 'Inventories'])
        goodwill = inst(['Goodwill'])
        net_ppe = inst(['PropertyPlantAndEquipmentNet'])
        non_current_assets = inst(['AssetsNoncurrent'])

        total_liab = inst(['Liabilities'])
        current_liab = inst(['LiabilitiesCurrent'])
        non_current_liab = inst(['LiabilitiesNoncurrent'])
        lt_debt = inst(['LongTermDebtNoncurrent'])
        current_debt = inst(['ShortTermBorrowings', 'CommercialPaper',
                             'LongTermDebtCurrent', 'SecuredDebtCurrent'])
        total_debt = inst(['LongTermDebt', 'DebtInstrumentCarryingAmount'])
        accts_payable = inst(['AccountsPayableCurrent', 'AccountsPayable'])
        accrued_exp = inst(['AccruedLiabilitiesCurrent', 'AccruedExpensesCurrent'])
        lease_current = inst(['OperatingLeaseLiabilityCurrent'])
        lease_noncurrent = inst(['OperatingLeaseLiabilityNoncurrent'])

        equity = inst(['StockholdersEquity',
                       'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'])
        retained = inst(['RetainedEarningsAccumulatedDeficit'])

        # Computed ratios
        debt_ratio = [_safe_divide(l, a) for l, a in zip(total_liab, total_assets)]
        d_to_e = [_safe_divide(td, eq) for td, eq in zip(total_debt, equity)]
        curr_ratio = [_safe_divide(ca, cl) for ca, cl in zip(current_assets, current_liab)]
        invested_cap = [
            round(td + eq - (c or 0), 2) if td is not None and eq is not None else None
            for td, eq, c in zip(total_debt, equity, cash_equiv)
        ]
        net_debt = [
            round(td - c, 2) if td is not None and c is not None else None
            for td, c in zip(total_debt, cash_equiv)
        ]

        balance_sheet = {
            'total_assets': total_assets,
            'current_assets': current_assets,
            'cash_and_short_term_investments': cash_and_st,
            'cash_and_equivalents': cash_equiv,
            'short_term_investments': marketable_sec,
            'accounts_receivable': accts_recv,
            'inventory': inventory,
            'total_non_current_assets': non_current_assets,
            'goodwill': goodwill,
            'net_ppe': net_ppe,
            'total_liabilities': total_liab,
            'current_liabilities': current_liab,
            'non_current_liabilities': non_current_liab,
            'long_term_debt': lt_debt,
            'current_debt': current_debt,
            'total_debt': total_debt,
            'accounts_payable': accts_payable,
            'accrued_expenses': accrued_exp,
            'lease_obligations_current': lease_current,
            'lease_obligations_noncurrent': lease_noncurrent,
            'net_debt': net_debt,
            'stockholders_equity': equity,
            'retained_earnings': retained,
            'invested_capital': invested_cap,
            'debt_ratio': debt_ratio,
            'debt_to_equity': d_to_e,
            'current_ratio': curr_ratio,
        }

        # ── Cash Flow (duration — handles cumulative YTD + FY-end derivation) ──
        def cf_dur(concepts, unit='USD'):
            """Cumulative YTD handling + FY-end derivation."""
            vals = _get_cashflow_quarterly_values(usgaap, concepts, end_dates, unit)
            return _derive_fy_end_values(usgaap, concepts, end_dates, vals, unit)

        op_cf = cf_dur(['NetCashProvidedByUsedInOperatingActivities',
                        'NetCashProvidedByOperatingActivities'])
        capex_raw = cf_dur(['PaymentsToAcquirePropertyPlantAndEquipment',
                            'PaymentsToAcquireProductiveAssets'])
        repurchases_raw = cf_dur(['PaymentsForRepurchaseOfCommonStock', 'PaymentsForRepurchaseOfEquity'])
        dividends_raw = cf_dur(['PaymentsOfDividends', 'PaymentsOfDividendsCommonStock'])
        inv_cf = cf_dur(['NetCashProvidedByUsedInInvestingActivities'])
        fin_cf = cf_dur(['NetCashProvidedByUsedInFinancingActivities'])
        dep_cf = cf_dur(['DepreciationDepletionAndAmortization',
                         'DepreciationAmortizationAndAccretionNet', 'Depreciation'])
        sbc = cf_dur(['ShareBasedCompensation', 'AllocatedShareBasedCompensationExpense'])

        # FCF = Operating CF - CapEx (capex_raw is positive payments, so subtract)
        fcf = [
            round(o - c, 2) if o is not None and c is not None else o
            for o, c in zip(op_cf, capex_raw)
        ]

        cash_flow = {
            'operating_cash_flow': op_cf,
            'capital_expenditure': [(-c if c is not None else None) for c in capex_raw],
            'free_cash_flow': fcf,
            'share_repurchases': [(-s if s is not None else None) for s in repurchases_raw],
            'dividends_paid': [(-d if d is not None else None) for d in dividends_raw],
            'investing_cash_flow': inv_cf,
            'financing_cash_flow': fin_cf,
            'depreciation_amortization': dep_cf,
            'stock_based_compensation': sbc,
        }

        # ── Valuation ────────────────────────────────────────
        # SEC filings don't include market price, so price-based ratios are N/A.
        # We provide per-share data so the dashboard can supplement with price.
        valuation = {
            'forward_pe': None,
            'trailing_pe': None,
            'peg_ratio': None,
            'price_to_book': None,
            'price_to_sales': None,
            'ev_to_ebitda': None,
            'ev_to_revenue': None,
            'ev_to_fcf': None,
            'enterprise_value': None,
            'market_cap': None,
            'price': None,
            'fifty_two_week_high': None,
            'fifty_two_week_low': None,
            'beta': None,
            'dividend_yield': None,
            'payout_ratio': None,
            'diluted_eps_ttm': None,
            'book_value_per_share': None,
            '_note': 'Valuation ratios require market price data. Use Yahoo Finance source for price-based metrics.',
        }

        # TTM EPS
        eps_recent = [e for e in diluted_eps[:4] if e is not None]
        if len(eps_recent) == 4:
            valuation['diluted_eps_ttm'] = _safe_round(sum(eps_recent), 2)

        # Book value per share
        eq0 = equity[0] if equity and equity[0] is not None else None
        sh0 = diluted_shares[0] if diluted_shares and diluted_shares[0] is not None else None
        if eq0 and sh0 and sh0 != 0:
            valuation['book_value_per_share'] = _safe_round(eq0 / sh0, 2)

        # ── Financial Analysis ────────────────────────────────
        rev0 = revenue[0] if revenue else None
        gp0 = gross_profit[0] if gross_profit else None
        oi0 = operating_income[0] if operating_income else None
        ebitda0 = ebitda[0] if ebitda else None
        ni0 = net_income[0] if net_income else None
        fcf0 = fcf[0] if fcf else None
        eq0_val = equity[0] if equity else None
        ta0 = total_assets[0] if total_assets else None
        ic0 = invested_cap[0] if invested_cap else None
        tp0 = tax_provision[0] if tax_provision else None
        pt0 = pretax_income[0] if pretax_income else None

        profitability = {
            'gross_margin': _safe_round(gp0 / rev0 * 100, 2) if gp0 and rev0 else None,
            'operating_margin': _safe_round(oi0 / rev0 * 100, 2) if oi0 and rev0 else None,
            'ebitda_margin': _safe_round(ebitda0 / rev0 * 100, 2) if ebitda0 and rev0 else None,
            'fcf_margin': _safe_round(fcf0 / rev0 * 100, 2) if fcf0 and rev0 else None,
            'net_margin': _safe_round(ni0 / rev0 * 100, 2) if ni0 and rev0 else None,
        }

        # Returns (annualized from quarterly)
        returns = {
            'roe': _safe_round((ni0 * 4) / eq0_val * 100, 2) if ni0 and eq0_val and eq0_val != 0 else None,
            'roa': _safe_round((ni0 * 4) / ta0 * 100, 2) if ni0 and ta0 and ta0 != 0 else None,
            'roic': None,
        }
        if oi0 and ic0 and ic0 != 0:
            tax_rate = 0.21
            if tp0 and pt0 and pt0 != 0:
                tax_rate = max(0, min(1, tp0 / pt0))
            nopat = oi0 * (1 - tax_rate)
            returns['roic'] = _safe_round((nopat * 4) / ic0 * 100, 2)

        turnover = {
            'asset_turnover': _safe_round((rev0 * 4) / ta0, 4) if rev0 and ta0 and ta0 != 0 else None,
            'debt_to_equity': d_to_e[0] if d_to_e else None,
            'current_ratio': curr_ratio[0] if curr_ratio else None,
        }

        growth = {
            'eps_growth': None,
            'revenue_growth': None,
            'earnings_quarterly_growth': None,
            'revenue_qoq': None,
            'revenue_yoy': None,
        }
        if len(revenue) >= 2 and revenue[0] and revenue[1] and revenue[1] != 0:
            growth['revenue_qoq'] = _safe_round((revenue[0] - revenue[1]) / abs(revenue[1]) * 100, 2)
        if len(revenue) >= 5 and revenue[0] and revenue[4] and revenue[4] != 0:
            growth['revenue_yoy'] = _safe_round((revenue[0] - revenue[4]) / abs(revenue[4]) * 100, 2)
            growth['revenue_growth'] = growth['revenue_yoy']
        if len(diluted_eps) >= 5 and diluted_eps[0] and diluted_eps[4] and diluted_eps[4] != 0:
            growth['eps_growth'] = _safe_round((diluted_eps[0] - diluted_eps[4]) / abs(diluted_eps[4]) * 100, 2)
        if len(net_income) >= 2 and net_income[0] and net_income[1] and net_income[1] != 0:
            growth['earnings_quarterly_growth'] = _safe_round((net_income[0] - net_income[1]) / abs(net_income[1]) * 100, 2)

        # ── Revenue Segments (from individual 10-K XBRL) ──────
        segments = _parse_revenue_segments(cik, ticker_symbol)

        result = {
            'ticker': ticker_symbol,
            'company_name': entity_name,
            'sector': 'N/A',
            'industry': 'N/A',
            'market_cap': None,
            'currency': 'USD',
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'SEC EDGAR (XBRL)',
            'quarters': quarters,
            'cik': cik,
            'income_statement': income_statement,
            'balance_sheet': balance_sheet,
            'cash_flow': cash_flow,
            'valuation': valuation,
            'financial_analysis': {
                'profitability': profitability,
                'returns': returns,
                'turnover': turnover,
                'growth': growth,
            },
            'revenue_segments': segments,
            'revenue_segments_note': None if segments else 'No segment data found in latest 10-K filing.',
        }

        # Supplement with Yahoo Finance (market cap, sector, industry, price-based valuation)
        result = _supplement_with_yahoo(result)

        return result

    except requests.exceptions.HTTPError as e:
        return {'ticker': ticker_symbol, 'error': f'SEC API HTTP error: {str(e)}'}
    except requests.exceptions.RequestException as e:
        return {'ticker': ticker_symbol, 'error': f'SEC API request error: {str(e)}'}
    except Exception as e:
        return {'ticker': ticker_symbol, 'error': str(e), 'traceback': traceback.format_exc()}


def get_top20_financials_sec(tickers=None):
    """Fetch SEC financial data for top 20 companies."""
    from data_extractors.equity_financials_extractor import TOP_20_TICKERS

    if tickers is None:
        tickers = TOP_20_TICKERS

    companies = {}
    errors = []

    for symbol in tickers:
        print(f"    [SEC] Fetching {symbol}...")
        data = get_company_financials_sec(symbol)
        companies[symbol] = data
        if 'error' in data:
            errors.append(f"{symbol}: {data['error']}")

    return {
        'companies': companies,
        'tickers': list(tickers),
        'count': len(tickers),
        'successful': len(tickers) - len(errors),
        'failed': len(errors),
        'errors': errors,
        'source': 'SEC EDGAR (XBRL)',
        'latest_date': datetime.now().strftime('%Y-%m-%d'),
    }
