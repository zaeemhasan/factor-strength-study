"""
config.py — Signal Engine v3.0
Single source of truth for all parameters, universes, and overrides.
No logic. No imports beyond typing. Import this everywhere.

Migration notes:
  - PHOTONICS alias removed. Use UNIVERSE everywhere.
  - Bollinger_Pct_B removed from KEEP_SIGNALS (BUG-02 resolved).
  - TICKER_SIGNAL_OVERRIDES cleared for unvalidated universes.
  - All magic numbers now named, typed, and documented.
"""

from typing import Dict, List, Tuple


# =============================================================================
# API KEYS — edit here only
# =============================================================================

FMP_API_KEY          = 'dQtyIChrt771K8IKgpm7C9DPRIqbZzVj'    # financialmodelingprep.com
FRED_API_KEY         = '739346a4b8a38dcf8ab2f6d4d3fef380'     # fred.stlouisfed.org
POLYGON_REST_API_KEY = 'Jfw_iVQvmga6eKI9aOSYleEsVfZtCGbZ'    # massive.com REST API key

# Schwab Developer API — not yet activated
# Register at: https://developer.schwab.com
# After registration paste credentials below.
SCHWAB_CLIENT_ID     = ''
SCHWAB_CLIENT_SECRET = ''
SCHWAB_REDIRECT_URI  = 'https://127.0.0.1'   # must match app registration exactly

# Derived availability flags
POLYGON_AVAILABLE = bool(POLYGON_REST_API_KEY)
SCHWAB_AVAILABLE  = bool(SCHWAB_CLIENT_ID and SCHWAB_CLIENT_SECRET)
FMP_AVAILABLE     = bool(FMP_API_KEY)
FRED_AVAILABLE    = bool(FRED_API_KEY)


# =============================================================================
# STUDY LOG — universe registry
# =============================================================================
# Gate requirements before running any universe:
#   1. N_eff / N > 0.50 (correlation diagnostic)
#   2. Each ticker has one-sentence business model description
#   3. Minimum 3yr clean OHLCV, <5% gaps
#   4. TICKER_SIGNAL_OVERRIDES starts empty — populate after IC run
#   5. Baseline IR documented after first run

STUDY_LOG: Dict[str, List[str]] = {

    # ── Thesis 1: Power Grid & Grid Modernization ─────────────────────────────
    # Status: COMPLETED v2.5 | Top signals: YieldCurve_Slope, CreditSpread
    'power-grid': [
        'ETN',  'EMR',  'HUBB', 'GEV',
        'PWR',  'MYR',  'AES',  'AME',
    ],

    # ── Thesis 2: AI Compute Silicon ─────────────────────────────────────────
    # Status: PARTIAL v2.3 | SMA200 overrides populated
    'ai-compute-silicon': [
        'NVDA', 'AMD',  'AVGO', 'MRVL',
    ],

    # ── Thesis 2b: AI Data Center Infrastructure ──────────────────────────────
    # Status: PENDING | Run correlation diagnostic first
    'ai-dc-infrastructure': [
        'VRT',  'SMCI', 'AAON', 'EQIX', 'DLR',
    ],

    # ── Thesis 3: Defense Technology & Rearmament ─────────────────────────────
    # Status: PENDING
    # Note: KTOS also in autonomous-robotics — clear overrides between runs
    'defense-tech': [
        'LMT',  'RTX',  'NOC',  'LHX',
        'KTOS', 'AVAV', 'PLTR', 'BAESY',
    ],

    # ── Thesis 4: Nuclear Energy ──────────────────────────────────────────────
    # Status: PENDING
    'nuclear-operators': [
        'CEG',  'VST',  'ETR',  'BWXT',
    ],
    'uranium-supply': [
        'CCJ',  'UEC',  'NXE',  'URA',
    ],

    # ── Thesis 5: Semiconductor Supply Chain ──────────────────────────────────
    # Status: PENDING | Priority universe — ASML propagation signal applicable
    'semi-supply-chain': [
        'AMAT', 'LRCX', 'KLAC', 'ASML',
        'AMKR', 'ENTG', 'MKSI', 'COHU',
    ],

    # ── Thesis 6: Autonomous & Robotic Systems ────────────────────────────────
    # Status: PENDING | KTOS overlap with defense-tech — isolate overrides
    'autonomous-robotics': [
        'ROK',  'BRKS', 'KTOS', 'AVAV',
        'QCOM', 'ABB',
    ],

    # ── Thesis 7: Sovereign AI ────────────────────────────────────────────────
    # Status: PENDING | Flagged heterogeneous — run correlation diagnostic first
    'sovereign-ai': [
        'EQIX', 'NVDA', 'SMCI', 'ASTS', 'VSAT',
    ],

    # ── Photonics (legacy development universe) ───────────────────────────────
    # Status: COMPLETED v2.1 | Full factor strength study published
    'photonics': [
        'AAOI', 'COHR', 'AEHR', 'LITE', 'IPGP',
    ],

    # ── Watch list — NOT engine-ready ─────────────────────────────────────────
    # Pre-revenue / low float. Excluded from all IC runs.
    'watch-speculative': [
        'OKLO', 'NNE',  'RCAT', 'MVIS', 'ACHR',
    ],
}

