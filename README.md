# Photonics IC Notebook: v2 → v2.1 Change Specification

**File:** `photonics_ic_analysis_v2.ipynb`  
**Output:** `photonics_ic_analysis_v2.1.ipynb`  
**Do not alter any cell not listed below.**

---

## Background (read before making changes)

This notebook computes Information Coefficients (IC) for trading signals
across 5 photonics stocks: AAOI, COHR, AEHR, LITE, IPGP.

Three bugs were identified from v2 output data:

1. **Weight inflation bug** — Culled signals (TNX_Change, Oil_Change, and
   others with zero statistical significance) are receiving ~89% of the
   normalized portfolio weight because their raw residual ε values are
   large due to high volatility, not because they carry predictive edge.
   Fix: gate weights to zero for culled signals before normalization.

2. **Regime-blind weights** — The combination engine computes one static
   weight per signal across all market conditions. Regime-conditional IC
   analysis showed signals only work when VIX < 20 AND TNX < 4.5%.
   When either condition is violated, all momentum/trend ICs collapse
   toward zero or flip sign. Fix: compute two weight sets — one for the
   active regime, one for risk-off/high-rate regime — and select
   dynamically based on current conditions.

3. **LITE SMA200 sign bug** — SMA200_Distance is scored identically for
   all tickers. But regime data shows LITE has POSITIVE IC for SMA200
   when TNX < 4.5% (momentum continuation) and NEGATIVE IC when
   TNX >= 4.5% (mean reversion like all other tickers). A fixed positive
   sign for LITE is wrong half the time. Fix: flip SMA200 sign for LITE
   conditionally on TNX regime.

---

## Change 1 of 4 — Update header cell (Cell 0, markdown)

**Location:** First cell of the notebook (markdown cell titled
`# Photonics Signal IC Analysis — v2`)

**Action:** Replace the version line and bullet list with the following.
Keep everything else in the cell identical.

**Replace:**
```
# Photonics Signal IC Analysis — v2
```
**With:**
```
# Photonics Signal IC Analysis — v2.1
```

**Replace the v2 bullet list:**
```
**v2 additions over v1:**
- Drive mount moved to Cell 0 (dependencies)
- Step 2: Serial demeaning integrated into IC pipeline
...
- Drive export of all outputs
```
**With:**
```
**v2 additions over v1:**
- Drive mount moved to Cell 0 (dependencies)
- Step 2: Serial demeaning integrated into IC pipeline
- Step 3: Sample variance per signal
- Step 4: Standardization (normalize by σ)
- Step 5: Drop most recent observation (no look-ahead)
- Step 6: Cross-sectional demeaning (remove shared regime factor)
- Step 7: Drop final period
- Step 8: Expected forward return (d-day moving average, normalized)
- Step 9: Residual regression — isolate independent contribution per signal
- Step 10/11: Optimal signal weights + normalization
- Regime-conditional IC (VIX above/below 20, TNX above/below 4.5%)
- Drive export of all outputs

**v2.1 changes over v2:**
- Fix 1: Weight gate — culled signals receive w=0 before normalization
- Fix 2: Regime-aware weights — two weight sets (active / risk-off),
  selected dynamically by current VIX and TNX levels
- Fix 3: LITE SMA200 sign flip — positive when TNX < 4.5%,
  negative when TNX >= 4.5%, matching regime-conditional IC data
```

---

## Change 2 of 4 — Add KEEP_SIGNALS constant to Configuration cell

**Location:** Cell titled `## 1. Configuration` (the cell containing
`PHOTONICS = [...]`, `HORIZONS = [...]`, etc.)

**Action:** Add the following block at the END of that cell's code,
after the `IC_MIN` and `CORR_MAX` lines. Do not remove anything.

```python
# --- v2.1: Signals approved to receive non-zero weight ---
# Culled signals are excluded here; they enter the weight engine with w=0.
# Based on v2 IC results: signals with Mean_AbsIC >= 0.03 AND Pct_Sig > 0
# TNX_Change, Oil_Change, SPX_Relative, SOX_Relative,
# VIX_Change_1d, SOX_vs_SPX all excluded (zero significance).
KEEP_SIGNALS = [
    'SMA200_Distance',
    'Momentum_21d',
    'EMA_Cross_9_21',
    'Bollinger_Pct_B',
    'Momentum_10d',
    'Volume_Surge',
    'VIX_Regime',      # retained as filter, weight will be small but non-zero
]
```

