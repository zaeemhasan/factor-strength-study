# Signal Engine v3 — Platform Migration

## Status: Phase 1 Complete (Structural Decomposition)

Migration from monolithic notebook (`signal_engine_v2_6_FINAL.ipynb`) to modular Python package.

## File Structure

```
v3/
├── config.py    — All parameters, universes, overrides. Single source of truth.
├── data.py      — All vendor API calls. yfinance, FRED, FMP, Massive, Schwab.
├── signals.py   — All signal construction functions. Stateless.
├── engine.py    — 11-step combination pipeline. Stateless.
└── app.py       — Streamlit UI. Phase 6 stub — not yet implemented.
```

## Known Bugs Carried Forward

| ID | Description | Fix Location | Status |
|----|-------------|--------------|--------|
| BUG-01 | VWAP/PC_Ratio datetime index mismatch on reindex | signals.py `build_polygon_signals()` | **FIXED in v3** |
| BUG-02 | Bollinger_Pct_B in KEEP_SIGNALS | config.py KEEP_SIGNALS | **FIXED in v3** |

## Migration Protocol Phases

- [x] Phase 0 — Freeze & archive (`signal_engine_v2_6_FINAL.ipynb`)
- [x] Phase 1 — Structural decomposition (this directory)
- [ ] Phase 2 — Purge (validate on 2 universes, confirm clean runs)
- [ ] Phase 3 — Re-parameterization (grid search VIX/TNX thresholds)
- [ ] Phase 4 — New universe intake protocol
- [ ] Phase 5 — New signal intake protocol (Polygon IC validation)
- [ ] Phase 6 — Streamlit migration (app.py implementation)

## Quick Start (Colab)

```python
import sys
sys.path.insert(0, '/content/drive/MyDrive/factor-strength-study/v3')

from config import *
from data import fetch_prices, fetch_short_interest, fetch_fmp, fetch_fred
from data import fetch_massive_vwap, fetch_massive_pc
from signals import build_signals
from engine import run_pipeline

# Pull data
close, volume, credit_close = fetch_prices(UNIVERSE, MACRO_TICKERS, CREDIT_TICKERS, START)
si_df       = fetch_short_interest(UNIVERSE)
fmp_data    = fetch_fmp(UNIVERSE, FMP_API_KEY)
fred_data   = fetch_fred(FRED_SERIES, FRED_API_KEY, START)
vwap_data   = fetch_massive_vwap(UNIVERSE, POLYGON_REST_API_KEY)
pc_data     = fetch_massive_pc(UNIVERSE, POLYGON_REST_API_KEY)

# Build signals
signals = build_signals(
    close, volume, credit_close, si_df, fmp_data, fred_data,
    vwap_data, pc_data, UNIVERSE
)

# Run pipeline
results = run_pipeline(
    signals, close, UNIVERSE, KEEP_SIGNALS,
    TICKER_SIGNAL_OVERRIDES, HORIZONS, D_LOOKBACK,
    VIX_THRESHOLD, TNX_THRESHOLD
)

# Access outputs
print(results['ic_summary'])
print(results['current_regime'])
results['mega_alpha_df'].tail()
```

## API Keys

Set in `config.py`:
- `FMP_API_KEY` — financialmodelingprep.com
- `FRED_API_KEY` — fred.stlouisfed.org  
- `POLYGON_REST_API_KEY` — massive.com (formerly polygon.io)
- `SCHWAB_CLIENT_ID` / `SCHWAB_CLIENT_SECRET` — developer.schwab.com (pending registration)
