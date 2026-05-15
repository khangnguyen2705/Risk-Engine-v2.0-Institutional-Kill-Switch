"""Upgrade 1 — Adaptive Anomaly Detection.

Instead of relying solely on static thresholds, this module maintains a
rolling behavioural profile of the trader and flags orders whose notional,
quantity, or inter-order timing deviate significantly (z-score) from the
recent baseline.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

from models.data_models import OrderProposal


@dataclass
class AnomalyScore:
    z_notional: float
    z_quantity: float
    z_timing: float
    composite_z: float
    is_anomalous: bool
    in_warmup: bool


class AnomalyDetector:
    """Rolling z-score anomaly detector for order flow."""

    def __init__(self, window_size: int = 100, warmup: int = 10, z_threshold: float = 4.0):
        self.window_size = window_size
        self.warmup = warmup
        self.z_threshold = z_threshold
        self._notionals: deque[float] = deque(maxlen=window_size)
        self._quantities: deque[float] = deque(maxlen=window_size)
        self._intervals: deque[float] = deque(maxlen=window_size)
        self._last_order_time: float | None = None

    @property
    def order_count(self) -> int:
        return len(self._notionals)

    @property
    def in_warmup(self) -> bool:
        return self.order_count < self.warmup

    def _z_score(self, value: float, history: deque[float]) -> float:
        if len(history) < self.warmup:
            return 0.0
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std = math.sqrt(variance) if variance > 0 else abs(mean) * 0.01 + 1.0
        return abs(value - mean) / std

    def score(self, order: OrderProposal) -> AnomalyScore:
        """Score an order against the trader's behavioural baseline."""
        z_n = self._z_score(order.notional, self._notionals)
        z_q = self._z_score(abs(order.quantity), self._quantities)

        # Timing z-score: inter-order interval
        z_t = 0.0
        now = time.time()
        if self._last_order_time is not None and len(self._intervals) >= self.warmup:
            interval = now - self._last_order_time
            z_t = self._z_score(interval, self._intervals)

        composite = max(z_n, z_q, z_t)

        result = AnomalyScore(
            z_notional=round(z_n, 2),
            z_quantity=round(z_q, 2),
            z_timing=round(z_t, 2),
            composite_z=round(composite, 2),
            is_anomalous=composite > self.z_threshold and not self.in_warmup,
            in_warmup=self.in_warmup,
        )
        return result

    def record(self, order: OrderProposal):
        """Add a processed order to the rolling window (call after scoring)."""
        self._notionals.append(order.notional)
        self._quantities.append(abs(order.quantity))

        now = time.time()
        if self._last_order_time is not None:
            self._intervals.append(now - self._last_order_time)
        self._last_order_time = now