---

## Change 3 of 4 — Replace Steps 10 & 11 weight cell

**Location:** The cell containing `### Steps 10 & 11` in its markdown
header (the cell immediately after the Step 9 residual regression cell).
This cell currently starts with `weight_log = []`.

**Action:** Replace the ENTIRE source of that code cell with the
following. Do not touch the markdown cell above it.

```python
# ── Steps 10 & 11: Signal Weights + Normalization (v2.1) ────────────────────
#
# v2.1 fixes:
#   Fix 1: Culled signals (not in KEEP_SIGNALS) receive w_raw = 0
#   Fix 2: Weights computed separately for two regimes:
#           'active'   = TNX < TNX_THRESHOLD and VIX < VIX_THRESHOLD
#           'risk_off' = TNX >= TNX_THRESHOLD or VIX >= VIX_THRESHOLD
#   Fix 3: SMA200_Distance sign for LITE flipped when TNX >= TNX_THRESHOLD

# Current regime (based on latest available data)
latest_vix = close['VIX'].dropna().iloc[-1]
latest_tnx = close['TNX'].dropna().iloc[-1]
current_regime = 'active' if (latest_vix < VIX_THRESHOLD and
                               latest_tnx < TNX_THRESHOLD) else 'risk_off'

print(f'Current VIX: {latest_vix:.2f}  TNX: {latest_tnx:.2f}')
print(f'Current regime: {current_regime.upper()}')
print()

# Regime masks for weight calibration
active_mask   = (close['VIX'] < VIX_THRESHOLD) & (close['TNX'] < TNX_THRESHOLD)
risk_off_mask = ~active_mask

def compute_weights_for_regime(regime_mask, label):
    """
    Compute normalized signal weights using only observations in regime_mask.
    Culled signals (not in KEEP_SIGNALS) receive w=0.
    Returns DataFrame: Signal × Ticker → w_norm
    """
    weight_log = []

    for sig_name in signals:
        for t in PHOTONICS:

            # Fix 1: Zero weight for culled signals
            if sig_name not in KEEP_SIGNALS:
                weight_log.append({
                    'Signal': sig_name, 'Ticker': t,
                    'Regime': label,
                    'w_raw': 0.0, 'w_norm': 0.0,
                    'culled': True
                })
                continue

            eps_series = epsilon[sig_name].get(t, pd.Series(dtype=float))
            if len(eps_series) == 0:
                weight_log.append({
                    'Signal': sig_name, 'Ticker': t,
                    'Regime': label,
                    'w_raw': np.nan, 'w_norm': np.nan,
                    'culled': False
                })
                continue

            # Filter epsilon to regime dates only
            regime_dates = close.index[regime_mask.reindex(close.index).fillna(False)]
            eps_regime   = eps_series[eps_series.index.isin(regime_dates)]

            if len(eps_regime) < 10:
                w_raw = 0.0
            else:
                w_raw = eps_regime.mean() / sigma[sig_name][t]

            # Fix 3: Flip SMA200 sign for LITE in risk-off/high-rate regime
            if sig_name == 'SMA200_Distance' and t == 'LITE' and label == 'risk_off':
                w_raw = -abs(w_raw)   # force negative (mean reversion)

            weight_log.append({
                'Signal': sig_name, 'Ticker': t,
                'Regime': label,
                'w_raw': w_raw, 'w_norm': np.nan,
                'culled': False
            })

    df = pd.DataFrame(weight_log)

    # Step 11: Normalize per ticker so Σ|w| = 1 (non-culled signals only)
    def normalize(group):
        group = group.copy()
        total = group.loc[~group['culled'], 'w_raw'].abs().sum()
        group['w_norm'] = group['w_raw'].apply(
            lambda x: x / total if total > 0 else 0.0
        )
        return group

    df = df.groupby('Ticker', group_keys=False).apply(normalize)
    return df

# Compute both regimes
weights_active   = compute_weights_for_regime(active_mask,   'active')
weights_risk_off = compute_weights_for_regime(risk_off_mask, 'risk_off')
weight_df        = pd.concat([weights_active, weights_risk_off], ignore_index=True)

# Select current regime weights for downstream use
weights_current = weight_df[weight_df['Regime'] == current_regime].copy()

print('=== Steps 10–11: Normalized Weights (current regime) ===')
w_pivot = (weights_current[~weights_current['culled']]
           .pivot(index='Signal', columns='Ticker', values='w_norm')
           .round(4))
print(w_pivot.to_string())
print()
print('Column sums (should be ~1.0):')
print(w_pivot.abs().sum().round(4).to_string())
```

