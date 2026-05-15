"""Domain models — immutable dataclasses with nanosecond-precision timestamps.

Every entity that crosses a module boundary is defined here so the entire
system shares a single source of truth for its vocabulary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class Action(Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    KILL = "KILL"


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARN"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class KillSwitchState(Enum):
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    HALTED = "HALTED"


class RegimeState(Enum):
    CALM = "CALM"
    ELEVATED = "ELEVATED"
    CRISIS = "CRISIS"

    @property
    def emoji(self) -> str:
        return {"CALM": "🟢", "ELEVATED": "🟡", "CRISIS": "🔴"}[self.value]


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderProposal:
    """A trade request from the Trader bot."""
    symbol: str
    side: Side
    quantity: float
    price: float
    strategy_id: str = "momentum_v1"
    order_id: str = field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.price)


@dataclass(frozen=True)
class RiskDecision:
    """Verdict from the Risk Engine for a given order."""
    order_id: str
    action: Action
    rules_triggered: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Position:
    """A single position in the portfolio."""
    symbol: str
    quantity: float = 0.0
    avg_entry: float = 0.0
    mark_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.mark_price

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity == 0:
            return 0.0
        return self.quantity * (self.mark_price - self.avg_entry)


@dataclass
class PortfolioSnapshot:
    """Full portfolio state at a point in time."""
    cash: float
    positions: dict[str, Position]
    nav: float
    high_water_mark: float
    drawdown_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    regime: RegimeState
    kill_switch_state: KillSwitchState
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class RiskEvent:
    """An entry in the audit trail."""
    event_type: str
    severity: Severity
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
