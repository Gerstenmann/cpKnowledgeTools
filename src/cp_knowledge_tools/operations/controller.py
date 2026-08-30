"""In-process technical run-state controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .contracts import RunState, utc_now

_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.REQUESTED: frozenset({RunState.CONTEXT_RESOLVED}),
    RunState.CONTEXT_RESOLVED: frozenset({RunState.PREFLIGHT_PASSED}),
    RunState.PREFLIGHT_PASSED: frozenset({RunState.PLANNED}),
    RunState.PLANNED: frozenset({RunState.PREVIEWED, RunState.BLOCKED}),
    RunState.PREVIEWED: frozenset({RunState.AWAITING_AUTHORITY}),
    RunState.AWAITING_AUTHORITY: frozenset({RunState.AUTHORIZED, RunState.BLOCKED}),
    RunState.AUTHORIZED: frozenset({RunState.STAGING}),
    RunState.STAGING: frozenset({RunState.APPLYING, RunState.BLOCKED}),
    RunState.APPLYING: frozenset({RunState.VERIFYING, RunState.PARTIAL_STATE_DETECTED}),
    RunState.VERIFYING: frozenset(
        {RunState.SUCCEEDED, RunState.PARTIAL_STATE_DETECTED}
    ),
    RunState.PARTIAL_STATE_DETECTED: frozenset({RunState.COMPENSATING}),
    RunState.COMPENSATING: frozenset(
        {RunState.COMPENSATED_FAILURE, RunState.FATAL_PARTIAL_STATE}
    ),
    RunState.FATAL_PARTIAL_STATE: frozenset({RunState.RECOVERY_REQUIRED}),
}


@dataclass(slots=True)
class InProcessRunController:
    state: RunState = RunState.REQUESTED
    history: list[RunState] = field(default_factory=lambda: [RunState.REQUESTED])
    clock: Callable[[], str] = utc_now
    events: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if (
            self.history == [RunState.REQUESTED]
            and self.state is not RunState.REQUESTED
        ):
            self.history = [self.state]
        if not self.events:
            self.events.append({"state": self.state.value, "occurred_at": self.clock()})

    def transition(self, target: RunState) -> None:
        allowed = _TRANSITIONS.get(self.state, frozenset())
        if target not in allowed:
            raise ValueError(f"invalid run-state transition: {self.state} -> {target}")
        self.state = target
        self.history.append(target)
        self.events.append({"state": target.value, "occurred_at": self.clock()})