---

## Change 4 of 4 — Update mega-alpha cell to use regime weights

**Location:** The cell containing `### Mega-Alpha` in the markdown above
it. This cell currently starts with `mega_alpha = {}`.

**Action:** Replace the ENTIRE source of that code cell with the
following:

```python
# ── Mega-Alpha: Combined Signal Score (v2.1, regime-aware) ──────────────────

mega_alpha = {}

for t in PHOTONICS:
    w_t = (weights_current[
               (weights_current['Ticker'] == t) &
               (~weights_current['culled'])
           ]
           .set_index('Signal')['w_norm'])

    score = pd.Series(0.0, index=close.index)
    for sig_name, w in w_t.items():
        # Fix 3: Apply sign flip for LITE SMA200 based on live TNX regime
        sig_vals = signals[sig_name][t].reindex(close.index).copy()
        if (sig_name == 'SMA200_Distance' and t == 'LITE'
                and latest_tnx >= TNX_THRESHOLD):
            sig_vals = -sig_vals

        score = score + w * sig_vals

    mega_alpha[t] = score

mega_alpha_df = pd.DataFrame(mega_alpha)

# Plot last 60 days
fig, axes = plt.subplots(len(PHOTONICS), 1, figsize=(14, 10), sharex=True)
for i, t in enumerate(PHOTONICS):
    recent = mega_alpha_df[t].dropna().iloc[-60:]
    colors = ['green' if v >= 0 else 'red' for v in recent.values]
    axes[i].bar(recent.index, recent.values, color=colors, alpha=0.7, width=0.8)
    axes[i].axhline(0, color='black', lw=0.5)
    axes[i].set_ylabel(t, fontsize=9)
    axes[i].tick_params(labelsize=7)

regime_label = f'Regime: {current_regime.upper()}  |  VIX={latest_vix:.1f}  TNX={latest_tnx:.2f}%'
fig.suptitle(f'Mega-Alpha v2.1 — {regime_label} (last 60 days)', fontsize=11)
plt.tight_layout()
plt.savefig(f'{FOLDER}/mega_alpha_v2.1.png', dpi=150, bbox_inches='tight')
plt.show()
print(f'Saved: mega_alpha_v2.1.png')
print(f'Active regime: {current_regime.upper()}')
```

---

## Export update (no cell change needed)

The export cell already saves `weight_df` and `mega_alpha_df`. After
the changes above, those variables will contain v2.1 data automatically.
Add these two lines to the export cell after the existing saves:

```python
weights_active.to_csv(f'{FOLDER}/signal_weights_active.csv', index=False)
weights_risk_off.to_csv(f'{FOLDER}/signal_weights_risk_off.csv', index=False)
```

---

## Summary of what each fix does at runtime

| Fix | Effect |
|-----|--------|
| Weight gate | TNX_Change and Oil_Change drop from ~89% combined weight to 0%. KEEP_SIGNALS share 100% of weight. |
| Regime weights | If VIX > 20 or TNX > 4.5% today, risk-off weights are used — these are calibrated only on stressed periods where momentum doesn't work. |
| LITE SMA200 sign | In current market (TNX ~4.3%, borderline), the sign is positive (continuation). If TNX crosses 4.5%, it auto-flips to negative (reversion). |

---

## Verification steps after applying changes

Run the notebook top to bottom. Check:

1. Weight table shows zero for TNX_Change, Oil_Change, SPX_Relative,
   SOX_Relative, VIX_Change_1d, SOX_vs_SPX
2. KEEP_SIGNALS column sums ≈ 1.0 per ticker
3. Console prints current regime label correctly
4. mega_alpha_v2.1.png saved to Drive folder
5. Both `signal_weights_active.csv` and `signal_weights_risk_off.csv`
   appear in Drive folder
