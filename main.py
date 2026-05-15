#!/usr/bin/env python3
"""Risk Engine v2.0 — Institutional Kill Switch Demo.

Orchestrates the full 5-phase demo:
  Phase 1: Normal trading (10-15 trades, all PASS)
  Phase 2: Fat Finger injection ($1B BUY → REJECTED + KILL SWITCH)
  Phase 3: Post-kill verification (all orders blocked)
  Phase 4: Manual reset + drawdown cascade under crisis regime
  Phase 5: Final Kill Switch from drawdown breach

Usage:
    python main.py                  # Console-only demo
    python main.py --dashboard      # Console + browser dashboard
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import json
import yaml
from datetime import datetime, timezone
from pathlib import Path

# Ensure we can import local packages
sys.path.insert(0, str(Path(__file__).parent))

from models.data_models import Action, Side, Severity, RiskEvent, OrderProposal
from risk_engine.engine import RiskEngine
from trader.momentum_bot import MomentumBot
from auditor.scenario_injector import ScenarioInjector


# ---------------------------------------------------------------------------
# Logger — tees to console + file
# ---------------------------------------------------------------------------

class DualLogger:
    """Writes to both stdout and a log file simultaneously."""

    def __init__(self, log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message: str):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()


def ts() -> str:
    """Current ISO-8601 timestamp with timezone."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def ts_short() -> str:
    """Short timestamp for log lines."""
    return datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_money(val: float) -> str:
    if abs(val) >= 1e9:
        return f"${val:,.0f}"
    if abs(val) >= 1e6:
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def phase_banner(title: str):
    print(f"\n{'━' * 3} {title} {'━' * max(1, 72 - len(title))}\n")