# Active study — change this line to switch universes
STUDY_NAME: str = 'power-grid'
UNIVERSE:   List[str] = STUDY_LOG[STUDY_NAME]


# =============================================================================
# DATA PARAMETERS
# =============================================================================

START = '2022-01-01'
END   = None   # None = today

# Macro and credit tickers always pulled alongside universe
MACRO_TICKERS  = ['^VIX', '^SOX', '^TNX', 'USO', '^GSPC', 'QQQ']
CREDIT_TICKERS = ['HYG', 'LQD', '^IRX']

# FRED series IDs
FRED_SERIES = {
    'HY_OAS'      : 'BAMLH0A0HYM2',   # ICE BofA HY OAS spread (daily)
    'YieldCurve'  : 'T10Y2Y',           # 10Y-2Y yield curve slope (daily)
    'CPI'         : 'CPIAUCSL',         # CPI All Items (monthly)
    'CoreCPI'     : 'CPILFESL',         # Core CPI ex food & energy (monthly)
    'Breakeven5Y' : 'T5YIE',           # 5Y breakeven inflation rate (daily)
}

# Output folder (Google Drive)
# Updated per-study at runtime: FOLDER = BASE_FOLDER / STUDY_NAME
BASE_FOLDER = '/content/drive/MyDrive/factor-strength-study'


# =============================================================================
# SIGNAL CONSTRUCTION PARAMETERS
# =============================================================================
# Each parameter: current value | valid range | needs grid search | last validated

HORIZONS    = [1, 3, 5, 10, 21]   # forward return horizons (trading days)

VOL_WINDOW  = 10     # volume surge rolling mean window | range: 5-20 | no
SMA_WINDOW  = 200    # SMA distance window | 200 = convention | no
EMA_FAST    = 9      # EMA cross fast window | range: 5-13 | no
EMA_SLOW    = 21     # EMA cross slow window | range: 15-30 | no
BB_WINDOW   = 20     # Bollinger band window | removed from KEEP | no
BB_STD      = 2.0    # Bollinger band std multiplier | convention | no

# Massive (Polygon) — Tier 7
VWAP_LOOKBACK_DAYS = 480   # 1-min bar history to pull (~2yr free tier) | no
VWAP_SLOPE_WINDOW  = 78    # bars for slope regression (78 x 1min ≈ intraday) | YES grid search
PC_RATIO_LOOKBACK  = 252   # trading days of P/C history | no

# Short interest — Tier 3
SI_GATE = 0.10   # >10% float short = elevated | range: 0.05-0.20 | no

# Earnings revisions — Tier 4
REVISION_LOOKBACK = 63   # trading days for revision trend | range: 42-90 | no


# =============================================================================
# COMBINATION ENGINE PARAMETERS
# =============================================================================
# All candidates for grid search in Phase 3 re-parameterization

D_LOOKBACK = 21      # Step 8 rolling window for expected return | range: 10-42 | YES

