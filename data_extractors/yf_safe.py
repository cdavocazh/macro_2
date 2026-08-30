"""Shared yfinance access wrapper that drops incomplete trailing bars.

Yahoo intermittently serves the most recent daily bar with Open/High/Low/Close
all NaN and only Volume populated.  Observed on 2026-08-28 across every US cash
equity, ETF and index (^GSPC, SPY, RSP, IWN, IWO, XLK, AAPL, ...) while futures
and FX were unaffected; it has also hit GC=F in earlier windows.

Extractors take ``.iloc[-1]`` to publish the latest value, so such a bar turns
into a silent ``null`` on the dashboard — or worse, into a fabricated signal:
``get_sp500_breadth_indicator()`` compared NaN closes, every comparison returned
False, and all 50 stocks landed in the "unchanged" branch, rendering 0% breadth
as "Weak bearish breadth - broad market weakness".

Fetching through ``yf_safe.Ticker`` instead of ``yf.Ticker`` trims those rows at
the boundary, so downstream ``.iloc[-1]`` sees the last bar that actually has a
price.  The proxy forwards every other attribute (``.info``, ``.options``,
``.option_chain``, ...) to the real ticker untouched.
"""
import yfinance as yf

_PRICE_COLS = ('Open', 'High', 'Low', 'Close')


def trim_incomplete_bars(df):
    """Drop trailing rows whose price columns are all NaN.

    Interior gaps are left alone — only the tail is trimmed, so historical
    series keep their shape.  Returns the frame unchanged when it has no
    recognisable price columns.
    """
    if df is None or getattr(df, 'empty', True):
        return df

    cols = [c for c in df.columns if c in _PRICE_COLS]
    if not cols:
        return df

    has_price = df[cols].notna().any(axis=1)
    if not has_price.any():
        return df.iloc[0:0]

    return df.loc[:has_price[has_price].index[-1]]


def last_valid(series):
    """Last non-NaN value of a Series, or None when there is none."""
    if series is None:
        return None
    clean = series.dropna()
    return None if clean.empty else clean.iloc[-1]


class _SafeTicker:
    """``yf.Ticker`` proxy whose ``.history()`` output is trimmed."""

    def __init__(self, inner):
        self._inner = inner

    def history(self, *args, **kwargs):
        return trim_incomplete_bars(self._inner.history(*args, **kwargs))

    def __getattr__(self, name):
        return getattr(self._inner, name)


def Ticker(*args, **kwargs):
    """Drop-in replacement for ``yf.Ticker`` with incomplete bars trimmed."""
    return _SafeTicker(yf.Ticker(*args, **kwargs))
