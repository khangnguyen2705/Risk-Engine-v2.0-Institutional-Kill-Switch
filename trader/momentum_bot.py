"""Momentum Trader Bot — reads market data and generates OrderProposals.

Uses a 5-bar momentum signal on S&P 500 Futures from the 1987 crash
dataset. Normal orders are sized $50K–$500K. The ``inject_fat_finger``
method allows the AI Auditor to override the next order with a $1B trade.
"""

from __future__ import annotations

import csv
from pathlib import Path
from collections import deque

from models.data_models import OrderProposal, Side


class MomentumBot:
    """Simulated momentum trader bot."""

    def __init__(
        self,
        data_path: str | Path,
        symbol: str = "SP500_Futures",
        lookback: int = 5,
        base_notional: float = 200_000,  # $200K base
    ):
        self.symbol = symbol
        self.lookback = lookback
        self.base_notional = base_notional
        self._prices: deque[float] = deque(maxlen=lookback + 1)
        self._timestamps: list[str] = []
        self._all_rows: list[dict] = []
        self._tick_index = 0
        self._fat_finger_pending = False
        self._fat_finger_notional = 0.0
        self._order_counter = 0

        # Load market data
        self._load_data(data_path, symbol)

    def _load_data(self, path: str | Path, symbol: str):
        path = Path(path)
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self._all_rows.append(row)

    @property
    def total_ticks(self) -> int:
        return len(self._all_rows)

    @property
    def current_price(self) -> float:
        if not self._prices:
            return 0.0
        return self._prices[-1]

    @property
    def current_timestamp(self) -> str:
        if self._tick_index > 0 and self._tick_index <= len(self._all_rows):
            return self._all_rows[self._tick_index - 1].get("Timestamp", "")
        return ""

    def tick(self) -> float | None:
        """Advance one tick. Returns the price, or None if data exhausted."""
        if self._tick_index >= len(self._all_rows):
            return None
        row = self._all_rows[self._tick_index]
        self._tick_index += 1
        try:
            price = float(row.get(self.symbol, row.get("SP500_Futures", "0")))
        except (ValueError, TypeError):
            # Handle non-numeric entries like "Halted" during crash
            return self._prices[-1] if self._prices else None
        self._prices.append(price)
        return price

    def should_trade(self) -> bool:
        """Returns True if we have enough history to generate a signal."""
        return len(self._prices) >= self.lookback + 1

    def generate_signal(self) -> float:
        """5-bar momentum: price / SMA(5) - 1."""
        prices = list(self._prices)
        sma = sum(prices[-self.lookback:]) / self.lookback
        if sma <= 0:
            return 0.0
        return (prices[-1] / sma) - 1.0

    def create_order(self) -> OrderProposal | None:
        """Generate an OrderProposal based on the current signal."""
        if not self.should_trade():
            return None

        # Check for fat finger override
        if self._fat_finger_pending:
            self._fat_finger_pending = False
            self._order_counter += 1
            price = self.current_price
            quantity = self._fat_finger_notional / price if price > 0 else 1_000_000
            return OrderProposal(
                symbol=self.symbol,
                side=Side.BUY,
                quantity=round(quantity, 0),
                price=price,
                order_id=f"ORD-{self._order_counter:04d}",
                strategy_id="momentum_v1_FAT_FINGER",
            )

        signal = self.generate_signal()
        if abs(signal) < 0.0005:  # Dead zone
            return None

        self._order_counter += 1
        price = self.current_price
        # Scale notional by signal strength (capped at 2.5× base)
        scale = min(abs(signal) * 50, 2.5)
        notional = self.base_notional * max(scale, 0.25)
        quantity = round(notional / price, 0) if price > 0 else 100

        side = Side.BUY if signal > 0 else Side.SELL

        return OrderProposal(
            symbol=self.symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_id=f"ORD-{self._order_counter:04d}",
            strategy_id="momentum_v1",
        )

    def inject_fat_finger(self, target_notional: float = 1_000_000_000):
        """Queue a fat-finger order for the next trade."""
        self._fat_finger_pending = True
        self._fat_finger_notional = target_notional