# Regime thresholds — currently arbitrary, not empirically optimized
# Grid search target: maximize out-of-sample IR across [15, 17.5, 20, 22.5, 25]
VIX_THRESHOLD = 20.0   # VIX above = risk-off | not grid searched yet

# Grid search target: maximize out-of-sample IR across [3.5, 4.0, 4.5, 5.0]
TNX_THRESHOLD = 4.5    # TNX above = high-rate | not grid searched yet


# =============================================================================
# CULLING THRESHOLDS
# =============================================================================

IC_MIN   = 0.03   # minimum mean |IC| for signal inclusion | range: 0.02-0.05 | YES
CORR_MAX = 0.70   # max signal-signal Spearman corr before redundancy flag | no
CORR_GATE = 0.85  # ticker-ticker redundancy gate (universe diagnostic) | no
CORR_WINDOW = 63  # trading days for recent correlation (~3 months) | no


# =============================================================================
# APPROVED SIGNALS — KEEP_SIGNALS
# =============================================================================
# Only signals in this list receive non-zero weight in the combination engine.
# Signals not listed receive w=0 (culled gate).
#
# Changes from v2.6:
#   REMOVED: Bollinger_Pct_B (redundant with Momentum_21d, corr=0.734) [BUG-02 resolved]
#   RETAINED: all others from v2.6
#
# New signal intake requirements (Phase 5 protocol):
#   1. Mean |IC| > IC_MIN on >= 2 universes or n > 30 quarters
#   2. Spearman corr with all existing KEEP signals < CORR_MAX
#   3. IC stable across VIX/TNX regime splits (or mechanism documented)
#   4. Data source, refresh frequency, and staleness documented
#   5. IR contribution estimate > 0.01 before adding

KEEP_SIGNALS: List[str] = [
    # Tier 1 — Price / Technical
    'SMA200_Distance',    # mean reversion | sign override required per ticker×regime
    'Momentum_21d',       # primary trend | strong AAOI, COHR, LITE | noise AEHR, IPGP
    'EMA_Cross_9_21',     # trend initiation | independent of Momentum_21d (corr=0.052)
    'Momentum_10d',       # secondary momentum | COHR, LITE only | partial redundancy with 21d
    'Volume_Surge',       # institutional participation | AEHR, LITE specific | genuinely independent

    # Tier 2 — Macro filters (not scored — regime gates only)
    'VIX_Regime',         # binary exposure gate | VIX > VIX_THRESHOLD = reduce exposure

    # Tier 5/6 — Credit & Macro
    'CreditSpread',       # risk appetite proxy | top signal power-grid study
    'YieldCurve_Slope',   # 10Y-2Y slope | top signal power-grid study | FRED preferred
    'YieldCurve_FRED',    # FRED version of yield curve | supersedes yfinance proxy
    'HY_OAS_FRED',        # ICE BofA HY OAS | cleaner than HYG/LQD proxy

    # Tier 7 — Massive (Polygon) — provisional, pending IC validation
    'VWAP_Slope',         # intraday accumulation signal | IC not yet validated | BUG-01 pending
    'PC_Ratio',           # options flow | IC not yet validated | free tier = snapshot only
]

# Signals under review — not in KEEP but tracked
REVIEW_SIGNALS: List[str] = [
    'Momentum_10d',       # partially redundant with 21d — monitor corr per universe
    'EPS_Revision_Dir',   # FMP data quality not validated against Bloomberg
    'EPS_Surprise_Avg',   # FMP data quality not validated against Bloomberg
    'SI_Momentum',        # interaction signal — depends on SI data recency
    'CPI_Regime',         # monthly signal — low frequency may limit IC
    'CoreCPI_Change',     # monthly signal — as above
    'Breakeven_Inflation',# daily FRED | not yet run on all universes
]


# =============================================================================
# TICKER-SIGNAL SIGN OVERRIDES
# =============================================================================
# Populated empirically after regime-conditional IC analysis.
# Format: (signal_name, ticker, regime) → sign multiplier (+1 or -1)
#
# Protocol:
#   - Clear all overrides when switching to a NEW universe not yet studied.
#   - Overrides only fire for tickers present in the active UNIVERSE.
#   - Evidence for each override stored in OVERRIDE_NOTES below.
#   - Do NOT carry overrides from one universe to another without IC evidence.
#
# Active overrides by study:

