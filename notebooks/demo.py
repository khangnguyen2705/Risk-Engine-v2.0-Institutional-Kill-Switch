#!/usr/bin/env python3
"""Risk Engine v2.0 — Interactive Demo Notebook.

Run this file to see the Risk Engine in action step-by-step.
Each section can be run independently in a Jupyter notebook
by pasting into separate cells.

Usage:
    python notebooks/demo.py
"""

# %% [markdown]
# # 🛡️ Risk Engine v2.0 — Interactive Demo
# 
# This notebook walks through the core components of the
# Institutional Kill Switch system.

# %% Cell 1: Setup
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml
from models.data_models import OrderProposal, Side, Action
from risk_engine.engine import RiskEngine
from risk_engine.anomaly_detector import AnomalyDetector
from risk_engine.regime_detector import RegimeDetector
from risk_engine.liquidity_analyzer import LiquidityAnalyzer
from trader.momentum_bot import MomentumBot

with open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")) as f:
    config = yaml.safe_load(f)

print("✅ Config loaded")
print(f"   Capital: ${config['portfolio']['starting_capital']:,}")
print(f"   Max Notional: ${config['risk_limits']['max_notional']:,}")
print(f"   Anomaly Threshold: {config['anomaly']['z_score_threshold']}σ")

# %% Cell 2: Initialize Engine
engine = RiskEngine(config)
print(f"✅ Risk Engine initialized")
print(f"   Kill Switch: {engine.kill_switch.state.value}")
print(f"   Regime: {engine.regime_detector.current_regime.emoji} {engine.regime_detector.current_regime.value}")
print(f"   Anomaly Warmup: {engine.anomaly_detector.in_warmup}")

# %% Cell 3: Normal Order — Should PASS
normal_order = OrderProposal(
    symbol="SP500_Futures",
    side=Side.BUY,
    quantity=100,
    price=288.06,
    order_id="DEMO-001",
)
print(f"\n📋 Order: {normal_order.side.value} {normal_order.quantity} "
      f"{normal_order.symbol} @ ${normal_order.price}")
print(f"   Notional: ${normal_order.notional:,.2f}")

decision = engine.evaluate(normal_order)
print(f"   ➜ Decision: {decision.action.value}")
if decision.action == Action.PASS:
    engine.on_fill(normal_order, normal_order.price)
    print(f"   ✅ Order filled. NAV: ${engine.portfolio.nav:,.2f}")

# %% Cell 4: Build Anomaly Baseline
print("\n📊 Building anomaly baseline (10 orders)...")
for i in range(10):
    order = OrderProposal(
        symbol="SP500_Futures", side=Side.SELL,
        quantity=170, price=288.0 - i * 0.5,
        order_id=f"DEMO-BASE-{i+1:02d}",
    )
    d = engine.evaluate(order)
    if d.action == Action.PASS:
        engine.on_fill(order, order.price)
        engine.anomaly_detector.record(order)

print(f"   Baseline orders: {engine.anomaly_detector.order_count}")
print(f"   Warmup complete: {not engine.anomaly_detector.in_warmup}")

# %% Cell 5: Fat Finger — Should KILL
fat_finger = OrderProposal(
    symbol="SP500_Futures",
    side=Side.BUY,
    quantity=3_471_499,   # 3.5 million shares
    price=288.06,
    order_id="DEMO-FAT-FINGER",
    strategy_id="momentum_v1_FAT_FINGER",
)
print(f"\n🚨 FAT FINGER: {fat_finger.side.value} {fat_finger.quantity:,} "
      f"{fat_finger.symbol} @ ${fat_finger.price}")
print(f"   Notional: ${fat_finger.notional:,.2f}")

decision = engine.evaluate(fat_finger)
print(f"\n   ➜ Decision: {decision.action.value}")
print(f"   Rules triggered: {len(decision.rules_triggered)}/10")
for rule in decision.rules_triggered:
    print(f"     ✗ {rule}")

print(f"\n   Kill Switch: {engine.kill_switch.state.value}")

# %% Cell 6: Post-Kill Verification
print("\n🔒 Attempting order after kill switch...")
post_kill = OrderProposal(
    symbol="SP500_Futures", side=Side.BUY,
    quantity=10, price=288.0, order_id="DEMO-POST-KILL",
)
d = engine.evaluate(post_kill)
print(f"   ➜ Decision: {d.action.value}")
print(f"   Reason: {d.details.get('reason', 'N/A')}")

