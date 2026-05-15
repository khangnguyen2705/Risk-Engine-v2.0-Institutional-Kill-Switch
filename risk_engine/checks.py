"""Static pre-trade risk checks.

Each function returns (passed: bool, reason: str).
The reason is human-readable and logged on failure.
"""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.data_models import OrderProposal, PortfolioSnapshot


def check_fat_finger_notional(order: OrderProposal, max_notional: float) -> tuple[bool, str]:
    """Reject orders exceeding the maximum notional value."""
    if order.notional > max_notional:
        return False, (
            f"fat_finger_notional: ${order.notional:,.2f} > ${max_notional:,.2f} limit"
        )
    return True, ""


def check_fat_finger_quantity(order: OrderProposal, max_quantity: float) -> tuple[bool, str]:
    """Reject orders exceeding the maximum share count."""
    if abs(order.quantity) > max_quantity:
        return False, (
            f"fat_finger_quantity: {abs(order.quantity):,.0f} > {max_quantity:,.0f} limit"
        )
    return True, ""


def check_max_drawdown(drawdown_pct: float, max_dd_pct: float) -> tuple[bool, str]:
    """Reject if portfolio drawdown exceeds the (regime-adjusted) limit."""
    if drawdown_pct > max_dd_pct:
        return False, (
            f"max_drawdown: {drawdown_pct:.2f}% > {max_dd_pct:.2f}% limit"
        )
    return True, ""


def check_position_concentration(
    order: OrderProposal,
    current_position_value: float,
    nav: float,
    max_concentration_pct: float,
) -> tuple[bool, str]:
    """Reject if post-trade concentration exceeds limit."""
    if nav <= 0:
        return True, ""
    post_trade_value = abs(current_position_value + order.notional)
    concentration = (post_trade_value / nav) * 100
    if concentration > max_concentration_pct:
        return False, (
            f"position_concentration: {concentration:.1f}% > "
            f"{max_concentration_pct:.1f}% NAV limit"
        )
    return True, ""


class VelocityTracker:
    """Tracks order submission rate for velocity checks."""

    def __init__(self, max_per_second: int = 50):
        self.max_per_second = max_per_second
        self._timestamps: deque[float] = deque()

    def check(self, order: OrderProposal) -> tuple[bool, str]:
        now = time.time()
        # Prune entries older than 1 second
        while self._timestamps and now - self._timestamps[0] > 1.0:
            self._timestamps.popleft()
        self._timestamps.append(now)

        if len(self._timestamps) > self.max_per_second:
            return False, (
                f"order_velocity: {len(self._timestamps)} orders/sec > "
                f"{self.max_per_second}/sec limit"
            )
        return True, ""


def check_daily_loss(daily_pnl_pct: float, max_daily_loss_pct: float) -> tuple[bool, str]:
    """Reject if daily loss exceeds the limit."""
    if abs(daily_pnl_pct) > max_daily_loss_pct and daily_pnl_pct < 0:
        return False, (
            f"daily_loss: {daily_pnl_pct:.2f}% > {max_daily_loss_pct:.2f}% limit"
        )
    return True, ""