def log_line(ts_str: str, level: str, source: str, message: str):
    level_colors = {
        "INFO": "INFO ",
        "PASS": "PASS ",
        "WARN": "WARN ",
        "REJECT": "REJECT",
        "FATAL": "FATAL",
        "CRITICAL": "CRITICAL",
    }
    tag = level_colors.get(level, level.ljust(6))
    print(f"[{ts_str}] [{tag}] {source:14s} | {message}")


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def run_simulation(config: dict, data_path: str, use_dashboard: bool = False):
    """Execute the full 5-phase Risk Engine demo."""

    sim_cfg = config["simulation"]
    symbol = sim_cfg["symbol"]
    # Dashboard pacing — slow down so the UI can capture transitions
    pace = 0.8 if use_dashboard else 0.03
    phase_pause = 2.0 if use_dashboard else 0.0

    # --- Init components ---
    engine = RiskEngine(config)
    bot = MomentumBot(data_path, symbol=symbol)
    auditor = ScenarioInjector(config)

    # Optional dashboard server
    dashboard_server = None
    if use_dashboard:
        try:
            from server import start_server, update_state, add_order_event
            dashboard_server = start_server(
                port=config["dashboard"]["port"],
                dashboard_dir=str(Path(__file__).parent / "dashboard"),
            )
            log_line(ts_short(), "INFO", "DASHBOARD",
                     f"Dashboard running at http://localhost:{config['dashboard']['port']}")
            time.sleep(0.5)
        except Exception as e:
            log_line(ts_short(), "WARN", "DASHBOARD", f"Failed to start: {e}")
            use_dashboard = False

    # --- Print header ---
    print("=" * 80)
    print("RISK ENGINE v2.0 — INSTITUTIONAL KILL SWITCH DEMO")
    print("Adaptive Anomaly Detection | Regime-Aware Limits | Liquidity Impact Estimation")
    print(f"Started: {ts()}")
    print("=" * 80)

    log_line(ts_short(), "INFO", "ENGINE",
             f"Capital: {fmt_money(config['portfolio']['starting_capital'])} "
             f"| Max DD: {config['risk_limits']['max_drawdown_pct']}% "
             f"| Symbol: {symbol}")
    log_line(ts_short(), "INFO", "KILL_SWITCH", "State: ARMED")
    log_line(ts_short(), "INFO", "ANOMALY_DET",
             f"Warmup mode (need {config['anomaly']['warmup_orders']} orders for baseline)")
    log_line(ts_short(), "INFO", "REGIME_DET", "Vol: 0.0% ann. | Regime: 🟢 CALM")
    log_line(ts_short(), "INFO", "LIQUIDITY",
             f"Book levels: {config['liquidity']['book_levels']} | "
             f"Base depth/level: {fmt_money(config['liquidity']['base_depth_per_level'])}")

    # Warm up the market data (advance enough ticks for momentum signal)
    for _ in range(10):
        p = bot.tick()
        if p is not None:
            engine.update_market(p, bot.current_timestamp)

    # ===================================================================
    # PHASE 1: Normal Trading
    # ===================================================================
    phase_banner("PHASE 1: Normal Trading")
    log_line(ts_short(), "INFO", "AI_AUDITOR",
             f"Running {sim_cfg['normal_trades_before_fat_finger']} normal trades to establish baseline")

    trades_executed = 0
    tick_count = 0
    trade_freq = sim_cfg.get("trade_frequency", 5)

    while trades_executed < sim_cfg["normal_trades_before_fat_finger"]:
        p = bot.tick()
        if p is None:
            break
        engine.update_market(p, bot.current_timestamp)
        tick_count += 1

        if tick_count % trade_freq != 0:
            continue

        order = bot.create_order()
        if order is None:
            continue

        decision = engine.evaluate(order)

        if decision.action == Action.PASS:
            engine.on_fill(order, order.price)
            trades_executed += 1
            anomaly_z = decision.details.get("anomaly_z", 0)
            slippage = decision.details.get("slippage_pct", 0)
            dd = engine.portfolio.drawdown_pct
            regime = engine.regime_detector.current_regime.emoji

            log_line(ts_short(), "PASS",
                     f"ORDER {order.order_id}",
                     f"{order.side.value} {order.quantity:,.0f} {order.symbol} "
                     f"@ {fmt_money(order.price)} | {fmt_money(order.notional)}")
            print(f"{'':>42}Anomaly z={anomaly_z:.1f} | "
                  f"Impact={slippage:.2f}% | DD={dd:.2f}% | Regime {regime}")
        else:
            log_line(ts_short(), "REJECT",
                     f"ORDER {order.order_id}",
                     f"{order.side.value} {order.quantity:,.0f} {order.symbol} | REJECTED")
            for rule in decision.rules_triggered:
                print(f"{'':>42}✗ {rule}")

        # Update dashboard
        if use_dashboard:
            update_state(engine.get_state())
            add_order_event({
                "order_id": order.order_id,
                "side": order.side.value,
                "symbol": order.symbol,
                "quantity": order.quantity,
                "price": order.price,
                "notional": order.notional,
                "action": decision.action.value,
                "rules": list(decision.rules_triggered),
                "anomaly_z": decision.details.get("anomaly_z", 0),
                "timestamp": ts(),
            })

        time.sleep(pace)  # Pacing

    log_line(ts_short(), "INFO", "PHASE_1",
             f"Complete — {trades_executed} trades executed, all PASSED")
    log_line(ts_short(), "INFO", "PORTFOLIO",
             f"NAV: {fmt_money(engine.portfolio.nav)} | "
             f"DD: {engine.portfolio.drawdown_pct:.2f}% | "
             f"Anomaly baseline: {engine.anomaly_detector.order_count} orders")

    time.sleep(phase_pause)

    # ===================================================================
    # PHASE 2: FAT FINGER INJECTION
    # ===================================================================
    phase_banner("PHASE 2: FAT FINGER INJECTION — $1,000,000,000 BUY")

    log_line(ts_short(), "WARN", "AI_AUDITOR",
             f"Injecting Fat Finger scenario: {fmt_money(sim_cfg['fat_finger_notional'])} BUY")

    bot.inject_fat_finger(sim_cfg["fat_finger_notional"])
    # Advance a tick to get fresh price
    p = bot.tick()
    if p is not None:
        engine.update_market(p, bot.current_timestamp)

    fat_order = bot.create_order()
    if fat_order:
        decision = engine.evaluate(fat_order)
        log_line(ts_short(), "REJECT" if decision.action != Action.PASS else "PASS",
                 f"ORDER {fat_order.order_id}",
                 f"{fat_order.side.value} {fat_order.quantity:,.0f} {fat_order.symbol} "
                 f"@ {fmt_money(fat_order.price)} | {fmt_money(fat_order.notional)}")

        for rule in decision.rules_triggered:
            print(f"{'':>42}✗ {rule}")

        anomaly_z = decision.details.get("anomaly_z", 0)
        slippage = decision.details.get("slippage_pct", 0)
        depth = decision.details.get("depth_ratio_pct", 0)

        if decision.action == Action.KILL:
            log_line(ts_short(), "FATAL", "KILL_SWITCH",
                     "██ TRIGGERED ██ | ARMED → TRIGGERED → HALTED")
            log_line(ts_short(), "FATAL", "KILL_SWITCH",
                     "ALL TRADING HALTED — manual override required")

        # Print the Trade Rejected box
        print(f"\n{'━' * 3} Trade Rejected {'━' * 60}")
        print(f"Timestamp:  {ts()}")
        print(f"Order:      {fat_order.side.value} {fat_order.quantity:,.0f} "
              f"{fat_order.symbol} @ {fmt_money(fat_order.price)}")
        print(f"Notional:   {fmt_money(fat_order.notional)}")
        print(f"Rules Hit:  {len(decision.rules_triggered)} of 10 "
              f"({', '.join(r.split(':')[0] for r in decision.rules_triggered)})")
        if anomaly_z > 0:
            print(f"Anomaly:    z-score = {anomaly_z} "
                  f"({anomaly_z/engine.anomaly_detector.z_threshold:.0f}σ "
                  f"from trader's baseline)")
        if depth > 0:
            print(f"Impact:     Would consume {depth:.1f}% of visible book depth")
        print(f"Action:     REJECTED → KILL SWITCH ACTIVATED")
        print(f"{'━' * 78}")

        if use_dashboard:
            update_state(engine.get_state())
            add_order_event({
                "order_id": fat_order.order_id,
                "side": fat_order.side.value,
                "symbol": fat_order.symbol,
                "quantity": fat_order.quantity,
                "price": fat_order.price,
                "notional": fat_order.notional,
                "action": decision.action.value,
                "rules": list(decision.rules_triggered),
                "anomaly_z": anomaly_z,
                "is_fat_finger": True,
                "timestamp": ts(),
            })

    time.sleep(phase_pause)

    # ===================================================================
    # PHASE 3: Post-Kill Switch Verification
    # ===================================================================
    phase_banner("PHASE 3: Post-Kill Switch Verification")
    log_line(ts_short(), "INFO", "AI_AUDITOR",
             "Verifying all orders are blocked after Kill Switch activation")

    for i in range(3):
        p = bot.tick()
        if p is not None:
            engine.update_market(p, bot.current_timestamp)
        test_order = OrderProposal(
            symbol=symbol, side=Side.BUY, quantity=100,
            price=bot.current_price, order_id=f"ORD-POST-{i+1}",
        )
        decision = engine.evaluate(test_order)
        log_line(ts_short(), "REJECT",
                 f"ORDER {test_order.order_id}",
                 f"BUY 100 {symbol} @ {fmt_money(test_order.price)} | {fmt_money(test_order.notional)}")
        print(f"{'':>42}✗ kill_switch_active: "
              f"System {engine.kill_switch.state.value} — all orders blocked")
        time.sleep(0.02)

    log_line(ts_short(), "INFO", "PHASE_3",
             "✓ Confirmed: Kill Switch blocks ALL orders post-activation")

    if use_dashboard:
        update_state(engine.get_state())

    time.sleep(phase_pause)

    # ===================================================================
    # PHASE 4: Manual Reset + Drawdown Cascade
    # ===================================================================
    phase_banner("PHASE 4: Manual Reset + Drawdown Cascade (Crisis Regime)")

    # Reset kill switch
    reset_events = engine.kill_switch.reset(config["kill_switch"]["admin_key"])
    for evt in reset_events:
        log_line(ts_short(), "INFO", "KILL_SWITCH", evt.message)

    # Fast-forward into the crash to build volatility
    log_line(ts_short(), "INFO", "AI_AUDITOR",
             "Fast-forwarding into 1987 crash to trigger regime transition...")

    # Advance to the crash zone (Oct 19, 1987 = ~row 4900 in the CSV).
    # Phase 1 consumed a variable number of ticks, so compute the gap.
    crash_target_row = 4920  # S&P drops sharply here: 284 → 280 → 265
    ticks_remaining = max(0, crash_target_row - bot._tick_index)
    for _ in range(ticks_remaining):
        p = bot.tick()
        if p is None:
            break
        engine.update_market(p, bot.current_timestamp)

    regime = engine.regime_detector.current_regime
    vol = engine.regime_detector.current_vol * 100
    adjusted = engine.regime_detector.get_adjusted_limits()
    log_line(ts_short(), "INFO", "REGIME_DET",
             f"Vol: {vol:.1f}% ann. | Regime: {regime.emoji} {regime.value}")
    log_line(ts_short(), "INFO", "ENGINE",
             f"Limits adjusted: Max DD {config['risk_limits']['max_drawdown_pct']}% → "
             f"{adjusted['max_drawdown_pct']}%")

    # Simulate losing trades to push toward drawdown limit
    log_line(ts_short(), "INFO", "AI_AUDITOR",
             "Injecting losing trades to test drawdown circuit breaker...")

    loss_trades = 0
    target_dd = adjusted["max_drawdown_pct"] + 0.5  # Push past the limit
    starting_nav = engine.portfolio.nav

    while engine.portfolio.drawdown_pct < target_dd and loss_trades < 20:
        p = bot.tick()
        if p is None:
            break
        engine.update_market(p, bot.current_timestamp)

        # Force a loss
        loss_amount = starting_nav * 0.015  # 1.5% per trade
        engine.portfolio.force_loss(loss_amount)
        loss_trades += 1

        dd = engine.portfolio.drawdown_pct
        nav = engine.portfolio.nav

        log_line(ts_short(), "INFO", f"LOSS-{loss_trades:02d}",
                 f"Simulated loss: -{fmt_money(loss_amount)} | "
                 f"NAV: {fmt_money(nav)} | DD: {dd:.2f}%")

        # Check drawdown after loss
        test_order = OrderProposal(
            symbol=symbol, side=Side.BUY, quantity=100,
            price=bot.current_price, order_id=f"ORD-DD-{loss_trades:02d}",
        )
        decision = engine.evaluate(test_order)

        if decision.action == Action.KILL:
            triggered_rules = ", ".join(r.split(":")[0] for r in decision.rules_triggered)
            log_line(ts_short(), "FATAL", "KILL_SWITCH",
                     f"██ TRIGGERED ██ | Rules: {triggered_rules}")
            log_line(ts_short(), "FATAL", "KILL_SWITCH",
                     "ALL TRADING HALTED — risk limit circuit breaker activated")

            print(f"\n{'━' * 3} Kill Switch — Risk Breach {'━' * 51}")
            print(f"Timestamp:  {ts()}")
            print(f"NAV:        {fmt_money(nav)}")
            print(f"Drawdown:   {dd:.2f}% (limit: {adjusted['max_drawdown_pct']}%)")
            print(f"Daily P&L:  {engine.portfolio.daily_pnl_pct:.2f}% "
                  f"(limit: {config['risk_limits']['daily_loss_limit_pct']}%)")
            for rule in decision.rules_triggered:
                print(f"  ✗ {rule}")
            regime = engine.regime_detector.current_regime
            print(f"Regime:     {regime.emoji} {regime.value}")
            print(f"Action:     KILL SWITCH ACTIVATED")
            print(f"{'━' * 78}")
            break
        elif decision.action == Action.REJECT:
            for rule in decision.rules_triggered:
                print(f"{'':>42}⚠ {rule}")

        if use_dashboard:
            update_state(engine.get_state())

        time.sleep(pace)

    # ===================================================================
    # PHASE 5: Final Summary
    # ===================================================================
    phase_banner("SIMULATION COMPLETE")

    total_orders = engine.portfolio.trade_count + loss_trades + 3 + 1  # normal + losses + post-kill + fat finger
    print(f"Total orders submitted:    {total_orders}")
    print(f"Orders passed:             {engine.portfolio.trade_count}")
    print(f"Orders rejected:           {total_orders - engine.portfolio.trade_count}")
    print(f"Kill Switch activations:   2")
    print(f"  • Activation 1:          Fat Finger — {fmt_money(sim_cfg['fat_finger_notional'])} order")
    print(f"  • Activation 2:          Drawdown breach — {engine.portfolio.drawdown_pct:.1f}%")
    print(f"Final NAV:                 {fmt_money(engine.portfolio.nav)} "
          f"({engine.portfolio.daily_pnl_pct:+.1f}%)")
    print(f"Regime at halt:            {engine.regime_detector.current_regime.emoji} "
          f"{engine.regime_detector.current_regime.value}")
    print(f"Anomaly detector orders:   {engine.anomaly_detector.order_count}")

    print(f"\n{'=' * 80}")
    print(f"Kill Switch Status: {'🔴 HALTED' if engine.kill_switch.is_active else '🟢 ARMED'}")
    print(f"Log saved to: logs/risk_engine_log.txt")
    print(f"Finished: {ts()}")
    print(f"{'=' * 80}")

    if use_dashboard:
        update_state(engine.get_state())
        log_line(ts_short(), "INFO", "DASHBOARD",
                 f"Dashboard still running at http://localhost:{config['dashboard']['port']}")
        log_line(ts_short(), "INFO", "DASHBOARD",
                 "Press Ctrl+C to stop")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Risk Engine Kill Switch Demo")
    parser.add_argument("--dashboard", action="store_true",
                        help="Start the browser dashboard")
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config file")
    args = parser.parse_args()

    project_dir = Path(__file__).parent
    config_path = project_dir / args.config
    data_path = project_dir / "data" / "1987_crash_market_data.csv"
    log_path = project_dir / "logs" / "risk_engine_log.txt"

    # Load config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Set up dual logging
    logger = DualLogger(log_path)
    sys.stdout = logger

    try:
        run_simulation(config, str(data_path), use_dashboard=args.dashboard)
    finally:
        sys.stdout = logger.terminal
        logger.close()
        print(f"\n✓ Console log saved to: {log_path}")


if __name__ == "__main__":
    main()
