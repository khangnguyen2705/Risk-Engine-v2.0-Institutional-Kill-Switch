# 🛡️ Risk Engine v2.0 — Institutional Kill Switch

> **Week 7: The Engine — Survival First.**
> An institutional-grade pre-trade risk engine ("Guardian" bot) that watches a momentum trader bot
> and blocks dangerous orders before they reach the market.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Status: Production Demo](https://img.shields.io/badge/status-production%20demo-brightgreen)

---

## 🎯 What This Does

This system simulates an **institutional trading desk's risk infrastructure** — the kind used at firms like Jane Street, Citadel, and Two Sigma. Every order from a trader bot must pass through a **10-layer pre-trade risk cascade** before execution. If any check fails, the order is rejected. If a critical breach occurs, the **Kill Switch** activates and halts ALL trading.

### The Demo Scenario
1. A momentum trader bot generates 12 normal trades (~$50K each) ✅
2. An AI Auditor injects a **$1 Billion "Fat Finger"** buy order 🚫
3. The Risk Engine blocks it — **6 of 10 rules fire simultaneously**
4. The **Kill Switch activates** → all subsequent orders are blocked
5. After manual reset, cascading losses trigger a **second Kill Switch** during a 1987-crash regime

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────────────────────────┐     ┌───────────┐
│  Trader Bot  │────▶│         RISK ENGINE              │────▶│ Portfolio  │
│ (Momentum)   │     │                                  │     │  Tracker   │
└─────────────┘     │  10 Pre-Trade Gates:              │     └───────────┘
                    │   ├─ Kill Switch Check             │
       ┌───────┐    │   ├─ Fat Finger (Notional)        │     ┌───────────┐
       │Market │───▶│   ├─ Fat Finger (Quantity)        │────▶│   Kill    │
       │ Data  │    │   ├─ Anomaly Detection (z-score)  │     │  Switch   │
       │(1987) │    │   ├─ Regime-Adjusted Drawdown     │     │  State    │
       └───────┘    │   ├─ Slippage Impact              │     │  Machine  │
                    │   ├─ Book Depth Ratio             │     └───────────┘
                    │   ├─ Position Concentration        │
                    │   ├─ Order Velocity               │     ┌───────────┐
                    │   └─ Daily Loss Limit             │────▶│ Dashboard │
                    └──────────────────────────────────┘     │  (Web UI) │
                                                             └───────────┘
```

---

## ⚡ Quick Start

```bash
# 1. Clone and enter the project
cd "Khang EWY - Week 7"

# 2. Install dependencies (only PyYAML needed)
pip install -r requirements.txt

# 3. Run the demo (console only)
python main.py

# 4. Or run with the live browser dashboard
python main.py --dashboard
# Then open http://localhost:8765
```

### Expected Output
```
━━━ PHASE 2: FAT FINGER INJECTION — $1,000,000,000 BUY ━━━━━━━━━━━━━━━━━━━━━━
[REJECT] ORDER ORD-0013 | BUY 3,471,499 SP500_Futures @ $288.06 | $1,000,000,002
  ✗ fat_finger_notional: $1,000,000,001.94 > $10,000,000.00 limit
  ✗ fat_finger_quantity: 3,471,499 > 100,000 limit
  ✗ anomaly_z_score: z=12779377.9 (threshold: 4.0)
  ✗ market_impact: slippage=100.07% > 2.0% limit
  ✗ book_depth: ratio=250000.0% > 30.0% limit
  ✗ position_concentration: 9993.5% > 25.0% NAV limit
[FATAL] KILL_SWITCH | ██ TRIGGERED ██ | ARMED → TRIGGERED → HALTED
```

---

## 📂 Project Structure

```
├── config.yaml                  # All risk thresholds — zero magic numbers
├── main.py                      # 5-phase demo orchestrator + dual logging
├── server.py                    # Dashboard HTTP server + JSON API
├── requirements.txt             # pyyaml>=6.0
│
├── models/
│   └── data_models.py           # Enums + frozen dataclasses (OrderProposal, etc.)
│
├── risk_engine/
│   ├── engine.py                # Core 10-layer cascade with short-circuit eval
│   ├── checks.py                # 6 static check functions
│   ├── kill_switch.py           # ARMED → TRIGGERED → HALTED state machine
│   ├── portfolio.py             # NAV, HWM, drawdown, auto-flatten
│   ├── anomaly_detector.py      # Upgrade 1: Rolling z-score (3 dimensions)
│   ├── regime_detector.py       # Upgrade 2: Vol-based CALM/ELEVATED/CRISIS
│   └── liquidity_analyzer.py    # Upgrade 3: Kyle's Lambda + synthetic book
│
├── trader/
│   └── momentum_bot.py          # 5-bar momentum strategy + fat-finger inject
│
├── auditor/
│   └── scenario_injector.py     # AI Auditor controlling demo phases
│
├── dashboard/
│   ├── index.html               # Real-time monitoring UI
│   ├── style.css                # Glassmorphism dark theme
│   ├── app.js                   # 200ms polling + gauge rendering
│   └── demo_snapshot.html       # Static HALTED-state snapshot
│
├── data/
│   └── 1987_crash_market_data.csv  # 7,921 rows of minute-level crash data
│
├── logs/
│   └── risk_engine_log.txt      # Timestamped audit trail (auto-generated)
│
└── screenshots/                 # Dashboard screenshots + recordings
```

---

## 🔬 Three Jane Street-Inspired Upgrades

### Upgrade 1: Adaptive Anomaly Detection
Instead of static "order > $10M → reject", the system learns what **normal** looks like by maintaining rolling statistics on the trader's last 100 orders across 3 dimensions:
- **Notional size** (dollar value)
- **Quantity** (share count)
- **Inter-order timing** (seconds between orders)

Any order deviating more than **4σ** from the baseline is flagged. The $1B fat finger scored **12.8 million σ**.

### Upgrade 2: Regime-Aware Dynamic Circuit Breakers
The system classifies the market into three regimes using rolling realized volatility from the 1987 crash data:

| Regime | Vol Range | Drawdown Limit | Position Sizing |
|--------|-----------|---------------|-----------------|
| 🟢 CALM | < 15% | 15% | 100% |
| 🟡 ELEVATED | 15–30% | 10% | 50% |
| 🔴 CRISIS | > 30% | 8% | 25% |

During the demo, the regime transitions to **🔴 CRISIS** at **65.8% annualized vol**, automatically tightening the drawdown limit from 15% → 8%.

### Upgrade 3: Liquidity-Aware Impact Estimation
A synthetic 5-level order book estimates market impact using:
- **Walk-the-book slippage**: Simulates filling the order level-by-level
- **Kyle's Lambda** (ΔP/ΔQ): Academic market microstructure model
- **Book depth ratio**: Order size vs. visible liquidity

The $1B fat finger would consume **250,000% of visible book depth** and cause **100% slippage**.

---

## ⚙️ Configuration

All risk parameters live in `config.yaml` — zero hardcoded values:

```yaml
risk_limits:
  max_notional: 10_000_000       # $10M per order
  max_quantity: 100_000          # 100K shares
  max_concentration_pct: 25.0    # 25% NAV in one name
  max_velocity_per_sec: 50       # Rate limiting
  daily_loss_limit_pct: 5.0      # 5% daily stop
  max_drawdown_pct: 15.0         # 15% from HWM (base)

anomaly:
  z_score_threshold: 4.0         # 4σ = anomalous

regime:
  annualization_factor: 98280    # √(252 × 390) for minute data
```

---

## 🔴 Kill Switch State Machine

```
    ┌─────────────────┐
    │     ARMED        │ ◄──── Normal operation
    │   (all checks)   │
    └────────┬─────────┘
             │ Critical breach
             ▼
    ┌─────────────────┐
    │   TRIGGERED      │ ──── Auto-flatten positions
    │  (blocking all)  │
    └────────┬─────────┘
             │ Immediate
             ▼
    ┌─────────────────┐
    │    HALTED         │ ──── ALL trading stopped
    │ (manual override) │
    └────────┬─────────┘
             │ Admin key: "OVERRIDE-2026"
             ▼
         Back to ARMED
```

---

## 📊 Demo Results

| Phase | Description | Result |
|:-----:|-------------|--------|
| 1 | 12 normal trades (~$50K each) | All ✅ PASSED |
| 2 | $1B Fat Finger injection | 🚫 6/10 rules → **KILL SWITCH** |
| 3 | 3 post-kill test orders | All ✅ BLOCKED |
| 4 | 1987 crash regime + losses | 🔴 CRISIS → daily loss -5.88% → **KILL SWITCH #2** |
| 5 | Final summary | NAV: $9.4M (-5.9%), Regime: 🔴 CRISIS |

---

## 🛠️ Tech Stack

- **Python 3.10+** — Standard library + PyYAML
- **No ML frameworks** — Pure statistical methods (z-scores, rolling vol)
- **No external APIs** — Fully self-contained simulation
- **Browser Dashboard** — Vanilla HTML/CSS/JS with glassmorphism design

---

## 📜 Submission Deliverables

1. **Console Log**: `logs/risk_engine_log.txt` — ISO-8601 timestamped "Trade Rejected" event
2. **Dashboard**: `python main.py --dashboard` → `http://localhost:8765`
3. **Screenshots**: `screenshots/` directory

---

## 📄 License

MIT License — Built for EWY Week 7: The Engine.
