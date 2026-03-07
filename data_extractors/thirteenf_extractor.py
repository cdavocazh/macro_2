"""
SEC EDGAR 13F-HR Institutional Holdings Extractor.

Fetches and parses 13F filings from SEC EDGAR to track institutional fund
holdings and quarter-over-quarter changes.

Uses the SEC EDGAR submissions API + filing archives:
- No API key required
- Rate limit: 10 requests/second (reuses sec_extractor rate limiter)
- Requires User-Agent header

Data flow:
1. submissions/CIK{cik}.json → find 13F-HR filings
2. Archives/edgar/data/{cik}/{acc}/index.json → locate infotable XML
3. Parse infotable XML → per-quarter holdings snapshots + QoQ changes
"""

import os
import requests
import time
import pandas as pd
from lxml import etree

from .sec_extractor import SEC_HEADERS, _rate_limit


# ── Fund Registry ────────────────────────────────────────────────────

FUND_REGISTRY = {
    'situational_awareness': {
        'cik': '0002045724',
        'name': 'Situational Awareness LP',
    },
    'berkshire_hathaway': {
        'cik': '0001067983',
        'name': 'Berkshire Hathaway Inc',
    },
    'bridgewater': {
        'cik': '0001350694',
        'name': 'Bridgewater Associates LP',
    },
    'citadel': {
        'cik': '0001423053',
        'name': 'Citadel Advisors LLC',
    },
    'renaissance_technologies': {
        'cik': '0001037389',
        'name': 'Renaissance Technologies LLC',
    },
}

OUTPUT_DIR = os.path.join('historical_data', '13F')

