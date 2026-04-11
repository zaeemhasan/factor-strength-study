"""
app.py — Signal Engine v3.0
Streamlit UI — Phase 6 stub.

NOT YET IMPLEMENTED. Scaffold only.
Full implementation begins after:
    - Phase 1 (decomposition) validated on >= 2 universes
    - Phase 2 (purge) complete
    - Phase 3 (re-parameterization) complete
    - Polygon IC validation complete
    - Schwab API activated

To run when ready:
    cd v3/
    streamlit run app.py

Architecture:
    app.py     — UI layer only. Imports from engine.py and config.py.
    engine.py  — All computation. No UI calls.
    signals.py — All signal construction. No UI calls.
    data.py    — All vendor API calls. No UI calls.
    config.py  — All parameters. No logic.
"""

# ── Planned UI Structure ──────────────────────────────────────────────────────
#
# Sidebar:
#   - Universe selector (dropdown from config.STUDY_LOG)
#   - Date range picker
#   - VIX threshold slider (range 15.0-25.0, step 0.5)
#   - TNX threshold slider (range 3.0-6.0, step 0.25)
#   - Regime override toggle (force active / force risk-off / auto)
#   - Run button
#
# Main Panel — 3 tabs:
#   Tab 1: IC Summary
#       - Signal verdict table (KEEP / REVIEW / CULLED status)
#       - Mean |IC| bar chart by signal
#       - N_eff and IR estimate display
#
#   Tab 2: Mega-Alpha
#       - Per-ticker mega-alpha chart (last 60 days, bar chart green/red)
#       - Current regime badge (ACTIVE / RISK-OFF)
#       - Signal weight table for current universe
#
#   Tab 3: Regime Heatmap
#       - IC × regime heatmap (VIX_Low, VIX_High, TNX_Low, TNX_High)
#       - Override evidence table
#
# Bottom Panel:
#   - Run manifest (study name, date, regime, VIX, TNX)
#   - Export button → downloads all CSVs as zip
#
# ── Implementation placeholder ────────────────────────────────────────────────

raise NotImplementedError(
    "app.py is a Phase 6 stub. "
    "Complete Phases 1-5 of the migration protocol before implementing."
)

# ── When implementing, start with this skeleton ───────────────────────────────
#
# import streamlit as st
# import pandas as pd
# import matplotlib.pyplot as plt
# from config import STUDY_LOG, KEEP_SIGNALS, TICKER_SIGNAL_OVERRIDES
# from config import VIX_THRESHOLD, TNX_THRESHOLD
# from data import fetch_prices, fetch_short_interest, fetch_fmp, fetch_fred
# from data import fetch_massive_vwap, fetch_massive_pc
# from signals import build_signals
# from engine import run_pipeline
#
# st.set_page_config(page_title='Signal Engine v3', layout='wide')
#
# with st.sidebar:
#     study_name = st.selectbox('Universe', list(STUDY_LOG.keys()))
#     vix_thresh = st.slider('VIX Threshold', 15.0, 25.0, VIX_THRESHOLD, 0.5)
#     tnx_thresh = st.slider('TNX Threshold', 3.0, 6.0, TNX_THRESHOLD, 0.25)
#     run_button = st.button('Run Engine')
#
# if run_button:
#     with st.spinner('Pulling data...'):
#         universe = STUDY_LOG[study_name]
#         # ... fetch, build signals, run pipeline
#         results = run_pipeline(...)
#
#     tab1, tab2, tab3 = st.tabs(['IC Summary', 'Mega-Alpha', 'Regime Heatmap'])
#     with tab1:
#         st.dataframe(results['ic_summary'])
#     with tab2:
#         st.bar_chart(results['mega_alpha_df'].iloc[-60:])
#     with tab3:
#         # heatmap via matplotlib
#         pass
