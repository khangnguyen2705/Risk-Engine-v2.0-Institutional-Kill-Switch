"""Upgrade 2 — Regime-Aware Dynamic Circuit Breakers.

Classifies the market into CALM / ELEVATED / CRISIS based on rolling
realised volatility, and returns regime-specific risk limit overrides.
During the 1987 crash simulation, the detector transitions 🟢→🟡→🔴
as volatility spikes, automatically tightening drawdown limits and
position size caps.
"""

from __future__ import annotations

import math
from collections import deque

from models.data_models import RegimeState, RiskEvent, Severity


class RegimeDetector:
    """Volatility-based market regime classifier."""

    def __init__(
        self,
        vol_window: int = 20,
        calm_max_vol: float = 0.15,
        elevated_max_vol: float = 0.30,
        annualization_factor: int = 252,
        overrides: dict | None = None,
    ):
        self.vol_window = vol_window
        self.calm_max_vol = calm_max_vol
        self.elevated_max_vol = elevated_max_vol
        self.annualization_factor = annualization_factor
        self._prices: deque[float] = deque(maxlen=vol_window + 1)
        self._current_regime = RegimeState.CALM
        self._current_vol = 0.0
        self.events: list[RiskEvent] = []

        self.overrides = overrides or {
            "CALM": {"max_drawdown_pct": 15.0, "position_size_mult": 1.0},
            "ELEVATED": {"max_drawdown_pct": 10.0, "position_size_mult": 0.5},
            "CRISIS": {"max_drawdown_pct": 8.0, "position_size_mult": 0.25},
        }

    @property
    def current_regime(self) -> RegimeState:
        return self._current_regime

    @property
    def current_vol(self) -> float:
        return self._current_vol

    def update(self, price: float, timestamp: str = "") -> list[RiskEvent]:
        """Feed a new price tick. Returns events if regime changes."""
        self._prices.append(price)

        if len(self._prices) < 3:
            return []

        # Compute log returns
        returns = []
        prices = list(self._prices)
        for i in range(1, len(prices)):
            if prices[i - 1] > 0 and prices[i] > 0:
                returns.append(math.log(prices[i] / prices[i - 1]))

        if not returns:
            return []

        # Realised volatility (annualised)
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        daily_vol = math.sqrt(var)
        ann_vol = daily_vol * math.sqrt(self.annualization_factor)
        self._current_vol = ann_vol

        # Classify regime
        old_regime = self._current_regime
        if ann_vol < self.calm_max_vol:
            self._current_regime = RegimeState.CALM
        elif ann_vol < self.elevated_max_vol:
            self._current_regime = RegimeState.ELEVATED
        else:
            self._current_regime = RegimeState.CRISIS

        events = []
        if self._current_regime != old_regime:
            evt = RiskEvent(
                event_type="REGIME_CHANGE",
                severity=Severity.WARNING,
                message=(
                    f"Regime transition: {old_regime.emoji} {old_regime.value} → "
                    f"{self._current_regime.emoji} {self._current_regime.value} "
                    f"| Vol: {ann_vol*100:.1f}% ann."
                ),
                context={
                    "old_regime": old_regime.value,
                    "new_regime": self._current_regime.value,
                    "vol": round(ann_vol, 4),
                },
                timestamp=timestamp,
            )
            events.append(evt)
            self.events.extend(events)

        return events

    def get_adjusted_limits(self) -> dict:
        """Return the regime-specific risk limit overrides."""
        return dict(self.overrides.get(self._current_regime.value, self.overrides["CALM"]))
