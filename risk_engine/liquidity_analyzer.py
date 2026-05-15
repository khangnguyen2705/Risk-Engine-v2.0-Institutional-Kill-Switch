"""Upgrade 3 — Liquidity-Aware Impact Estimation.

Maintains a synthetic order book derived from the price feed and estimates
market impact for incoming orders using Kyle's Lambda, book depth ratio,
and walk-the-book slippage estimation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from models.data_models import OrderProposal


@dataclass
class LiquidityReport:
    estimated_slippage_pct: float
    book_depth_ratio_pct: float
    kyle_lambda_impact_bps: float
    total_book_depth: float
    mid_price: float
    passed_slippage: bool
    passed_depth: bool
    reason: str


class LiquidityAnalyzer:
    """Synthetic order-book and market-impact estimator."""

    def __init__(
        self,
        book_levels: int = 5,
        base_spread_bps: float = 5.0,
        base_depth_per_level: float = 50_000,
        max_slippage_pct: float = 2.0,
        max_depth_ratio_pct: float = 30.0,
        kyle_lambda_warn_bps: float = 50.0,
    ):
        self.book_levels = book_levels
        self.base_spread_bps = base_spread_bps
        self.base_depth_per_level = base_depth_per_level
        self.max_slippage_pct = max_slippage_pct
        self.max_depth_ratio_pct = max_depth_ratio_pct
        self.kyle_lambda_warn_bps = kyle_lambda_warn_bps

        self._mid_price = 0.0
        self._vol_multiplier = 1.0  # Widens spread in volatile regimes

    def update(self, mid_price: float, vol_ann: float = 0.0):
        """Update the synthetic book with the latest mid price and vol."""
        self._mid_price = mid_price
        # In crisis, spread widens: vol > 30% → multiplier up to 5×
        self._vol_multiplier = max(1.0, 1.0 + (vol_ann - 0.15) * 10) if vol_ann > 0.15 else 1.0

    def _build_book(self) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Generate a synthetic 5-level bid/ask book."""
        spread_pct = self.base_spread_bps / 10_000 * self._vol_multiplier
        half_spread = self._mid_price * spread_pct / 2
        depth = self.base_depth_per_level

        bids, asks = [], []
        for i in range(self.book_levels):
            bid_price = self._mid_price - half_spread * (1 + i * 0.5)
            ask_price = self._mid_price + half_spread * (1 + i * 0.5)
            # Deeper levels have more liquidity
            level_depth = depth * (1 + i * 0.3)
            bid_qty = level_depth / bid_price if bid_price > 0 else 0
            ask_qty = level_depth / ask_price if ask_price > 0 else 0
            bids.append((bid_price, bid_qty))
            asks.append((ask_price, ask_qty))

        return bids, asks

    def estimate_impact(self, order: OrderProposal) -> LiquidityReport:
        """Estimate the market impact of an order."""
        if self._mid_price <= 0:
            return LiquidityReport(
                estimated_slippage_pct=0, book_depth_ratio_pct=0,
                kyle_lambda_impact_bps=0, total_book_depth=0,
                mid_price=0, passed_slippage=True, passed_depth=True, reason="",
            )

        bids, asks = self._build_book()
        book = asks if order.side.value == "BUY" else bids
        total_depth = sum(price * qty for price, qty in book)
        order_qty = abs(order.quantity)

        # Walk the book to compute fill price
        remaining = order_qty
        total_cost = 0.0
        for price, qty in book:
            fill = min(remaining, qty)
            total_cost += fill * price
            remaining -= fill
            if remaining <= 0:
                break

        if remaining > 0:
            # Order exceeds entire book — use worst price extrapolated
            worst_price = book[-1][0] * (1 + remaining / order_qty)
            total_cost += remaining * worst_price

        avg_fill = total_cost / order_qty if order_qty > 0 else self._mid_price
        slippage_pct = abs(avg_fill - self._mid_price) / self._mid_price * 100

        # Book depth ratio
        depth_ratio = (order.notional / total_depth * 100) if total_depth > 0 else 999.0

        # Kyle's Lambda estimate: ΔP/ΔQ (simplified)
        kyle_lambda = (slippage_pct / 100 * self._mid_price) / order_qty if order_qty > 0 else 0
        kyle_impact_bps = slippage_pct * 100  # Convert to bps

        passed_slip = slippage_pct <= self.max_slippage_pct
        passed_depth = depth_ratio <= self.max_depth_ratio_pct

        reasons = []
        if not passed_slip:
            reasons.append(f"market_impact: slippage={slippage_pct:.1f}% > {self.max_slippage_pct}% limit")
        if not passed_depth:
            reasons.append(f"book_depth: ratio={depth_ratio:.1f}% > {self.max_depth_ratio_pct}% limit")

        return LiquidityReport(
            estimated_slippage_pct=round(slippage_pct, 2),
            book_depth_ratio_pct=round(depth_ratio, 2),
            kyle_lambda_impact_bps=round(kyle_impact_bps, 2),
            total_book_depth=round(total_depth, 2),
            mid_price=self._mid_price,
            passed_slippage=passed_slip,
            passed_depth=passed_depth,
            reason=" | ".join(reasons),
        )
