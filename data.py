"""
data.py — Signal Engine v3.0
All vendor API calls isolated here. No signal construction. No globals.
Each function takes explicit parameters and returns clean DataFrames.

Vendors:
    fetch_prices()       — yfinance OHLCV (universe + macro + credit)
    fetch_short_interest() — yfinance .info snapshot (monthly)
    fetch_fmp()          — Financial Modeling Prep (earnings estimates/surprises)
    fetch_fred()         — FRED API (credit, inflation, yield curve)
    fetch_massive_vwap() — Massive.com (formerly Polygon) 1-min bars → VWAP slope
    fetch_massive_pc()   — Massive.com options chain → P/C ratio snapshot
    schwab_authenticate()  — Schwab OAuth2 PKCE flow (stub — not yet activated)
    schwab_quote()         — Schwab real-time Level 1 quote
    schwab_price_history() — Schwab OHLCV history (daily, up to 10yr)
    schwab_account_positions() — Schwab live account positions
"""

import time
import requests
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings('ignore')


# =============================================================================
# yfinance — Price, Volume, Macro, Credit
# =============================================================================

def fetch_prices(
    universe:       List[str],
    macro_tickers:  List[str],
    credit_tickers: List[str],
    start:          str,
    end:            Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Pull OHLCV data for universe + macro + credit tickers via yfinance.

    Returns:
        close  — DataFrame(index=dates, columns=tickers), adjusted close
        volume — DataFrame(index=dates, columns=tickers)
        credit_close — DataFrame(index=dates, columns=credit tickers)
                       renamed for signal construction (HYG, LQD, IRX)
    """
    import yfinance as yf

    all_tickers = list(dict.fromkeys(universe + macro_tickers + credit_tickers))
    raw = yf.download(all_tickers, start=start, end=end,
                      auto_adjust=True, progress=False)

    close  = raw['Close'].copy()
    volume = raw['Volume'].copy()

    # Drop failed tickers
    nan_cols   = [c for c in close.columns if pd.isna(c)]
    empty_cols = close.columns[close.isna().all()].tolist()
    drop = nan_cols + empty_cols
    if drop:
        print(f'  Dropping {len(drop)} failed tickers: {drop}')
        close  = close.drop(columns=drop)
        volume = volume.drop(columns=drop)

    # Rename macro tickers to clean names
    rename = {'^VIX': 'VIX', '^SOX': 'SOX', '^TNX': 'TNX',
              '^GSPC': 'SPX', '^IRX': 'IRX'}
    close  = close.rename(columns=rename)
    volume = volume.rename(columns=rename)

    # Separate credit close for signal construction
    credit_rename = {'^IRX': 'IRX'}
    credit_cols   = [rename.get(c, c) for c in credit_tickers if rename.get(c, c) in close.columns]
    credit_close  = close[credit_cols].copy()

    # Validate universe loaded
    active_universe = [t for t in universe if t in close.columns]
    missing = [t for t in universe if t not in close.columns]
    if missing:
        print(f'  WARNING — tickers not loaded: {missing}')

    print(f'  Loaded: {len(active_universe)} universe | '
          f'{close.shape[0]} dates | '
          f'{close.index[0].date()} → {close.index[-1].date()}')

    return close, volume, credit_close


# =============================================================================
# yfinance — Short Interest (Tier 3)
# =============================================================================

def fetch_short_interest(universe: List[str]) -> pd.DataFrame:
    """
    Pull short interest snapshot from yfinance .info per ticker.
    Data is monthly, not daily — treat as a static signal at run time.

    Returns:
        DataFrame(index=tickers, columns=['shortPercentOfFloat',
                  'shortRatio', 'sharesShort', 'sharesOutstanding', 'floatShares'])
    """
    import yfinance as yf

    print('Pulling short interest (yfinance snapshot)...')
    si_data = {}
    for t in universe:
        try:
            info = yf.Ticker(t).info
            si_data[t] = {
                'sharesShort'          : info.get('sharesShort',          np.nan),
                'sharesOutstanding'    : info.get('sharesOutstanding',    np.nan),
                'shortRatio'           : info.get('shortRatio',           np.nan),
                'shortPercentOfFloat'  : info.get('shortPercentOfFloat',  np.nan),
                'floatShares'          : info.get('floatShares',          np.nan),
            }
            pct   = si_data[t]['shortPercentOfFloat']
            ratio = si_data[t]['shortRatio']
            pct_str   = f'{pct*100:.1f}%' if pct and not np.isnan(pct) else 'n/a'
            ratio_str = f'{ratio:.1f}d'    if ratio and not np.isnan(ratio) else 'n/a'
            print(f'  {t}: SI%={pct_str}  DaysToCover={ratio_str}')
        except Exception as e:
            si_data[t] = {}
            print(f'  {t}: SI failed ({e})')

    return pd.DataFrame(si_data).T


# =============================================================================
# Financial Modeling Prep — Earnings Revisions (Tier 4)
# =============================================================================

def fetch_fmp(
    universe:  List[str],
    api_key:   str,
    lookback:  int = 63,
) -> Dict[str, dict]:
    """
    Pull analyst estimates and earnings surprises from FMP free tier.
    Rate limit: 250 calls/day on free tier.

    Returns:
        dict keyed by ticker → {'estimates': [...], 'surprises': [...]}
        Empty lists if API unavailable or ticker not found.
    """
    if not api_key:
        print('FMP_API_KEY not set — skipping Tier 4.')
        return {t: {'estimates': [], 'surprises': []} for t in universe}

    print('Pulling earnings estimate revisions (FMP)...')
    base     = 'https://financialmodelingprep.com/api/v3'
    fmp_data = {}

    for t in universe:
        try:
            r1 = requests.get(
                f'{base}/analyst-estimates/{t}?limit=8&apikey={api_key}',
                timeout=10
            )
            r2 = requests.get(
                f'{base}/earnings-surprises/{t}?apikey={api_key}',
                timeout=10
            )
            fmp_data[t] = {
                'estimates': r1.json()[:4] if isinstance(r1.json(), list) else [],
                'surprises': r2.json()[:4] if isinstance(r2.json(), list) else [],
            }
            print(f'  {t}: {len(fmp_data[t]["estimates"])} estimates, '
                  f'{len(fmp_data[t]["surprises"])} surprises')
        except Exception as e:
            fmp_data[t] = {'estimates': [], 'surprises': []}
            print(f'  {t}: FMP failed ({e})')

    return fmp_data


# =============================================================================
# FRED API — Credit & Macro (Tier 6)
# =============================================================================

def fetch_fred(
    series_map: Dict[str, str],
    api_key:    str,
    start:      str,
) -> Dict[str, pd.Series]:
    """
    Pull named FRED series.

    Args:
        series_map — {'name': 'FRED_SERIES_ID', ...}
        api_key    — FRED API key
        start      — start date string 'YYYY-MM-DD'

    Returns:
        dict keyed by name → pd.Series(index=dates, values=float)
        Empty Series for any failed pull.
    """
    if not api_key:
        print('FRED_API_KEY not set — skipping Tier 6.')
        return {name: pd.Series(dtype=float) for name in series_map}

    from fredapi import Fred
    fred      = Fred(api_key=api_key)
    fred_data = {}

    print('Pulling FRED data...')
    for name, series_id in series_map.items():
        try:
            s = fred.get_series(series_id, observation_start=start)
            fred_data[name] = s
            print(f'  {name} ({series_id}): {len(s)} obs | '
                  f'latest={s.index[-1].date()} val={s.iloc[-1]:.4f}')
        except Exception as e:
            fred_data[name] = pd.Series(dtype=float)
            print(f'  {name}: FRED failed ({e})')

    return fred_data


# =============================================================================
# Massive.com (formerly Polygon.io) — Intraday VWAP Slope (Tier 7)
# =============================================================================

def fetch_massive_vwap(
    universe:      List[str],
    api_key:       str,
    lookback_days: int = 480,
    slope_window:  int = 78,
    rate_limit:    float = 0.12,
) -> Dict[str, pd.Series]:
    """
    Pull 1-minute aggregate bars from Massive.com and compute daily VWAP slope.

    VWAP slope = linear regression slope of (price - VWAP) / VWAP
                 over the last `slope_window` bars of each session.
    Positive slope = price trending above VWAP = institutional accumulation.

    Free tier: 2yr of 1-min bars, 15min delayed live.
    Endpoint: api.polygon.io (unchanged post Massive rebrand).

    BUG-01 FIX: Index converted to datetime64 before return to avoid
    TypeError on reindex against daily close index.

    Returns:
        dict keyed by ticker → pd.Series(index=pd.DatetimeIndex, values=slope)
    """
    from sklearn.linear_model import LinearRegression
    from polygon import RESTClient

    if not api_key:
        print('POLYGON_REST_API_KEY not set — skipping VWAP slope.')
        return {t: pd.Series(dtype=float) for t in universe}

    print('=== Tier 7A: Massive VWAP Slope Pull ===')
    poly      = RESTClient(api_key=api_key)
    end_dt    = datetime.today()
    start_dt  = end_dt - timedelta(days=int(lookback_days * 1.4))
    start_str = start_dt.strftime('%Y-%m-%d')
    end_str   = end_dt.strftime('%Y-%m-%d')

    vwap_slope_data = {}

    for t in universe:
        print(f'  {t}...', end=' ', flush=True)
        try:
            bars = []
            for agg in poly.list_aggs(
                ticker=t, multiplier=1, timespan='minute',
                from_=start_str, to=end_str,
                adjusted=True, limit=50000,
            ):
                bars.append({
                    'ts':     pd.Timestamp(agg.timestamp, unit='ms', tz='US/Eastern'),
                    'high':   agg.high,
                    'low':    agg.low,
                    'close':  agg.close,
                    'volume': agg.volume,
                    'vwap':   getattr(agg, 'vwap', None),
                })

            if not bars:
                print('no data')
                vwap_slope_data[t] = pd.Series(dtype=float)
                continue

            df       = pd.DataFrame(bars).set_index('ts').sort_index()
            df['pv'] = ((df['high'] + df['low'] + df['close']) / 3) * df['volume']
            df['date'] = df.index.date

            daily_slopes = {}
            for date, session in df.groupby('date'):
                if len(session) < slope_window:
                    continue
                session      = session.copy()
                cum_pv       = session['pv'].cumsum()
                cum_vol      = session['volume'].cumsum()
                session['vwap_calc'] = cum_pv / cum_vol.replace(0, np.nan)
                vwap_col     = 'vwap' if session['vwap'].notna().any() else 'vwap_calc'
                session['dist'] = (
                    (session['close'] - session[vwap_col]) / session[vwap_col]
                )
                tail = session['dist'].dropna().tail(slope_window).values
                if len(tail) < 10:
                    continue
                x     = np.arange(len(tail)).reshape(-1, 1)
                slope = LinearRegression().fit(x, tail).coef_[0]
                daily_slopes[pd.Timestamp(date)] = slope   # BUG-01 FIX: Timestamp not date

            # BUG-01 FIX: ensure DatetimeIndex dtype
            s = pd.Series(daily_slopes).sort_index()
            s.index = pd.to_datetime(s.index)
            vwap_slope_data[t] = s

            print(f'{len(daily_slopes)} sessions')
            time.sleep(rate_limit)

        except Exception as e:
            print(f'ERROR: {e}')
            vwap_slope_data[t] = pd.Series(dtype=float)

    return vwap_slope_data


# =============================================================================
# Massive.com — Daily Put/Call Ratio Snapshot (Tier 7)
# =============================================================================

def fetch_massive_pc(
    universe:   List[str],
    api_key:    str,
    base_url:   str = 'https://api.polygon.io',
    rate_limit: float = 0.12,
) -> Dict[str, pd.Series]:
    """
    Pull today's put/call ratio snapshot per ticker from Massive.com options endpoint.

    Free tier: current-day snapshot only. Historical P/C requires paid tier.
    Returns a single-point Series per ticker (today's date → P/C ratio).

    BUG-01 FIX: Index set to pd.Timestamp (datetime64 compatible).

    Returns:
        dict keyed by ticker → pd.Series(index=[today_timestamp], values=[pc_ratio])
        Empty Series if options data unavailable (may require Starter plan).
    """
    if not api_key:
        print('POLYGON_REST_API_KEY not set — skipping P/C ratio.')
        return {t: pd.Series(dtype=float) for t in universe}

    print('=== Tier 7B: Massive P/C Ratio Snapshot ===')
    today       = pd.Timestamp.today().normalize()
    pc_ratio_data = {}

    for t in universe:
        try:
            resp = requests.get(
                f'{base_url}/v3/snapshot/options/{t}',
                params={'apiKey': api_key, 'limit': 250},
                timeout=10,
            )
            data = resp.json()

            if resp.status_code != 200 or 'results' not in data:
                pc_ratio_data[t] = pd.Series(dtype=float)
                print(f'  {t}: no options data (may require Starter plan)')
                continue

            puts  = sum(1 for r in data['results']
                        if r.get('details', {}).get('contract_type') == 'put')
            calls = sum(1 for r in data['results']
                        if r.get('details', {}).get('contract_type') == 'call')
            pc    = puts / calls if calls > 0 else np.nan

            # BUG-01 FIX: use pd.Timestamp not datetime.date
            s = pd.Series({today: pc})
            s.index = pd.to_datetime(s.index)
            pc_ratio_data[t] = s

            print(f'  {t}: P/C={pc:.3f}  (puts={puts}, calls={calls})')
            time.sleep(rate_limit)

        except Exception as e:
            print(f'  {t}: ERROR {e}')
            pc_ratio_data[t] = pd.Series(dtype=float)

    return pc_ratio_data


# =============================================================================
# Schwab Developer API — Stubs (Tier 8)
# =============================================================================

_schwab_token: Optional[str] = None


def schwab_authenticate(
    client_id:     str,
    client_secret: str,
    redirect_uri:  str,
    auth_url:      str,
    token_url:     str,
) -> Optional[str]:
    """
    OAuth2 PKCE flow for Schwab API.
    NOT YET ACTIVE — requires registered app at developer.schwab.com.

    Steps:
        1. Prints authorization URL — open in browser
        2. User logs in, redirected to redirect_uri?code=...
        3. Paste the code when prompted
        4. Exchanges code for access token (valid ~30min)

    Returns:
        access token string, or None on failure
    """
    import base64, urllib.parse

    if not client_id or not client_secret:
        print('Schwab not configured.')
        print('Register at developer.schwab.com, then set SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET in config.py.')
        return None

    auth_params = {
        'response_type': 'code',
        'client_id':     client_id,
        'redirect_uri':  redirect_uri,
    }
    url = auth_url + '?' + urllib.parse.urlencode(auth_params)
    print(f'Open this URL to authorize:\n{url}')
    code = input('Paste the authorization code from the redirect URL: ').strip()

    creds = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    resp  = requests.post(token_url, headers={
        'Authorization': f'Basic {creds}',
        'Content-Type':  'application/x-www-form-urlencoded',
    }, data={
        'grant_type':   'authorization_code',
        'code':         code,
        'redirect_uri': redirect_uri,
    })

    if resp.status_code == 200:
        global _schwab_token
        _schwab_token = resp.json()['access_token']
        print('Schwab authenticated.')
        return _schwab_token
    else:
        print(f'Auth failed: {resp.status_code} {resp.text}')
        return None


def schwab_quote(ticker: str, base_url: str, token: Optional[str] = None) -> dict:
    """
    Real-time Level 1 quote for a ticker via Schwab.
    Use for live signal monitoring — not for IC backtesting.

    Returns dict with keys: bid, ask, last, volume, mark
    Returns empty dict if no token or request fails.
    """
    tok = token or _schwab_token
    if not tok:
        print('No Schwab token. Run schwab_authenticate() first.')
        return {}

    resp = requests.get(
        f'{base_url}/quotes',
        headers={'Authorization': f'Bearer {tok}'},
        params={'symbols': ticker, 'fields': 'quote'},
        timeout=10,
    )
    if resp.status_code == 200:
        q = resp.json().get(ticker, {}).get('quote', {})
        return {
            'bid':    q.get('bidPrice'),
            'ask':    q.get('askPrice'),
            'last':   q.get('lastPrice'),
            'volume': q.get('totalVolume'),
            'mark':   q.get('mark'),
        }
    print(f'Schwab quote error {resp.status_code}: {resp.text[:200]}')
    return {}


def schwab_price_history(
    ticker:      str,
    base_url:    str,
    period_type: str = 'year',
    period:      int = 2,
    freq_type:   str = 'daily',
    freq:        int = 1,
    token:       Optional[str] = None,
) -> pd.DataFrame:
    """
    OHLCV price history from Schwab.
    Provides up to 10yr daily bars or ~48 days of 1-min bars.
    NOTE: No historical options data — use Massive for IC backtesting.

    Returns DataFrame(index=dates, columns=[open,high,low,close,volume])
    """
    tok = token or _schwab_token
    if not tok:
        print('No Schwab token.')
        return pd.DataFrame()

    resp = requests.get(
        f'{base_url}/pricehistory',
        headers={'Authorization': f'Bearer {tok}'},
        params={
            'symbol':               ticker,
            'periodType':           period_type,
            'period':               period,
            'frequencyType':        freq_type,
            'frequency':            freq,
            'needExtendedHoursData': False,
        },
        timeout=15,
    )
    if resp.status_code == 200:
        candles = resp.json().get('candles', [])
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles)
        df['date'] = pd.to_datetime(df['datetime'], unit='ms')
        return df.set_index('date')[['open','high','low','close','volume']].sort_index()

    print(f'Schwab history error {resp.status_code}: {resp.text[:200]}')
    return pd.DataFrame()


def schwab_account_positions(
    token:    Optional[str] = None,
) -> List[dict]:
    """
    Live account positions from Schwab.
    Returns list of dicts: symbol, quantity, avg_price, market_value.
    """
    tok = token or _schwab_token
    if not tok:
        print('No Schwab token.')
        return []

    resp = requests.get(
        'https://api.schwabapi.com/trader/v1/accounts',
        headers={'Authorization': f'Bearer {tok}'},
        params={'fields': 'positions'},
        timeout=10,
    )
    if resp.status_code == 200:
        positions = []
        for acct in resp.json():
            for pos in acct.get('securitiesAccount', {}).get('positions', []):
                positions.append({
                    'symbol':       pos['instrument']['symbol'],
                    'quantity':     pos['longQuantity'],
                    'avg_price':    pos['averagePrice'],
                    'market_value': pos['marketValue'],
                })
        return positions

    print(f'Schwab positions error {resp.status_code}: {resp.text[:200]}')
    return []