# 13F XML namespace
_NS = {'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}


# ── SEC API Helpers ──────────────────────────────────────────────────

def _sec_get_json(url):
    """GET JSON from SEC EDGAR with rate limiting."""
    _rate_limit()
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _sec_get_raw(url, timeout=60):
    """GET raw response from SEC EDGAR with rate limiting."""
    _rate_limit()
    resp = requests.get(url, headers=SEC_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


# ── Filing List ──────────────────────────────────────────────────────

def get_13f_filing_list(cik, max_filings=8):
    """Get list of 13F-HR filings for a CIK from SEC EDGAR.

    Args:
        cik: Zero-padded CIK string (e.g., '0001067983')
        max_filings: Maximum number of filings to return

    Returns:
        list of dicts: {accession_number, filing_date, report_date, quarter_label}
        OR dict with 'error' key on failure.
    """
    try:
        url = f'https://data.sec.gov/submissions/CIK{cik}.json'
        data = _sec_get_json(url)

        recent = data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        accessions = recent.get('accessionNumber', [])
        filing_dates = recent.get('filingDate', [])
        report_dates = recent.get('reportDate', [])

        # Collect all 13F-HR and 13F-HR/A filings
        raw_filings = []
        for i, form in enumerate(forms):
            if form in ('13F-HR', '13F-HR/A'):
                report_date = report_dates[i] if i < len(report_dates) else ''
                quarter_label = _date_to_quarter(report_date)
                raw_filings.append({
                    'accession_number': accessions[i],
                    'filing_date': filing_dates[i],
                    'report_date': report_date,
                    'quarter_label': quarter_label,
                    'form': form,
                })

        # Deduplicate by quarter: prefer 13F-HR/A (amendment) over 13F-HR,
        # and later filing_date over earlier
        by_quarter = {}
        for f in raw_filings:
            q = f['quarter_label']
            if q not in by_quarter:
                by_quarter[q] = f
            else:
                existing = by_quarter[q]
                # Prefer amendment over original
                if f['form'] == '13F-HR/A' and existing['form'] == '13F-HR':
                    by_quarter[q] = f
                # If both same type, prefer later filing date
                elif f['form'] == existing['form'] and f['filing_date'] > existing['filing_date']:
                    by_quarter[q] = f

        # Sort by report_date descending, take max_filings
        filings = sorted(by_quarter.values(), key=lambda x: x['report_date'], reverse=True)
        return filings[:max_filings]

    except Exception as e:
        return {'error': f'Failed to get filing list for CIK {cik}: {str(e)}'}


def _date_to_quarter(date_str):
    """Convert YYYY-MM-DD to quarter label like '2025Q4'."""
    if not date_str or len(date_str) < 7:
        return 'Unknown'
    try:
        month = int(date_str[5:7])
        year = date_str[:4]
        quarter = (month - 1) // 3 + 1
        return f'{year}Q{quarter}'
    except (ValueError, IndexError):
        return 'Unknown'


# ── Infotable XML Discovery ─────────────────────────────────────────

def _find_infotable_url(cik, accession_number):
    """Find the infotable XML URL from a 13F filing's document list.

    Args:
        cik: Zero-padded CIK string
        accession_number: With dashes (e.g., '0001067983-25-000002')

    Returns:
        str: Full URL to the infotable XML, or None if not found.
    """
    cik_num = cik.lstrip('0') or '0'
    acc_no_dashes = accession_number.replace('-', '')

    # Try index.json to enumerate documents
    try:
        index_url = f'https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dashes}/index.json'
        data = _sec_get_json(index_url)
        items = data.get('directory', {}).get('item', [])

        base_url = f'https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dashes}'

        # Priority 1: XML file with "infotable" in name
        for item in items:
            name = item.get('name', '')
            if name.lower().endswith('.xml') and 'infotable' in name.lower():
                return f'{base_url}/{name}'

        # Priority 2: XML file with "table" in name (some filers use different naming)
        for item in items:
            name = item.get('name', '')
            if name.lower().endswith('.xml') and 'table' in name.lower():
                return f'{base_url}/{name}'

        # Priority 3: Any XML file that isn't the primary doc or R-files
        for item in items:
            name = item.get('name', '')
            if (name.lower().endswith('.xml')
                    and not name.startswith('R')
                    and not name.startswith('FilingSummary')
                    and 'primary' not in name.lower()):
                return f'{base_url}/{name}'

    except Exception:
        pass

    # Fallback: try common filename
    return f'https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dashes}/infotable.xml'


# ── XML Parsing ──────────────────────────────────────────────────────

def parse_13f_infotable(xml_content):
    """Parse 13F information table XML into a list of holdings.

    Args:
        xml_content: bytes — raw XML content of the infotable

    Returns:
        list of dicts with holding data, or empty list on parse failure.
    """
    try:
        root = etree.fromstring(xml_content)
    except etree.XMLSyntaxError:
        return []

    holdings = []

    # Try with namespace first, fall back to no-namespace
    info_tables = root.findall('.//ns:infoTable', _NS)
    if not info_tables:
        # Try without namespace (older filings)
        info_tables = root.findall('.//{*}infoTable')
    if not info_tables:
        # Try bare tags
        info_tables = root.findall('.//infoTable')

    for info in info_tables:
        holdings.append(_parse_single_holding(info))

    return holdings


def _parse_single_holding(info):
    """Parse a single <infoTable> element into a holdings dict."""

    def _text(tag):
        """Find text in element, trying namespace then bare."""
        el = info.find(f'ns:{tag}', _NS)
        if el is None:
            el = info.find(f'{{*}}{tag}')
        if el is None:
            el = info.find(tag)
        return el.text.strip() if el is not None and el.text else None

    def _int_val(tag):
        val = _text(tag)
        try:
            return int(val) if val else 0
        except ValueError:
            return 0

    # Shares/principal amount is nested under shrsOrPrnAmt
    shares = 0
    share_type = 'SH'
    shramt_el = info.find('ns:shrsOrPrnAmt', _NS)
    if shramt_el is None:
        shramt_el = info.find('{*}shrsOrPrnAmt')
    if shramt_el is None:
        shramt_el = info.find('shrsOrPrnAmt')

    if shramt_el is not None:
        for tag in ('sshPrnamt', '{*}sshPrnamt', 'ns:sshPrnamt'):
            ns_map = _NS if tag.startswith('ns:') else None
            el = shramt_el.find(tag, ns_map) if ns_map else shramt_el.find(tag)
            if el is not None and el.text:
                try:
                    shares = int(el.text.strip())
                except ValueError:
                    pass
                break

        for tag in ('sshPrnamtType', '{*}sshPrnamtType', 'ns:sshPrnamtType'):
            ns_map = _NS if tag.startswith('ns:') else None
            el = shramt_el.find(tag, ns_map) if ns_map else shramt_el.find(tag)
            if el is not None and el.text:
                share_type = el.text.strip()
                break

    # Voting authority is nested
    voting_sole = voting_shared = voting_none = 0
    vote_el = info.find('ns:votingAuthority', _NS)
    if vote_el is None:
        vote_el = info.find('{*}votingAuthority')
    if vote_el is None:
        vote_el = info.find('votingAuthority')

    if vote_el is not None:
        for attr, tag_name in [('sole', 'Sole'), ('shared', 'Shared'), ('none', 'None')]:
            for prefix in (f'ns:{tag_name}', f'{{*}}{tag_name}', tag_name):
                ns_map = _NS if prefix.startswith('ns:') else None
                el = vote_el.find(prefix, ns_map) if ns_map else vote_el.find(prefix)
                if el is not None and el.text:
                    try:
                        if attr == 'sole':
                            voting_sole = int(el.text.strip())
                        elif attr == 'shared':
                            voting_shared = int(el.text.strip())
                        else:
                            voting_none = int(el.text.strip())
                    except ValueError:
                        pass
                    break

    return {
        'name_of_issuer': _text('nameOfIssuer') or '',
        'title_of_class': _text('titleOfClass') or '',
        'cusip': _text('cusip') or '',
        'value': _int_val('value'),
        'shares': shares,
        'share_type': share_type,
        'put_call': _text('putCall') or '',
        'investment_discretion': _text('investmentDiscretion') or '',
        'voting_sole': voting_sole,
        'voting_shared': voting_shared,
        'voting_none': voting_none,
    }


# ── Fetch Holdings ───────────────────────────────────────────────────

def fetch_13f_holdings(cik, accession_number):
    """Fetch and parse all holdings from a single 13F filing.

    Returns:
        list of holding dicts, or dict with 'error' key.
    """
    try:
        xml_url = _find_infotable_url(cik, accession_number)
        if not xml_url:
            return {'error': f'Could not find infotable XML for {accession_number}'}

        resp = _sec_get_raw(xml_url, timeout=60)
        holdings = parse_13f_infotable(resp.content)

        if not holdings:
            return {'error': f'No holdings parsed from {xml_url}'}

        return holdings

    except requests.HTTPError as e:
        return {'error': f'HTTP {e.response.status_code} fetching {accession_number}'}
    except Exception as e:
        return {'error': f'Error fetching holdings for {accession_number}: {str(e)}'}


# ── Change Computation ───────────────────────────────────────────────

def compute_changes(current_holdings, previous_holdings):
    """Compute quarter-over-quarter changes between two filing snapshots.

    Keys positions by (cusip, put_call) to handle options vs shares.

    Returns:
        list of change dicts with action classification.
    """
    def _build_map(holdings):
        m = {}
        for h in holdings:
            key = (h['cusip'], h.get('put_call') or '')
            if key in m:
                m[key]['shares'] += h['shares']
                m[key]['value'] += h['value']
            else:
                m[key] = {
                    'shares': h['shares'],
                    'value': h['value'],
                    'name_of_issuer': h['name_of_issuer'],
                    'title_of_class': h['title_of_class'],
                }
        return m

    curr_map = _build_map(current_holdings)
    prev_map = _build_map(previous_holdings)
    all_keys = set(curr_map.keys()) | set(prev_map.keys())

    changes = []
    for key in sorted(all_keys):
        cusip, put_call = key
        curr = curr_map.get(key)
        prev = prev_map.get(key)

        curr_shares = curr['shares'] if curr else 0
        prev_shares = prev['shares'] if prev else 0
        curr_value = curr['value'] if curr else 0
        prev_value = prev['value'] if prev else 0

        shares_change = curr_shares - prev_shares

        if prev_shares > 0:
            shares_change_pct = round((curr_shares - prev_shares) / prev_shares * 100, 2)
        elif curr_shares > 0:
            shares_change_pct = None  # NEW position
        else:
            shares_change_pct = 0.0

        if prev is None:
            action = 'NEW'
        elif curr is None:
            action = 'EXITED'
        elif curr_shares > prev_shares:
            action = 'INCREASED'
        elif curr_shares < prev_shares:
            action = 'DECREASED'
        else:
            action = 'UNCHANGED'

        name = (curr or prev)['name_of_issuer']
        title = (curr or prev)['title_of_class']

        changes.append({
            'cusip': cusip,
            'name_of_issuer': name,
            'title_of_class': title,
            'put_call': put_call,
            'current_shares': curr_shares,
            'previous_shares': prev_shares,
            'shares_change': shares_change,
            'shares_change_pct': shares_change_pct,
            'current_value': curr_value,
            'previous_value': prev_value,
            'value_change': curr_value - prev_value,
            'action': action,
        })

    return changes


# ── Fund Extraction Pipeline ─────────────────────────────────────────

def extract_fund_13f(fund_key, max_filings=8, output_dir=None):
    """Extract 13F holdings for a single fund.

    Saves per-quarter holdings CSVs and a cumulative changes.csv.

    Returns:
        dict with extraction summary.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR

    if fund_key not in FUND_REGISTRY:
        return {'error': f'Unknown fund: {fund_key}'}

    fund = FUND_REGISTRY[fund_key]
    cik = fund['cik']
    fund_name = fund['name']
    fund_dir = os.path.join(output_dir, fund_key)
    os.makedirs(fund_dir, exist_ok=True)

    print(f'\n  📁 {fund_name} (CIK {cik})')

    # Step 1: Get filing list
    filings = get_13f_filing_list(cik, max_filings=max_filings)
    if isinstance(filings, dict) and 'error' in filings:
        print(f'    ❌ {filings["error"]}')
        return filings
    if not filings:
        msg = f'No 13F-HR filings found for {fund_name}'
        print(f'    ❌ {msg}')
        return {'error': msg}

    print(f'    Found {len(filings)} filing(s)')

    # Step 2: Fetch holdings for each filing
    all_quarter_holdings = []  # [(quarter_label, filing_info, holdings_list)]
    holdings_saved = 0

    for filing in filings:
        quarter = filing['quarter_label']
        acc = filing['accession_number']
        print(f'    📄 {quarter} (filed {filing["filing_date"]})... ', end='', flush=True)

        holdings = fetch_13f_holdings(cik, acc)
        if isinstance(holdings, dict) and 'error' in holdings:
            print(f'❌ {holdings["error"]}')
            continue

        # Compute portfolio percentages
        total_value = sum(h['value'] for h in holdings)
        for h in holdings:
            h['pct_of_portfolio'] = round(h['value'] / total_value * 100, 4) if total_value > 0 else 0

        # Save per-quarter CSV
        df = pd.DataFrame(holdings)
        df['filing_date'] = filing['filing_date']
        df['report_date'] = filing['report_date']
        df['quarter'] = quarter
        df['fund'] = fund_key

        csv_path = os.path.join(fund_dir, f'holdings_{quarter}.csv')
        df.to_csv(csv_path, index=False)
        holdings_saved += 1
        print(f'{len(holdings)} positions')

        all_quarter_holdings.append((quarter, filing, holdings))

    # Step 3: Compute QoQ changes between consecutive quarters
    all_changes = []
    # Holdings are sorted newest-first; iterate pairs (newer, older)
    for i in range(len(all_quarter_holdings) - 1):
        curr_quarter, curr_filing, curr_holdings = all_quarter_holdings[i]
        prev_quarter, prev_filing, prev_holdings = all_quarter_holdings[i + 1]

        changes = compute_changes(curr_holdings, prev_holdings)
        for c in changes:
            c['quarter'] = curr_quarter
            c['previous_quarter'] = prev_quarter
        all_changes.extend(changes)

    # Save changes.csv
    changes_computed = False
    if all_changes:
        changes_df = pd.DataFrame(all_changes)
        # Reorder columns
        col_order = [
            'quarter', 'previous_quarter', 'cusip', 'name_of_issuer',
            'title_of_class', 'put_call', 'current_shares', 'previous_shares',
            'shares_change', 'shares_change_pct', 'current_value',
            'previous_value', 'value_change', 'action',
        ]
        changes_df = changes_df[[c for c in col_order if c in changes_df.columns]]
        changes_path = os.path.join(fund_dir, 'changes.csv')
        changes_df.to_csv(changes_path, index=False)
        changes_computed = True

        # Print summary of changes
        actions = changes_df['action'].value_counts()
        action_str = ', '.join(f'{k}: {v}' for k, v in actions.items())
        print(f'    📊 Changes: {action_str}')
    elif len(all_quarter_holdings) < 2:
        print(f'    ℹ️  Only {len(all_quarter_holdings)} filing(s) — no changes to compute')

    return {
        'fund': fund_key,
        'fund_name': fund_name,
        'filings_found': len(filings),
        'holdings_saved': holdings_saved,
        'changes_computed': changes_computed,
        'total_changes': len(all_changes),
    }


def extract_all_funds(max_filings=8, output_dir=None, funds=None):
    """Extract 13F holdings for all (or selected) funds.

    Args:
        max_filings: Filings per fund (default 8 = ~2 years)
        output_dir: Base output directory
        funds: Optional list of fund keys (default: all in FUND_REGISTRY)

    Returns:
        dict with 'results', 'successful', 'failed' keys.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    if funds is None:
        funds = list(FUND_REGISTRY.keys())

    os.makedirs(output_dir, exist_ok=True)

    start = time.time()
    results = []
    successful = 0
    failed = 0

    print(f'🏦 Extracting 13F holdings for {len(funds)} fund(s)...')

    for fund_key in funds:
        result = extract_fund_13f(fund_key, max_filings=max_filings, output_dir=output_dir)
        results.append(result)
        if 'error' in result:
            failed += 1
        else:
            successful += 1

    elapsed = time.time() - start
    print(f'\n✅ Done in {elapsed:.1f}s — {successful} succeeded, {failed} failed')

    return {
        'results': results,
        'successful': successful,
        'failed': failed,
        'elapsed': elapsed,
    }
