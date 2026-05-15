"""Core Risk Engine — the 10-layer pre-trade gate.

Every OrderProposal must pass through ``evaluate()`` before execution.
The engine orchestrates static checks, adaptive anomaly detection,
regime-aware drawdown limits, and liquidity impact estimation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from models.data_models import (
    OrderProposal, RiskDecision, RiskEvent,
    Action, Severity, Side,
)
from risk_engine.checks import (
    check_fat_finger_notional, check_fat_finger_quantity,
    check_max_drawdown, check_position_concentration,
    check_daily_loss, VelocityTracker,
)
from risk_engine.kill_switch import KillSwitch
from risk_engine.portfolio import Portfolio
from risk_engine.anomaly_detector import AnomalyDetector
from risk_engine.regime_detector import RegimeDetector
from risk_engine.liquidity_analyzer import LiquidityAnalyzer


class RiskEngine:
    """Institutional-grade pre-trade risk gate with kill switch."""

    def __init__(self, config: dict):
        limits = config["risk_limits"]
        anomaly_cfg = config.get("anomaly", {})
        regime_cfg = config.get("regime", {})
        liq_cfg = config.get("liquidity", {})
        ks_cfg = config.get("kill_switch", {})

        # Portfolio
        self.portfolio = Portfolio(config["portfolio"]["starting_capital"])

        # Static limits
        self.max_notional = limits["max_notional"]
        self.max_quantity = limits["max_quantity"]
        self.max_concentration_pct = limits["max_concentration_pct"]
        self.max_daily_loss_pct = limits["daily_loss_limit_pct"]
        self.base_max_drawdown_pct = limits["max_drawdown_pct"]

        # Components
        self.kill_switch = KillSwitch(admin_key=ks_cfg.get("admin_key", "OVERRIDE-2026"))
        self.velocity_tracker = VelocityTracker(limits["max_velocity_per_sec"])

        self.anomaly_detector = AnomalyDetector(
            window_size=anomaly_cfg.get("window_size", 100),
            warmup=anomaly_cfg.get("warmup_orders", 10),
            z_threshold=anomaly_cfg.get("z_score_threshold", 4.0),
        )

        overrides = {}
        for regime_name in ("calm", "elevated", "crisis"):
            cfg_block = regime_cfg.get("overrides", {}).get(regime_name, {})
            overrides[regime_name.upper()] = {
                "max_drawdown_pct": cfg_block.get("max_drawdown_pct", self.base_max_drawdown_pct),
                "position_size_mult": cfg_block.get("position_size_mult", 1.0),
            }

        self.regime_detector = RegimeDetector(
            vol_window=regime_cfg.get("vol_window", 20),
            calm_max_vol=regime_cfg.get("thresholds", {}).get("calm_max_vol", 0.15),
            elevated_max_vol=regime_cfg.get("thresholds", {}).get("elevated_max_vol", 0.30),
            annualization_factor=regime_cfg.get("annualization_factor", 252),
            overrides=overrides,
        )

        self.liquidity_analyzer = LiquidityAnalyzer(
            book_levels=liq_cfg.get("book_levels", 5),
            base_spread_bps=liq_cfg.get("base_spread_bps", 5.0),
            base_depth_per_level=liq_cfg.get("base_depth_per_level", 50_000),
            max_slippage_pct=liq_cfg.get("max_slippage_pct", 2.0),
            max_depth_ratio_pct=liq_cfg.get("max_book_depth_ratio_pct", 30.0),
        )

        # Event log
        self.events: list[RiskEvent] = []

    def _log(self, event: RiskEvent):
        self.events.append(event)

    def _log_many(self, events: list[RiskEvent]):
        self.events.extend(events)

    def update_market(self, price: float, timestamp: str = ""):
        """Feed a price tick to the regime detector & liquidity analyzer."""
        regime_events = self.regime_detector.update(price, timestamp)
        self._log_many(regime_events)
        self.liquidity_analyzer.update(price, self.regime_detector.current_vol)

    def evaluate(self, order: OrderProposal) -> RiskDecision:
        """Run all 10 pre-trade checks. Returns PASS, REJECT, or KILL."""
        now = datetime.now(timezone.utc).isoformat()
        failures: list[str] = []
        details: dict = {}
        is_kill_level = False

        # Check 0: Kill switch already active?
        if self.kill_switch.is_active:
            return RiskDecision(
                order_id=order.order_id,
                action=Action.REJECT,
                rules_triggered=("kill_switch_active",),
                details={"reason": f"System {self.kill_switch.state.value} — all orders blocked"},
                timestamp=now,
            )

        # Check 1: Fat Finger (Notional)
        ok, reason = check_fat_finger_notional(order, self.max_notional)
        if not ok:
            failures.append(reason)
            is_kill_level = order.notional > self.max_notional * 10  # 10× = kill level

        # Check 2: Fat Finger (Quantity)
        ok, reason = check_fat_finger_quantity(order, self.max_quantity)
        if not ok:
            failures.append(reason)

        # Check 3: Adaptive Anomaly (Upgrade 1)
        anomaly = self.anomaly_detector.score(order)
        details["anomaly_z"] = anomaly.composite_z
        details["anomaly_warmup"] = anomaly.in_warmup
        if anomaly.is_anomalous:
            failures.append(
                f"anomaly_z_score: z={anomaly.composite_z} (threshold: "
                f"{self.anomaly_detector.z_threshold})"
            )

        # Check 4: Regime-Adjusted Drawdown (Upgrade 2)
        adjusted = self.regime_detector.get_adjusted_limits()
        max_dd = adjusted["max_drawdown_pct"]
        details["regime"] = self.regime_detector.current_regime.value
        details["regime_max_dd"] = max_dd
        ok, reason = check_max_drawdown(self.portfolio.drawdown_pct, max_dd)
        if not ok:
            failures.append(reason)
            is_kill_level = True

        # Check 5 & 6: Liquidity Impact (Upgrade 3)
        liq = self.liquidity_analyzer.estimate_impact(order)
        details["slippage_pct"] = liq.estimated_slippage_pct
        details["depth_ratio_pct"] = liq.book_depth_ratio_pct
        details["kyle_impact_bps"] = liq.kyle_lambda_impact_bps
        if not liq.passed_slippage:
            failures.append(
                f"market_impact: slippage={liq.estimated_slippage_pct}% > "
                f"{self.liquidity_analyzer.max_slippage_pct}% limit"
            )
        if not liq.passed_depth:
            failures.append(
                f"book_depth: ratio={liq.book_depth_ratio_pct:.1f}% > "
                f"{self.liquidity_analyzer.max_depth_ratio_pct}% limit"
            )

        # Check 7: Position Concentration
        pos_val = self.portfolio.get_position_value(order.symbol)
        ok, reason = check_position_concentration(
            order, pos_val, self.portfolio.nav, self.max_concentration_pct
        )
        if not ok:
            failures.append(reason)

        # Check 8: Order Velocity
        ok, reason = self.velocity_tracker.check(order)
        if not ok:
            failures.append(reason)

        # Check 9: Daily Loss
        ok, reason = check_daily_loss(
            self.portfolio.daily_pnl_pct, self.max_daily_loss_pct
        )
        if not ok:
            failures.append(reason)
            is_kill_level = True

        # --- Decision ---
        if not failures:
            # All checks passed — record for anomaly baseline
            self.anomaly_detector.record(order)
            return RiskDecision(
                order_id=order.order_id,
                action=Action.PASS,
                details=details,
                timestamp=now,
            )

        # At least one failure
        details["rules_failed"] = len(failures)
        details["rules_total"] = 10

        if is_kill_level:
            ks_events = self.kill_switch.trigger(failures[0])
            self._log_many(ks_events)
            # Auto-flatten: close all positions on kill
            flatten_pnl = self.portfolio.flatten_all()
            if flatten_pnl != 0:
                self._log(RiskEvent(
                    event_type="AUTO_FLATTEN",
                    severity=Severity.FATAL,
                    message=f"Positions flattened — realized P&L: ${flatten_pnl:,.2f}",
                    timestamp=now,
                ))
            return RiskDecision(
                order_id=order.order_id,
                action=Action.KILL,
                rules_triggered=tuple(failures),
                details=details,
                timestamp=now,
            )

        return RiskDecision(
            order_id=order.order_id,
            action=Action.REJECT,
            rules_triggered=tuple(failures),
            details=details,
            timestamp=now,
        )

    def on_fill(self, order: OrderProposal, fill_price: float):
        """Post-trade: update positions and run post-trade checks."""
        self.portfolio.on_fill(order, fill_price)
        self.portfolio.mark_to_market(order.symbol, fill_price)

    def get_state(self) -> dict:
        """Full engine state for the dashboard API."""
        return {
            "portfolio": {
                "cash": round(self.portfolio.cash, 2),
                "nav": round(self.portfolio.nav, 2),
                "hwm": round(self.portfolio.high_water_mark, 2),
                "drawdown_pct": round(self.portfolio.drawdown_pct, 4),
                "daily_pnl": round(self.portfolio.daily_pnl, 2),
                "daily_pnl_pct": round(self.portfolio.daily_pnl_pct, 4),
                "trade_count": self.portfolio.trade_count,
                "positions": {
                    s: {"qty": p.quantity, "avg_entry": p.avg_entry,
                        "mark": p.mark_price, "upnl": round(p.unrealized_pnl, 2)}
                    for s, p in self.portfolio.positions.items()
                },
            },
            "regime": {
                "state": self.regime_detector.current_regime.value,
                "emoji": self.regime_detector.current_regime.emoji,
                "vol": round(self.regime_detector.current_vol * 100, 2),
                "limits": self.regime_detector.get_adjusted_limits(),
            },
            "kill_switch": {
                "state": self.kill_switch.state.value,
                "is_active": self.kill_switch.is_active,
                "trigger_reason": self.kill_switch.trigger_reason,
                "trigger_time": self.kill_switch.trigger_time,
            },
            "anomaly": {
                "order_count": self.anomaly_detector.order_count,
                "in_warmup": self.anomaly_detector.in_warmup,
            },
            "liquidity": {
                "mid_price": self.liquidity_analyzer._mid_price,
                "vol_multiplier": round(self.liquidity_analyzer._vol_multiplier, 2),
            },
            "events": [
                {
                    "type": e.event_type,
                    "severity": e.severity.value,
                    "message": e.message,
                    "timestamp": e.timestamp,
                }
                for e in self.events[-50:]  # Last 50 events
            ],
        }
