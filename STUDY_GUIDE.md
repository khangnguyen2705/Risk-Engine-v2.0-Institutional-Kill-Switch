# Risk Engine v2.0 — Complete Study Guide
### Everything You Need to Defend This Project to a Professor

> **Who this is for**: A college freshman who needs to explain every decision,
> every line of logic, and every concept in this project with confidence.

---

## Table of Contents
1. [The Big Picture — What Problem Are We Solving?](#1-the-big-picture)
2. [Real-World Context — Why Do Trading Firms Need This?](#2-real-world-context)
3. [How the System Works — Step by Step](#3-how-the-system-works)
4. [The 10 Risk Checks — Explained Like You're 5](#4-the-10-risk-checks)
5. [The 3 Upgrades — What Makes This Extraordinary](#5-the-3-upgrades)
6. [The Kill Switch — A State Machine](#6-the-kill-switch)
7. [The Code — File by File Walkthrough](#7-the-code)
8. [The Math — Every Formula Explained](#8-the-math)
9. [The Demo — What Happens When You Run It](#9-the-demo)
10. [Professor Q&A — Anticipated Questions and Answers](#10-professor-qa)
11. [Glossary](#11-glossary)

---

## 1. The Big Picture

### The Analogy
Imagine you're a bank teller. A customer walks in and says "I'd like to withdraw $1 billion." You wouldn't just hand them the money — you'd check:
- Do they have $1B in their account? (Balance check)
- Is this normal for them? (Behavioral check)
- Does the bank even have $1B in cash? (Liquidity check)
- Is this a mistake? A typo? (Fat finger check)

**Our Risk Engine does exactly this, but for stock trades, in milliseconds.**

### The Setup
We have two bots:
- **The Trader Bot** ("Momentum Bot") — reads stock price data and decides to buy/sell
- **The Guardian Bot** ("Risk Engine") — watches every order the Trader wants to make and decides: **PASS**, **REJECT**, or **KILL** (emergency halt)

The Trader Bot CANNOT place a trade without the Risk Engine's approval. Period.

### The Scenario
An **AI Auditor** tests our Risk Engine by:
1. Letting the Trader make normal trades (should all pass ✅)
2. Injecting a **$1 Billion** trade (should be blocked 🚫)
3. Trying to trade after the system is halted (should be blocked 🚫)
4. Simulating market crash losses to trigger a second emergency halt

---

## 2. Real-World Context

### Why Does This Matter?

**Knight Capital (2012)**: A trading firm lost **$440 million in 45 minutes** due to a software bug that sent millions of unintended orders. They had no kill switch. The firm went bankrupt.

**Fat Finger Trades**: In 2014, a trader at Samsung Securities accidentally issued $105 billion in shares instead of $105 million — a typo. That's 30× the company's value.

**The 1987 Crash ("Black Monday")**: The S&P 500 dropped **22.6% in one day**. Our project uses actual minute-by-minute price data from this crash to stress-test the system.

### What Do Real Firms Do?

At firms like **Jane Street** (one of the world's largest market makers):
- Every order passes through a risk engine before reaching the exchange
- The risk engine has **absolute veto power** — if it says no, the trade doesn't happen
- They use statistical anomaly detection, not just static limits
- They have kill switches that can halt ALL trading in microseconds

**Our project replicates this architecture.**

---

## 3. How the System Works

### The Flow (Every Single Trade)

```
Trader Bot generates an order
        │
        ▼
   ┌─────────────┐
   │ Risk Engine  │ ◄── Runs 10 checks in sequence
   │  evaluate()  │
   └──────┬───────┘
          │
    ┌─────┴─────┐
    │           │
  PASS?       FAIL?
    │           │
    ▼           ▼
 Execute    How bad?
  trade        │
            ┌──┴──┐
          Minor  Critical
            │       │
         REJECT    KILL
         (this    (halt
         order)    ALL
                  trading)
```

### What Triggers KILL vs. REJECT?

| Trigger | Action | Why |
|---------|--------|-----|
| Order too big ($10M+) | REJECT | Might be a mistake, but not catastrophic |
| Order is 100× too big ($100M+) | **KILL** | Definitely a fat finger — shut everything down |
| Drawdown exceeds limit | **KILL** | We're losing too much money — stop now |
| Daily loss exceeds 5% | **KILL** | The day is over, we're bleeding |
| Anomaly z-score > 4σ | REJECT | Unusual but not necessarily fatal |
| Slippage too high | REJECT | Market can't absorb this order |

---

## 4. The 10 Risk Checks

Every order runs through these 10 gates **in sequence**. Think of it as airport security with 10 checkpoints — you must pass ALL of them.

### Gate 0: Kill Switch Check
**Question**: "Is the system already in emergency mode?"
**How**: Check if `kill_switch.state` is `TRIGGERED` or `HALTED`
**If fail**: Instant REJECT — don't even look at the order

### Gate 1: Fat Finger — Notional Value
**Question**: "Is this order worth more than $10 million?"
**How**: `order.quantity × order.price > $10,000,000?`
**Example**: The $1B order → $1,000,000,002 > $10,000,000 → **FAIL**
**If >100× limit**: Escalates to KILL (not just REJECT)

### Gate 2: Fat Finger — Quantity
**Question**: "Is this order for more than 100,000 shares?"
**How**: `abs(order.quantity) > 100,000?`
**Example**: 3,471,499 shares > 100,000 → **FAIL**

### Gate 3: Adaptive Anomaly Detection (Upgrade 1)
**Question**: "Is this order abnormal compared to what this trader usually does?"
**How**: Calculate z-score against rolling history (see Math section)
**Example**: Normal orders are ~$50K. A $1B order is **12.8 million σ** from normal → **FAIL**

### Gate 4: Regime-Adjusted Drawdown (Upgrade 2)
**Question**: "Have we lost too much money from our peak?"
**How**: `(peak_NAV - current_NAV) / peak_NAV > limit?`
**Twist**: The limit changes based on market conditions (CALM=15%, CRISIS=8%)

### Gate 5: Slippage Impact (Upgrade 3)
**Question**: "If we place this order, how much will the price move against us?"
**How**: Walk through a synthetic order book level-by-level
**Example**: $1B order → **100% slippage** (price would double) → **FAIL**

### Gate 6: Book Depth Ratio (Upgrade 3)
**Question**: "Is this order bigger than the available market liquidity?"
**How**: `order_value / total_book_depth × 100`
**Example**: $1B order vs $400K book depth → **250,000%** → **FAIL**

### Gate 7: Position Concentration
**Question**: "Would this put too much of our portfolio in one stock?"
**How**: `(position_value + order_value) / NAV × 100 > 25%?`
**Example**: $1B order in a $10M portfolio → **9,993%** concentration → **FAIL**

### Gate 8: Order Velocity
**Question**: "Is the trader sending orders too fast?"
**How**: Count orders in the last 1 second. If > 50 → **FAIL**
**Note**: This didn't fire in our demo because orders were spaced 800ms apart

### Gate 9: Daily Loss Limit
**Question**: "Have we lost more than 5% today?"
**How**: `(current_NAV - start_of_day_NAV) / start_of_day_NAV < -5%?`
**Example**: -5.88% daily loss → **FAIL** → escalates to **KILL**

---

## 5. The 3 Upgrades

These upgrades are what separate a "homework project" from an "institutional-grade system."

### Upgrade 1: Adaptive Anomaly Detection

**The Problem with Static Rules**: A rule like "reject orders > $10M" is too rigid. What if a trader normally trades $9M? That's fine. But what if a trader who normally trades $50K suddenly submits $9M? That's suspicious — even though it's under the $10M limit.

**The Solution**: Instead of asking "is this order big?", ask **"is this order unusual for THIS trader?"**

**How It Works**:
1. Keep a rolling window of the last 100 orders
2. Track three dimensions: dollar value, share count, and timing between orders
3. For each new order, compute how many **standard deviations** it is from the mean
4. If the z-score > 4.0 (4 sigma), flag it as anomalous

**Warmup Period**: The first 10 orders are always passed (the system needs data to learn what "normal" looks like).

**Real Result**: The $1B fat finger scored **z = 12,779,377.9** — that's 12.8 million standard deviations from normal. For context, a z-score of 6 has a probability of 1-in-500-million.

### Upgrade 2: Regime-Aware Dynamic Circuit Breakers

**The Problem**: Using the same risk limits in calm markets and crisis markets is dangerous. During a crash, a 10% drawdown can happen in minutes — you need tighter limits.

**The Solution**: Automatically detect the market regime using **realized volatility** and adjust limits accordingly.

**How It Works**:
1. Track the last 20 price returns (log returns)
2. Compute the standard deviation → this is the realized volatility
3. Annualize it: `annual_vol = minute_vol × √(252 × 390)`
   - 252 trading days/year × 390 minutes/day = 98,280 minutes/year
4. Classify:
   - Vol < 15% → 🟢 CALM (normal market)
   - Vol 15-30% → 🟡 ELEVATED (getting risky)
   - Vol > 30% → 🔴 CRISIS (crash mode)

**Real Result**: During the 1987 crash simulation, vol hit **65.8%** → 🔴 CRISIS → drawdown limit automatically tightened from 15% to **8%**.

### Upgrade 3: Liquidity-Aware Impact Estimation

**The Problem**: Even if an order passes all other checks, it might be too large for the market to absorb. Trying to buy $1B of a stock that only has $400K of visible orders would crash the price.

**The Solution**: Build a **synthetic order book** and simulate what happens if you try to fill the order.

**How It Works**:
1. Generate a 5-level bid/ask book based on the current price
2. "Walk the book": fill the order level by level, tracking the average price
3. Compare the average fill price to the mid price → this is the **slippage**
4. Also compute **Kyle's Lambda**: a measure from academic finance (Kyle, 1985) that quantifies how much price moves per unit of order flow

**Real Result**: The $1B order would cause **100% slippage** (price doubles) and consume **250,000%** of visible book depth.

---

## 6. The Kill Switch

The kill switch is implemented as a **finite state machine** — a concept from computer science where a system can be in one of several states, with defined transitions between them.

### The States

| State | Meaning | Orders Allowed? |
|-------|---------|:---------:|
| **ARMED** | Normal operation | ✅ Yes |
| **TRIGGERED** | Critical breach detected | ❌ No |
| **HALTED** | All trading stopped, positions flattened | ❌ No |

### The Transitions

```
ARMED ──(critical breach)──▶ TRIGGERED ──(auto)──▶ HALTED
                                                      │
                                 (admin key required)  │
                                                      ▼
                                                    ARMED
```

**Key Design Decisions**:
- Once triggered, you **cannot restart** without a manual admin key (`OVERRIDE-2026`)
- The system **auto-flattens** all positions on kill (closes all trades at current price)
- A second breach while already HALTED creates a `KILL_SWITCH_REDUNDANT` event (logged but no state change)
- Every state change creates an **audit trail** (a `RiskEvent` object with timestamp)

### Why a State Machine?
A professor might ask: "Why not just use a boolean flag?"

Answer: A boolean (`is_halted = True/False`) doesn't capture the full lifecycle:
- You can't distinguish between "just triggered" and "fully halted with positions flattened"
- You can't enforce that reset requires authentication
- You can't maintain an audit trail of state transitions
- You can't prevent race conditions where multiple triggers fire simultaneously

---

## 7. The Code — File by File

### `config.yaml` — The Control Center
Every single number in the system comes from this file. This is called **"no magic numbers"** — a best practice where hardcoded values are forbidden.

**Why this matters**: If a professor asks "what happens if we change the drawdown limit?", the answer is: "Change one number in config.yaml and re-run. Nothing else changes."

### `models/data_models.py` — The Vocabulary
Defines every data structure using Python **dataclasses**:
- `OrderProposal` — a trade request (frozen = cannot be modified after creation)
- `RiskDecision` — the engine's verdict (PASS/REJECT/KILL)
- `RiskEvent` — an audit trail entry
- `Position` — a single stock holding
- `PortfolioSnapshot` — full portfolio state at a point in time

**Key concept**: `frozen=True` means immutability. Once created, an `OrderProposal` cannot be altered. This prevents bugs where someone accidentally modifies an order after it's been evaluated.

### `risk_engine/engine.py` — The Brain (277 lines)
The `evaluate()` method is the heart of the system:
1. Run all 10 checks
2. Collect failures
3. Decide: PASS (no failures), REJECT (minor failures), or KILL (critical failures)
4. If KILL: trigger kill switch + auto-flatten positions
5. If PASS: record order in anomaly detector's baseline

**Design pattern**: **Short-circuit evaluation** — each check adds to a `failures` list. All checks always run (unlike Python's `and` operator which stops early). This is intentional: we want to know ALL the rules that fired, not just the first one.

### `risk_engine/checks.py` — Static Rules (6 functions)
Each function has the same signature: `(inputs) → (passed: bool, reason: str)`

This is a design pattern called **Strategy Pattern** — each check is a pure function with no side effects. You can add/remove/reorder checks without touching any other code.

### `risk_engine/kill_switch.py` — The Emergency Brake
Implements the state machine. The `trigger()` method:
1. Changes state ARMED → TRIGGERED → HALTED
2. Records 3 events (triggered, state change, halt)
3. Returns the events for logging

The `reset()` method requires an admin key — simulating the real-world requirement where only a senior risk officer can restart trading.

### `risk_engine/portfolio.py` — The Accountant
Tracks:
- **Cash**: Money not invested
- **Positions**: What stocks we hold, at what price
- **NAV (Net Asset Value)**: Cash + market value of positions
- **HWM (High Water Mark)**: The highest NAV ever reached
- **Drawdown**: How far we've fallen from the HWM
- **Daily P&L**: Today's profit/loss

`flatten_all()`: Emergency position closure — sets all positions to zero at current market price.

### `risk_engine/anomaly_detector.py` — The Behavioral Profiler
Maintains 3 rolling `deque` buffers (fixed-size queues):
- `_notionals`: Last 100 order dollar values
- `_quantities`: Last 100 order share counts
- `_intervals`: Last 100 inter-order time gaps

The `_z_score()` method: `z = |value - mean| / std`

The `composite_z` is the **maximum** of all three z-scores — we take the worst one.

### `risk_engine/regime_detector.py` — The Weather Station
Reads market volatility and classifies it:
- Computes **log returns**: `ln(price_t / price_{t-1})`
- Computes **realized vol**: `std(returns) × √(annualization_factor)`
- Classifies into CALM/ELEVATED/CRISIS
- Returns regime-adjusted limits (tighter in crisis)

### `risk_engine/liquidity_analyzer.py` — The Market Depth Estimator
Builds a synthetic order book and estimates:
- **Slippage**: How much the price moves if we fill our entire order
- **Book depth ratio**: Our order vs. total visible liquidity
- **Kyle's Lambda**: Price impact per unit traded

### `trader/momentum_bot.py` — The Strategy Bot
Uses a **5-bar momentum signal**:
1. Compute SMA(5) = average of last 5 prices
2. Signal = current_price / SMA(5) - 1
3. If signal > 0 → BUY; if signal < 0 → SELL
4. Size = signal strength × $200K base

The `inject_fat_finger()` method lets the AI Auditor override the next order with a $1B trade.

### `main.py` — The Director (498 lines)
Orchestrates the 5-phase demo. Key features:
- **DualLogger**: Writes to both terminal AND a file simultaneously
- **Pacing**: Adds delays so the dashboard can capture state changes
- **Dynamic crash targeting**: Computes exactly how many ticks to skip to reach the 1987 crash

---

## 8. The Math

### Z-Score (Anomaly Detection)
```
z = |x - μ| / σ
```
Where:
- `x` = the value being tested (e.g., $1,000,000,000)
- `μ` (mu) = mean of the rolling window (e.g., $50,000)
- `σ` (sigma) = standard deviation of the rolling window (e.g., $78.34)

For the fat finger: `z = |1,000,000,000 - 50,000| / 78.34 = 12,779,377.9`

**Interpretation**: This value is 12.8 million standard deviations from normal. The probability of this occurring naturally is effectively **zero**.

### Realized Volatility (Regime Detection)
```
r_t = ln(P_t / P_{t-1})           # Log return at time t
σ_minute = std(r_1, r_2, ..., r_20)  # Standard deviation of 20 returns
σ_annual = σ_minute × √98280     # Annualize (252 days × 390 min/day)
```

During the 1987 crash: `σ_annual = 0.00210 × √98280 = 0.658 = 65.8%`

For reference: Normal S&P 500 annual vol is about 15-20%. During the 2008 crisis it hit ~80%. Our 65.8% correctly classifies as **CRISIS**.

### Drawdown (Portfolio Risk)
```
Drawdown% = (HWM - NAV) / HWM × 100
```
Where:
- HWM = highest NAV ever achieved (our peak was ~$10,012,395)
- NAV = current portfolio value ($9,411,651 after losses)

Result: `(10,012,395 - 9,411,651) / 10,012,395 × 100 = 6.0%`

### Kyle's Lambda (Market Microstructure)
From Kyle (1985), the permanent price impact of a trade:
```
ΔP = λ × ΔQ
```
Where `λ` (lambda) is the price impact per unit of order flow. Higher lambda = less liquid market.

### Walk-the-Book Slippage
Simulate filling an order by consuming book levels:
```
Level 1: Buy 170 shares @ $288.10 (best ask)
Level 2: Buy 221 shares @ $288.14
Level 3: Buy 272 shares @ $288.17
Level 4: Buy 323 shares @ $288.21
Level 5: Buy 374 shares @ $288.24
Remaining: 3,470,139 shares → extrapolate at worst price
Average fill: $576.14 vs mid $288.06 → slippage = 100%
```

---

## 9. The Demo — What Happens

### Phase 1: Normal Trading
- Bot reads 1987 market data (Oct 16, before the crash)
- Generates 12 SELL orders of ~$50K each (momentum is down)
- All pass through the 10-layer check ✅
- Anomaly detector builds its baseline: 12 orders, mean ≈ $50K

### Phase 2: Fat Finger ($1B)
- AI Auditor calls `bot.inject_fat_finger(1_000_000_000)`
- Next order becomes: BUY 3,471,499 shares @ $288.06 = $1,000,000,002
- **6 of 10 rules fire simultaneously**:
  1. Notional: $1B > $10M ✗
  2. Quantity: 3.5M > 100K ✗
  3. Anomaly: z=12.8M > 4.0 ✗
  4. Slippage: 100% > 2% ✗
  5. Book depth: 250,000% > 30% ✗
  6. Concentration: 9,993% > 25% ✗
- Because notional > 10× limit ($100M), this is **KILL level**
- Kill Switch: ARMED → TRIGGERED → HALTED
- Positions auto-flattened

### Phase 3: Post-Kill Verification
- 3 small test orders ($28K each) are submitted
- ALL blocked: "System HALTED — all orders blocked"
- Proves the kill switch actually works

### Phase 4: Reset + Crisis Regime + Drawdown Cascade
- Admin key resets kill switch: HALTED → ARMED
- Fast-forward to Oct 19, 1987 (the crash day)
- Regime detector sees vol spike: 🟢 CALM → 🔴 CRISIS (65.8%)
- Drawdown limit tightens: 15% → 8%
- Simulate 4 losing trades ($150K each)
- After $600K loss: daily P&L = -5.88% > 5% limit
- **KILL SWITCH #2** activates

### Phase 5: Final Summary
```
Total orders: 20 | Passed: 12 | Rejected: 8
Kill Switch activations: 2
Final NAV: $9,411,651 (-5.9%)
Regime: 🔴 CRISIS
```

---

## 10. Professor Q&A

### "Why Python and not C++ like real trading firms?"
Real HFT firms use C++ for nanosecond-level latency. But the **risk logic** is the same regardless of language. This project demonstrates the architecture and decision framework. Porting to C++ would change the syntax but not the design.

### "Why 10 checks? Why not 5 or 20?"
10 covers the core categories: size limits (2), behavioral analysis (1), portfolio risk (2), market microstructure (2), rate limiting (1), loss limits (2). Each check is independent — you can add or remove checks without affecting others.

### "How is this different from just setting a max order size?"
A max order size is **one** of our 10 checks. But it misses:
- An order that's under the limit but anomalous for that trader (Upgrade 1)
- An order in a crashing market where limits should be tighter (Upgrade 2)
- An order the market literally can't absorb (Upgrade 3)

### "What happens if two checks disagree?"
They can't "disagree" — they're independent gates. ANY failure blocks the order. This is the **principle of least privilege** applied to trading.

### "Why use z-scores instead of machine learning?"
Z-scores are:
1. **Interpretable** — you can explain exactly why an order was flagged
2. **Deterministic** — same input = same output, every time
3. **Fast** — O(1) computation vs. ML inference
4. **Auditable** — regulators require explainable risk decisions

Real firms use ML for signal generation but statistical methods for risk controls, because risk must be deterministic and explainable.

### "What is a 'frozen dataclass' and why use it?"
A frozen dataclass is **immutable** — once created, its fields cannot be changed. This prevents bugs where an order is modified after risk evaluation. If you evaluated an order for $50K and someone changed it to $50M afterward, the risk check would be meaningless.

### "What's the difference between drawdown and daily loss?"
- **Drawdown**: How far we've fallen from our ALL-TIME peak. Measured from the High Water Mark.
- **Daily loss**: How much we've lost TODAY. Resets each day.

A system can have low drawdown but high daily loss (if the HWM was set recently), or high drawdown but low daily loss (if the drawdown accumulated over many days).

### "Why does the regime detector use log returns instead of simple returns?"
Log returns are **additive** across time periods: `ln(P_2/P_0) = ln(P_2/P_1) + ln(P_1/P_0)`. Simple returns are not. This makes log returns mathematically cleaner for volatility estimation. It's standard practice in quantitative finance.

### "What's the annualization factor of 98,280?"
There are 252 trading days per year and 390 trading minutes per day (6.5 hours). Our data is minute-level, so: `252 × 390 = 98,280 minutes/year`. To convert minute volatility to annual: multiply by `√98,280 ≈ 313.5`.

### "Could this actually be used in production?"
The architecture is production-grade. For actual deployment, you'd need:
- C++ or Rust for microsecond latency
- Real market data feeds (FIX protocol)
- Persistent state (database for crash recovery)
- Async event-driven architecture
- Regulatory compliance (SEC Rule 15c3-5)

### "What's Kyle's Lambda from?"
Albert Kyle's 1985 paper "Continuous Auctions and Insider Trading" — one of the most cited papers in market microstructure. It models how informed trading moves prices. Lambda (λ) measures the price impact per unit of order flow. Higher λ = less liquid market.

---

## 11. Glossary

| Term | Definition |
|------|-----------|
| **NAV** | Net Asset Value — total portfolio value (cash + positions) |
| **HWM** | High Water Mark — the highest NAV ever achieved |
| **Drawdown** | Percentage decline from the HWM |
| **Notional** | Dollar value of a trade (price × quantity) |
| **Fat Finger** | An accidental trade with wrong size (e.g., typing $1B instead of $1M) |
| **Kill Switch** | Emergency mechanism to halt all trading |
| **Z-Score** | Number of standard deviations from the mean |
| **Sigma (σ)** | Standard deviation — a measure of spread/variation |
| **Regime** | Market condition classification (CALM/ELEVATED/CRISIS) |
| **Realized Vol** | Historical volatility measured from actual returns |
| **Slippage** | Difference between expected and actual trade price |
| **Order Book** | Queue of buy/sell orders at different prices |
| **Kyle's Lambda** | Price impact coefficient from Kyle (1985) |
| **Annualization** | Converting short-term measurements to yearly equivalents |
| **Log Return** | `ln(P_t / P_{t-1})` — mathematically additive return measure |
| **Deque** | Double-ended queue — a fixed-size sliding window data structure |
| **State Machine** | System with defined states and transitions between them |
| **Frozen Dataclass** | Immutable Python object — cannot be modified after creation |
| **Short-Circuit** | Stopping evaluation early when a condition is met |
| **Dual Logger** | Writes output to both screen and file simultaneously |
| **Walk the Book** | Simulating how an order fills by consuming book levels |
| **Pure Function** | Function with no side effects — same input always gives same output |

---

> **Final tip for defending this project**: When a professor challenges you, always tie your answer back to **real-world risk management**. Every design decision in this project mirrors how firms with billions of dollars at stake actually protect themselves. The z-score, the state machine, the regime detection, the Kyle's Lambda — none of these are academic exercises. They're the actual tools used on trading desks. This project isn't simulating risk management — it IS risk management, running on simulated data.
