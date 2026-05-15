"""AI Auditor — Scenario Injector.

Orchestrates the 5-phase demo by commanding the Trader bot and
verifying Risk Engine responses. Each phase has clear visual
separators and timestamped logging.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from models.data_models import Action, RiskEvent, Severity


class ScenarioInjector:
    """Orchestrates adversarial test scenarios against the Risk Engine."""

    def __init__(self, config: dict):
        self.normal_trades = config["simulation"]["normal_trades_before_fat_finger"]
        self.fat_finger_notional = config["simulation"]["fat_finger_notional"]
        self.trade_frequency = config["simulation"].get("trade_frequency", 5)
        self.admin_key = config["kill_switch"]["admin_key"]
        self.events: list[RiskEvent] = []

    def log_event(self, msg: str, severity: Severity = Severity.WARNING) -> RiskEvent:
        evt = RiskEvent(
            event_type="AI_AUDITOR",
            severity=severity,
            message=msg,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.events.append(evt)
        return evt
