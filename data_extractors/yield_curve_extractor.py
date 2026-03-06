"""
Yield Curve analysis extractor.
Fetches 2s10s spread from FRED and classifies the yield curve regime
into one of four states: Bear Steepener, Bull Steepener, Bear Flattener, Bull Flattener.

Regime classification:
  - Steepening = spread widening (10Y - 2Y increasing)
  - Flattening = spread narrowing (10Y - 2Y decreasing)
  - Bull = average rate level falling (lower yields)
  - Bear = average rate level rising (higher yields)

Historical cycle sequence: Bear Flattener → Bull Flattener → Bull Steepener → Bear Steepener → repeat
"""
import pandas as pd
from fredapi import Fred
import config


# Regime metadata for display
REGIME_INFO = {
    'Bear Steepener': {
        'emoji': '🟠',
        'color': '#ff9800',
        'signal': 'Growth / inflation rising',
        'detail': (
            'Both yields rising, 10Y rising faster. '
            'Markets pricing higher growth or inflation. '
            'Typically bullish equities, bearish long-duration bonds.'
        ),
    },
    'Bull Steepener': {
        'emoji': '🔴',
        'color': '#f44336',
        'signal': 'Recession / Fed easing',
        'detail': (
            'Both yields falling, 2Y falling faster (Fed cutting anticipated). '
            'Classic recession signal. Risk-off for equities, bullish for bonds.'
        ),
    },
    'Bear Flattener': {
        'emoji': '🟡',
        'color': '#ffc107',
        'signal': 'Fed tightening cycle',
        'detail': (
            'Both yields rising, 2Y rising faster (Fed hiking). '
            'Late cycle indicator. Curve heading toward inversion.'
        ),
    },
    'Bull Flattener': {
        'emoji': '🔵',
        'color': '#2196f3',
        'signal': 'Flight to quality',
        'detail': (
            'Both yields falling, 10Y falling faster. '
            'Investors rushing to long-duration safety. Pre-recession positioning.'
        ),
    },
    'Neutral': {
        'emoji': '⚪',
        'color': '#9e9e9e',
        'signal': 'No clear regime',
        'detail': 'Spread change within ±1bp over the lookback period. No dominant trend.',
    },
}


def _classify_regime(delta_2y, delta_10y, delta_spread):
    """
    Classify yield curve regime based on rate and spread changes.

    Args:
        delta_2y: Change in 2Y yield over lookback period
        delta_10y: Change in 10Y yield over lookback period
        delta_spread: Change in 2s10s spread over lookback period

    Returns:
        Regime string: one of REGIME_INFO keys
    """
    THRESHOLD = 0.01  # 1bp minimum change to classify (avoid noise)

    avg_rate_move = (delta_2y + delta_10y) / 2

    if delta_spread > THRESHOLD:       # Steepening
        if avg_rate_move <= 0:
            return 'Bull Steepener'
        else:
            return 'Bear Steepener'
    elif delta_spread < -THRESHOLD:    # Flattening
        if avg_rate_move <= 0:
            return 'Bull Flattener'
        else:
            return 'Bear Flattener'
    else:
        return 'Neutral'


def get_yield_curve_data():
    """
    Get 2s10s yield spread and classify the current yield curve regime.

    Fetches:
      - T10Y2Y: 10Y minus 2Y spread (pre-computed by FRED)
      - DGS2: 2-Year Treasury yield
      - DGS10: 10-Year Treasury yield

    Regime classification uses a 20-business-day lookback (~1 month)
    to determine the direction and type of yield curve movement.

    Returns: dict with spread, regime, deltas, historical series
    """
    LOOKBACK = 20  # business days

    try:
        fred = Fred(api_key=config.FRED_API_KEY)

        # Fetch all three series
        spread_raw = fred.get_series('T10Y2Y')
        dgs2_raw = fred.get_series('DGS2')
        dgs10_raw = fred.get_series('DGS10')

        if spread_raw is None or dgs2_raw is None or dgs10_raw is None:
            return {'error': 'Could not fetch yield curve data from FRED'}

        spread = spread_raw.dropna()
        dgs2 = dgs2_raw.dropna()
        dgs10 = dgs10_raw.dropna()

        if spread.empty or dgs2.empty or dgs10.empty:
            return {'error': 'Empty yield curve data from FRED'}

        # Current values
        current_spread = float(spread.iloc[-1])
        current_2y = float(dgs2.iloc[-1])
        current_10y = float(dgs10.iloc[-1])
        latest_date = spread.index[-1]

        # Previous day change
        prev_spread = float(spread.iloc[-2]) if len(spread) >= 2 else current_spread
        change_1d = round(current_spread - prev_spread, 4)

        # Compute regime using lookback period
        min_len = LOOKBACK + 1
        if len(dgs2) >= min_len and len(dgs10) >= min_len and len(spread) >= min_len:
            delta_2y = float(dgs2.iloc[-1] - dgs2.iloc[-(LOOKBACK + 1)])
            delta_10y = float(dgs10.iloc[-1] - dgs10.iloc[-(LOOKBACK + 1)])
            delta_spread = float(spread.iloc[-1] - spread.iloc[-(LOOKBACK + 1)])

            regime = _classify_regime(delta_2y, delta_10y, delta_spread)
        else:
            delta_2y = 0
            delta_10y = 0
            delta_spread = 0
            regime = 'Neutral'

        regime_info = REGIME_INFO[regime]

        return {
            'spread_2s10s': round(current_spread, 4),
            'us_2y_yield': round(current_2y, 4),
            'us_10y_yield': round(current_10y, 4),
            'change_1d': change_1d,
            'is_inverted': current_spread < 0,
            # Regime classification
            'regime': regime,
            'regime_emoji': regime_info['emoji'],
            'regime_color': regime_info['color'],
            'regime_signal': regime_info['signal'],
            'regime_detail': regime_info['detail'],
            # Deltas for transparency
            'delta_2y': round(delta_2y, 4),
            'delta_10y': round(delta_10y, 4),
            'delta_spread': round(delta_spread, 4),
            'lookback_days': LOOKBACK,
            # Metadata
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (T10Y2Y, DGS2, DGS10)',
            'units': 'Percentage Points',
            # Historical series for charts
            'historical': spread,
            'historical_2y': dgs2,
            'historical_10y': dgs10,
        }

    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f'Error fetching yield curve data: {str(e)}'}
