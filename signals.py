"""
signals.py — Signal Engine v3.0
All signal construction functions.

Rules:
  - Every function signature: (close, volume=None, **kwargs) → pd.DataFrame
  - Index = dates, columns = tickers
  - No API calls. No config constants imported directly.
    Pass parameters explicitly — functions are stateless and testable.
  - No globals. No PHOTONICS alias.

Purge from v2.6:
  - Bollinger_Pct_B removed (BUG-02 resolved)
  - PHOTONICS alias removed throughout
  - All functions now take universe as explicit parameter

BUG-01 FIX applied in build_polygon_signals():
  datetime index conversion before reindex.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


# =============================================================================
# Tier 1 — Price / Technical
# =============================================================================

def sig_momentum(
    close:    pd.DataFrame,
    universe: List[str],
    window:   int,
) -> pd.DataFrame:
    """n-day price momentum = pct_change(window)."""
    return close[universe].pct_change(window)


def sig_volume_surge(
    volume:   pd.DataFrame,
    universe: List[str],
    window:   int = 10,
) -> pd.DataFrame:
    """Volume / rolling mean - 1. Positive = above-average participation."""
    avg = volume[universe].rolling(window).mean()
    return (volume[universe] / avg) - 1


def sig_sma200_distance(
    close:    pd.DataFrame,
    universe: List[str],
    window:   int = 200,
) -> pd.DataFrame:
    """% distance from n-day SMA. Positive = above SMA."""
    sma = close[universe].rolling(window).mean()
    return (close[universe] - sma) / sma


def sig_ema_cross(
    close:    pd.DataFrame,
    universe: List[str],
    fast:     int = 9,
    slow:     int = 21,
) -> pd.DataFrame:
    """(Fast EMA - Slow EMA) / price. Positive = fast above slow."""
    ema_f = close[universe].ewm(span=fast).mean()
    ema_s = close[universe].ewm(span=slow).mean()
    return (ema_f - ema_s) / close[universe]


# NOTE: sig_bollinger_position removed (BUG-02 — Bollinger_Pct_B culled).
# Function retained as a comment for reference if needed in future studies.
# def sig_bollinger_position(close, universe, window=20, n_std=2.0):
#     mid   = close[universe].rolling(window).mean()
#     std   = close[universe].rolling(window).std()
#     upper = mid + n_std * std
#     lower = mid - n_std * std
#     return (close[universe] - lower) / (upper - lower) - 0.5


# =============================================================================
# Tier 2 — Macro Regime Filters
# =============================================================================

def sig_vix_regime(
    close:         pd.DataFrame,
    universe:      List[str],
    vix_threshold: float = 20.0,
) -> pd.DataFrame:
    """
    Binary regime: +1 if VIX < threshold (risk-on), -1 if VIX >= threshold.
    Used as position sizing gate, not a scored directional signal.
    """
    regime = pd.Series(
        np.where(close['VIX'] < vix_threshold, 1, -1),
        index=close.index
    )
    return pd.DataFrame({t: regime for t in universe})


def sig_vix_change(
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """Inverted 1-day VIX return. Falling VIX = bullish signal. CULLED in v2.6."""
    r = -close['VIX'].pct_change(1)
    return pd.DataFrame({t: r for t in universe})


def sig_sox_relative(
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """Ticker return minus SOX return. CULLED in v2.6 (near-zero IC)."""
    return close[universe].pct_change(1).subtract(close['SOX'].pct_change(1), axis=0)


def sig_tnx_change(
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """Inverted TNX daily change. CULLED in v2.6 (zero significance)."""
    r = -close['TNX'].pct_change(1)
    return pd.DataFrame({t: r for t in universe})


def sig_oil_change(
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """USO daily return. CULLED in v2.6 (zero significance)."""
    r = close['USO'].pct_change(1)
    return pd.DataFrame({t: r for t in universe})


def sig_spx_relative(
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """Ticker return minus SPX return. CULLED in v2.6."""
    return close[universe].pct_change(1).subtract(close['SPX'].pct_change(1), axis=0)


def sig_sox_vs_spx(
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """SOX return minus SPX return. CULLED in v2.6."""
    spread = close['SOX'].pct_change(1) - close['SPX'].pct_change(1)
    return pd.DataFrame({t: spread for t in universe})


# =============================================================================
# Tier 3 — Short Interest
# =============================================================================

def sig_si_ratio(
    si_df:    pd.DataFrame,
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """
    Short interest as % of float, broadcast as static daily signal.
    Cross-sectionally ranked within universe.
    Data is monthly — treat as slow-moving signal.
    """
    si_pct = {}
    for t in universe:
        if t in si_df.index:
            val = si_df.loc[t, 'shortPercentOfFloat']
            si_pct[t] = pd.Series(val if not pd.isna(val) else 0.0,
                                   index=close.index)
        else:
            si_pct[t] = pd.Series(0.0, index=close.index)

    df = pd.DataFrame(si_pct)
    # Cross-sectional rank
    return df.rank(axis=1, pct=True) - 0.5


def sig_si_days_to_cover(
    si_df:    pd.DataFrame,
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """Days-to-cover (short ratio), broadcast as static daily signal."""
    dtc = {}
    for t in universe:
        if t in si_df.index:
            val = si_df.loc[t, 'shortRatio']
            dtc[t] = pd.Series(val if not pd.isna(val) else 0.0,
                                index=close.index)
        else:
            dtc[t] = pd.Series(0.0, index=close.index)

    df = pd.DataFrame(dtc)
    return df.rank(axis=1, pct=True) - 0.5


def sig_si_momentum_interaction(
    si_df:    pd.DataFrame,
    close:    pd.DataFrame,
    universe: List[str],
    window:   int = 21,
) -> pd.DataFrame:
    """
    Short squeeze setup: high SI × positive price momentum.
    Both components ranked cross-sectionally. Product = interaction.
    """
    si_ranked  = sig_si_ratio(si_df, close, universe)
    mom_ranked = close[universe].pct_change(window).rank(axis=1, pct=True) - 0.5
    return si_ranked * mom_ranked


# =============================================================================
# Tier 4 — Earnings Estimate Revisions
# =============================================================================

def sig_eps_revision_direction(
    fmp_data: Dict[str, dict],
    close:    pd.DataFrame,
    universe: List[str],
) -> pd.DataFrame:
    """
    Direction of most recent analyst estimate revision.
    +1 = upward revision, -1 = downward, 0 = no data.
    PROVISIONAL: FMP data quality not yet validated against Bloomberg.
    """
    rev_dir = {}
    for t in universe:
        estimates = fmp_data.get(t, {}).get('estimates', [])
        if len(estimates) >= 2:
            curr = estimates[0].get('estimatedEpsAvg', 0)
            prev = estimates[1].get('estimatedEpsAvg', 0)
            direction = 1 if curr > prev else (-1 if curr < prev else 0)
        else:
            direction = 0
        rev_dir[t] = pd.Series(float(direction), index=close.index)

    return pd.DataFrame(rev_dir)


def sig_eps_surprise_avg(
    fmp_data: Dict[str, dict],
    close:    pd.DataFrame,
    universe: List[str],
    n:        int = 4,
) -> pd.DataFrame:
    """
    Average EPS surprise over last n quarters.
    Positive = consistent beat, negative = consistent miss.
    PROVISIONAL: FMP data quality not yet validated.
    """
    surprise_avg = {}
    for t in universe:
        surprises = fmp_data.get(t, {}).get('surprises', [])
        vals = []
        for s in surprises[:n]:
            actual   = s.get('actualEarningResult', None)
            estimate = s.get('estimatedEarning', None)
            if actual is not None and estimate and estimate != 0:
                vals.append((actual - estimate) / abs(estimate))
        avg = np.mean(vals) if vals else 0.0
        surprise_avg[t] = pd.Series(float(avg), index=close.index)

    return pd.DataFrame(surprise_avg)


# =============================================================================
# Tier 5 — Credit Market (yfinance proxy)
# =============================================================================

def sig_credit_spread(
    credit_close: pd.DataFrame,
    close:        pd.DataFrame,
    universe:     List[str],
) -> pd.DataFrame:
    """
    HY credit spread proxy: -(HYG return - LQD return).
    Negative sign: widening spread (HYG underperforms) = risk-off = bearish signal.
    Superseded by HY_OAS_FRED when FRED key available.
    """
    if 'HYG' not in credit_close.columns or 'LQD' not in credit_close.columns:
        return pd.DataFrame(0.0, index=close.index, columns=universe)

    spread = -(credit_close['HYG'].pct_change(1) - credit_close['LQD'].pct_change(1))
    return pd.DataFrame({t: spread for t in universe})


def sig_credit_spread_change(
    credit_close: pd.DataFrame,
    close:        pd.DataFrame,
    universe:     List[str],
    window:       int = 5,
) -> pd.DataFrame:
    """5-day change in HY-IG spread proxy."""
    if 'HYG' not in credit_close.columns or 'LQD' not in credit_close.columns:
        return pd.DataFrame(0.0, index=close.index, columns=universe)

    spread     = credit_close['HYG'] / credit_close['LQD']
    spread_chg = -spread.pct_change(window)
    return pd.DataFrame({t: spread_chg for t in universe})


def sig_yield_curve_slope(
    credit_close: pd.DataFrame,
    close:        pd.DataFrame,
    universe:     List[str],
) -> pd.DataFrame:
    """
    10Y-2Y yield curve slope proxy via TNX - IRX.
    Steepening = positive = growth regime.
    Superseded by YieldCurve_FRED when FRED key available.
    """
    if 'TNX' not in close.columns or 'IRX' not in close.columns:
        return pd.DataFrame(0.0, index=close.index, columns=universe)

    slope = close['TNX'] - close['IRX']
    return pd.DataFrame({t: slope for t in universe})


# =============================================================================
# Tier 6 — FRED Macro
# =============================================================================

def sig_breakeven_inflation(
    fred_data: Dict[str, pd.Series],
    close:     pd.DataFrame,
    universe:  List[str],
) -> pd.DataFrame:
    """5Y breakeven inflation rate — market-implied forward inflation."""
    s = fred_data.get('Breakeven5Y', pd.Series(dtype=float))
    if s.empty:
        return pd.DataFrame(0.0, index=close.index, columns=universe)
    s_aligned = s.reindex(close.index, method='ffill')
    return pd.DataFrame({t: s_aligned for t in universe})


def sig_cpi_regime(
    fred_data: Dict[str, pd.Series],
    close:     pd.DataFrame,
    universe:  List[str],
) -> pd.DataFrame:
    """
    CPI momentum regime: +1 if 3-month CPI change > 0 (accelerating),
    -1 if decelerating. Monthly data broadcast to daily.
    """
    s = fred_data.get('CPI', pd.Series(dtype=float))
    if s.empty:
        return pd.DataFrame(0.0, index=close.index, columns=universe)
    momentum = s.pct_change(3)
    regime   = np.sign(momentum).reindex(close.index, method='ffill').fillna(0)
    return pd.DataFrame({t: regime for t in universe})


def sig_corecpi_change(
    fred_data: Dict[str, pd.Series],
    close:     pd.DataFrame,
    universe:  List[str],
) -> pd.DataFrame:
    """3-month change in core CPI — inflation momentum signal."""
    s = fred_data.get('CoreCPI', pd.Series(dtype=float))
    if s.empty:
        return pd.DataFrame(0.0, index=close.index, columns=universe)
    chg = s.pct_change(3).reindex(close.index, method='ffill').fillna(0)
    return pd.DataFrame({t: chg for t in universe})


def sig_hy_oas(
    fred_data:    Dict[str, pd.Series],
    credit_close: pd.DataFrame,
    close:        pd.DataFrame,
    universe:     List[str],
) -> pd.DataFrame:
    """
    HY OAS spread from FRED (BAMLH0A0HYM2). Cleaner than HYG/LQD proxy.
    Falling OAS = tightening spreads = risk appetite = bullish signal.
    Falls back to yfinance proxy if FRED data unavailable.
    """
    s = fred_data.get('HY_OAS', pd.Series(dtype=float))
    if not s.empty:
        # Invert: falling spread = positive signal
        spread = -s.pct_change(5).reindex(close.index, method='ffill').fillna(0)
        return pd.DataFrame({t: spread for t in universe})
    # Fallback to yfinance proxy
    return sig_credit_spread(credit_close, close, universe)


def sig_yield_curve_fred(
    fred_data: Dict[str, pd.Series],
    close:     pd.DataFrame,
    universe:  List[str],
) -> pd.DataFrame:
    """
    10Y-2Y yield curve slope from FRED (T10Y2Y).
    Cleaner than TNX-IRX reconstruction.
    Falls back to yfinance proxy if FRED data unavailable.
    """
    s = fred_data.get('YieldCurve', pd.Series(dtype=float))
    if not s.empty:
        slope = s.reindex(close.index, method='ffill').fillna(0)
        return pd.DataFrame({t: slope for t in universe})
    # Fallback to yfinance proxy
    if 'TNX' in close.columns and 'IRX' in close.columns:
        slope = (close['TNX'] - close['IRX'])
        return pd.DataFrame({t: slope for t in universe})
    return pd.DataFrame(0.0, index=close.index, columns=universe)


# =============================================================================
# Tier 7 — Massive.com (Polygon) Signals
# =============================================================================

def build_polygon_signals(
    vwap_slope_data: Dict[str, pd.Series],
    pc_ratio_data:   Dict[str, pd.Series],
    close:           pd.DataFrame,
    universe:        List[str],
) -> Dict[str, pd.DataFrame]:
    """
    Align Massive VWAP slope and P/C ratio data to daily close index.

    BUG-01 FIX: Input series index converted to datetime64 before reindex
    to avoid TypeError: Cannot compare dtypes int64 and datetime64[ns].

    Returns dict with keys 'VWAP_Slope' and 'PC_Ratio'.
    Empty DataFrames (all NaN) if Massive pull was skipped.
    """
    def align(series_dict: Dict[str, pd.Series], name: str) -> pd.DataFrame:
        aligned = {}
        for t in universe:
            s = series_dict.get(t, pd.Series(dtype=float))
            if len(s) > 0:
                # BUG-01 FIX: ensure datetime index before reindex
                s = s.copy()
                s.index = pd.to_datetime(s.index)
            aligned[t] = s.reindex(close.index, method='ffill')
        return pd.DataFrame(aligned)

    return {
        'VWAP_Slope': align(vwap_slope_data, 'VWAP_Slope'),
        'PC_Ratio':   align(pc_ratio_data,   'PC_Ratio'),
    }


# =============================================================================
# Signal Registry — build full signals dict
# =============================================================================

def build_signals(
    close:           pd.DataFrame,
    volume:          pd.DataFrame,
    credit_close:    pd.DataFrame,
    si_df:           pd.DataFrame,
    fmp_data:        Dict[str, dict],
    fred_data:       Dict[str, pd.Series],
    vwap_slope_data: Dict[str, pd.Series],
    pc_ratio_data:   Dict[str, pd.Series],
    universe:        List[str],
    # Signal construction parameters (passed explicitly, not from globals)
    vol_window:      int   = 10,
    sma_window:      int   = 200,
    ema_fast:        int   = 9,
    ema_slow:        int   = 21,
    vix_threshold:   float = 20.0,
) -> Dict[str, pd.DataFrame]:
    """
    Build complete signals dict from all data sources.
    All parameters explicit — no globals, fully testable.

    Returns:
        dict keyed by signal_name → pd.DataFrame(index=dates, columns=universe)
    """
    polygon_sigs = build_polygon_signals(
        vwap_slope_data, pc_ratio_data, close, universe
    )

    signals = {
        # ── Tier 1: Price / Technical ─────────────────────────────────────────
        'Momentum_5d'      : sig_momentum(close, universe, 5),
        'Momentum_10d'     : sig_momentum(close, universe, 10),
        'Momentum_21d'     : sig_momentum(close, universe, 21),
        'Volume_Surge'     : sig_volume_surge(volume, universe, vol_window),
        'SMA200_Distance'  : sig_sma200_distance(close, universe, sma_window),
        'EMA_Cross_9_21'   : sig_ema_cross(close, universe, ema_fast, ema_slow),
        # Bollinger_Pct_B REMOVED — BUG-02 resolved

        # ── Tier 2: Macro (culled signals retained for IC comparison only) ────
        'VIX_Regime'       : sig_vix_regime(close, universe, vix_threshold),
        'VIX_Change_1d'    : sig_vix_change(close, universe),
        'SOX_Relative'     : sig_sox_relative(close, universe),
        'TNX_Change'       : sig_tnx_change(close, universe),
        'Oil_Change'       : sig_oil_change(close, universe),
        'SPX_Relative'     : sig_spx_relative(close, universe),
        'SOX_vs_SPX'       : sig_sox_vs_spx(close, universe),

        # ── Tier 3: Short Interest ────────────────────────────────────────────
        'SI_Ratio'         : sig_si_ratio(si_df, close, universe),
        'SI_DaysToCover'   : sig_si_days_to_cover(si_df, close, universe),
        'SI_Momentum'      : sig_si_momentum_interaction(si_df, close, universe),

        # ── Tier 4: Earnings Estimate Revisions ───────────────────────────────
        'EPS_Revision_Dir' : sig_eps_revision_direction(fmp_data, close, universe),
        'EPS_Surprise_Avg' : sig_eps_surprise_avg(fmp_data, close, universe),

        # ── Tier 5: Credit Market (yfinance proxy) ────────────────────────────
        'CreditSpread'         : sig_credit_spread(credit_close, close, universe),
        'CreditSpread_Change'  : sig_credit_spread_change(credit_close, close, universe),
        'YieldCurve_Slope'     : sig_yield_curve_slope(credit_close, close, universe),

        # ── Tier 6: FRED Macro ────────────────────────────────────────────────
        'Breakeven_Inflation'  : sig_breakeven_inflation(fred_data, close, universe),
        'CPI_Regime'           : sig_cpi_regime(fred_data, close, universe),
        'CoreCPI_Change'       : sig_corecpi_change(fred_data, close, universe),
        'HY_OAS_FRED'          : sig_hy_oas(fred_data, credit_close, close, universe),
        'YieldCurve_FRED'      : sig_yield_curve_fred(fred_data, close, universe),

        # ── Tier 7: Massive.com — provisional, pending IC validation ──────────
        'VWAP_Slope'           : polygon_sigs['VWAP_Slope'],
        'PC_Ratio'             : polygon_sigs['PC_Ratio'],
    }

    # Tier map for diagnostics
    tier_map = {
        'Tier 1 Price'    : ['Momentum_5d','Momentum_10d','Momentum_21d',
                             'Volume_Surge','SMA200_Distance','EMA_Cross_9_21'],
        'Tier 2 Macro'    : ['VIX_Regime','VIX_Change_1d','SOX_Relative',
                             'TNX_Change','Oil_Change','SPX_Relative','SOX_vs_SPX'],
        'Tier 3 ShortInt' : ['SI_Ratio','SI_DaysToCover','SI_Momentum'],
        'Tier 4 Earnings' : ['EPS_Revision_Dir','EPS_Surprise_Avg'],
        'Tier 5 Credit'   : ['CreditSpread','CreditSpread_Change','YieldCurve_Slope'],
        'Tier 6 FRED'     : ['Breakeven_Inflation','CPI_Regime','CoreCPI_Change',
                             'HY_OAS_FRED','YieldCurve_FRED'],
        'Tier 7 Massive'  : ['VWAP_Slope','PC_Ratio'],
    }

    print(f'{len(signals)} signals built:')
    for tier, names in tier_map.items():
        present = [s for s in names if s in signals]
        print(f'  {tier}: {present}')

    return signals
