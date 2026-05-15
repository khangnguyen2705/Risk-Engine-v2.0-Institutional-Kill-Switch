"""Kill Switch — state machine with audit trail.

States
------
ARMED     → normal operation, all checks running
TRIGGERED → a critical breach occurred, rejecting all new orders
HALTED    → positions flattened, system fully stopped

Transitions
-----------
ARMED → TRIGGERED  : on any kill-switch-level breach
TRIGGERED → HALTED : after positions are flattened (or immediately)
HALTED → ARMED     : manual override with admin key only
"""

from __future__ import annotations

from datetime import datetime, timezone

from models.data_models import KillSwitchState, RiskEvent, Severity


class KillSwitch:
    """Institutional kill switch with full audit trail."""

    def __init__(self, admin_key: str = "OVERRIDE-2026"):
        self.state = KillSwitchState.ARMED
        self.admin_key = admin_key
        self.trigger_reason: str | None = None
        self.trigger_time: str | None = None
        self.events: list[RiskEvent] = []

    @property
    def is_active(self) -> bool:
        return self.state in (KillSwitchState.TRIGGERED, KillSwitchState.HALTED)

    def trigger(self, reason: str) -> list[RiskEvent]:
        """Activate the kill switch. Returns generated events."""
        if self.state != KillSwitchState.ARMED:
            # Already triggered — just log the additional attempt
            evt = RiskEvent(
                event_type="KILL_SWITCH_REDUNDANT",
                severity=Severity.CRITICAL,
                message=f"Kill switch already {self.state.value} — additional breach: {reason}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self.events.append(evt)
            return [evt]

        now = datetime.now(timezone.utc).isoformat()
        self.state = KillSwitchState.TRIGGERED
        self.trigger_reason = reason
        self.trigger_time = now

        events = [
            RiskEvent(
                event_type="KILL_SWITCH_TRIGGERED",
                severity=Severity.FATAL,
                message=f"██ KILL SWITCH TRIGGERED ██ | Reason: {reason}",
                timestamp=now,
            ),
            RiskEvent(
                event_type="KILL_SWITCH_STATE_CHANGE",
                severity=Severity.FATAL,
                message=f"State transition: ARMED → TRIGGERED",
                timestamp=now,
            ),
            RiskEvent(
                event_type="KILL_SWITCH_HALT",
                severity=Severity.FATAL,
                message="ALL TRADING HALTED — manual override required",
                timestamp=now,
            ),
        ]
        self.events.extend(events)

        # Immediately transition to HALTED
        self.state = KillSwitchState.HALTED
        return events

    def reset(self, key: str) -> list[RiskEvent]:
        """Manual override — requires admin key."""
        now = datetime.now(timezone.utc).isoformat()
        if key != self.admin_key:
            evt = RiskEvent(
                event_type="KILL_SWITCH_RESET_DENIED",
                severity=Severity.WARNING,
                message="Kill switch reset DENIED — invalid admin key",
                timestamp=now,
            )
            self.events.append(evt)
            return [evt]

        old_state = self.state.value
        self.state = KillSwitchState.ARMED
        self.trigger_reason = None
        self.trigger_time = None

        evt = RiskEvent(
            event_type="KILL_SWITCH_RESET",
            severity=Severity.INFO,
            message=f"Manual reset: {old_state} → ARMED",
            timestamp=now,
        )
        self.events.append(evt)
        return [evt]
