/**
 * Instrument → TradingView symbol mapping for the large chart drawer.
 *
 * TradingView's FREE embeddable widget does not carry exchange-licensed futures
 * data. `COMEX:GC1!` / `CME_MINI:ES1!` resolve in symbol search but render
 * "This symbol is only available on TradingView" inside the widget — verified
 * 2026-09-09. So futures are mapped to their closest FREE proxy (TradingView's
 * own spot indices, or a liquid ETF), and `proxyNote` states what the viewer is
 * actually looking at. Never silently swap an instrument for a lookalike.
 *
 * Anything absent here (FRED series, computed ratios, on-chain metrics) falls
 * back to the native lightweight-charts engine, which plots the repo's own data.
 *
 * Hyperliquid perps and the HIP-3 builder markets have been natively listed on
 * TradingView since 2026-07 under the HYPERLIQUID: / HIP3XYZ: prefixes.
 */

// key → { symbol, proxyNote? }.  proxyNote set ⇒ NOT the same instrument as the
// dashboard card; the drawer surfaces the note so the difference is visible.
export const TV_SYMBOLS_YF = {
  // Index futures → free index / ETF proxies
  es_futures: { symbol: 'SP:SPX', proxyNote: 'S&P 500 cash index — ES futures data is not licensed for the free widget' },
  rty_futures: { symbol: 'AMEX:IWM', proxyNote: 'Russell 2000 ETF (IWM) — RTY futures are not licensed for the free widget' },

  // Commodity futures → free spot indices / ETFs
  gold: { symbol: 'TVC:GOLD', proxyNote: 'Spot gold (US$/oz) — GC futures are not licensed for the free widget' },
  silver: { symbol: 'TVC:SILVER', proxyNote: 'Spot silver — SI futures are not licensed for the free widget' },
  crude_oil: { symbol: 'TVC:USOIL', proxyNote: 'WTI spot — CL futures are not licensed for the free widget' },
  natural_gas: { symbol: 'AMEX:UNG', proxyNote: 'US Natural Gas Fund (UNG) — NG futures are not licensed for the free widget' },
  copper: { symbol: 'AMEX:CPER', proxyNote: 'US Copper Index Fund (CPER) — HG futures are not licensed for the free widget' },

  // These are genuinely the same instrument on TradingView
  vix: { symbol: 'TVC:VIX' },
  dxy: { symbol: 'TVC:DXY' },
  us_10y: { symbol: 'TVC:US10Y' },
  usdjpy: { symbol: 'FX:USDJPY' },
  eurusd: { symbol: 'FX:EURUSD' },
  gbpusd: { symbol: 'FX:GBPUSD' },
  eurjpy: { symbol: 'FX:EURJPY' },
  spy: { symbol: 'AMEX:SPY' },
  hyg: { symbol: 'AMEX:HYG' },
  lqd: { symbol: 'AMEX:LQD' },
  // ^MOVE has no TradingView equivalent — native engine only.
};

export const TV_SYMBOLS_HL = {
  btc: { symbol: 'HYPERLIQUID:BTCUSDC.P' },
  eth: { symbol: 'HYPERLIQUID:ETHUSDC.P' },
  sol: { symbol: 'HYPERLIQUID:SOLUSDC.P' },
  hype: { symbol: 'HYPERLIQUID:HYPEUSDC.P' },
  paxg: { symbol: 'HYPERLIQUID:PAXGUSDC.P' },
  xyz100: { symbol: 'HIP3XYZ:XYZ100USDC.P' },
  // The abandoned flx:* builder listings (oil/sp500/natgas/copper_hl) are
  // deliberately absent — they carry no TradingView listing and their own
  // quotes are stale, so the native engine's `illiquid` framing is correct.
};

/** { symbol, proxyNote? } for an instrument, or null when it isn't listed. */
export function tvEntry(source, key) {
  if (!key) return null;
  const map = source === 'hl' ? TV_SYMBOLS_HL : TV_SYMBOLS_YF;
  return map[key] || null;
}

/** Bare TradingView symbol, or null. */
export function tvSymbol(source, key) {
  return tvEntry(source, key)?.symbol || null;
}
