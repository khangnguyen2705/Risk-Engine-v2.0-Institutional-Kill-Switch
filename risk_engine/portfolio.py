"""Portfolio & position tracker with real-time P&L and drawdown."""

from __future__ import annotations

from models.data_models import (
    OrderProposal, Position, PortfolioSnapshot,
    Side, RegimeState, KillSwitchState,
)


class Portfolio:
    """Tracks positions, cash, NAV, high-water mark, and drawdown."""

    def __init__(self, starting_capital: float):
        self.cash = starting_capital
        self.starting_capital = starting_capital
        self.positions: dict[str, Position] = {}
        self.high_water_mark = starting_capital
        self.realized_pnl = 0.0
        self.daily_starting_nav = starting_capital
        self.trade_count = 0

    @property
    def nav(self) -> float:
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash + position_value

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def drawdown_pct(self) -> float:
        if self.high_water_mark <= 0:
            return 0.0
        return max(0.0, (self.high_water_mark - self.nav) / self.high_water_mark * 100)

    @property
    def daily_pnl(self) -> float:
        return self.nav - self.daily_starting_nav

    @property
    def daily_pnl_pct(self) -> float:
        if self.daily_starting_nav <= 0:
            return 0.0
        return (self.nav - self.daily_starting_nav) / self.daily_starting_nav * 100

    def mark_to_market(self, symbol: str, price: float):
        """Update mark price for a position."""
        if symbol in self.positions:
            self.positions[symbol].mark_price = price
        # Update HWM
        current_nav = self.nav
        if current_nav > self.high_water_mark:
            self.high_water_mark = current_nav

    def get_position_value(self, symbol: str) -> float:
        """Get current market value of a position."""
        if symbol not in self.positions:
            return 0.0
        return abs(self.positions[symbol].market_value)

    def on_fill(self, order: OrderProposal, fill_price: float):
        """Process an order fill — update position and cash."""
        self.trade_count += 1
        symbol = order.symbol
        qty = order.quantity if order.side == Side.BUY else -order.quantity

        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=0.0,
                avg_entry=0.0,
                mark_price=fill_price,
            )

        pos = self.positions[symbol]
        old_qty = pos.quantity

        if old_qty == 0:
            # New position
            pos.quantity = qty
            pos.avg_entry = fill_price
        elif (old_qty > 0 and qty > 0) or (old_qty < 0 and qty < 0):
            # Adding to position — weighted average entry
            total_qty = old_qty + qty
            pos.avg_entry = (old_qty * pos.avg_entry + qty * fill_price) / total_qty
            pos.quantity = total_qty
        else:
            # Reducing / closing / flipping
            close_qty = min(abs(qty), abs(old_qty))
            pnl = close_qty * (fill_price - pos.avg_entry) * (1 if old_qty > 0 else -1)
            self.realized_pnl += pnl
            self.cash += pnl

            remaining = old_qty + qty
            if abs(remaining) < 1e-9:
                pos.quantity = 0.0
                pos.avg_entry = 0.0
            elif (remaining > 0) != (old_qty > 0):
                # Flipped direction
                pos.quantity = remaining
                pos.avg_entry = fill_price
            else:
                pos.quantity = remaining

        pos.mark_price = fill_price
        # Deduct/add cash for the trade
        self.cash -= qty * fill_price

        # Update HWM
        current_nav = self.nav
        if current_nav > self.high_water_mark:
            self.high_water_mark = current_nav

    def force_loss(self, amount: float):
        """Simulate a loss without a fill (for drawdown testing)."""
        self.cash -= amount
        self.realized_pnl -= amount

    def flatten_all(self) -> float:
        """Close all positions at mark price. Returns total realized P&L."""
        total_pnl = 0.0
        for symbol, pos in list(self.positions.items()):
            if pos.quantity == 0:
                continue
            pnl = pos.unrealized_pnl
            self.cash += pos.market_value
            self.realized_pnl += pnl
            total_pnl += pnl
            pos.quantity = 0.0
            pos.avg_entry = 0.0
        return total_pnl

    def get_snapshot(self, regime: RegimeState, ks_state: KillSwitchState) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            cash=self.cash,
            positions=dict(self.positions),
            nav=self.nav,
            high_water_mark=self.high_water_mark,
            drawdown_pct=self.drawdown_pct,
            daily_pnl=self.daily_pnl,
            daily_pnl_pct=self.daily_pnl_pct,
            regime=regime,
            kill_switch_state=ks_state,
        )
