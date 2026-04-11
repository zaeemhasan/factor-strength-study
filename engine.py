"""
engine.py — Signal Engine v3.0
11-step alpha combination pipeline. Fully stateless.
Same inputs always produce same outputs. No globals. No API calls.

Steps:
    1.  Raw signal dict (built in signals.py)
    2.  Serial demeaning — removes trend drift
    3.  Sample variance per signal×ticker
    4.  Standardization — unit variance
    5.  Drop most recent observation — no look-ahead
    6.  Cross-sectional demeaning — removes shared macro factor
    7.  Drop final period — secondary data hygiene
    8.  Expected forward return (rolling D_LOOKBACK window)
    9.  Residual regression — extract independent contribution per signal
    10. Signal weights — rank-normalized ε / σ, regime-conditional
    11. Normalize — Σ|w| = 1 per ticker

    Mega-Alpha: weighted combination of all KEEP signals → daily score per ticker.
    Regime-Conditional IC: split by VIX and TNX threshold.
"""

import warnings
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, rankdata
from sklearn.linear_model import LinearRegression
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings('ignore')


# =============================================================================
# IC Computation
# =============================================================================

def compute_ic(
    signal_df: pd.DataFrame,
    close:     pd.DataFrame,
    ticker:    str,
    horizon:   int,
) -> Tuple[float, float]:
    """
    Spearman rank IC between signal and forward return at given horizon.

    Returns:
        (ic, p_value) — (nan, nan) if insufficient data
    """
    if ticker not in signal_df.columns or ticker not in close.columns:
        return np.nan, np.nan

    fwd  = close[ticker].pct_change(horizon).shift(-horizon)
    sig  = signal_df[ticker]
    df   = pd.concat([sig, fwd], axis=1).dropna()
    df.columns = ['signal', 'fwd']

    if len(df) < 20:
        return np.nan, np.nan

    ic, pval = spearmanr(df['signal'], df['fwd'])
    return round(float(ic), 6), round(float(pval), 6)


def run_ic_baseline(
    signals:  Dict[str, pd.DataFrame],
    close:    pd.DataFrame,
    universe: List[str],
    horizons: List[int],
) -> pd.DataFrame:
    """
    v1 IC baseline — raw signals, all horizons.
    Returns DataFrame with columns: Signal, Ticker, Horizon, IC, p_value.
    """
    rows = []
    for sig_name, sig_df in signals.items():
        for t in universe:
            for h in horizons:
                ic, pval = compute_ic(sig_df, close, t, h)
                rows.append({
                    'Signal':  sig_name,
                    'Ticker':  t,
                    'Horizon': h,
                    'IC':      ic,
                    'p_value': pval,
                })
    return pd.DataFrame(rows)


def summarize_ic(ic_df: pd.DataFrame) -> pd.DataFrame:
    """
    Best horizon per signal: highest mean |IC| across tickers.
    Returns DataFrame: Signal, Optimal_Horizon, Mean_IC, Mean_AbsIC, Pct_Sig.
    """
    rows = []
    for sig_name, grp in ic_df.groupby('Signal'):
        by_horizon = (grp.groupby('Horizon')
                        .agg(Mean_AbsIC=('IC', lambda x: x.abs().mean()))
                        .reset_index())
        best_h   = by_horizon.loc[by_horizon['Mean_AbsIC'].idxmax(), 'Horizon']
        best_grp = grp[grp['Horizon'] == best_h]
        rows.append({
            'Signal':           sig_name,
            'Optimal_Horizon':  int(best_h),
            'Mean_IC':          round(best_grp['IC'].mean(), 6),
            'Mean_AbsIC':       round(best_grp['IC'].abs().mean(), 6),
            'Pct_Sig':          round((best_grp['p_value'] < 0.05).mean(), 4),
        })
    return pd.DataFrame(rows).sort_values('Mean_AbsIC', ascending=False).reset_index(drop=True)


# =============================================================================
# Steps 2-7 — Signal Preprocessing
# =============================================================================

