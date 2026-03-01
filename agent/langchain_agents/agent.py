"""
Financial Data Discrepancy Review Agent — LangChain SDK + Minimax LLM.

Usage:
    python -m agent.langchain_agents.agent "Review AAPL data for discrepancies"
    python -m agent.langchain_agents.agent "Scan all 20 companies for missing SEC data"
    python -m agent.langchain_agents.agent "Compare Yahoo vs SEC for NVDA and suggest fixes"

Requires:
    pip install langchain langchain-openai langgraph
    export MINIMAX_API_KEY=your_key
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from agent.shared.config import MINIMAX_API_KEY, MINIMAX_MODEL, MINIMAX_BASE_URL
from agent.shared import tools as shared_tools


# ── Minimax LLM via LangChain ────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    if not MINIMAX_API_KEY:
        raise ValueError(
            "MINIMAX_API_KEY not set. Export it: export MINIMAX_API_KEY=your_key"
        )
    return ChatOpenAI(
        model=MINIMAX_MODEL,
        api_key=MINIMAX_API_KEY,
        base_url=MINIMAX_BASE_URL,
        temperature=0.3,
        max_tokens=4096,
    )


# ── Tool Wrappers (adapt shared tools to @tool) ─────────────────────

@tool
def compare_sources(ticker: str) -> str:
    """
    Compare financial data between Yahoo Finance and SEC EDGAR for a ticker.
    Flags discrepancies in revenue, net income, cash flow, EPS, and balance sheet.
    Use this when investigating why two sources show different numbers.
    """
    return shared_tools.compare_sources(ticker)


@tool
def detect_missing_data(ticker: str, source: str = "both") -> str:
    """
    Scan a company's financial data for missing values, quarter gaps,
    and incomplete metrics. Source can be 'yahoo', 'sec', or 'both'.

    Detects:
    - None values in revenue, net income, cash flow, balance sheet
    - Non-consecutive quarter timelines
    - Entire metric sections that are empty (e.g. XBRL concept not found)
    """
    return shared_tools.detect_missing_data(ticker, source)


@tool
def validate_sec_xbrl_concepts(ticker: str) -> str:
    """
    Check which XBRL concepts exist for a ticker in SEC EDGAR.
    Shows available vs missing concepts for revenue, net income, cash flow, etc.
    Also detects cumulative YTD reporting style and IFRS vs US-GAAP.

    Use this to diagnose WHY a specific metric returns None from SEC EDGAR.
    """
    return shared_tools.validate_sec_xbrl_concepts(ticker)


@tool
def read_extractor_source(filename: str) -> str:
    """
    Read the source code of a data extractor to review its logic.
    Examples: 'sec_extractor.py', 'equity_financials_extractor.py',
    'web_scrapers.py', 'utils/helpers.py'
    """
    return shared_tools.read_extractor_source(filename)


@tool
def list_extractor_files() -> str:
    """List all data extractor files with their sizes and line counts."""
    return shared_tools.list_extractor_files()


@tool
def suggest_code_fix(filename: str, issue_description: str) -> str:
    """
    Prepare a structured code fix suggestion for a data extractor.
    Provide the filename and a description of the issue found.
    The result includes the source code for you to analyze and suggest specific changes.
    """
    return shared_tools.suggest_code_fix(filename, issue_description)


@tool
def batch_missing_data_scan(tickers: str = "", source: str = "sec") -> str:
    """
    Scan multiple tickers for missing data. Leave tickers empty for all top 20.
    Returns a coverage summary per ticker showing quarter gaps, empty metrics,
    and partial metrics.
    """
    return shared_tools.batch_missing_data_scan(tickers, source)


@tool
def format_web_search_query(ticker: str, issue_type: str) -> str:
    """
    Generate a web search query to research a data issue.
    issue_type: 'xbrl_concept', 'fiscal_year', 'reporting_change',
                'sec_filing', or 'data_discrepancy'.
    """
    return shared_tools.format_web_search_query(ticker, issue_type)


# ── Agent Definition ─────────────────────────────────────────────────

SYSTEM_INSTRUCTIONS = """\
You are a Financial Data Quality Analyst specializing in reviewing data discrepancies
across multiple financial data sources (Yahoo Finance, SEC EDGAR XBRL, FRED, web scrapers).

Your job is to:

1. **Detect missing data**: Find None values, quarter gaps, and incomplete metrics
   across the 20 largest US companies by market cap.

2. **Cross-source validation**: Compare Yahoo Finance vs SEC EDGAR data and flag
   discrepancies in revenue, net income, EPS, cash flow, and balance sheet items.

3. **Root cause analysis**: When data is missing, investigate WHY:
   - Is the XBRL concept name different? (e.g. ProfitLoss vs NetIncomeLoss)
   - Is the company using cumulative YTD cash flow reporting?
   - Is the FY-end quarter missing because it's only in the 10-K annual filing?
   - Did the company switch XBRL concepts mid-year? (e.g. GOOGL revenue concepts)
   - Is the company a foreign issuer using IFRS instead of US-GAAP? (e.g. TSM)
   - Are web scrapers being blocked (403 errors, bot detection)?

4. **Codebase review**: Read the extractor source code to understand extraction logic,
   identify bugs, and suggest specific code fixes.

5. **Internet research**: When you need external context (fiscal year dates, XBRL
   taxonomy changes, known data provider issues), generate appropriate search queries.

Common discrepancy patterns you should check:
- Revenue concept variations: RevenueFromContractWithCustomer* vs Revenues vs bank-specific
- Cash flow cumulative YTD: NVDA, TSLA report cumulative instead of standalone quarterly
- FY-end quarter gap: Annual filing (10-K) only has full-year total, not standalone Q4
- Net income concept: Some companies use ProfitLoss (AVGO, MA) instead of NetIncomeLoss
- CapEx concept: Some use PaymentsToAcquireProductiveAssets instead of PropertyPlantAndEquipment
- Forward P/E unreliable: MacroMicro returns 403; falls back to trailing P/E (proxy)
- Put/Call ratio: CBOE scraping unreliable; multiple fallback chain

When suggesting code fixes, be specific: mention exact line numbers, the current code,
and the proposed replacement code.

Always start by understanding the scope of the request, then use tools systematically
to investigate. Present findings in a clear, structured format.
"""

ALL_TOOLS = [
    compare_sources,
    detect_missing_data,
    validate_sec_xbrl_concepts,
    read_extractor_source,
    list_extractor_files,
    suggest_code_fix,
    batch_missing_data_scan,
    format_web_search_query,
]


def create_agent():
    """Create the financial data review agent with Minimax LLM via LangChain."""
    llm = _get_llm()
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_INSTRUCTIONS,
    )


def run_agent(query: str) -> str:
    """Run the agent with a user query and return the final output."""
    graph = create_agent()
    result = graph.invoke({"messages": [HumanMessage(content=query)]})
    # Extract the last AI message
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
            return msg.content
    return str(result)


# ── CLI Entry Point ──────────────────────────────────────────────────

def _interactive():
    """Interactive REPL mode."""
    graph = create_agent()
    print("Financial Data Discrepancy Review Agent (LangChain + Minimax)")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not query or query.lower() in ("quit", "exit", "q"):
            break

        print("\nAgent: Thinking...\n")
        try:
            result = graph.invoke({"messages": [HumanMessage(content=query)]})
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
                    print(f"Agent: {msg.content}\n")
                    break
        except Exception as e:
            print(f"Error: {e}\n")


def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(run_agent(query))
    else:
        _interactive()


if __name__ == "__main__":
    main()