# %% Cell 7: Anomaly Detection Deep Dive
print("\n🔬 Anomaly Detection Analysis")
detector = AnomalyDetector(window_size=100, warmup=5, z_threshold=4.0)

# Feed normal orders
import random
for i in range(20):
    order = OrderProposal(
        symbol="TEST", side=Side.BUY,
        quantity=random.randint(90, 110),
        price=100.0, order_id=f"TEST-{i}",
    )
    score = detector.score(order)
    detector.record(order)

# Now test an outlier
outlier = OrderProposal(
    symbol="TEST", side=Side.BUY,
    quantity=50_000,  # 500x normal
    price=100.0, order_id="TEST-OUTLIER",
)
score = detector.score(outlier)
print(f"   Normal qty range: 90-110")
print(f"   Outlier qty: {outlier.quantity:,}")
print(f"   Z-score (notional): {score.z_notional}")
print(f"   Z-score (quantity): {score.z_quantity}")
print(f"   Z-score (timing):   {score.z_timing}")
print(f"   Composite z: {score.composite_z}")
print(f"   Is anomalous: {score.is_anomalous}")

# %% Cell 8: Regime Detection Walkthrough
print("\n🌡️ Regime Detection Walkthrough")
rd = RegimeDetector(vol_window=10, calm_max_vol=0.15,
                    elevated_max_vol=0.30, annualization_factor=252)

# Calm market (tiny moves)
prices_calm = [100 + i * 0.01 for i in range(15)]
for p in prices_calm:
    rd.update(p)
print(f"   After calm data:   {rd.current_regime.emoji} {rd.current_regime.value} "
      f"(vol: {rd.current_vol*100:.1f}%)")

# Crisis market (big moves)
import math
rd2 = RegimeDetector(vol_window=10, calm_max_vol=0.15,
                     elevated_max_vol=0.30, annualization_factor=252)
prices_crash = [100]
for i in range(15):
    prices_crash.append(prices_crash[-1] * (1 - 0.02 * (1 + i * 0.1)))
for p in prices_crash:
    rd2.update(p)
print(f"   After crash data:  {rd2.current_regime.emoji} {rd2.current_regime.value} "
      f"(vol: {rd2.current_vol*100:.1f}%)")

limits = rd2.get_adjusted_limits()
print(f"   Crisis DD limit:   {limits['max_drawdown_pct']}%")
print(f"   Crisis pos sizing: {limits['position_size_mult']}x")

# %% Cell 9: Liquidity Impact Estimation
print("\n💧 Liquidity Impact Demo")
la = LiquidityAnalyzer(book_levels=5, base_spread_bps=5.0,
                       base_depth_per_level=50_000)
la.update(mid_price=288.0, vol_ann=0.20)

# Small order (should pass)
small = OrderProposal(symbol="TEST", side=Side.BUY,
                      quantity=50, price=288.0, order_id="LIQ-SMALL")
r = la.estimate_impact(small)
print(f"   Small order (50 shares):")
print(f"     Slippage: {r.estimated_slippage_pct:.4f}%  ({'✅ PASS' if r.passed_slippage else '❌ FAIL'})")
print(f"     Depth ratio: {r.book_depth_ratio_pct:.2f}%")

# Huge order (should fail)
huge = OrderProposal(symbol="TEST", side=Side.BUY,
                     quantity=1_000_000, price=288.0, order_id="LIQ-HUGE")
r = la.estimate_impact(huge)
print(f"   Huge order (1M shares):")
print(f"     Slippage: {r.estimated_slippage_pct:.2f}%  ({'✅ PASS' if r.passed_slippage else '❌ FAIL'})")
print(f"     Depth ratio: {r.book_depth_ratio_pct:.0f}%")
print(f"     Kyle impact: {r.kyle_lambda_impact_bps:.0f} bps")

# %% Cell 10: Summary
print("\n" + "=" * 60)
print("  🛡️  Risk Engine v2.0 — Demo Complete")
print("=" * 60)
print(f"  10-layer cascade: ✅")
print(f"  Anomaly detection (3-dim z-score): ✅")
print(f"  Regime-aware circuit breakers: ✅")
print(f"  Liquidity impact estimation: ✅")
print(f"  Kill switch state machine: ✅")
print(f"  Auto-flatten on kill: ✅")
print("=" * 60)


if __name__ == "__main__":
    pass  # All cells execute on import