def step2_demean(signals: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Step 2: Serial demeaning — subtract rolling mean from each signal."""
    X = {}
    for sig_name, df in signals.items():
        rolling_mean = df.expanding().mean()
        X[sig_name]  = df - rolling_mean
    return X


def step3_variance(
    X:        Dict[str, pd.DataFrame],
    universe: List[str],
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    """
    Step 3: Sample variance and std dev per signal×ticker.
    Returns (sigma2, sigma) both keyed [signal_name][ticker].
    """
    sigma2 = {}
    sigma  = {}
    for sig_name, df in X.items():
        sigma2[sig_name] = {}
        sigma[sig_name]  = {}
        for t in universe:
            if t not in df.columns:
                sigma2[sig_name][t] = 1.0
                sigma[sig_name][t]  = 1.0
                continue
            vals = df[t].dropna().values
            v    = float(np.var(vals)) if len(vals) > 1 else 1.0
            sigma2[sig_name][t] = v if v > 0 else 1.0
            sigma[sig_name][t]  = float(np.sqrt(sigma2[sig_name][t]))
    return sigma2, sigma


def step4_standardize(
    X:        Dict[str, pd.DataFrame],
    sigma:    Dict[str, Dict[str, float]],
    universe: List[str],
) -> Dict[str, pd.DataFrame]:
    """Step 4: Standardize each signal×ticker to unit variance."""
    Y = {}
    for sig_name, df in X.items():
        std_df = df.copy()
        for t in universe:
            if t in df.columns:
                std_df[t] = df[t] / sigma[sig_name][t]
        Y[sig_name] = std_df
    return Y


def step5_drop_recent(Y: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Step 5: Drop most recent observation to prevent look-ahead."""
    return {k: v.dropna().iloc[:-1] for k, v in Y.items()}


def step6_cross_sectional_demean(
    Y_hist:   Dict[str, pd.DataFrame],
    universe: List[str],
) -> Dict[str, pd.DataFrame]:
    """
    Step 6: Cross-sectional demeaning.
    At each date, subtract mean across tickers.
    Returns Lambda keyed by ticker → DataFrame(index=dates, columns=signals).
    """
    Lambda = {}
    for t in universe:
        ticker_panel = pd.DataFrame({
            sig: Y_hist[sig][t] if t in Y_hist[sig].columns
            else pd.Series(dtype=float)
            for sig in Y_hist
        })
        cross_mean   = ticker_panel.mean(axis=1)
        Lambda[t]    = ticker_panel.subtract(cross_mean, axis=0)
    return Lambda


def step7_drop_final(Lambda: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Step 7: Drop final period after cross-sectional demeaning."""
    return {t: df.iloc[:-1] for t, df in Lambda.items()}


# =============================================================================
# Step 8 — Expected Forward Return
# =============================================================================

def step8_expected_return(
    signals:    Dict[str, pd.DataFrame],
    close:      pd.DataFrame,
    universe:   List[str],
    sigma:      Dict[str, Dict[str, float]],
    best_horizon: Dict[str, int],
    d_lookback: int = 21,
) -> Dict[str, pd.DataFrame]:
    """
    Step 8: Normalized expected forward return per signal×ticker.
    E(i,t) = rolling mean of d-day forward return / σ(i,t)
    """
    E_norm = {}
    valid_signals = [s for s in signals if s in best_horizon]

    for sig_name in valid_signals:
        h  = int(best_horizon[sig_name])
        ev = {}
        for t in universe:
            if t not in close.columns:
                continue
            fwd   = close[t].pct_change(h).shift(-h)
            e_raw = fwd.rolling(d_lookback).mean()
            ev[t] = e_raw / sigma[sig_name][t]
        E_norm[sig_name] = pd.DataFrame(ev)

    return E_norm


# =============================================================================
# Step 9 — Residual Regression
# =============================================================================

def step9_residual_regression(
    E_norm:      Dict[str, pd.DataFrame],
    Lambda_hist: Dict[str, pd.DataFrame],
    universe:    List[str],
) -> Tuple[Dict[str, Dict[str, pd.Series]], pd.DataFrame]:
    """
    Step 9: Extract independent contribution of each signal via OLS.
    Regress E_norm on Lambda_hist. Residual ε = independent edge.

    Returns:
        epsilon       — dict[signal][ticker] → pd.Series of residuals
        regression_df — DataFrame with Beta, R2, N, Eps_std per signal×ticker
    """
    epsilon        = {}
    regression_log = []

    for sig_name in E_norm:
        eps_per_ticker = {}
        for t in universe:
            try:
                lam    = Lambda_hist[t][sig_name].dropna() if sig_name in Lambda_hist.get(t, pd.DataFrame()).columns else pd.Series(dtype=float)
                e      = E_norm[sig_name][t].dropna() if t in E_norm[sig_name].columns else pd.Series(dtype=float)
                common = lam.index.intersection(e.index)

                if len(common) < 30:
                    eps_per_ticker[t] = pd.Series(dtype=float)
                    continue

                lam_c = lam.loc[common].values.reshape(-1, 1)
                e_c   = e.loc[common].values
                reg   = LinearRegression(fit_intercept=False)
                reg.fit(lam_c, e_c)
                resid = e_c - reg.predict(lam_c)

                eps_per_ticker[t] = pd.Series(resid, index=common)
                regression_log.append({
                    'Signal' : sig_name,
                    'Ticker' : t,
                    'Beta'   : round(reg.coef_[0], 6),
                    'R2'     : round(reg.score(lam_c, e_c), 6),
                    'N'      : len(common),
                    'Eps_std': round(resid.std(), 6),
                })
            except Exception as ex:
                eps_per_ticker[t] = pd.Series(dtype=float)

        epsilon[sig_name] = eps_per_ticker

    reg_df = pd.DataFrame(regression_log) if regression_log else pd.DataFrame(
        columns=['Signal', 'Ticker', 'Beta', 'R2', 'N', 'Eps_std']
    )
    return epsilon, reg_df


# =============================================================================
# Steps 10-11 — Signal Weights
# =============================================================================

def _rank_normalize(series: pd.Series) -> pd.Series:
    """Map series to percentile rank [0, 1]."""
    if len(series) == 0:
        return series
    return pd.Series(rankdata(series) / len(series), index=series.index)


def compute_weights_for_regime(
    regime_mask:              pd.Series,
    label:                    str,
    epsilon:                  Dict[str, Dict[str, pd.Series]],
    sigma:                    Dict[str, Dict[str, float]],
    universe:                 List[str],
    keep_signals:             List[str],
    close_index:              pd.Index,
    ticker_signal_overrides:  Dict[Tuple[str, str, str], int],
) -> pd.DataFrame:
    """
    Steps 10-11: Compute normalized signal weights for a given regime.

    Fixes from v2.x:
        v2.1 — culled signals receive w=0
        v2.2 — ε rank-normalized before weight computation
        v2.2 — TICKER_SIGNAL_OVERRIDES map applied after normalization
    """
    weight_log = []

    for sig_name in epsilon:
        for t in universe:

            # Step 10 Fix 1: zero weight for culled signals
            if sig_name not in keep_signals:
                weight_log.append({
                    'Signal': sig_name, 'Ticker': t, 'Regime': label,
                    'w_raw': 0.0, 'w_norm': 0.0, 'culled': True
                })
                continue

            eps_series = epsilon[sig_name].get(t, pd.Series(dtype=float))
            if len(eps_series) == 0:
                weight_log.append({
                    'Signal': sig_name, 'Ticker': t, 'Regime': label,
                    'w_raw': np.nan, 'w_norm': np.nan, 'culled': False
                })
                continue

            regime_dates = close_index[regime_mask.reindex(close_index).fillna(False)]
            eps_regime   = eps_series[eps_series.index.isin(regime_dates)]

            if len(eps_regime) < 10:
                w_raw = 0.0
            else:
                # Step 10 Fix 2: rank-normalize ε
                eps_ranked = _rank_normalize(eps_regime)
                w_raw      = eps_ranked.mean() / sigma[sig_name][t]

            # Step 10 Fix 3: apply sign override
            override_sign = ticker_signal_overrides.get((sig_name, t, label), +1)
            w_raw = override_sign * abs(w_raw) if w_raw != 0 else 0.0

            weight_log.append({
                'Signal': sig_name, 'Ticker': t, 'Regime': label,
                'w_raw': w_raw, 'w_norm': np.nan, 'culled': False
            })

    df = pd.DataFrame(weight_log)

    # Step 11: normalize per ticker, non-culled only
    def normalize(group):
        group = group.copy()
        total = group.loc[~group['culled'], 'w_raw'].abs().sum()
        group['w_norm'] = group['w_raw'].apply(
            lambda x: x / total if total > 0 else 0.0
        )
        return group

    return df.groupby('Ticker', group_keys=False).apply(normalize)


def compute_all_weights(
    epsilon:                 Dict[str, Dict[str, pd.Series]],
    sigma:                   Dict[str, Dict[str, float]],
    close:                   pd.DataFrame,
    universe:                List[str],
    keep_signals:            List[str],
    ticker_signal_overrides: Dict[Tuple[str, str, str], int],
    vix_threshold:           float = 20.0,
    tnx_threshold:           float = 4.5,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """
    Compute weights for both active and risk-off regimes.
    Select current regime based on latest VIX and TNX values.

    Returns:
        weights_active   — weight DataFrame for active regime
        weights_risk_off — weight DataFrame for risk-off regime
        weights_current  — weight DataFrame for current regime
        current_regime   — 'active' or 'risk_off'
    """
    latest_vix = close['VIX'].dropna().iloc[-1]
    latest_tnx = close['TNX'].dropna().iloc[-1]
    current_regime = (
        'active' if (latest_vix < vix_threshold and latest_tnx < tnx_threshold)
        else 'risk_off'
    )

    print(f'VIX: {latest_vix:.2f}  TNX: {latest_tnx:.2f}%  →  Regime: {current_regime.upper()}')

    active_mask   = (close['VIX'] < vix_threshold) & (close['TNX'] < tnx_threshold)
    risk_off_mask = ~active_mask

    weights_active = compute_weights_for_regime(
        active_mask, 'active', epsilon, sigma, universe,
        keep_signals, close.index, ticker_signal_overrides
    )
    weights_risk_off = compute_weights_for_regime(
        risk_off_mask, 'risk_off', epsilon, sigma, universe,
        keep_signals, close.index, ticker_signal_overrides
    )

    weight_df       = pd.concat([weights_active, weights_risk_off], ignore_index=True)
    weights_current = weight_df[weight_df['Regime'] == current_regime].copy()

    return weights_active, weights_risk_off, weights_current, current_regime


# =============================================================================
# Mega-Alpha
# =============================================================================

def compute_mega_alpha(
    signals:                 Dict[str, pd.DataFrame],
    weights_current:         pd.DataFrame,
    close:                   pd.DataFrame,
    universe:                List[str],
    current_regime:          str,
    ticker_signal_overrides: Dict[Tuple[str, str, str], int],
) -> pd.DataFrame:
    """
    Weighted combination of all KEEP signals → daily mega-alpha score per ticker.
    Positive = bullish composite. Negative = bearish composite.
    Sign overrides applied from TICKER_SIGNAL_OVERRIDES per current regime.
    """
    mega_alpha = {}

    for t in universe:
        w_t = (weights_current[
                   (weights_current['Ticker'] == t) &
                   (~weights_current['culled'])
               ].set_index('Signal')['w_norm'])

        score = pd.Series(0.0, index=close.index)
        for sig_name, w in w_t.items():
            if sig_name not in signals or t not in signals[sig_name].columns:
                continue
            sig_vals      = signals[sig_name][t].reindex(close.index).copy()
            override_sign = ticker_signal_overrides.get((sig_name, t, current_regime), +1)
            sig_vals      = override_sign * sig_vals
            score         = score + w * sig_vals

        mega_alpha[t] = score

    return pd.DataFrame(mega_alpha)


# =============================================================================
# Regime-Conditional IC
# =============================================================================

def compute_regime_ic(
    signals:       Dict[str, pd.DataFrame],
    close:         pd.DataFrame,
    universe:      List[str],
    keep_signals:  List[str],
    vix_threshold: float = 20.0,
    tnx_threshold: float = 4.5,
    horizon:       int   = 21,
) -> pd.DataFrame:
    """
    Split sample by VIX and TNX regime, compute IC per split.
    Shows how signal edge varies across macro environments.

    Returns DataFrame: Regime, Signal, Ticker, IC, p_value, N, Sig
    """
    regimes = {
        'VIX_Low (risk-on)'  : close['VIX'] <  vix_threshold,
        'VIX_High (risk-off)': close['VIX'] >= vix_threshold,
        'TNX_Low (<4.5%)'    : close['TNX'] <  tnx_threshold,
        'TNX_High (>=4.5%)' : close['TNX'] >= tnx_threshold,
    }

    rows = []
    for regime_name, mask in regimes.items():
        for sig_name in keep_signals:
            if sig_name not in signals:
                continue
            sig_df = signals[sig_name]
            for t in universe:
                if t not in sig_df.columns or t not in close.columns:
                    continue
                fwd      = close[t].pct_change(horizon).shift(-horizon)
                sig_vals = sig_df[t]
                df       = pd.concat([sig_vals, fwd], axis=1).dropna()
                df.columns = ['signal', 'fwd']
                df_regime  = df[mask.reindex(df.index).fillna(False)]

                if len(df_regime) < 20:
                    continue

                ic, pval = spearmanr(df_regime['signal'], df_regime['fwd'])
                rows.append({
                    'Regime' : regime_name,
                    'Signal' : sig_name,
                    'Ticker' : t,
                    'IC'     : round(float(ic), 4),
                    'p_value': round(float(pval), 4),
                    'N'      : len(df_regime),
                    'Sig'    : pval < 0.05,
                })

    return pd.DataFrame(rows)


# =============================================================================
# Full Pipeline Runner
# =============================================================================

def run_pipeline(
    signals:                 Dict[str, pd.DataFrame],
    close:                   pd.DataFrame,
    universe:                List[str],
    keep_signals:            List[str],
    ticker_signal_overrides: Dict[Tuple[str, str, str], int],
    horizons:                List[int]   = [1, 3, 5, 10, 21],
    d_lookback:              int         = 21,
    vix_threshold:           float       = 20.0,
    tnx_threshold:           float       = 4.5,
    verbose:                 bool        = True,
) -> dict:
    """
    Run the full 11-step pipeline end to end.
    Returns a results dict with all intermediate outputs.
    """
    if verbose:
        print('=== Running Signal Engine Pipeline ===')

    # Step 1 — IC baseline
    if verbose: print('Step 1: IC baseline...')
    ic_df       = run_ic_baseline(signals, close, universe, horizons)
    ic_summary  = summarize_ic(ic_df)
    best_horizon = ic_summary.set_index('Signal')['Optimal_Horizon'].to_dict()
    valid_signals = [s for s in signals if s in best_horizon]

    # Steps 2-7 — preprocessing
    if verbose: print('Steps 2-7: Signal preprocessing...')
    X           = step2_demean(signals)
    sigma2, sigma = step3_variance(X, universe)
    Y           = step4_standardize(X, sigma, universe)
    Y_hist      = step5_drop_recent(Y)
    Lambda      = step6_cross_sectional_demean(Y_hist, universe)
    Lambda_hist = step7_drop_final(Lambda)

    # Step 8 — expected return
    if verbose: print('Step 8: Expected forward return...')
    E_norm = step8_expected_return(
        {k: signals[k] for k in valid_signals},
        close, universe, sigma, best_horizon, d_lookback
    )

    # Step 9 — residual regression
    if verbose: print('Step 9: Residual regression...')
    epsilon, reg_df = step9_residual_regression(E_norm, Lambda_hist, universe)

    # Steps 10-11 — weights
    if verbose: print('Steps 10-11: Computing weights...')
    weights_active, weights_risk_off, weights_current, current_regime = compute_all_weights(
        epsilon, sigma, close, universe, keep_signals,
        ticker_signal_overrides, vix_threshold, tnx_threshold
    )

    # Mega-alpha
    if verbose: print('Computing mega-alpha...')
    mega_alpha_df = compute_mega_alpha(
        signals, weights_current, close, universe,
        current_regime, ticker_signal_overrides
    )

    # Regime IC
    if verbose: print('Computing regime-conditional IC...')
    regime_ic_df = compute_regime_ic(
        signals, close, universe, keep_signals, vix_threshold, tnx_threshold
    )

    if verbose: print('Pipeline complete.')

    return {
        'ic_df':          ic_df,
        'ic_summary':     ic_summary,
        'best_horizon':   best_horizon,
        'sigma':          sigma,
        'epsilon':        epsilon,
        'reg_df':         reg_df,
        'weights_active': weights_active,
        'weights_risk_off': weights_risk_off,
        'weights_current':  weights_current,
        'current_regime': current_regime,
        'mega_alpha_df':  mega_alpha_df,
        'regime_ic_df':   regime_ic_df,
    }
