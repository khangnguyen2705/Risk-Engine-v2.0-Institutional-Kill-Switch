#!/usr/bin/env python3
"""Risk Engine v2.0 — Performance Benchmarks.

Measures latency, throughput, and accuracy of the 10-layer risk cascade.

Usage:
    python benchmarks/run_benchmarks.py
"""

import sys, os, time, statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml
from models.data_models import OrderProposal, Side, Action
from risk_engine.engine import RiskEngine

with open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")) as f:
    config = yaml.safe_load(f)


def fmt(us: float) -> str:
    if us < 1:
        return f"{us*1000:.0f}ns"
    if us < 1000:
        return f"{us:.1f}µs"
    return f"{us/1000:.2f}ms"


def benchmark_evaluate_latency(n: int = 10_000):
    """Measure per-order evaluation latency."""
    engine = RiskEngine(config)
    # Warmup anomaly detector
    for i in range(20):
        o = OrderProposal(symbol="SP500_Futures", side=Side.BUY,
                          quantity=100, price=288.0, order_id=f"W-{i}")
        d = engine.evaluate(o)
        if d.action == Action.PASS:
            engine.on_fill(o, 288.0)
    engine.update_market(288.0)

    # Benchmark: normal orders (PASS path)
    latencies_pass = []
    for i in range(n):
        o = OrderProposal(symbol="SP500_Futures", side=Side.BUY,
                          quantity=100, price=288.0, order_id=f"B-{i}")
        t0 = time.perf_counter_ns()
        engine.evaluate(o)
        t1 = time.perf_counter_ns()
        latencies_pass.append((t1 - t0) / 1000)  # to µs

    # Benchmark: fat finger orders (REJECT/KILL path)
    engine2 = RiskEngine(config)
    for i in range(20):
        o = OrderProposal(symbol="SP500_Futures", side=Side.BUY,
                          quantity=100, price=288.0, order_id=f"W2-{i}")
        d = engine2.evaluate(o)
        if d.action == Action.PASS:
            engine2.on_fill(o, 288.0)
    engine2.update_market(288.0)

    latencies_reject = []
    for i in range(n):
        engine2.kill_switch.state = __import__("models.data_models",
            fromlist=["KillSwitchState"]).KillSwitchState.ARMED
        o = OrderProposal(symbol="SP500_Futures", side=Side.BUY,
                          quantity=5_000_000, price=288.0, order_id=f"F-{i}")
        t0 = time.perf_counter_ns()
        engine2.evaluate(o)
        t1 = time.perf_counter_ns()
        latencies_reject.append((t1 - t0) / 1000)

    return latencies_pass, latencies_reject


def benchmark_throughput(duration_sec: float = 2.0):
    """Measure orders-per-second throughput."""
    engine = RiskEngine(config)
    engine.update_market(288.0)
    count = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < duration_sec:
        o = OrderProposal(symbol="SP500_Futures", side=Side.BUY,
                          quantity=100, price=288.0, order_id=f"T-{count}")
        engine.evaluate(o)
        count += 1
    elapsed = time.perf_counter() - t0
    return count, elapsed


def benchmark_anomaly_accuracy():
    """Test anomaly detection precision: 0 false positives on normal, 100% catch on fat fingers."""
    from risk_engine.anomaly_detector import AnomalyDetector
    detector = AnomalyDetector(window_size=100, warmup=10, z_threshold=4.0)

    # Build baseline
    normal_orders = []
    for i in range(50):
        o = OrderProposal(symbol="TEST", side=Side.BUY,
                          quantity=100 + (i % 20), price=288.0, order_id=f"N-{i}")
        detector.score(o)
        detector.record(o)
        normal_orders.append(o)

    # Test normal orders (should NOT be flagged)
    false_positives = 0
    for i in range(100):
        o = OrderProposal(symbol="TEST", side=Side.BUY,
                          quantity=100 + (i % 20), price=288.0, order_id=f"TN-{i}")
        score = detector.score(o)
        if score.is_anomalous:
            false_positives += 1
        detector.record(o)

    # Test fat fingers (SHOULD be flagged)
    true_positives = 0
    fat_fingers = [1_000, 10_000, 100_000, 1_000_000, 10_000_000]
    for qty in fat_fingers:
        o = OrderProposal(symbol="TEST", side=Side.BUY,
                          quantity=qty, price=288.0, order_id=f"FF-{qty}")
        score = detector.score(o)
        if score.is_anomalous:
            true_positives += 1

    return false_positives, 100, true_positives, len(fat_fingers)