TICKER_SIGNAL_OVERRIDES: Dict[Tuple[str, str, str], int] = {

    # ── Photonics study (v2.1) ────────────────────────────────────────────────
    # LITE SMA200: continuation in active regime (IC=+0.263), reverts in risk-off (IC=-0.495)
    ('SMA200_Distance', 'LITE', 'risk_off'): -1,

    # ── AI Compute Silicon study (v2.3) ───────────────────────────────────────
    # SMA200 uniformly bearish for large-cap semis post-peak
    ('SMA200_Distance', 'NVDA', 'active'): -1,
    ('SMA200_Distance', 'AMD',  'active'): -1,
    ('SMA200_Distance', 'AVGO', 'active'): -1,
    ('SMA200_Distance', 'MRVL', 'active'): -1,
    ('SMA200_Distance', 'QCOM', 'active'): -1,

    # ── All other universes: no overrides until IC evidence gathered ──────────
}

# Evidence log — reference only, not used in computation
OVERRIDE_NOTES: Dict[Tuple[str, str, str], dict] = {
    ('SMA200_Distance', 'LITE', 'risk_off'): {
        'IC_active'  : +0.263,
        'IC_riskoff' : -0.495,
        'source'     : 'photonics v2.1',
        'note'       : 'Structural AI datacom uptrend = continuation active. Reverts at TNX>=4.5%.',
        'validated'  : '2026-04',
    },
    ('SMA200_Distance', 'NVDA', 'active'): {
        'IC_vix_low'  : +0.068,
        'IC_vix_high' : -0.274,
        'source'      : 'ai-compute-silicon v2.3',
        'note'        : 'Post-peak mean reversion in sample.',
        'validated'   : '2026-04',
    },
    ('SMA200_Distance', 'AVGO', 'active'): {
        'IC_vix_low'  : -0.267,
        'IC_vix_high' : -0.453,
        'source'      : 'ai-compute-silicon v2.3',
        'note'        : 'Strongest reversion in semis, consistent both regimes.',
        'validated'   : '2026-04',
    },
    ('SMA200_Distance', 'MRVL', 'active'): {
        'IC_vix_low'  : -0.346,
        'IC_vix_high' : -0.080,
        'source'      : 'ai-compute-silicon v2.3',
        'note'        : 'Strong active regime. Risk-off smaller sample.',
        'validated'   : '2026-04',
    },
    ('SMA200_Distance', 'AMD', 'active'): {
        'IC_vix_low'  : -0.054,
        'IC_vix_high' : -0.329,
        'source'      : 'ai-compute-silicon v2.3',
        'note'        : 'Directionally consistent. Clearer in risk-off.',
        'validated'   : '2026-04',
    },
    ('SMA200_Distance', 'QCOM', 'active'): {
        'IC_vix_low'  : -0.022,
        'IC_vix_high' : -0.355,
        'source'      : 'ai-compute-silicon v2.3',
        'note'        : 'Persistent negative mega-alpha. Sector rotation signal.',
        'validated'   : '2026-04',
    },
}


# =============================================================================
# SCHWAB / MASSIVE API ENDPOINTS
# =============================================================================

MASSIVE_BASE     = 'https://api.polygon.io'       # endpoint unchanged post-rebrand
SCHWAB_BASE      = 'https://api.schwabapi.com/marketdata/v1'
SCHWAB_AUTH_URL  = 'https://api.schwabapi.com/v1/oauth/authorize'
SCHWAB_TOKEN_URL = 'https://api.schwabapi.com/v1/oauth/token'


# =============================================================================
# KNOWN BUGS — carried forward from v2.6 FINAL
# =============================================================================
# BUG-01: VWAP/PC_Ratio datetime index mismatch on reindex.
#         Fix location: signals.py → build_polygon_signals()
#         Fix: convert series index to pd.to_datetime before reindex.
#
# BUG-02: Bollinger_Pct_B in KEEP_SIGNALS (v2.6 archive).
#         Resolved here: Bollinger_Pct_B not in v3 KEEP_SIGNALS.