def benchmark_regime_transitions():
    """Verify regime transitions on synthetic data."""
    from risk_engine.regime_detector import RegimeDetector

    rd = RegimeDetector(vol_window=10, calm_max_vol=0.15,
                        elevated_max_vol=0.30, annualization_factor=98280)

    # Calm market
    for i in range(20):
        rd.update(100 + i * 0.001)
    calm_regime = rd.current_regime.value

    # Force crisis: alternating volatile swings (high variance in returns)
    import math
    price = 100.0
    for i in range(20):
        shock = 0.05 * (1 if i % 2 == 0 else -1)  # ±5% swings
        price *= (1 + shock)
        rd.update(price)
    crisis_regime = rd.current_regime.value

    return calm_regime, crisis_regime


if __name__ == "__main__":
    print("=" * 65)
    print("  🛡️  Risk Engine v2.0 — Performance Benchmarks")
    print("=" * 65)

    # 1. Latency
    print("\n┌─ LATENCY (10,000 evaluations) ─────────────────────────────┐")
    lp, lr = benchmark_evaluate_latency(10_000)
    print(f"│  PASS path:                                                │")
    print(f"│    Mean:   {fmt(statistics.mean(lp)):>8s}                              │")
    print(f"│    Median: {fmt(statistics.median(lp)):>8s}                              │")
    print(f"│    P99:    {fmt(sorted(lp)[int(len(lp)*0.99)]):>8s}                              │")
    print(f"│    Min:    {fmt(min(lp)):>8s}                              │")
    print(f"│    Max:    {fmt(max(lp)):>8s}                              │")
    print(f"│  KILL path:                                                │")
    print(f"│    Mean:   {fmt(statistics.mean(lr)):>8s}                              │")
    print(f"│    Median: {fmt(statistics.median(lr)):>8s}                              │")
    print(f"│    P99:    {fmt(sorted(lr)[int(len(lr)*0.99)]):>8s}                              │")
    print(f"└────────────────────────────────────────────────────────────┘")

    # 2. Throughput
    print("\n┌─ THROUGHPUT (2-second burst) ──────────────────────────────┐")
    count, elapsed = benchmark_throughput(2.0)
    ops = count / elapsed
    print(f"│  Orders evaluated:  {count:,}                             │")
    print(f"│  Elapsed:           {elapsed:.3f}s                            │")
    print(f"│  Throughput:        {ops:,.0f} orders/sec                    │")
    print(f"└────────────────────────────────────────────────────────────┘")

    # 3. Anomaly Accuracy
    print("\n┌─ ANOMALY DETECTION ACCURACY ───────────────────────────────┐")
    fp, total_normal, tp, total_fat = benchmark_anomaly_accuracy()
    print(f"│  Normal orders tested:   {total_normal}                          │")
    print(f"│  False positives:        {fp}  (target: 0)                   │")
    print(f"│  Fat fingers tested:     {total_fat}                             │")
    print(f"│  True positives:         {tp}/{total_fat}  (target: {total_fat}/{total_fat})                │")
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 100
    recall = tp / total_fat * 100 if total_fat > 0 else 100
    print(f"│  Precision:              {precision:.0f}%                           │")
    print(f"│  Recall:                 {recall:.0f}%                           │")
    print(f"└────────────────────────────────────────────────────────────┘")

    # 4. Regime Transitions
    print("\n┌─ REGIME TRANSITION VERIFICATION ──────────────────────────┐")
    calm, crisis = benchmark_regime_transitions()
    print(f"│  Calm data  → {calm:8s}  {'✅' if calm == 'CALM' else '❌'}                          │")
    print(f"│  Crash data → {crisis:8s}  {'✅' if crisis == 'CRISIS' else '❌'}                          │")
    print(f"└────────────────────────────────────────────────────────────┘")

    print(f"\n{'=' * 65}")
    print(f"  ✅ All benchmarks complete")
    print(f"{'=' * 65}")
